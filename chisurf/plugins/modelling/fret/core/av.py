"""Accessible volumes for the FRET plugin: the sites, not the solver.

The solver is ``IMP.bff``'s, in C++ (``IMP.bff.get_av``), and so is reading a
structure (``IMP.bff.read_pdb_records``). What is here is the part that is
this application's: walking an ``fps.json`` ``Positions`` section, resolving
each labelling site to an attachment atom **by identity**, dispatching over
several PDBs, and caching what a repeated GUI action would otherwise read
again.

Two things that used to be here are gone. The hand-built ``IMP::Model`` --
particles, a selection, an ``AV`` decorator -- is one ``get_av`` call now.
And the LabelLib/IMP.bff backend switch went with it: ``IMP.bff.labellib``
*is* LabelLib's interface, the same names and the same grids, so the switch
was between a library and its own API.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class AccessibleVolume:
    """Represents the 3D positional distribution of a dye label."""

    points: np.ndarray  # (N, 4) float64 — xyz + weight
    density: np.ndarray  # (nx, ny, nz) float32 — 3D voxel density
    grid_origin: np.ndarray  # (3,) float64
    grid_step: float
    grid_shape: tuple[int, int, int]
    attachment_point: np.ndarray  # (3,) float64
    position_name: str = ""
    params: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return self.points.shape[0] if self.points.ndim == 2 else 0

    @property
    def mean_position(self) -> np.ndarray:
        if self.n_points == 0:
            return self.attachment_point.copy()
        w = self.points[:, 3]
        if w.sum() == 0:
            return self.attachment_point.copy()
        return np.average(self.points[:, :3], axis=0, weights=w)

    @property
    def has_volume(self) -> bool:
        return self.n_points > 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _active_backend_name() -> str:
    """Name of the accessible-volume backend in use.

    Returns
    -------
    str
        Always ``"imp.bff"``. There used to be two -- LabelLib on Windows,
        IMP.bff elsewhere -- and there is one now, because ``IMP.bff.labellib``
        *is* LabelLib's interface: the same names, the same argument order, the
        same grids. Keeping a switch between a library and its own API was
        keeping two ways to be wrong.
    """
    return "imp.bff"


def select_backend(name: str) -> None:
    """Choose the accessible-volume backend.

    Parameters
    ----------
    name : str
        ``"auto"`` or ``"imp-bff"``; ``"labellib"`` is accepted and means the
        same thing (see :func:`_active_backend_name`).

    Raises
    ------
    ValueError
        For any other name.
    """
    if name not in ("auto", "imp-bff", "imp.bff", "labellib"):
        raise ValueError(f"Unknown backend name: '{name}'")


def compute_av(
    atoms: np.ndarray,
    source_xyz: np.ndarray,
    linker_length: float,
    linker_width: float,
    radii: tuple[float, float, float],
    disc_step: float | None = None,
    pdb_path: str | None = None,
    source_info: dict | None = None,
) -> AccessibleVolume:
    """Compute one accessible volume.

    The solver is ``IMP.bff``'s, in C++. This resolves the attachment point
    and hands over arrays; it does not build a model, and it does not know how
    a volume is rastered.

    Parameters
    ----------
    atoms : numpy.ndarray
        ``(N, 4)`` of x, y, z and van der Waals radius -- the obstacles.
    source_xyz : numpy.ndarray
        ``(3,)`` attachment point. Used when the site cannot be resolved from
        ``pdb_path`` and ``source_info``, and as the answer's own attachment
        point either way.
    linker_length, linker_width : float
        The linker, Angstrom.
    radii : tuple of float
        The dye's three radii; a zero second or third radius means AV1.
    disc_step : float, optional
        Grid resolution, Angstrom; ``None`` takes IMP.bff's default
        (``AV_DEFAULT_SIMULATION_GRID_RESOLUTION``, FPS's and Olga's 0.9).
    pdb_path : str, optional
        The structure the site names. When given together with
        ``source_info`` the attachment atom is resolved by *identity*, which
        is the only way that cannot silently attach a dye to the wrong atom.
    source_info : dict, optional
        ``chain_identifier``, ``residue_seq_number``, ``atom_name``, and an
        optional ``allowed_sphere_radius`` (absent: FPS's ``0.5 * linker_width``).

    Returns
    -------
    AccessibleVolume
        The volume, empty (``has_volume`` false) when the search found no
        reachable space -- which is an answer, not an error.
    """
    import IMP.bff as bff

    r1, r2, r3 = (float(r) for r in radii)
    if disc_step is None:
        disc_step = bff.AV_DEFAULT_SIMULATION_GRID_RESOLUTION
    xyz = np.ascontiguousarray(np.asarray(source_xyz, dtype=np.float64)[:3])

    if pdb_path and source_info:
        found = _find_attachment_point(
            atoms,
            str(source_info.get("chain_identifier", "")),
            int(source_info.get("residue_seq_number", 0)),
            str(source_info.get("atom_name", "CA")),
            pdb_path=pdb_path,
        )
        if found is not None:
            xyz = np.ascontiguousarray(np.asarray(found, dtype=np.float64))

    # The allowed sphere around the attachment atom is on: the position's own,
    # else FPS's rule for this width, LinkerInitialSphere 0.5 x linker_width
    # (2.25 A at the default width, ``AV_DEFAULT_ALLOWED_SPHERE``). The
    # attachment atom itself is dropped from the obstacles by IMP.bff.
    declared = (source_info or {}).get("allowed_sphere_radius")
    allowed = (
        float(declared)
        if declared is not None
        else float(bff.av_derived_allowed_sphere_radius(float(linker_width)))
    )
    result = bff.get_av(
        np.ascontiguousarray(np.asarray(atoms, dtype=np.float64)[:, :4]),
        xyz,
        linker_length=float(linker_length),
        linker_width=float(linker_width),
        r1=r1,
        r2=r2,
        r3=r3,
        grid_resolution=float(disc_step),
        allowed_sphere_radius=allowed,
    )

    ng = int(result.ng)
    density = np.ascontiguousarray(np.asarray(result.get_density(), dtype=np.float32)).reshape(
        (ng, ng, ng)
    )
    points = np.asarray(result.points, dtype=np.float64).reshape(-1, 4)
    return AccessibleVolume(
        points=points,
        density=density,
        grid_origin=np.asarray(result.get_grid_origin(), dtype=np.float64),
        grid_step=float(result.grid_step),
        grid_shape=(ng, ng, ng),
        attachment_point=np.asarray(result.attachment_point, dtype=np.float64),
    )


def compute_avs_for_structure(
    atoms: np.ndarray,
    positions: dict,
    pdb_path: str | list[str] | None = None,
    disc_step: float | None = None,
) -> dict[str, AccessibleVolume]:
    """Compute AVs for all positions in an fps.json ``Positions`` dict.

    Parameters
    ----------
    atoms : (N, 4) float64
        xyzr from :func:`load_structure_with_vdw`. Used as fallback if pdb_path is not given.
    positions : dict
        fps.json Positions section.
    """
    import IMP.bff as bff

    if isinstance(pdb_path, (list, tuple)):
        pdb_paths = list(pdb_path)
    elif isinstance(pdb_path, str) and "," in pdb_path:
        pdb_paths = [p.strip() for p in pdb_path.split(",")]
    elif isinstance(pdb_path, str):
        pdb_paths = [pdb_path]
    else:
        pdb_paths = []

    avs: dict[str, AccessibleVolume] = {}
    for pname, pdef in positions.items():
        bi = int(pdef.get("body_id", 0))
        curr_pdb = pdb_paths[bi] if bi < len(pdb_paths) else (pdb_paths[0] if pdb_paths else None)

        if curr_pdb is not None:
            curr_atoms = load_structure_with_vdw(curr_pdb)
        else:
            curr_atoms = atoms

        # Absent parameters take IMP.bff's defaults -- FPS's, the same ones
        # its own fps.json reader applies; an AV3 gets FPS's three radii.
        av3 = pdef.get("simulation_type", "AV1") == "AV3"
        ll = float(pdef.get("linker_length", bff.AV_DEFAULT_LINKER_LENGTH))
        lw = float(pdef.get("linker_width", bff.AV_DEFAULT_LINKER_WIDTH))
        r1 = float(
            pdef.get("radius1", bff.AV_DEFAULT_AV3_RADIUS1 if av3 else bff.AV_DEFAULT_RADIUS1)
        )
        r2 = float(pdef.get("radius2", bff.AV_DEFAULT_AV3_RADIUS2 if av3 else 0.0))
        r3 = float(pdef.get("radius3", bff.AV_DEFAULT_AV3_RADIUS3 if av3 else 0.0))
        ds = float(
            disc_step
            or pdef.get("simulation_grid_resolution", bff.AV_DEFAULT_SIMULATION_GRID_RESOLUTION)
        )

        chain = pdef.get("chain_identifier", "")
        resseq = pdef.get("residue_seq_number", 0)
        aname = pdef.get("atom_name", "CA")

        source_xyz = _find_attachment_point(curr_atoms, chain, resseq, aname, pdb_path=curr_pdb)
        if source_xyz is None:
            avs[pname] = AccessibleVolume(
                points=np.zeros((0, 4), dtype=np.float64),
                density=np.zeros((1, 1, 1), dtype=np.float32),
                grid_origin=np.zeros(3),
                grid_step=ds,
                grid_shape=(1, 1, 1),
                attachment_point=np.zeros(3),
                position_name=pname,
            )
            continue

        clean_atoms = _strip_residue_atoms(curr_atoms, chain, resseq, pdb_path=curr_pdb)

        av = compute_av(
            atoms=clean_atoms,
            source_xyz=source_xyz,
            linker_length=ll,
            linker_width=lw,
            radii=(r1, r2, r3),
            disc_step=ds,
            pdb_path=curr_pdb,
            source_info=pdef,
        )
        av.position_name = pname
        av.params = pdef
        avs[pname] = av
    return avs


# ---------------------------------------------------------------------------
# Helper: the structure's records and its obstacle radii
# ---------------------------------------------------------------------------

# The obstacle radii are not this module's: they are IMP's radii times IMP.bff's
# one declared scale (``chisurf.core.structure.av.radii``), the same set every
# AV door uses. The records below carry identity only -- chain, residue, atom
# name, coordinates -- for resolving a site and stripping its residue.


def _pdb_cache_token(pdb_path: str) -> tuple[str, int, int]:
    """Return a cache token that changes when a PDB file changes.

    Parameters
    ----------
    pdb_path : str
        Path to a PDB file.

    Returns
    -------
    tuple
        Absolute path, modification time in ns, and file size.
    """
    path = os.path.abspath(pdb_path)
    stat = os.stat(path)
    return path, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=32)
def _load_pdb_records_cached(
    pdb_path: str,
    mtime_ns: int,
    size: int,
) -> tuple[tuple[str, int, str, float, float, float], ...]:
    """Load ATOM/HETATM records from a PDB file.

    Parameters
    ----------
    pdb_path : str
        Absolute path to a PDB file.
    mtime_ns : int
        File modification timestamp used as part of the cache key.
    size : int
        File size used as part of the cache key.

    Returns
    -------
    tuple
        Records containing chain, residue number, atom name and xyz.
    """
    del mtime_ns, size
    rows = []
    with open(pdb_path) as f:
        for line in f:
            if not line.startswith(("ATOM  ", "HETATM")):
                continue
            try:
                xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                resseq = int(line[22:26].strip())
            except ValueError:
                continue
            chain = line[21].strip()
            atom_name = line[12:16].strip()
            rows.append((chain, resseq, atom_name, xyz[0], xyz[1], xyz[2]))
    if not rows:
        raise ValueError(f"No ATOM/HETATM coordinates found in '{pdb_path}'")
    return tuple(rows)


def _cached_pdb_records(
    pdb_path: str,
) -> tuple[tuple[str, int, str, float, float, float], ...]:
    """Return cached PDB records for a path.

    Parameters
    ----------
    pdb_path : str
        Path to a PDB file.

    Returns
    -------
    tuple
        Cached ATOM/HETATM records.
    """
    return _load_pdb_records_cached(*_pdb_cache_token(pdb_path))


def load_structure_with_vdw(pdb_path: str) -> np.ndarray:
    """Load a PDB as the obstacle array the solver takes.

    Parameters
    ----------
    pdb_path : str
        The structure.

    Returns
    -------
    numpy.ndarray
        ``(N, 4)`` of x, y, z and obstacle radius: IMP's radius times
        ``AV_DEFAULT_RADIUS_SCALE``, the one radius set of every AV door.

    Notes
    -----
    ``IMP.bff.load_structure_with_vdw`` reads it (through
    :func:`chisurf.core.structure.av.radii.obstacle_xyzr`), cached on
    ``(path, mtime, size)`` inside the library -- an ``fps.json`` with a dozen
    positions reads one file a dozen times. It used to carry FPS's Bondi
    element radii, a second radius set beside IMP's.
    """
    from chisurf.core.structure.av.radii import obstacle_xyzr

    return obstacle_xyzr(pdb_path)


def _find_attachment_point(
    atoms: np.ndarray,
    chain: str,
    resseq: int,
    atom_name: str,
    pdb_path: str | None = None,
) -> np.ndarray | None:
    """Find the coordinates of an attachment atom.

    If pdb_path is provided, the atom is resolved by identity — chain, residue
    number and atom name — and a miss stays a miss: an unresolvable site
    returns ``None`` rather than a positional guess, because a dye attached to
    an unrelated atom yields a plausible and entirely wrong accessible volume.
    Without a PDB file the atoms array carries no identity at all, so the
    residue sequence number is used as a proxy index into it.

    Parameters
    ----------
    atoms : (N, 4) ndarray
        The atoms array (x, y, z, radius).
    chain : str
        The chain identifier.
    resseq : int
        The residue sequence number.
    atom_name : str
        The attachment atom name (e.g., 'CA', 'CB').
    pdb_path : str, optional
        Path to the PDB file for exact matching.

    Returns
    -------
    ndarray or None
        The (3,) coordinates of the attachment atom, or None if not found.
    """
    if pdb_path and os.path.exists(pdb_path):
        try:
            records = _cached_pdb_records(pdb_path)
        except Exception:
            logger.warning("Could not read atom records from %s", pdb_path, exc_info=True)
            return None
        for line_chain, line_resseq, line_atom_name, x, y, z in records:
            if line_resseq == resseq and line_atom_name == atom_name:
                if not chain or line_chain == chain:
                    return np.array([x, y, z], dtype=np.float64)
        logger.warning(
            "Attachment atom '%s:%s:%s' does not exist in %s",
            chain,
            resseq,
            atom_name,
            pdb_path,
        )
        return None

    return atoms[resseq - 1, :3] if resseq > 0 and resseq <= atoms.shape[0] else None


def _strip_residue_atoms(
    atoms: np.ndarray,
    chain: str,
    resseq: int,
    pdb_path: str | None = None,
) -> np.ndarray:
    """Remove the attachment residue's atoms from the coordinate array.

    Parameters
    ----------
    atoms : (N, 4) ndarray
        The atoms array (x, y, z, radius).
    chain : str
        The chain identifier of the residue to exclude.
    resseq : int
        The residue sequence number of the residue to exclude.
    pdb_path : str, optional
        Path to the PDB file for exact matching of residue atoms.

    Returns
    -------
    clean_atoms : (M, 4) ndarray
        The coordinate array with residue atoms removed.
    """
    if not pdb_path or not os.path.exists(pdb_path):
        return atoms

    try:
        records = _cached_pdb_records(pdb_path)
    except Exception:
        return atoms

    if len(records) == atoms.shape[0]:
        keep_mask = np.asarray(
            [
                not (line_resseq == resseq and (not chain or line_chain == chain))
                for line_chain, line_resseq, _, _, _, _ in records
            ],
            dtype=bool,
        )
        return atoms[keep_mask]

    coords_to_exclude = [
        [x, y, z]
        for line_chain, line_resseq, _, x, y, z in records
        if line_resseq == resseq and (not chain or line_chain == chain)
    ]
    if not coords_to_exclude:
        return atoms

    coords_to_exclude_arr = np.array(coords_to_exclude, dtype=np.float64)
    distances = np.linalg.norm(
        atoms[:, None, :3] - coords_to_exclude_arr[None, :, :],
        axis=2,
    )
    return atoms[~np.any(distances < 0.01, axis=1)]
