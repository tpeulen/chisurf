"""PyMOL's selection keywords, transcribed from its selector.

Every selection keyword PyMOL knows lives in one table in its source —
``Keyword[]`` in ``layer3/Selector.cpp`` — together with a code whose suffix
encodes what the keyword *takes*::

    SELE_RSNs   's'  one value list        resn ALA+GLY
    SELE_HETz   'z'  nothing              hetatm
    SELE_BVLx   'x'  operator and number  b < 30
    SELE_BYR1   '1'  one selection        byres (chain A)
    SELE_AND2   '2'  infix, two operands  ... and ...
    SELE_ARD_   '_'  number, selection    around 5, chain A

Keeping that shape here rather than spreading it through the parser is what
makes the parser able to *reach* every keyword. The bug this module exists to
kill was a hand-maintained tuple of property names in the parser that had drifted
from the evaluator: ``resn`` was implemented and evaluated correctly, but the
parser did not list it, so ``resn NAG`` silently parsed as an implicit ``AND`` of
two bare identifiers and matched nothing. One table, consulted by both halves,
cannot drift like that.

Aliases are PyMOL's, including the deprecated ``;`` forms and the ``c.``-style
abbreviations, so a selection copied out of a twenty-year-old script still works.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Arity",
    "Keyword",
    "KEYWORDS",
    "CANONICAL",
    "lookup",
    "split_keyword",
]


class Arity(Enum):
    """What a keyword consumes, mirroring the suffix of PyMOL's ``SELE_`` codes."""

    #: ``z`` — a class of atoms, no argument: ``hetatm``, ``solvent``.
    FLAG = "z"
    #: ``s`` — a value list: ``resn ALA+GLY``, ``resi 10-20``.
    STRING = "s"
    #: ``x`` — a comparison against a number: ``b < 30``.
    NUMERIC = "x"
    #: ``1`` — one selection, expanded: ``byres``, ``bychain``.
    UNARY = "1"
    #: ``2`` — infix between two selections: ``and``, ``or``, ``in``.
    BINARY = "2"
    #: ``_`` — a distance then a selection: ``around 5, chain A``.
    DIST = "_"
    #: ``_`` with the ``of`` connective: ``within 5 of chain A``.
    DIST_OF = "of"
    #: ``p.`` — a named custom property.
    PROP = "p"


@dataclass(frozen=True)
class Keyword:
    """One selection keyword: its canonical name and what it takes."""

    canonical: str
    arity: Arity


#: canonical name -> every spelling PyMOL accepts for it.
#:
#: Transcribed from ``Keyword[]`` in ``layer3/Selector.cpp``. The first alias of
#: each row is the canonical name itself.
CANONICAL: dict[str, tuple[Arity, tuple[str, ...]]] = {
    # ---------------------------------------------------------------- operators
    "and": (Arity.BINARY, ("and", "&")),
    "or": (Arity.BINARY, ("or", "|")),
    "subtract": (Arity.BINARY, ("-",)),
    "in": (Arity.BINARY, ("in",)),
    "like": (Arity.BINARY, ("like", "l;", "l.")),
    # ------------------------------------------------------------ expand by ...
    "byres": (Arity.UNARY, ("byres", "byresidue", "byresi", "br;", "br.")),
    "bychain": (Arity.UNARY, ("bychain", "bc.")),
    "byobject": (Arity.UNARY, ("byobject", "byobj", "bo;", "bo.")),
    "bymolecule": (Arity.UNARY, ("bymolecule", "bymol", "bm.")),
    "bysegment": (Arity.UNARY, ("bysegment", "byseg", "bysegi", "bs.")),
    "bycalpha": (Arity.UNARY, ("bycalpha", "bca.")),
    "bound_to": (Arity.UNARY, ("bound_to", "bto.")),
    "byring": (Arity.UNARY, ("byring",)),
    "bycell": (Arity.UNARY, ("bycell",)),
    "first": (Arity.UNARY, ("first",)),
    "last": (Arity.UNARY, ("last",)),
    # ------------------------------------------------------------- distance ops
    "around": (Arity.DIST, ("around", "a;", "a.")),
    "expand": (Arity.DIST, ("expand", "x;", "x.")),
    "extend": (Arity.DIST, ("extend", "xt.")),
    "gap": (Arity.DIST, ("gap",)),
    "within": (Arity.DIST_OF, ("within", "w.")),
    "near_to": (Arity.DIST_OF, ("near_to", "nto.")),
    "beyond": (Arity.DIST_OF, ("beyond", "be.")),
    # ---------------------------------------------------------- named properties
    "name": (Arity.STRING, ("name", "n;", "n.")),
    "elem": (Arity.STRING, ("elem", "element", "symbol", "e;", "e.")),
    "resi": (Arity.STRING, ("resi", "residue", "resident", "resid", "i;", "i.")),
    "resn": (Arity.STRING, ("resn", "resname", "r;", "r.")),
    "chain": (Arity.STRING, ("chain", "c;", "c.")),
    "segi": (Arity.STRING, ("segi", "segment", "segid", "s;", "s.")),
    "ss": (Arity.STRING, ("ss",)),
    "alt": (Arity.STRING, ("alt", "altloc")),
    "index": (Arity.STRING, ("index", "idx.")),
    "id": (Arity.STRING, ("id",)),
    "rank": (Arity.STRING, ("rank",)),
    "object": (Arity.STRING, ("object", "model", "o.", "m;", "m.")),
    "rep": (Arity.STRING, ("rep",)),
    "color": (Arity.STRING, ("color",)),
    "cartoon_color": (Arity.STRING, ("cartoon_color",)),
    "ribbon_color": (Arity.STRING, ("ribbon_color",)),
    "label": (Arity.STRING, ("label",)),
    "flag": (Arity.STRING, ("flag", "f;", "f.")),
    "state": (Arity.STRING, ("state",)),
    "stereo": (Arity.STRING, ("stereo",)),
    "numeric_type": (Arity.STRING, ("numeric_type", "nt;", "nt.")),
    "text_type": (Arity.STRING, ("text_type", "tt;", "tt.")),
    "custom": (Arity.STRING, ("custom",)),
    "pepseq": (Arity.STRING, ("pepseq", "ps.")),
    "selection": (Arity.STRING, ("%",)),
    # ------------------------------------------------------- numeric properties
    "b": (Arity.NUMERIC, ("b",)),
    "q": (Arity.NUMERIC, ("q",)),
    "x": (Arity.NUMERIC, ("x",)),
    "y": (Arity.NUMERIC, ("y",)),
    "z": (Arity.NUMERIC, ("z",)),
    "partial_charge": (Arity.NUMERIC, ("partial_charge", "pc;", "pc.")),
    "formal_charge": (Arity.NUMERIC, ("formal_charge", "fc;", "fc.")),
    # ------------------------------------------------------------ atom classes
    "all": (Arity.FLAG, ("all", "*")),
    "none": (Arity.FLAG, ("none",)),
    "hetatm": (Arity.FLAG, ("hetatm", "het")),
    "hydro": (Arity.FLAG, ("hydro", "hydrogens", "h;", "h.")),
    "visible": (Arity.FLAG, ("visible", "v;", "v.")),
    "enabled": (Arity.FLAG, ("enabled",)),
    "masked": (Arity.FLAG, ("masked", "msk.")),
    "protected": (Arity.FLAG, ("protected",)),
    "bonded": (Arity.FLAG, ("bonded",)),
    "center": (Arity.FLAG, ("center",)),
    "origin": (Arity.FLAG, ("origin",)),
    "donors": (Arity.FLAG, ("donors", "don.")),
    "acceptors": (Arity.FLAG, ("acceptors", "acc.")),
    "delocalized": (Arity.FLAG, ("delocalized", "deloc.")),
    "fixed": (Arity.FLAG, ("fixed", "fxd.")),
    "restrained": (Arity.FLAG, ("restrained", "rst.")),
    "polymer": (Arity.FLAG, ("polymer", "pol.")),
    "polymer.protein": (Arity.FLAG, ("polymer.protein",)),
    "polymer.nucleic": (Arity.FLAG, ("polymer.nucleic",)),
    "organic": (Arity.FLAG, ("organic", "org.")),
    "inorganic": (Arity.FLAG, ("inorganic", "ino.")),
    "solvent": (Arity.FLAG, ("solvent", "sol.")),
    "guide": (Arity.FLAG, ("guide",)),
    "present": (Arity.FLAG, ("present", "pr.")),
    "metals": (Arity.FLAG, ("metals",)),
    "backbone": (Arity.FLAG, ("backbone", "bb.")),
    "sidechain": (Arity.FLAG, ("sidechain", "sc.")),
    "hba": (Arity.FLAG, ("hba.",)),
    "hbd": (Arity.FLAG, ("hbd.",)),
    # ---------------------------------------------------------------- custom
    "p": (Arity.PROP, ("p.",)),
}


def _build() -> dict[str, Keyword]:
    """Invert :data:`CANONICAL` into an alias lookup."""
    table: dict[str, Keyword] = {}
    for canonical, (arity, aliases) in CANONICAL.items():
        for alias in aliases:
            table[alias] = Keyword(canonical, arity)
    return table


#: Every spelling -> the keyword it means. Lower-cased keys.
KEYWORDS: dict[str, Keyword] = _build()

#: Abbreviations whose value may be written with no space (``c.A``, ``n.CA``).
#: PyMOL's tokenizer allows this, and published scripts rely on it.
_GLUED = tuple(
    sorted(
        (alias for alias in KEYWORDS if alias.endswith((".", ";"))),
        key=len,
        reverse=True,
    )
)


def lookup(word: str) -> Keyword | None:
    """Return the keyword ``word`` names, or ``None`` if it is not one.

    Parameters
    ----------
    word : str
        A token from a selection expression; case is ignored, as in PyMOL.

    Returns
    -------
    Keyword or None
        The keyword, or ``None`` — in which case the word is an object or
        named-selection reference, not a keyword.
    """
    return KEYWORDS.get((word or "").strip().lower())


def split_keyword(word: str) -> tuple[Keyword, str] | None:
    """Split an abbreviation from a value glued onto it.

    ``c.A`` and ``c. A`` mean the same thing in PyMOL, so the parser has to cope
    with the value arriving inside the same token as the keyword.

    Parameters
    ----------
    word : str
        A token from a selection expression.

    Returns
    -------
    tuple or None
        ``(keyword, remainder)`` where ``remainder`` is ``""`` when the token was
        the bare abbreviation, or ``None`` if the token does not start with a
        recognised abbreviation.
    """
    lowered = (word or "").strip().lower()
    if not lowered:
        return None
    direct = KEYWORDS.get(lowered)
    if direct is not None:
        return direct, ""
    for alias in _GLUED:
        if lowered.startswith(alias) and len(lowered) > len(alias):
            return KEYWORDS[alias], word.strip()[len(alias):]
    return None
