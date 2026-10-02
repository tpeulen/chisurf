"""Plain text of the view model's small HTML report (the canvas has no rich text)."""

import html
import re

_BREAKS = re.compile(r"<\s*(?:br|p|div)\s*/?>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def plain(rich: str) -> str:
    """The HTML of ``info_html`` as lines of text."""
    return html.unescape(_TAGS.sub("", _BREAKS.sub("\n", rich))).strip()
