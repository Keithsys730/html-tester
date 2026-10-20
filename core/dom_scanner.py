from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup, Tag


@dataclass
class InteractiveElement:
    tag: str
    element_type: str  # button, select, input, form, anchor, etc.
    selector: str
    xpath: str
    outer_html: str
    line_number: Optional[int]
    attributes: dict


class DOMScanner:
    """Scans and extracts interactive DOM nodes with robust encoding and line locator."""

    ENCODINGS = ["utf-8", "utf-8-sig", "cp950", "gbk", "latin-1"]

    @classmethod
    def read_file_safely(cls, file_path: Path) -> Tuple[str, str]:
        """Reads file attempting multiple encodings, returns (content, detected_encoding)."""
        raw_bytes = file_path.read_bytes()
        for enc in cls.ENCODINGS:
            try:
                text = raw_bytes.decode(enc)
                return text, enc
            except (UnicodeDecodeError, LookupError):
                continue
        return raw_bytes.decode("utf-8", errors="replace"), "utf-8"

    @classmethod
    def scan_interactive_elements(cls, html_content: str) -> List[InteractiveElement]:
        soup = BeautifulSoup(html_content, "html.parser")
        results: List[InteractiveElement] = []

        # Find buttons, inputs, selects, textareas, forms, and anchors
        interactive_tags = ["button", "input", "select", "textarea", "form", "a"]
        all_candidates = soup.find_all(interactive_tags)

        # Also find elements with onclick attribute
        onclick_elements = soup.find_all(lambda el: el.has_attr("onclick") if isinstance(el, Tag) else False)
        # Deterministic document order preservation
        merged_list = list(dict.fromkeys(all_candidates + onclick_elements))

        for el in merged_list:
            if not isinstance(el, Tag):
                continue

            tag_name = el.name.lower()
            element_type = tag_name
            if tag_name == "input":
                element_type = f"input[{el.get('type', 'text')}]"

            selector = cls._build_css_selector(el)
            xpath = cls._build_xpath(el)
            outer_html = str(el)
            line_no = getattr(el, "sourceline", None)

            results.append(
                InteractiveElement(
                    tag=tag_name,
                    element_type=element_type,
                    selector=selector,
                    xpath=xpath,
                    outer_html=outer_html,
                    line_number=line_no,
                    attributes=dict(el.attrs),
                )
            )

        return results

    @classmethod
    def _build_css_selector(cls, el: Tag) -> str:
        if el.get("id"):
            return f"{el.name}#{el.get('id')}"
        classes = el.get("class", [])
        if classes:
            class_str = ".".join(classes)
            return f"{el.name}.{class_str}"
        name_attr = el.get("name")
        if name_attr:
            return f"{el.name}[name=\"{name_attr}\"]"
        return el.name

    @classmethod
    def _build_xpath(cls, el: Tag) -> str:
        if el.get("id"):
            return f"//{el.name}[@id='{el.get('id')}']"
        # Calculate positional index among siblings with same tag
        parent = el.parent
        if parent and isinstance(parent, Tag) and parent.name and parent.name != "[document]":
            siblings = [sib for sib in parent.children if isinstance(sib, Tag) and sib.name == el.name]
            if len(siblings) > 1:
                idx = siblings.index(el) + 1
                return f"({cls._build_xpath(parent)}/{el.name})[{idx}]"
            return f"{cls._build_xpath(parent)}/{el.name}"
        return f"//{el.name}"

    @classmethod
    def extract_dom_slice(cls, html_content: str, line_no: Optional[int], context_lines: int = 25) -> str:
        """Extracts localized source code around target line to prevent token explosion."""
        lines = html_content.splitlines()
        if not line_no or line_no > len(lines):
            return "\n".join(lines[: context_lines * 2])
        start = max(0, line_no - context_lines - 1)
        end = min(len(lines), line_no + context_lines)
        return "\n".join(f"{idx+1:4d} | {line}" for idx, line in enumerate(lines[start:end], start=start))
