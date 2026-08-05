"""Trajectory geometry: superposition, RMSD, distances, joining and slicing.

Coordinates come from :mod:`chisurf.core.fio.trajectory` and the atom
descriptions from :mod:`chisurf.core.structure.topology`; this is what the rest
of ChiSurf actually *does* with them. Together the three replace the MD library
the tree used to depend on.

The operations here are the ones the tree uses, with the same signatures, so
call sites move over without rewriting: :func:`rmsd`, :func:`compute_distances`,
:func:`join`, :meth:`Trajectory.superpose`, slicing, and :func:`iterload` for
trajectories too large to hold at once.

Units
-----
**Nanometres**, matching the trajectory objects this replaces, so ported call
sites keep their factors of ten exactly where they were. The DCD reader
underneath works in Ångström and :func:`load` converts once, visibly.

Notes
-----
Superposition is Kabsch via SVD rather than the quaternion method the reference
uses. They agree to floating-point precision — the tests check that against it
directly — and the SVD is a dozen readable lines against several hundred.
"""

from __future__ import annotations

import numpy as np

from .topology import Element, Topology, element

__all__ = ["Element", "Topology", "Trajectory", "compute_distances", "iterload", "join",
           "element", "load", "load_frame", "rmsd"]


def _kabsch_rotations(mobile: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Return the rotation aligning each frame of *mobile* onto *target*.

    Parameters
    ----------
    mobile : numpy.ndarray
        ``(n_frames, n_atoms, 3)``, already centred on its own centroid.
    target : numpy.ndarray
        ``(n_atoms, 3)``, already centred.

    Returns
    -------
    numpy.ndarray
        ``(n_frames, 3, 3)`` rotation matrices, right-handed.
    """
    covariance = np.einsum("fai,aj->fij", mobile, target)
    u, _, vt = np.linalg.svd(covariance)
    # A plain SVD can hand back a reflection, which superimposes a molecule on
    # its mirror image and reports a flatteringly small RMSD. Flipping the sign
    # of the smallest singular direction is what keeps the rotation proper.
    handedness = np.sign(np.linalg.det(np.einsum("fij,fjk->fik", u, vt)))
    u = u.copy()
    u[:, :, -1] *= handedness[:, None]
    return np.einsum("fij,fjk->fik", u, vt)


def _superposition(mobile_xyz, target_xyz, indices):
    """Return ``(rotations, mobile_centroids, target_centroid)`` for a fit."""
    mobile_sel = mobile_xyz[:, indices]
    target_sel = target_xyz[indices]
    mobile_centre = mobile_sel.mean(axis=1)
    target_centre = target_sel.mean(axis=0)
    rotations = _kabsch_rotations(mobile_sel - mobile_centre[:, None, :],
                                  target_sel - target_centre)
    return rotations, mobile_centre, target_centre


class Trajectory:
    """Coordinates over time, with the topology they belong to.

    Parameters
    ----------
    xyz : array_like
        ``(n_frames, n_atoms, 3)`` in nanometres. A single ``(n_atoms, 3)``
        frame is accepted and promoted.
    topology : Topology, optional
        Atom descriptions. Optional so geometry-only work needs no structure
        file, but anything selecting atoms by name requires it.
    time : array_like, optional
        ``(n_frames,)`` simulation time.
    """

    def __init__(self, xyz, topology: Topology = None, time=None):
        xyz = np.ascontiguousarray(xyz, dtype=np.float32)
        if xyz.ndim == 2:
            xyz = xyz[np.newaxis]
        if xyz.ndim != 3 or xyz.shape[2] != 3:
            raise ValueError(f"expected (n_frames, n_atoms, 3), got {xyz.shape}")
        if topology is not None and topology.n_atoms != xyz.shape[1]:
            raise ValueError(
                f"topology has {topology.n_atoms} atoms but the coordinates "
                f"have {xyz.shape[1]}"
            )
        self.xyz = xyz
        self.topology = topology
        self.time = (np.arange(len(xyz), dtype=np.float32) if time is None
                     else np.asarray(time, dtype=np.float32))

    # -- shape ---------------------------------------------------------------
    @property
    def n_frames(self) -> int:
        """Number of frames."""
        return int(self.xyz.shape[0])

    @property
    def n_atoms(self) -> int:
        """Number of atoms."""
        return int(self.xyz.shape[1])

    @property
    def top(self) -> Topology:
        """The topology; the short name the tree already uses."""
        return self.topology

    def __len__(self) -> int:
        """Return the number of frames."""
        return self.n_frames

    def __getitem__(self, key) -> Trajectory:
        """Return the selected frames as a new trajectory."""
        index = [key] if isinstance(key, (int, np.integer)) else key
        return Trajectory(self.xyz[index], self.topology, self.time[index])

    def __repr__(self) -> str:
        """Return the frame and atom counts."""
        return f"<Trajectory: {self.n_frames} frames, {self.n_atoms} atoms>"

    # -- geometry ------------------------------------------------------------
    def atom_slice(self, indices) -> Trajectory:
        """Return a trajectory holding only *indices*.

        Parameters
        ----------
        indices : array_like of int
            Atom indices to keep, in that order.

        Returns
        -------
        Trajectory
        """
        indices = np.asarray(indices, dtype=np.intp)
        return Trajectory(self.xyz[:, indices],
                          None if self.topology is None else self.topology.subset(indices),
                          self.time)

    def center_coordinates(self) -> Trajectory:
        """Move every frame's centroid to the origin, in place."""
        self.xyz -= self.xyz.mean(axis=1, keepdims=True)
        return self

    def superpose(self, reference: Trajectory, frame: int = 0,
                  atom_indices=None) -> Trajectory:
        """Rotate and translate each frame onto *reference*, in place.

        Parameters
        ----------
        reference : Trajectory
            Trajectory holding the frame to align onto.
        frame : int, optional
            Which frame of *reference* to use.
        atom_indices : array_like of int, optional
            Fit on these atoms only; the transform still moves every atom.
            This is the usual case — fit on the backbone, carry the sidechains.

        Returns
        -------
        Trajectory
            ``self``, modified in place.
        """
        indices = (np.arange(self.n_atoms) if atom_indices is None
                   else np.asarray(atom_indices, dtype=np.intp))
        rotations, mobile_centre, target_centre = _superposition(
            self.xyz, reference.xyz[frame], indices)
        moved = np.einsum("fai,fij->faj", self.xyz - mobile_centre[:, None, :], rotations)
        self.xyz = np.ascontiguousarray(moved + target_centre, dtype=np.float32)
        return self

    # -- output --------------------------------------------------------------
    def save_dcd(self, filename) -> None:
        """Write the trajectory as a DCD (converting nanometres to Ångström)."""
        from chisurf.core.fio.trajectory import write_dcd
        write_dcd(filename, self.xyz * 10.0)

    def save_pdb(self, filename) -> None:
        """Write the frames as a multi-model PDB.

        Needs a topology: a PDB records atom names and residues, which
        coordinates alone cannot supply.
        """
        from chisurf.core.fio.structure.coordinates import write_pdb

        if self.topology is None:
            raise ValueError("cannot write a PDB without a topology")
        atoms = self.topology.atom_array.copy()
        for frame in range(self.n_frames):
            atoms["xyz"] = self.xyz[frame] * 10.0        # nm here, Angstrom in a PDB
            write_pdb(str(filename), atoms, append_model=frame > 0)

    def save(self, filename) -> None:
        """Write the trajectory, choosing the format from the suffix."""
        name = str(filename).lower()
        if name.endswith(".dcd"):
            self.save_dcd(filename)
        elif name.endswith(".pdb"):
            self.save_pdb(filename)
        else:
            raise ValueError(f"cannot write {filename!r}: .dcd and .pdb are written")


def rmsd(target: Trajectory, reference: Trajectory, frame: int = 0,
         atom_indices=None, precentered: bool = False) -> np.ndarray:
    """Return the minimal RMSD of each frame of *target* against one reference frame.

    "Minimal" means after optimal rigid superposition: the value does not
    change if either structure is moved or rotated.

    Parameters
    ----------
    target : Trajectory
        Frames to measure.
    reference : Trajectory
        Trajectory holding the reference frame.
    frame : int, optional
        Which frame of *reference*.
    atom_indices : array_like of int, optional
        Measure over these atoms only.
    precentered : bool, optional
        Accepted for signature compatibility and ignored: the centroids are
        removed here regardless, which costs one subtraction and removes a way
        to get a silently wrong answer by mislabelling the input.

    Returns
    -------
    numpy.ndarray
        ``(target.n_frames,)`` RMSD in the trajectory's units (nanometres).
    """
    indices = (np.arange(target.n_atoms) if atom_indices is None
               else np.asarray(atom_indices, dtype=np.intp))
    mobile = target.xyz[:, indices].astype(np.float64)
    fixed = reference.xyz[frame][indices].astype(np.float64)
    mobile = mobile - mobile.mean(axis=1, keepdims=True)
    fixed = fixed - fixed.mean(axis=0)
    rotations = _kabsch_rotations(mobile, fixed)
    aligned = np.einsum("fai,fij->faj", mobile, rotations)
    difference = aligned - fixed
    return np.sqrt((difference ** 2).sum(axis=(1, 2)) / len(indices)).astype(np.float32)


def compute_distances(trajectory: Trajectory, atom_pairs, periodic: bool = False,
                      opt: bool = True) -> np.ndarray:
    """Return the distance between each atom pair, in every frame.

    Parameters
    ----------
    trajectory : Trajectory
        The frames to measure.
    atom_pairs : array_like
        ``(n_pairs, 2)`` atom indices.
    periodic : bool, optional
        Apply the minimum-image convention. Unsupported: no call site in this
        tree uses it, and a wrong periodic distance is indistinguishable from a
        right one, so it raises rather than quietly ignoring the request.
    opt : bool, optional
        Accepted for signature compatibility and ignored.

    Returns
    -------
    numpy.ndarray
        ``(n_frames, n_pairs)`` distances, in the trajectory's units.
    """
    if periodic:
        raise NotImplementedError(
            "periodic distances are not implemented; pass periodic=False"
        )
    pairs = np.asarray(atom_pairs, dtype=np.intp).reshape(-1, 2)
    delta = trajectory.xyz[:, pairs[:, 0]] - trajectory.xyz[:, pairs[:, 1]]
    return np.sqrt((delta ** 2).sum(axis=-1))


def join(trajectories) -> Trajectory:
    """Concatenate trajectories that share a topology.

    Parameters
    ----------
    trajectories : sequence of Trajectory
        Trajectories to concatenate, in order. They must agree on atom count;
        the first one's topology is kept.

    Returns
    -------
    Trajectory
    """
    trajectories = list(trajectories)
    if not trajectories:
        raise ValueError("nothing to join")
    n_atoms = trajectories[0].n_atoms
    if any(t.n_atoms != n_atoms for t in trajectories):
        raise ValueError("cannot join trajectories with different atom counts")
    return Trajectory(np.concatenate([t.xyz for t in trajectories]),
                      trajectories[0].topology,
                      np.concatenate([t.time for t in trajectories]))


def load(filename, top=None, stride: int = None, atom_indices=None) -> Trajectory:
    """Read a trajectory or a structure.

    Parameters
    ----------
    filename : str or os.PathLike
        ``.dcd``, ``.xtc``, or a structure file (``.pdb``, ``.cif``) read as a
        single frame.
    top : str or Topology, optional
        Topology, required for the coordinate-only formats.
    stride : int, optional
        Keep every *stride*-th frame.
    atom_indices : array_like of int, optional
        Keep only these atoms.

    Returns
    -------
    Trajectory
    """
    name = str(filename).lower()
    if name.endswith((".dcd", ".xtc")):
        if top is None:
            raise ValueError(f"{filename!r} stores coordinates only; pass top=")
        topology = top if isinstance(top, Topology) else Topology.from_file(str(top))
        if name.endswith(".dcd"):
            from chisurf.core.fio.trajectory import dcd_info, read_dcd
            xyz, _, _ = read_dcd(filename, stride=stride, atom_indices=atom_indices)
            xyz = xyz / 10.0                     # Angstrom on disk, nm in memory
            # DCD records a first step, an interval and a timestep rather than
            # a free list of times. Rebuild the axis from those, so a strided
            # trajectory keeps its real spacing instead of counting frames.
            header = dcd_info(filename)
            step = header.step_interval * (int(stride) if stride else 1)
            time = (header.first_step + np.arange(len(xyz)) * step) * header.delta
            return Trajectory(xyz, topology.subset(atom_indices)
                              if atom_indices is not None else topology, time)
        else:
            from chisurf.core.fio.trajectory import read_xtc
            xyz, _, _, _ = read_xtc(filename, stride=stride, atom_indices=atom_indices)
        if atom_indices is not None:
            topology = topology.subset(atom_indices)
        return Trajectory(xyz, topology)

    topology = Topology.from_file(str(filename))
    xyz = topology.atom_array["xyz"][np.newaxis] / 10.0    # PDB is Angstrom
    if atom_indices is not None:
        indices = np.asarray(atom_indices, dtype=np.intp)
        return Trajectory(xyz[:, indices], topology.subset(indices))
    return Trajectory(xyz, topology)


def load_frame(filename, index: int, top=None) -> Trajectory:
    """Read a single frame.

    Parameters
    ----------
    filename : str or os.PathLike
        Trajectory or structure file.
    index : int
        Frame to read.
    top : str or Topology, optional
        Topology, for the coordinate-only formats.

    Returns
    -------
    Trajectory
        A one-frame trajectory.
    """
    return load(filename, top=top)[int(index)]


def iterload(filename, chunk: int = 100, stride: int = None, top=None):
    """Yield a trajectory in chunks of *chunk* frames.

    The whole file is decoded once and handed out in slices, which is enough
    for the sizes this tree sees and keeps the readers simple. It exists so
    call sites that stream do not have to change shape.

    Parameters
    ----------
    filename : str or os.PathLike
        Trajectory file.
    chunk : int, optional
        Frames per chunk.
    stride : int, optional
        Keep every *stride*-th frame.
    top : str or Topology, optional
        Topology, for the coordinate-only formats.

    Yields
    ------
    Trajectory
    """
    trajectory = load(filename, top=top, stride=stride)
    for start in range(0, trajectory.n_frames, max(1, int(chunk))):
        yield trajectory[start:start + int(chunk)]
