"""Passive rich HTML notebook output, mapped to native text and tables."""

from __future__ import annotations

from html.parser import HTMLParser


class HtmlOutputParser(HTMLParser):
    """Preserve visible formatting and tables without a browser or script runtime."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.text = []
        self.rows = None
        self.row = None
        self.cell = None
        self.ignore = 0
        self._links = []

    def _append(self, value: str) -> None:
        (self.cell if self.cell is not None else self.text).append(value)

    def _flush(self) -> None:
        content = "".join(self.text).strip()
        if content:
            self.blocks.append(("markdown", content))
        self.text.clear()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ("script", "style"):
            self.ignore += 1
            return
        if self.ignore:
            return
        if tag == "table":
            self._flush()
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "img":
            if self.cell is not None:
                self._append(values.get("alt", "Image"))
            else:
                self._flush()
                self.blocks.append(("image", values))
        elif tag in ("p", "div"):
            self._append("\n\n")
        elif tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
            self._append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "br":
            self._append("\n")
        elif tag in ("b", "strong"):
            self._append("**")
        elif tag in ("i", "em"):
            self._append("*")
        elif tag == "pre":
            self._append("\n```\n")
        elif tag == "code":
            self._append("`")
        elif tag == "li":
            self._append("\n- ")
        elif tag == "a":
            self._links.append(values.get("href", ""))
            self._append("[")
        elif tag == "sup":
            self._append("^(")
        elif tag == "sub":
            self._append("_(")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignore = max(0, self.ignore - 1)
            return
        if self.ignore:
            return
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.blocks.append(("table", self.rows))
            self.rows = None
        elif tag in ("p", "div", "ul", "ol") or (
            tag.startswith("h") and len(tag) == 2 and tag[1].isdigit()
        ):
            self._append("\n\n")
        elif tag in ("b", "strong"):
            self._append("**")
        elif tag in ("i", "em"):
            self._append("*")
        elif tag == "pre":
            self._append("\n```\n")
        elif tag == "code":
            self._append("`")
        elif tag == "a" and self._links:
            self._append("](" + self._links.pop() + ")")
        elif tag in ("sub", "sup"):
            self._append(")")

    def handle_data(self, data):
        if not self.ignore:
            self._append(data)

    def finish(self):
        self._flush()
        return self.blocks


def html_blocks(source: str):
    """Return native-renderable text, table and image blocks from passive HTML."""
    parser = HtmlOutputParser()
    parser.feed(source)
    parser.close()
    return parser.finish()
