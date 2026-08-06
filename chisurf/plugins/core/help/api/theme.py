"""Colours and typography for rendered help pages.

The help browser paints HTML into a Qt rich-text widget, and that widget does
not inherit the application stylesheet the way an ordinary widget does: unless
the page says otherwise it is black text on white, which is exactly what the
screenshots of ChiSurf's dark theme showed — a bright rectangle in a dark
window.

So the page carries its own colours, taken from the palette the application is
actually running with. Everything the renderer needs to colour is named here
once: body text, headings, links, code, the rules and the admonition boxes. The
maths renderer takes ``text`` from the same object, so a formula is the colour
of the sentence it sits in rather than always black.

Qt's rich-text engine implements a subset of CSS 2.1. The stylesheet below
sticks to what it honours — colour, background, font, margins, padding, borders
and text alignment — because anything else is silently ignored rather than
reported.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Theme", "DARK", "LIGHT", "from_palette", "stylesheet"]


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


def from_palette(widget) -> Theme:
    """Return the theme matching *widget*'s palette.

    Parameters
    ----------
    widget : QtWidgets.QWidget or None
        Widget whose palette decides light or dark. ``None`` selects
        :data:`LIGHT`.

    Returns
    -------
    Theme
        :data:`DARK` when the widget's base colour is dark, else :data:`LIGHT`,
        with the background taken from the palette so the page and the widget
        agree exactly.

    """
    if widget is None:
        return LIGHT
    try:
        from qtpy.QtGui import QPalette

        palette = widget.palette()
        base = palette.color(QPalette.Base)
        text = palette.color(QPalette.Text)
    except Exception:  # pragma: no cover - not a Qt widget
        return LIGHT

    # Perceived lightness; the midpoint is well clear of both themes' bases.
    luminance = (0.299 * base.red() + 0.587 * base.green() + 0.114 * base.blue()) / 255.0
    theme = DARK if luminance < 0.5 else LIGHT
    replacements = {"background": base.name()}
    # A palette with an explicit text colour wins over the preset, so a custom
    # ChiSurf stylesheet does not end up with documentation in a foreign grey.
    if text.isValid():
        replacements["text"] = text.name()
    return Theme(**{**theme.__dict__, **replacements})


def stylesheet(theme: Theme, *, font_size: float = 10.5) -> str:
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
  line-height: 148%;
}}
h1 {{ font-size: {font_size + 7.5:.1f}pt; color: {theme.heading}; margin: 2px 0 10px 0; }}
h2 {{ font-size: {font_size + 4.0:.1f}pt; color: {theme.heading}; margin: 20px 0 6px 0; }}
h3 {{ font-size: {font_size + 2.0:.1f}pt; color: {theme.heading}; margin: 16px 0 4px 0; }}
h4, h5, h6 {{ font-size: {font_size + 0.5:.1f}pt; color: {theme.heading}; margin: 14px 0 4px 0; }}
p {{ margin: 7px 0; }}
a {{ color: {theme.link}; text-decoration: none; }}
li {{ margin: 3px 0; }}
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
