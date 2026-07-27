"""Canonical atom order, for PyMOL's ``sort``.

``AtomInfoCompare`` in ``layer2/AtomInfo.cpp`` orders atoms by
``segi -> chain -> hetatm -> res_id -> inscode -> res_name -> priority -> name``.
The interesting field is **priority**, assigned by name in
``AtomInfoAssignParameters``, and it is transcribed here rather than reinvented.

Two things about it are counter-intuitive and both were got wrong by guessing
first:

* **priority depends only on the Greek letter, not on the branch number.** ``CG2``
  and ``OG1`` both score 5, and their order is then settled by comparing the
  *names* -- so ``CG2`` comes first, which is what deposited files actually
  contain. Folding the branch digit into the priority instead put ``OG1`` first
  and disagreed with every real structure checked;
* **a one-character ``C`` or ``O`` sorts near the end** (997, 998), not fourth.
  PyMOL's canonical order within a residue is therefore
  ``N, CA, CB, CG, ..., C, O, OXT`` -- side chain *before* the carbonyl, which is
  not the order a PDB file is written in. Matching PyMOL means matching this.

Hydrogens live in a parallel 1000-series so they follow every heavy atom, and
``OXT``/``HXT`` get 999/1999 so a terminal atom is last.
"""

from __future__ import annotations

import numpy as np

__all__ = ["GREEK_PRIORITY", "HYDROGEN_PRIORITY", "atom_priority", "sort_order"]

#: Second character of a heavy-atom name -> priority. Straight from the
#: ``switch (*(n + 1))`` in AtomInfoAssignParameters.
GREEK_PRIORITY = {
    "A": 3, "B": 4, "G": 5, "D": 6, "E": 7, "Z": 8, "H": 9,
    "I": 10, "J": 11, "K": 12, "L": 13, "M": 14, "N": 15,
}

#: The same for a hydrogen or deuterium, offset into the 1000-series so every
#: hydrogen follows every heavy atom.
HYDROGEN_PRIORITY = {
    "A": 1003, "B": 1003, "G": 1004, "D": 1005, "E": 1006, "Z": 1007,
    "H": 1008, "I": 1009, "J": 1010, "K": 1011, "L": 1012, "M": 1013,
    "N": 1002,
}

#: One-character names. ``C`` and ``O`` deliberately sort after the side chain.
_SINGLE_CHAR = {"N": 1, "C": 997, "O": 998}


def atom_priority(name: str) -> int:
    """PyMOL's per-name sort priority.

    Parameters
    ----------
    name : str
        Atom name, stripped of padding.

    Returns
    -------
    int
        Lower sorts earlier.
    """
    text = str(name).strip()
    if not text:
        return 1000
    first = text[0].upper()
    second = text[1].upper() if len(text) > 1 else ""

    # Hydrogen and deuterium: the 1000-series.
    if first in ("D", "H"):
        if not second:
            return 1001
        if second == "X":
            return 1999
        if second.isdigit():
            # `pri = 1020` then the digits appended, then +25.
            return _digit_priority(text[1:], base=1020)
        return HYDROGEN_PRIORITY.get(second, 1500)

    # Phosphate first, so it precedes the numbered C/N/O atoms of a nucleotide.
    if first == "P":
        return 20

    if first in ("N", "C", "O", "S"):
        if not second:
            return _SINGLE_CHAR.get(first, 1000)
        if second == "X":
            # OXT and friends: the terminal atom goes last.
            return 999 if len(text) > 2 and text[2].upper() == "T" else 16
        if second.isdigit():
            return _digit_priority(text[1:], base=0)
        return GREEK_PRIORITY.get(second, 500)

    return 1000


def _digit_priority(digits: str, *, base: int) -> int:
    """The numeric branch: accumulate the digits, then add 25.

    Transcribed literally -- ``pri = base``, then ``pri = pri * 10 + digit`` for
    each character, then ``pri += 25``. The accumulation runs over the whole
    remainder of the name, so ``C12`` and ``C1`` are ordered by value rather than
    by string.
    """
    priority = base
    for character in digits:
        if not character.isdigit():
            break
        priority = priority * 10 + int(character)
    return priority + 25


def sort_order(atoms: np.ndarray) -> np.ndarray:
    """Indices that put ``atoms`` in PyMOL's canonical order.

    The key follows ``AtomInfoCompare``'s field order: chain, then residue
    number, then residue name, then priority, then the atom name as a plain
    string comparison -- which is what settles the ties priority leaves.

    Returns
    -------
    numpy.ndarray
        An index array; ``atoms[sort_order(atoms)]`` is sorted. Stable, so atoms
        the key cannot distinguish keep their relative order: a reorder that is
        not a no-op invalidates every per-atom array and every bond index, so it
        should happen only where the key genuinely asks for it.
    """
    names = atoms.dtype.names or ()
    if "atom_name" not in names:
        return np.arange(len(atoms), dtype=int)

    def column(key, default=""):
        if key not in names:
            return np.array([default] * len(atoms))
        return np.char.strip(np.asarray(atoms[key]).astype(str))

    chains = column("chain")
    res_names = column("res_name")
    atom_names = column("atom_name")
    res_ids = (
        np.asarray(atoms["res_id"], dtype=int) if "res_id" in names
        else np.zeros(len(atoms), dtype=int)
    )
    priorities = np.array([atom_priority(n) for n in atom_names], dtype=int)

    keys = list(zip(
        chains.tolist(),
        res_ids.tolist(),
        res_names.tolist(),
        priorities.tolist(),
        atom_names.tolist(),
    ))
    return np.array(sorted(range(len(atoms)), key=lambda i: keys[i]), dtype=int)


#: Every state field indexed by atom on its **first** axis, and therefore
#: invalidated by a reorder.
#:
#: Written out rather than detected by shape, because a shape test cannot tell an
#: atom-length array from a residue-length one that happens to match, and being
#: wrong here silently scrambles colours or masks against coordinates. A
#: guardrail test walks the state dataclass and fails if a new array field
#: appears that is neither listed here nor listed as exempt -- so the list cannot
#: quietly fall behind.
ATOM_INDEXED_FIELDS = (
    "atoms",
    "all_atom_coords",
    "colors_per_atom_override",
    "ball_mask",
    "sticks_mask",
    "protected_mask",
    "masked_mask",
    "hidden_mask",
)

#: Array fields that are *not* atom-indexed, listed so the guardrail can tell
#: "known to be safe" from "nobody has looked at this yet".
NON_ATOM_INDEXED_FIELDS = (
    "coords",                     # per residue (the CA trace)
    "colors_per_residue_override",
    "colors_per_ca",
    "cartoon_mask",               # per residue
    "residue_ids",
    "residue_names",
    "residue_chain_ids",
    "center",
    "bond_pairs",                 # holds indices; remapped, not permuted
    "frames",                     # (T, N, 3): atom axis is the *second*
    "frames_raw",
    "all_atom_radii",             # atom-indexed but rebuilt from `atoms`
    "all_atom_res_ids",
    "bead_radii",
    "secondary_structure",
    "ss_codes",
    "raw_center",                 # a single 3-vector
    "residue_oneletter",          # per residue
    "trace_ups",                  # per trace point, i.e. per residue
    # Per residue in *shape*, but its values are atom indices -- so neither
    # permuting nor subsetting it is right, and leaving it alone is wrong too:
    # the indices would point at whatever atom now sits at that slot. It is a
    # cache of pure topology, so both operations discard it below and the next
    # rebuild recomputes it.
    "backbone_map",
)


def _drop_backbone_map(state) -> None:
    """Discard the cached N/C/O lookup: its values are atom indices.

    Called from both the permute and the subset path. Recomputing it costs a
    fraction of a millisecond, and a stale one silently orients every ribbon
    from the wrong atoms.
    """
    if getattr(state, "backbone_map", None) is not None:
        state.backbone_map = None


def permute_atom_state(state, order: np.ndarray) -> dict[str, int]:
    """Apply an atom reordering to every array that is indexed by atom.

    Parameters
    ----------
    state : _MolViewObjectState
        The object state to reorder in place.
    order : numpy.ndarray
        Index array from :func:`sort_order`.

    Returns
    -------
    dict
        ``{"fields": n, "bonds": n}`` -- how many arrays were permuted and how
        many bond indices were remapped.
    """
    order = np.asarray(order, dtype=int)
    n_atoms = order.shape[0]
    moved = 0
    _drop_backbone_map(state)
    for field_name in ATOM_INDEXED_FIELDS:
        value = getattr(state, field_name, None)
        if value is None:
            continue
        array = np.asarray(value)
        if array.shape[0] != n_atoms:
            continue
        setattr(state, field_name, array[order])
        moved += 1

    # Bonds hold *indices*, so they are remapped rather than permuted: an atom
    # that moved from position i to position j must have every bond referring to
    # it updated. Getting this wrong reconnects the molecule at random, which is
    # obvious in a picture and silent in the data.
    #
    # Worth knowing: remapping `bond_pairs` is belt-and-braces for a caller that
    # uses this function directly. The `sort` command rebuilds afterwards, which
    # re-infers bonds from the coordinates and overwrites whatever is set here --
    # so a mutation test that breaks *this* line passes, while one that breaks the
    # `bond_edits` remap below fails. The edits are the part that must be right,
    # because they are replayed on top of each fresh inference.
    inverse = np.empty(n_atoms, dtype=int)
    inverse[order] = np.arange(n_atoms)

    remapped = 0
    pairs = getattr(state, "bond_pairs", None)
    if pairs is not None:
        arr = np.asarray(pairs, dtype=int)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            state.bond_pairs = inverse[arr[:, :2]]
            remapped = int(arr.shape[0])

    edits = getattr(state, "bond_edits", None)
    if isinstance(edits, dict):
        def remap(key):
            a, b = int(key[0]), int(key[1])
            new = (int(inverse[a]), int(inverse[b]))
            return new if new[0] <= new[1] else (new[1], new[0])

        added = edits.get("added") or {}
        removed = edits.get("removed") or set()
        edits["added"] = {remap(k): v for k, v in added.items()}
        edits["removed"] = {remap(k) for k in removed}

    # Frames carry the atom axis second.
    for field_name in ("frames", "frames_raw"):
        value = getattr(state, field_name, None)
        if value is None:
            continue
        array = np.asarray(value)
        if array.ndim == 3 and array.shape[1] == n_atoms:
            setattr(state, field_name, array[:, order, :])
            moved += 1

    return {"fields": moved, "bonds": remapped}


def subset_atom_state(state, keep: np.ndarray) -> dict[str, int]:
    """Apply an atom *removal* to every array that is indexed by atom.

    The mirror of :func:`permute_atom_state`, and needed for the same reason:
    deleting atoms invalidates every per-atom array and every bond index. Without
    it ``remove solvent`` left a per-atom colour array of the **old** length --
    silently mis-colouring what remained -- and a representation mask that no
    longer lined up with the atoms, so a sphere stayed on screen where a deleted
    water had been.

    Parameters
    ----------
    state : _MolViewObjectState
        The object state to trim in place.
    keep : numpy.ndarray
        Boolean over the *old* atoms; True for the ones that survive.

    Returns
    -------
    dict
        ``{"fields": n, "bonds": n}`` -- arrays trimmed, bonds kept.
    """
    _drop_backbone_map(state)
    keep = np.asarray(keep, dtype=bool)
    n_old = keep.shape[0]
    moved = 0
    for field_name in ATOM_INDEXED_FIELDS:
        value = getattr(state, field_name, None)
        if value is None:
            continue
        array = np.asarray(value)
        if array.shape[0] != n_old:
            continue
        setattr(state, field_name, array[keep])
        moved += 1

    # Old index -> new index, or -1 for a removed atom.
    remap = np.full(n_old, -1, dtype=int)
    remap[keep] = np.arange(int(keep.sum()))

    kept_bonds = 0
    pairs = getattr(state, "bond_pairs", None)
    if pairs is not None:
        arr = np.asarray(pairs, dtype=int)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            survives = (remap[arr[:, 0]] >= 0) & (remap[arr[:, 1]] >= 0)
            state.bond_pairs = remap[arr[survives][:, :2]]
            kept_bonds = int(survives.sum())

    edits = getattr(state, "bond_edits", None)
    if isinstance(edits, dict):
        def survives(key):
            a, b = int(key[0]), int(key[1])
            return 0 <= a < n_old and 0 <= b < n_old and remap[a] >= 0 and remap[b] >= 0

        def moved_key(key):
            a, b = int(remap[int(key[0])]), int(remap[int(key[1])])
            return (a, b) if a <= b else (b, a)

        added = edits.get("added") or {}
        removed = edits.get("removed") or set()
        edits["added"] = {
            moved_key(k): v for k, v in added.items() if survives(k)
        }
        edits["removed"] = {moved_key(k) for k in removed if survives(k)}

    for field_name in ("frames", "frames_raw"):
        value = getattr(state, field_name, None)
        if value is None:
            continue
        array = np.asarray(value)
        if array.ndim == 3 and array.shape[1] == n_old:
            setattr(state, field_name, array[:, keep, :])
            moved += 1

    # A representation is a mask *and* a flag, and removing the last atom a mask
    # selected has to clear the flag too. Otherwise `show spheres, solvent`
    # followed by `remove solvent` leaves the flag set over an empty mask, and
    # the builder falls back to its default -- drawing points along the chain
    # that nobody asked for.
    for mask_name, flag_name in (
        ("ball_mask", "show_atoms"),
        ("sticks_mask", "show_sticks"),
    ):
        mask = getattr(state, mask_name, None)
        if mask is not None and not np.asarray(mask, dtype=bool).any():
            setattr(state, flag_name, False)

    return {"fields": moved, "bonds": kept_bonds}
