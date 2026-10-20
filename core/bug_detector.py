from dataclasses import dataclass
from typing import Optional


@dataclass
class BugReportItem:
    bug_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str  # JS_RUNTIME_ERROR, RESOURCE_NOT_FOUND, UNRESPONSIVE_CLICKABLE, etc.
    selector: str
    xpath: str
    line_number: Optional[int]
    outer_html: str
    trigger_action: str
    observed_result: str
    repro_script: str
    screenshot_path: Optional[str] = None
    remediation_guidance: Optional[str] = None


class BugDetector:
    """Classifies anomalies into deterministic severities and standard bug records."""

    @staticmethod
    def classify_js_error(bug_id: str, error_msg: str, stack: str, element=None, screenshot=None) -> BugReportItem:
        return BugReportItem(
            bug_id=bug_id,
            severity="CRITICAL",
            category="JS_RUNTIME_ERROR",
            selector=getattr(element, "selector", "window"),
            xpath=getattr(element, "xpath", "//html"),
            line_number=getattr(element, "line_number", None),
            outer_html=getattr(element, "outer_html", "<script>"),
            trigger_action=f"Interact with {getattr(element, 'selector', 'page')}",
            observed_result=f"Uncaught Exception: {error_msg}\nStack trace:\n{stack}",
            repro_script=f"// Trigger: navigate to page, click {getattr(element, 'selector', 'target')}",
            screenshot_path=screenshot,
            remediation_guidance="Fix underlying JavaScript syntax, undeclared identifier, or unhandled promise rejection."
        )

    @staticmethod
    def classify_resource_404(bug_id: str, url: str, failure_text: str) -> BugReportItem:
        return BugReportItem(
            bug_id=bug_id,
            severity="HIGH",
            category="RESOURCE_NOT_FOUND",
            selector="link, script, img",
            xpath="//head | //body",
            line_number=None,
            outer_html=f'<asset src="{url}">',
            trigger_action="Page load asset request",
            observed_result=f"Asset failed to load: {url} (reason: {failure_text})",
            repro_script=f"// Inspect asset link at {url}",
            screenshot_path=None,
            remediation_guidance="Verify local asset relative path or ensure referenced resource is bundled."
        )
