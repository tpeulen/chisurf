"""Writing structures back out — PDB and mmCIF.

Without this chimol is a one-way street: it can show a structure but not hand one
back, so any transform, any deleted water, any renumbering is trapped inside the
viewer. That made ``save`` the single largest hole in replacing PyMOL, ahead of
any representation.

The writers deliberately serialise **what the viewer holds**, not the file it came
from: coordinates as currently transformed, atoms as currently present. Rewriting
the source file would silently discard exactly the work a user wants to keep. The
viewer stores coordinates centred and scaled for rendering, so
:func:`unscale_coordinates` puts them back into Angstrom about the original
origin first — writing scene units into a PDB would produce a file that loads
somewhere else entirely.

PyMOL's own rule is followed for the format: chosen from the extension, and an
unrecognised extension writes PDB rather than failing (``pymol/exporting.py``:
"If the file format is not recognized, then a PDB file is written by default").
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = [
    "format_for_path",
    "unscale_coordinates",
    "write_pdb",
    "write_mmcif",
    "write_structure",
]

#: Extensions PyMOL maps to a molecular format, and what we write for each.
_MOLECULAR_FORMATS = {
    ".pdb": "pdb",
    ".ent": "pdb",
    ".pqr": "pdb",
    ".cif": "mmcif",
    ".mmcif": "mmcif",
}

#: Residue names written as ``HETATM`` rather than ``ATOM``.
_SOLVENT = {"HOH", "WAT", "DOD", "H2O", "SOL", "TIP3"}


def format_for_path(path: str | Path) -> str:
    """Pick the output format from the extension, PyMOL's way.

    Parameters
    ----------
    path : str or pathlib.Path
        Target file name.

    Returns
    -------
    str
        ``"pdb"`` or ``"mmcif"``. An unrecognised extension gives ``"pdb"``,
        matching PyMOL rather than raising: a typo in the extension should still
        produce a usable file.
    """
    return _MOLECULAR_FORMATS.get(Path(path).suffix.lower(), "pdb")


def unscale_coordinates(
    coords: np.ndarray, scale: float = 1.0, centre: np.ndarray | None = None
) -> np.ndarray:
    """Undo the viewer's centring and scaling, back to Angstrom.

    The viewer works in scene units about the origin; a file has to carry the
    coordinates the rest of the world uses. Getting this wrong writes a file that
    loads at the wrong size and position, which is worse than not writing one.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(N, 3)`` scene-unit coordinates.
    scale : float
        Scene units per Angstrom.
    centre : numpy.ndarray, optional
        The original centre that was subtracted.

    Returns
    -------
    numpy.ndarray
        ``(N, 3)`` coordinates in Angstrom.
    """
    out = np.asarray(coords, dtype=float)
    if scale and abs(float(scale)) > 1e-12:
        out = out / float(scale)
    if centre is not None:
        out = out + np.asarray(centre, dtype=float).reshape(3)
    return out


def _field(atoms: np.ndarray, name: str, default):
    """Read a field from a structured array, or broadcast a default."""
    names = atoms.dtype.names or ()
    if name in names:
        return atoms[name]
    return np.full(len(atoms), default)


def _is_hetatm(res_names: np.ndarray, elements: np.ndarray) -> np.ndarray:
    """Which records are ``HETATM``: solvent, or anything not a standard residue.

    A viewer cannot always know a residue's polymer status, so this errs toward
    ``ATOM`` for anything with a three-letter name that is not solvent — a
    misfiled ligand still round-trips, whereas a mislabelled backbone would break
    the chain for whatever reads the file next.
    """
    names = np.char.upper(np.char.strip(res_names.astype(str)))
    return np.isin(names, list(_SOLVENT))


def write_pdb(
    path: str | Path,
    atoms: np.ndarray,
    coords: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    title: str | None = None,
) -> int:
    """Write ``ATOM``/``HETATM`` records in PDB column format.

    Parameters
    ----------
    path : str or pathlib.Path
        Target file.
    atoms : numpy.ndarray
        Structured atom array; ``atom_name``, ``res_name``, ``chain``,
        ``res_id`` and ``element`` are used when present.
    coords : numpy.ndarray
        ``(N, 3)`` coordinates **in Angstrom**, aligned with ``atoms``.
    mask : numpy.ndarray, optional
        Boolean selection; only the marked atoms are written.
    title : str, optional
        Written as a ``TITLE`` record.

    Returns
    -------
    int
        Number of atom records written.

    Raises
    ------
    ValueError
        If the atoms and coordinates do not line up.
    """
    xyz = np.asarray(coords, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.shape[0] != len(atoms):
        raise ValueError(
            f"coords {xyz.shape} does not match {len(atoms)} atoms"
        )

    keep = np.ones(len(atoms), dtype=bool) if mask is None else np.asarray(
        mask, dtype=bool
    )
    if keep.shape[0] != len(atoms):
        raise ValueError("mask length does not match the atom count")

    names = _field(atoms, "atom_name", "C").astype(str)
    res_names = _field(atoms, "res_name", "UNK").astype(str)
    chains = _field(atoms, "chain", "A").astype(str)
    res_ids = np.asarray(_field(atoms, "res_id", 1)).astype(int, copy=False)
    elements = _field(atoms, "element", "").astype(str)
    hetatm = _is_hetatm(res_names, elements)

    lines: list[str] = []
    if title:
        lines.append(f"TITLE     {str(title)[:70]}\n")

    serial = 0
    for i in np.nonzero(keep)[0]:
        serial += 1
        name = names[i].strip()[:4]
        # PDB puts a one- or two-letter element name in column 14, not 13, so
        # that a four-character name like "HD11" still lines up.
        atom_field = f"{name:<4}" if len(name) >= 4 else f" {name:<3}"
        element = elements[i].strip().upper()[:2]
        if not element:
            element = "".join(c for c in name if c.isalpha())[:1].upper()
        # Percent formatting rather than f-strings: PDB is a fixed-column
        # format, and the widths read far more clearly written out like this.
        lines.append(
            "%-6s%5d %-4s%1s%3s %1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f"  # noqa: UP031
            "          %2s\n"
            % (
                "HETATM" if hetatm[i] else "ATOM",
                serial % 100000,
                atom_field,
                " ",
                res_names[i].strip()[:3],
                (chains[i].strip() or "A")[:1],
                int(res_ids[i]) % 10000,
                " ",
                xyz[i, 0],
                xyz[i, 1],
                xyz[i, 2],
                1.0,
                0.0,
                element,
            )
        )
    lines.append("END\n")

    Path(path).write_text("".join(lines), encoding="utf-8")
    return serial


def write_mmcif(
    path: str | Path,
    atoms: np.ndarray,
    coords: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    name: str = "chimol",
) -> int:
    """Write a minimal mmCIF with a single ``atom_site`` loop.

    Only the columns a reader needs to reconstruct the model are emitted. mmCIF
    matters here for one specific reason: it has **no 4-character residue-number
    limit**, so a structure that would silently wrap around in PDB format
    survives.

    Parameters
    ----------
    path : str or pathlib.Path
        Target file.
    atoms : numpy.ndarray
        Structured atom array.
    coords : numpy.ndarray
        ``(N, 3)`` coordinates in Angstrom.
    mask : numpy.ndarray, optional
        Boolean selection.
    name : str, optional
        Data block name.

    Returns
    -------
    int
        Number of atom records written.
    """
    xyz = np.asarray(coords, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.shape[0] != len(atoms):
        raise ValueError(
            f"coords {xyz.shape} does not match {len(atoms)} atoms"
        )
    keep = np.ones(len(atoms), dtype=bool) if mask is None else np.asarray(
        mask, dtype=bool
    )

    names = _field(atoms, "atom_name", "C").astype(str)
    res_names = _field(atoms, "res_name", "UNK").astype(str)
    chains = _field(atoms, "chain", "A").astype(str)
    res_ids = np.asarray(_field(atoms, "res_id", 1)).astype(int, copy=False)
    elements = _field(atoms, "element", "C").astype(str)
    hetatm = _is_hetatm(res_names, elements)

    out = [
        f"data_{name}\n",
        "#\n",
        "loop_\n",
        "_atom_site.group_PDB\n",
        "_atom_site.id\n",
        "_atom_site.type_symbol\n",
        "_atom_site.label_atom_id\n",
        "_atom_site.label_comp_id\n",
        "_atom_site.label_asym_id\n",
        "_atom_site.label_seq_id\n",
        "_atom_site.Cartn_x\n",
        "_atom_site.Cartn_y\n",
        "_atom_site.Cartn_z\n",
        "_atom_site.occupancy\n",
        "_atom_site.B_iso_or_equiv\n",
    ]

    serial = 0
    for i in np.nonzero(keep)[0]:
        serial += 1
        element = elements[i].strip().upper() or "C"
        out.append(
            "%s %d %s %s %s %s %d %.3f %.3f %.3f 1.000 0.000\n"  # noqa: UP031
            % (
                "HETATM" if hetatm[i] else "ATOM",
                serial,
                element,
                names[i].strip() or "C",
                res_names[i].strip() or "UNK",
                chains[i].strip() or "A",
                int(res_ids[i]),
                xyz[i, 0],
                xyz[i, 1],
                xyz[i, 2],
            )
        )
    out.append("#\n")
    Path(path).write_text("".join(out), encoding="utf-8")
    return serial


def write_structure(
    path: str | Path,
    atoms: np.ndarray,
    coords: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    title: str | None = None,
) -> tuple[str, int]:
    """Write ``atoms`` in whichever format ``path``'s extension names.

    Returns
    -------
    tuple
        ``(format, n_written)``.
    """
    fmt = format_for_path(path)
    if fmt == "mmcif":
        return fmt, write_mmcif(
            path, atoms, coords, mask=mask, name=Path(path).stem or "chimol"
        )
    return fmt, write_pdb(path, atoms, coords, mask=mask, title=title)
