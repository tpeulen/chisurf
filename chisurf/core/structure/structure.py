from __future__ import annotations
from chisurf import typing

import copy
import os
import tempfile

import numpy as np

import chisurf.core.fio
import chisurf.core.fio.structure.coordinates
import chisurf.core.base

clusterCriteria = [
    'maxclust',
    'inconsistent',
    'distance'
]


def add_backbone_amide_hydrogens(
        atoms: np.ndarray,
        bond_length: float = 1.01,
        max_peptide_bond: float = 1.45
) -> np.ndarray:
    """Return *atoms* with a backbone amide hydrogen appended per residue.

    Every non-proline residue keeps exactly one atom named ``H`` -- proline's
    secondary amine has none, and that is the only atom this codebase's
    reduced (backbone + amide-H) representation ever looks up (see
    ``chisurf.core.structure.protein.residue_atoms_internal`` and
    :class:`chisurf.core.structure.potential.potentials.HPotential`, the
    statistical hydrogen-bond potential it exists for).

    Where the preceding residue's carbonyl carbon is known and really bonded
    (same chain, C(i-1)-N(i) within *max_peptide_bond*), the amide nitrogen
    is sp2 and its two known substituents fix the third: the N-H direction is
    the negated sum of the unit vectors to C(i-1) and CA(i), in their shared
    plane. At a chain start or a break in the numbering, there is no such
    C(i-1) -- the real N-terminus there is a charged NH3+ with no single
    fixed H orientation anyway (they rotate freely, and an all-atom tool
    only fixes one by optimizing against nearby acceptors) -- so a
    representative direction is built instead from an ideal tetrahedral
    frame around N using only CA and C of the same residue.

    Parameters
    ----------
    atoms : np.ndarray
        Structured atom array (``chisurf.core.fio.structure.coordinates.atom_dtype``).
    bond_length : float
        N-H bond length in Angstrom.
    max_peptide_bond : float
        Maximum C(i-1)-N(i) distance treated as a real peptide bond.

    Returns
    -------
    np.ndarray
        *atoms* with one row appended per residue that received a new ``H``.
    """
    if atoms.size == 0:
        return atoms

    tetrahedral_cos = -1.0 / 3.0
    tetrahedral_sin = (1.0 - tetrahedral_cos ** 2) ** 0.5

    residues: list[tuple[str, int, list[int]]] = []
    index_by_key: dict[tuple[str, int], int] = {}
    for i in range(atoms.size):
        key = (str(atoms['chain'][i]), int(atoms['res_id'][i]))
        pos = index_by_key.get(key)
        if pos is None:
            index_by_key[key] = len(residues)
            residues.append([str(atoms['res_name'][i]), key, [i]])
        else:
            residues[pos][2].append(i)

    new_rows = []
    prev_chain = None
    prev_c_xyz = None
    for res_name, (chain, res_id), idx in residues:
        res_atoms = atoms[idx]
        names = res_atoms['atom_name']

        def get_xyz(name: str, _names=names, _res_atoms=res_atoms):
            mask = _names == name
            return _res_atoms['xyz'][mask][0] if mask.any() else None

        n_xyz = get_xyz('N')
        ca_xyz = get_xyz('CA')
        c_xyz = get_xyz('C')
        has_h = bool((names == 'H').any())

        h_dir = None
        if (
            not has_h
            and res_name.strip().upper() != 'PRO'
            and n_xyz is not None
            and ca_xyz is not None
        ):
            if (
                prev_c_xyz is not None
                and chain == prev_chain
                and np.linalg.norm(n_xyz - prev_c_xyz) <= max_peptide_bond
            ):
                dir_c = n_xyz - prev_c_xyz
                dir_ca = n_xyz - ca_xyz
                dir_c /= np.linalg.norm(dir_c)
                dir_ca /= np.linalg.norm(dir_ca)
                candidate = -(dir_c + dir_ca)
                candidate_norm = np.linalg.norm(candidate)
                if candidate_norm > 1e-6:
                    h_dir = candidate / candidate_norm
            elif c_xyz is not None:
                # Chain start (or a break in the numbering): no bonded C(i-1)
                # to fix the amide plane, so build one representative
                # tetrahedral N-H direction from CA and C of this residue.
                z_axis = ca_xyz - n_xyz
                z_axis /= np.linalg.norm(z_axis)
                ref = c_xyz - ca_xyz
                x_axis = ref - np.dot(ref, z_axis) * z_axis
                x_norm = np.linalg.norm(x_axis)
                if x_norm > 1e-6:
                    x_axis /= x_norm
                    candidate = tetrahedral_cos * z_axis + tetrahedral_sin * x_axis
                    candidate_norm = np.linalg.norm(candidate)
                    if candidate_norm > 1e-6:
                        h_dir = candidate / candidate_norm

        if h_dir is not None:
            row = np.zeros(1, dtype=atoms.dtype)
            row['chain'] = chain
            row['res_id'] = res_id
            row['res_name'] = res_name
            row['atom_name'] = 'H'
            row['element'] = 'H'
            row['xyz'] = n_xyz + bond_length * h_dir
            new_rows.append(row)

        prev_chain = chain
        prev_c_xyz = c_xyz

    if not new_rows:
        return atoms

    added = np.concatenate(new_rows)
    next_i = int(atoms['i'].max()) + 1 if atoms.size else 0
    next_atom_id = int(atoms['atom_id'].max()) + 1 if atoms.size else 0
    added['i'] = np.arange(next_i, next_i + added.size)
    added['atom_id'] = np.arange(next_atom_id, next_atom_id + added.size)
    try:
        import chisurf.core.support.common
        added['mass'] = chisurf.core.support.common.atom_weights['H']
    except (ImportError, KeyError):
        pass
    return np.concatenate([atoms, added])


class Structure(chisurf.core.base.Base):
    """

    Attributes
    ----------
    max_atom_residue : int
        Maximum atoms per residue. The maximum atoms per residue have to be
        limited, because of the residue/atom lookup tables. By default
        maximum 16 atoms per residue are allowed.

    xyz : numpy-array
        The xyz-attribute is an array of the cartesian coordinates represented
        by the attribute atom

    residue_names: list
        residue names is a list of the residue-names. Here the residues are
        represented by the same name as the initial PDB-file, usually 3-letter
        amino-acid code. The residue_names attribute may look like:
        ['TYR', 'HIS', 'ARG']

    n_atoms: int
        The number of atoms

    b_factos: array
        An array of the b-factors.

    radius_gyration: float
        The attribute radius_gyration returns the radius of gyration of the
        structure. The radius of gyration is given by:
        rG = (np.sqrt((coord - rM) ** 2).sum(axis=1)).mean()
        Here rM are the mean coordinates of the structure.


    :param filename: str
        Path to the pdb file on disk
    :param make_coarse: bool
        Conversion to coarse representation using internal coordinates.
        Side-chains are not considered. The Cbeta-atoms is moved to center of
        mass of the side-chain.
    :param verbose: bool
        print output to stdout
    :param auto_update: bool
        update cartesian-coordiantes automatically after change of internal
        coordinates. This only applies for coarse-grained coordinates

    Examples
    --------

    >>> import chisurf.core.settings as mfm.structure
    >>> structure = mfm.structure.structure.Structure('1dg3', verbose=True)
    ======================================
    Filename: ../test/data/structure/HM_1FN5_Naming.pdb
    Path: ../test/data/structure
    Number of atoms: 9316
    >>> print(str(structure)[:324])
    ATOM      1    N HIS A   6     -18.863  20.262  33.465  0.00  0.00             N
    ATOM      2   CA HIS A   6     -17.949  21.401  33.768  0.00  0.00             C
    ATOM      3    C HIS A   6     -18.327  22.599  32.897  0.00  0.00             C
    ATOM      4    O HIS A   6     -19.507  22.812  32.614  0.00  0.00             O

    Write structure to disk

    >>> structure.write('test_out.pdb')

    Radius of gyration

    >>> structure.radius_gyration
    39.24072662264825

    """

    def __init__(
            self,
            p_object=None,
            *args,
            auto_update: bool = False,
            filename: str = None,
            verbose: bool = False,
            pdb_id: str = None,
            protonate: bool = False,
            keep_water: bool = False,
            only_standard_residues: bool = True,
            radii: str = "charmm",
            **kwargs
    ):
        """Initialize a :class:`Structure` from a PDB file, PDB id, or copy.

        Parameters
        ----------
        keep_water : bool
            Keep water molecules. The default drops them, which suits the
            modelling code; a viewer that must show the deposited model as
            deposited asks for them.
        radii : {"charmm", "vdw"}
            Which radius the atoms carry, and which reader runs. ``"vdw"``
            takes the native PDB parser -- ~50x faster on a 9315-atom structure
            -- and gives the element's van der Waals radius, which is what a
            viewer draws with. ``"charmm"`` keeps IMP's per-atom-type Rmin, and
            stays the default because the accessible-volume code sizes its
            probes with it.
        only_standard_residues : bool
            Drop ligands, sugars and modified residues. On by default for the
            same reason.
        """
        super().__init__(*args, **kwargs)
        self.auto_update = auto_update
        self._filename = filename
        self._atoms = None
        self._residue_dict = None
        self._potentials = list()
        self._sequence = None
        self.verbose = verbose
        self.io = chisurf.core.fio.structure.coordinates
        self.pdbid = None

        if isinstance(pdb_id, str):
            self.pdbid = pdb_id
            p_object = pdb_id
        if isinstance(filename, str):
            p_object = filename
        ####################################################
        #              Load ATOM COORDINATES               #
        ####################################################
        if isinstance(p_object, Structure):
            self.atoms = np.copy(p_object.atoms)
            self.filename = copy.copy(p_object.filename)
        elif p_object is None:
            self._atoms = None
            self._filename = None
        elif isinstance(p_object, str):
            if os.path.isfile(p_object):
                self._atoms = self.io.read(
                    p_object,
                    verbose=self.verbose,
                    keep_water=keep_water,
                    only_standard_residues=only_standard_residues,
                    radii=radii,
                )
                self.filename = p_object
            elif len(p_object) == 4:
                self._atoms = self.io.fetch_pdb(p_object)
                self.pdbid = p_object
            else:
                return
        if protonate and p_object is not None:
            self.protonate()

    @property
    def sequence(self) -> typing.Dict:
        """A dictionary mapping chain identifiers to residue name sequences."""
        if self._sequence is None:
            self._sequence = chisurf.core.structure.sequence(self)
        return self._sequence

    @property
    def internal_coordinates(self):
        """Returns None for the base Structure class; subclasses may override."""
        return None

    @property
    def energy(self) -> float:
        """Sum of all attached potential energies."""
        energies = [e(self, **kwargs) for e, kwargs in self._potentials]
        return sum(energies)

    @property
    def atoms(self) -> np.array:
        """The full atom array containing coordinates, names, b-factors, etc."""
        if isinstance(self._atoms, np.ndarray):
            return self._atoms
        else:
            return np.zeros(
                1,
                dtype={
                    'names': chisurf.core.fio.structure.coordinates.keys,
                    'formats': chisurf.core.fio.structure.coordinates.formats
                }
            )

    @atoms.setter
    def atoms(
            self,
            v: np.array
    ):
        """Set the array of atoms (must be a NumPy structured array)."""
        if isinstance(v, np.ndarray):
            self._atoms = v

    @property
    def xyz(self) -> np.array:
        """Cartesian coordinates of all atoms
        """
        return self.atoms['xyz']

    @xyz.setter
    def xyz(
            self,
            v: np.array
    ):
        """Set cartesian coordinates of all atoms."""
        self.atoms['xyz'] = v

    @property
    def vdw(self) -> np.array:
        """Van der Waals radii of all atoms
        """
        return self.atoms['radius']

    @vdw.setter
    def vdw(
            self,
            v: np.array
    ):
        """Set Van der Waals radii of all atoms."""
        self.atoms['radius'] = v

    @property
    def residue_names(self) -> typing.List[str]:
        """Sorted list of unique residue names (e.g. three-letter codes)."""
        res_name = list(set(self.atoms['res_name']))
        res_name.sort()
        return res_name

    @property
    def residue_dict(self):
        """Dictionary mapping residue IDs to dictionaries of their atoms."""
        if self._residue_dict is None:
            residue_dict = chisurf.core.structure.make_dictionary_of_atoms(
                self.atoms
            )
            self._residue_dict = residue_dict
        return self._residue_dict

    @property
    def n_atoms(self) -> int:
        """Total number of atoms."""
        return len(self.atoms)

    @property
    def n_residues(self) -> int:
        """Total number of residues."""
        return len(self.residue_ids)

    @property
    def atom_types(self):
        """Set of all unique atom names present in the structure."""
        return set(self.atoms['atom_name'])

    @property
    def residue_ids(self) -> typing.List[int]:
        """List of unique residue IDs."""
        residue_ids = list(set(self.atoms['res_id']))
        return residue_ids

    def get_atom_index(
            self,
            atom_names
    ):
        """Returns a list of the indeces with a given atom name

        :param atom_names: list of string of the atom-names
        :return: list of integers the indices with a given atom name
        """
        chisurf.core.structure.get_atom_index_by_name(self.atoms, atom_names)

    @property
    def b_factors(self):
        """B-factors of the C-alpha atoms
        """
        sel = chisurf.core.structure.get_atom_index_by_name(self.atoms, ['CA'])[0]
        bfac = self.atoms[sel]['bfactor']
        return bfac

    @b_factors.setter
    def b_factors(self, v):
        """Set b-factors of C-alpha atoms."""
        s = self
        sel = chisurf.core.structure.get_atom_index_by_name(s.atoms, ['CA'])[0]
        for ai, bi in zip(sel, v):
            s._atoms[ai]['bfactor'] = bi

    @property
    def radius_gyration(self) -> float:
        """Radius of gyration of the structure.

        Returns
        -------
        float
            The unweighted radius of gyration in Angstrom, defined as the
            root-mean-square distance of the atoms from their centroid,
            ``sqrt(mean(|r_i - r_mean|**2))``.
        """
        coord = self.xyz
        rM = coord.mean(axis=0)
        rG = np.sqrt(((coord - rM) ** 2).sum(axis=1).mean())
        return float(rG)

    def append_potential(
            self,
            function,
            kwargs: typing.Dict = None
    ):
        """

        :param function:
        :param kwargs:
        :return:

        Examples
        --------

        >>> import chisurf.core.structure
        >>> structure = chisurf.core.structure.Structure('./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb', verbose=True)
        >>> structure.append_potential(mfm.structure.potential.lennard_jones_calpha)
        >>> structure.energy
        -948.0396693387753

        >>> structure.append_potential(chisurf.core.structure.potential.internal_potential_calpha, kwargs={})
        """
        if kwargs is None:
            kwargs = dict()
        self._potentials.append(
            [function, kwargs]
        )

    def update_coordinates(self):
        """Update cartesian coordinates if auto_update is enabled."""
        if self.auto_update:
            self.update()

    def write(
            self,
            filename: str = None,
            append_model: bool = False,
            append_coordinates: bool = False,
    ):
        """
        Write the structure to a filename. By default it uses PDB files

        :param filename: The filename
        :param append_model: bool
            If True the structure is appended to the filename as a new model otherwise the file is overwritten
        """
        if filename is None:
            filename = self._filename
        aw = np.copy(self.atoms)
        aw['xyz'] = self.xyz
        self.io.write_pdb(
            filename,
            aw,
            append_model=append_model,
            append_coordinates=append_coordinates
        )

    def protonate(self) -> None:
        """Add the backbone amide hydrogen every residue can carry.

        ChiSurf's statistical hydrogen-bond potential (:class:`HPotential`,
        ``chisurf.core.structure.potential.potentials``) only ever looks up one
        hydrogen per residue -- the backbone amide N-H named ``H`` -- so a full
        all-atom protonation tool is more than the codebase needs. This builds
        exactly that atom from ideal sp2 nitrogen geometry, in place, and skips
        residues that cannot have one: proline (secondary amine) and the first
        residue of a chain (a charged N-terminus has no plain ``H``).
        """
        self.atoms = add_backbone_amide_hydrogens(self.atoms)

    def update(
            self,
            **kwargs
    ):
        """Update internal state. Base implementation is a no-op."""
        pass

    def __str__(self):
        """Return the structure as a PDB-formatted string."""
        s = ""
        if self.atoms is not None:
            s = ""
            for at in self.atoms:
                # `%1.1s` for the chain, not `%1s`: `%1s` is a *minimum* width in
                # Python and does not truncate, so a chain id wider than the one
                # column a PDB file has would shift every following field. Chain
                # ids of two or more characters are ordinary in mmCIF -- the
                # eight-spoke nuclear pore has 518 of them.
                s += "%-6s%5d %4s%1s%3s %1.1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2s%2s\n" % \
                     ("ATOM ",
                      at['atom_id'], at['atom_name'], " ", at['res_name'], at['chain'],
                      at['res_id'], " ",
                      at['xyz'][0], at['xyz'][1], at['xyz'][2],
                      0.0, 0.0, "  ", at['element'])
        return s + "END\n"

    def __deepcopy__(self, memo):
        """Deep copy implementation that preserves the atom array and filename."""
        new = copy.copy(self)
        new._atoms = np.copy(self._atoms)
        new.filename = copy.copy(self.filename)
        return new


def onRMSF(
        structures,
        selectedNbrs: typing.List[int],
        atomName: str = None,
        **kwargs):
    """Calculates the root mean square deviation with respect to the average structure
    for a given set of structures. The structures do not have to be aligned.

    :param structures:
    :param selectedNbrs:
    :param atomName:
    :param weights:
    :return:
    """
    weights = kwargs.get('weights', np.ones(len(selectedNbrs), dtype=np.float32))
    weights /= sum(weights)

    candidateStructures = [copy.deepcopy(structures[i]) for i in selectedNbrs]
    print("calculating average structure as a reference")
    reference = average(candidateStructures, weights=weights)
    print("aligning selected structures with respect to reference")
    for s in candidateStructures:
        super_impose(reference, s)
    print("Getting %s-atoms of reference" % atomName)
    ar = reference.getAtoms(atomName=atomName)
    cr = ar['xyz']
    msf = np.zeros(len(ar), dtype=np.float32)
    for i, s in enumerate(candidateStructures):
        a = s.getAtoms(atomName=atomName)
        ca = a['xyz']
        msf += weights[i] * np.sum((cr - ca) ** 2, axis=1)
    return np.sqrt(msf)


def rmsd(
        structure_a: chisurf.core.structure.Structure,
        structure_b: chisurf.core.structure.Structure,
        atom_indices=None
):
    """Calculates the root-mean-squared deviation between two structures. In case the indices of the atoms are
    provided only the, respective atoms are used to calculate the RMSD.

    :param structure_a:
    :param structure_b:
    :param atom_indices:

    :return: float, root-mean-squared deviation

    Examples
    --------

    >>> import chisurf.core.settings as mfm
    >>> times = mfm.TrajectoryFile('./test/data/structure/2807_8_9_b.h5', mode='r', stride=1)
    >>> s1 = times[10]
    >>> s1
    <mfm.structure.structure.Structure at 0x135f3ad0>
    >>> s2 = times[0]
    >>> s2
    <mfm.structure.structure.Structure at 0x1348fbb0>
    >>> rmsd(s1, s2)
    6.960082250440536

    """
    if atom_indices is not None:
        a = structure_a.xyz[atom_indices]
        b = structure_b.xyz[atom_indices]
    else:
        a = structure_a.xyz
        b = structure_b.xyz
    return float(np.sqrt(1. / a.shape[0] * ((a - b) ** 2).sum()))


def super_impose(
        structure_ref: chisurf.core.structure.Structure,
        structure_align: chisurf.core.structure.Structure,
        atom_indices=None
):
    """Superimpose two structures

    :param structure_ref:
    :param structure_align:
    :param atom_indices:
    :return:
    """
    if atom_indices is not None:
        a_atoms = structure_align.xyz[atom_indices]
        r_atoms = structure_ref.xyz[atom_indices]
    else:
        a_atoms = structure_align.xyz
        r_atoms = structure_ref.xyz

    # Center coordinates
    n = r_atoms.shape[0]
    av1 = a_atoms.sum(axis=0) / n
    av2 = r_atoms.sum(axis=0) / n
    re = structure_ref.xyz - av2
    al = structure_align.xyz - av1

    # Calculate rotation matrix
    a = np.dot(np.transpose(al), re)
    u, d, vt = np.linalg.svd(a)

    rot = np.transpose(np.dot(np.transpose(vt), np.transpose(u)))
    if np.linalg.det(rot) < 0:
        vt[2] = -vt[2]
        rot = np.transpose(np.dot(np.transpose(vt), np.transpose(u)))

    # Rotate structure
    structure_align.xyz = np.dot(al, rot)


def find_best(
        target,
        reference,
        atom_indices=None
):
    """
    target and reference are both trajectories
    (:class:`chisurf.core.structure.trajectory_data.Trajectory`);
    reference is of length 1, target of arbitrary length

    returns a Structure object and the index within the trajectory

    Examples
    --------

    >>> import chisurf.core.settings as mfm
    >>> times = times = mfm.TrajectoryFile('./test/data/structure/2807_8_9_b.h5', mode='r', stride=1)
    >>> find_best(times.mdtraj, times.mdtraj[2])
    (2, <Trajectory: 1 frames, 2495 atoms>)
    """
    from .trajectory_data import rmsd as _rmsd

    rmsds = _rmsd(target, reference, atom_indices=atom_indices)
    iMin = np.argmin(rmsds)
    return iMin, target[iMin]


def make_dictionary_of_atoms(atoms):
    """Organizes atoms residue-wise in an dict

    :param atoms:
    :return: dict
    """
    residue_dict = dict()
    for res in list(set(atoms['res_id'])):
        at_nbr = np.where(atoms['res_id'] == res)
        residue_dict[res] = dict()
        for atom in atoms[at_nbr]:
            residue_dict[res][atom['atom_name']] = atom
    return residue_dict


def get_coordinates_of_residues(atoms, quencher, verbose=False):
    """
    Returns coordinates and indices of all atoms of certain residue type.

    :param pdb: numpy-array
        numpy-array as returned by PDB.read
    :param quencher: dict
    :param verbose: bool
    :return:

    Examples
    --------

    >>> import chisurf.core.settings as mfm
    >>> pdb_file = models
    >>> pdb = chisurf.core.fio.pdb_file.read(pdb_file, verbose=True)
    Opening PDB-file: ./test/data/model/hgbp1/hGBP1_closed.pdb
    ======================================
    Filename: ./test/data/model/hgbp1/hGBP1_closed.pdb
    Path: ./test/data/model/hgbp1
    Number of atoms: 9316
    --------------------------------------
    >>> chisurf.tools.dye_diffusion.dye_diffusion.get_quencher_coordinates(pdb, {'TRP': ['CA']})
    dict([('TRP', array([[ 74.783,  -7.884,  18.04 ],
        [ 71.558, -13.346,  15.126],
       [ 70.873,   4.983,  23.373],
       [ 61.507,  -8.977,  33.237]]))])
    """
    if verbose:
        print("Finding quenchers")
        print(quencher)
    atom_idx = get_atom_index_of_residue_types(atoms, quencher)
    coordinates = dict()
    for res_key in quencher:
        coordinates[res_key] = atoms['xyz'][atom_idx[res_key]]
    if verbose:
        print("Quencher atom-indeces: \n %s" % atom_idx)
        print("Quencher coordinates: \n %s" % coordinates)
    return coordinates


def get_atom_index_of_residue_types(
        pdb,
        res_types,
        verbose: bool = False
):
    """
    Returns atom-indices given a selection of residue types and atom names as dict.
    The selection is based on dictionaries. For each residue-type only the atoms within a
    list are selected (see example)

    :param pdb:
    :param res_types: dict
    :param verbose: bool
    :return: dict

    Examples
    --------

    >>> import chisurf.core.fio
    >>> pdb_file = models
    >>> pdb = chisurf.core.fio.PDB.read(pdb_file, verbose=True)
    Opening PDB-file: ./test/data/model/hgbp1/hGBP1_closed.pdb
    ======================================
    Filename: ./test/data/model/hgbp1/hGBP1_closed.pdb
    Path: ./test/data/model/hgbp1
    Number of atoms: 9316
    --------------------------

    Get all atom-indices of all C-alphas in the TRY

    >>> chisurf.tools.dye_diffusion.dye_diffusion.selection2atom_idx(pdb, {'TRP': ['CA']})
    dict([('TRP', array([1114, 1155, 1651, 2690], dtype=uint32))])
    >>> chisurf.tools.dye_diffusion.dye_diffusion.selection2atom_idx(pdb, {'TRP': ['CA'], 'TYR': ['CA']})
    dict([('TRP', array([1114, 1155, 1651, 2690], dtype=uint32)), ('TYR', array([ 608,  707, 1879,
    2107, 2128, 3013, 3067, 4231, 4667, 5169, 6651, 6733, 7005, 7026, 7289, 8272], dtype=uint32))])
    """
    atom_idx = dict()
    for residue_key in res_types:
        atoms = []
        for atom_name in res_types[residue_key]:
            atoms.append(np.where((pdb['res_name'] == residue_key) & (pdb['atom_name'] == atom_name))[0])
        if len(atoms) > 0:
            atom_idx[residue_key] = np.array(np.hstack(atoms), dtype=np.uint32)
        else:
            atom_idx[residue_key] = np.array([], dtype=np.uint32)
    return atom_idx


def get_atom_index_by_name(
        pdb,
        atom_names,
        verbose: bool = False
):
    """
    Returns atom-indices given a an atomic name as list.

    :param pdb:
    :param atom_names: list of strings
    :param verbose: bool
    :return: list

    Examples
    --------

    >>> import chisurf.core.settings as mfm
    >>> pdb_file = './test/data/model/hgbp1/hGBP1_closed.pdb'
    >>> pdb = chisurf.core.fio.PDB.read(pdb_file, verbose=True)
    Opening PDB-file: ./test/data/model/hgbp1/hGBP1_closed.pdb
    ======================================
    Filename: ./test/data/model/hgbp1/hGBP1_closed.pdb
    Path: ./test/data/model/hgbp1
    Number of atoms: 9316
    --------------------------

    Get all atom-indices of all C-alphas in the TRY

    >>> chisurf.tools.dye_diffusion.dye_diffusion.selection2atom_idx(pdb, {'TRP': ['CA']})
    dict([('TRP', array([1114, 1155, 1651, 2690], dtype=uint32))])
    >>> chisurf.tools.dye_diffusion.dye_diffusion.selection2atom_idx(pdb, {'TRP': ['CA'], 'TYR': ['CA']})
    dict([('TRP', array([1114, 1155, 1651, 2690], dtype=uint32)), ('TYR', array([ 608,  707, 1879,
    2107, 2128, 3013, 3067, 4231, 4667, 5169, 6651, 6733, 7005, 7026, 7289, 8272], dtype=uint32))])
    """
    atoms = []
    for atom_name in atom_names:
        atoms.append(np.where((pdb['atom_name'] == atom_name))[0])
    return atoms


def sequence(
        structure_obj
) -> typing.Dict:
    """Return dictionary of sequences keyed to chain and type of sequence used.

    :param structure_obj: Structure
    """
    # Check to see if there are multiple model.  If there are, only look
    # at the first model.
    p = structure_obj.atoms
    atoms = [a for a in p if a['atom_name'] == "CA "]
    chain_dict = dict([(l[21], []) for l in atoms])
    for c in list(chain_dict.keys()):
        chain_dict[c] = [l[17:20] for l in atoms if l[21] == c]
    return chain_dict


def count_atoms(topology_dict):
    """Count the number of atoms in a topology dict

    :param topology_dict: dict
        a topology of a structure as python dict (as described by MDTraj)
    :return: int
    """
    n_atoms = 0
    for chain in topology_dict['chains']:
        for residue in chain['residues']:
            n_atoms += len(residue['atoms'])
    return n_atoms


def average(
        structures: typing.List[chisurf.core.structure.Structure],
        weights: typing.List[float] = None,
        write: bool = True,
        filename: str = None,
        verbose: bool = True
) -> chisurf.core.structure.Structure:
    """
    Calculates weighted average of a list of structures.
    saves to filename if write is True
    if filename not provided makes new "average.pdb" file in temp-folder
    of the system

    Examples
    --------

    >>> import chisurf.core.structure
    >>> traj = chisurf.core.structure.TrajectoryFile('./test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd', topology='./test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb', mode='r', stride=1)
    >>> avg = traj.average
    >>> avg
    <mfm.structure.structure.Structure at 0x117ff770>
    >>> avg.labeling_file
    'c:\\users\\peulen\\appdata\\local\\temp\\average.pdb'
    """
    if weights is None:
        weights = np.ones(
            len(structures), dtype=np.float64
        )
        weights /= weights.sum()
    else:
        weights = np.array(weights)
    avg = chisurf.core.structure.Structure()
    avg.atoms = np.copy(structures[0].atoms)
    avg.xyz *= 0.0

    for i, s in enumerate(structures):
        avg.xyz += weights[i] * s.xyz
    if filename is None:
        filename = os.path.join(
            tempfile.tempdir, "average.pdb"
        )
    if write:
        if verbose:
            print("Writing average to file: %s" % filename)
        avg.filename = filename
        avg.write()
    return avg
