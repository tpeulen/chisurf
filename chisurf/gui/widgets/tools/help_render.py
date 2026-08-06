"""Render a help page the way the documentation browser does.

A plugin's ``help.md`` is the same dialect as everything else in ``docs/``:
MyST admonitions, cross-reference roles, ``{cite}`` citations, LaTeX. Qt's own
``QTextBrowser.setMarkdown`` knows none of that, so the ``?`` modal showed
``:::{note}``, ``{cite}`key``` and ``\\tau_D`` as literal text — the very
defects that were fixed in the browser, still present in the window most
readers actually open.

One function, used by every place that puts a help page into a Qt widget, so
there is one answer to "what does a help page look like".
"""

from __future__ import annotations

import logging
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["render_help", "show_in_browser"]


def render_help(
    text: str,
    path: Optional[pathlib.Path] = None,
    *,
    widget=None,
    font_size: float = 10.5,
) -> Optional[str]:
    """Return *text* as themed HTML, or ``None`` when it cannot be rendered.

    Parameters
    ----------
    text : str
        Help source, MyST-flavoured Markdown (or reStructuredText).
    path : pathlib.Path, optional
        Where it came from — decides the dialect and resolves relative links.
    widget : QtWidgets.QWidget, optional
        Widget whose palette the colours follow.
    font_size : float, optional
        Body text size in points.

    Returns
    -------
    str or None
        A complete HTML document, or ``None`` so the caller can fall back.

    """
    try:
        from chisurf.gui.widgets.tools.doc_links import expand_roles
        from chisurf.plugins.core.help.api import theme as theme_api
        from chisurf.plugins.core.help.api.bibliography import expand_citations
        from chisurf.plugins.core.help.api.mathtext import MathRenderer
        from chisurf.plugins.core.help.api.render import render_document
    except Exception:  # pragma: no cover - help API unavailable
        logger.debug("help renderer unavailable", exc_info=True)
        return None

    base = path.parent if path is not None else None
    try:
        shown = expand_roles(text, base)
    except Exception:
        logger.debug("could not expand cross-reference roles", exc_info=True)
        shown = text
    try:
        shown = expand_citations(shown)
    except Exception:
        logger.debug("could not expand citations", exc_info=True)
    try:
        from chisurf.plugins.core.help.api.source_links import expand_source_roles

        shown = expand_source_roles(shown)
    except Exception:
        logger.debug("could not expand source roles", exc_info=True)

    theme = theme_api.from_palette(widget)
    # A `?` modal is much narrower than the documentation window, and a formula
    # wider than it gives the modal a horizontal scrollbar rather than being
    # stacked or shrunk to fit.
    column = MathRenderer.MAX_DISPLAY_WIDTH
    try:
        if widget is not None and widget.width() > 200:
            column = min(column, widget.width() - 60)
    except Exception:
        pass
    try:
        return render_document(
            shown,
            path or pathlib.Path("help.md"),
            theme=theme,
            math=MathRenderer(colour=theme.text, font_size=font_size, max_width=column),
            font_size=font_size,
        )
    except Exception:
        logger.debug("could not render the help page", exc_info=True)
        return None


def show_in_browser(browser, text: str, path: Optional[pathlib.Path] = None) -> None:
    """Put a help page into *browser*, rendered, with a safe fallback.

    Falls back to Qt's own Markdown and then to plain text, so a renderer
    failure degrades the *typography* rather than losing the help.
    """
    html = render_help(text, path, widget=browser)
    if html is not None:
        if path is not None:
            try:
                browser.setSearchPaths([str(path.parent)])
            except Exception:
                logger.debug("could not set the image search path", exc_info=True)
        try:
            browser.setHtml(html)
            return
        except Exception:
            # Only a *failure to display* falls through to the plain forms; a
            # missing base URL must not cost the reader the rendering.
            logger.debug("could not set the rendered help", exc_info=True)
    if hasattr(browser, "setMarkdown"):
        browser.setMarkdown(text)
    else:  # pragma: no cover - very old Qt
        browser.setPlainText(text)
