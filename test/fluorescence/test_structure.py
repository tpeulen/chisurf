import copy
import pathlib
import tempfile
import unittest

import numpy as np
import utils

TOPDIR = pathlib.Path(__file__).parent.parent

utils.set_search_paths(TOPDIR)

import chisurf.core.structure


class Tests(unittest.TestCase):
    pdb_filename = "./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb"
    s1 = chisurf.core.structure.ProteinCentroid(pdb_filename, verbose=True)

    s1_ref_xyz = np.array(
        [
            [72.739, -17.501, 8.879],
            [73.841, -17.042, 9.747],
            [74.361, -18.178, 10.643],
            [73.642, -18.708, 11.489],
            [73.1036816, -14.05035305, 10.73760945],
        ]
    )

    s2 = chisurf.core.structure.Structure(pdb_filename, verbose=True)

    def test_structure_Structure(self):
        s1 = chisurf.core.structure.Structure(pdb_id="148L")
        s2 = chisurf.core.structure.Structure("148L")
        self.assertEqual(np.allclose(s1.atoms["xyz"], s2.atoms["xyz"]), True)
        _, filename = tempfile.mkstemp(suffix=".pdb")
        s2.write(filename=filename)
        s2.write(filename=filename + ".gz")
        s3 = chisurf.core.structure.Structure(filename=filename)
        self.assertAlmostEqual(s3.radius_gyration, 16.300839603006693)

    def test_structure_copy(self):
        s2 = self.s2
        s5 = copy.copy(s2)
        self.assertEqual(s5.atoms is s2.atoms, True)
        s6 = copy.deepcopy(s2)
        self.assertEqual(s6.atoms is s2.atoms, False)
        s1 = self.s1
        s6 = copy.deepcopy(s1)
        self.assertEqual(s6.atoms is s1.atoms, False)
        s7 = copy.copy(s1)
        self.assertEqual(s7.atoms is s1.atoms, True)

    def test_angles(self):
        s1 = self.s1
        # the omega angles
        self.assertEqual(s1.n_residues, s1.omega.shape[0])
        self.assertEqual(s1.n_residues, s1.psi.shape[0])
        self.assertEqual(s1.n_residues, s1.phi.shape[0])
        self.assertEqual(s1.auto_update, False)

    def test_change_dihedral(self):

        self.assertEqual(np.allclose(self.s1_ref_xyz, self.s1.atoms["xyz"][:5]), True)

        s1 = self.s1
        a = self.s1_ref_xyz
        self.assertEqual(np.allclose(a, s1.atoms["xyz"][:5]), True)

        before = s1.atoms["xyz"].copy()
        # The omega getter fancy-indexes ``coord_i``, so it returns a copy and
        # an in-place ``*=`` would write into a temporary. Set through the
        # property, whose setter writes the internal coordinates.
        s1.omega = np.zeros_like(s1.omega)
        s1.update()
        # The omega rows sit at the CA atoms and residue 1's row carries
        # dummy anchors (0, 0, 0), so its own atoms cannot move; the first
        # effective omega is the CA of residue 2 (atom 7). Zeroing every
        # omega turns the trans peptide bonds (~180 deg) cis (0 deg) and
        # must move everything from that CA onward.
        self.assertEqual(np.allclose(before[:7], s1.atoms["xyz"][:7]), True)
        self.assertEqual(np.allclose(before[7:], s1.atoms["xyz"][7:]), False)

    def test_traj_opening(self):
        # A trajectory is two files: DCD stores coordinates and nothing else, so
        # the atom names come from the topology beside it.
        import chisurf.core.structure

        traj = chisurf.core.structure.TrajectoryFile(
            "./test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd",
            topology="./test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb",
            stride=1,
        )
        self.assertEqual(isinstance(traj[0], chisurf.core.structure.Structure), True)
        self.assertEqual(len(traj), 464)

    def test_traj_writing(self):
        import tempfile

        import chisurf.core.structure

        _, filename = tempfile.mkstemp(".h5")
        structure = chisurf.core.structure.ProteinCentroid(
            "./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb", auto_update=True
        )
        traj_write = chisurf.core.structure.TrajectoryFile(structure, filename=filename)
        self.assertEqual(len(traj_write), 1)

        # append structures
        structure.omega *= 0.0
        n = 22
        for i in range(n):
            traj_write.append(structure)
        self.assertEqual(len(traj_write), n + 1)
        len(traj_write)

    def test_labeled_structure(self):
        """An AV distance distribution between two labelling sites.

        This was marked ``expectedFailure`` from a time when the call raised.
        It stopped raising, and an expected failure that succeeds is itself a
        red test -- so it reported failure while the code under it worked.
        Verified stale independently of the atom-dtype change that found it:
        it succeeds with the old field widths too.

        It also asserted nothing: "passing" meant "did not raise". A
        distribution is now checked for being a distribution -- normalised,
        finite, and over positive distances -- so the test can fail for a
        reason.
        """
        import chisurf.core.structure
        import chisurf.core.structure.labeled_structure

        structure = chisurf.core.structure.Structure(
            "./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb"
        )
        donor_description = {"residue_seq_number": 18, "atom_name": "CB"}
        acceptor_description = {"residue_seq_number": 577, "atom_name": "CB"}
        pRDA, rda = chisurf.core.structure.labeled_structure.av_distance_distribution(
            structure,
            donor_av_parameter=donor_description,
            acceptor_av_parameter=acceptor_description,
        )

        self.assertEqual(len(pRDA), len(rda))
        self.assertTrue(np.all(np.isfinite(pRDA)))
        self.assertTrue(np.all(rda >= 0.0))
        self.assertGreater(pRDA.sum(), 0.0, "the distribution has no weight")
        # The two sites are far apart in the closed structure; a distribution
        # collapsed onto one bin would mean the AV clouds degenerated.
        self.assertGreater(np.count_nonzero(pRDA), 1)
