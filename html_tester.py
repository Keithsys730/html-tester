import argparse
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.browser_runner import BrowserRunner
from core.dom_scanner import DOMScanner
from core.fixer import AutoFixer
from core.llm_gateway import LLMGateway
from core.network_guard import NetworkGuard
from core.server import EphemeralLocalServer
from reporter import ReportGenerator

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
ARTIFACTS_DIR = OUTPUT_DIR / "artifacts"
FIXED_DIR = OUTPUT_DIR / "fixed"
BACKUP_DIR = BASE_DIR / "backup"
CONFIG_PATH = BASE_DIR / "config.yaml"


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    target = config_path or CONFIG_PATH
    if target.exists():
        try:
            data = yaml.safe_load(target.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def run_diagnose(config: Optional[Dict[str, Any]] = None) -> None:
    cfg = config if config is not None else load_config()
    browser_cfg = cfg.get("browser", {}) if isinstance(cfg.get("browser"), dict) else {}
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm"), dict) else {}

    runner = BrowserRunner(
        artifacts_dir=ARTIFACTS_DIR,
        action_timeout_ms=int(browser_cfg.get("action_timeout_ms", 5000)),
        navigation_timeout_ms=int(browser_cfg.get("navigation_timeout_ms", 10000)),
        quiescence_wait_ms=int(browser_cfg.get("quiescence_wait_ms", 400)),
        headless=bool(browser_cfg.get("headless", True))
    )
    detected_channel = runner.detect_available_channel()
    gateway = LLMGateway(llm_config=llm_cfg)

    print("=======================================================")
    print("=== HTML Tester Standalone Environment Diagnostic ===")
    print("=======================================================")
    print(f"OS: {platform.system()} {platform.release()} (Architecture: {platform.machine()})")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Script Directory: {BASE_DIR}")
    print(f"System Browser Detected: {detected_channel or 'None (using standard Chromium)'}")
    print(f"LLM Key Configured: {'Yes' if gateway.has_any_provider else 'No (test-only mode)'}")
    print("Directories:")
    print(f"  - input/: {INPUT_DIR.exists()}")
    print(f"  - output/: {OUTPUT_DIR.exists()}")
    print(f"  - backup/: {BACKUP_DIR.exists()}")
    print("=======================================================")


def test_file(
    html_file: Path,
    mode: str = "test",
    max_heal_rounds: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None
) -> bool:
    cfg = config if config is not None else load_config()
    browser_cfg = cfg.get("browser", {}) if isinstance(cfg.get("browser"), dict) else {}
    scanner_cfg = cfg.get("scanner", {}) if isinstance(cfg.get("scanner"), dict) else {}
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm"), dict) else {}

    effective_heal_rounds = (
        max_heal_rounds
        if max_heal_rounds is not None
        else int(llm_cfg.get("max_heal_rounds", 3))
    )
    max_budget = int(scanner_cfg.get("max_interactive_budget_per_element", 2))

    print(f"\n[+] Processing Target: {html_file.name}")
    content, enc = DOMScanner.read_file_safely(html_file)
    elements = DOMScanner.scan_interactive_elements(content)
    print(f"    - Encoding: {enc}")
    print(f"    - Discovered Interactive Elements: {len(elements)}")

    runner = BrowserRunner(
        artifacts_dir=ARTIFACTS_DIR,
        action_timeout_ms=int(browser_cfg.get("action_timeout_ms", 5000)),
        navigation_timeout_ms=int(browser_cfg.get("navigation_timeout_ms", 10000)),
        quiescence_wait_ms=int(browser_cfg.get("quiescence_wait_ms", 400)),
        headless=bool(browser_cfg.get("headless", True))
    )
    llm_gateway = LLMGateway(llm_config=llm_cfg)
    fixer = AutoFixer(backup_dir=BACKUP_DIR, llm_gateway=llm_gateway)
    diff_log = []
    current_bugs = []

    # 1. Ephemeral Local HTTP Server with Context Manager (guarantees socket cleanup)
    with EphemeralLocalServer(serve_dir=html_file.parent) as server:
        base_url = server.base_url
        test_url = f"{base_url}/{html_file.name}"
        print(f"    - Local Server: {test_url}")

        guard = NetworkGuard(local_base_url=base_url)
        current_bugs = runner.run_tests(test_url, elements, network_guard=guard, max_budget=max_budget)

        # 2. Closed-Loop Healing (if mode == 'fix')
        if mode == "fix" and current_bugs:
            print(f"    - Found {len(current_bugs)} bugs. Initializing Auto-Heal Loop...")
            fixer.create_backup(html_file)
            heal_succeeded = False

            try:
                for round_idx in range(1, effective_heal_rounds + 1):
                    print(f"      [Round {round_idx}/{effective_heal_rounds}] Attempting surgical repair...")
                    for bug in current_bugs:
                        success, diff_or_reason = fixer.attempt_fix(html_file, bug)
                        if success:
                            diff_log.append(diff_or_reason)
                            print(f"        -> Applied fix for {bug.bug_id}")
                        else:
                            print(f"        -> Failed to fix {bug.bug_id}: {diff_or_reason}")

                    # Re-test after repairs
                    content_updated, _ = DOMScanner.read_file_safely(html_file)
                    elements_updated = DOMScanner.scan_interactive_elements(content_updated)
                    current_bugs = runner.run_tests(test_url, elements_updated, network_guard=guard, max_budget=max_budget)

                    if not current_bugs:
                        print("      [✓] All bugs resolved and verified green!")
                        fixed_dest = FIXED_DIR / html_file.name
                        shutil.copy2(html_file, fixed_dest)
                        print(f"      [✓] Fixed file exported to: {fixed_dest}")
                        heal_succeeded = True
                        break
            finally:
                # If healing was attempted but failed to turn green, restore original backup to prevent data loss
                if not heal_succeeded:
                    print("      [!] Healing did not achieve green status; rolling back to original state.")
                    fixer.restore_backup(html_file)

    # 3. Generate Report
    final_verdict = "PASS" if not current_bugs else ("RESOLVED" if diff_log and not current_bugs else "FAIL")
    rep_path = ReportGenerator.generate_report(
        target_file=html_file,
        elements_count=len(elements),
        bugs=current_bugs,
        output_dir=REPORTS_DIR,
        diff_log=diff_log,
        final_verdict=final_verdict
    )
    print(f"    - Generated AI Report: {rep_path.relative_to(BASE_DIR)}")
    print(f"    - Status: {final_verdict}")
    return final_verdict in ("PASS", "RESOLVED")


def main():
    parser = argparse.ArgumentParser(description="Standalone Portable HTML Testing & Self-Healing Agent")
    parser.add_argument("--mode", choices=["test", "fix"], default="test", help="Execution mode: test (only) or fix (closed-loop heal)")
    parser.add_argument("--target", type=str, help="Specific .html file path to test")
    parser.add_argument("--diagnose", action="store_true", help="Run environment diagnostic check")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any target file has unresolved defects (useful for CI/CD)")

    args = parser.parse_args()
    cfg = load_config()

    if args.diagnose:
        run_diagnose(config=cfg)
        return

    # Ensure output folders exist
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    FIXED_DIR.mkdir(parents=True, exist_ok=True)

    any_failed = False

    if args.target:
        target_path = Path(args.target).resolve()
        if not target_path.exists():
            print(f"Error: Target file does not exist: {target_path}")
            sys.exit(1)
        passed = test_file(target_path, mode=args.mode, config=cfg)
        if not passed:
            any_failed = True
    else:
        # Scan input/ directory (supports both top-level and subdirectories, .html and .htm)
        candidates = list(INPUT_DIR.rglob("*.html")) + list(INPUT_DIR.rglob("*.htm"))
        # Exclude hidden files or folders
        html_files = sorted(list({f for f in candidates if not f.name.startswith(".") and ".venv" not in f.parts}))
        if not html_files:
            print(f"[!] No .html or .htm files found in: {INPUT_DIR}")
            print("    Please place your target .html files (or project folders) into the input/ directory and run again.")
            return

        print(f"[*] Found {len(html_files)} HTML file(s) in input/. Starting execution...")
        for f in html_files:
            passed = test_file(f, mode=args.mode, config=cfg)
            if not passed:
                any_failed = True

    if args.strict and any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
