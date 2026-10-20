import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from core.bug_detector import BugReportItem


class ReportGenerator:
    """Generates AI-actionable Markdown reports with strict YAML frontmatter and secret redaction."""

    SECRET_PATTERNS = [
        (r'(?i)(bearer\s+)[a-z0-9_\-\.]{20,}', r'\1[REDACTED_TOKEN]'),
        (r'(?i)(password\s*[:=]\s*["\'])[^\'"]+(["\'])', r'\1[REDACTED_PASSWORD]\2'),
        (r'(?i)(api[_-]?key\s*[:=]\s*["\'])[^\'"]+(["\'])', r'\1[REDACTED_API_KEY]\2'),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        for pattern, repl in cls.SECRET_PATTERNS:
            text = re.sub(pattern, repl, text)
        return text

    @classmethod
    def generate_report(
        cls,
        target_file: Path,
        elements_count: int,
        bugs: List[BugReportItem],
        output_dir: Path,
        diff_log: Optional[List[str]] = None,
        final_verdict: Optional[str] = None
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")

        verdict = final_verdict or ("PASS" if not bugs else "FAIL")

        severities = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for b in bugs:
            k = b.severity.lower()
            if k in severities:
                severities[k] += 1

        doc = []
        doc.append("---")
        doc.append(f'target_file: "{target_file.name}"')
        doc.append(f'timestamp: "{timestamp_iso}"')
        doc.append(f'verdict: "{verdict}"')
        doc.append(f"total_elements_tested: {elements_count}")
        doc.append(f"bugs_found: {len(bugs)}")
        doc.append("severity_breakdown:")
        doc.append(f"  critical: {severities['critical']}")
        doc.append(f"  high: {severities['high']}")
        doc.append(f"  medium: {severities['medium']}")
        doc.append(f"  low: {severities['low']}")
        doc.append("---\n")

        doc.append(f"# Automated HTML Testing & Self-Healing Report\n")
        doc.append(f"- **Target File**: {target_file.resolve()}")
        doc.append(f"- **Status**: {verdict}")
        doc.append(f"- **Tested Interactive Elements**: {elements_count}")
        doc.append(f"- **Detected Anomalies**: {len(bugs)}\n")

        if diff_log:
            doc.append("## Self-Healing Audit Trail")
            for entry in diff_log:
                doc.append(f"```diff\n{entry}\n```\n")

        if not bugs:
            doc.append("## Verification Verdict")
            doc.append("> [!NOTE]")
            doc.append("> All discovered interactive controls operated cleanly without uncaught runtime errors or broken assets.\n")
        else:
            doc.append("## Detected Defect Details\n")
            for b in bugs:
                doc.append(f"### [{b.severity}] {b.bug_id}: {b.category}")
                doc.append(f"- **CSS Selector**: {b.selector}")
                doc.append(f"- **XPath**: {b.xpath}")
                if b.line_number:
                    doc.append(f"- **Estimated Line**: {b.line_number}")
                doc.append(f"- **Trigger Action**: {b.trigger_action}")
                doc.append(f"- **Observed Error**:\n```text\n{cls.redact(b.observed_result)}\n```")
                doc.append(f"- **Element Snippet**:\n```html\n{b.outer_html}\n```")
                if b.screenshot_path and Path(b.screenshot_path).exists():
                    doc.append(f"- **Visual Proof**: `artifacts/{Path(b.screenshot_path).name}`")
                if b.remediation_guidance:
                    doc.append(f"- **AI Remediation Guidance**: {b.remediation_guidance}")
                doc.append("\n---\n")

        report_filename = f"report_{target_file.stem}_{timestamp_slug}.md"
        report_path = output_dir / report_filename
        report_path.write_text("\n".join(doc), encoding="utf-8")
        return report_path
