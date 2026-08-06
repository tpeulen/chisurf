"""Format-agnostic document rendering for the Help browser.

The browser serves Markdown (guides, concepts, plugin READMEs) and
reStructuredText (the user manual) side by side. Callers should not care which
is which, so this module dispatches on the file suffix and presents one
interface for both.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.core.help.api.markdown import extract_title, render_markdown
from chisurf.plugins.core.help.api.rst import extract_rst_title, render_rst

#: Suffixes handled as reStructuredText.
RST_SUFFIXES = (".rst",)

#: Suffixes handled as Markdown.
MARKDOWN_SUFFIXES = (".md", ".markdown")


def is_rst(path) -> bool:
    """Whether *path* names a reStructuredText document.

    Parameters
    ----------
    path : str or pathlib.Path
        Document path.

    Returns
    -------
    bool
        *True* for reStructuredText.

    """
    return pathlib.Path(path).suffix.lower() in RST_SUFFIXES


def render_document(
    text: str, path, *, theme=None, math=None, font_size: float = 10.5
) -> str | None:
    """Render *text* to HTML according to the format implied by *path*.

    Parameters
    ----------
    text : str
        Document source.
    path : str or pathlib.Path
        Document path; only its suffix is used.
    theme : Theme, optional
        Colours for the page; the light theme when omitted.
    math : MathRenderer, optional
        Shared renderer for LaTeX, so its cache survives across pages.

    Returns
    -------
    str or None
        Rendered HTML, or *None* when the format has no renderer available.

    """
    if is_rst(path):
        return render_rst(text, theme=theme, math=math, font_size=font_size)
    return render_markdown(text, theme=theme, math=math, font_size=font_size)


def document_title(text: str, path) -> str | None:
    """Return the document title according to the format implied by *path*.

    Parameters
    ----------
    text : str
        Document source.
    path : str or pathlib.Path
        Document path; only its suffix is used.

    Returns
    -------
    str or None
        Title, or *None* when the document has none.

    """
    return extract_rst_title(text) if is_rst(path) else extract_title(text)
