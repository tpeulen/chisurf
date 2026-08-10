from __future__ import annotations
from chisurf import typing

import copy
import os
import tempfile

import numpy as np

import chisurf.core.base
import chisurf.core.structure
from .topology import Topology as _Topology
from .trajectory_data import Trajectory as _Trajectory
from . import trajectory_data as _traj_data


class Universe(object):

    def __init__(
            self,
            structure: chisurf.core.structure.Structure = None
    ):
        """Initialize Universe with an optional starting structure."""
        self.structures = [] if structure is None else [structure]
        self.potentials = list()
        self.scaling = list()

    def addPotential(
            self,
            potential,
            scale: float = 1.0
    ) -> None:
        """Add a potential with a scaling factor."""
        self.potentials.append(potential)
        self.scaling.append(scale)

    def removePotential(
            self,
            potentialNbr: int = None
    ) -> None:
        """Remove a potential by index (default: last)."""
        if potentialNbr == -1:
            self.potentials.pop()
            self.scaling.pop()
        else:
            self.potentials.pop(potentialNbr)
            self.scaling.pop(potentialNbr)

    def clearPotentials(self) -> None:
        """Remove all potentials and scaling factors."""
        self.potentials = list()
        self.scaling = list()

    def getEnergy(
            self,
            structure: chisurf.core.structure.Structure = None
    ) -> float:
        """Calculate total energy as sum of all potentials for a given structure."""
        for p in self.potentials:
            p.structure = structure
        Es = self.getEnergies()
        E = Es.sum()
        return E

    def getEnergies(
            self,
            structure: chisurf.core.structure.Structure = None
    ) -> np.ndarray:
        """Calculate individual scaled energies for all potentials."""
        for p in self.potentials:
            p.structure = structure
        scales = np.array(self.scaling)
        Es = np.array([pot.getEnergy() for pot in self.potentials])
        return scales * Es


class TrajectoryFile(
    _Trajectory,
    chisurf.core.base.Base
):

    """A trajectory of :class:`Structure` frames, read from a file.

    Coordinates come from ChiSurf's own readers
    (:mod:`chisurf.core.fio.trajectory`) and the atom descriptions from
    :class:`~chisurf.core.structure.topology.Topology`; there is no MD library
    behind this.

    Accepts a ``.pdb``, a ``.dcd`` or ``.xtc`` (with ``topology=``), a
    :class:`~chisurf.core.structure.trajectory_data.Trajectory`, or a
    :class:`Structure`

    Parameters
    ----------

    structure : string / mfm.structure.Structure
        determines the topology
        is either a string containing the filename of a PDB-File or an instance
        of mfm.structure.Structure() Obligatory in write reading_routine, not
        needed in reading reading_routine

    filename_hdf : string
        the filename of the HDF5-file

    Other Parameters
    ----------------
    verbose : bool

    stride : int, default=None
        Only read every stride-th frame.

    frame : integer or None
        If frame is an integer only the frame number provided by the integer is
        loaded otherwise the whole trajectory is loaded.

    See Also
    --------

    mfm.mfm.structure.Structure

    Examples
    --------

    Making new h5-Trajectory file

    >>> import chisurf.core.structure
    >>> from chisurf.core.structure import TrajectoryFile
    >>> s = chisurf.core.structure.Structure('./test/data/modelling/trajectory/hgbp1/T4L_Topology.pdb', verbose=True, make_coarse=False)
    >>> traj = chisurf.core.structure.TrajectoryFile('./test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd', s, mode='w')
    >>> traj[0]
    <mfm.structure.structure.mfm.structure.Structure at 0x11f34e10>
    >>> print(traj[0])
    ATOM      1    N MET     1     -10.750  14.401  -5.002  0.00  0.00             N
    ATOM      2   H1 MET     1     -11.310  14.080  -4.226  0.00  0.00             H
    ATOM      3   H2 MET     1     -11.333  14.344  -5.825  0.00  0.00             H
    ATOM      4   H3 MET     1     -10.387  15.316  -4.776  0.00  0.00             H
    ATOM      5   CA MET     1      -9.555  13.486  -5.166  0.00  0.00             C
    ....

    Opening h5-Trajectory file

    >>> import chisurf.core.structure
    >>> from chisurf.core.structure import TrajectoryFile
    >>> traj = TrajectoryFile('./test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd', topology='./test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb', mode='r', stride=1)
    >>> print(traj[0:3])
    [<mfm.structure.structure.mfm.structure.Structure at 0x1345d5d0>,
    <mfm.structure.structure.mfm.structure.Structure at 0x1345d610>,
    <mfm.structure.structure.mfm.structure.Structure at 0x132d2230>]

    Name of the trajectory

    >>> print(traj.name)
    '/ data/ structure/ data/ structure/ T4L_Trajectory.h5'

    initialize from another trajectory

    >>> import chisurf.core.structure
    >>> from chisurf.core.structure import TrajectoryFile
    >>> traj = TrajectoryFile('./test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd', topology='./test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb', mode='r', stride=1)
    >>> t2 = TrajectoryFile(traj, filename='test.dcd')

    Attributes:
    -----------
    rmsd : array/list containing the rmsd vs the reference structure of -new- / added structures upon addition
    of the strucutre

    """

    parameterNames = [
        'rmsd',
        'drmsd',
        'energy',
        'chi2'
    ]

    def __init__(
            self,
            p_object,
            filename: str = None,
            rmsd_ref_state: int = 0,
            stride: int = 1,
            inverse_trajectory: bool = False,
            center: bool = False,
            verbose: bool = False,
            atom_indices: typing.List[int] = None,
            mode: str = 'r',
            topology: str = None
    ):
        """

        :param p_object: a path to a .pdb/.cif/.dcd/.xtc file, a Trajectory,
            or a chisurf.core.structure.Structure object;
        :param filename:
        :param rmsd_ref_state:
        :param stride:
        :param inverse_trajectory:
        :param center:
        :param verbose:
        :param atom_indices:
        :param mode:
        :param topology: path to a PDB supplying the topology. Required for
            ``.dcd`` and ``.xtc``, which store coordinates only -- the atom
            names, elements and connectivity are simply not in those files.
        :param args:
        :param kwargs:
        """
        self.mode = mode
        self.atom_indices = atom_indices
        self.stride = stride
        self._rmsd_ref_state = rmsd_ref_state
        self.verbose = verbose
        self.center = center
        self._invert = inverse_trajectory
        self._structure = None
        self._filename = filename

        traj_data = _traj_data

        if isinstance(p_object, str):
            lowered = p_object.lower()
            if self._filename is None:
                self._filename = p_object
            if lowered.endswith((".dcd", ".xtc")):
                if topology is None:
                    raise ValueError(
                        f"{p_object!r} stores coordinates only; pass topology=<pdb path>"
                    )
                loaded = traj_data.load(p_object, top=topology, stride=self.stride,
                                        atom_indices=atom_indices)
                structure = chisurf.core.structure.Structure(topology)
            elif lowered.endswith((".pdb", ".ent", ".cif", ".pqr")):
                loaded = traj_data.load(p_object, atom_indices=atom_indices)
                structure = chisurf.core.structure.Structure(p_object)
            else:
                raise ValueError(
                    f"cannot read {p_object!r}: expected .pdb, .cif, .dcd or .xtc"
                )
        elif isinstance(p_object, traj_data.Trajectory):
            loaded = p_object
            structure = self._structure_from(loaded)
        elif isinstance(p_object, chisurf.core.structure.Structure):
            structure = p_object
            loaded = traj_data.Trajectory(
                p_object.xyz[np.newaxis],
                _Topology(p_object.atoms),
            )
        else:
            raise TypeError(f"cannot build a trajectory from {type(p_object).__name__}")

        self.structure = structure
        super().__init__(xyz=loaded.xyz, topology=loaded.topology, time=loaded.time)

        if self.center:
            self.center_coordinates()

        self.rmsd_ref_state = rmsd_ref_state
        self.rmsd = list()
        self.drmsd = list()
        self.energy = list()
        self.chi2r = list()
        self.offset = 0

    @staticmethod
    def _structure_from(trajectory) -> "chisurf.core.structure.Structure":
        """Return a :class:`Structure` for a trajectory's first frame."""
        structure = chisurf.core.structure.Structure()
        if trajectory.topology is not None:
            atoms = trajectory.topology.atom_array.copy()
            atoms["xyz"] = trajectory.xyz[0]
            structure.atoms = atoms
        return structure

    def clear(self):
        """Clear all recorded RMSD, dRMSD, energy, and chi2 values."""
        self.rmsd = list()
        self.drmsd = list()
        self.energy = list()
        self.chi2r = list()
        self.rmsd_ref_state = 0

    @property
    def xyz(self):
        """Cartesian coordinates of each atom in each simulation frame

        If the attribute :py:attribute:`.TrajectoryFile.invert` is True the 
        oder of the trajectory is inverted
        """
        if self.invert:
            return self._xyz[::-1]
        return self._xyz

    @xyz.setter
    def xyz(self, v):
        """Set cartesian coordinates."""
        self._xyz = np.ascontiguousarray(v, dtype=np.float32)

    @property
    def structure(self) -> chisurf.core.structure.Structure:
        """The template structure used for the trajectory."""
        return self._structure

    @structure.setter
    def structure(
            self,
            v: chisurf.core.structure.Structure
    ):
        """Set the template structure (a shallow copy is stored)."""
        self._structure = copy.copy(v)

    @property
    def invert(self) -> bool:
        """If True the oder of the trajectory is inverted (by default False)
        """
        return self._invert

    @invert.setter
    def invert(
            self,
            v: bool
    ):
        """Enable or disable inversion of the trajectory order."""
        self._invert = bool(v)

    @property
    def filename(self) -> str:
        """The filename of the trajectory
        """
        return self._filename

    @filename.setter
    def filename(
            self,
            v: str
    ):
        """Set the trajectory filename; saving the trajectory to disk."""
        if isinstance(v, str):
            self._filename = v
            self.save(v)

    @property
    def name(self) -> str:
        """The name of the trajectory composed of the directory and the filename
        """
        try:
            fn = copy.copy(self.directory + self.filename)
            return fn.replace('/', '/ ')
        except AttributeError:
            return "None"

    @property
    def rmsd_ref_state(self) -> int:
        """The index (frame number) of the reference state used for the RMSD
        calculation
        """
        return self._rmsd_ref_state

    @rmsd_ref_state.setter
    def rmsd_ref_state(
            self,
            ref_frame: int
    ):
        """Set the reference frame for RMSD calculations and compute RMSDs."""
        self._rmsd_ref_state = ref_frame
        self.rmsd = _traj_data.rmsd(self, self, ref_frame)

    @property
    def directory(self) -> str:
        """Directory in which the filename of the trajectory is located in
        """
        return os.path.dirname(self.filename)

    @property
    def reference(self) -> chisurf.core.structure.Structure:
        """The reference structure used for RMSD-calculation. This cannot be
        set directly but has to be set via the number of the reference state
         :py:attribute`.rmsd_ref_state`
        """
        if self.rmsd_ref_state == 'average':
            return self.average
        else:
            return self[int(self.rmsd_ref_state)]

    @property
    def average(self) -> chisurf.core.structure.Structure:
        """
        The average structure (:py:class:`~mfm.structure.mfm.structure.Structure`)
        of the trajectory
        """
        return chisurf.core.structure.average(self[:len(self)])

    @property
    def values(self) -> np.array:
        """A 2D-numpy array containing the RMSD, dRMSD, energy and the chi2
        values of the trajectory

        Examples
        --------

        >>> import chisurf.core.settings as mfm
        >>> from chisurf.core.structure import TrajectoryFile
        >>> traj = TrajectoryFile('./test/data/structure/2807_8_9_b.dcd', topology='top.pdb', stride=1)
        >>> traj
        <Trajectory: 92 frames, 2495 atoms>
        >>> traj.values
        array([], shape=(4, 0), dtype=float64)
        >>> traj.append(times[0])
        inf     inf     0.0000  0.6678
        >>> traj.append(times[0])
        inf     inf     0.0000  0.0000
        >>> traj.values
        array([ [  5.96507968e-09,   5.96508192e-09],
                [  6.67834069e-01,   5.96507944e-09],
                [             inf,              inf],
                [             inf,              inf]])
        """
        rmsd = np.array(self.rmsd)
        drmsd = np.array(self.drmsd)
        energy = np.array(self.energy)
        chi2 = np.array(self.chi2r)
        return np.vstack([rmsd, drmsd, energy, chi2])

    def append(
            self,
            xyz,
            update_rmsd: bool = True,
            energy: float = np.inf,
            energy_fret: float = np.inf,
            verbose: bool = False
    ):
        """Append a structure of type :py::class`mfm.mfm.structure.Structure`
        to the trajectory

        :param structure: mfm.structure.Structure
        :param update_rmsd: bool
        :param energy: float
            Energy of the system
        :param energy_fret: float
            Energy of the FRET-potential
        :param verbose: bool
            By default True. If True energy, energy_fret, RMSD and dRMSD are
            printed to std-out.

        Examples
        --------

        >>> import chisurf.core.settings as mfm
        >>> from chisurf.core.structure import TrajectoryFile
        >>> traj = TrajectoryFile('./test/data/structure/2807_8_9_b.dcd', topology='top.pdb', stride=1)
        >>> traj
        <Trajectory: 92 frames, 2495 atoms>
        >>> t.append(traj[0])
        <Trajectory: 93 frames, 2495 atoms>
        """
        verbose = verbose or self.verbose
        if isinstance(xyz, chisurf.core.structure.Structure):
            xyz = xyz.xyz

        # Appending grows the trajectory in memory. It used to reopen the file
        # and write one frame per call, which made a Monte-Carlo run pay a file
        # round-trip per accepted move; :meth:`save` writes when asked.
        frame = np.asarray(xyz, dtype=np.float32).reshape((1, -1, 3))
        self._xyz = (frame if self._xyz is None or len(self._xyz) == 0
                     else np.append(self._xyz, frame, axis=0))
        self.time = np.arange(len(self._xyz), dtype=np.float32)

        if update_rmsd and len(self._xyz) > 1:
            # Indexing this class yields Structure objects, not frames, so the
            # RMSD is taken on plain trajectories built from the coordinates.
            def frame_at(index):
                """Return frame *index* as a one-frame trajectory."""
                return _traj_data.Trajectory(self._xyz[index][np.newaxis])

            new_frame = frame_at(-1)
            next_drmsd = _traj_data.rmsd(new_frame, frame_at(-2))
            next_rmsd = _traj_data.rmsd(
                new_frame, frame_at(self.rmsd_ref_state))
        else:
            next_drmsd = [0.0]
            next_rmsd = [0.0]
        self.drmsd.append(float(next_drmsd[0]))
        self.rmsd.append(float(next_rmsd[0]))
        self.energy.append(energy)
        self.chi2r.append(energy_fret)
        if verbose:
            print("%.3f\t%.3f\t%.4f\t%.4f" % (energy, energy_fret, next_rmsd[0], next_drmsd[0]))

    def __iter__(self):
        """
        Implements iterator
        >>> import chisurf.core.structure
        >>> from chisurf.core.structure import TrajectoryFile
        >>> traj = TrajectoryFile('./test/data/structure/2807_8_9_b.dcd', topology='top.pdb', stride=1)
        >>> for s in traj:
        >>>     print(s)
        [<mfm.structure.structure.mfm.structure.Structure object at 0x12FAE330>, <mfm.structure.structure.mfm.structure.Structure object at 0x12FAE3B0>, <li
        b.structure.mfm.structure.Structure.mfm.structure.Structure object at 0x11852070>, <mfm.structure.structure.mfm.structure.Structure object at 0x131052D0>, <mfm.st
        ructure.mfm.structure.Structure.mfm.structure.Structure object at 0x13195270>, <mfm.structure.structure.mfm.structure.Structure object at 0x13228210>]
        """
        for i in range(len(self)):
            yield self[i]

    def __next__(self):
        """
        Iterate trough the trajectory. The current frame is stored in the
        trajectory property ``offset``

        Returns
        -------
        next : mfm.structure.Structure
            Returns the next structure in the trajectory

        Example
        -------

        >>> import chisurf.core.structure
        >>> traj = chisurf.core.structure.TrajectoryFile('./test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd', topology='./test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb', mode='r', stride=1)
        >>> s = str(traj.next())
        >>> print(s[:500])
        ATOM      1    N MET A   1       7.332 -10.706 -15.034  0.00  0.00             N
        ATOM      2    H MET A   1       7.280 -10.088 -15.830  0.00  0.00             H
        ATOM      3   H2 MET A   1       7.007 -11.615 -15.330  0.00  0.00             H
        ATOM      4   H3 MET A   1       8.267 -10.697 -14.653  0.00  0.00             H
        ATOM      5   CA MET A   1       6.341 -10.257 -14.033  0.00  0.00             C
        ATOM      6   HA MET A   1       5.441  -9.927 -14.551  0.00  0.00             H
        >>> s = str(traj.next())
        >>> print(s[:500])
        ATOM      1    N MET A   1      12.234  -5.443 -11.675  0.00  0.00             N
        ATOM      2    H MET A   1      12.560  -5.462 -10.719  0.00  0.00             H
        ATOM      3   H2 MET A   1      12.359  -4.507 -12.036  0.00  0.00             H
        ATOM      4   H3 MET A   1      12.767  -6.064 -12.265  0.00  0.00             H
        ATOM      5   CA MET A   1      10.824  -5.798 -11.763  0.00  0.00             C
        ATOM      6   HA MET A   1      10.490  -5.577 -12.777  0.00  0.00             H
        ATOM      7
        """
        if self.offset == len(self):
            raise StopIteration
        element = self[self.offset]
        self.offset += 1
        return element

    def slice(self, key, copy=True):
        """Return the selected frames as a new :class:`TrajectoryFile`."""
        return TrajectoryFile(
            p_object=_traj_data.Trajectory(self._xyz[key], self.topology))

    def __getitem__(self, key):
        """Return a structure (int key) or list of structures (slice key)."""
        # TODO: do sth. about the evaluation speed (maybe lazy evaluation)
        # http://code.activestate.com/recipes/576410-lazy-lists/
        if isinstance(key, int):
            s = copy.copy(self.structure)
            s.xyz = self._xyz[key]
            s.update()
            return s

        elif isinstance(key, slice):
            start, stop, step = key.start, key.stop, key.step
            # set start and step to their integer defaults if they are None.
            if start is None:
                start = 0
            if step is None:
                step = 1

            def make_structure(i):
                """Create a :class:`Structure` instance for trajectory index *i*."""
                s = copy.copy(self.structure)
                s._filename = self.structure.labeling_file
                s.xyz = self._xyz[i]
                s.update()
                return s

            # make a generator instead of a list
            return [make_structure(i) for i in range(start, stop, step)]


def translate(
        xyz: np.ndarray,
        vector: np.ndarray
) -> None:
    """ Translate a trajectory by an vector

    :param xyz: numpy array
        (frame fit_index, atom_number, coord)
    :param vector:
    :return:
    """
    xyz += np.asarray(vector, dtype=xyz.dtype)


def rotate(
        xyz: np.ndarray,
        rm: np.ndarray
) -> None:
    """ Rotates a trajectory (frame, atom, coord)

    :param xyz: numpy array
        The coordinates (frame fit_index, atom fit_index, coord)

    :param rm: numpy array 3x3 dtpye np.float32 - the rotation matrix
    :return:

    Examples
    --------

    >>> from chisurf.core.structure.trajectory import TrajectoryFile
    >>> import numpy as np
    >>> traj = TrajectoryFile('stride_100.h5')
    >>> xyz = traj.xyz
    >>> b = np.array([[-0.856274009, 0.513258278, -0.057972118], [0.513934493, 0.835381866, -0.194957629], [-0.051634759, -0.196731016, -0.979096889]], dtype=np.float32)
    >>> rotate(xyz, b)

    """
    # rm applied to each coordinate as a column vector, so for the rows stored
    # here that is xyz @ rm.T. The result is written back through [...] rather
    # than rebound, because the caller relies on the update being in place.
    xyz[...] = xyz @ np.asarray(rm, dtype=xyz.dtype).T
