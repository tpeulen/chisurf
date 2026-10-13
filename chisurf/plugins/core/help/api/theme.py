"""Colours and typography for rendered help pages.

The help browser paints HTML into a Qt rich-text widget, and that widget does
not inherit the application stylesheet the way an ordinary widget does: unless
the page says otherwise it is black text on white, which is exactly what the
screenshots of ChiSurf's dark theme showed — a bright rectangle in a dark
window.

So the page carries its own colours, taken from the colours the application is
actually running with: :func:`from_tokens` reads emtk's palette tokens
(:mod:`emtk.style`, which an application re-themes with ``use_palette``), and
:func:`from_colours` takes any background/text pair -- a Qt host converts its
widget palette to that pair itself, so this module imports no toolkit.
Everything the renderer needs to colour is named here once: body text,
headings, links, code, the rules and the admonition boxes. The maths renderer
takes ``text`` from the same object, so a formula is the colour of the sentence
it sits in rather than always black.

Qt's rich-text engine implements a subset of CSS 2.1. The stylesheet below
sticks to what it honours — colour, background, font, margins, padding, borders
and text alignment — because anything else is silently ignored rather than
reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Theme", "DARK", "LIGHT", "from_colours", "from_tokens", "stylesheet"]


@dataclass(frozen=True)
class Theme:
    """Colour set for a rendered documentation page."""

    background: str
    text: str
    muted: str
    heading: str
    link: str
    rule: str
    code_background: str
    code_text: str
    quote_bar: str
    #: ``(border, background)`` per admonition kind.
    note: tuple[str, str]
    warning: tuple[str, str]
    tip: tuple[str, str]
    danger: tuple[str, str]
    #: Whether this is a dark theme; a few choices (image borders) depend on it.
    dark: bool = False


LIGHT = Theme(
    background="#ffffff",
    text="#1f2328",
    muted="#656d76",
    heading="#0d1117",
    link="#0969da",
    rule="#d8dee4",
    code_background="#f2f4f7",
    code_text="#8b2c4b",
    quote_bar="#d0d7de",
    note=("#0969da", "#eef5fd"),
    warning=("#bf8700", "#fdf6e3"),
    tip=("#1a7f37", "#eefbf1"),
    danger=("#cf222e", "#fdeeee"),
    dark=False,
)

DARK = Theme(
    background="#21252b",
    text="#d7dce3",
    muted="#9aa4b2",
    heading="#f0f3f7",
    link="#6cb6ff",
    rule="#3a4048",
    code_background="#2b3038",
    code_text="#f0a3bd",
    quote_bar="#4a515b",
    note=("#4184e4", "#25303f"),
    warning=("#c69026", "#33301f"),
    tip=("#3fb950", "#1f3025"),
    danger=("#f85149", "#3a2426"),
    dark=True,
)


def _hex(colour) -> str | None:
    """``"#rrggbb"`` for a ``"#rrggbb"`` string or an ``(r, g, b[, a])`` tuple of 0-255 ints."""
    if colour is None:
        return None
    if isinstance(colour, str):
        text = colour.strip()
        return text.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", text) else None
    try:
        r, g, b = (int(round(float(c))) for c in tuple(colour)[:3])
    except (TypeError, ValueError):
        return None
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, c)) for c in (r, g, b)))


def from_colours(background, text=None) -> Theme:
    """Return the theme matching a page *background* (and optionally its *text* colour).

    Parameters
    ----------
    background : str or tuple
        ``"#rrggbb"`` or ``(r, g, b[, a])``; decides light or dark. An unreadable
        value selects :data:`LIGHT`.
    text : str or tuple, optional
        Body text colour; wins over the preset, so a custom application palette
        does not end up with documentation in a foreign grey.

    Returns
    -------
    Theme
        :data:`DARK` when the background is dark, else :data:`LIGHT`, with the
        background (and text) replaced so the page and its window agree exactly.

    """
    base = _hex(background)
    if base is None:
        return LIGHT
    r, g, b = (int(base[i : i + 2], 16) for i in (1, 3, 5))
    # Perceived lightness; the midpoint is well clear of both themes' bases.
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    theme = DARK if luminance < 0.5 else LIGHT
    replacements = {"background": base}
    fg = _hex(text)
    if fg is not None:
        replacements["text"] = fg
    return Theme(**{**theme.__dict__, **replacements})


def from_tokens() -> Theme:
    """Return the theme of the running emtk palette (``emtk.style`` ``WINDOW_BG`` and ``TEXT``).

    The tokens are read at call time, so an application that re-themed emtk with
    ``emtk.style.use_palette`` gets pages in its own colours. Without emtk the
    light theme is returned.

    Returns
    -------
    Theme
    """
    try:
        from emtk import style
    except Exception:  # pragma: no cover - emtk is a hard dependency of the app, not of this module
        return LIGHT
    return from_colours(style.WINDOW_BG, style.TEXT)


def stylesheet(theme: Theme, *, font_size: float = 12.0) -> str:
    """Build the ``<style>`` block for a page rendered with *theme*.

    Parameters
    ----------
    theme : Theme
        Colours to use.
    font_size : float, optional
        Body text size in points.

    Returns
    -------
    str
        A complete ``<style>…</style>`` element.

    """
    note_border, note_bg = theme.note
    warn_border, warn_bg = theme.warning
    tip_border, tip_bg = theme.tip
    danger_border, danger_bg = theme.danger
    return f"""<style>
body {{
  font-family: -apple-system, 'Helvetica Neue', 'Segoe UI', Arial, sans-serif;
  font-size: {font_size}pt;
  color: {theme.text};
  background-color: {theme.background};
  /* Qt's rich-text engine applies ``line-height`` to the *line box*, not to
     the font, so a value tuned by eye in a browser reads far looser here: 148%
     put nearly two blank lines' worth of air between every pair of lines and
     a page of prose barely filled the window. */
  line-height: 122%;
}}
h1 {{ font-size: {font_size + 7.5:.1f}pt; color: {theme.heading}; margin: 2px 0 8px 0; }}
h2 {{ font-size: {font_size + 4.0:.1f}pt; color: {theme.heading}; margin: 16px 0 5px 0; }}
h3 {{ font-size: {font_size + 2.0:.1f}pt; color: {theme.heading}; margin: 13px 0 3px 0; }}
h4, h5, h6 {{ font-size: {font_size + 0.5:.1f}pt; color: {theme.heading}; margin: 11px 0 3px 0; }}
p {{ margin: 6px 0; }}
a {{ color: {theme.link}; text-decoration: none; }}
li {{ margin: 2px 0; }}
hr {{ border: 1px solid {theme.rule}; }}
code {{
  font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace;
  font-size: {font_size - 0.5:.1f}pt;
  background-color: {theme.code_background};
  color: {theme.code_text};
}}
pre {{
  font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace;
  font-size: {font_size - 0.5:.1f}pt;
  background-color: {theme.code_background};
  color: {theme.text};
  padding: 8px;
  margin: 8px 0;
  /* Qt scrolls the *document*, not the block: one long command line would put
     a horizontal scrollbar under the whole page and slide every paragraph on
     it sideways with the code. Wrapping keeps the page still. */
  white-space: pre-wrap;
}}
pre code {{ background-color: {theme.code_background}; color: {theme.text}; }}
/* A link into the source keeps the code font but takes the link colour --
   otherwise it is indistinguishable from the code spans around it and nobody
   discovers it is clickable. */
a code {{ color: {theme.link}; }}
blockquote {{
  color: {theme.muted};
  border-left: 3px solid {theme.quote_bar};
  padding-left: 10px;
  margin: 8px 0 8px 4px;
}}
table {{ border-color: {theme.rule}; margin: 10px 0; }}
th {{
  background-color: {theme.code_background};
  color: {theme.heading};
  padding: 4px 8px;
  text-align: left;
}}
td {{ padding: 4px 8px; }}
td.admonition {{
  background-color: {note_bg};
  border-left: 4px solid {note_border};
}}
table.admonition {{ margin: 12px 0; }}
.admonition-title {{ color: {note_border}; font-weight: bold; margin: 0 0 4px 0; }}
td.admonition.warning, td.admonition.caution, td.admonition.attention {{
  background-color: {warn_bg}; border-left-color: {warn_border};
}}
.admonition.warning .admonition-title,
.admonition.caution .admonition-title,
.admonition.attention .admonition-title {{ color: {warn_border}; }}
td.admonition.tip, td.admonition.hint, td.admonition.seealso {{
  background-color: {tip_bg}; border-left-color: {tip_border};
}}
.admonition.tip .admonition-title,
.admonition.hint .admonition-title,
.admonition.seealso .admonition-title {{ color: {tip_border}; }}
td.admonition.danger, td.admonition.error {{
  background-color: {danger_bg}; border-left-color: {danger_border};
}}
.admonition.danger .admonition-title,
.admonition.error .admonition-title {{ color: {danger_border}; }}
.math-fallback {{
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  color: {theme.text};
}}
.doc-caption {{ color: {theme.muted}; font-size: {font_size - 1.0:.1f}pt; }}
.doc-breadcrumb {{ color: {theme.muted}; font-size: {font_size - 1.0:.1f}pt; margin: 0 0 6px 0; }}
.doc-card-title {{ color: {theme.heading}; font-weight: bold; }}
.doc-hit {{ color: {theme.muted}; }}
</style>"""
