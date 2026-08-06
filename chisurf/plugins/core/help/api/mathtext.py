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
    # Matrices before the row/column separators are thrown away: mathtext has
    # no matrix environment, and a matrix whose separators were already deleted
    # reads as one run-on string ("[1α0γ]" for a 2x2).
    text = _flatten_matrices(text)
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
    # Any matrix delimiters left over from a form _flatten_matrices could not
    # pair up are dropped rather than shown as literal text.
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
    text = _rewrite_brace(text, "underbrace", "_", "underset")
    text = _rewrite_brace(text, "overbrace", "^", "overset")
    text = re.sub(r"\\underbrace\s*\{", r"{", text)
    text = re.sub(r"\\overbrace\s*\{", r"{", text)
    text = re.sub(r"\\stackrel(?![A-Za-z])", r"\\overset", text)
    # Spacing commands mathtext does not define.
    text = re.sub(r"\\(?:!|>|medspace|thinspace|thickspace|negthinspace)", " ", text)
    text = text.replace(r"\nonumber", "").replace(r"\notag", "")
    text = re.sub(r"\\label\s*\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:displaystyle|textstyle|scriptstyle|limits|nolimits)\b", "", text)
    text = re.sub(r"\\operatorname\s*\*?\s*\{", r"\\mathrm{", text)
    # mathtext drops ordinary spaces in maths mode, so ``\mathrm{amplitude
    # decay}`` -- a *label*, not a formula -- came out as "amplitudedecay".
    text = _space_text_groups(text)
    # ``\left.``/``\right.`` (invisible delimiters) are unsupported.
    text = text.replace(r"\left.", "").replace(r"\right.", "")
    return text.strip()



#: Matrix environments and the delimiters they are set in.
_MATRIX_DELIMITERS = {
    # ``matrix`` and ``smallmatrix`` carry no delimiters of their own: the
    # source supplies them, usually as ``\left[ … \right]``.
    "matrix": ("", ""), "smallmatrix": ("", ""),
    "pmatrix": ("(", ")"), "bmatrix": ("[", "]"),
    "Bmatrix": (r"\{", r"\}"), "vmatrix": ("|", "|"), "Vmatrix": (r"\|", r"\|"),
}

_MATRIX_BLOCK = re.compile(
    r"\\begin\{(" + "|".join(_MATRIX_DELIMITERS) + r")\*?\}(.*?)\\end\{\1\*?\}",
    re.DOTALL,
)


def _flatten_matrices(text: str) -> str:
    r"""Write a matrix as a bracketed list of rows.

    mathtext has no matrix environment, so a matrix has to become something
    one-dimensional. Deleting the ``&`` and ``\\`` separators — which is what
    the generic rewrite below does — turns a 2x2 into one run-on string; keeping
    them as ``,`` and ``;`` keeps the shape readable.
    """
    def _one(match: "re.Match[str]") -> str:
        left, right = _MATRIX_DELIMITERS[match.group(1)]
        rows = [row.strip() for row in re.split(r"\\\\", match.group(2))]
        rows = [row for row in rows if row.strip(" &\n\t")]
        body = r";\; ".join(
            r",\, ".join(cell.strip() for cell in row.split("&") if cell.strip())
            for row in rows
        )
        return f"{left}{body}{right}"

    previous = None
    while previous != text:
        previous = text
        text = _MATRIX_BLOCK.sub(_one, text)
    return text


def _matched_group(text: str, start: int) -> tuple[str, int]:
    r"""Return the contents of the ``{…}`` at *start* and the index after it.

    Brace matching rather than a regex, because a regex has to fix how deeply
    groups may nest — and a formula that nests one level deeper than it allows
    does not fail loudly, it silently keeps the ``\underbrace`` label as a
    *subscript* stuck to the end of the expression.
    """
    if start >= len(text) or text[start] != "{":
        return "", start
    depth, index = 0, start
    while index < len(text):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1: index], index + 1
        index += 1
    return "", start


def _rewrite_brace(text: str, command: str, marker: str, replacement: str) -> str:
    r"""Rewrite ``\command{X}<marker>{Y}`` into ``\replacement{Y}{X}``.

    mathtext has ``\underset``/``\overset`` but no braces, so this is how a
    label under a term survives — as a label under the term rather than as a
    subscript of it.
    """
    out, index = [], 0
    token = "\\" + command
    while True:
        found = text.find(token, index)
        if found < 0:
            out.append(text[index:])
            return "".join(out)
        after = found + len(token)
        while after < len(text) and text[after] == " ":
            after += 1
        body, after_body = _matched_group(text, after)
        cursor = after_body
        while cursor < len(text) and text[cursor] == " ":
            cursor += 1
        if not body or cursor >= len(text) or text[cursor] != marker:
            out.append(text[index:after_body or after])
            index = after_body if after_body > found else found + len(token)
            continue
        cursor += 1
        while cursor < len(text) and text[cursor] == " ":
            cursor += 1
        label, after_label = _matched_group(text, cursor)
        if not label:
            out.append(text[index:after_body])
            index = after_body
            continue
        out.append(text[index:found])
        out.append(f"\\{replacement}{{{label}}}{{{body}}}")
        index = after_label


def _space_text_groups(text: str) -> str:
    r"""Make the spaces inside ``\mathrm{…}`` survive into the raster."""
    out, index = [], 0
    while True:
        match = re.search(r"\\(mathrm|mathbf|mathit)\s*\{", text[index:])
        if match is None:
            out.append(text[index:])
            return "".join(out)
        start = index + match.start()
        brace = index + match.end() - 1
        body, after = _matched_group(text, brace)
        if not after or after == brace:
            out.append(text[index:brace + 1])
            index = brace + 1
            continue
        out.append(text[index:brace + 1])
        out.append(re.sub(r" +", r"\\ ", body))
        out.append("}")
        index = after


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


#: Separators an author uses to set two formulas side by side on one line.
#: Ordered widest-gap first, so a row breaks at the biggest space it has.
#: Deliberately *not* the thin spaces ``\;`` and ``\,``: those separate a
#: symbol from its neighbour inside one expression, and breaking there leaves an
#: orphan arrow or comma alone on a line.
_SIDE_BY_SIDE = (r"\qquad", r"\quad")


def _side_by_side(latex: str) -> list[str]:
    """Split one display row where its author put horizontal space.

    ``E = a, \\qquad S = b`` is two statements typeset on one line; if they do
    not fit on one line, stacking them is what a typesetter would do. The split
    is made only at **brace depth zero** — a ``\\qquad`` inside ``\\frac{…}`` or
    ``\\text{…}`` is part of one expression and breaking there would produce two
    unparsable halves.

    Parameters
    ----------
    latex : str
        One display row, already free of ``\\\\`` separators.

    Returns
    -------
    list of str
        The pieces, with a trailing comma kept on the piece it belongs to; a
        single-element list when the row has no top-level separator.

    """
    for separator in _SIDE_BY_SIDE:
        parts, depth, start = [], 0, 0
        index = 0
        while index < len(latex):
            character = latex[index]
            if character == "\\" and latex.startswith(separator, index):
                after = index + len(separator)
                # ``\quad`` must not match the start of ``\quadrant``.
                if depth == 0 and not latex[after: after + 1].isalpha():
                    piece = latex[start:index].strip()
                    if piece:
                        parts.append(piece)
                    start = after
                    index = after
                    continue
            if character == "{":
                depth += 1
            elif character == "}":
                depth = max(0, depth - 1)
            index += 1
        tail = latex[start:].strip()
        if tail:
            parts.append(tail)
        parts = [p.strip().rstrip("&").strip() for p in parts]
        parts = [p for p in parts if p]
        if len(parts) > 1:
            return parts
    return [latex]


def _scaled(tag: str, width: int) -> str:
    """Shrink an ``<img>`` fragment to *width*, keeping its aspect ratio."""
    match = re.search(r'width="(\d+)"\s+height="(\d+)"', tag or "")
    if not match:
        return tag
    current, height = int(match.group(1)), int(match.group(2))
    if current <= width or current <= 0:
        return tag
    scaled_height = max(1, round(height * width / current))
    return tag.replace(match.group(0), f'width="{width}" height="{scaled_height}"')


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

#: Big operators. Their limits become ordinary sub-/superscripts, which is what
#: an *inline* formula wants anyway — a sum with stacked limits inside a
#: sentence is a tall image that pushes the line apart.
_HTML_OPERATORS = {
    "sum": "Σ", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬",
    "oint": "∮", "bigcup": "⋃", "bigcap": "⋂", "bigoplus": "⨁",
}

#: Upright function names, as TeX sets them.
_HTML_FUNCTIONS = (
    "exp", "ln", "log", "sin", "cos", "tan", "sinh", "cosh", "tanh", "arg",
    "max", "min", "det", "dim", "lim", "sup", "inf", "erf", "erfc", "Tr",
    "arcsin", "arccos", "arctan", "Pr", "deg", "gcd", "mod", "Var", "Cov",
)

#: Script and blackboard letters that have a character of their own.
_HTML_SCRIPT = {
    "L": "ℒ", "N": "ℕ", "R": "ℝ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "𝒫",
    "H": "ℋ", "F": "ℱ", "E": "ℰ", "D": "𝒟", "O": "𝒪", "I": "ℐ", "B": "ℬ",
}

#: Accents, as combining marks placed after the letter they sit on.
_HTML_ACCENTS = {
    "hat": "\u0302", "widehat": "\u0302", "bar": "\u0304",
    "overline": "\u0304", "tilde": "\u0303", "widetilde": "\u0303",
    "vec": "\u20d7", "dot": "\u0307", "ddot": "\u0308",
    "check": "\u030c", "breve": "\u0306", "acute": "\u0301",
    "grave": "\u0300", "mathring": "\u030a",
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
    # A matrix is two-dimensional only as long as it keeps its environment; once
    # flattened to "[a, b; c, d]" it is ordinary text, and text is what an
    # inline formula should be.
    latex = _flatten_matrices(latex)
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
    swallowed = False
    while index < len(text) and text[index] == " ":
        index += 1
        swallowed = True
    # ...but TeX then sets its own space around a relation, and we do not, so
    # a swallowed space in front of one has to be given back: "λ = x", not
    # "λ= x".
    following = ""
    if swallowed and index < len(text):
        nxt = text[index]
        if nxt in _INLINE_RELATIONS or nxt == "-":
            following = "&#8201;"
    if name in _HTML_SPACES:
        return _HTML_SPACES[name], index
    if name in _HTML_SYMBOLS:
        symbol = _HTML_SYMBOLS[name]
        if symbol in _SPACED_SYMBOLS:
            return f"&#8201;{symbol}&#8201;", index
        return symbol + following, index
    if name in _HTML_OPERATORS:
        return _HTML_OPERATORS[name] + following, index
    if name in _HTML_FUNCTIONS:
        return name + following, index
    if name in ("frac", "tfrac", "dfrac", "cfrac"):
        numerator, index = _inline_atom(text, index)
        denominator, index = _inline_atom(text, index)
        return f"{_bracket(numerator)}/{_bracket(denominator)}", index
    if name == "sqrt":
        # ``\sqrt[3]{x}`` -- the index is shown before the radical.
        degree = ""
        if index < len(text) and text[index] == "[":
            close = text.find("]", index)
            if close < 0:
                raise _UnsupportedInline("unterminated root index")
            degree, _ = _inline_group(text[index + 1: close], 0, False)
            degree = f"<sup>{degree}</sup>"
            index = close + 1
        radicand, index = _inline_atom(text, index)
        return f"{degree}&radic;{_bracket(radicand, always=True)}", index
    if name in _HTML_ACCENTS:
        base, index = _inline_atom(text, index)
        return base + _HTML_ACCENTS[name], index
    if name in ("mathcal", "mathscr"):
        inner, index = _inline_atom(text, index)
        letter = re.sub(r"<[^>]+>", "", inner)
        return _HTML_SCRIPT.get(letter, f"<i>{letter}</i>"), index
    if name in ("boldsymbol", "pmb"):
        inner, index = _inline_atom(text, index)
        return f"<b>{inner}</b>", index
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
        # ...and inside words a hyphen is a hyphen, not a minus sign: this is
        # prose set in a formula, so "shot-noise" must not become "shot−noise".
        inner = inner.replace("−", "-")
        return f"{open_tag}{inner}{close_tag}", index
    if name in ("left", "right", "big", "bigl", "bigr", "Big", "Bigl", "Bigr"):
        return "", index
    raise _UnsupportedInline(f"command {name!r}")


def _bracket(html: str, always: bool = False) -> str:
    """Parenthesise a fraction part when leaving it bare would change what it says.

    An inline fraction is written with a slash — ``a/b`` — because a stacked one
    is a picture in the middle of a sentence. The slash binds tighter than a sum
    or a difference, so ``(a+b)/c`` has to keep its parentheses.
    """
    plain = re.sub(r"<[^>]+>", "", html)
    plain = plain.replace("&#8201;", " ").replace("&nbsp;", " ").strip()
    if plain.startswith("(") and plain.endswith(")"):
        return html
    if always:
        return html if len(plain) <= 1 else f"({html})"
    if len(plain) <= 1:
        return html
    if re.search(r"[+\-−±×⋅·/ ]", plain):
        return f"({html})"
    return html


#: Characters TeX sets as relations or binary operators. A command name eats
#: the space that terminates it, so ``\lambda = x`` would come out as "λ= x"
#: unless the space is put back in front of one of these.
_INLINE_RELATIONS = set("=<>+\u2212\u00b1\u2213\u2260\u2264\u2265\u2248\u221d")


def _inline_char(char: str) -> str:
    """Convert one ordinary character, italicising variables as TeX does."""
    if char.isalpha():
        return f"<i>{char}</i>"
    if char == "-":
        # A hyphen is not a minus sign: it is half the width and sits lower,
        # and in "E(1-E)" the difference is visible at reading size.
        return "\u2212"
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

    #: Widest a displayed formula may be, in the same pixels the text column is
    #: measured in. A formula wider than the column is not merely ugly: Qt gives
    #: the *whole page* a horizontal scrollbar, so every paragraph on it starts
    #: sliding sideways under the reader.
    MAX_DISPLAY_WIDTH = 860

    def __init__(
        self,
        colour: str = "#202020",
        font_size: float = 11.0,
        max_width: int = MAX_DISPLAY_WIDTH,
    ):
        self.colour = colour
        self.font_size = float(font_size)
        self.max_width = int(max_width)
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
        rows = []
        for row in math_rows(latex):
            rows.extend(self._fit(row))
        return '<p align="center" class="math-display">' + "<br>".join(rows) + "</p>"

    def _fit(self, row: str) -> list[str]:
        """Return the fragments for one source row, none wider than the column.

        A row written as ``A, \\qquad B`` is two formulas set side by side, and
        when the pair does not fit the typographic answer is to stack them —
        *not* to shrink them, which is what leaves one equation on a page
        visibly smaller than the rest. Only when a single indivisible formula is
        still too wide is it scaled down, because the alternative is a page that
        scrolls sideways.
        """
        tag = self._one(row, True)
        if self._width_of(tag) <= self.max_width:
            return [tag]
        parts = _side_by_side(row)
        if len(parts) > 1:
            fitted = []
            for part in parts:
                fitted.extend(self._fit(part))
            return fitted
        return [_scaled(tag, self.max_width)]

    @staticmethod
    def _width_of(tag: str) -> int:
        """Displayed width of an ``<img>`` fragment, or 0 when it is text."""
        match = re.search(r'width="(\d+)"', tag or "")
        return int(match.group(1)) if match else 0

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
        # A tall inline image bottom-aligned on the baseline shoves the line
        # apart and floats above the words; centring it on the line is the
        # closest Qt gets to a baseline-aware inline formula.
        style = "" if display else ' style="vertical-align: middle"'
        return f'<img src="data:image/png;base64,{encoded}"{attrs}{style} alt="{alt}">'


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
