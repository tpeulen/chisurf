"""Per-voxel site tables: what the dye meets at every position it can reach.

A site table describes one labelled site (structure, residue, linker length) on the voxels of
its accessible volume. Per voxel it holds

* ``neighbours`` ``(n, n_types)`` int8 -- residues of each type within the slow radius (the
  stickiness features);
* ``contacts`` ``(n, n_quenchers, n_offsets, 2)`` float16 -- quenchers in contact with the
  dye at every tested contact-distance change, for the crystal side chains (``[..., 0]``) and
  their rotamer ensembles weighted by probability (``[..., 1]``);
* ``exposure`` ``(n,)`` float32 -- the uncovered fraction of the dye's water shell
  (Shrake-Rupley);
* ``distances`` -- the quencher distances the distance-continuous rate kernel reads: per voxel,
  quencher type and side-chain source (crystal, rotamers weighted by probability), a histogram
  of ``u = r - R_q`` (``r`` voxel centre to quencher centre, ``R_q`` the reference contact
  radius) on the declared ``distance_histogram`` bins, bin 0 collecting everything closer than
  the lowest edge. It is sparse, so it is stored as row, column and weight arrays
  (:class:`DistanceHistogram`).

The geometry is IMP.bff's: the accessible volume (``get_av`` with IMP radii), the voxel frame
(``ProbeAccessibleVolume.get_voxel_centres``), ``residue_type_neighbour_counts``,
``quencher_rotamer_ensembles``, the quenching model's contact maps and
``probe_solvent_exposure``. There is no Python fallback: a kernel IMP.bff lacks raises,
naming it. Tables are cached as ``.npz`` under the settings directory, keyed by the
structure's bytes, the site, every declared setting and the IMP.bff version.

The selections (quenchers, groups, offsets, radii, grid) are declared in
``settings/analysis/site_model.yaml``. The record of the port from the MalE prototype is the
OKF concept ``okf/plugins/quest-prototype-migration.md``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import columns as _columns

#: The site-model declaration file.
SITE_MODEL = _columns.ANALYSIS_SETTINGS_DIR / "site_model.yaml"

#: Bumped whenever the table's construction changes in this module.
SCHEMA = "site-table-v2"

#: The IMP.bff names a site table needs.
_KERNELS = (
    "get_av",
    "ObstacleAtoms",
    "ProbeAccessibleVolume",
    "QuenchedDonorDecay",
    "ResidueQuenching",
    "ResidueQuenchingMap",
    "amino_acid_quenching_defaults",
    "residue_type_neighbour_counts",
    "quencher_rotamer_ensembles",
    "probe_solvent_exposure",
    "get_data_path",
)


def settings(path=SITE_MODEL):
    """The declared site-model settings.

    Parameters
    ----------
    path : str or pathlib.Path, optional
        Declaration file; ``settings/analysis/site_model.yaml`` by default.

    Returns
    -------
    dict
        The ``settings`` mapping.
    """
    return _columns.settings(path)


def residue_types(settings_=None):
    """Residue types of the neighbour columns, group by group in declared order.

    Parameters
    ----------
    settings_ : dict, optional
        Declared settings; the site-model file by default.

    Returns
    -------
    list of str
    """
    s = settings_ or settings()
    return [r for group in s["groups"].values() for r in group]


def _bff():
    """IMP.bff with every kernel a site table needs.

    Returns
    -------
    module
        ``IMP.bff``.

    Raises
    ------
    ImportError
        When IMP.bff is missing, or lacks one of the kernels (named in the message).
    """
    try:
        import IMP.bff as bff
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(f"site tables need IMP.bff, which is not importable ({exc})") from exc
    missing = [name for name in _KERNELS if not hasattr(bff, name)]
    if missing:
        raise ImportError(
            f"this IMP.bff ({getattr(bff, '__version__', '?')}) lacks the site-table kernel(s) "
            f"{', '.join(missing)}; update imp.bff"
        )
    for name in ("get_voxel_indices", "get_voxel_centres"):
        if not hasattr(bff.ProbeAccessibleVolume, name):
            raise ImportError(f"this IMP.bff lacks ProbeAccessibleVolume.{name}; update imp.bff")
    return bff


def rotamer_library_path():
    """IMP.bff's side-chain rotamer library (``sidechains.drot.pto``).

    Returns
    -------
    pathlib.Path

    Raises
    ------
    FileNotFoundError
        When IMP.bff's data is not installed (``imp_bff_fetch_data``).
    """
    path = Path(_bff().get_data_path("rotamer_library")) / "sidechains.drot.pto"
    if not path.exists():
        raise FileNotFoundError(
            f"IMP.bff's side-chain library {path} is missing; run imp_bff_fetch_data"
        )
    return path


# ------------------------------------------------------------------ atoms --


def site_atoms(structure, site, chain=None, settings_=None):
    """The obstacle atoms of a labelled site.

    Waters and hydrogens are dropped; at the labelled residue only the backbone and the
    attachment atom stay (the dye replaces the side chain). The atom set is the plugin
    reader's (IMP's default selector: first model, altloc blank or A, ligands kept).

    Parameters
    ----------
    structure : str or pathlib.Path or numpy.ndarray
        Structure file (PDB or mmCIF), or an atom array of
        :func:`~chisurf.plugins.quenching_estimator.core.structure.reader.read`.
    site : int
        Labelled residue number.
    chain : str, optional
        Labelled chain; the declared ``chain`` by default.
    settings_ : dict, optional
        Declared settings; the site-model file by default.

    Returns
    -------
    numpy.ndarray
        The kept atoms (the reader's structured dtype).
    """
    s = settings_ or settings()
    chain = s["chain"] if chain is None else chain
    if isinstance(structure, np.ndarray):
        atoms = structure
    else:
        from ..structure import reader

        atoms = reader.read(str(structure), verbose=False)
    element = np.char.upper(np.char.strip(atoms["element"].astype(str)))
    keep = ~np.isin(element, list(s["dropped_elements"]))
    at_site = (atoms["chain"].astype(str) == chain) & (atoms["res_id"] == int(site))
    names = np.char.strip(atoms["atom_name"].astype(str))
    keep &= ~(at_site & ~np.isin(names, list(s["site_atoms"])))
    return atoms[keep]


def obstacles(atoms):
    """IMP.bff ``ObstacleAtoms`` of an atom array.

    Parameters
    ----------
    atoms : numpy.ndarray
        Atom array (reader dtype).

    Returns
    -------
    IMP.bff.ObstacleAtoms
    """
    o = _bff().ObstacleAtoms()
    o.chains = [str(c) for c in atoms["chain"]]
    o.res_ids = [int(r) for r in atoms["res_id"]]
    o.res_names = [str(r).strip() for r in atoms["res_name"]]
    o.atom_names = [str(a).strip() for a in atoms["atom_name"]]
    o.coords = [float(v) for v in np.asarray(atoms["coord"], dtype=float).ravel()]
    return o


def attachment_point(atoms, site, chain=None, settings_=None):
    """Coordinates of the attachment atom of the labelled residue.

    Parameters
    ----------
    atoms : numpy.ndarray
        Atom array (reader dtype).
    site : int
        Labelled residue number.
    chain : str, optional
        Labelled chain; the declared ``chain`` by default.
    settings_ : dict, optional
        Declared settings.

    Returns
    -------
    numpy.ndarray
        ``(3,)`` in A.

    Raises
    ------
    ValueError
        When the residue has no (or more than one) attachment atom.
    """
    s = settings_ or settings()
    chain = s["chain"] if chain is None else chain
    hit = np.flatnonzero(
        (atoms["chain"].astype(str) == chain)
        & (atoms["res_id"] == int(site))
        & (np.char.strip(atoms["atom_name"].astype(str)) == s["attachment_atom"])
    )
    if hit.size != 1:
        raise ValueError(f"{chain}:{site} has {hit.size} {s['attachment_atom']} atoms, need one")
    return np.asarray(atoms["coord"][hit[0]], dtype=float)


def accessible_volume(atoms, site, linker_length, chain=None, settings_=None):
    """The dye's accessible volume at a site, with today's IMP.bff geometry.

    The obstacles are IMP's radii times IMP.bff's radius scale; allowed sphere and link search
    are IMP.bff's defaults unless ``settings.av`` sets them. Linker width, dye radius and grid
    are the declared analysis values.

    Parameters
    ----------
    atoms : numpy.ndarray
        Obstacle atoms (:func:`site_atoms`).
    site : int
        Labelled residue number.
    linker_length : float
        Stretched linker length (A).
    chain : str, optional
        Labelled chain.
    settings_ : dict, optional
        Declared settings.

    Returns
    -------
    IMP.bff.ProbeAccessibleVolume
    """
    from ..av import _link_search_stencil, av_defaults

    s = settings_ or settings()
    bff = _bff()
    defaults = av_defaults()
    av = dict(s.get("av") or {})
    scale = defaults["radius_scale"] if av.get("radius_scale") is None else av["radius_scale"]
    sphere = (
        defaults["allowed_sphere_radius"]
        if av.get("allowed_sphere_radius") is None
        else av["allowed_sphere_radius"]
    )
    link = defaults["link_search"] if av.get("link_search") is None else av["link_search"]
    xyzr = np.ascontiguousarray(
        np.hstack(
            [
                np.asarray(atoms["coord"], dtype=np.float64).reshape(-1, 3),
                (np.asarray(atoms["radius"], dtype=np.float64) * float(scale)).reshape(-1, 1),
            ]
        )
    )
    return bff.get_av(
        xyzr,
        [float(v) for v in attachment_point(atoms, site, chain, s)],
        float(linker_length),
        float(s["linker_width"]),
        float(s["dye_radius"]),
        0.0,
        0.0,
        float(s["grid"]),
        float(sphere),
        int(_link_search_stencil(link)),
    )


# --------------------------------------------------------------- features --


def quencher_ensembles(atoms, site, chain=None, settings_=None, library=None):
    """Crystal centre and rotamer ensemble of every quenching residue of the chain.

    The labelled residue is left out (its side chain is replaced by the dye).

    Parameters
    ----------
    atoms : numpy.ndarray
        Obstacle atoms (:func:`site_atoms`).
    site : int
        Labelled residue number.
    chain : str, optional
        Labelled chain.
    settings_ : dict, optional
        Declared settings.
    library : str or pathlib.Path, optional
        Rotamer library; :func:`rotamer_library_path` by default.

    Returns
    -------
    list of dict
        ``{"name", "res_id", "crystal" (3,), "centres" (m, 3), "probabilities" (m,),
        "from_library"}`` in chain order.
    """
    s = settings_ or settings()
    chain = s["chain"] if chain is None else chain
    bff = _bff()
    o = obstacles(atoms)
    found = bff.quencher_rotamer_ensembles(
        o.chains,
        o.res_ids,
        o.res_names,
        o.atom_names,
        o.coords,
        list(s["quenchers"]),
        str(library or rotamer_library_path()),
        bff.ResidueQuenchingMap(),
        float(s["clash"]),
    )
    out = []
    for q in found:
        if str(q.chain) != chain or int(q.res_id) == int(site):
            continue
        out.append(
            dict(
                name=str(q.res_name),
                res_id=int(q.res_id),
                crystal=np.asarray(q.get_crystal(), dtype=float),
                centres=np.asarray(q.get_centres(), dtype=float).reshape(-1, 3),
                probabilities=np.asarray(q.get_probabilities(), dtype=float),
                from_library=bool(q.from_library),
            )
        )
    return out


def _grid_options(s):
    """The quenching model's grid keyword arguments (declared ``grid_options``)."""
    return {k: (int(v) if k == "n_photons" else float(v)) for k, v in s["grid_options"].items()}


def contact_map(av, quenchers, name, delta, source, settings_=None):
    """Quenchers of one type in contact with the dye, per voxel (rotamers weighted).

    Every quencher centre is a point obstacle of its own residue; its contact radius is the
    reference chemistry's ``quench_radius`` plus *delta*, and its map value is its weight
    (1 for the crystal centre, the rotamer probability otherwise). The map is the quenching
    model's rate map at unit rate, so the grid frame and the stamping are IMP.bff's.

    Parameters
    ----------
    av : IMP.bff.ProbeAccessibleVolume
        The site's volume.
    quenchers : list of dict
        :func:`quencher_ensembles`.
    name : str
        Quencher residue type.
    delta : float
        Contact-distance change (A).
    source : {"crystal", "rotamer"}
        Which side-chain positions.
    settings_ : dict, optional
        Declared settings.

    Returns
    -------
    numpy.ndarray or None
        Flat ``ng**3`` map, ``None`` when the chain has no quencher of this type.
    """
    s = settings_ or settings()
    bff = _bff()
    radius = bff.amino_acid_quenching_defaults(1.0, 1.0, float(s["dye_radius"]))[name].quench_radius
    radius = float(radius) + float(delta)
    centres, table = [], bff.ResidueQuenchingMap()
    for q in quenchers:
        if q["name"] != name:
            continue
        if source == "crystal":
            pairs = [(q["crystal"], 1.0)]
        else:
            pairs = list(zip(q["centres"], q["probabilities"]))
        for centre, weight in pairs:
            label = f"Q{len(centres):04d}"
            centres.append(np.asarray(centre, dtype=float))
            table[label] = bff.ResidueQuenching(1.0, float(weight), radius, ["X"])
    if not centres:
        return None
    o = bff.ObstacleAtoms()
    o.chains = [s["chain"]] * len(centres)
    o.res_ids = list(range(1, len(centres) + 1))
    o.res_names = [f"Q{i:04d}" for i in range(len(centres))]
    o.atom_names = ["X"] * len(centres)
    o.coords = [float(v) for c in centres for v in c]
    m = bff.QuenchedDonorDecay(
        av, o, tau0=4.0, quenching_table=table, n_trajectories=1, random_seed=1, t_max=1.0,
        **_grid_options(s),
    )
    m.update_grids()
    return np.asarray(m.get_quenching_rate_map(), dtype=float).ravel()


@dataclass(frozen=True)
class DistanceHistogram:
    """Sparse per-voxel histogram of quencher distances (see the module docstring).

    Entry ``e`` adds ``weights[e]`` to voxel ``rows[e]``, quencher ``q``, source ``m`` and bin
    ``b`` with ``columns[e] = (q * 2 + m) * n_bins + b``.

    Attributes
    ----------
    rows : numpy.ndarray
        ``(nnz,)`` int32, ascending.
    columns : numpy.ndarray
        ``(nnz,)`` int16.
    weights : numpy.ndarray
        ``(nnz,)`` float32: quencher centres (crystal 1, rotamers their probability).
    lower, step : float
        Lowest bin edge and bin width of u (A); bin 0 is everything below *lower*.
    n_bins : int
        Bins per (quencher, source), the underflow bin included.
    """

    rows: np.ndarray
    columns: np.ndarray
    weights: np.ndarray
    lower: float
    step: float
    n_bins: int

    def edges(self):
        """Lower and upper edge of every bin (bin 0 from -inf).

        Returns
        -------
        tuple of numpy.ndarray
        """
        k = np.arange(self.n_bins)
        lo = self.lower + (k - 1) * self.step
        lo[0] = -np.inf
        return lo, lo + self.step


def distance_bins(settings_=None):
    """The declared histogram bins: ``(lower, step, n_bins)`` (underflow bin included).

    Parameters
    ----------
    settings_ : dict, optional

    Returns
    -------
    tuple
    """
    s = settings_ or settings()
    d = s["distance_histogram"]
    lower, upper, step = float(d["lower"]), float(d["upper"]), float(d["step"])
    return lower, step, int(round((upper - lower) / step)) + 1


def distance_histogram(centres, quenchers, settings_=None, chunk=20000):
    """The quencher-distance histogram of every voxel.

    Parameters
    ----------
    centres : numpy.ndarray
        ``(n, 3)`` voxel centres (the volume's grid frame).
    quenchers : list of dict
        :func:`quencher_ensembles`.
    settings_ : dict, optional
    chunk : int, optional
        Voxels per block (memory).

    Returns
    -------
    DistanceHistogram
    """
    s = settings_ or settings()
    bff = _bff()
    lower, step, n_bins = distance_bins(s)
    defaults = bff.amino_acid_quenching_defaults(1.0, 1.0, float(s["dye_radius"]))
    centres = np.asarray(centres, float)
    rows, cols, weights = [], [], []
    for q, name in enumerate(s["quenchers"]):
        radius = float(defaults[name].quench_radius)
        for m, source in enumerate(("crystal", "rotamer")):
            points, w = [], []
            for x in quenchers:
                if x["name"] != name:
                    continue
                if source == "crystal":
                    points.append(x["crystal"])
                    w.append(1.0)
                else:
                    points.extend(x["centres"])
                    w.extend(x["probabilities"])
            if not points:
                continue
            points, w = np.asarray(points, float), np.asarray(w, float)
            base = (q * 2 + m) * n_bins
            for start in range(0, len(centres), chunk):
                block = centres[start:start + chunk]
                u = np.sqrt(((block[:, None, :] - points[None]) ** 2).sum(-1)) - radius
                b = np.floor((u - lower) / step).astype(np.int64) + 1
                b[u < lower] = 0
                keep = b < n_bins
                r_local, c_local = np.nonzero(keep)
                flat = r_local * n_bins + b[keep]
                hist = np.bincount(flat, weights=w[c_local], minlength=len(block) * n_bins)
                nz = np.flatnonzero(hist)
                rows.append(start + nz // n_bins)
                cols.append(base + nz % n_bins)
                weights.append(hist[nz])
    if rows:
        rows, cols, weights = (np.concatenate(v) for v in (rows, cols, weights))
    else:
        rows, cols, weights = np.zeros(0, int), np.zeros(0, int), np.zeros(0)
    order = np.lexsort((cols, rows))
    return DistanceHistogram(rows=rows[order].astype(np.int32), columns=cols[order].astype(np.int16),
                             weights=weights[order].astype(np.float32), lower=lower, step=step,
                             n_bins=n_bins)


def water_radii(atoms, settings_=None):
    """Radius of each atom a water molecule may not overlap (declared per element).

    Parameters
    ----------
    atoms : numpy.ndarray
        Atom array.
    settings_ : dict, optional
        Declared settings.

    Returns
    -------
    numpy.ndarray
    """
    s = settings_ or settings()
    table = {str(k).upper(): float(v) for k, v in s["water_vdw_radii"].items()}
    default = float(s["water_vdw_default"])
    return np.array(
        [table.get(str(e).strip().upper(), default) for e in atoms["element"]], dtype=float
    )


@dataclass(frozen=True)
class SiteTable:
    """One site's per-voxel features (see the module docstring).

    Attributes
    ----------
    neighbours : numpy.ndarray
        ``(n, n_types)`` int8, columns in :func:`residue_types` order.
    contacts : numpy.ndarray
        ``(n, n_quenchers, n_offsets, 2)`` float16; last axis crystal, rotamer.
    exposure : numpy.ndarray
        ``(n,)`` float32 water exposure.
    voxel_indices : numpy.ndarray or None
        ``(n,)`` flat C-order voxel index into the volume's ``ng**3`` grid.
    distances : DistanceHistogram or None
        Quencher distances (``None`` for a prototype table or a schema-v1 file).
    meta : dict
        Volume geometry (``ng``, ``dg``, ``grid_origin``, ``attachment``) and the inputs.
    path : pathlib.Path or None
        The cache file it was read from or written to.
    """

    neighbours: np.ndarray
    contacts: np.ndarray
    exposure: np.ndarray
    voxel_indices: np.ndarray | None = None
    distances: DistanceHistogram | None = None
    meta: dict = field(default_factory=dict)
    path: Path | None = None

    @property
    def n_voxels(self):
        """Number of reachable voxels."""
        return int(self.neighbours.shape[0])

    def voxel_centres(self):
        """Voxel centres (A), from the stored grid frame.

        Returns
        -------
        numpy.ndarray
            ``(n, 3)``.

        Raises
        ------
        ValueError
            When the table carries no voxel geometry (a prototype table).
        """
        if self.voxel_indices is None or "ng" not in self.meta:
            raise ValueError("this site table carries no voxel geometry")
        ng = int(self.meta["ng"])
        ijk = np.stack(np.unravel_index(self.voxel_indices, (ng,) * 3), 1)
        return np.asarray(self.meta["grid_origin"], dtype=float) + ijk * float(self.meta["dg"])

    def save(self, path):
        """Write the table as compressed ``.npz``.

        Parameters
        ----------
        path : str or pathlib.Path

        Returns
        -------
        pathlib.Path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        extra = {} if self.voxel_indices is None else {"voxel_indices": self.voxel_indices}
        if self.distances is not None:
            d = self.distances
            extra.update(distance_rows=d.rows, distance_columns=d.columns,
                         distance_weights=d.weights,
                         distance_bins=np.array([d.lower, d.step, d.n_bins], float))
        tmp = path.with_name(path.name + ".part.npz")
        np.savez_compressed(
            tmp,
            neighbours=self.neighbours,
            contacts=self.contacts,
            exposure=self.exposure,
            meta=np.array(json.dumps(self.meta, sort_keys=True)),
            **extra,
        )
        tmp.replace(path)
        return path


def load_site_table(path):
    """Read a site table (this module's, or a MalE prototype cache file).

    Parameters
    ----------
    path : str or pathlib.Path

    Returns
    -------
    SiteTable
    """
    path = Path(path)
    with np.load(path, allow_pickle=False) as f:
        meta = json.loads(str(f["meta"])) if "meta" in f else {}
        distances = None
        if "distance_rows" in f:
            lower, step, n_bins = (float(v) for v in f["distance_bins"])
            distances = DistanceHistogram(rows=f["distance_rows"], columns=f["distance_columns"],
                                          weights=f["distance_weights"], lower=lower, step=step,
                                          n_bins=int(n_bins))
        return SiteTable(
            distances=distances,
            neighbours=f["neighbours"],
            contacts=f["contacts"],
            exposure=f["exposure"],
            voxel_indices=f["voxel_indices"] if "voxel_indices" in f else None,
            meta=meta,
            path=path,
        )


def table_from_volume(av, atoms, site, chain=None, settings_=None, library=None):
    """Build a site table on a given volume.

    The voxels are ``av.get_voxel_indices()`` in that order; their centres are
    ``av.get_voxel_centres()`` (the grid frame).

    Parameters
    ----------
    av : IMP.bff.ProbeAccessibleVolume
        The site's volume (:func:`accessible_volume`, or any other, e.g. a stored one).
    atoms : numpy.ndarray
        Obstacle atoms (:func:`site_atoms`).
    site : int
        Labelled residue number.
    chain : str, optional
        Labelled chain.
    settings_ : dict, optional
        Declared settings.
    library : str or pathlib.Path, optional
        Rotamer library.

    Returns
    -------
    SiteTable
    """
    s = settings_ or settings()
    bff = _bff()
    points = np.asarray(av.get_voxel_indices(), dtype=np.int64)
    o = obstacles(atoms)
    counts = np.asarray(
        bff.residue_type_neighbour_counts(av, o, residue_types(s), float(s["slow_radius"]))
    )
    if counts.max(initial=0) > np.iinfo(np.int8).max:
        raise OverflowError("a neighbour count exceeds int8")
    neighbours = counts.astype(np.int8)

    quenchers = quencher_ensembles(atoms, site, chain, s, library)
    offsets = list(s["radius_offsets"])
    contacts = np.zeros((len(points), len(s["quenchers"]), len(offsets), 2), dtype=np.float32)
    for k, name in enumerate(s["quenchers"]):
        for j, delta in enumerate(offsets):
            for m, source in enumerate(("crystal", "rotamer")):
                grid = contact_map(av, quenchers, name, delta, source, s)
                if grid is not None:
                    contacts[:, k, j, m] = grid[points]

    centres = np.asarray(av.get_voxel_centres(), dtype=float)
    distances = distance_histogram(centres, quenchers, s)
    xyz = np.asarray(atoms["coord"], dtype=float)
    exposure = np.asarray(
        bff.probe_solvent_exposure(
            centres.ravel(), xyz.ravel(), water_radii(atoms, s), float(s["dye_radius"]),
            float(s["water_radius"]), int(s["exposure_points"]),
        ),
        dtype=float,
    )
    meta = dict(
        ng=int(av.ng),
        dg=float(av.grid_step),
        grid_origin=[float(v) for v in av.get_grid_origin()],
        attachment=[float(v) for v in av.get_attachment_point()],
        n_quenchers=len(quenchers),
        n_rotamer_quenchers=int(sum(q["from_library"] for q in quenchers)),
    )
    return SiteTable(
        neighbours=neighbours,
        contacts=contacts.astype(np.float16),
        exposure=exposure.astype(np.float32),
        voxel_indices=points.astype(np.int32),
        distances=distances,
        meta=meta,
    )


# ------------------------------------------------------------------ cache --


def default_cache_dir():
    """Where site tables are cached: ``<settings>/cache/quenching_estimator/site_tables``.

    Returns
    -------
    pathlib.Path
    """
    from chisurf.core.settings.path_utils import get_path

    return Path(get_path("settings")) / "cache" / "quenching_estimator" / "site_tables"


def site_key(structure_path, site, linker_length, chain=None, settings_=None):
    """Content key of a site table.

    It covers the structure file's bytes, the site, the linker length, every declared
    setting the table depends on, the table schema and the IMP.bff version.

    Parameters
    ----------
    structure_path : str or pathlib.Path
    site : int
    linker_length : float
    chain : str, optional
    settings_ : dict, optional

    Returns
    -------
    str
        16 hex digits.
    """
    s = settings_ or settings()
    bff = _bff()
    used = {
        k: s[k]
        for k in (
            "chain", "attachment_atom", "site_atoms", "dropped_elements", "linker_width",
            "dye_radius", "grid", "av", "quenchers", "groups", "slow_radius", "radius_offsets",
            "clash", "water_radius", "exposure_points", "water_vdw_radii", "water_vdw_default",
            "grid_options", "distance_histogram",
        )
    }
    blob = json.dumps(
        [
            SCHEMA,
            hashlib.sha256(Path(structure_path).read_bytes()).hexdigest(),
            s["chain"] if chain is None else chain,
            int(site),
            round(float(linker_length), 6),
            used,
            str(getattr(bff, "__version__", "?")),
        ],
        sort_keys=True,
    )
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def build_site_table(structure_path, site, linker_length, chain=None, settings_=None):
    """Build a site table from a structure (no cache).

    Parameters
    ----------
    structure_path : str or pathlib.Path
        PDB or mmCIF file.
    site : int
        Labelled residue.
    linker_length : float
        Stretched linker length (A).
    chain : str, optional
        Labelled chain.
    settings_ : dict, optional
        Declared settings.

    Returns
    -------
    SiteTable
    """
    s = settings_ or settings()
    atoms = site_atoms(structure_path, site, chain, s)
    av = accessible_volume(atoms, site, linker_length, chain, s)
    table = table_from_volume(av, atoms, site, chain, s)
    table.meta.update(
        structure=Path(structure_path).name, site=int(site), linker_length=float(linker_length),
        chain=s["chain"] if chain is None else chain,
    )
    return table


def site_table(structure_path, site, linker_length, chain=None, settings_=None, cache_dir=None,
               use_cache=True):
    """The site table of (structure, site, linker), read from the cache or built and stored.

    Parameters
    ----------
    structure_path : str or pathlib.Path
        PDB or mmCIF file.
    site : int
        Labelled residue.
    linker_length : float
        Stretched linker length (A).
    chain : str, optional
        Labelled chain.
    settings_ : dict, optional
        Declared settings.
    cache_dir : str or pathlib.Path, optional
        Cache folder; :func:`default_cache_dir` by default.
    use_cache : bool, optional
        False builds without reading or writing the cache.

    Returns
    -------
    SiteTable
    """
    s = settings_ or settings()
    if not use_cache:
        return build_site_table(structure_path, site, linker_length, chain, s)
    folder = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    path = folder / f"site_{site_key(structure_path, site, linker_length, chain, s)}.npz"
    if path.exists():
        return load_site_table(path)
    table = build_site_table(structure_path, site, linker_length, chain, s)
    table.save(path)
    return load_site_table(path)


def male_structure(state, settings_=None):
    """Path of a shipped MalE structure (``examples/male/``).

    Parameters
    ----------
    state : str
        ``APO`` or ``HOLO`` (declared ``structures``).
    settings_ : dict, optional

    Returns
    -------
    pathlib.Path
    """
    s = settings_ or settings()
    return Path(__file__).resolve().parents[2] / "examples" / "male" / s["structures"][state]


# ------------------------------------------------- equilibrium vs the walk --


def direct_lifetime(av, atoms, slow_factor, tau0, settings_=None):
    """Equilibrium mean lifetime with the quenching model's own maps (notebook cell 23).

    The occupancy of a voxel is ``1 / s`` (``s`` the slow-factor map at one slow factor for
    every residue), and the lifetime there is ``1 / (1/tau0 + k)`` with ``k`` the reference
    chemistry's quenching-rate map; no visibility cutoff.

    Parameters
    ----------
    av : IMP.bff.ProbeAccessibleVolume
    atoms : numpy.ndarray
        Obstacle atoms.
    slow_factor : float
    tau0 : float
        ns.
    settings_ : dict, optional
        Declared settings (``validation`` block).

    Returns
    -------
    float
        ns.
    """
    s = settings_ or settings()
    v = s["validation"]
    bff = _bff()
    table = bff.amino_acid_quenching_defaults(1.0, float(slow_factor), float(s["dye_radius"]))
    m = bff.QuenchedDonorDecay(
        av, obstacles(atoms), tau0=float(tau0), quenching_table=table,
        critical_distance=float(v["critical_distance"]), slow_radius=float(s["slow_radius"]),
        probe_radius=float(s["dye_radius"]), diffusion_coefficient=float(v["diffusion_coefficient"]),
        slow_fact=float(slow_factor), t_step=float(v["t_step"]), t_max=1.0, n_photons=1,
        n_trajectories=1, random_seed=1,
    )
    m.update_grids()
    return equilibrium_lifetime(
        m.get_density(), m.get_slow_factor_map(), m.get_quenching_rate_map(), tau0
    )


def equilibrium_lifetime(density, slow_factor_map, rate_map, tau0):
    """Static mean lifetime over the equilibrium occupancy ``p ~ 1/s`` (notebook cell 23).

    The one copy of the closed form: :func:`direct_lifetime` calls it on IMP.bff's maps,
    and the forward simulator's ``"equilibrium"`` ensemble
    (``core/ensembles.py``) on its own. With ``s = prod_g s_g^(n_g)`` it is the site
    model's ``p ~ prod s^-n`` (:meth:`.site_model.Site.weights`).

    Parameters
    ----------
    density, slow_factor_map, rate_map : array_like
        Same-shape maps: occupancy (> 0 inside), slow factor ``s``, quenching rate (1/ns).
    tau0 : float
        ns.

    Returns
    -------
    float
        ``sum_x p(x) / (1/tau0 + k(x))``, ns.
    """
    density = np.asarray(density, dtype=float).ravel()
    s_map = np.asarray(slow_factor_map, dtype=float).ravel()
    k_map = np.asarray(rate_map, dtype=float).ravel()
    ok = (density > 0) & (s_map > 0)
    p = 1.0 / s_map[ok]
    p /= p.sum()
    return float((p / (1.0 / float(tau0) + k_map[ok])).sum())


def walk_lifetimes(av, atoms, slow_factor, tau0, settings_=None):
    """Brownian-walk mean lifetimes, one per declared seed (notebook cell 23).

    Parameters
    ----------
    av : IMP.bff.ProbeAccessibleVolume
    atoms : numpy.ndarray
    slow_factor : float
    tau0 : float
    settings_ : dict, optional

    Returns
    -------
    list of float
        ns, quantum yield times tau0 per seed.
    """
    s = settings_ or settings()
    v = s["validation"]
    bff = _bff()
    table = bff.amino_acid_quenching_defaults(1.0, float(slow_factor), float(s["dye_radius"]))
    out = []
    for seed in v["seeds"]:
        m = bff.QuenchedDonorDecay(
            av, obstacles(atoms), tau0=float(tau0), quenching_table=table,
            critical_distance=float(v["critical_distance"]), slow_radius=float(s["slow_radius"]),
            probe_radius=float(s["dye_radius"]),
            diffusion_coefficient=float(v["diffusion_coefficient"]), slow_fact=float(slow_factor),
            t_step=float(v["t_step"]), t_max=float(v["t_max"]), n_photons=int(v["n_photons"]),
            n_trajectories=int(v["n_trajectories"]), random_seed=int(seed),
        )
        m.simulate_diffusion()
        m.simulate_photons()
        out.append(float(m.quantum_yield) * float(tau0))
    return out
