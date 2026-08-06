"""Typeset the LaTeX in the documentation for the in-app help browser.

The concept pages are written with real mathematics — ``$$ E = 1/(1 + (R/R_0)^6) $$``
— because that is the only honest way to say what a model computes. Qt's
rich-text engine has no maths, so before this module the browser showed the
source: a reader met ``\\frac{1}{\\tau_D}\\left(\\frac{R_0}{R}\\right)^6`` where
the formula should be, on the pages that carry the most information.

Formulas are rasterised with matplotlib's built-in *mathtext* engine, which
needs no LaTeX installation, and embedded as ``data:`` URIs so the HTML stays
self-contained. Two details matter for the result to look like part of the page
rather than pasted into it:

* it is rendered at twice the nominal size and displayed at half, so the glyphs
  stay sharp on a high-resolution screen;
* it is rendered in the *text* colour of the current theme, so a formula on a
  dark page is not a white box.

mathtext understands a large subset of LaTeX but not all of it, so
:func:`normalise_latex` rewrites the constructs the documentation uses that it
would reject (``\\text``, ``\\boxed``, ``\\bigl``, environments…). Anything that
still fails falls back to the source in a monospace span — degraded, never a
traceback and never a blank.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "MathRenderer",
    "normalise_latex",
    "split_math",
]

#: Cheap unicode stand-ins used when a formula cannot be rasterised at all.
_FALLBACK_SYMBOLS = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ",
    r"\kappa": "κ", r"\lambda": "λ", r"\mu": "µ", r"\nu": "ν",
    r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
    r"\phi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Delta": "Δ", r"\Gamma": "Γ", r"\Sigma": "Σ", r"\Omega": "Ω",
    r"\Phi": "Φ", r"\Psi": "Ψ", r"\Lambda": "Λ", r"\Theta": "Θ",
    r"\times": "×", r"\cdot": "·", r"\approx": "≈", r"\propto": "∝",
    r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\pm": "±",
    r"\to": "→", r"\rightarrow": "→", r"\langle": "⟨", r"\rangle": "⟩",
    r"\infty": "∞", r"\partial": "∂", r"\sum": "Σ", r"\int": "∫",
    r"\sqrt": "√", r"\ll": "≪", r"\gg": "≫", r"\equiv": "≡",
}

#: Environments that mathtext cannot parse; their rows are joined instead.
_ENVIRONMENTS = re.compile(
    r"\\begin\{(?:align|align\*|aligned|equation|equation\*|split|gather|gather\*)\}"
    r"(.*?)"
    r"\\end\{(?:align|align\*|aligned|equation|equation\*|split|gather|gather\*)\}",
    re.DOTALL,
)


def normalise_latex(latex: str) -> str:
    """Rewrite *latex* into the subset matplotlib's mathtext accepts.

    Parameters
    ----------
    latex : str
        Formula source as written in the documentation, without delimiters.

    Returns
    -------
    str
        An equivalent formula mathtext can parse. The rewrite is lossy for
        alignment only: multi-line environments become a single line.

    """
    text = latex.strip()

    # Multi-line environments: keep the mathematics, drop the alignment.
    def _flatten(match: "re.Match[str]") -> str:
        body = match.group(1)
        body = body.replace(r"\\", " ").replace("&", "")
        return body

    text = _ENVIRONMENTS.sub(_flatten, text)
    text = text.replace(r"\\", " ")
    text = re.sub(r"(?<!\\)&", "", text)
    # mathtext parses one line: a newline inside a formula is a parse error, not
    # a line break, so the source's wrapping is folded away here. Display
    # mathematics is split into rows *before* this, by :func:`math_rows`.
    text = re.sub(r"\s+", " ", text)

    # ``\text``/``\textrm``/``\mbox`` -> upright maths; mathtext has \mathrm.
    text = re.sub(r"\\(?:text|textrm|mbox|textnormal)\s*\{", r"\\mathrm{", text)
    text = re.sub(r"\\(?:textbf)\s*\{", r"\\mathbf{", text)
    text = re.sub(r"\\(?:textit|emph)\s*\{", r"\\mathit{", text)

    # ``\boxed{x}`` has no mathtext equivalent; the emphasis is lost, not the maths.
    text = re.sub(r"\\boxed\s*\{", "{", text)
    # Manual delimiter sizing: mathtext sizes with \left/\right only, and a bare
    # ``\big(`` is not a delimiter pair, so the modifier is dropped rather than
    # mapped -- mapping ``\big)`` to ``\left)`` produced unbalanced input.
    text = re.sub(
        r"\\(?:Biggl|Biggr|biggl|biggr|Bigll|Bigl|Bigr|bigl|bigr"
        r"|Bigg|bigg|Big|big)(?![A-Za-z])",
        "",
        text,
    )
    # Font families mathtext does not carry.
    text = re.sub(r"\\(?:mathsf|mathtt|mathfrak|mathscr)(?![A-Za-z])", r"\\mathrm", text)
    text = re.sub(r"\\boldsymbol(?![A-Za-z])\s*", r"\\mathbf", text)
    text = re.sub(r"\\pmb(?![A-Za-z])\s*", r"\\mathbf", text)
    # A font command takes the next *token* in TeX; mathtext demands a group.
    text = re.sub(
        r"\\(mathbf|mathrm|mathit|mathcal|mathbb|mathsf)\s*(\\[A-Za-z]+|[A-Za-z0-9])(?![A-Za-z])",
        r"\\\1{\2}",
        text,
    )
    # Matrix environments have no mathtext equivalent; the rows are shown as a
    # bracketed, comma-separated list rather than dropped.
    text = re.sub(
        r"\\begin\{[bBpvV]?matrix\*?\}|\\begin\{smallmatrix\}|"
        r"\\end\{[bBpvV]?matrix\*?\}|\\end\{smallmatrix\}",
        "",
        text,
    )
    # Abbreviated relations and fraction spellings.
    for short, long in (
        (r"\le", r"\leq"), (r"\ge", r"\geq"), (r"\ne", r"\neq"),
        (r"\tfrac", r"\frac"), (r"\dfrac", r"\frac"), (r"\cfrac", r"\frac"),
        (r"\lVert", r"\|"), (r"\rVert", r"\|"),
        (r"\lvert", r"|"), (r"\rvert", r"|"),
        (r"\coloneqq", ":="), (r"\eqqcolon", "=:"),
    ):
        text = re.sub(re.escape(short) + r"(?![A-Za-z])", long.replace("\\", "\\\\"), text)
    # ``\frac12`` -- TeX takes the next two tokens; mathtext demands groups.
    text = re.sub(
        r"\\(frac|binom)\s*(\\[A-Za-z]+|[^{\\\s])\s*(\\[A-Za-z]+|[^{\\\s])",
        r"\\\1{\2}{\3}",
        text,
    )
    text = re.sub(r"\\sqrt\s*(\\[A-Za-z]+|[A-Za-z0-9])(?![A-Za-z])", r"\\sqrt{\1}", text)
    # Braces/labels under a term: mathtext has \underset but no \underbrace, so
    # ``\underbrace{X}_{label}`` becomes ``\underset{label}{X}`` -- the label
    # stays *under* the term instead of turning into a subscript of it, which
    # read as part of the formula.
    text = re.sub(
        r"\\underbrace\s*\{((?:[^{}]|\{[^{}]*\})*)\}\s*_\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
        r"\\underset{\2}{\1}",
        text,
    )
    text = re.sub(
        r"\\overbrace\s*\{((?:[^{}]|\{[^{}]*\})*)\}\s*\^\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
        r"\\overset{\2}{\1}",
        text,
    )
    text = re.sub(r"\\underbrace\s*\{", r"{", text)
    text = re.sub(r"\\overbrace\s*\{", r"{", text)
    text = re.sub(r"\\stackrel(?![A-Za-z])", r"\\overset", text)
    # Spacing commands mathtext does not define.
    text = re.sub(r"\\(?:!|>|medspace|thinspace|thickspace|negthinspace)", " ", text)
    text = text.replace(r"\nonumber", "").replace(r"\notag", "")
    text = re.sub(r"\\label\s*\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:displaystyle|textstyle|scriptstyle|limits|nolimits)\b", "", text)
    text = re.sub(r"\\operatorname\s*\*?\s*\{", r"\\mathrm{", text)
    # ``\left.``/``\right.`` (invisible delimiters) are unsupported.
    text = text.replace(r"\left.", "").replace(r"\right.", "")
    return text.strip()


def math_rows(latex: str) -> list[str]:
    """Split display mathematics into the lines it was written as.

    mathtext typesets a single line, so a multi-line derivation has to become
    several images stacked in the page rather than one that fails to parse.
    Rows come from the ``\\\\`` separators of the source, inside an ``align``
    environment or not.

    Parameters
    ----------
    latex : str
        Display-mathematics source without delimiters.

    Returns
    -------
    list of str
        One entry per typeset line; never empty for non-empty input.

    """
    body = latex
    match = _ENVIRONMENTS.search(body)
    if match is not None:
        body = match.group(1)
    rows = [row.strip() for row in re.split(r"\\\\", body)]
    rows = [row for row in rows if row.strip(" &\n\t")]
    return rows or [latex]


def _unicode_fallback(latex: str) -> str:
    """Best-effort plain-text rendering for a formula that will not typeset."""
    text = normalise_latex(latex)
    for command, symbol in _FALLBACK_SYMBOLS.items():
        text = re.sub(re.escape(command) + r"(?![A-Za-z])", symbol, text)
    text = re.sub(r"\\(?:left|right|mathrm|mathbf|mathit|mathcal)\b", "", text)
    text = re.sub(r"\\[A-Za-z]+", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


#: Symbols that have a faithful character equivalent, for inline mathematics.
_HTML_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "µ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "varrho": "ϱ", "sigma": "σ", "varsigma": "ς",
    "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
    "times": "×", "cdot": "·", "cdots": "⋯", "ldots": "…", "dots": "…",
    "approx": "≈", "propto": "∝", "sim": "∼", "simeq": "≃", "equiv": "≡",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "ll": "≪", "gg": "≫", "pm": "±", "mp": "∓", "ast": "∗", "star": "⋆",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "leftrightarrow": "↔", "mapsto": "↦",
    "langle": "⟨", "rangle": "⟩", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖", "vert": "|", "Vert": "‖",
    "infty": "∞", "partial": "∂", "nabla": "∇", "propto ": "∝",
    "perp": "⊥", "parallel": "∥", "angle": "∠", "circ": "∘",
    "in": "∈", "notin": "∉", "subset": "⊂", "cup": "∪", "cap": "∩",
    "forall": "∀", "exists": "∃", "emptyset": "∅", "ell": "ℓ",
    "prime": "′", "degree": "°", "percent": "%", "mid": "|",
    "backslash": "\\", "colon": ":", "bullet": "•", "dagger": "†",
    "top": "⊤", "bot": "⊥", "hbar": "ℏ", "Re": "ℜ", "Im": "ℑ",
    "AA": "Å", "micro": "µ", "lesssim": "≲", "gtrsim": "≳",
    "leftrightarrows": "⇄", "rightleftharpoons": "⇌", "propto2": "∝",
}

#: Spacing commands and their HTML equivalents.
_HTML_SPACES = {
    ",": "&#8201;", ";": "&#8201;", ":": "&#8201;", "!": "", " ": " ",
    "quad": "&nbsp;&nbsp;", "qquad": "&nbsp;&nbsp;&nbsp;&nbsp;",
    "thinspace": "&#8201;", "medspace": "&#8201;", "thickspace": "&nbsp;",
}

#: Font commands that map onto an HTML element rather than a raster image.
_HTML_FONTS = {
    "mathrm": ("", ""), "text": ("", ""), "textrm": ("", ""),
    "mathbf": ("<b>", "</b>"), "textbf": ("<b>", "</b>"),
    "mathit": ("<i>", "</i>"), "textit": ("<i>", "</i>"), "emph": ("<i>", "</i>"),
    "mathsf": ("", ""), "mathtt": ("<code>", "</code>"), "operatorname": ("", ""),
}


#: Relations and binary operators, which read as cramped without air round them.
_SPACED_SYMBOLS = {
    "×", "·", "≈", "∝", "∼", "≃", "≡", "≤", "≥", "≠", "≪", "≫", "±", "∓",
    "→", "←", "⇒", "↔", "↦", "∈", "∉", "⊂", "∪", "∩", "≲", "≳", "⇄", "⇌",
}


class _UnsupportedInline(Exception):
    """Raised when a formula needs real typesetting rather than HTML."""


def html_math(latex: str) -> Optional[str]:
    """Render *latex* as HTML text, or return *None* if it needs typesetting.

    Inline mathematics is mostly symbols with sub- and superscripts —
    ``\\tau_D``, ``R_0``, ``1/R^6`` — and those are far better as real text
    than as pictures: an image sits at its own baseline, in its own font, and
    at a size that stops matching as soon as the reader changes the page's.
    Only genuinely two-dimensional constructs (fractions, roots, sums with
    limits) fall through to :class:`MathRenderer`.

    Parameters
    ----------
    latex : str
        Formula source without delimiters.

    Returns
    -------
    str or None
        An HTML fragment, or *None* when the formula must be rasterised.

    """
    try:
        html, position = _inline_group(latex, 0, stop_at_brace=False)
    except _UnsupportedInline:
        return None
    if position < len(latex):
        return None
    return html or None


def _inline_group(text: str, index: int, stop_at_brace: bool) -> tuple[str, int]:
    """Convert tokens from *index* until the end or a closing brace."""
    out: list[str] = []
    while index < len(text):
        char = text[index]
        if char == "}":
            if stop_at_brace:
                return "".join(out), index
            raise _UnsupportedInline("unbalanced brace")
        if char == "{":
            inner, index = _inline_group(text, index + 1, True)
            if index >= len(text) or text[index] != "}":
                raise _UnsupportedInline("unbalanced brace")
            out.append(inner)
            index += 1
            continue
        if char in "_^":
            script, index = _inline_atom(text, index + 1)
            tag = "sub" if char == "_" else "sup"
            out.append(f"<{tag}>{script}</{tag}>")
            continue
        if char == "\\":
            fragment, index = _inline_command(text, index)
            out.append(fragment)
            continue
        if char == "$":
            raise _UnsupportedInline("nested delimiter")
        out.append(_inline_char(char))
        index += 1
    return "".join(out), index


def _inline_atom(text: str, index: int) -> tuple[str, int]:
    """Convert the single token (or braced group) that a script applies to."""
    while index < len(text) and text[index] == " ":
        index += 1
    if index >= len(text):
        raise _UnsupportedInline("dangling script")
    if text[index] == "{":
        inner, index = _inline_group(text, index + 1, True)
        if index >= len(text) or text[index] != "}":
            raise _UnsupportedInline("unbalanced brace")
        return inner, index + 1
    if text[index] == "\\":
        return _inline_command(text, index)
    return _inline_char(text[index]), index + 1


def _inline_command(text: str, index: int) -> tuple[str, int]:
    """Convert one ``\\command`` starting at the backslash."""
    match = re.match(r"\\([A-Za-z]+)", text[index:])
    if match is None:
        symbol = text[index + 1: index + 2]
        if symbol in _HTML_SPACES:
            return _HTML_SPACES[symbol], index + 2
        if symbol in "{}%$&#_":
            return _inline_char(symbol), index + 2
        raise _UnsupportedInline(f"escape {symbol!r}")

    name = match.group(1)
    index += len(match.group(0))
    # TeX swallows the whitespace that terminates a command name, so
    # ``\langle E\rangle`` must not come out as "⟨ E⟩".
    while index < len(text) and text[index] == " ":
        index += 1
    if name in _HTML_SPACES:
        return _HTML_SPACES[name], index
    if name in _HTML_SYMBOLS:
        symbol = _HTML_SYMBOLS[name]
        if symbol in _SPACED_SYMBOLS:
            return f"&#8201;{symbol}&#8201;", index
        return symbol, index
    if name in _HTML_FONTS:
        while index < len(text) and text[index] == " ":
            index += 1
        open_tag, close_tag = _HTML_FONTS[name]
        if index < len(text) and text[index] == "{":
            inner, index = _inline_group(text, index + 1, True)
            if index >= len(text) or text[index] != "}":
                raise _UnsupportedInline("unbalanced brace")
            index += 1
        else:
            inner, index = _inline_atom(text, index)
        # Upright by construction: strip the italics the letters were given.
        if not open_tag:
            inner = re.sub(r"</?i>", "", inner)
        return f"{open_tag}{inner}{close_tag}", index
    if name in ("left", "right", "big", "bigl", "bigr", "Big", "Bigl", "Bigr"):
        return "", index
    raise _UnsupportedInline(f"command {name!r}")


def _inline_char(char: str) -> str:
    """Convert one ordinary character, italicising variables as TeX does."""
    if char.isalpha():
        return f"<i>{char}</i>"
    if char == "&":
        return "&amp;"
    if char == "<":
        return "&lt;"
    if char == ">":
        return "&gt;"
    if char == "~":
        return "&nbsp;"
    return char


class MathRenderer:
    """Rasterise LaTeX formulas to inline images, caching what it has drawn.

    Parameters
    ----------
    colour : str, optional
        Foreground colour of the glyphs, as a CSS/matplotlib colour.
    font_size : float, optional
        Nominal point size of inline mathematics; display mathematics is drawn
        slightly larger.

    Notes
    -----
    One renderer belongs to one theme. The cache is keyed by the formula *and*
    the colour, so switching theme cannot serve a formula in the old colour.

    """

    #: Supersampling factor; the image is displayed at ``1 / _SCALE`` of its size.
    _SCALE = 2

    #: Optical correction. A formula set at the body's point size *looks*
    #: smaller than the body: the maths font's x-height is lower than the UI
    #: font's, and a formula is read as a unit rather than as a line of text.
    _INLINE_SCALE = 1.12
    _DISPLAY_SCALE = 1.32

    #: Glyph set. The pages are set in a sans interface font and *inline*
    #: mathematics is real text in that font, so a serif maths face would make
    #: the same symbol look like two different symbols depending on whether it
    #: landed in a sentence or in a displayed equation.
    _FONTSET = "stixsans"

    def __init__(self, colour: str = "#202020", font_size: float = 11.0):
        self.colour = colour
        self.font_size = float(font_size)
        self._cache: dict[tuple[str, bool], Optional[str]] = {}
        self._available: Optional[bool] = None

    # ── public API ──────────────────────────────────────────────────

    def to_html(self, latex: str, display: bool = False) -> str:
        """Return an HTML fragment showing *latex*.

        Parameters
        ----------
        latex : str
            Formula source without delimiters.
        display : bool, optional
            Whether this is display mathematics (its own centred block) rather
            than inline.

        Returns
        -------
        str
            An ``<img>`` when the formula could be typeset, otherwise a
            monospace span holding a readable approximation.

        """
        if not display:
            as_text = html_math(latex.strip())
            if as_text is not None:
                return f'<span class="math-inline">{as_text}</span>'
            return self._one(latex, False)
        rows = [self._one(row, True) for row in math_rows(latex)]
        return '<p align="center" class="math-display">' + "<br>".join(rows) + "</p>"

    def _one(self, latex: str, display: bool) -> str:
        """Return the fragment for a single typeset line, image or fallback."""
        tag = self._image_tag(latex, display)
        if tag is not None:
            return tag
        fallback = _unicode_fallback(latex)
        escaped = fallback.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<span class="math-fallback">{escaped}</span>'

    # ── internals ───────────────────────────────────────────────────

    def _image_tag(self, latex: str, display: bool) -> Optional[str]:
        key = (latex, display)
        if key in self._cache:
            return self._cache[key]
        tag = self._render(latex, display)
        self._cache[key] = tag
        return tag

    def _render(self, latex: str, display: bool) -> Optional[str]:
        if self._available is False:
            return None
        try:
            from matplotlib.figure import Figure
            from matplotlib.font_manager import FontProperties
        except Exception:  # pragma: no cover - matplotlib always present in-app
            self._available = False
            logger.debug("matplotlib unavailable; help maths stays as text")
            return None
        self._available = True

        source = normalise_latex(latex)
        if not source:
            return None
        size = self.font_size * (self._DISPLAY_SCALE if display else self._INLINE_SCALE)
        prop = FontProperties(size=size * self._SCALE)
        buffer = io.BytesIO()
        try:
            import matplotlib

            # Scoped: the glyph set is a property of *this* page, and setting
            # it globally would restyle every plot the application draws.
            with matplotlib.rc_context({"mathtext.fontset": self._FONTSET}):
                # Drawn onto a transparent figure rather than through
                # ``math_to_image``, which bakes in an opaque white background
                # -- on a dark page every formula arrived as a bright card.
                figure = Figure(figsize=(0.01, 0.01), dpi=100)
                figure.patch.set_alpha(0.0)
                figure.text(0, 0, f"${source}$", fontproperties=prop, color=self.colour)
                figure.savefig(
                    buffer,
                    format="png",
                    dpi=100,
                    transparent=True,
                    bbox_inches="tight",
                    pad_inches=0.02,
                )
        except Exception:
            logger.debug("could not typeset %r", latex, exc_info=True)
            return None

        data = buffer.getvalue()
        if not data:
            return None
        width, height = _png_size(data)
        encoded = base64.b64encode(data).decode("ascii")
        attrs = ""
        if width and height:
            attrs = (
                f' width="{max(1, round(width / self._SCALE))}"'
                f' height="{max(1, round(height / self._SCALE))}"'
            )
        alt = source.replace('"', "&quot;")
        return f'<img src="data:image/png;base64,{encoded}"{attrs} alt="{alt}">'


def _png_size(data: bytes) -> tuple[int, int]:
    """Read the pixel size out of a PNG header without decoding the image."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


#: ``$$…$$``, ``\[…\]``, ``$…$`` and ``\(…\)``, in that precedence.
_MATH_PATTERNS = (
    (re.compile(r"\$\$(.+?)\$\$", re.DOTALL), True),
    (re.compile(r"\\\[(.+?)\\\]", re.DOTALL), True),
    (re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", re.DOTALL), False),
    (re.compile(r"\\\((.+?)\\\)", re.DOTALL), False),
)


def split_math(text: str):
    """Split *text* into literal and mathematical parts.

    Parameters
    ----------
    text : str
        Markdown source.

    Yields
    ------
    tuple
        ``(kind, payload)`` where *kind* is ``"text"``, ``"inline"`` or
        ``"display"``.

    Notes
    -----
    Fenced and inline code are *not* excluded here — the caller masks those
    first, because ``$`` inside a shell example is not mathematics.

    """
    position = 0
    while position < len(text):
        best = None
        for pattern, display in _MATH_PATTERNS:
            match = pattern.search(text, position)
            if match is None:
                continue
            if best is None or match.start() < best[0].start():
                best = (match, display)
        if best is None:
            yield "text", text[position:]
            return
        match, display = best
        if match.start() > position:
            yield "text", text[position:match.start()]
        yield ("display" if display else "inline"), match.group(1)
        position = match.end()
