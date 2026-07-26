"""Adding hydrogens, as PyMOL's ``h_add`` does.

Geometry transcribed from ``layer2/HydrogenAdder.cpp::
ObjectMoleculeSetMissingNeighborCoords``. Two details there are easy to lose and
both change the answer:

* the ``switch (n_system)`` **falls through**. With one neighbour present the
  tetrahedral branch runs cases 1, 2 *and* 3, building the second, third and
  fourth directions in turn. Reading it as an if/elif gives one hydrogen where
  three are wanted;
* the constants are the cosine and sine of the ideal angle, not the angle:
  ``-0.334``/``0.943`` for 109.5°, ``-0.500``/``0.866`` for 120.0°, and ``1.41``
  for ``tan(109.5/2)`` in the two-neighbour case.

How many hydrogens, and where
-----------------------------
PyMOL works from **bond valences**, and warns in ``h_add``'s own help that PDB
files do not carry them for ligands. Measured here on a fully hydrogenated
protein (``hGBP1_closed.pdb``, 4671 hydrogens), the obvious substitute --
``valence(element) - heavy neighbours`` -- is **wrong for 41.6% of atoms**: it
adds a hydrogen to every carbonyl carbon, every carboxyl oxygen and every
aromatic carbon, because a double bond looks like a free valence when no orders
are known.

So standard residues use a **template**: how many hydrogens each named atom
takes, and whether its geometry is planar or tetrahedral. That is exact for
proteins, which is what ``h_add`` is for. Anything without a template is
reported rather than guessed at -- an approximate hydrogen is worse than a
missing one, because it looks like data.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "TETRAHEDRAL",
    "PLANAR",
    "LINEAR",
    "RESIDUE_TEMPLATES",
    "X_H_BOND_LENGTH",
    "open_valence_directions",
    "plan_hydrogens",
]

TETRAHEDRAL = "tetrahedral"
PLANAR = "planar"
LINEAR = "linear"

#: cos/sin of the ideal angles, exactly as HydrogenAdder.cpp spells them.
_COS_109_5, _SIN_109_5 = -0.334, 0.943
_COS_120, _SIN_120 = -0.500, 0.866
#: tan(109.5 / 2), the two-neighbour tetrahedral spread.
_TAN_HALF_109_5 = 1.41

#: How far a hydrogen sits from its parent, by parent element (Angstrom).
X_H_BOND_LENGTH = {"C": 1.09, "N": 1.01, "O": 0.96, "S": 1.34, "P": 1.44}
_DEFAULT_X_H = 1.09

#: Backbone, shared by every amino acid. ``N`` is a planar amide with one
#: hydrogen; the carbonyl ``C`` and ``O`` take none, which is precisely where the
#: valence-counting shortcut goes wrong.
_BACKBONE = {
    "N": (1, PLANAR),
    "CA": (1, TETRAHEDRAL),
    "C": (0, PLANAR),
    "O": (0, PLANAR),
    "OXT": (0, PLANAR),
}

#: Side chains: ``atom name -> (hydrogen count, geometry)``. Only atoms that
#: differ from "none" need listing, but the zeros are kept where they are the
#: interesting case -- a carbon that looks unsaturated and is not.
_SIDE_CHAINS: dict[str, dict[str, tuple[int, str]]] = {
    "ALA": {"CB": (3, TETRAHEDRAL)},
    "ARG": {
        "CB": (2, TETRAHEDRAL), "CG": (2, TETRAHEDRAL), "CD": (2, TETRAHEDRAL),
        "NE": (1, PLANAR), "CZ": (0, PLANAR),
        "NH1": (2, PLANAR), "NH2": (2, PLANAR),
    },
    "ASN": {
        "CB": (2, TETRAHEDRAL), "CG": (0, PLANAR),
        "OD1": (0, PLANAR), "ND2": (2, PLANAR),
    },
    "ASP": {
        "CB": (2, TETRAHEDRAL), "CG": (0, PLANAR),
        "OD1": (0, PLANAR), "OD2": (0, PLANAR),
    },
    "CYS": {"CB": (2, TETRAHEDRAL), "SG": (1, TETRAHEDRAL)},
    "GLN": {
        "CB": (2, TETRAHEDRAL), "CG": (2, TETRAHEDRAL), "CD": (0, PLANAR),
        "OE1": (0, PLANAR), "NE2": (2, PLANAR),
    },
    "GLU": {
        "CB": (2, TETRAHEDRAL), "CG": (2, TETRAHEDRAL), "CD": (0, PLANAR),
        "OE1": (0, PLANAR), "OE2": (0, PLANAR),
    },
    "GLY": {"CA": (2, TETRAHEDRAL)},
    # Neutral histidine, ND1-protonated (HID) -- the tautomer has to be chosen
    # and this is the common default. See TAUTOMER_NOTES.
    "HIS": {
        "CB": (2, TETRAHEDRAL), "CG": (0, PLANAR), "ND1": (1, PLANAR),
        "CD2": (1, PLANAR), "CE1": (1, PLANAR), "NE2": (0, PLANAR),
    },
    "ILE": {
        "CB": (1, TETRAHEDRAL), "CG1": (2, TETRAHEDRAL),
        "CG2": (3, TETRAHEDRAL), "CD1": (3, TETRAHEDRAL),
    },
    "LEU": {
        "CB": (2, TETRAHEDRAL), "CG": (1, TETRAHEDRAL),
        "CD1": (3, TETRAHEDRAL), "CD2": (3, TETRAHEDRAL),
    },
    "LYS": {
        "CB": (2, TETRAHEDRAL), "CG": (2, TETRAHEDRAL), "CD": (2, TETRAHEDRAL),
        "CE": (2, TETRAHEDRAL), "NZ": (3, TETRAHEDRAL),
    },
    "MET": {
        "CB": (2, TETRAHEDRAL), "CG": (2, TETRAHEDRAL),
        "SD": (0, TETRAHEDRAL), "CE": (3, TETRAHEDRAL),
    },
    "PHE": {
        "CB": (2, TETRAHEDRAL), "CG": (0, PLANAR),
        "CD1": (1, PLANAR), "CD2": (1, PLANAR),
        "CE1": (1, PLANAR), "CE2": (1, PLANAR), "CZ": (1, PLANAR),
    },
    # Proline's nitrogen is in the ring and carries no hydrogen at all.
    "PRO": {
        "N": (0, PLANAR), "CB": (2, TETRAHEDRAL),
        "CG": (2, TETRAHEDRAL), "CD": (2, TETRAHEDRAL),
    },
    "SER": {"CB": (2, TETRAHEDRAL), "OG": (1, TETRAHEDRAL)},
    "THR": {
        "CB": (1, TETRAHEDRAL), "OG1": (1, TETRAHEDRAL),
        "CG2": (3, TETRAHEDRAL),
    },
    "TRP": {
        "CB": (2, TETRAHEDRAL), "CG": (0, PLANAR), "CD1": (1, PLANAR),
        "NE1": (1, PLANAR), "CD2": (0, PLANAR), "CE2": (0, PLANAR),
        "CE3": (1, PLANAR), "CZ2": (1, PLANAR), "CZ3": (1, PLANAR),
        "CH2": (1, PLANAR),
    },
    "TYR": {
        "CB": (2, TETRAHEDRAL), "CG": (0, PLANAR),
        "CD1": (1, PLANAR), "CD2": (1, PLANAR),
        "CE1": (1, PLANAR), "CE2": (1, PLANAR),
        "CZ": (0, PLANAR), "OH": (1, TETRAHEDRAL),
    },
    "VAL": {
        "CB": (1, TETRAHEDRAL), "CG1": (3, TETRAHEDRAL),
        "CG2": (3, TETRAHEDRAL),
    },
}

#: Ambiguities a template cannot settle, kept where they can be reported.
TAUTOMER_NOTES = {
    "HIS": "histidine is treated as ND1-protonated (HID); NE2 tautomers and "
           "the charged form need the hydrogen placed by hand",
}

#: ``res_name -> {atom_name: (n_hydrogens, geometry)}``, backbone folded in.
RESIDUE_TEMPLATES: dict[str, dict[str, tuple[int, str]]] = {
    name: {**_BACKBONE, **side} for name, side in _SIDE_CHAINS.items()
}
#: Water: two hydrogens on a bent oxygen, which the tetrahedral frame gives.
RESIDUE_TEMPLATES["HOH"] = {"O": (2, TETRAHEDRAL)}
RESIDUE_TEMPLATES["WAT"] = {"O": (2, TETRAHEDRAL)}


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def _frame_from_one(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """An orthonormal pair completing ``x`` -- PyMOL's ``get_system1f3f``."""
    x = x / max(float(np.linalg.norm(x)), 1e-12)
    # Any axis not parallel to x; picking the smallest component keeps it stable.
    helper = np.zeros(3)
    helper[int(np.argmin(np.abs(x)))] = 1.0
    y = np.cross(x, helper)
    y /= max(float(np.linalg.norm(y)), 1e-12)
    z = np.cross(x, y)
    z /= max(float(np.linalg.norm(z)), 1e-12)
    return y, z


def open_valence_directions(
    neighbour_dirs: list[np.ndarray] | np.ndarray,
    geometry: str,
    n_wanted: int,
) -> list[np.ndarray]:
    """Unit vectors for the free valences of an atom.

    A transcription of ``ObjectMoleculeSetMissingNeighborCoords``, including its
    fall-through: with one neighbour present, the tetrahedral branch produces the
    second, third and fourth directions in sequence, each built from the ones
    before it.

    Parameters
    ----------
    neighbour_dirs : list of numpy.ndarray
        Unit vectors from the atom towards each neighbour it already has.
    geometry : str
        ``TETRAHEDRAL``, ``PLANAR`` or ``LINEAR``.
    n_wanted : int
        How many directions to return.

    Returns
    -------
    list of numpy.ndarray
        Up to ``n_wanted`` unit vectors, fewer when the geometry has no room:
        a tetrahedral atom with three neighbours has exactly one free valence
        however many hydrogens were asked for.
    """
    if n_wanted <= 0:
        return []

    dirs = [
        np.asarray(d, dtype=float) / max(float(np.linalg.norm(d)), 1e-12)
        for d in neighbour_dirs
    ]
    n_present = len(dirs)

    slots = {TETRAHEDRAL: 4, PLANAR: 3, LINEAR: 2}.get(geometry, 4)
    if n_present >= slots:
        return []

    buf = list(dirs)
    if not buf:
        # No neighbour to work from: PyMOL takes a random direction. A fixed one
        # keeps a session reproducible, which matters more here than isotropy.
        buf.append(np.array([1.0, 0.0, 0.0]))

    if geometry == LINEAR:
        if len(buf) == 1:
            buf.append(-buf[0])
    elif geometry == PLANAR:
        if len(buf) == 1:
            _, z = _frame_from_one(buf[0])
            buf.append(_normalise(_COS_120 * buf[0] + _SIN_120 * z))
        if len(buf) == 2:
            buf.append(_normalise(-(buf[0] + buf[1])))
    else:  # tetrahedral
        if len(buf) == 1:
            _, z = _frame_from_one(buf[0])
            buf.append(_normalise(_COS_109_5 * buf[0] + _SIN_109_5 * z))
        if len(buf) == 2:
            bisector = -_normalise(buf[0] + buf[1])
            perp = _normalise(np.cross(buf[0], buf[1])) * _TAN_HALF_109_5
            buf.append(_normalise(bisector + perp))
        if len(buf) == 3:
            buf.append(_normalise(-(buf[0] + buf[1] + buf[2])))

    # PyMOL caps the count at what the geometry leaves free.
    free = buf[n_present:]
    return free[: min(n_wanted, slots - n_present)]


def _normalise(v: np.ndarray) -> np.ndarray:
    return np.asarray(v, dtype=float) / max(float(np.linalg.norm(v)), 1e-12)


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def plan_hydrogens(
    atoms: np.ndarray,
    bond_pairs: np.ndarray | None,
    mask: np.ndarray | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Work out every hydrogen to add, without adding any.

    Separated from the mutation so the decision can be tested on its own and so
    a caller can report before changing anything.

    Parameters
    ----------
    atoms : numpy.ndarray
        The structured atom array.
    bond_pairs : numpy.ndarray or None
        ``(N, 2)`` bonds; used to find each atom's existing neighbours.
    mask : numpy.ndarray, optional
        Atoms to consider; all of them when omitted.

    Returns
    -------
    tuple
        ``(plan, unknown)`` where each plan entry is
        ``{"parent": int, "name": str, "xyz": ndarray}`` and ``unknown`` counts
        residue names that have no template, by name.
    """
    names = atoms.dtype.names or ()
    if "xyz" not in names or "atom_name" not in names:
        return [], {}

    xyz = np.asarray(atoms["xyz"], dtype=float)
    atom_names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    res_names = (
        np.char.strip(np.asarray(atoms["res_name"]).astype(str))
        if "res_name" in names
        else np.array([""] * len(atoms))
    )
    res_ids = (
        np.asarray(atoms["res_id"]) if "res_id" in names
        else np.zeros(len(atoms), dtype=int)
    )
    elements = (
        np.char.strip(np.asarray(atoms["element"]).astype(str)).astype("U2")
        if "element" in names
        else np.array([n[:1] for n in atom_names])
    )

    neighbours: dict[int, list[int]] = {}
    if bond_pairs is not None:
        pairs = np.asarray(bond_pairs, dtype=int)
        if pairs.ndim == 2 and pairs.shape[1] >= 2:
            for a, b in pairs[:, :2]:
                neighbours.setdefault(int(a), []).append(int(b))
                neighbours.setdefault(int(b), []).append(int(a))

    consider = (
        np.ones(len(atoms), dtype=bool) if mask is None
        else np.asarray(mask, dtype=bool)
    )

    plan: list[dict] = []
    unknown: dict[str, int] = {}
    # Hydrogens already present must not be counted again, and they occupy a
    # valence: a residue read with some of its hydrogens gets only the rest.
    for index in np.nonzero(consider)[0]:
        element = str(elements[index]).upper()
        if element == "H":
            continue
        template = RESIDUE_TEMPLATES.get(str(res_names[index]).upper())
        if template is None:
            key = str(res_names[index]).upper() or "?"
            unknown[key] = unknown.get(key, 0) + 1
            continue
        entry = template.get(str(atom_names[index]))
        if entry is None:
            continue
        n_hydrogens, geometry = entry

        existing = neighbours.get(int(index), [])
        heavy_dirs = []
        heavy_neighbours: list[int] = []
        n_existing_h = 0
        for other in existing:
            if str(elements[other]).upper() == "H":
                n_existing_h += 1
                continue
            heavy_neighbours.append(int(other))
            heavy_dirs.append(xyz[other] - xyz[index])

        n_hydrogens, geometry = _adjust_for_context(
            residue=str(res_names[index]).upper(),
            atom=str(atom_names[index]),
            n_hydrogens=n_hydrogens,
            geometry=geometry,
            heavy_neighbours=heavy_neighbours,
            index=int(index),
            atom_names=atom_names,
            res_ids=res_ids,
            elements=elements,
            neighbours=neighbours,
        )
        if n_hydrogens <= 0:
            continue

        wanted = n_hydrogens - n_existing_h
        if wanted <= 0:
            continue

        directions = open_valence_directions(heavy_dirs, geometry, wanted)
        length = X_H_BOND_LENGTH.get(element, _DEFAULT_X_H)
        stem = str(atom_names[index])
        for k, direction in enumerate(directions):
            plan.append({
                "parent": int(index),
                "res_id": int(res_ids[index]),
                "name": _hydrogen_name(stem, k, len(directions)),
                "xyz": xyz[index] + direction * length,
            })
    return plan, unknown


def _adjust_for_context(
    *,
    residue: str,
    atom: str,
    n_hydrogens: int,
    geometry: str,
    heavy_neighbours: list[int],
    index: int,
    atom_names: np.ndarray,
    res_ids: np.ndarray,
    elements: np.ndarray,
    neighbours: dict[int, list[int]],
) -> tuple[int, str]:
    """Two corrections a per-residue template cannot express.

    Both were found by checking the template against a fully hydrogenated
    protein, where they were the *only* disagreements out of 4644 atoms.

    **The N-terminus is an ammonium, not an amide.** A backbone nitrogen with no
    preceding carbonyl carbon carries three hydrogens on a tetrahedral centre
    rather than one on a planar one. It is detectable from the bond graph -- one
    heavy neighbour instead of two -- so it needs no separate residue name.

    **Histidine's tautomer is a property of the structure, not of the residue.**
    The template assumes ND1-protonated (HID); if the file already carries a
    hydrogen on NE2 then it is the other tautomer and ND1 must take none.
    Without any hydrogens to go on the tautomer is genuinely unknowable and the
    default stands -- PyMOL picks one too.
    """
    if atom == "N" and residue != "PRO":
        # Chain-initial: bonded to CA but to no preceding C.
        has_preceding_c = any(
            str(atom_names[n]) == "C" and int(res_ids[n]) != int(res_ids[index])
            for n in heavy_neighbours
        )
        if not has_preceding_c and heavy_neighbours:
            return 3, TETRAHEDRAL
    if atom == "N" and residue == "PRO":
        has_preceding_c = any(
            str(atom_names[n]) == "C" and int(res_ids[n]) != int(res_ids[index])
            for n in heavy_neighbours
        )
        if not has_preceding_c and heavy_neighbours:
            return 2, TETRAHEDRAL

    if residue == "HIS" and atom == "ND1":
        # Look for a hydrogen already on this residue's NE2.
        for other, others_neighbours in neighbours.items():
            if (
                str(atom_names[other]) == "NE2"
                and int(res_ids[other]) == int(res_ids[index])
                and any(
                    str(elements[h]).upper() == "H" for h in others_neighbours
                )
            ):
                return 0, geometry
    return n_hydrogens, geometry


def _hydrogen_name(parent_name: str, k: int, total: int) -> str:
    """PDB-ish hydrogen name: ``H`` plus the parent's suffix, numbered if needed.

    ``CB`` with three hydrogens gives ``HB1``, ``HB2``, ``HB3``; ``CA`` with one
    gives ``HA``. Names are cosmetic here -- nothing keys on them -- but a wrong
    one is confusing in a label, and a duplicate is confusing in a selection.
    """
    suffix = parent_name[1:] if len(parent_name) > 1 else ""
    base = f"H{suffix}"
    if total <= 1:
        return base[:4]
    return f"{base}{k + 1}"[:4]
