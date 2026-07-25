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
from typing import Any

_BANNER_RST = """\
.. warning::
   **This page has not been checked by a human.** It was largely drafted
   automatically and may contain errors. {detail}

"""

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
    source[0] = _BANNER_RST.format(detail=detail) + source[0]


def setup(app) -> dict[str, Any]:
    """Register the extension with Sphinx."""
    app.add_config_value("review_banner_enabled", True, "env")
    app.connect("source-read", _on_source_read)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
