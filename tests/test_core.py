import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock

from core.dom_scanner import DOMScanner
from core.server import EphemeralLocalServer
from core.network_guard import NetworkGuard
from core.bug_detector import BugDetector, BugReportItem
from core.fixer import AutoFixer
from core.llm_gateway import LLMGateway
from reporter import ReportGenerator


def test_dom_scanner_and_encoding():
    sample_html = """<!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <button id="btn-submit" onclick="submitForm()">Submit</button>
        <button>First No-ID</button>
        <button>Second No-ID</button>
        <select name="city"><option value="tpe">Taipei</option></select>
        <input type="submit" value="Send">
    </body>
    </html>"""

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as f:
        f.write(sample_html)
        tmp_path = Path(f.name)

    try:
        content, enc = DOMScanner.read_file_safely(tmp_path)
        assert enc == "utf-8"
        elements = DOMScanner.scan_interactive_elements(content)
        selectors = [e.selector for e in elements]
        assert "button#btn-submit" in selectors
        assert "input[submit]" in [e.element_type for e in elements]
        # Verify unique xpaths for sibling buttons and no [document] syntax error
        no_id_xpaths = [e.xpath for e in elements if e.tag == "button" and "id" not in e.attributes]
        assert len(no_id_xpaths) == 2
        assert no_id_xpaths[0] != no_id_xpaths[1]
        for xpath in [e.xpath for e in elements]:
            assert "[document]" not in xpath, f"XPath contains illegal [document] node: {xpath}"
    finally:
        tmp_path.unlink()


def test_ephemeral_server_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
        with EphemeralLocalServer(serve_dir=tmp_path) as server:
            assert server.port > 0
            assert server.base_url.startswith("http://127.0.0.1:")
            assert server.httpd is not None
        # Verify stopped after context exit
        assert server.httpd is None


def test_network_guard_resource_types():
    guard = NetworkGuard(local_base_url="http://127.0.0.1:8000")
    page_mock = MagicMock()
    captured_routes = {}

    def mock_route_fn(pattern, handler):
        captured_routes[pattern] = handler

    page_mock.route = mock_route_fn
    guard.attach(page_mock)

    handler = captured_routes["**/*"]

    # 1. External Script request
    script_route = MagicMock()
    script_route.request.url = "https://cdn.tailwindcss.com"
    script_route.request.resource_type = "script"
    handler(script_route)
    script_route.fulfill.assert_called_once_with(
        status=200,
        content_type="application/javascript",
        body="/* mocked by html_tester */"
    )

    # 2. External Stylesheet request
    css_route = MagicMock()
    css_route.request.url = "https://cdn.example.com/style.css"
    css_route.request.resource_type = "stylesheet"
    handler(css_route)
    css_route.fulfill.assert_called_once_with(
        status=200,
        content_type="text/css",
        body="/* mocked by html_tester */"
    )


def test_fixer_anti_cheating_prevents_handler_removal():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir = Path(tmpdir)
        target = tmp_dir / "target.html"
        target.write_text('<button id="btn" onclick="broken()">Click</button>', encoding="utf-8")

        mock_llm = MagicMock(spec=LLMGateway)
        mock_llm.has_any_provider = True
        # LLM maliciously tries to remove the onclick handler to make tests green
        mock_llm.generate.return_value = 'SEARCH:\n<button id="btn" onclick="broken()">Click</button>\nREPLACE:\n<button id="btn">Click</button>'

        fixer = AutoFixer(backup_dir=tmp_dir / "backup", llm_gateway=mock_llm)
        bug = BugReportItem(
            bug_id="BUG-001",
            severity="CRITICAL",
            category="JS_RUNTIME_ERROR",
            selector="button#btn",
            xpath="//button[@id='btn']",
            line_number=1,
            outer_html='<button id="btn" onclick="broken()">Click</button>',
            trigger_action="Click",
            observed_result="broken is not defined",
            repro_script=""
        )

        success, reason = fixer.attempt_fix(target, bug)
        assert success is False
        assert "Anti-cheating violation" in reason
        # Verify content was NOT modified
        assert 'onclick="broken()"' in target.read_text(encoding="utf-8")


def test_report_generator_formatting():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        target = out_dir / "test.html"
        target.write_text("<p>hi</p>", encoding="utf-8")

        bug = BugReportItem(
            bug_id="BUG-001",
            severity="CRITICAL",
            category="JS_RUNTIME_ERROR",
            selector="button#leak",
            xpath="//button",
            line_number=10,
            outer_html="<button>",
            trigger_action="Click",
            observed_result="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and password=\"secret123\"",
            repro_script="",
        )

        rep = ReportGenerator.generate_report(
            target_file=target,
            elements_count=1,
            bugs=[bug],
            output_dir=out_dir,
            diff_log=["- old\n+ new"]
        )
        content = rep.read_text(encoding="utf-8")
        assert "[REDACTED_TOKEN]" in content
        assert "[REDACTED_PASSWORD]" in content
        assert "```diff" in content
