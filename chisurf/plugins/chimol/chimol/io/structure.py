from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import numpy as np
from qtpy import QtWidgets

logger = logging.getLogger(__name__)

StructureFactory = Optional[Callable[[str], object]]
FileDialogCallable = Optional[Callable[..., Sequence[str]]]

_DEFAULT_FILTER = "Structure files (*.pdb *.ent *.gro *.cif *.mmcif);;All files (*.*)"


class MdtrajNotAvailableError(RuntimeError):
    """Raised when a trajectory requires MDTraj but it is not installed."""

    pass


def _fallback_open_files(parent: Optional[QtWidgets.QWidget] = None) -> list[str]:
    files, _ = QtWidgets.QFileDialog.getOpenFileNames(
        parent,
        "Open structure file",
        "",
        _DEFAULT_FILTER,
    )
    return [str(f) for f in files]


def open_structure_files(
    parent: Optional[QtWidgets.QWidget] = None,
    *,
    opener: FileDialogCallable = None,
    description: str = "Open structure file",
    file_type: str = _DEFAULT_FILTER,
) -> list[str]:
    if opener is not None:
        try:
            result = opener(description=description, file_type=file_type)
            return [str(f) for f in result]
        except Exception:
            pass
    return _fallback_open_files(parent)


@dataclass
class PdbBackbone:
    """Coordinates plus the residue metadata recovered from a PDB file.

    This is the payload used when the core ``Structure`` reader is unavailable
    or fails. Carrying the backbone metadata matters for more than the info
    panel: without residue and chain ids the viewer cannot find segment
    boundaries and splines a single polyline through every atom in file order.

    Attributes
    ----------
    coords : numpy.ndarray
        All ``ATOM``/``HETATM`` coordinates, shape ``(N, 3)``.
    trace_coords : numpy.ndarray or None
        The CA trace, shape ``(M, 3)``, or ``None`` when the file has no
        recognisable protein backbone.
    res_ids, res_names, chain_ids : numpy.ndarray or None
        Per-CA residue number, residue name and chain id, each of length ``M``.
    """

    coords: np.ndarray
    trace_coords: np.ndarray | None = None
    res_ids: np.ndarray | None = None
    res_names: np.ndarray | None = None
    chain_ids: np.ndarray | None = None


def _parse_pdb_backbone(path: str) -> PdbBackbone:
    """Parse coordinates and the CA backbone out of a PDB file.

    Only the first model is read, and alternate locations other than the first
    are skipped, so that a multi-model or altloc-bearing file does not produce a
    trace that jumps between conformers.

    Parameters
    ----------
    path : str
        Path to the PDB file.

    Returns
    -------
    PdbBackbone
        Coordinates and, when a protein backbone is present, the CA trace with
        its residue metadata.

    Raises
    ------
    ValueError
        If the file contains no usable atom coordinates.
    """
    coords: list[tuple[float, float, float]] = []
    trace: list[tuple[float, float, float]] = []
    res_ids: list[int] = []
    res_names: list[str] = []
    chain_ids: list[str] = []
    seen_residues: set[tuple[str, str]] = set()

    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("ENDMDL"):
                break
            is_atom = line.startswith("ATOM")
            if not (is_atom or line.startswith("HETATM")):
                continue
            try:
                xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            except ValueError:
                continue
            coords.append(xyz)

            # The CA trace drives the cartoon/trace geometry, so it must come
            # from polymer records only -- ligands and waters are not backbone.
            if not is_atom:
                continue
            altloc = line[16:17]
            if altloc not in (" ", "", "A"):
                continue
            if line[12:16].strip() != "CA":
                continue
            chain = line[21:22].strip()
            res_seq = line[22:27].strip()  # includes the insertion code
            key = (chain, res_seq)
            if key in seen_residues:
                continue
            seen_residues.add(key)
            try:
                res_id = int(line[22:26])
            except ValueError:
                continue
            trace.append(xyz)
            res_ids.append(res_id)
            res_names.append(line[17:20].strip())
            chain_ids.append(chain)

    if not coords:
        raise ValueError(f"No atom coordinates found in {path!r}")

    if len(trace) >= 2:
        return PdbBackbone(
            coords=np.asarray(coords, dtype=float),
            trace_coords=np.asarray(trace, dtype=float),
            res_ids=np.asarray(res_ids, dtype=int),
            res_names=np.asarray(res_names, dtype=object),
            chain_ids=np.asarray(chain_ids, dtype=object),
        )
    return PdbBackbone(coords=np.asarray(coords, dtype=float))


def parse_pdb_secondary_structure(path: str | Path) -> dict[tuple[str, int], str] | None:
    """Read the author-deposited ``HELIX``/``SHEET`` records from a PDB file.

    A deposited structure carries the depositor's own secondary-structure
    annotation, and that is what PyMOL shows unless the user explicitly asks it
    to recompute with ``dss``. For 148L the two agree exactly, so honouring the
    records is both closer to PyMOL and closer to the truth than any local
    estimate. Files without the records (predictions, trajectory frames, edited
    structures) simply return ``None`` and the caller falls back to computing.

    Parameters
    ----------
    path : str or pathlib.Path
        PDB file to read. Only the header records are parsed.

    Returns
    -------
    dict or None
        ``{(chain_id, residue_number): "H" | "E"}`` covering every residue the
        records span, or ``None`` when the file declares no secondary structure.

    Notes
    -----
    Column positions follow the PDB format: ``HELIX`` puts the initial chain and
    sequence number at columns 20 and 22-25 and the terminal ones at 32 and
    34-37; ``SHEET`` uses 22 and 23-26, and 33 and 34-37. Records spanning
    different start and end chains are skipped rather than guessed at.
    """
    records: dict[tuple[str, int], str] = {}

    def _span(code: str, chain0: str, res0: str, chain1: str, res1: str) -> None:
        c0, c1 = chain0.strip(), chain1.strip()
        if c0 != c1:
            return
        try:
            lo, hi = int(res0), int(res1)
        except ValueError:
            return
        if hi < lo:
            lo, hi = hi, lo
        for res in range(lo, hi + 1):
            records[(c0, res)] = code

    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("HELIX "):
                    _span("H", line[19:20], line[21:25], line[31:32], line[33:37])
                elif line.startswith("SHEET "):
                    _span("E", line[21:22], line[22:26], line[32:33], line[33:37])
                elif line.startswith(("ATOM", "HETATM", "MODEL")):
                    break  # the records all precede the coordinates
    except Exception:
        # Never let a malformed header cost the caller its structure: fall back
        # to computing the assignment, but say so rather than failing silently.
        logger.warning("Could not read secondary-structure records from %s", path,
                       exc_info=True)
        return None

    return records or None


def load_trajectory_frames(path: Path) -> np.ndarray:
    """Load a trajectory or multi-frame structure using MDTraj.

    The returned array has shape ``(T, N, 3)`` with coordinates in Angstroms.
    This helper is only used for formats that are not handled by the IMP-based
    readers in :mod:`chisurf.core.fio.structure.coordinates`.
    """

    try:  # Lazy import so Moview does not hard-depend on mdtraj
        import mdtraj as md  # type: ignore[import]
    except Exception as exc:  # pragma: no cover - environment dependent
        raise MdtrajNotAvailableError(
            "MDTraj is required to load this file type (e.g. GRO/HDF5 trajectory). "
            "Install it with 'conda install -c conda-forge mdtraj' or 'pip install mdtraj'."
        ) from exc

    suffix = path.suffix.lower()
    # For now we restrict to formats where MDTraj can infer topology from the
    # file itself without a separate topology argument.
    if suffix not in {".gro", ".g96", ".h5", ".hdf5"}:
        raise ValueError(f"File type '{suffix}' is not recognised as an MDTraj trajectory/structure")

    try:
        traj = md.load(str(path))
    except Exception as exc:
        raise RuntimeError(f"mdtraj failed to load '{path}': {exc}") from exc

    xyz = getattr(traj, "xyz", None)
    if xyz is None:
        raise RuntimeError(f"mdtraj did not return coordinates for '{path}'")

    arr = np.asarray(xyz, dtype=float)
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.shape[0] == 0 or arr.shape[1] == 0:
        raise RuntimeError(f"mdtraj returned invalid xyz array for '{path}' with shape {arr.shape!r}")

    # MDTraj uses nanometers; convert to Angstrom to be consistent with IMP
    # based loaders used elsewhere in ChiSurf/Moview.
    arr *= 10.0
    return arr


def _read_full_model(structure_factory: Callable[..., object], path: Path) -> object:
    """Build a structure that keeps waters, ligands and modified residues.

    The core reader is tuned for modelling and drops solvent and non-standard
    residues by default, which is wrong for a viewer: a deposited entry then
    appears without the waters and ligands that PyMOL shows, and the atom counts
    disagree with the file. Ask for the full model, and fall back to the plain
    call for factories that predate the arguments (or are not the core reader at
    all, as in standalone Chimol).

    Parameters
    ----------
    structure_factory : callable
        Factory taking a path and returning a structure object.
    path : pathlib.Path
        File to read.

    Returns
    -------
    object
        The structure the factory produced.
    """
    try:
        return structure_factory(
            str(path), keep_water=True, only_standard_residues=False
        )
    except TypeError:
        logger.debug(
            "Structure factory does not accept keep_water/only_standard_residues; "
            "loading %s without solvent and hetero residues.",
            path,
        )
        return structure_factory(str(path))


def load_structure_payload(
    path: Path,
    *,
    structure_factory: StructureFactory = None,
) -> tuple[object | None, PdbBackbone | None]:
    """Load ``path`` as a ``Structure``, falling back to a parsed PDB backbone.

    Parameters
    ----------
    path : pathlib.Path
        File to load.
    structure_factory : callable or None
        Factory building the core ``Structure`` from a path. When it is missing
        or fails, the file is parsed directly for coordinates and backbone.

    Returns
    -------
    tuple
        ``(structure, None)`` when the core reader succeeded, otherwise
        ``(None, PdbBackbone)``.
    """
    structure = None
    if structure_factory is None:
        logger.warning(
            "No structure factory available for %s; falling back to the "
            "built-in PDB parser (no radius of gyration).",
            path,
        )
    else:
        try:
            structure = _read_full_model(structure_factory, path)
        except Exception:
            logger.warning(
                "Structure reader failed for %s; falling back to the built-in "
                "PDB parser (no radius of gyration).",
                path,
                exc_info=True,
            )
            structure = None

    # Reject empty/invalid structures so that callers can fall back to
    # alternative loaders (e.g. MDTraj for trajectories or GRO files).
    if structure is not None:
        try:
            n_atoms = getattr(structure, "n_atoms", None)
        except Exception:
            n_atoms = None
        if isinstance(n_atoms, int) and n_atoms <= 0:
            logger.warning(
                "Structure reader returned an empty structure for %s; falling "
                "back to raw coordinates.",
                path,
            )
            structure = None

    if structure is not None:
        return structure, None

    backbone = _parse_pdb_backbone(str(path))
    coords = backbone.coords
    if coords.ndim != 2 or coords.shape[1] != 3 or coords.shape[0] == 0:
        raise ValueError(f"No valid coordinates in {path}")
    if backbone.trace_coords is None:
        logger.warning(
            "No protein backbone found in %s; the viewer will show bare "
            "coordinates without residues or sequence.",
            path,
        )
    return None, backbone


__all__ = [
    "PdbBackbone",
    "open_structure_files",
    "load_structure_payload",
    "load_trajectory_frames",
    "parse_pdb_secondary_structure",
    "MdtrajNotAvailableError",
]
