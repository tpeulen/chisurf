import inspect
import json
import os
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from chisurf.plugins.quenching_estimator.core.av import (
    AV,
    ISOTROPIC_KAPPA2,
    RDAMeanE,
    fret_rate_pair_trace,
    fret_rate_trace,
    grid_center_index,
    simulate_walkers,
    walk_mobility,
)
from chisurf.plugins.quenching_estimator.core.ensembles import (
    decay_photons,
    ensemble_fields,
    equilibrium_lifetimes,
    normalize_ensemble,
    pde_decay,
    pde_lifetimes,
    pde_solver,
    static_photons,
    walk_segment,
)
from chisurf.plugins.quenching_estimator.core.io import write_xyz

# No Qt in this module: the desktop form lives in `quest.gui`, and a headless
# run must not pay for a GUI toolkit it never uses. Progress is reported through
# a callback (see DonorDecay.update_all), not by driving a dialog from inside
# the simulation (okf/specs/plugin-integration.md).
from chisurf.plugins.quenching_estimator.core.photon import simulate_photon_trace_rate
from chisurf.plugins.quenching_estimator.core.structure import Structure
from chisurf.plugins.quenching_estimator.core.structure.reader import read as _read_pdb

# ---------------------------------------------------------------------------
# PET chemistry -- the C++ of `IMP.bff` (``PETQuenching.h``)
#
# The reference chemistry, the quencher-atom table and the per-residue
# interaction model are general fluorescence machinery, not application logic.
# `IMP.bff` serves them from its compiled core: the functions are top-level
# (`quencher_atoms`, `pet_quenching_reference`, `standard_amino_acid_residues`,
# `amino_acid_quenching_defaults`, `normalize_amino_acid_quenching`) and the three
# tables below are built from them once. There is no `IMP.bff.quenching` module any
# more (it was removed when the model moved to C++): importing it raised
# ModuleNotFoundError and every simulation with it.
#
# Resolved on first use, never at import: `import quest.core` must not pull
# `IMP` in (okf/references/known-issues.md).
# ---------------------------------------------------------------------------

#: The dye sphere radius the reference contact distances are offset by (Angstrom), when IMP.bff does not name one.
_FALLBACK_DYE_RADIUS = 3.5

_PET = None


def _pet():
    """The PET chemistry of `IMP.bff` as one namespace, built on first use."""
    global _PET
    if _PET is None:
        import types

        import IMP.bff as bff

        _PET = types.SimpleNamespace(
            QUENCHER_ATOMS={k: tuple(v) for k, v in dict(bff.quencher_atoms()).items()},
            STANDARD_AMINO_ACID_RESIDUES=tuple(bff.standard_amino_acid_residues()),
            PET_QUENCHING_REFERENCE={
                k: {"kQ": float(v.kQ), "contact_distance": float(v.contact_distance)}
                for k, v in dict(bff.pet_quenching_reference()).items()
            },
            DEFAULT_DYE_RADIUS=getattr(bff, "DEFAULT_DYE_RADIUS", _FALLBACK_DYE_RADIUS),
            amino_acid_quenching_defaults=bff.amino_acid_quenching_defaults,
            normalize_amino_acid_quenching=bff.normalize_amino_acid_quenching,
        )
    return _PET


def __getattr__(name):
    """Resolve the moved PET tables lazily (PEP 562)."""
    moved = {
        "STANDARD_AMINO_ACID_RESIDUES": "STANDARD_AMINO_ACID_RESIDUES",
        "DEFAULT_QUENCHER_ATOMS": "QUENCHER_ATOMS",
        "REFERENCE_PET_QUENCHING": "PET_QUENCHING_REFERENCE",
        "DEFAULT_DYE_RADIUS": "DEFAULT_DYE_RADIUS",
    }
    if name in moved:
        value = getattr(_pet(), moved[name])
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def default_quencher_table():
    """Reference PET chemistry in the legacy ``quencher`` shape the GUI edits.

    ``{residue: {"atoms": [...], "kQ": float}}`` — no per-residue contact radius
    and no per-residue stickiness; those stay global on the legacy path. Derived
    from the same upstream reference chemistry as
    :func:`default_amino_acid_interactions`, so the GUI cannot simulate
    something different from the CLI.
    """
    pet = _pet()
    return OrderedDict(
        (
            residue,
            {
                "atoms": list(pet.QUENCHER_ATOMS[residue]),
                "kQ": float(reference["kQ"]),
            },
        )
        for residue, reference in pet.PET_QUENCHING_REFERENCE.items()
    )


def _interaction_to_dict(params):
    """One residue's C++ ``ResidueQuenching`` as the plain mapping a project document holds.

    ``quench_radius`` NaN (the C++ spelling of "inherit the model-wide critical distance") becomes ``None``.
    """
    radius = float(params.quench_radius)
    return {
        "slow_factor": float(params.slow_factor),
        "kQ": float(params.kQ),
        "quench_radius": None if radius != radius else radius,
        "quench_atoms": list(params.quench_atoms),
    }


def _interaction_table_to_dict(table):
    """``{residue: ResidueQuenching}`` (C++) as ``{residue: {"kQ", "slow_factor", "quench_radius", "quench_atoms"}}``.

    A project document is JSON: it must hold plain mappings, never the C++ objects (they cannot be copied or serialised).
    """
    return OrderedDict(
        (str(residue), _interaction_to_dict(params)) for residue, params in dict(table).items()
    )


def _interaction_table_from_dict(value):
    """The inverse: a (partial) mapping of plain mappings as the C++ ``ResidueQuenchingMap`` its normaliser takes.

    A residue's entry may be a mapping with any of ``kQ``, ``slow_factor``, ``quench_radius`` (None: inherit),
    ``quench_atoms``; a bare number is a slow factor (the legacy spelling saved dyes still use).
    """
    import IMP.bff as bff

    table = bff.ResidueQuenchingMap()
    for residue, entry in (value or {}).items():
        item = bff.ResidueQuenching()
        if isinstance(entry, dict):
            if entry.get("kQ") is not None:
                item.kQ = float(entry["kQ"])
            if entry.get("slow_factor") is not None:
                item.slow_factor = float(entry["slow_factor"])
            if "quench_radius" in entry:
                try:
                    item.quench_radius = float(entry["quench_radius"])
                except (
                    TypeError,
                    ValueError,
                ):  # None or text: inherit the model-wide critical distance
                    item.quench_radius = float("nan")
            if entry.get("quench_atoms") is not None:
                item.quench_atoms = tuple(entry["quench_atoms"])
        else:
            item.slow_factor = float(entry)
        table[_normalize_residue_name(residue)] = item
    return table


def default_amino_acid_interactions(kQ_scale=1.0, slow_factor=1.0, dye_radius=None):
    """A full interaction table from the reference PET chemistry, as plain mappings.

    Delegates to :func:`IMP.bff.amino_acid_quenching_defaults`.

    :param kQ_scale: dye-specific multiplier on every reference ``kQ``.
    :param slow_factor: diffusion scaling applied near every residue.
    :param dye_radius: dye sphere radius; the trajectory tracks the dye centre,
        so the reference surface contact distances are offset by it.
    """
    pet = _pet()
    if dye_radius is None:
        dye_radius = pet.DEFAULT_DYE_RADIUS
    return _interaction_table_to_dict(
        pet.amino_acid_quenching_defaults(kQ_scale, slow_factor, dye_radius)
    )


def normalize_amino_acid_interactions(value=None):
    """The full per-residue interaction table (plain mappings) with defaults filled in.

    Delegates to :func:`IMP.bff.normalize_amino_acid_quenching`.
    """
    return _interaction_table_to_dict(
        _pet().normalize_amino_acid_quenching(_interaction_table_from_dict(value))
    )


def _clamp_slow_factor(value):
    return min(1.0, max(0.0, float(value)))


def _normalize_residue_name(value):
    if isinstance(value, bytes):
        return value.decode("ascii", errors="ignore").strip().upper()
    return str(value).strip().upper()


DEFAULT_AMINO_ACID_SLOW_FACTS = None  # built on first use by the accessor below


def normalize_amino_acid_slow_facts(value=None):
    """The per-residue stickiness table, defaults filled in."""
    normalized = OrderedDict((res, 1.0) for res in _pet().STANDARD_AMINO_ACID_RESIDUES)
    if not value:
        return normalized
    for residue, factor in value.items():
        normalized[_normalize_residue_name(residue)] = _clamp_slow_factor(factor)
    return normalized


MAX_PARALLEL_TRAJECTORIES = 8


def selection2atom_idx(pdb, res_types, verbose=False):
    """
    Lookup atom-idx using residues:
     a = {'TRP': 'CA'}
     selection2atom_idx(pdb, a, all_atoms=False)
    returns all CA atoms of TRP in the PDB

    selection2atom_idx(pdb, a, all_atoms=True)
    returns all atoms of TRP in the PDB

    """
    if verbose:
        print("selection2atom_idx")
    atom_idx = OrderedDict()
    for residue_key in res_types:
        atoms = []
        for atom_name in res_types[residue_key]:
            atoms.append(
                np.where((pdb["res_name"] == residue_key) & (pdb["atom_name"] == atom_name))[0]
            )
        if len(atoms) > 0:
            atom_idx[residue_key] = np.array(np.hstack(atoms), dtype=np.uint32)
        else:
            atom_idx[residue_key] = np.array([], dtype=np.uint32)
    return atom_idx


def save_hist(filename, x, y, verbose=False):
    """
    Saves data x, y to file in histogram-format (csv). x and y
    should have the same lenght.
    :param filename: string
        Target filename
    :param x: array
    :param y: array
    :param verbose: bool
    """
    if verbose:
        print("Writing histogram to file: %s" % filename)
    fp = open(filename, "w")
    for p in zip(x, y):
        fp.write("%.3f\t%i\n" % (p[0], p[1]))
    fp.close()


def is_quenched(distance2, critical_distance, verbose=False):
    """
    square of distance to quencher
    """
    critical_distance2 = critical_distance**2
    collided = np.less(distance2, critical_distance2)
    re = collided.sum(axis=0).T
    if verbose:
        print("Determine if frame is quenched")
        nq = re.sum()
        nt = re.shape[0]
        print("Quenched frames: %s/%s, %.2f%%" % (nq, nt, float(nq) / nt * 100.0))
    return np.asarray(re, dtype=np.uint8)


def get_quencher_coordinates(pdb, quencher, verbose=True, all_atoms=True):
    """
    returns coordinates and indices of all atoms of certain
    residue type.
    pdb: is a numpy-pdb array as returned by _read_pdb
    """
    if verbose:
        print("Finding quenchers")
        print(quencher)
    atom_idx = selection2atom_idx(pdb, quencher)
    coordinates = OrderedDict()
    for res_key in quencher:
        coordinates[res_key] = pdb["coord"][atom_idx[res_key]]
    if verbose:
        print("Quencher atom-indeces: \n %s" % atom_idx)
        print("Quencher coordinates: \n %s" % coordinates)
    return coordinates


class SimulateDiffusion:
    @property
    def mean(self):
        traj = self._traj
        mean = traj.mean(axis=0)
        return mean

    @property
    def distance_to_mean(self):
        mean = self.mean
        dm = np.linalg.norm(self._traj - mean, axis=1)
        return dm

    @property
    def traj(self):
        if self.quencher is None:
            raise ValueError("Set quenching residues")
        if self._traj is None:
            raise ValueError("Run simulation first.")
        if self._critical_distance is None:
            raise ValueError("Set critical quenching distance")
        return self._traj, self._is_quenched

    @property
    def quencher_distances(self):
        if self._quencher_distances is None:
            raise ValueError("Set quencher first.")
        return self._quencher_distances

    @property
    def critical_distance(self):
        return self._critical_distance

    @critical_distance.setter
    def critical_distance(self, v):
        self._critical_distance = v
        if self._k_quench_grid_trace is not None:
            self._is_quenched = self._k_quench_grid_trace > 0.0
            return
        if not self.quencher:
            if self._traj is not None:
                self._is_quenched = np.zeros(self._traj.shape[0], dtype=bool)
            return
        self._is_quenched = is_quenched(
            self.quencher_distances, self._critical_distance, self.verbose
        )

    @property
    def quenched(self):
        if self._is_quenched is None:
            raise ValueError("Run simulation first and set critical distance")
        return self._is_quenched

    def save_trajectory(self, filename, skip):
        write_xyz(filename, (self._traj)[::skip])

    def __init__(
        self,
        av,
        quencher,
        output_file="out",
        verbose=False,
        critical_distance=None,
        trajectory_suffix="_traj.xyz",
        all_quencher_atoms=True,
    ):
        """

        :param av:
        :param quencher:
        :param output_file:
        :param verbose:
        :param critical_distance:
        :param trajectory_suffix:
        :param all_quencher_atoms:
        pdb_file: pdb-file of the structure
        """
        if verbose:
            print("")
            print("Simulate Diffusion")
            print("-----------------")
        self.av = av
        self.all_quencher_atoms = all_quencher_atoms
        #: Walkers and frames per walker of the last run (see :meth:`run`).
        self.n_walkers = 0
        self.frames_per_walker = 0

        self.pdb = av.structure.atoms
        self.verbose = verbose
        av_fast, av_slow, x0, dg = av.density_fast, av.density_slow, av.x0, av.dg
        self.dg = dg
        self.x0 = x0
        self.output_file = output_file
        self.av_fast = av_fast
        self.av_slow = av_slow
        self.t_step = None
        self._traj = None
        self._critical_distance = critical_distance

        self._quencher = None
        self._quencher_coordinates = None
        self._quencher_distances = None
        self._is_quenched = None
        self._k_quench_grid_trace = None
        self._kQ = None
        self._quencher_row_ranges = {}
        if self._has_k_quench_grid():
            self._quencher = OrderedDict()
            self._quencher_atom_indices = OrderedDict()
            self._quencher_coordinates = OrderedDict()
        elif not quencher:
            self._quencher = OrderedDict()
            self._quencher_atom_indices = OrderedDict()
            self._quencher_coordinates = OrderedDict()
            self._is_quenched = np.zeros(0, dtype=bool)
        else:
            self.quencher = quencher

        self.trajectory_suffix = trajectory_suffix

    def _has_k_quench_grid(self):
        k_quench_grid = getattr(self.av, "k_quench_grid", None)
        return k_quench_grid is not None and np.any(np.asarray(k_quench_grid) > 0.0)

    def get_quencher_distance2(self, quencher_coordinates, verbose=False):
        """Return squared atom-to-trajectory distances in Angstrom squared.

        Parameters
        ----------
        quencher_coordinates : numpy.ndarray
            Quencher atom positions, shaped ``(n_quenchers, 3)``.
        verbose : bool, optional
            Report the number of quenchers being evaluated.

        Returns
        -------
        numpy.ndarray
            ``(n_quenchers, n_frames)`` squared distances stored as float16,
            retaining the precision used by the contact-threshold calculation.
        """
        verbose = self.verbose or verbose
        m, n = self._traj.shape[0], quencher_coordinates.shape[0]
        dist = np.zeros((n, m), dtype=np.float16)
        traj = self._traj
        if verbose:
            print("")
            print("Calculating quencher distances")
            print("Total quenching atoms: %s" % n)
        for i, quencher_position in enumerate(quencher_coordinates):
            dist[i] = np.sum((traj - quencher_position) ** 2, axis=1)
        return dist

    @property
    def quencher(self):
        return self._quencher

    @quencher.setter
    def quencher(self, quencher):
        normalized_quencher = OrderedDict()
        for res_key, val in quencher.items():
            if isinstance(val, dict):
                normalized_quencher[res_key] = {
                    "atoms": list(val.get("atoms", [])),
                    "kQ": float(val.get("kQ", 2.0)),
                }
            else:
                # Legacy format: list of atoms
                normalized_quencher[res_key] = {"atoms": list(val), "kQ": 2.0}

        if self.all_quencher_atoms:
            pdb = self.pdb
            for residue_key in normalized_quencher:
                atoms_idx = np.where(pdb["res_name"] == residue_key)[0]
                all_atoms = list(set(pdb[atoms_idx]["atom_name"]))
                normalized_quencher[residue_key]["atoms"] = all_atoms

        self._quencher = normalized_quencher

        # helper dict mapping residue_key to list of atoms
        atom_mapping = OrderedDict()
        for res_key, val in self._quencher.items():
            atom_mapping[res_key] = val["atoms"]

        self._quencher_atom_indices = selection2atom_idx(self.pdb, atom_mapping)
        if self.verbose:
            print("_quencher_atom_indices")
            print(self._quencher_atom_indices)

        self._quencher_coordinates = get_quencher_coordinates(
            self.pdb, atom_mapping, verbose=self.verbose
        )
        if self.verbose:
            print("Quencher coordinates:")
            print(self._quencher_coordinates)

        start_row = 0
        self._quencher_row_ranges = {}
        for res_key, coords in self._quencher_coordinates.items():
            n_rows = coords.shape[0]
            self._quencher_row_ranges[res_key] = (start_row, start_row + n_rows)
            start_row += n_rows

    @property
    def k_quench(self):
        if self._k_quench_grid_trace is not None:
            return self._k_quench_grid_trace
        if not self.quencher and self._traj is not None:
            return np.zeros(self._traj.shape[0], dtype=np.float32)
        if self._is_quenched is None or self._quencher_distances is None:
            raise ValueError("Run simulation first and set critical distance")
        critical_distance2 = self._critical_distance**2
        collided = np.less(self._quencher_distances, critical_distance2)
        n_frames = collided.shape[1]
        k_quench = np.zeros(n_frames, dtype=np.float32)
        for res_key, (start, end) in self._quencher_row_ranges.items():
            if start == end:
                continue
            res_collided = np.any(collided[start:end, :], axis=0)
            res_kQ = self._quencher[res_key]["kQ"]
            k_quench += np.where(res_collided, res_kQ, 0.0).astype(np.float32)
        return k_quench

    def _sample_grid_at_trajectory(self, grid):
        if self._traj is None:
            raise ValueError("Run simulation first.")
        values = np.asarray(grid, dtype=np.float32)
        shape = values.shape
        # This maps Angstrom back to a voxel index; `_center_grid_indices` maps
        # the *quencher* coordinates to voxel indices when the grid is stamped.
        # The two have to be the same map, or the walk reads the quenching
        # rates from beside where they were written. It used the float corner
        # `(n - 1) / 2` until 2026-07-28, which differs from the kernels'
        # integer offset on every even edge length -- see
        # `quest.core.av.grid_center_index`.
        center_index = np.array([grid_center_index(n) for n in shape], dtype=np.float64)
        # `floor`, not `trunc`: `trunc` maps [-1, 0) to 0, so a position up to
        # one voxel *below* the grid was treated as inside it and read voxel 0's
        # quenching rate. `floor` sends it to -1, which the bounds check below
        # then rejects.
        indices = np.floor((self._traj - self.x0) / float(self.dg) + center_index).astype(np.int64)
        inside = np.ones(indices.shape[0], dtype=bool)
        for axis, size in enumerate(shape):
            inside &= (indices[:, axis] >= 0) & (indices[:, axis] < size)
        out = np.zeros(indices.shape[0], dtype=np.float32)
        if np.any(inside):
            out[inside] = values[tuple(indices[inside].T)]
        return out

    @property
    def kQ(self):
        return self._kQ

    @staticmethod
    def _resolve_parallel_trajectories(parallel_trajectories):
        requested = -1 if parallel_trajectories is None else int(parallel_trajectories)
        if requested == -1:
            return max(1, min(os.cpu_count() or 1, MAX_PARALLEL_TRAJECTORIES))
        return max(1, min(requested, MAX_PARALLEL_TRAJECTORIES))

    @property
    def quencher_coordinates(self):
        return np.vstack(list(self._quencher_coordinates.values()))

    @property
    def quencher_atom_indices(self):
        return self._quencher_atom_indeces

    @quencher_atom_indices.setter
    def quencher_atom_indices(self, atom_indices):
        if not isinstance(atom_indices, list):
            raise ValueError("Quencher indeces have to be a list of integers")
        atom_indices = np.array(self._quencher_atom_indices, dtype=np.uint32)
        self._quencher_atom_indeces = atom_indices

    def run(
        self,
        D=40.0,
        slow_fact=0.01,
        t_step=0.002,
        t_max=10000,
        save_traj=False,
        save_j=50,
        verbose=True,
        random_seed=None,
        parallel_trajectories=-1,
        t_walk=None,
        **kwargs,
    ):
        """Walk the dye from its equilibrium occupancy (:func:`.av.simulate_walkers`).

        :param D: float
            diffusion coefficient of dye in Ang**2/ns
        :param slow_fact: float or ``(ng, ng, ng)`` array
            Mobility scaling: a scalar inside the slow (contact) volume, or the per-voxel
            field (:func:`.av.walk_mobility`). Its inverse is the walk's equilibrium and
            the walkers' start distribution.
        :param t_step: float
            The time-step of the simulation in nano-seconds
        :param t_max: float
            Simulated time per trajectory block, in nano-seconds; the run covers
            ``parallel_trajectories * t_max`` in all.
        :param save_traj: bool
            If True the trajectory is saved to self.output_file+'_traj.xyz'. Default value True
        :param save_j: int
            Only every save_j frame of the trajectory is saved.
        :param verbose:
        :param random_seed:
            Optional seed for deterministic trajectory diagnostics.
        :param parallel_trajectories:
            Number of ``t_max`` blocks. Use -1 for all CPU cores, capped at 8 (the walkers
            are vectorised, so this sets the simulated time, not threads).
        :param t_walk:
            Length of one walker, ns; ``None`` is ``t_max`` (one walker per block). The
            blocks are cut into ``round(t_max / t_walk)`` independent walkers, each started
            from the equilibrium occupancy, concatenated walker after walker.
        """
        verbose = verbose or self.verbose
        self.t_step = t_step
        dg = self.dg
        density, slow_density = self.av_fast, self.av_slow
        n_blocks = self._resolve_parallel_trajectories(parallel_trajectories)
        t_walk = float(t_max) if t_walk is None else min(float(t_max), float(t_walk))
        per_block = max(1, int(round(float(t_max) / t_walk))) if t_walk > 0 else 1
        n_walkers = n_blocks * per_block
        if verbose:
            print("Simulate dye-trajectory")
            print("Simulation time [us]: %.2f" % (n_blocks * t_max / 1000))
            print("Time-step [ps]: %.2f" % (t_step * 1000))
            print("Walkers: %i x %.1f ns" % (n_walkers, t_walk))
            print("AV-grid parameter [Ang]: %.2f" % dg)
            print("Diff coeff. [Ang/ns2]: %.2f" % D)
            print("------")
        start = time.process_time()
        mobility = walk_mobility(density, slow_density, slow_fact)
        traj, n_steps, n_accepted, n_rejected = simulate_walkers(
            density, mobility, dg, t_walk, t_step, D, n_walkers=n_walkers,
            random_seed=random_seed,
        )
        if traj.shape[0] == 0:
            self._traj = None
            return
        self.n_walkers = n_walkers
        self.frames_per_walker = int(n_steps)
        traj += self.x0
        self._traj = traj
        k_quench_grid = getattr(self.av, "k_quench_grid", None)
        if self._has_k_quench_grid():
            self._k_quench_grid_trace = self._sample_grid_at_trajectory(k_quench_grid)
            self._is_quenched = self._k_quench_grid_trace > 0.0

        if verbose:
            print("Accepted steps: %i" % n_accepted)
            print("Rejected steps: %i" % n_rejected)
        end = time.process_time()
        if verbose:
            print("time spent: %.2gs" % (end - start))
            print("n_accepted: %s" % n_accepted)
            print("-----------------------")
            print("Attachment point: %s" % self.x0)
            print("Mean dye-position: %s" % self.mean)

        if save_traj:
            self.save_trajectory(self.output_file + self.trajectory_suffix, save_j)
        if not self._has_k_quench_grid():
            if self.quencher:
                self._quencher_distances = self.get_quencher_distance2(
                    self.quencher_coordinates, verbose
                )
            else:
                self._is_quenched = np.zeros(self._traj.shape[0], dtype=bool)
        if verbose:
            print("Quencher distances:")
            if self._quencher_distances is not None:
                print("Quencher distances shape: %s, %s" % self._quencher_distances.shape)
                print(self._quencher_distances)


class DonorDecay:
    def __init__(
        self,
        tau0=None,
        kQ=1.0,
        nph=0,
        verbose=False,
        auto_update=False,
        pdb=None,
        attachment_residue=None,
        attachment_atom=None,
        attachment_chain=None,
        dg=None,
        sticky_mode="quencher",
        save_avs=True,
        D=None,
        slow_fact=0.05,
        critical_distance=None,
        output_file="out",
        av_parameter=None,
        quencher={"TRP": ["CB"], "TYR": ["CB"], "HIS": ["CB"]},
        t_max=10000.0,
        t_step=0.004,
        slow_radius=10.0,
        all_quencher_atoms=True,
        stickiness_mode="global",
        amino_acid_slow_facts=None,
        amino_acid_interactions=None,
        random_seed=None,
        parallel_trajectories=-1,
        coarse_grained=False,
        acceptor_D=None,
        acceptor_slow_fact=None,
        acceptor_slow_radius=None,
        acceptor_amino_acid_interactions=None,
        acceptor_dynamics="trajectory",
        ensemble=None,
    ):
        """
        quenching trajectory as calculated by SimulateDiffusion.quenched
        :param tau0: float
        :param kQ: float
        :param nph:
        :param verbose: bool
        :param auto_update:
        :param pdb:
        :param attachment_residue: string
        :param attachment_atom: int
        :param attachment_chain: string
        :param dg: float
        :param sticky_mode:
        :param save_avs: bool
        :param D: float
        :param slow_fact: float
        :param critical_distance: float
        :param output_file: string
        :param av_parameter:
        :param quencher:
        :param t_max: float
        :param t_step: float
        :param slow_radius: float
        :param all_quencher_atoms:
        :param stickiness_mode:
        :param amino_acid_slow_facts:
        :param amino_acid_interactions:
        :param random_seed:
            Optional seed for deterministic trajectory diagnostics.
        :param parallel_trajectories:
            Number of independent diffusion trajectories to run and combine
            before photon sampling. Use -1 for all CPU cores, capped at 8.
        :param coarse_grained: bool
            Reduce the structure to backbone plus CB before simulating, with CB
            moved to the side-chain centre of mass. This shrinks the atom count
            used for the accessible volume considerably. Note that side-chain
            atoms are then absent, so every residue's quenching centre falls
            back to its CB - which, sitting at the side-chain centre of mass, is
            a reasonable stand-in for the redox-active moiety.
        :param ensemble: str
            ``"walk"`` (default), ``"equilibrium"`` or ``"pde"``: where the dye sits during
            the excited state (:mod:`.ensembles`). Only the walk simulates FRET.
        """
        self.verbose = verbose
        self.ensemble = normalize_ensemble(ensemble)
        #: :class:`.ensembles.EnsembleLifetimes` of the last equilibrium/PDE solve.
        self.ensemble_lifetimes = None
        self._ensemble_fields = None
        self._av = None
        self._diffusion = None
        self.tau0 = tau0
        self.n_photons = nph
        self.kQ = kQ
        self.auto_update = auto_update
        self._photon_trace = None
        self._pdb = pdb
        self.attachment_residue = attachment_residue
        self.attachment_atom = attachment_atom
        self.attachment_chain = attachment_chain
        self.diffusion_coefficient = D
        self.slow_fact = _clamp_slow_factor(slow_fact)
        # Unset grid and AV parameters are IMP.bff's declared defaults (they
        # were 0.5 A and 20/0.5/5.0 here, guesses of this class's own).
        if dg is None or av_parameter is None:
            from chisurf.plugins.quenching_estimator.core.av import av1_parameter, av_defaults

            if dg is None:
                dg = av_defaults()["simulation_grid_resolution"]
            if av_parameter is None:
                av_parameter = av1_parameter()
        self.dg = dg
        self.save_avs = save_avs
        self.critical_distance = critical_distance
        self.output_file = output_file
        self.av_parameter = av_parameter
        self.quencher = quencher
        self.t_max = t_max
        self.t_step = t_step
        self.sticky_mode = sticky_mode
        self.slow_radius = slow_radius
        self.all_quencher_atoms = all_quencher_atoms
        self.stickiness_mode = stickiness_mode
        self.amino_acid_slow_facts = normalize_amino_acid_slow_facts(amino_acid_slow_facts)

        # The acceptor is a *different dye*: its own diffusion coefficient, its
        # own stickiness radius and its own per-residue interaction table. A
        # cyanine and a rhodamine do not stick to the same residues to the same
        # degree, and modelling them with one table was silently wrong. Each
        # falls back to the donor's value, so a project that says nothing about
        # the acceptor behaves as it did before.
        self.acceptor_diffusion_coefficient = acceptor_D
        self.acceptor_slow_fact = acceptor_slow_fact
        self.acceptor_slow_radius = acceptor_slow_radius
        self.acceptor_amino_acid_interactions = (
            normalize_amino_acid_interactions(acceptor_amino_acid_interactions)
            if acceptor_amino_acid_interactions is not None
            else None
        )
        #: ``"trajectory"`` simulates the acceptor's walk and pairs it with the
        #: donor's frame by frame; ``"averaged"`` is the fast-acceptor limit,
        #: averaging over its static cloud.
        self.acceptor_dynamics = acceptor_dynamics
        self._acceptor_diffusion = None
        self.amino_acid_interactions = normalize_amino_acid_interactions(amino_acid_interactions)
        self.random_seed = random_seed
        self.parallel_trajectories = int(
            -1 if parallel_trajectories is None else parallel_trajectories
        )
        self.coarse_grained = bool(coarse_grained)
        self._structure = None
        self._residue_site_cache = None
        self.fret_enabled = False
        self.fret_R0 = None
        self.fret_kappa2_value = None
        self.acceptor_chain = None
        self.acceptor_residue = None
        self.acceptor_atom = None
        self.fret_av_parameter = None
        self._acceptor_av = None
        self._photon_trace_fret = None

    def __str__(self):
        s = ""
        return s

    @property
    def quantum_yield(self):
        dt, n = self.photon_trace
        n_ph = self.n_photons
        if n_ph <= 0:
            # The GUI spin box counts photons in millions, so a user can ask for
            # 0.00 M. That is an empty simulation, not a crash.
            return 0.0
        n_f = n.sum()
        return float(n_f) / n_ph

    @property
    def diffusion(self):
        """The donor's walk, simulated on first use; ``None`` for the non-walk ensembles."""
        if self._diffusion is None and self.ensemble == "walk":
            self.simulate_diffusion()
        return self._diffusion

    @property
    def walk_segment(self):
        """Length of one walker, ns (:func:`.ensembles.walk_segment`)."""
        if not self.tau0:
            return None
        n_blocks = SimulateDiffusion._resolve_parallel_trajectories(self.parallel_trajectories)
        return walk_segment(self.tau0, self.t_max, n_blocks)

    def _walk_mobility(self, av, slow_fact):
        """The mobility field the walk runs on (and the ensembles read its inverse from)."""
        if self.stickiness_mode == "amino_acid":
            grid = getattr(av, "slow_factor_grid", None)
            if grid is not None:
                slow_fact = grid
        return walk_mobility(av.density_fast, av.density_slow, slow_fact)

    @property
    def ensemble_fields(self):
        """:class:`.ensembles.EnsembleFields` of the donor's volume, built on first use."""
        if self._ensemble_fields is None:
            av = self.av
            self._ensemble_fields = ensemble_fields(
                av.density_fast,
                self._walk_mobility(av, self.slow_fact),
                getattr(av, "k_quench_grid", None),
                av.dg,
                self.diffusion_coefficient,
            )
        return self._ensemble_fields

    def solve_ensemble(self, verbose=False):
        """The ``"equilibrium"`` / ``"pde"`` donor: lifetimes, then a photon trace.

        The photon trace has the walk's shape (delay, emitted), so the histogram, the
        quantum yield and the mean arrival time downstream read it unchanged.
        """
        if self.ensemble == "walk":
            raise ValueError("solve_ensemble is the equilibrium/pde path; the walk walks")
        f = self.ensemble_fields
        if self.ensemble == "equilibrium":
            self.ensemble_lifetimes = equilibrium_lifetimes(f, self.tau0)
            self._photon_trace = static_photons(f, self.tau0, self.n_photons, self._photon_seed())
        else:
            solver = pde_solver(f)
            self.ensemble_lifetimes = pde_lifetimes(f, self.tau0, solver)
            t, intensity = pde_decay(f, self.tau0, solver)
            self._photon_trace = decay_photons(
                t, intensity, self.ensemble_lifetimes.quantum_yield, self.n_photons,
                self._photon_seed(),
            )
        if verbose or self.verbose:
            print("Ensemble %s: %s" % (self.ensemble, self.ensemble_lifetimes.as_dict()))
        return self.ensemble_lifetimes

    def ensemble_sample(self, n=20000):
        """``n`` dye positions drawn from the equilibrium occupancy, Angstrom.

        Same convention as a walk frame (a uniform point inside a voxel drawn from ``w``);
        it is one-step walkers, so the two cannot disagree on where a voxel is.
        """
        av = self.av
        mobility = self._walk_mobility(av, self.slow_fact)
        xyz, _, _, _ = simulate_walkers(
            av.density_fast, mobility, av.dg, 1.0, 1.0, 0.0, n_walkers=int(n),
            random_seed=self.random_seed,
        )
        return xyz + av.x0

    @property
    def slow_center(self):
        coordinates, _residue_names = self.slow_center_data
        return coordinates

    @property
    def slow_center_data(self):
        slow_centers, _quench_centers, residue_names = self.residue_site_data
        return slow_centers, residue_names

    @property
    def quench_center_data(self):
        _slow_centers, quench_centers, residue_names = self.residue_site_data
        return quench_centers, residue_names

    @property
    def residue_site_data(self):
        """Return ``(slow_centers, quench_centers, residue_names)`` per residue.

        The *slow* centre is the coarse side-chain position (CB, else CA) that
        drives the unspecific stickiness model. The *quench* centre is the
        centroid of the residue's PET-active atoms (see
        ``DEFAULT_QUENCHER_ATOMS`` and the per-residue ``quench_atoms``
        override), so quenching is evaluated at the reactive moiety rather than
        at CB.
        """
        cached = getattr(self, "_residue_site_cache", None)
        cache_key = (id(self._structure), self._quench_atoms_cache_key())
        if cached is not None and cached[0] == cache_key:
            return cached[1]

        atoms = self.structure.atoms
        residue_keys = OrderedDict()
        for idx, atom in enumerate(atoms):
            key = (
                _normalize_residue_name(atom["chain"]),
                int(atom["res_id"]),
                _normalize_residue_name(atom["res_name"]),
            )
            residue_keys.setdefault(key, []).append(idx)

        slow_centers = []
        quench_centers = []
        residue_names = []
        for (_chain, _res_id, res_name), indices in residue_keys.items():
            block = atoms[np.asarray(indices, dtype=np.int64)]
            atom_names = [_normalize_residue_name(name) for name in block["atom_name"]]
            coords = np.asarray(block["coord"], dtype=np.float64)
            residue_name = _normalize_residue_name(res_name)

            if "CB" in atom_names:
                selected = atom_names.index("CB")
            elif "CA" in atom_names:
                selected = atom_names.index("CA")
            else:
                selected = 0
            slow_center = coords[selected]

            wanted = self._quench_atoms_for_residue(residue_name)
            matched = [i for i, name in enumerate(atom_names) if name in wanted]
            quench_center = coords[matched].mean(axis=0) if matched else slow_center

            slow_centers.append(slow_center)
            quench_centers.append(quench_center)
            residue_names.append(residue_name)

        result = (
            np.asarray(slow_centers, dtype=np.float64),
            np.asarray(quench_centers, dtype=np.float64),
            residue_names,
        )
        self._residue_site_cache = (cache_key, result)
        return result

    def _quench_atoms_cache_key(self):
        return tuple(
            (residue, tuple(params.get("quench_atoms") or ()))
            for residue, params in self.amino_acid_interactions.items()
        )

    def _quench_atoms_for_residue(self, residue_name):
        params = self.amino_acid_interactions.get(_normalize_residue_name(residue_name))
        if params is None:
            return frozenset(_pet().QUENCHER_ATOMS.get(residue_name, ("CB",)))
        return frozenset(params.get("quench_atoms") or ("CB",))

    @property
    def slow_center_slow_fact(self):
        _coordinates, residue_names = self.slow_center_data
        return self._slow_facts_for_residue_names(residue_names)

    _INTERACTION_FALLBACK = {
        "slow_factor": 1.0,
        "kQ": 0.0,
        "quench_radius": None,
        "quench_atoms": ("CB",),
    }

    def _interaction_for_residue(self, residue_name, interactions=None):
        table = self.amino_acid_interactions if interactions is None else interactions
        return table.get(_normalize_residue_name(residue_name), self._INTERACTION_FALLBACK)

    @property
    def acceptor_interactions(self):
        """The acceptor's interaction table, defaulting to the donor's.

        A project that never mentions the acceptor's chemistry gets the donor's,
        which is what QuEst always did — but the two are now separable, because
        different dyes stick to different residues by different amounts.
        """
        if self.acceptor_amino_acid_interactions is not None:
            return self.acceptor_amino_acid_interactions
        return self.amino_acid_interactions

    @property
    def acceptor_slow_radius_value(self):
        if self.acceptor_slow_radius is not None:
            return float(self.acceptor_slow_radius)
        return float(self.slow_radius)

    @property
    def acceptor_diffusion_coefficient_value(self):
        if self.acceptor_diffusion_coefficient is not None:
            return float(self.acceptor_diffusion_coefficient)
        return float(self.diffusion_coefficient)

    @property
    def acceptor_slow_fact_value(self):
        if self.acceptor_slow_fact is not None:
            return _clamp_slow_factor(self.acceptor_slow_fact)
        return self.slow_fact

    def _slow_facts_for_residue_names(self, residue_names, interactions=None):
        return np.asarray(
            [
                self._interaction_for_residue(res, interactions)["slow_factor"]
                for res in residue_names
            ],
            dtype=np.float64,
        )

    def _kq_for_residue_names(self, residue_names):
        return np.asarray(
            [self._interaction_for_residue(res)["kQ"] for res in residue_names],
            dtype=np.float64,
        )

    def _quench_radii_for_residue_names(self, residue_names):
        """Per-residue contact radius, falling back to the global critical distance."""
        default_radius = float(self.critical_distance or 0.0)
        return np.asarray(
            [
                (
                    default_radius
                    if self._interaction_for_residue(res).get("quench_radius") is None
                    else float(self._interaction_for_residue(res)["quench_radius"])
                )
                for res in residue_names
            ],
            dtype=np.float64,
        )

    @property
    def k_quench(self):
        return self.diffusion.k_quench

    def _calc_slow_av(self, verbose=False):
        """Build the stickiness and quenching grids for the current AV."""
        slow_centers, quench_centers, residue_names = self.residue_site_data
        self._av.calc_slow_av(
            save=self.save_avs,
            slow_centers=slow_centers,
            slow_radius=self.slow_radius,
            verbose=verbose or self.verbose,
            slow_fact=self._slow_facts_for_residue_names(residue_names),
            quench_centers=quench_centers,
            quench_radius=self._quench_radii_for_residue_names(residue_names),
            k_quench=self._kq_for_residue_names(residue_names),
        )

    @property
    def av(self):
        if self._av is None:
            self.calc_av()
            self._calc_slow_av()
        return self._av

    @property
    def photon_trace(self):
        if self._photon_trace is None:
            if self.ensemble == "walk":
                self.calc_photons()
            else:
                self.solve_ensemble()
        return self._photon_trace

    @property
    def collisions(self):
        """Share of the ensemble in contact with a quencher (walk: of the frames)."""
        if self.ensemble != "walk":
            if self.ensemble_lifetimes is None:
                self.solve_ensemble()
            return float(self.ensemble_lifetimes.contact_fraction)
        return float(self.diffusion.quenched.sum()) / self.diffusion.quenched.shape[0]

    @property
    def structure(self):
        return self._structure

    @structure.setter
    def structure(self, v):
        # Accept a path or an already-parsed Structure: the GUI parses once and
        # hands the same object to every model it builds, and parsing 1500 atoms
        # again per run is pure cost.
        # auto_update=False: QuEst never edits torsion angles, so the internal
        # coordinate build is pure overhead.
        self._structure = (
            v
            if isinstance(v, Structure)
            else Structure(v, make_coarse=self.coarse_grained, auto_update=False)
        )
        self._residue_site_cache = None
        tf = tempfile.NamedTemporaryFile(suffix=".pdb")
        self._tmp_file = tf.name
        tf.close()
        self._structure.write(self._tmp_file)

    def calc_av(self, verbose=False):
        verbose = verbose or self.verbose
        dg = self.dg
        residue = self.attachment_residue
        attachment_atom = self.attachment_atom
        chain = self.attachment_chain
        structure = self.structure
        av = AV(
            structure,
            residue_seq_number=residue,
            atom_name=attachment_atom,
            chain_identifier=chain,
            simulation_grid_resolution=dg,
            save_av=self.save_avs,
            verbose=verbose,
            output_file=self.output_file,
            **self.av_parameter,
        )
        self._av = av

    def simulate_diffusion(self, verbose=False, plot_traj=False):
        all_quencher_atoms = self.all_quencher_atoms
        verbose = verbose or self.verbose
        av = self.av
        D = self.diffusion_coefficient
        slow_fact = self._walk_mobility(av, self.slow_fact)
        diffusion = SimulateDiffusion(
            av, quencher=self.quencher, verbose=verbose, all_quencher_atoms=all_quencher_atoms
        )
        diffusion.run(
            D=D,
            verbose=verbose,
            slow_fact=slow_fact,
            t_max=self.t_max,
            t_step=self.t_step,
            random_seed=self.random_seed,
            parallel_trajectories=self.parallel_trajectories,
            t_walk=self.walk_segment,
        )
        self._diffusion = diffusion
        success = diffusion._traj is not None
        return success

    def _photon_seed(self):
        """Seed for the photon trace, derived from but distinct from the walk's.

        Returns ``None`` when the project sets no ``random_seed``, which keeps
        the faster multi-threaded photon kernel in play. Offsetting the base
        seed stops the photon trace from replaying the same draw sequence as
        the diffusion trajectory it is scored against.
        """
        if getattr(self, "random_seed", None) is None:
            return None
        return int((int(self.random_seed) + 7919) % ((2**31) - 1))

    def calc_photons(self, verbose=False, donor_traj=None, kQ=None):
        """
        `n_ph`: number of generated photons
        `pq`: quenching probability if distance of fluorphore is below the `critical_distance`
        """
        verbose = verbose or self.verbose
        n_photons = self.n_photons
        tau0 = self.tau0
        if donor_traj is None:
            donor_traj = self.diffusion

        k_quench = donor_traj.k_quench

        if verbose:
            print("")
            print("Simulating decay:")
            print("----------------")
            print("Number of excitation photons: %s" % n_photons)
            print("Number of frames    : %s" % k_quench.shape[0])
            print("Quencher-wise kQ rates used.")

        t_step = donor_traj.t_step
        dts, phs = simulate_photon_trace_rate(
            n_ph=n_photons,
            kQ=k_quench,
            t_step=t_step,
            tau0=tau0,
            random_seed=self._photon_seed(),
        )

        n_photons = phs.shape[0]
        n_f = phs.sum()
        if verbose or self.verbose:
            print("Number of absorbed photons: %s" % (n_photons))
            print("Number of fluorescent photons: %s" % (n_f))
            print("Quantum yield: %.2f" % (float(n_f) / n_photons))
        self._photon_trace = dts, phs

    def get_histogram(self, nbins=4096, range=(0, 50)):
        """Decay histogram of the donor photons that were actually emitted.

        Only photons flagged as fluorescent enter the histogram. A photon lost
        to quenching comes back from ``_photon_rate_walk`` as ``dt = 0.0``, so
        histogramming the whole trace piles every non-emitted photon into the
        first bin -- a spike of photons that were never emitted, and a curve
        whose total is the excitation count rather than ``QY x N``.

        Parameters
        ----------
        nbins : int
            Number of histogram bins.
        range : tuple of float
            ``(t_min, t_max)`` of the time axis, in nanoseconds.

        Returns
        -------
        x : numpy.ndarray
            Bin edges, ``nbins + 1`` long.
        y : numpy.ndarray
            Counts per bin.
        """
        dts, nph = self.photon_trace
        y, x = np.histogram(dts[nph == 1], range=range, bins=nbins)
        return x, y

    def save_histogram(self, filename="hist.txt", verbose=False, nbins=4096, range=(0, 50)):
        verbose = verbose or self.verbose
        (
            x,
            y,
        ) = self.get_histogram(nbins, range)
        save_hist(filename, x, y, verbose)

    def calc_acceptor_av(self, verbose=False):
        verbose = verbose or self.verbose
        if self._structure is None:
            return None
        residue = self.acceptor_residue
        atom = self.acceptor_atom
        chain = self.acceptor_chain
        if residue is None or atom is None:
            return None
        params = self.fret_av_parameter if self.fret_av_parameter is not None else self.av_parameter
        try:
            av = AV(
                self.structure,
                residue_seq_number=residue,
                atom_name=atom,
                chain_identifier=chain,
                simulation_grid_resolution=self.dg,
                save_av=self.save_avs,
                verbose=verbose,
                output_file=self.output_file + "_A",
                **params,
            )
        except ValueError as error:
            # Say which dye is at fault. A scan moves the donor from site to
            # site but leaves the acceptor where the project put it, so a stale
            # acceptor makes every single site fail for a reason that looks
            # like it is about the site being scanned.
            raise ValueError("Acceptor dye: %s" % error) from error
        # Stickiness from the *acceptor's* table and radius, not the donor's.
        # This used to pass `self.slow_center` / `self.slow_radius`, so the
        # acceptor inherited the donor's adhesion whatever dye it was.
        slow_centers, _quench_centers, residue_names = self.residue_site_data
        av.calc_slow_av(
            save=self.save_avs,
            slow_centers=slow_centers,
            slow_radius=self.acceptor_slow_radius_value,
            verbose=verbose,
            slow_fact=self._slow_facts_for_residue_names(residue_names, self.acceptor_interactions),
        )
        self._acceptor_av = av
        self._acceptor_diffusion = None  # its walk belongs to this volume
        return av

    @property
    def acceptor_av(self):
        if self._acceptor_av is None:
            self.calc_acceptor_av()
        return self._acceptor_av

    @property
    def acceptor_diffusion(self):
        """The acceptor's Brownian walk, simulated on first use."""
        if self._acceptor_diffusion is None:
            self.simulate_acceptor_diffusion()
        return self._acceptor_diffusion

    def simulate_acceptor_diffusion(self, verbose=False):
        """Walk the acceptor through its own accessible volume.

        Same machinery as the donor, with the acceptor's diffusion coefficient
        and stickiness — but no quenching: the acceptor's own PET quenching
        would change how bright *it* is, and QuEst reports the donor's decay.
        What the FRET rate needs from this is positions.

        The two walks must share a time base to be paired frame by frame, so
        `t_max` and `t_step` are the project's, not per dye. The seed is offset
        from the donor's: two dyes driven by the same random stream would move
        in lockstep, which is not two independent walks.
        """
        verbose = verbose or self.verbose
        av = self.acceptor_av
        if av is None:
            raise ValueError(
                "FRET is enabled but the acceptor dye is not defined: set its "
                "chain, residue and atom (fret.dyes[1].attachment)."
            )

        slow_fact = self._walk_mobility(av, self.acceptor_slow_fact_value)

        seed = self.random_seed
        if seed is not None:
            seed = int((int(seed) + 104729) % ((2**31) - 1))

        diffusion = SimulateDiffusion(
            av, quencher={}, verbose=verbose, all_quencher_atoms=self.all_quencher_atoms
        )
        diffusion.run(
            D=self.acceptor_diffusion_coefficient_value,
            verbose=verbose,
            slow_fact=slow_fact,
            t_max=self.t_max,
            t_step=self.t_step,
            random_seed=seed,
            parallel_trajectories=self.parallel_trajectories,
            t_walk=self.walk_segment,
        )
        self._acceptor_diffusion = diffusion
        return diffusion._traj is not None

    @property
    def fret_R0_angstrom(self):
        """Forster radius in Angstrom, falling back to a typical xanthene pair."""
        return float(self.fret_R0) if self.fret_R0 is not None else 52.0

    @property
    def fret_kappa2(self):
        """Orientation factor, defaulting to the isotropic dynamic average 2/3.

        **This is an assumption, not a model.** QuEst's dye is a structureless
        point in a volume and has no transition dipole to orient, so kappa2
        cannot be computed here -- it is stated. Making it a parameter is what
        closes OBJ-01 item 6 ("no orientation factor is *chosen or documented*")
        without pretending the physics is simulated; see
        `quest.core.av._kappa2_scale`.

        The default reproduces every number computed before it existed, because
        a published R0 is already quoted at kappa2 = 2/3.
        """
        return ISOTROPIC_KAPPA2 if self.fret_kappa2_value is None else float(self.fret_kappa2_value)

    def rda_mean_e(self, n_samples=50000):
        """Forster-averaged donor-acceptor distance <R_DA>_E, in Angstrom.

        A diagnostic over the two static clouds -- what a FRET-efficiency
        measurement reports as a distance. The simulation itself does not use
        it: the decay comes from the per-frame rate in
        :meth:`calc_fret_rate_trace`.
        """
        acceptor_av = (
            self._acceptor_av if self._acceptor_av is not None else self.calc_acceptor_av()
        )
        if acceptor_av is None:
            return None
        return float(RDAMeanE(self.av, acceptor_av, self.fret_R0_angstrom, n_samples))

    def calc_fret_rate_trace(self, verbose=False):
        """FRET rate for every frame, in 1/ns.

        Two regimes, chosen by :attr:`acceptor_dynamics`:

        ``"trajectory"`` (default)
            Both dyes diffuse and stick, each with its own diffusion
            coefficient and interaction table, and the rate uses their
            instantaneous separation::

                k_FRET(t) = (1/tau0) * (R0 / |r_D(t) - r_A(t)|)^6

        ``"averaged"``
            The acceptor is averaged over its accessible volume — the
            *fast-acceptor limit*, valid when it explores that volume quickly
            compared with the donor's excited-state lifetime, and wrong when it
            is immobilised.

        The two are not interchangeable: ``<(R0/r)^6>`` over a cloud is not
        ``(R0/<r>)^6``, and averaging first weights close approaches heavily.
        """
        verbose = verbose or self.verbose
        acceptor_av = (
            self._acceptor_av
            if self._acceptor_av is not None
            else self.calc_acceptor_av(verbose=verbose)
        )
        if acceptor_av is None:
            raise ValueError(
                "FRET is enabled but the acceptor dye is not defined: set its "
                "chain, residue and atom (fret.dyes[1].attachment)."
            )

        trajectory = getattr(self.diffusion, "_traj", None)
        if trajectory is None:
            raise ValueError("Run the diffusion simulation before computing FRET rates.")

        # Both dyes are *centres*, so the closest physical approach is the sum
        # of the two radii — two spheres cannot interpenetrate, and (R0/r)^6
        # diverges if they are allowed to.
        donor_radius = float((self.av_parameter or {}).get("radius1", _pet().DEFAULT_DYE_RADIUS))
        acceptor_params = (
            self.fret_av_parameter if self.fret_av_parameter is not None else self.av_parameter
        )
        acceptor_radius = float((acceptor_params or {}).get("radius1", _pet().DEFAULT_DYE_RADIUS))
        r_min = donor_radius + acceptor_radius

        if str(self.acceptor_dynamics).lower() == "averaged":
            rates = fret_rate_trace(
                trajectory,
                acceptor_av.points,
                R0=self.fret_R0_angstrom,
                tau0=self.tau0,
                r_min=r_min,
                kappa2=self.fret_kappa2,
            )
        else:
            acceptor_trajectory = getattr(self.acceptor_diffusion, "_traj", None)
            if acceptor_trajectory is None:
                raise ValueError(
                    "The acceptor trajectory could not be simulated; set "
                    "fret.acceptor_dynamics to 'averaged' to use its accessible "
                    "volume instead."
                )
            rates = fret_rate_pair_trace(
                trajectory,
                acceptor_trajectory,
                R0=self.fret_R0_angstrom,
                tau0=self.tau0,
                r_min=r_min,
                kappa2=self.fret_kappa2,
            )
        if verbose:
            print("FRET rate: mean %.4f 1/ns over %i frames" % (rates.mean(), rates.shape[0]))
        return rates

    def calc_photons_fret(self, verbose=False):
        verbose = verbose or self.verbose
        if not getattr(self, "fret_enabled", False):
            self._photon_trace_fret = None
            return
        k_fret = self.calc_fret_rate_trace(verbose=verbose)
        donor_traj = self.diffusion
        k_quench = donor_traj.k_quench
        t_step = donor_traj.t_step
        n_photons = self.n_photons
        # Quenching and transfer are parallel de-excitation channels, so their
        # rates add frame by frame.
        k_total = (np.asarray(k_quench, dtype=np.float64) + k_fret).astype(np.float32)
        dts, phs = simulate_photon_trace_rate(
            n_ph=n_photons,
            kQ=k_total,
            t_step=t_step,
            tau0=self.tau0,
            random_seed=self._photon_seed(),
        )
        self._photon_trace_fret = dts, phs

    @property
    def photon_trace_fret(self):
        if self._photon_trace_fret is None:
            self.calc_photons_fret()
        return self._photon_trace_fret

    @property
    def quantum_yield_fret(self):
        if self._photon_trace_fret is None:
            self.calc_photons_fret()
        if self._photon_trace_fret is None:
            return 0.0
        dt, n = self._photon_trace_fret
        n_ph = self.n_photons
        if n_ph <= 0:
            return 0.0
        n_f = n.sum()
        return float(n_f) / n_ph

    @property
    def fret_efficiency(self):
        """Transfer efficiency from the two simulated decays: 1 - QY_DA/QY_D.

        One definition, deliberately. There used to be a second -- analytic,
        from <R_DA>_E over the static clouds -- which ignored quenching and
        silently took precedence over this one whenever it had been computed.
        The two disagreed, and only this one reflects what the simulation
        actually produced.
        """
        qy_d = self.quantum_yield
        qy_da = self.quantum_yield_fret
        if qy_d <= 0:
            return 0.0
        return max(0.0, 1.0 - qy_da / qy_d)

    def get_histogram_fret(self, nbins=4096, range=(0, 50)):
        """Decay histogram of the D--A photons that were actually emitted.

        Same rule as :meth:`get_histogram`: quenched *and* transferred photons
        come back with ``dt = 0.0``, so only the fluorescent ones are counted.
        Here it matters more -- the non-emitted fraction is ``1 - QY_DA``, so
        an unfiltered curve buries the transfer efficiency under a first-bin
        spike and totals the excitation count whatever the transfer.

        Parameters
        ----------
        nbins : int
            Number of histogram bins.
        range : tuple of float
            ``(t_min, t_max)`` of the time axis, in nanoseconds.

        Returns
        -------
        x : numpy.ndarray or None
            Bin edges, or ``None`` when no D--A trace could be simulated.
        y : numpy.ndarray or None
            Counts per bin, or ``None``.
        """
        if self._photon_trace_fret is None:
            self.calc_photons_fret()
        if self._photon_trace_fret is None:
            return None, None
        dts, nph = self._photon_trace_fret
        y, x = np.histogram(dts[nph == 1], range=range, bins=nbins)
        return x, y

    def update_all(self, verbose=False, progress=None):
        """Run the whole pipeline: AV, contact volume, diffusion, photons.

        Parameters
        ----------
        verbose : bool
            Print stage-by-stage detail.
        progress : callable, optional
            ``progress(fraction, message)`` called as each stage starts, with
            *fraction* in [0, 1]. This is how a UI shows progress **without the
            model knowing what a UI is** -- it used to drive a
            ``QProgressDialog`` directly, which put Qt in the middle of the
            simulation.

        Returns
        -------
        bool
            Whether a trajectory was produced.
        """
        verbose = verbose or self.verbose
        # No explicit gc.collect() here: the grids and trajectories this method
        # replaces are plain refcounted NumPy buffers, so they are freed as soon
        # as the attributes are rebound. Forcing a full generational collection
        # cost ~20 ms per run, which a residue scan pays hundreds of times.
        if verbose:
            print("Updating simulation")

        def report(fraction, message):
            if progress is not None:
                progress(fraction, message)

        report(0.0, "Initializing simulation...")

        report(0.2, "Calculating accessible volume (AV)...")
        self.calc_av(verbose=verbose)

        report(0.4, "Calculating slow AV (ACV)...")
        self._calc_slow_av(verbose=verbose)
        self._ensemble_fields = None
        self.ensemble_lifetimes = None
        self._photon_trace = None

        if self.ensemble != "walk":
            report(0.6, "Solving the %s ensemble..." % self.ensemble)
            self.solve_ensemble(verbose=verbose)
            report(1.0, "Photon trace drawn from the %s ensemble." % self.ensemble)
            return True

        report(0.6, "Simulating dye diffusion...")
        success = self.simulate_diffusion(verbose=verbose)
        if not success:
            if verbose:
                print("Trajectory calculation failed.")
            return False

        report(0.8, "Calculating quencher distances...")
        self.diffusion.critical_distance = self.critical_distance

        report(1.0, "Simulating photon decay trace...")
        self.calc_photons(verbose=verbose)
        return True


def _get_dye_repository_path():
    """The plugin's dye preset file, ``settings/dye_repository.json``."""
    from ..settings import SETTINGS_DIR

    return str(SETTINGS_DIR / "dye_repository.json")
