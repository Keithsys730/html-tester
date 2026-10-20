"""Tests for dynamic path resolution, macOS bundle detection, config wiring, and CWD hijacking defense."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.browser_runner import BrowserRunner
from core.llm_gateway import LLMGateway
from html_tester import load_config


def test_no_hardcoded_git_or_drive_paths_in_production_files():
    """Verify hardcoded absolute paths are eliminated from production files."""
    prod_files = [
        ROOT / "core" / "browser_runner.py",
        ROOT / "core" / "bug_detector.py",
        ROOT / "core" / "dom_scanner.py",
        ROOT / "core" / "fixer.py",
        ROOT / "core" / "llm_gateway.py",
        ROOT / "core" / "network_guard.py",
        ROOT / "core" / "server.py",
        ROOT / "html_tester.py",
        ROOT / "reporter.py",
        ROOT / "run.bat",
        ROOT / "run.sh",
    ]
    for file_path in prod_files:
        assert file_path.is_file(), f"Missing production file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "C:/Program Files/Git" not in content, f"Found hardcoded path in {file_path}"
        assert "C:\\Program Files\\Git" not in content, f"Found hardcoded path in {file_path}"
        assert "D:\\AI_Code_Workspace" not in content, f"Found hardcoded workspace path in {file_path}"


def test_browser_runner_detect_available_channel_dynamic(tmp_path, monkeypatch):
    """Test BrowserRunner.detect_available_channel resolves dynamically via environment roots."""
    artifacts = tmp_path / "artifacts"
    runner = BrowserRunner(artifacts_dir=artifacts)

    # Default environment run should not crash and return valid channel or None
    channel = runner.detect_available_channel()
    assert channel in ("msedge", "chrome", None)

    # Test with simulated mock ProgramFiles containing mock Edge
    mock_program_files = tmp_path / "ProgramFiles"
    mock_edge = mock_program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    mock_edge.parent.mkdir(parents=True, exist_ok=True)
    mock_edge.write_text("fake edge", encoding="utf-8")

    monkeypatch.setenv("ProgramFiles", str(mock_program_files))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "empty_pfx86"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty_localappdata"))
    monkeypatch.setenv("MACOS_APPLICATIONS_DIR", str(tmp_path / "empty_mac_apps"))
    monkeypatch.setenv("PATH", "")

    detected = runner.detect_available_channel()
    assert detected == "msedge"


def test_browser_runner_detect_available_channel_macos_bundle(tmp_path, monkeypatch):
    """Test BrowserRunner detects macOS Google Chrome.app bundle when Windows paths are empty."""
    artifacts = tmp_path / "artifacts"
    runner = BrowserRunner(artifacts_dir=artifacts)

    mac_apps = tmp_path / "Applications"
    mac_chrome = mac_apps / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
    mac_chrome.parent.mkdir(parents=True, exist_ok=True)
    mac_chrome.write_text("fake mac chrome", encoding="utf-8")

    monkeypatch.setenv("ProgramFiles", str(tmp_path / "non_existent_pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "non_existent_pf86"))
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "non_existent_pfw64"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "non_existent_lad"))
    monkeypatch.setenv("SystemDrive", str(tmp_path / "non_existent_sd"))
    monkeypatch.setenv("MACOS_APPLICATIONS_DIR", str(mac_apps))
    monkeypatch.setenv("PATH", "")

    assert runner.detect_available_channel() == "chrome"


def test_browser_runner_ignores_decoy_browser_in_cwd(tmp_path, monkeypatch):
    """Test BrowserRunner ignores decoy browser executables located in CWD."""
    artifacts = tmp_path / "artifacts"
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    decoy_edge = cwd_dir / ("msedge.exe" if os.name == "nt" else "msedge")
    decoy_edge.write_text("fake edge", encoding="utf-8")

    monkeypatch.chdir(cwd_dir)
    monkeypatch.setenv("PATH", str(cwd_dir))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "non_existent_pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "non_existent_pf86"))
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "non_existent_pfw64"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "non_existent_lad"))
    monkeypatch.setenv("SystemDrive", str(tmp_path / "non_existent_sd"))
    monkeypatch.setenv("MACOS_APPLICATIONS_DIR", str(tmp_path / "non_existent_mac"))

    runner = BrowserRunner(artifacts_dir=artifacts)
    assert runner.detect_available_channel() is None


def test_load_config_and_llm_gateway_wiring(tmp_path, monkeypatch):
    """Verify config.yaml is loaded and honors custom timeouts and LLM settings."""
    cfg = load_config()
    assert cfg.get("browser", {}).get("action_timeout_ms") == 5000
    assert cfg.get("llm", {}).get("max_heal_rounds") == 3

    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    gw_disabled = LLMGateway(env_path=tmp_path / ".env", llm_config={"enabled": False})
    assert gw_disabled.has_any_provider is False
    assert gw_disabled.generate("hello") is None
