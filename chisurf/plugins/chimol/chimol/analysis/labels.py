"""Atom labels, and the expression language PyMOL labels them with.

``cmd.label`` does not take a template string — it takes a **Python expression**
evaluated once per atom with that atom's properties in scope, which is why
PyMOL's own Label menu is full of entries like ``"%s-%s" % (resn, resi)`` and
``'%1.2f' % b``. Anything less than that is not the same feature: half the
usefulness of labels is computing them.

The property names are PyMOL's (``name``, ``resn``, ``resi``, ``chain``,
``elem``, ``b``, ``q``, ``vdw``, ``oneletter``, ``segi``, ``index``, ``x/y/z``),
so the expressions in its menus and in published scripts work unchanged.

Evaluation is deliberately **not** a bare ``eval`` over builtins: a label
expression arrives from a menu, a script or a text box, and it should not be able
to open a file. Only the atom properties and a small set of formatting helpers are
in scope.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "ATOM_PROPERTIES",
    "atom_namespace",
    "label_expression",
    "evaluate_labels",
]

#: PyMOL property name -> the field it reads in chimol's atom array.
#:
#: This is the one mapping between PyMOL's vocabulary and the atom dtype, and it
#: is shared by ``label``, ``iterate`` and ``alter``. It has to be: ``alter`` used
#: to carry a second, hand-written copy naming ``chain_id``, ``b_factor`` and
#: ``occupancy`` -- none of which are fields -- so ``alter sele, b=42`` wrote
#: nothing at all while reporting how many atoms it had altered.
ATOM_PROPERTIES: dict[str, str] = {
    "name": "atom_name",
    "resn": "res_name",
    "resi": "res_id",
    "resv": "res_id",
    "chain": "chain",
    "segi": "segi",
    "elem": "element",
    "b": "bfactor",
    "q": "occupancy",
    "vdw": "radius",
    "index": "i",
    "formal_charge": "charge",
    "partial_charge": "charge",
    "mass": "mass",
}

#: Names that exist in the namespace but are computed, not stored, so writing to
#: them cannot be persisted. ``alter`` reports an attempt rather than dropping it.
DERIVED_PROPERTIES: frozenset[str] = frozenset(
    {"oneletter", "x", "y", "z", "rank"}
)

#: What a label expression is allowed to call. No builtins, no imports.
_SAFE_BUILTINS: dict[str, object] = {
    "abs": abs,
    "float": float,
    "int": int,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "str": str,
    "format": format,
}

#: Three-letter to one-letter, for PyMOL's ``oneletter``.
_ONE_LETTER = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "SEC": "U", "PYL": "O", "MSE": "M",
    "DA": "A", "DC": "C", "DG": "G", "DT": "T", "DU": "U",
    "A": "A", "C": "C", "G": "G", "U": "U", "T": "T",
}


def label_expression(kind: str) -> str:
    """Return the expression behind one of PyMOL's Label-menu entries.

    Parameters
    ----------
    kind : str
        Menu entry name, e.g. ``"residues"`` or ``"b-factor"``.

    Returns
    -------
    str
        A label expression, or ``""`` for "clear".

    Raises
    ------
    KeyError
        If the entry is not one PyMOL offers.
    """
    return _MENU_EXPRESSIONS[kind]


#: Verbatim from ``pymol/menu.py:mol_labels``, so the menu and the command
#: language cannot drift apart.
_MENU_EXPRESSIONS: dict[str, str] = {
    "clear": "",
    "residues": '"%s-%s" % (resn, resi)',
    "residues (oneletter)": "oneletter + resi",
    "chains": "chain",
    "segments": "segi",
    "atom name": "name",
    "element symbol": "elem",
    "residue name": "resn",
    "one letter code": "oneletter",
    "residue identifier": "resi",
    "chain identifier": "chain",
    "segment identifier": "segi",
    "b-factor": "'%1.2f' % b",
    "occupancy": "'%1.2f' % q",
    "vdw radius": "'%1.2f' % vdw",
}


def atom_namespace(
    atoms: np.ndarray, index: int, coords: np.ndarray | None = None
) -> dict:
    """Build the PyMOL property namespace for one atom.

    Shared by ``label``, ``iterate`` and ``alter`` so the three cannot disagree
    about what ``b`` or ``chain`` means.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array.
    index : int
        Atom to describe.
    coords : numpy.ndarray, optional
        ``(N, 3)`` positions supplying ``x``/``y``/``z``.

    Returns
    -------
    dict
        PyMOL's property names bound to this atom's values.
    """
    return _properties_for(atoms, index, coords)


def _properties_for(atoms: np.ndarray, index: int, coords: np.ndarray) -> dict:
    """Build the namespace one atom's label expression is evaluated in."""
    names = atoms.dtype.names or ()
    scope: dict[str, object] = {}

    for pymol_name, field in ATOM_PROPERTIES.items():
        if field in names:
            value = atoms[field][index]
            if isinstance(value, (np.integer,)):
                value = int(value)
            elif isinstance(value, (np.floating,)):
                value = float(value)
            else:
                value = str(value).strip()
            scope[pymol_name] = value
        else:
            # Absent fields must still resolve, or every expression mentioning
            # one fails on a structure that happens not to carry it.
            scope[pymol_name] = "" if pymol_name not in ("b", "q", "vdw") else 0.0

    # PyMOL gives resi as a *string*, since insertion codes exist.
    if "resi" in scope:
        scope["resi"] = str(scope["resi"])
    scope["resv"] = scope.get("resi", "")

    res_name = str(scope.get("resn", "")).upper()
    scope["oneletter"] = _ONE_LETTER.get(res_name, "X")

    if coords is not None and index < coords.shape[0]:
        scope["x"] = float(coords[index, 0])
        scope["y"] = float(coords[index, 1])
        scope["z"] = float(coords[index, 2])
    return scope


def evaluate_labels(
    atoms: np.ndarray,
    coords: np.ndarray,
    expression: str,
    mask: np.ndarray | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Evaluate a PyMOL label expression over the selected atoms.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array.
    coords : numpy.ndarray
        ``(N, 3)`` positions, used for ``x``/``y``/``z`` and returned for the
        labelled atoms.
    expression : str
        Python expression in PyMOL's property namespace. An empty expression
        clears, matching ``cmd.label(sel, "")``.
    mask : numpy.ndarray, optional
        Boolean selection.

    Returns
    -------
    tuple
        ``(indices, texts)`` — the atom indices that got a label and the text for
        each. An atom whose expression fails is skipped rather than aborting the
        whole command, since one odd residue should not cost the other thousand
        their labels.

    Raises
    ------
    SyntaxError
        If the expression does not parse at all; that is worth reporting, since
        it is wrong for every atom rather than one.
    """
    expr = (expression or "").strip()
    if not expr:
        return np.zeros(0, dtype=int), []

    code = compile(expr, "<label>", "eval")
    keep = (
        np.ones(len(atoms), dtype=bool) if mask is None
        else np.asarray(mask, dtype=bool)
    )

    indices: list[int] = []
    texts: list[str] = []
    for i in np.nonzero(keep)[0]:
        scope = _properties_for(atoms, int(i), coords)
        try:
            value = eval(code, {"__builtins__": _SAFE_BUILTINS}, scope)
        except Exception:
            continue
        indices.append(int(i))
        texts.append("" if value is None else str(value))
    return np.asarray(indices, dtype=int), texts
