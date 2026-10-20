import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from core.bug_detector import BugReportItem
from core.dom_scanner import DOMScanner
from core.llm_gateway import LLMGateway


class AutoFixer:
    """Orchestrates surgical code fixes with anti-cheating review and atomic backup/rollback."""

    def __init__(self, backup_dir: Path, llm_gateway: LLMGateway):
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm_gateway

    def create_backup(self, target_file: Path) -> Path:
        dest = self.backup_dir / f"{target_file.name}.orig"
        shutil.copy2(target_file, dest)
        return dest

    def restore_backup(self, target_file: Path) -> None:
        src = self.backup_dir / f"{target_file.name}.orig"
        if src.exists():
            shutil.copy2(src, target_file)

    def attempt_fix(self, target_file: Path, bug: BugReportItem) -> Tuple[bool, str]:
        """Attempts to fix a bug in target_file. Returns (success, diff_or_reason)."""
        if not self.llm.has_any_provider:
            return False, "No LLM API Key configured; running in test-only mode."

        content, encoding = DOMScanner.read_file_safely(target_file)
        dom_slice = DOMScanner.extract_dom_slice(content, bug.line_number, context_lines=20)

        system_prompt = (
            "You are an expert Frontend Surgical Code Fixer. "
            "Your task is to fix a deterministic JavaScript / DOM bug in an HTML file.\n"
            "ANTI-CHEATING CONTRACT:\n"
            "1. NEVER delete the element, event listener, or button to bypass the error.\n"
            "2. NEVER replace the logic with an empty no-op function.\n"
            "3. Provide ONLY a minimal targeted replacement chunk.\n"
            "Output Format:\n"
            "SEARCH:\n"
            "<exact lines to find>\n"
            "REPLACE:\n"
            "<replacement lines>\n"
        )

        user_prompt = (
            f"Target Bug: {bug.bug_id} ({bug.category})\n"
            f"Selector: {bug.selector}\n"
            f"Error details:\n{bug.observed_result}\n\n"
            f"Local Source Code Context:\n{dom_slice}\n\n"
            "Please output the SEARCH and REPLACE blocks to fix this error."
        )

        response = self.llm.generate(user_prompt, system_prompt=system_prompt)
        if not response or "SEARCH:" not in response or "REPLACE:" not in response:
            return False, "LLM did not return a valid SEARCH/REPLACE patch block."

        try:
            search_part = response.split("SEARCH:")[1].split("REPLACE:")[0].strip()
            replace_part = response.split("REPLACE:")[1].strip()

            # Anti-cheating check 1: check if replace block is empty or no-op
            clean_replace = re.sub(r"/\*.*?\*/|//.*?$|\s+", "", replace_part, flags=re.MULTILINE)
            if not clean_replace:
                return False, "Anti-cheating violation: replacement cannot be empty or pure whitespace/comments."

            if clean_replace in ["return;", "function(){return;}", "()=>{return;}"]:
                return False, "Anti-cheating violation: replacement cannot be a no-op return."

            if search_part not in content:
                return False, "Patch target not found in source file."

            # Snapshot element inventory before applying patch
            old_elements = DOMScanner.scan_interactive_elements(content)

            # Apply replacement tentatively
            patched_content = content.replace(search_part, replace_part, 1)

            # Verify patched DOM integrity and anti-cheating invariants
            new_elements = DOMScanner.scan_interactive_elements(patched_content)

            # Anti-cheating check 2: Interactive elements must not decrease
            if len(new_elements) < len(old_elements):
                return False, "Anti-cheating violation: interactive elements were removed."

            # Anti-cheating check 3: Target element must still exist and keep its handler
            if bug.selector:
                old_matching = [e for e in old_elements if e.selector == bug.selector]
                new_matching = [e for e in new_elements if e.selector == bug.selector]
                if old_matching and not new_matching:
                    return False, f"Anti-cheating violation: target element {bug.selector} was removed."
                if old_matching and new_matching:
                    old_el = old_matching[0]
                    new_el = new_matching[0]
                    if "onclick" in old_el.attributes and "onclick" not in new_el.attributes:
                        return False, f"Anti-cheating violation: onclick handler was stripped from {bug.selector}."

            target_file.write_text(patched_content, encoding=encoding)
            diff_summary = f"--- Original\n+++ Fixed\n- {search_part}\n+ {replace_part}"
            return True, diff_summary
        except Exception as e:
            return False, f"Failed to apply patch: {e}"
