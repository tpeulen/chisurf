"""Classifying atoms the way PyMOL's selector does.

``polymer``, ``organic``, ``solvent``, ``inorganic``, ``backbone``, ``sidechain``,
``guide`` and ``metals`` are not residue-name lookups in PyMOL — they are derived
per residue from *which atoms are present*, in ``SelectorClassifyAtoms``
(``layer3/Selector.cpp``). That distinction matters: a modified residue, a
non-standard ligand or a nucleic acid with unusual naming lands in the right class
without anyone maintaining a table of names, and a residue named ``ALA`` that is
missing its backbone does not pretend to be polymer.

The rule, transcribed from that function::

    CA and N and C and O, plus a peptide bond   -> polymer | protein
    O3' C3' C4' C5' O5', plus an O3/P bond      -> polymer | nucleic
    else any carbon                             -> organic
    else (O or OH2) and a single-atom residue   -> solvent
    else not all hydrogens                      -> inorganic

**One documented deviation.** PyMOL additionally requires a peptide (C-N) or
phosphodiester bond before calling a residue polymer, which needs connectivity
chimol does not carry at this level. Atom-name presence alone is used, so an
isolated free amino acid classifies as protein where PyMOL would call it organic.
The consequence is confined to single-residue objects.

Guide atoms follow the same function: ``CA`` for protein, ``C4'`` for nucleic with
``C3'`` as the fallback for backbones lacking it.

``metals`` is by atomic number, exactly as ``AtomInfoType::isMetal`` in
``layer2/AtomInfo.h`` defines it — not a symbol list.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "AtomClasses",
    "ATOMIC_NUMBER",
    "BACKBONE_NAMES",
    "classify_atoms",
    "is_metal",
    "residue_runs",
]

#: ``backbone_names[]`` from ``layer3/Selector.cpp``, verbatim and in its order.
BACKBONE_NAMES: tuple[str, ...] = (
    # protein
    "CA", "C", "O", "N", "OXT", "H",
    # nucleic acid
    "P", "OP1", "OP2", "OP3", "C1'", "C2'", "O2'",
    "C3'", "O3'", "C4'", "O4'", "C5'", "O5'",
    "H1'", "H3'", "H4'",
    "H2'", "H2''", "H12'", "H22'",
    "H5'", "H5''", "H15'", "H25'",
    "HO2'", "HO3'", "HO5'",
)

#: Atomic numbers by element symbol, upper-cased. Enough of the table to decide
#: :func:`is_metal`, which is defined by proton count rather than by symbol, and
#: to tell an element symbol from an atom-name prefix when a PDB record carries
#: no element column (see ``io.structure._element_symbol_from_pdb_line``).
ATOMIC_NUMBER: dict[str, int] = {
    sym: z
    for z, sym in enumerate(
        """H HE LI BE B C N O F NE NA MG AL SI P S CL AR K CA SC TI V CR MN FE
        CO NI CU ZN GA GE AS SE BR KR RB SR Y ZR NB MO TC RU RH PD AG CD IN SN
        SB TE I XE CS BA LA CE PR ND PM SM EU GD TB DY HO ER TM YB LU HF TA W
        RE OS IR PT AU HG TL PB BI PO AT RN FR RA AC TH PA U NP PU AM CM BK CF
        ES FM MD NO LR RF DB SG BH HS MT DS RG CN NH FL MC LV TS OG""".split(),
        start=1,
    )
}

#: Names PyMOL treats as the nucleic backbone markers, allowing ``*`` for ``'``
#: as files written before the mmCIF era do.
_NUCLEIC_MARKERS = {
    "O3": ("O3'", "O3*"),
    "C3": ("C3'", "C3*"),
    "C4": ("C4'", "C4*"),
    "C5": ("C5'", "C5*"),
    "O5": ("O5'", "O5*"),
}


@dataclass
class AtomClasses:
    """Per-atom boolean masks for every class PyMOL's selector can name."""

    protein: np.ndarray
    nucleic: np.ndarray
    organic: np.ndarray
    solvent: np.ndarray
    inorganic: np.ndarray
    guide: np.ndarray
    backbone: np.ndarray
    sidechain: np.ndarray
    hydrogen: np.ndarray
    metal: np.ndarray

    @property
    def polymer(self) -> np.ndarray:
        """Protein or nucleic — PyMOL's ``cAtomFlag_polymer``."""
        return self.protein | self.nucleic


def is_metal(elements: np.ndarray) -> np.ndarray:
    """Which atoms are metals, by proton count.

    Parameters
    ----------
    elements : numpy.ndarray
        Element symbols, one per atom.

    Returns
    -------
    numpy.ndarray
        Boolean mask.

    Notes
    -----
    The ranges are ``AtomInfoType::isMetal`` in ``layer2/AtomInfo.h``: everything
    metallic falls in ``3-4``, ``11-13``, ``19-31``, ``37-50``, ``55-84`` or above
    ``86``. Expressed as proton counts it needs no periodic-table bookkeeping.
    """
    symbols = np.char.upper(np.char.strip(np.asarray(elements).astype(str)))
    protons = np.array([ATOMIC_NUMBER.get(s, 0) for s in symbols], dtype=int)
    return (
        ((protons > 2) & (protons < 5))
        | ((protons > 10) & (protons < 14))
        | ((protons > 18) & (protons < 32))
        | ((protons > 36) & (protons < 51))
        | ((protons > 54) & (protons < 85))
        | (protons > 86)
    )


def residue_runs(atoms: np.ndarray) -> list[tuple[int, int]]:
    """Split atoms into contiguous residues, as PyMOL's classifier walks them.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array carrying ``chain`` and ``res_id`` when available.

    Returns
    -------
    list of tuple
        ``(start, stop)`` half-open index ranges, one per residue.

    Notes
    -----
    Contiguity, not sorting: PyMOL classifies each run of adjacent atoms sharing a
    residue, so the same residue number appearing twice in a file (two chains, or
    two copies) yields two runs rather than being merged. That is what lets
    ``solvent``'s "single-atom residue" test work at all.
    """
    n = len(atoms)
    if n == 0:
        return []
    names = atoms.dtype.names or ()
    keys: list[np.ndarray] = []
    for field in ("chain", "res_id", "segi"):
        if field in names:
            keys.append(np.asarray(atoms[field]).astype(str))
    if not keys:
        return [(0, n)]

    changed = np.zeros(n, dtype=bool)
    for key in keys:
        changed[1:] |= key[1:] != key[:-1]
    starts = np.concatenate(([0], np.nonzero(changed)[0]))
    stops = np.concatenate((starts[1:], [n]))
    return [(int(a), int(b)) for a, b in zip(starts, stops)]


def _names_of(atoms: np.ndarray) -> np.ndarray:
    """Upper-cased, stripped atom names, or empty strings when absent."""
    if "atom_name" in (atoms.dtype.names or ()):
        return np.char.upper(np.char.strip(atoms["atom_name"].astype(str)))
    return np.full(len(atoms), "", dtype=object).astype(str)


def _elements_of(atoms: np.ndarray, names: np.ndarray) -> np.ndarray:
    """Element symbols, guessed from the atom name when the field is missing."""
    fields = atoms.dtype.names or ()
    if "element" in fields:
        elements = np.char.upper(np.char.strip(atoms["element"].astype(str)))
        if np.any(elements != ""):
            return elements
    # A PDB atom name begins with the element for everything but hydrogen
    # padding, which is enough to classify.
    return np.array([n[:1] for n in names], dtype="U2")


def classify_atoms(atoms: np.ndarray) -> AtomClasses:
    """Classify every atom, following ``SelectorClassifyAtoms``.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array. ``atom_name`` drives the classification;
        ``element``, ``chain`` and ``res_id`` are used when present.

    Returns
    -------
    AtomClasses
        Boolean masks, one per class.
    """
    n = len(atoms)
    names = _names_of(atoms)
    elements = _elements_of(atoms, names)

    protein = np.zeros(n, dtype=bool)
    nucleic = np.zeros(n, dtype=bool)
    organic = np.zeros(n, dtype=bool)
    solvent = np.zeros(n, dtype=bool)
    inorganic = np.zeros(n, dtype=bool)
    guide = np.zeros(n, dtype=bool)

    hydrogen = np.isin(elements, ("H", "D"))
    metal = is_metal(elements)

    for start, stop in residue_runs(atoms):
        residue = names[start:stop]
        present = set(residue.tolist())
        has_carbon = bool(np.any(elements[start:stop] == "C"))

        is_protein = {"CA", "N", "C", "O"} <= present
        is_nucleic = all(
            any(alias in present for alias in aliases)
            for aliases in _NUCLEIC_MARKERS.values()
        )

        if is_protein:
            protein[start:stop] = True
        elif is_nucleic:
            nucleic[start:stop] = True
        elif has_carbon:
            organic[start:stop] = True
        elif (stop - start) == 1 and ({"O", "OH2"} & present):
            solvent[start:stop] = True
        elif not np.all(hydrogen[start:stop]):
            inorganic[start:stop] = True

        if not (is_protein or is_nucleic):
            continue
        # The guide atom: CA for protein, C4' for nucleic with C3' as fallback.
        wanted = ("CA",) if is_protein else _NUCLEIC_MARKERS["C4"]
        picked = _first_index(residue, wanted)
        if picked is None and is_nucleic:
            picked = _first_index(residue, _NUCLEIC_MARKERS["C3"])
        if picked is not None:
            guide[start + picked] = True

    polymer = protein | nucleic
    on_backbone = np.isin(names, BACKBONE_NAMES)
    backbone = polymer & on_backbone
    sidechain = polymer & ~on_backbone

    return AtomClasses(
        protein=protein,
        nucleic=nucleic,
        organic=organic,
        solvent=solvent,
        inorganic=inorganic,
        guide=guide,
        backbone=backbone,
        sidechain=sidechain,
        hydrogen=hydrogen,
        metal=metal,
    )


def _first_index(residue_names: np.ndarray, wanted: tuple[str, ...]) -> int | None:
    """Index of the first atom in a residue named one of ``wanted``."""
    for candidate in wanted:
        hit = np.nonzero(residue_names == candidate)[0]
        if hit.size:
            return int(hit[0])
    return None
