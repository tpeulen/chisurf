"""Atom-selection expressions, evaluated against ChiSurf's atom array.

Selection strings reach this module from the GUI and from saved projects, so
the syntax is the one users and files already contain -- ``name CA``,
``resname ALA and resSeq 5``, ``protein and not water``. Keeping it identical
is the point: this replaces an external parser, and changing the language at
the same time would silently invalidate every selection anyone has saved.

The grammar
-----------
=========================== ================================================
``all`` / ``everything``    every atom; ``none``/``nothing`` for the empty set
``protein``, ``water``,     residue-name keyword sets
``nucleic``, ``backbone``,
``sidechain``, ``hydrogen``
``name CA``                 atom name
``resname ALA``             residue name
``resSeq 5``                residue number **as written in the file**
``resid 5``                 residue **index**, counted from zero
``chainid 0``               chain index, counted from zero
``chain A``                 chain identifier as written
``index 7``                 atom index
``element C`` / ``type C``  element symbol
``mass``, ``charge``,       numeric per-atom fields
``radius``, ``bfactor``
=========================== ================================================

Values may be a list (``name CA CB``), a range (``resSeq 5 to 9``), or a
comparison (``mass > 12``, ``resSeq >= 5``). Terms combine with ``and``/``&&``,
``or``/``||``, ``not``/``!`` and parentheses, with the usual precedence.

Notes
-----
``resid`` and ``resSeq`` are different and the difference bites: a structure
starting at residue 17 has ``resid 0`` and ``resSeq 17`` pointing at the same
atom. The same holds for ``chainid`` (an index) against ``chain`` (whatever
letter the file uses).
"""

from __future__ import annotations

import re

import numpy as np

__all__ = ["SelectionError", "select", "selection_mask"]


class SelectionError(ValueError):
    """Raised when a selection expression cannot be parsed or evaluated."""


#: Residue names treated as water.
WATER_RESIDUES = frozenset({"HOH", "H2O", "WAT", "SOL", "TIP", "TIP3", "TIP4", "SPC"})

#: The twenty standard amino acids plus the usual protonation variants.
PROTEIN_RESIDUES = frozenset(
    {
        "ALA",
        "ARG",
        "ASN",
        "ASP",
        "CYS",
        "GLN",
        "GLU",
        "GLY",
        "HIS",
        "ILE",
        "LEU",
        "LYS",
        "MET",
        "PHE",
        "PRO",
        "SER",
        "THR",
        "TRP",
        "TYR",
        "VAL",
        "HID",
        "HIE",
        "HIP",
        "HSD",
        "HSE",
        "HSP",
        "CYX",
        "CYM",
        "ASH",
        "GLH",
        "LYN",
        "MSE",
        "SEC",
        "PYL",
    }
)

#: Nucleic-acid residues, DNA and RNA, with the common 3- and 5-prime forms.
NUCLEIC_RESIDUES = frozenset(
    {
        "A",
        "C",
        "G",
        "T",
        "U",
        "DA",
        "DC",
        "DG",
        "DT",
        "DU",
        "RA",
        "RC",
        "RG",
        "RU",
        "ADE",
        "CYT",
        "GUA",
        "THY",
        "URA",
        "A3",
        "A5",
        "C3",
        "C5",
        "G3",
        "G5",
        "T3",
        "T5",
        "U3",
        "U5",
    }
)

#: Protein backbone atom names. Deliberately *not* including ``OXT``: the
#: language being reproduced counts only these four, and adding the terminal
#: oxygen would move one atom per chain between ``backbone`` and ``sidechain``.
BACKBONE_ATOMS = frozenset({"N", "CA", "C", "O"})

#: ``sidechain`` is not simply "protein and not backbone" -- the backbone
#: *hydrogens* and the terminal oxygen belong to neither set. Leaving them in
#: put 544 extra atoms in the sidechain of the test structure.
NON_SIDECHAIN_ATOMS = frozenset(BACKBONE_ATOMS | {"H", "HA", "H1", "H2", "H3", "OXT"})

#: Fields addressable by name, mapped to the atom-array column behind them.
_STRING_FIELDS = {
    "name": "atom_name",
    "resname": "res_name",
    "chain": "chain",
    "element": "element",
    "type": "element",
}
_NUMERIC_FIELDS = {
    "resseq": "res_id",
    "index": "i",
    "serial": "atom_id",
    "mass": "mass",
    "charge": "charge",
    "radius": "radius",
    "bfactor": "bfactor",
}
#: Fields that are an *index* rather than a stored value, so they are computed.
_INDEX_FIELDS = ("resid", "chainid")

_KEYWORDS = (
    "all",
    "everything",
    "none",
    "nothing",
    "water",
    "waters",
    "protein",
    "nucleic",
    "backbone",
    "sidechain",
    "hydrogen",
)
_COMPARISONS = ("==", "!=", "<=", ">=", "<", ">")

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<op>==|!=|<=|>=|<|>|&&|\|\||!)
      | (?P<quoted>'[^']*'|\"[^\"]*\")
      | (?P<word>[A-Za-z_][A-Za-z_0-9]*)
      | (?P<number>-?\d+\.?\d*)
      | (?P<other>\S)
    )""",
    re.VERBOSE,
)


def _tokenize(expression: str) -> list[str]:
    """Split *expression* into tokens."""
    tokens, pos = [], 0
    for match in _TOKEN.finditer(expression):
        if match.start() != pos and expression[pos : match.start()].strip():
            raise SelectionError(f"cannot parse {expression!r} near {expression[pos:]!r}")
        pos = match.end()
        if match.group("other"):
            raise SelectionError(f"unexpected {match.group('other')!r} in {expression!r}")
        tokens.append(match.group(match.lastgroup))
    return tokens


def _residue_index(atoms: np.ndarray) -> np.ndarray:
    """Return a residue index per atom, numbered from zero in file order.

    A residue is a (chain, res_id, res_name) run: numbering by ``res_id`` alone
    merges the residue 5 of every chain, and numbering by unique value sorts
    them, which is not the file's order.
    """
    keys = np.stack(
        [
            atoms["chain"].astype("U4"),
            atoms["res_id"].astype("U12"),
            atoms["res_name"].astype("U5"),
        ],
        axis=1,
    )
    changed = np.ones(len(atoms), dtype=bool)
    if len(atoms) > 1:
        changed[1:] = np.any(keys[1:] != keys[:-1], axis=1)
    return np.cumsum(changed) - 1


def _chain_index(atoms: np.ndarray) -> np.ndarray:
    """Return a chain index per atom, numbered from zero in file order."""
    chains = atoms["chain"]
    changed = np.ones(len(atoms), dtype=bool)
    if len(atoms) > 1:
        changed[1:] = chains[1:] != chains[:-1]
    return np.cumsum(changed) - 1


class _Parser:
    """Recursive-descent parser over the token list, producing a boolean mask."""

    def __init__(self, tokens: list[str], atoms: np.ndarray):
        self.tokens = tokens
        self.pos = 0
        self.atoms = atoms

    # -- token helpers ------------------------------------------------------
    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

    def accept(self, *values):
        if (token := self.peek()) is not None and token.lower() in values:
            self.pos += 1
            return token.lower()
        return None

    # -- grammar ------------------------------------------------------------
    def parse(self) -> np.ndarray:
        mask = self.parse_or()
        if self.peek() is not None:
            raise SelectionError(f"trailing {' '.join(self.tokens[self.pos :])!r}")
        return mask

    def parse_or(self) -> np.ndarray:
        mask = self.parse_and()
        while self.accept("or", "||"):
            mask = mask | self.parse_and()
        return mask

    def parse_and(self) -> np.ndarray:
        mask = self.parse_not()
        while self.accept("and", "&&"):
            mask = mask & self.parse_not()
        return mask

    def parse_not(self) -> np.ndarray:
        if self.accept("not", "!"):
            return ~self.parse_not()
        return self.parse_term()

    def parse_term(self) -> np.ndarray:
        token = self.take()
        if token is None:
            raise SelectionError("expression ended early")
        if token == "(":
            mask = self.parse_or()
            if self.take() != ")":
                raise SelectionError("unbalanced parenthesis")
            return mask
        lowered = token.lower()
        if lowered in _KEYWORDS:
            return self._keyword(lowered)
        if lowered in _STRING_FIELDS:
            return self._string_field(_STRING_FIELDS[lowered])
        if lowered in _NUMERIC_FIELDS:
            return self._numeric_field(self.atoms[_NUMERIC_FIELDS[lowered]])
        if lowered in _INDEX_FIELDS:
            values = _residue_index(self.atoms) if lowered == "resid" else _chain_index(self.atoms)
            return self._numeric_field(values)
        raise SelectionError(f"unknown selection keyword {token!r}")

    # -- leaves -------------------------------------------------------------
    def _keyword(self, word: str) -> np.ndarray:
        names = np.char.upper(self.atoms["res_name"].astype(str))
        if word in ("all", "everything"):
            return np.ones(len(self.atoms), dtype=bool)
        if word in ("none", "nothing"):
            return np.zeros(len(self.atoms), dtype=bool)
        if word in ("water", "waters"):
            return np.isin(names, list(WATER_RESIDUES))
        if word == "protein":
            return np.isin(names, list(PROTEIN_RESIDUES))
        if word == "nucleic":
            return np.isin(names, list(NUCLEIC_RESIDUES))
        if word == "backbone":
            atom_names = np.char.upper(self.atoms["atom_name"].astype(str))
            return np.isin(names, list(PROTEIN_RESIDUES)) & np.isin(
                atom_names, list(BACKBONE_ATOMS)
            )
        if word == "sidechain":
            atom_names = np.char.upper(self.atoms["atom_name"].astype(str))
            return np.isin(names, list(PROTEIN_RESIDUES)) & ~np.isin(
                atom_names, list(NON_SIDECHAIN_ATOMS)
            )
        # hydrogen: the element field is authoritative when populated, and the
        # name is the fallback -- plenty of PDBs leave the element column blank.
        element = np.char.upper(self.atoms["element"].astype(str))
        by_element = element == "H"
        if by_element.any():
            return by_element
        atom_names = np.char.upper(self.atoms["atom_name"].astype(str))
        return np.char.startswith(atom_names, "H")

    def _values(self) -> list[str]:
        """Consume the value list that follows a field name."""
        values = []
        while (token := self.peek()) is not None:
            if token in ("(", ")") or token.lower() in ("and", "or", "not", "&&", "||", "!"):
                break
            values.append(self.take())
        if not values:
            raise SelectionError("a selection field needs a value")
        return values

    def _string_field(self, column: str) -> np.ndarray:
        if (comparison := self.accept(*_COMPARISONS)) is not None:
            wanted = self.take()
            column_values = np.char.upper(self.atoms[column].astype(str))
            if comparison == "==":
                return column_values == wanted.strip("'\"").upper()
            if comparison == "!=":
                return column_values != wanted.strip("'\"").upper()
            raise SelectionError(f"{comparison!r} does not apply to text")
        wanted = [value.strip("'\"").upper() for value in self._values()]
        return np.isin(np.char.upper(self.atoms[column].astype(str)), wanted)

    def _numeric_field(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values)
        if (comparison := self.accept(*_COMPARISONS)) is not None:
            number = self._number(self.take())
            return {
                "==": values == number,
                "!=": values != number,
                "<": values < number,
                "<=": values <= number,
                ">": values > number,
                ">=": values >= number,
            }[comparison]
        tokens = self._values()
        # `resSeq 5 to 9` is inclusive at both ends, as in the language this
        # replaces -- an exclusive upper bound would quietly drop one residue.
        if len(tokens) == 3 and tokens[1].lower() in ("to", "through", "-"):
            low, high = self._number(tokens[0]), self._number(tokens[2])
            return (values >= low) & (values <= high)
        wanted = [self._number(token) for token in tokens]
        return np.isin(values, wanted)

    @staticmethod
    def _number(token: str) -> float:
        try:
            return float(token)
        except (TypeError, ValueError):
            raise SelectionError(f"expected a number, got {token!r}") from None


def selection_mask(atoms: np.ndarray, expression: str) -> np.ndarray:
    """Return a boolean mask of the atoms *expression* selects.

    Parameters
    ----------
    atoms : numpy.ndarray
        ChiSurf's structured atom array (see
        :mod:`chisurf.core.fio.structure.coordinates`).
    expression : str
        Selection expression.

    Returns
    -------
    numpy.ndarray
        Boolean mask, one entry per atom.

    Raises
    ------
    SelectionError
        If the expression cannot be parsed.
    """
    tokens = _tokenize(expression)
    if not tokens:
        raise SelectionError("empty selection expression")
    return _Parser(tokens, atoms).parse()


def select(atoms: np.ndarray, expression: str) -> np.ndarray:
    """Return the indices of the atoms *expression* selects.

    Parameters
    ----------
    atoms : numpy.ndarray
        ChiSurf's structured atom array.
    expression : str
        Selection expression.

    Returns
    -------
    numpy.ndarray
        Integer indices, ascending.
    """
    return np.flatnonzero(selection_mask(atoms, expression))
