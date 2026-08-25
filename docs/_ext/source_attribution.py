"""Sphinx extension rendering the ``sources:`` front-matter block.

The documentation is CC BY-SA 4.0 (``docs/licensing.md``), which lets a page
adapt material from the CC BY-SA commons -- Wikipedia most obviously -- on
condition that the source is credited and changes are noted. That obligation is
*per page*, so it is declared in the page's own front matter:

.. code-block:: yaml

    sources:
      - text: Adapted in part from the English Wikipedia article "Exciplex"
        url: https://en.wikipedia.org/wiki/Exciplex
        licence: CC-BY-SA-4.0

Front matter alone is invisible to a reader, and an attribution nobody can see
does not discharge anything. This extension turns the block into a rendered
"Sources" section at the foot of the page, so the credit travels with the text
when the page is printed, exported or copied out.

``test/test_docs_sources.py`` is the other half: it checks the block's shape and
that the licence is one the documentation can actually accept.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

#: Inbound licences the documentation can absorb. Anything else -- NC, ND,
#: GPL-only prose, a paper's text -- cannot be adapted here at all, so a page
#: declaring one is a mistake rather than something to render. Kept in step with
#: the table in ``docs/licensing.md``.
ACCEPTED = {
    "CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-4.0", "CC-BY-3.0",
    "CC0-1.0", "public-domain",
}


def _read_sources(text: str) -> list[dict]:
    """Return the ``sources`` list from a page's front matter, or ``[]``."""
    match = _FRONT_MATTER.match(text)
    if not match:
        return []
    try:
        import yaml

        meta = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return []
    raw = meta.get("sources") or []
    return [s for s in raw if isinstance(s, dict) and s.get("text")]


def _render(sources: list[dict], markdown: bool) -> str:
    """Build the Sources section for a page, in MyST or reStructuredText."""
    lines = []
    for s in sources:
        text, url = str(s["text"]).strip(), str(s.get("url", "")).strip()
        licence = str(s.get("licence", "")).strip()
        suffix = f" ({licence})" if licence else ""
        if markdown:
            lines.append(f"- [{text}]({url}){suffix}" if url else f"- {text}{suffix}")
        else:
            lines.append(f"- `{text} <{url}>`_{suffix}" if url else f"- {text}{suffix}")
    body = "\n".join(lines)
    intro = (
        "This page adapts material from the works below, with changes. "
        "They are credited under the terms of their licences; this page is "
        "itself CC BY-SA 4.0."
    )
    if markdown:
        return f"\n\n## Sources\n\n{intro}\n\n{body}\n"
    return f"\n\nSources\n-------\n\n{intro}\n\n{body}\n"


def _on_source_read(app, docname: str, source: list) -> None:
    """Append a rendered Sources section to any page declaring one."""
    if not app.config.source_attribution_enabled:
        return
    text = source[0]
    sources = _read_sources(text)
    if not sources:
        return
    try:
        path = str(pathlib.Path(app.env.doc2path(docname)))
    except Exception:
        path = docname
    source[0] = text.rstrip("\n") + _render(sources, markdown=path.endswith(".md"))


def setup(app) -> dict[str, Any]:
    """Register the extension with Sphinx."""
    app.add_config_value("source_attribution_enabled", True, "env")
    app.connect("source-read", _on_source_read)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
