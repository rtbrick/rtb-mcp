"""Turn rtbrick.com HTML into readable text split into sections.

Docs pages are Antora sites: the content lives in <article class="doc">, the title in
<h1 class="page">, and every h2-h6 carries an id usable as a #fragment. Pages without
that article (the marketing site) fall back to the whole body minus navigation chrome.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

_BLOCK_TAGS = {
    "p", "div", "li", "dt", "dd", "tr", "table", "ul", "ol", "dl",
    "blockquote", "br", "hr", "section", "figure", "figcaption",
}
_SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "template", "svg", "button"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_FENCE = "\x00"  # marks <pre> boundaries until tidy() turns them into ``` fences


@dataclass
class Section:
    anchor: str
    heading: str
    level: int
    text: str


@dataclass
class Page:
    url: str
    title: str
    sections: List[Section]

    def section_url(self, section: Section) -> str:
        return f"{self.url}#{section.anchor}" if section.anchor else self.url

    def to_markdown(self, sections: Optional[List[Section]] = None) -> str:
        parts = [f"# {self.title}"]
        for s in self.sections if sections is None else sections:
            if s.heading and s.level > 1:
                parts.append(f"{'#' * s.level} {s.heading}")
            if s.text:
                parts.append(s.text)
        return "\n\n".join(parts)

    def section_slice(self, query: str) -> List[Section]:
        """The section matching an anchor or heading, plus its subsections."""
        q = query.strip().lstrip("#").lower()
        start = next((i for i, s in enumerate(self.sections) if s.anchor.lower() == q), None)
        if start is None:
            start = next(
                (i for i, s in enumerate(self.sections) if q and q in s.heading.lower()), None
            )
        if start is None:
            return []
        level = self.sections[start].level
        end = start + 1
        while end < len(self.sections) and self.sections[end].level > level:
            end += 1
        return self.sections[start:end]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Page":
        return cls(
            url=data["url"],
            title=data["title"],
            sections=[Section(**s) for s in data["sections"]],
        )


class _Extractor(HTMLParser):
    def __init__(self, article_only: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.article_only = article_only
        self.found_article = False
        self.in_content = not article_only
        self.article_depth = 0
        self.skip_depth = 0
        self.pre_depth = 0
        self.cell_depth = 0
        self.cell_index = 0
        self.inline_code: Optional[List[str]] = None  # text of the open inline <code>
        self.in_title_tag = False
        self.html_title = ""
        self.page_title = ""
        self.heading: Optional[Dict[str, Any]] = None
        self.sections: List[Section] = []
        self._anchor, self._heading_text, self._level = "", "", 1
        self._buf: List[str] = []

    # -- output helpers --------------------------------------------------------

    def _emit(self, text: str) -> None:
        if self.heading is not None:
            self.heading["parts"].append(text)
        else:
            self._buf.append(text)

    def _flush(self) -> None:
        text = tidy("".join(self._buf))
        if text or self._heading_text:
            self.sections.append(Section(self._anchor, self._heading_text, self._level, text))
        self._buf = []

    def _break(self) -> None:
        self._emit(" " if self.cell_depth else "\n")

    # -- parser callbacks ------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self.in_title_tag = True
            return
        if self.article_only and tag == "article":
            if self.in_content:
                self.article_depth += 1
            elif not self.found_article and "doc" in attr.get("class", "").split():
                self.found_article = self.in_content = True
                self.article_depth = 1
            return
        if not self.in_content:
            return
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in _HEADINGS:
            self.heading = {"tag": tag, "anchor": attr.get("id", ""), "parts": []}
        elif tag == "pre":
            self.pre_depth += 1
            self._emit(_FENCE)
        elif tag == "code" and not self.pre_depth:
            self.inline_code = []
        elif tag in ("td", "th"):
            self._emit(" | " if self.cell_index else "")
            self.cell_index += 1
            self.cell_depth += 1
        elif tag == "tr":
            # Rows are separated by a single newline (see handle_endtag); a table nested
            # in a cell (admonitions) stays on the cell's line.
            self.cell_index = 0
            self._break()
        elif tag == "li":
            self._emit(" " if self.cell_depth else "\n- ")
        elif tag in _BLOCK_TAGS:
            self._break()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title_tag = False
            return
        if self.article_only and tag == "article" and self.in_content:
            self.article_depth -= 1
            if self.article_depth == 0:
                self.in_content = False
            return
        if not self.in_content:
            return
        if tag in _SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if self.heading is not None and tag == self.heading["tag"]:
            text = re.sub(r"\s+", " ", "".join(self.heading["parts"])).strip()
            level = int(tag[1])
            if level == 1 and not self.page_title:
                self.page_title = text
            else:
                self._flush()
                self._anchor, self._heading_text, self._level = self.heading["anchor"], text, level
            self.heading = None
        elif tag == "pre":
            self.pre_depth = max(0, self.pre_depth - 1)
            self._emit(_FENCE)
        elif tag == "code" and not self.pre_depth:
            self._close_inline_code()
        elif tag in ("td", "th"):
            self.cell_depth = max(0, self.cell_depth - 1)
        elif tag in _BLOCK_TAGS and tag != "tr":
            self._break()

    def handle_data(self, data: str) -> None:
        if self.in_title_tag:
            self.html_title += data
            return
        if not self.in_content or self.skip_depth:
            return
        if self.pre_depth:
            self._emit(data)
        elif self.inline_code is not None:
            # Nested tags (<em>peer</em>) split the text; keep the spaces between parts.
            self.inline_code.append(data)
        else:
            self._emit(re.sub(r"\s+", " ", data))

    def _close_inline_code(self) -> None:
        if self.inline_code is None:
            return
        code = re.sub(r"\s+", " ", "".join(self.inline_code)).strip()
        self.inline_code = None
        if code:
            self._emit(f"`{code}`")

    def close(self) -> None:
        super().close()
        self._close_inline_code()
        self._flush()


def tidy(raw: str) -> str:
    """Normalise whitespace outside code blocks and fence the code blocks."""
    out = []
    for i, segment in enumerate(raw.split(_FENCE)):
        if i % 2:  # inside <pre>
            code = segment.strip("\n")
            if code.strip():
                out.append(f"\n```\n{code}\n```\n")
        else:
            lines = (re.sub(r"[ \t]+", " ", line).strip() for line in segment.split("\n"))
            out.append("\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def _parse(html: str, article_only: bool) -> _Extractor:
    parser = _Extractor(article_only)
    parser.feed(html)
    parser.close()
    return parser


def extract_page(html: str, url: str) -> Page:
    parser = _parse(html, article_only=True)
    if not parser.found_article:
        parser = _parse(html, article_only=False)
    title = parser.page_title or parser.html_title.split(" :: ")[0].strip() or url
    return Page(url=url, title=title, sections=parser.sections)


def looks_like_html(text: str) -> bool:
    head = text[:4096].lstrip().lower()
    return head.startswith("<!doctype html") or "<html" in head or "<body" in head


def to_page(text: str, url: str) -> Page:
    """Extract HTML; keep any other text (JSON, YAML, plain text) exactly as served."""
    if looks_like_html(text):
        return extract_page(text, url)
    return Page(url=url, title=url, sections=[Section("", "", 1, text)])
