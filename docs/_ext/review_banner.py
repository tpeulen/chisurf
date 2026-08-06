"""Sphinx extension stamping unreviewed manual pages with a banner.

Much of the user manual was machine-drafted. Pages that no human has signed off
are still built — hiding them would leave holes in the toctree and break
cross-references — but they are marked in the rendered output so a reader can
tell at a glance that the page is unchecked.

The hard release gate lives elsewhere: ``csc help review-check`` (the
``docs-check-reviewed`` task) exits non-zero when any tracked page is unreviewed
or stale. This extension only makes the state visible.

Set ``review_banner_enabled = False`` in ``conf.py`` to suppress the banners.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

_BANNER_RST = """\
.. warning::
   **This page has not been checked by a human.** It was largely drafted
   automatically and may contain errors. {detail}

"""

#: The same banner in MyST. A page in Markdown was being stamped with the
#: reStructuredText form, which Markdown does not parse: the directive reached
#: the reader as the literal text ".. warning::" at the top of the page.
_BANNER_MYST = """\
:::{{warning}}
**This page has not been checked by a human.** It was largely drafted
automatically and may contain errors. {detail}
:::

"""

_FRONT_MATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)

_DETAIL = {
    "unreviewed": "It has never been reviewed.",
    "stale": (
        "It was reviewed once, but has been edited since, so the earlier "
        "sign-off no longer applies."
    ),
}


def _status_of(path: str) -> str:
    """Return the review status of *path*, or an empty string when unavailable."""
    try:
        from chisurf.plugins.core.help.api import review
    except Exception:
        return ""
    try:
        if not review.is_tracked(path):
            return ""
        return review.status_of(path).status
    except Exception:
        return ""


def _on_source_read(app, docname: str, source: list) -> None:
    """Prepend a banner to unreviewed or stale pages."""
    if not app.config.review_banner_enabled:
        return
    try:
        path = str(pathlib.Path(app.env.doc2path(docname)))
    except Exception:
        return
    status = _status_of(path)
    detail = _DETAIL.get(status)
    if detail is None:
        return

    template = _BANNER_MYST if path.endswith(".md") else _BANNER_RST
    banner = template.format(detail=detail)

    # After the front matter, never before it. A Markdown page carries an
    # Open-Knowledge-Format header, and MyST only recognises it when the file
    # *begins* with it — prepending the banner turned the whole header into a
    # setext heading, so every page's title became its own metadata.
    text = source[0]
    match = _FRONT_MATTER.match(text)
    if match:
        source[0] = text[: match.end()] + "\n" + banner + text[match.end() :].lstrip("\n")
    else:
        source[0] = banner + text


def setup(app) -> dict[str, Any]:
    """Register the extension with Sphinx."""
    app.add_config_value("review_banner_enabled", True, "env")
    app.connect("source-read", _on_source_read)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
