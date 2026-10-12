import os
from copy import deepcopy, copy
from collections import OrderedDict
import tempfile

import numpy as np

from chisurf.plugins.quenching_estimator.core.structure import reader as PDB

import os.path


clusterCriteria = ['maxclust', 'inconsistent', 'distance']


#: Backbone atom slots for the per-residue lookup table below. Only these
#: positions are indexed; a residue's remaining side-chain atoms are found by
#: name when they are needed, not tabulated here.
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

#: The residues QuEst indexes, in a fixed order — `res2id` turns a three-letter
#: code into the integer `Structure.residue_types` carries. PRO is the one with
#: extra entries, because its ring closes through CG and CD.
residue_atoms_internal = OrderedDict(
    [
        (residue, ['N', 'C', 'CA', 'CB', 'O', 'H'])
        for residue in (
            'CYS', 'MET', 'PHE', 'ILE', 'LEU', 'VAL', 'TRP', 'TYR', 'ALA',
            'THR', 'SER', 'GLN', 'ASN', 'GLU', 'ASP', 'HIS', 'ARG', 'LYS',
        )
    ]
    + [
        ('GLY', ['N', 'C', 'CA', 'O', 'H']),
        ('PRO', ['N', 'C', 'CA', 'CB', 'O', 'H', 'CG', 'CD']),
    ]
)

a2id = dict(internal_atom_numbers)
id2a = {number: name for name, number in internal_atom_numbers}
res2id = {residue: index for index, residue in enumerate(residue_atoms_internal)}


#: Helpers the `Structure` class itself needs. Everything else that used to live
#: at module level here — RMSD, clustering, torsion/internal coordinates,
#: `r2i`, and the geometry primitives behind them — had no caller anywhere in
#: QuEst and is gone. That is IMP's and ChiSurf's work, not a simulation
#: engine's (okf/specs/imp-tricks-dedup.md).


def move_center_of_mass(structure, all_atoms):
    """Fold each residue's side chain into its CB pseudo-atom.

    Grouped on ``residue_index`` -- the reader's ``(chain, res_id,
    insertion_code)`` identity -- not on ``res_id``. Matching on ``res_id``
    alone gathered *every* chain's residue 40 into one centre of mass, so in any
    multi-chain structure one chain's side chains were folded into another's CB.

    The enumeration also has to agree with the row order of ``structure.l_cb``,
    which `make_residue_lookup_table` fills from ``residue_dict``. Both now
    iterate ``residue_indices``; they used to be built from two independently
    constructed orderings that agreed only because each happened to iterate a
    ``set()`` of small integers.
    """
    for i, res in enumerate(structure.residue_indices):
        at_nbr = np.where(all_atoms['residue_index'] == res)[0]
        cb_nbr = structure.l_cb[i]
        if cb_nbr > 0:
            cb = structure.atoms[cb_nbr]
            cb['coord'] *= cb['mass']
            for at in at_nbr:
                atom = all_atoms[at]
                residue_name = atom['res_name']
                # A residue with no coarse template has no "side chain" to fold
                # into a CB; its atoms are kept whole by `to_coarse` and must
                # not be collapsed into somebody else's centre of mass.
                if residue_name not in residue_atoms_internal:
                    continue
                if atom['atom_name'] not in residue_atoms_internal[residue_name]:
                    cb['coord'] += atom['coord'] * atom['mass']
                    cb['mass'] += atom['mass']
            cb['coord'] /= cb['mass']
            structure.atoms[cb_nbr] = cb

def make_residue_lookup_table(structure):
    l_residue = np.zeros((structure.n_residues, structure.max_atom_residue), dtype=np.int32) - 1
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

def get_residue_sequence(structure):
    try:
        residue_dict = structure.residue_dict
        return [residue_dict[key]['C']['res_name'] for key in list(residue_dict.keys())]
    except KeyError:
        return structure.io.sequence(structure)


class Structure(object):

    max_atom_residue = 16

    def __init__(self, filename=None, make_coarse=True, verbose=False, auto_update=True):
        """

        Attributes
        ----------
        max_atom_residue : int
            Maximum atoms per residue. The maximum atoms per residue have to be limited, because of the
            residue/atom lookup tables. By default maximum 16 atoms per residue are allowed.

        xyz : numpy-array
            The xyz-attribute is an array of the cartesian coordinates represented by the attribute atom

        residue_names: list
            residue names is a list of the residue-names. Here the residues are represented by the same
            name as the initial PDB-file, usually 3-letter amino-acid code. The residue_names attribute
            may look like: ['TYR', 'HIS', 'ARG']

        n_atoms: int
            The number of atoms

        b_factos: array
            An array of the b-factors.

        radius_gyration: float
            The attribute radius_gyration returns the radius of gyration of the structure. The radius of gyration
            is given by: rG = (np.sqrt((coord - rM) ** 2).sum(axis=1)).mean()
            Here rM are the mean coordinates of the structure.


        Parameters
        ----------
        :param filename: str
            Path to the pdb file on disk
        :param make_coarse: bool
            Conversion to coarse representation using internal coordinates. Side-chains are
            not considered. The Cbeta-atoms is moved to center of mass of the side-chain.
        :param verbose: bool
            print output to stdout
        :param auto_update: bool
            update cartesian-coordiantes automatically after change of internal coordinates.
            This only applies for coarse-grained coordinates

        Examples
        --------
        >>>         >>> s_coarse = lib.Structure('/sample_data/structure/HM_1FN5_Naming.pdb', verbose=True, make_coarse=True)
        ======================================
        Filename: /sample_data/structure/HM_1FN5_Naming.pdb
        Path: /sample_data/structure
        Number of atoms: 9316
        --------------------------------------
        Atoms internal: 3457
        --------------------------------------
        >>> print s_coarse
        ATOM   2274    O ALA   386      52.927  10.468 -17.263  0.00  0.00             O
        ATOM   2275   CB ALA   386      53.143  12.198 -14.414  0.00  0.00             C
        >>> s_coarse.omega *= 0.0
        >>> s_coarse.omega += 3.14
        >>> print s_coarse
        ATOM   2273    C ALA   386      47.799  59.970  21.123  0.00  0.00             C
        ATOM   2274    O ALA   386      47.600  59.096  20.280  0.00  0.00             O
        >>> s_coarse.write('test_out.pdb')
        >>> s_aa = lib.Structure('/sample_data/structure/HM_1FN5_Naming.pdb', verbose=True, make_coarse=False)
        >>> print s_aa
        ATOM   9312    H MET   583      40.848  10.075  17.847  0.00  0.00             H
        ATOM   9313   HA MET   583      40.666   8.204  15.667  0.00  0.00             H
        ATOM   9314  HB3 MET   583      38.898   7.206  16.889  0.00  0.00             H
        ATOM   9315  HB2 MET   583      38.796   8.525  17.846  0.00  0.00             H
        >>> print s_aa.omega
        array([], dtype=float64)
        >>> s_aa.to_coarse()
        >>> print s_aa
        ATOM   3451   CA MET   583      40.059   8.800  16.208  0.00  0.00             C
        ATOM   3452    C MET   583      38.993   9.376  15.256  0.00  0.00             C
        ATOM   3453    O MET   583      38.405  10.421  15.616  0.00  0.00             O
        ATOM   3454   CB MET   583      39.408   7.952  17.308  0.00  0.00             C
        ATOM   3455    H MET   583      40.848  10.075  17.847  0.00  0.00             H
        print s_aa.omega
        array([ 0.        ,  3.09665806, -3.08322105,  3.13562203,  3.09102453,...])
        """

        super(Structure, self).__init__()
        self.is_coarse = make_coarse
        self.verbose = verbose
        self.auto_update = auto_update
        self.io = PDB

        if filename is not None:
            self.filename = filename

            ####################################################
            ######         PREPARE   COORDINATES          ######
            ####################################################
            self.atoms = self.io.read(filename, verbose=self.verbose)

            ####################################################
            ######         LOOKUP TABLES                  ######
            ####################################################
            self.l_res, self.l_ca, self.l_cb, self.l_c, self.l_n, self.l_h = make_residue_lookup_table(self)
            self.residue_types = np.array([res2id[res] for res in list(self.atoms['res_name'])
                                           if res in list(res2id.keys())], dtype=np.int32)
            self.dist_ca = np.zeros((self.n_residues, self.n_residues), dtype=np.float64)


            self.sequence = get_residue_sequence(self)

        if make_coarse:
            self.to_coarse()

    def to_coarse(self):
        """
        Converts the structure-instance into a coarse structure.

        Examples
        --------

        >>> s_aa = lib.Structure('/sample_data/structure/HM_1FN5_Naming.pdb', verbose=True, make_coarse=False)
        >>> print s_aa
        ATOM   9312    H MET   583      40.848  10.075  17.847  0.00  0.00             H
        ATOM   9313   HA MET   583      40.666   8.204  15.667  0.00  0.00             H
        ATOM   9314  HB3 MET   583      38.898   7.206  16.889  0.00  0.00             H
        ATOM   9315  HB2 MET   583      38.796   8.525  17.846  0.00  0.00             H
        >>> s_aa.to_coarse()
        >>> print s_aa
        ATOM   3451   CA MET   583      40.059   8.800  16.208  0.00  0.00             C
        ATOM   3452    C MET   583      38.993   9.376  15.256  0.00  0.00             C
        ATOM   3453    O MET   583      38.405  10.421  15.616  0.00  0.00             O
        ATOM   3454   CB MET   583      39.408   7.952  17.308  0.00  0.00             C
        ATOM   3455    H MET   583      40.848  10.075  17.847  0.00  0.00             H
        print s_aa.omega
        array([ 0.        ,  3.09665806, -3.08322105,  3.13562203,  3.09102453,...])
        """
        self.is_coarse = True

        ####################################################
        ######       TAKE ONLY INTERNAL ATOMS         ######
        ####################################################
        all_atoms = np.copy(self.atoms)
        # Residues with no coarse template -- ligands, cofactors, modified
        # residues -- are kept **whole**. Coarse-graining reduces an amino acid
        # to its backbone plus CB; a bound sugar has no such reduction, and
        # dropping it would silently reinstate the HETATM stripping that
        # `quest/core/structure/reader.py` deliberately stopped doing. Before this, keeping
        # HETATM records raised `KeyError: 'FGA'` here.
        tmp = [
            atom for atom in all_atoms
            if atom['res_name'] not in residue_atoms_internal
            or atom['atom_name'] in residue_atoms_internal[atom['res_name']]
        ]
        atoms = np.empty(len(tmp), dtype={'names': PDB.keys, 'formats': PDB.formats})
        atoms[:] = tmp
        atoms['i'] = np.arange(atoms.shape[0])
        atoms['atom_id'] = np.arange(atoms.shape[0])
        self.atoms = atoms

        ####################################################
        ######         LOOKUP TABLES                  ######
        ####################################################
        self.l_res, self.l_ca, self.l_cb, self.l_c, self.l_n, self.l_h = make_residue_lookup_table(self)
        tmp = [res2id[res] for res in list(self.atoms['res_name']) if res in list(res2id.keys())]
        self.residue_types = np.array(tmp, dtype=np.int32)
        self.dist_ca = np.zeros((self.n_residues, self.n_residues), dtype=np.float64)

        ####################################################
        ######         REASSIGN COORDINATES           ######
        ####################################################
        move_center_of_mass(self, all_atoms)

        self.sequence = get_residue_sequence(self)

    @property
    def xyz(self):
        return self.atoms['coord']

    @xyz.setter
    def xyz(self, v):
        self.atoms['coord'] = v

    @property
    def vdw(self):
        return self.atoms['radius']

    @vdw.setter
    def vdw(self, v):
        self.atoms['radius'] = v

    @property
    def residue_names(self):
        res_name = list(set(self.atoms['res_name']))
        res_name.sort()
        return res_name

    @property
    def residue_dict(self):
        """Atoms grouped by residue, keyed by ``residue_index``.

        **Not by ``res_id``.** It was until 2026-07-28, and residue numbers
        restart per chain: on `tests/data/mc4r_dimer.cif` all 534 ids occur in
        both chains, so every entry held the union of two residues' atoms and
        whichever chain came second overwrote the first, atom name by atom name.
        Everything derived from this -- the CA/CB/C/N/H lookup tables, the
        sequence, the dihedrals, which CB a labelling site attaches to --
        inherited that.
        """
        residue_dict = OrderedDict()
        for res in self.residue_indices:
            at_nbr = np.where(self.atoms['residue_index'] == res)
            residue_dict[res] = OrderedDict()
            for atom in self.atoms[at_nbr]:
                residue_dict[res][atom['atom_name']] = atom
        return residue_dict

    @property  # OK
    def n_atoms(self):
        return len(self.atoms)

    @property  # OK
    def n_residues(self):
        return len(self.residue_indices)

    @property  # OK
    def atom_types(self):
        return set(self.atoms['atom_name'])

    @property  # OK
    def residue_indices(self):
        """Every distinct residue in this structure, in file order.

        The identity is ``(chain, res_id, insertion_code)``, resolved to an
        integer by the reader. Iterate this to walk residues; `residue_ids`
        below answers a different question and must not be used for grouping.
        """
        return sorted({int(index) for index in self.atoms['residue_index']})

    @property  # OK
    def residue_ids(self):
        """The distinct residue *numbers*, for display.

        Ambiguous by construction in a multi-chain structure -- two chains share
        almost all of them. Grouping on this is the defect fixed on 2026-07-28;
        use `residue_indices`.
        """
        return sorted({int(res_id) for res_id in self.atoms['res_id']})

    @property  # OK
    def b_factors(self):
        bfac = self.atoms[self.l_ca]['bfactor']
        return bfac

    @property
    def radius_gyration(self):
        coord = self.xyz
        rM = coord[:, :].mean(axis=0)
        rG = (np.sqrt((coord - rM) ** 2).sum(axis=1)).mean()
        return float(rG)

    def update_coordinates(self):
        if self.auto_update:
            self.update()

    def update_dist(self):
        raise NotImplementedError(
            "CA-distance matrices require the cStructure extension, which is not "
            "part of QuEst. Compute distances from Structure.xyz instead."
        )

    def update(self, start_point=0):
        """Rebuild cartesian coordinates from the internal (torsion) ones.

        Requires the cStructure extension module, which QuEst does not ship.
        Coarse-graining does not depend on this: it writes cartesian
        coordinates directly.
        """
        raise NotImplementedError(
            "Rebuilding cartesian coordinates from torsion angles requires the "
            "cStructure extension, which is not part of QuEst."
        )

    def write(self, filename=None, append=False):
        if filename is None:
            filename = self.filename
        aw = np.copy(self.atoms)
        aw['coord'] = self.xyz
        self.io.write(filename, aw, append=append)

    def __str__(self):
        if self.atoms is None:
            return ""
        else:
            s = ""
            for at in self.atoms:
                s += "%-6s%5d %4s%1s%3s %1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2s%2s\n" % \
                     ("ATOM ",
                      at['atom_id'], at['atom_name'], " ", at['res_name'], at['chain'],
                      at['res_id'], " ",
                      at['coord'][0], at['coord'][1], at['coord'][2],
                      0.0, 0.0, "  ", at['element'])
            return s

    def __deepcopy__(self, memo):
        new = copy(self)
        new.atoms = np.copy(self.atoms)
        new.dist_ca = np.copy(self.dist_ca)
        new.filename = copy(self.filename)
        new.io = self.io

        new.l_ca = deepcopy(self.l_ca)
        new.l_cb = deepcopy(self.l_cb)
        new.l_c = deepcopy(self.l_c)
        new.l_n = deepcopy(self.l_n)
        new.l_h = deepcopy(self.l_h)
        new.l_res = deepcopy(self.l_res)

        return new
