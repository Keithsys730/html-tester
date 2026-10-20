import os
import shutil
import time
from pathlib import Path
from typing import List, Optional, Tuple
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Error as PlaywrightError

from core.bug_detector import BugDetector, BugReportItem
from core.dom_scanner import InteractiveElement
from core.network_guard import NetworkGuard


class BrowserRunner:
    """Headless browser engine with system-browser sniffing, crash resilience, and visual capture."""

    def __init__(
        self,
        artifacts_dir: Path,
        action_timeout_ms: int = 5000,
        navigation_timeout_ms: int = 10000,
        quiescence_wait_ms: int = 400,
        headless: bool = True
    ):
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.action_timeout_ms = action_timeout_ms
        self.navigation_timeout_ms = navigation_timeout_ms
        self.quiescence_wait_ms = quiescence_wait_ms
        self.headless = headless
        self.preferred_channels = ["msedge", "chrome", None]  # None means bundled Chromium

    @staticmethod
    def _is_safe_command(cmd: str) -> bool:
        old_env = os.environ.get("NoDefaultCurrentDirectoryInExePath")
        os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"
        try:
            discovered = shutil.which(cmd)
        finally:
            if old_env is None:
                os.environ.pop("NoDefaultCurrentDirectoryInExePath", None)
            else:
                os.environ["NoDefaultCurrentDirectoryInExePath"] = old_env
        if not discovered:
            return False
        try:
            p = Path(discovered).resolve()
            cwd = Path.cwd().resolve()
            if p == cwd or p.parent == cwd or p.is_relative_to(cwd):
                return False
        except Exception:
            pass
        return True

    def detect_available_channel(self) -> Optional[str]:
        """Detects if system Edge or Chrome is installed on the host without hardcoded drives."""
        # Collect candidate installation root directories dynamically
        program_roots: List[str] = []
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            val = os.getenv(env_var)
            if val and val not in program_roots:
                program_roots.append(val)
        sys_drive = os.getenv("SystemDrive", "C:")
        for suffix in ("Program Files", "Program Files (x86)"):
            candidate_dir = f"{sys_drive}\\{suffix}"
            if candidate_dir not in program_roots:
                program_roots.append(candidate_dir)

        local_app_data = os.getenv("LOCALAPPDATA", "")
        mac_apps_dir = os.getenv("MACOS_APPLICATIONS_DIR", "/Applications")

        # 1. Edge candidates (Windows, macOS, and PATH)
        edge_paths: List[str] = [
            os.path.join(root, r"Microsoft\Edge\Application\msedge.exe")
            for root in program_roots
        ]
        if local_app_data:
            edge_paths.append(os.path.join(local_app_data, r"Microsoft\Edge\Application\msedge.exe"))
        edge_paths.append(os.path.join(mac_apps_dir, "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
        for p in edge_paths:
            if p and os.path.exists(p):
                return "msedge"
        if any(self._is_safe_command(c) for c in ("msedge", "microsoft-edge", "microsoft-edge-stable")):
            return "msedge"

        # 2. Chrome candidates (Windows, macOS, and PATH)
        chrome_paths: List[str] = [
            os.path.join(root, r"Google\Chrome\Application\chrome.exe")
            for root in program_roots
        ]
        if local_app_data:
            chrome_paths.append(os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe"))
        chrome_paths.append(os.path.join(mac_apps_dir, "Google Chrome.app/Contents/MacOS/Google Chrome"))
        for p in chrome_paths:
            if p and os.path.exists(p):
                return "chrome"
        if any(self._is_safe_command(c) for c in ("chrome", "google-chrome", "google-chrome-stable")):
            return "chrome"

        return None

    def run_tests(
        self,
        url: str,
        elements: List[InteractiveElement],
        network_guard: Optional[NetworkGuard] = None,
        max_budget: int = 2
    ) -> List[BugReportItem]:
        bugs: List[BugReportItem] = []
        bug_seq = 1

        with sync_playwright() as p:
            channel = self.detect_available_channel()
            launch_args = {
                "headless": self.headless,
                "args": ["--mute-audio", "--no-sandbox", "--disable-gpu"]
            }
            if channel:
                launch_args["channel"] = channel

            try:
                browser: Browser = p.chromium.launch(**launch_args)
            except Exception:
                # Fallback to standard chromium if channel launch fails
                launch_args.pop("channel", None)
                browser = p.chromium.launch(**launch_args)

            context: BrowserContext = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1280, "height": 800}
            )

            page: Page = context.new_page()
            page.set_default_timeout(self.action_timeout_ms)

            # 1. Native Dialog Guard
            page.on("dialog", lambda dialog: dialog.dismiss())

            # 2. Capture Unhandled JS Exceptions
            captured_page_errors: List[str] = []

            def on_page_error(err):
                captured_page_errors.append(str(err))

            page.on("pageerror", on_page_error)

            # 3. Capture Network Failures
            captured_request_failures: List[Tuple[str, str]] = []

            def on_request_failed(request):
                # Ignore aborted calls by router
                failure = request.failure
                if failure and "aborted" not in failure.lower():
                    captured_request_failures.append((request.url, failure))

            page.on("requestfailed", on_request_failed)

            # 4. Attach Outbound Network Sandboxing
            if network_guard:
                network_guard.attach(page)

            # Load Page
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
                # Brief quiescence wait for dynamic hydration
                page.wait_for_timeout(self.quiescence_wait_ms)
            except Exception as e:
                bugs.append(
                    BugDetector.classify_js_error(
                        bug_id=f"BUG-{bug_seq:03d}",
                        error_msg=f"Page navigation failed: {e}",
                        stack="Navigation Phase",
                        element=None
                    )
                )
                browser.close()
                return bugs

            # Record page load errors
            for err in captured_page_errors:
                shot_path = str(self.artifacts_dir / f"BUG-{bug_seq:03d}.png")
                try:
                    page.screenshot(path=shot_path)
                except Exception:
                    shot_path = None
                bugs.append(
                    BugDetector.classify_js_error(
                        bug_id=f"BUG-{bug_seq:03d}",
                        error_msg=err,
                        stack="Global Window Runtime Error",
                        element=None,
                        screenshot=shot_path
                    )
                )
                bug_seq += 1
            captured_page_errors.clear()

            # Record initial asset 404s
            for fail_url, fail_reason in captured_request_failures:
                bugs.append(
                    BugDetector.classify_resource_404(
                        bug_id=f"BUG-{bug_seq:03d}",
                        url=fail_url,
                        failure_text=fail_reason
                    )
                )
                bug_seq += 1
            captured_request_failures.clear()

            # 5. Dynamic Element Interaction
            for elem in elements:
                try:
                    locator = None
                    if elem.xpath:
                        try:
                            candidate = page.locator(f"xpath={elem.xpath}").first
                            if candidate.count() > 0:
                                locator = candidate
                        except Exception:
                            locator = None

                    if locator is None and elem.selector:
                        locator = page.locator(elem.selector).first

                    if locator is None or not locator.is_visible() or not locator.is_enabled():
                        continue

                    # Scroll into view
                    locator.scroll_into_view_if_needed(timeout=1000)

                    # Perform action based on element type
                    input_type = elem.attributes.get("type", "").lower()
                    if (
                        elem.tag == "button"
                        or elem.tag == "a"
                        or elem.attributes.get("onclick")
                        or (elem.tag == "input" and input_type in ["submit", "button", "reset"])
                    ):
                        locator.click(timeout=self.action_timeout_ms)
                    elif elem.tag == "select":
                        options = locator.locator("option").all()
                        if len(options) > 1:
                            locator.select_option(index=1, timeout=self.action_timeout_ms)
                    elif elem.tag == "input":
                        if input_type in ["checkbox", "radio"]:
                            locator.click(timeout=self.action_timeout_ms)
                        elif input_type not in ["hidden", "submit", "button", "reset"]:
                            locator.fill("test-value", timeout=self.action_timeout_ms)

                    # Check if interaction generated new uncaught errors
                    page.wait_for_timeout(100)
                    if captured_page_errors:
                        for err in captured_page_errors:
                            shot_path = str(self.artifacts_dir / f"BUG-{bug_seq:03d}.png")
                            try:
                                page.screenshot(path=shot_path)
                            except Exception:
                                shot_path = None

                            bugs.append(
                                BugDetector.classify_js_error(
                                    bug_id=f"BUG-{bug_seq:03d}",
                                    error_msg=err,
                                    stack=f"Error after interacting with {elem.selector}",
                                    element=elem,
                                    screenshot=shot_path
                                )
                            )
                            bug_seq += 1
                        captured_page_errors.clear()

                except PlaywrightError as pe:
                    # Timeout or unclickable element is not necessarily a hard bug
                    continue
                except Exception as ex:
                    continue

            browser.close()

        return bugs
