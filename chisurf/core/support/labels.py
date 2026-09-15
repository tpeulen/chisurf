"""One name for the code, one for the reader.

A quantity in this program has two names. Code, translators, documentation
tables and view-spec keys want ``tau_D(0)``, ``R_DA``, ``Phi_D`` — plain ASCII,
greppable, diffable, translatable. A physicist reading the screen wants
:math:`\\tau_{D(0)}`, :math:`R_{DA}`, :math:`\\Phi_D`.

Writing the second form by hand as HTML in every view spec — ``"&tau;<sub>D(0)
</sub>"`` — buys the typography and loses everything else: the string stops
being searchable, the translator is handed markup, and the generated
documentation cell renders as literal angle brackets. So the plain spelling
stays the single source of truth and this module derives the typeset one:

>>> to_rich("tau_D(0)")
'&tau;<sub>D(0)</sub>'
>>> to_rich("R_DA")
'R<sub>DA</sub>'
>>> to_plain("&kappa;<sup>2</sup>")
'κ2'

The convention is the one already used in the sources: ``_`` opens a subscript,
``^`` a superscript, each running to the next delimiter, or braces for an
explicit group (``tau_{D,app}``). A spelled-out Greek letter becomes the letter.

Nothing here imports Qt: the same conversion is needed by the headless
documentation generator and by the RPC layer, not only by widgets.
"""

from __future__ import annotations

import html
import re

__all__ = ["GREEK", "to_rich", "to_plain", "to_unicode", "has_markup"]

#: Digits and signs that Unicode can actually place as sub- and superscripts.
#: Letters are deliberately absent: Unicode has no subscript ``D`` or ``A``, so
#: ``R_DA`` has no honest single-line form and keeps its underscore rather than
#: being silently mangled into something that looks like a different quantity.
_SUBSCRIPT_DIGITS = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUPERSCRIPT_DIGITS = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")

#: Spelled-out Greek names and the letters they denote. Capitalised keys give
#: the capital letter, so ``Phi_D`` is the donor quantum yield and ``phi`` the
#: lower-case letter.
GREEK: dict[str, str] = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "µ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Chi": "Χ",
    "Psi": "Ψ", "Omega": "Ω",
}

#: Maximal runs of ASCII letters. Matching whole runs rather than the Greek
#: names directly is what makes ``alphabet`` survive: the run is the entire word,
#: which is not in :data:`GREEK`. A neighbour test would have to define "letter",
#: and Python's ``\w`` counts ``²`` as one — which silently left ``kappa²``
#: untypeset.
_WORD_RE = re.compile(r"[A-Za-z]+")

#: ``_x`` / ``^x`` / ``_{x y}``. The unbraced run takes letters and digits (any
#: script, so ``r_D∞`` keeps the infinity inside the subscript) plus the
#: punctuation that occurs inside real subscripts — ``tau_D(0)``, ``x_D,0``,
#: ``k_-1`` — but stops at whitespace, ``/`` and a further ``_``/``^``.
_SUBSUP_RE = re.compile(r"([_^])(?:\{([^}]*)\}|((?:[^\W_]|[,.+()∞-])+))")

#: Anything that looks like it was already typeset by hand.
_MARKUP_RE = re.compile(r"<(sub|sup|b|i|br|span|font)\b[^>]*>|&[A-Za-z][A-Za-z0-9]*;")

#: Tags to drop when going the other way.
_TAG_RE = re.compile(r"<[^>]+>")


def has_markup(text: str) -> bool:
    """Whether ``text`` already carries hand-written rich-text markup.

    Parameters
    ----------
    text : str
        The candidate label.

    Returns
    -------
    bool
        True when the string contains an HTML tag or character entity, in which
        case :func:`to_rich` leaves it alone.
    """
    return bool(text) and bool(_MARKUP_RE.search(str(text)))


def to_rich(text: str) -> str:
    """Typeset a plain label: Greek names to letters, ``_``/``^`` to scripts.

    A label that already contains markup is returned unchanged, so the many
    view specs and models that spell their labels out in HTML keep working and
    can be converted at leisure.

    Parameters
    ----------
    text : str
        Plain label, e.g. ``"tau_D(0) (ns)"``.

    Returns
    -------
    str
        An HTML fragment suitable for a rich-text ``QLabel``.

    Examples
    --------
    >>> to_rich("Phi_D")
    '&Phi;<sub>D</sub>'
    >>> to_rich("kappa^2")
    '&kappa;<sup>2</sup>'
    >>> to_rich("Mean R_app/R_DA")
    'Mean R<sub>app</sub>/R<sub>DA</sub>'
    >>> to_rich("already <sub>done</sub>")
    'already <sub>done</sub>'
    """
    if not text:
        return ""
    source = str(text)
    if has_markup(source):
        return source

    escaped = html.escape(source, quote=False)
    # Named entities rather than the literal letters: a QLabel renders both, but
    # entities survive a trip through a non-UTF-8 aware layer intact.
    lettered = _WORD_RE.sub(
        lambda m: f"&{m.group(0)};" if m.group(0) in GREEK else m.group(0), escaped
    )

    def script(match: re.Match) -> str:
        tag = "sub" if match.group(1) == "_" else "sup"
        braced = match.group(2) is not None
        body = match.group(2) if braced else match.group(3)
        trailing = ""
        if not braced:
            # A subscript may contain parentheses (``tau_D(0)``) but must not
            # eat the one that closes an enclosing group (``P(R_DA)``), nor a
            # comma or full stop that belongs to the sentence around it.
            while body and (
                (body[-1] == ")" and body.count(")") > body.count("("))
                or body[-1] in ",."
            ):
                trailing = body[-1] + trailing
                body = body[:-1]
        if not body:
            return match.group(0)
        return f"<{tag}>{body}</{tag}>{trailing}"

    return _SUBSUP_RE.sub(script, lettered)


def to_plain(text: str) -> str:
    """Strip a label back to readable text, for tooltips, tables and logs.

    Markup is removed and entities resolved, so a hand-written
    ``"&tau;<sub>0</sub>"`` and a generated one both read as ``τ0``. A label
    that was already plain comes back unchanged.

    Parameters
    ----------
    text : str
        Plain or rich label.

    Returns
    -------
    str
        The same label with no tags and no character entities.

    Examples
    --------
    >>> to_plain("R<sub>DA</sub>")
    'RDA'
    >>> to_plain("tau_D(0)")
    'tau_D(0)'
    """
    if not text:
        return ""
    return html.unescape(_TAG_RE.sub("", str(text)))


def to_unicode(text: str) -> str:
    """Typeset a plain label using Unicode alone, for places markup cannot go.

    A table cell, a plot axis, a CSV header and a log line all render one flat
    string. This gives them the Greek letters and — where Unicode has the
    glyphs — real sub- and superscripts, so a factor table reads ``α`` and
    ``R₀`` rather than ``alpha`` and ``r0``.

    Only digits and signs have subscript glyphs, so ``R_DA`` keeps its
    underscore: there is no subscript ``D``, and dropping to ``RDA`` would name
    a different thing. Use :func:`to_rich` wherever markup is allowed.

    Parameters
    ----------
    text : str
        Plain label, e.g. ``"r0"`` or ``"kappa^2"``.

    Returns
    -------
    str
        The label with Greek letters and Unicode scripts applied.

    Examples
    --------
    >>> to_unicode("gamma")
    'γ'
    >>> to_unicode("kappa^2")
    'κ²'
    >>> to_unicode("R_0")
    'R₀'
    >>> to_unicode("R_DA")
    'R_DA'
    """
    if not text:
        return ""
    source = _TAG_RE.sub("", html.unescape(str(text)))
    lettered = _WORD_RE.sub(
        lambda m: GREEK.get(m.group(0), m.group(0)), source
    )

    def script(match: re.Match) -> str:
        body = match.group(2) if match.group(2) is not None else match.group(3)
        table = _SUBSCRIPT_DIGITS if match.group(1) == "_" else _SUPERSCRIPT_DIGITS
        converted = body.translate(table)
        # All-or-nothing: a partially converted run (``R_D0`` -> ``R_D₀``) reads
        # worse than leaving it alone.
        return converted if converted != body and not any(
            c.isalpha() for c in body
        ) else match.group(0)

    return _SUBSUP_RE.sub(script, lettered)
