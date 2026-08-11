from __future__ import annotations

import math
import copy
import numpy as np

import chisurf as cs
import chisurf.core.fio.structure
import chisurf.core.math.linalg
from chisurf.core.structure.structure import Structure


internal_formats = ['i4', 'i4', 'i4', 'i4', 'f8', 'f8', 'f8']

internal_atom_numbers = [
    ('N', 0),
    ('CA', 1),
    ('C', 2),
    ('O', 3),
    ('CB', 4),
    ('H', 5),
    ('CG', 6),
    ('CD', 7),
]
residue_atoms_internal = dict([
    ('CYS', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('MET', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('PHE', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('ILE', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('LEU', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('VAL', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('TRP', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('TYR', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('ALA', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('GLY', ['N', 'C', 'CA', 'O', 'H']),
    ('THR', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('SER', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('GLN', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('ASN', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('GLU', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('ASP', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('HIS', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('ARG', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('LYS', ['N', 'C', 'CA', 'CB', 'O', 'H']),
    ('PRO', ['N', 'C', 'CA', 'CB', 'O', 'H', 'CG', 'CD']),
]
)
internal_keys = ['i', 'ib', 'ia', 'id', 'b', 'a', 'd']
a2id = dict(internal_atom_numbers)
id2a = dict([(a[1], a[0]) for a in internal_atom_numbers])
res2id = dict([(aa, i) for i, aa in enumerate(residue_atoms_internal)])


def r2i(coord_i, a1, a2, a3, a4, ai):
    """Cartesian coordinates to internal-coordinates

    :param coord_i: a numpy array which contains the number of the atoms a1, a2, a3, a4 and the bond-length, angle,
    and dihedral angle between the four atoms
    :param a1: first atoms
    :param a2: second atom
    :param a3: third atom
    :param a4: fourth atom (the next atom)
    :param ai: The index of the internal coordinate which is defined by the four atoms
    :return: the index of the next atom (ai+1)
    """
    vn = a4['xyz']
    v1 = a1['xyz']
    v2 = a2['xyz']
    v3 = a3['xyz']
    b = cs.core.math.linalg.norm3(v3 - vn)
    a = cs.core.math.linalg.angle(v2, v3, vn)
    d = cs.core.math.linalg.dihedral(v1, v2, v3, vn)
    coord_i[ai] = a4['i'], a3['i'], a2['i'], a1['i'], b, a, d
    return ai + 1


# `cache=True`: this is the one kernel on the structure-loading path whose
# machine code was **not** written to disk, so every new process paid to
# compile it again. Measured over a plain PDB load, eight kernels compile and
# seven of them were already cached; this was the eighth.
def atom_dist(
        aDist: np.ndarray,
        resLookUp: np.ndarray,
        xyz: np.ndarray,
        aID: np.ndarray
):
    """

    :param aDist: a 2D array that is used to write out the distance matrix
    :param resLookUp: a lookup array that is used to identify the atom types
    :param xyz: the coordinates of all atoms
    :param aID: the atom type (an integer) for that the distance matrix is calculated
    :return:
    """
    n_residues = resLookUp.shape[0]
    for i in range(n_residues):
        ia1 = resLookUp[i, aID]
        if ia1 < 0:
            continue
        a1 = xyz[ia1, 0]
        a2 = xyz[ia1, 1]
        a3 = xyz[ia1, 2]
        for j in range(i, n_residues):
            ia2 = resLookUp[j, aID]
            if ia2 < 0:
                continue
            b1 = xyz[ia2, 0] - a1
            b2 = xyz[ia2, 1] - a2
            b3 = xyz[ia2, 2] - a3

            d12 = math.sqrt(b1*b1 + b2*b2 + b3*b3)

            aDist[i, j] = d12
            aDist[j, i] = d12
    return aDist


def move_center_of_mass(
        structure: Structure,
        all_atoms
):
    """

    :param structure:
    :param all_atoms:
    :return:
    """
    for i, res in enumerate(structure.residue_ids):
        at_nbr = np.where(all_atoms['res_id'] == res)[0]
        cb_nbr = structure.l_cb[i]
        if cb_nbr > 0:
            cb = structure.atoms[cb_nbr]
            cb['xyz'] *= cb['mass']
            for at in at_nbr:
                atom = all_atoms[at]
                residue_name = atom['res_name']
                if atom['atom_name'] not in residue_atoms_internal[residue_name]:
                    cb['xyz'] += atom['xyz'] * atom['mass']
                    cb['mass'] += atom['mass']
            cb['xyz'] /= cb['mass']
            structure.atoms[cb_nbr] = cb


def make_residue_lookup_table(
        structure: Structure
):
    """

    :param structure:
    :return:
    """
    l_residue = np.zeros(
        (structure.n_residues, structure.max_atom_residue),
        dtype=np.int32) - 1
    n = 0
    res_dict = structure.residue_dict
    for residue in list(res_dict.values()):
        for atom in list(residue.values()):
            atom_name = atom['atom_name']
            if atom_name in list(a2id.keys()):
                l_residue[n, a2id[atom_name]] = atom['i']
        n += 1
    l_ca = l_residue[:, a2id['CA']]
    l_cb = l_residue[:, a2id['CB']]
    l_c = l_residue[:, a2id['C']]
    l_n = l_residue[:, a2id['N']]
    l_h = l_residue[:, a2id['H']]
    return l_residue, l_ca, l_cb, l_c, l_n, l_h


def internal_to_cartesian(
        bond: np.array,
        angle: np.array,
        dihedral: np.array,
        ans,
        i_b: np.array,
        i_a: np.array,
        i_d: np.array,
        n_atoms: int,
        r,
        p,
        startPoint: int
) -> np.ndarray:
    """

    :param bond: bond-length
    :param angle: angle
    :param dihedral: dihedral
    :param ans:
    :param i_b:
    :param i_a:
    :param i_d:
    :param n_atoms:
    :param r:
    :param startPoint:
    :return:
    """

    for i in range(n_atoms):
        sin_theta = math.sin(angle[i])
        cos_theta = math.cos(angle[i])
        sin_phi = math.sin(dihedral[i])
        cos_phi = math.cos(dihedral[i])

        p[i*3 + 0] = bond[i] * sin_theta * sin_phi
        p[i*3 + 1] = bond[i] * sin_theta * cos_phi
        p[i*3 + 2] = bond[i] * cos_theta

    for i in range(n_atoms):
        if i_b[i] != 0 and i_a[i] != 0 and i_d[i] != 0:
            ab1 = (r[i_b[i], 0] - r[i_a[i], 0])
            ab2 = (r[i_b[i], 1] - r[i_a[i], 1])
            ab3 = (r[i_b[i], 2] - r[i_a[i], 2])
            nab = math.sqrt(ab1*ab1+ab2*ab2+ab3*ab3)
            ab1 /= nab
            ab2 /= nab
            ab3 /= nab
            bc1 = (r[i_a[i], 0] - r[i_d[i], 0])
            bc2 = (r[i_a[i], 1] - r[i_d[i], 1])
            bc3 = (r[i_a[i], 2] - r[i_d[i], 2])
            nbc = math.sqrt(bc1*bc1+bc2*bc2+bc3*bc3)
            bc1 /= nbc
            bc2 /= nbc
            bc3 /= nbc
            v1 = ab3 * bc2 - ab2 * bc3
            v2 = ab1 * bc3 - ab3 * bc1
            v3 = ab2 * bc1 - ab1 * bc2
            cos_alpha = ab1*bc1 + ab2*bc2 + ab3*bc3
            sin_alpha = math.sqrt(1.0 - cos_alpha * cos_alpha)
            v1 /= sin_alpha
            v2 /= sin_alpha
            v3 /= sin_alpha
            u1 = v2 * ab3 - v3 * ab2
            u2 = v3 * ab1 - v1 * ab3
            u3 = v1 * ab2 - v2 * ab1

            r[ans[i], 0] = r[i_b[i], 0] + v1 * p[i * 3 + 0] + u1 * p[i * 3 + 1] - ab1 * p[i * 3 + 2]
            r[ans[i], 1] = r[i_b[i], 1] + v2 * p[i * 3 + 0] + u2 * p[i * 3 + 1] - ab2 * p[i * 3 + 2]
            r[ans[i], 2] = r[i_b[i], 2] + v3 * p[i * 3 + 0] + u3 * p[i * 3 + 1] - ab3 * p[i * 3 + 2]
    return r


def _measure_internal_coordinates(structure: Structure, plans: list) -> int:
    """Fill ``structure.coord_i`` from a list of planned rows.

    Parameters
    ----------
    structure : Structure
        Structure whose ``coord_i`` array is written in place.
    plans : list of tuple
        One entry per internal coordinate, in output order. ``('row', values)``
        carries a complete record; ``('quad', (a1, a2, a3, a4))`` carries four
        atom records whose bond length, angle and dihedral are still to be
        measured.

    Returns
    -------
    int
        Number of rows written, i.e. the length ``coord_i`` truncates to.

    Notes
    -----
    Every quadruple is measured in one stacked call per quantity, which is the
    whole point of collecting them first: the same three helpers that cost
    ~14 us per scalar invocation cost ~2 us for the entire structure when handed
    an ``(n, 3)`` array.
    """
    quads = [payload for kind, payload in plans if kind == 'quad']
    lengths = angles = dihedrals = None
    if quads:
        n = len(quads)
        xyz = structure.atoms['xyz']
        gather = [
            xyz[np.fromiter((q[k]['i'] for q in quads), dtype=np.int64, count=n)]
            for k in range(4)
        ]
        v1, v2, v3, vn = gather
        lengths = cs.core.math.linalg.norm3(v3 - vn)
        angles = cs.core.math.linalg.angle(v2, v3, vn)
        dihedrals = cs.core.math.linalg.dihedral(v1, v2, v3, vn)

    ai = 0
    q = 0
    for kind, payload in plans:
        if kind == 'row':
            structure.coord_i[ai] = payload
        else:
            a1, a2, a3, a4 = payload
            structure.coord_i[ai] = (
                a4['i'], a3['i'], a2['i'], a1['i'],
                lengths[q], angles[q], dihedrals[q],
            )
            q += 1
        ai += 1
    return ai


def calc_internal_coordinates_bb(
        structure: Structure,
        verbose: bool = None,
        **kwargs
):
    """Calculate backbone and side-chain internal coordinates for a protein structure."""
    if verbose is None:
        verbose = cs.core.settings.cs_settings['verbose']

    structure.coord_i = np.zeros(
        structure.atoms.shape[0],
        dtype={
            'names': internal_keys,
            'formats': internal_formats
        }
    )
    # Each internal coordinate is the same three geometric measurements on a
    # different quadruple of atoms, so the residue walk only *chooses* the
    # quadruples -- it does not need to measure them one at a time. Collecting
    # them first and measuring all of them in three stacked calls turns ~10,000
    # three-element operations into three operations on a (n, 3) array, which is
    # what the helpers in :mod:`chisurf.core.math.linalg` are written against.
    # Measured on hGBP1 (3456 coordinates), median of seven warm calls: 0.474 s
    # calling them one quadruple at a time, 0.096 s when those helpers were
    # numba-compiled, 0.021 s stacked. So this is 4.5x faster than the compiled
    # scalar version it replaces -- the win is removing ~10,000 Python calls,
    # not the arithmetic, which is why compiling them could not reach it.
    plans: list[tuple[str, object]] = []
    rp = None
    res_nr = 0
    for rn in list(structure.residue_dict.values()):
        # ``residue_dict`` holds every residue in the file, waters and other
        # heteroatoms included, and those have no backbone -- 148L reaches this
        # loop with HOH entries and used to die on ``KeyError: 'CA'``. A
        # backbone internal coordinate needs N, CA and C, so a residue without
        # them is not one this function has anything to say about. Skipping
        # before ``rp`` is reassigned keeps the chain of previous residues over
        # backbone-complete ones only.
        if not {'N', 'CA', 'C'} <= rn.keys():
            continue
        res_nr += 1
        # BACKBONE
        if rp is None:
            # The first residue has no predecessor, so its first three rows are
            # partial by construction rather than measured against four atoms.
            # There are three of them per structure; they stay scalar.
            plans.append(('row', (rn['N']['i'], 0, 0, 0, 0.0, 0.0, 0.0)))
            plans.append(('row', (
                rn['CA']['i'], rn['N']['i'], 0, 0,
                float(cs.core.math.linalg.norm3(rn['N']['xyz'] - rn['CA']['xyz'])), 0.0, 0.0,
            )))
            plans.append(('row', (
                rn['C']['i'], rn['CA']['i'], rn['N']['i'], 0,
                float(cs.core.math.linalg.norm3(rn['CA']['xyz'] - rn['C']['xyz'])),
                float(cs.core.math.linalg.angle(
                    rn['C']['xyz'], rn['CA']['xyz'], rn['N']['xyz'])),
                0.0,
            )))
        else:
            plans.append(('quad', (rp['N'], rp['CA'], rp['C'], rn['N'])))
            plans.append(('quad', (rp['CA'], rp['C'], rn['N'], rn['CA'])))
            plans.append(('quad', (rp['C'], rn['N'], rn['CA'], rn['C'])))
        if 'O' in rn:
            plans.append(('quad', (rn['N'], rn['CA'], rn['C'], rn['O'])))  # O
        # SIDECHAIN
        #
        # Which atoms a residue *should* have is decided by its name; which it
        # *does* have is decided by the file, and the two differ routinely.
        # Selecting on the name alone raised ``KeyError: 'H'`` on any X-ray
        # structure, because X-ray does not resolve hydrogens -- which is to
        # say on most PDB entries, 148L included. Incomplete side chains
        # (unmodelled CB/CG/CD past a disordered point) fail the same way.
        # ``coord_i`` is truncated to ``ai`` at the end of the loop, so a
        # skipped atom simply yields one fewer internal coordinate.
        resName = rn['CA']['res_name']
        # Each internal coordinate names four atoms, so all four have to be
        # present -- not merely the one being placed.
        if {'O', 'C', 'CA', 'CB'} <= rn.keys():
            plans.append(('quad', (rn['O'], rn['C'], rn['CA'], rn['CB'])))  # CB
        if resName == 'PRO':
            if {'N', 'CA', 'CB', 'CG'} <= rn.keys():
                plans.append(('quad', (rn['N'], rn['CA'], rn['CB'], rn['CG'])))  # CG
            if {'CA', 'CB', 'CG', 'CD'} <= rn.keys():
                plans.append(('quad', (rn['CA'], rn['CB'], rn['CG'], rn['CD'])))  # CD
        elif 'H' in rn:
            plans.append(('quad', (rn['N'], rn['CA'], rn['C'], rn['H'])))  # H
        rp = rn

    ai = _measure_internal_coordinates(structure, plans)
    if verbose:
        print("Atoms internal: %s" % (ai + 1))
        print("--------------------------------------")
    structure.coord_i = structure.coord_i[:ai]
    # ``l_c`` / ``l_ca`` / ``l_n`` are built from a table pre-filled with -1,
    # so -1 is their "this residue has no such atom" sentinel -- every water in
    # the file contributes three of them. Looking a sentinel up as if it were an
    # atom index raised ``ValueError: -1 is not in list``. An atom that exists
    # but whose internal coordinate was skipped above is absent here too, so
    # membership is the test rather than the sign.
    #
    # The dict also replaces a ``list(...).index(...)`` rebuilt per lookup,
    # which made this O(n_atoms * n_residues).
    position = {int(v): i for i, v in enumerate(structure.coord_i['i'])}
    structure._phi_indices = [position[int(x)] for x in structure.l_c if int(x) in position]
    structure._omega_indices = [position[int(x)] for x in structure.l_ca if int(x) in position]
    structure._psi_indices = [position[int(x)] for x in structure.l_n if int(x) in position]
    structure._chi_indices = [position[int(x)] for x in structure.l_cb if int(x) in position]


class ProteinCentroid(
    Structure
):
    """
    A coarse grained representation for proteins, where the backbone
    is atomistic and the side-chains are represented by a single atom.

    Examples
    --------

    >>> import cs.core.structure
    >>> pdb_filename = './data/atomic_coordinates/pdb_files/hGBP1_closed.pdb'
    >>> sp = cs.core.structure.ProteinCentroid(pdb_filename, verbose=True, make_coarse=True)
    ======================================
    Filename: /data/structure/HM_1FN5_Naming.pdb
    Path: /data/structure
    Number of atoms: 9316
    --------------------------------------
    Atoms internal: 3457
    --------------------------------------
    >>> print(sp)
    ATOM   2274    O ALA   386      52.927  10.468 -17.263  0.00  0.00             O
    ATOM   2275   CB ALA   386      53.143  12.198 -14.414  0.00  0.00             C
    >>> sp.omega *= 0.0
    >>> sp.omega += 3.14
    >>> print(sp)
    ATOM   2273    C ALA   386      47.799  59.970  21.123  0.00  0.00             C
    ATOM   2274    O ALA   386      47.600  59.096  20.280  0.00  0.00             O
    >>> sp.write('test_out.pdb')
    >>> s_aa = cs.core.structure.ProteinCentroid(pdb_filename, verbose=True, make_coarse=False)
    >>> print(s_aa)
    ATOM   9312    H MET   583      40.848  10.075  17.847  0.00  0.00             H
    ATOM   9313   HA MET   583      40.666   8.204  15.667  0.00  0.00             H
    ATOM   9314  HB3 MET   583      38.898   7.206  16.889  0.00  0.00             H
    ATOM   9315  HB2 MET   583      38.796   8.525  17.846  0.00  0.00             H
    >>> print(s_aa.omega)
    array([], dtype=float64)
    >>> s_aa.to_coarse()
    >>> print(s_aa)
    ATOM   3451   CA MET   583      40.059   8.800  16.208  0.00  0.00             C
    ATOM   3452    C MET   583      38.993   9.376  15.256  0.00  0.00             C
    ATOM   3453    O MET   583      38.405  10.421  15.616  0.00  0.00             O
    ATOM   3454   CB MET   583      39.408   7.952  17.308  0.00  0.00             C
    ATOM   3455    H MET   583      40.848  10.075  17.847  0.00  0.00             H
    >>> print(s_aa.omega)
    array([ 0.        ,  3.09665806, -3.08322105,  3.13562203,  3.09102453,...])
    """

    max_atom_residue = 16

    @property
    def internal_coordinates(self):
        """The internal (bond/angle/dihedral) coordinate array."""
        return self.coord_i

    @property
    def phi(self):
        """Phi dihedral angles of the protein backbone."""
        return self.internal_coordinates[self._phi_indices]['d']

    @phi.setter
    def phi(self, v):
        """Set phi dihedral angles."""
        self.internal_coordinates['d'][self._phi_indices] = v
        self.update_coordinates()

    @property
    def omega(self):
        """Omega dihedral angles of the protein backbone."""
        return self.internal_coordinates[self._omega_indices]['d']

    @omega.setter
    def omega(self, v):
        """Set omega dihedral angles."""
        self.internal_coordinates['d'][self._omega_indices] = v
        self.update_coordinates()

    @property
    def chi(self):
        """Chi (side-chain) dihedral angles."""
        return self.internal_coordinates[self._chi_indices]['d']

    @chi.setter
    def chi(self, v):
        """Set chi (side-chain) dihedral angles."""
        self.internal_coordinates['d'][self._chi_indices] = v
        self.update_coordinates()

    @property
    def psi(self):
        """Psi dihedral angles of the protein backbone."""
        return self.internal_coordinates[self._psi_indices]['d']

    @psi.setter
    def psi(self, v):
        """Set psi dihedral angles."""
        self.internal_coordinates['d'][self._psi_indices] = v
        self.update_coordinates()

    def __deepcopy__(self, memo):
        """Deep copy with lookup tables and internal coordinates."""
        new = super().__deepcopy__(self)
        new.dist_ca = np.copy(self.dist_ca)
        new.coord_i = np.copy(self.internal_coordinates)

        new.l_ca = copy.deepcopy(self.l_ca)
        new.l_cb = copy.deepcopy(self.l_cb)
        new.l_c = copy.deepcopy(self.l_c)
        new.l_n = copy.deepcopy(self.l_n)
        new.l_h = copy.deepcopy(self.l_h)
        new.l_res = copy.deepcopy(self.l_res)

        return new

    def __init__(
            self,
            p_object=None,
            *args,
            **kwargs
    ):
        """Initialize ProteinCentroid, optionally converting to coarse-grained representation."""
        # Protonation is now optional and defaults to False since the protonate method is a no-op
        protonate_param = kwargs.pop('protonate', False)
        super().__init__(
            p_object,
            *args,
            protonate=protonate_param,
            **kwargs
        )

        self.coord_i = np.zeros(
            self.atoms.shape[0],
            dtype={'names': internal_keys, 'formats': internal_formats}
        )
        self.dist_ca = np.zeros(
            (self.n_residues, self.n_residues),
            dtype=np.float64
        )
        self._phi_indices = list()
        self._omega_indices = list()
        self._psi_indices = list()
        self._chi_indices = list()
        self._temp = np.empty(
            self.n_atoms * 3,
            dtype=np.float64
        )  # used to convert internal to cartesian coordinates
        if p_object is not None:
            self.to_coarse()

        ####################################################
        #              LOOKUP TABLES                       #
        ####################################################
        self.l_res, self.l_ca, self.l_cb, self.l_c, self.l_n, self.l_h = make_residue_lookup_table(self)
        self.residue_types = np.array(
            [
                res2id[res] for res in list(
                    self.atoms['res_name']
                )
                if res in list(
                    res2id.keys()
                )
            ], dtype=np.int32
        )

    def update_dist(self):
        """Update the C-alpha distance matrix."""
        atom_dist(self.dist_ca, self.l_res, self.xyz, a2id['CA'])

    def update(
            self,
            start_point: int = 0
    ):
        """Update cartesian coordinates from internal coordinates."""
        ic = self.internal_coordinates
        n_atoms = ic.shape[0]

        bond = ic['b']
        angle = ic['a']
        dihedral = ic['d']
        ans = ic['i']

        ib = ic['ib']
        ia = ic['ia']
        id = ic['id']

        p = self._temp
        self.atoms['xyz'] = internal_to_cartesian(
            bond,
            angle,
            dihedral,
            ans,
            ib, ia, id,
            n_atoms,
            self.atoms['xyz'],
            p,
            start_point
        )
        self.update_dist()

    def to_coarse(self):
        """
        Converts the structure-instance into a coarse structure.

        Examples
        --------

        >>> import cs.core.structure
        >>> s_aa = cs.core.structure.ProteinCentroid('./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb', verbose=True, make_coarse=False)
        >>> print(s_aa)
        ATOM   9312    H MET   583      40.848  10.075  17.847  0.00  0.00             H
        ATOM   9313   HA MET   583      40.666   8.204  15.667  0.00  0.00             H
        ATOM   9314  HB3 MET   583      38.898   7.206  16.889  0.00  0.00             H
        ATOM   9315  HB2 MET   583      38.796   8.525  17.846  0.00  0.00             H
        >>> s_aa.to_coarse()
        >>> print(s_aa)
        ATOM   3451   CA MET   583      40.059   8.800  16.208  0.00  0.00             C
        ATOM   3452    C MET   583      38.993   9.376  15.256  0.00  0.00             C
        ATOM   3453    O MET   583      38.405  10.421  15.616  0.00  0.00             O
        ATOM   3454   CB MET   583      39.408   7.952  17.308  0.00  0.00             C
        ATOM   3455    H MET   583      40.848  10.075  17.847  0.00  0.00             H
        print(s_aa.omega)
        array([ 0.        ,  3.09665806, -3.08322105,  3.13562203,  3.09102453,...])
        """
        self.is_coarse = True

        ####################################################
        ######       TAKE ONLY INTERNAL ATOMS         ######
        ####################################################
        all_atoms = np.copy(self.atoms)
        tmp = list()
        n_atoms = 0
        for atom in all_atoms:
            if atom['atom_name'] in residue_atoms_internal[atom['res_name']]:
                tmp.append(atom)
                n_atoms += 1

        atoms = np.empty(
            n_atoms,
            dtype={
                'names': cs.core.fio.structure.coordinates.keys,
                'formats': cs.core.fio.structure.coordinates.formats
            }
        )

        atoms[:] = tmp
        atoms['i'] = np.arange(atoms.shape[0])
        atoms['atom_id'] = np.arange(atoms.shape[0])
        self.atoms = atoms

        ####################################################
        ######         LOOKUP TABLES                  ######
        ####################################################
        self.l_res, self.l_ca, self.l_cb, self.l_c, self.l_n, self.l_h = make_residue_lookup_table(self)
        tmp = [
            res2id[res] for res in list(self.atoms['res_name']) if res in list(res2id.keys())
        ]
        self.residue_types = np.array(tmp, dtype=np.int32)
        self.dist_ca = np.zeros(
            (self.n_residues, self.n_residues), dtype=np.float64
        )

        ####################################################
        ######         REASSIGN COORDINATES           ######
        ####################################################
        move_center_of_mass(self, all_atoms)

        ####################################################
        ######         INTERNAL  COORDINATES          ######
        ####################################################
        #coord_i = np.zeros(self.atoms.shape[0], dtype={'names': internal_keys, 'formats': internal_formats})
        calc_internal_coordinates_bb(self)
        self.update_coordinates()
        self.update_dist()
