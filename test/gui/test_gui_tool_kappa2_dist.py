"""The κ² distribution calculator, driven the way its GUI drives it.

The tool is AutoForm over a plain model object (PRD-40): the inputs are named
fields, ``compute`` runs the selected model, and the outputs are fields again.
This used to poke ``doubleSpinBox_10`` and friends — the names Designer gave
the widgets of a ``.ui`` file that no longer exists — so every test errored
with ``'Kappa2Dist' object has no attribute 'doubleSpinBox_2'``. The numbers
asserted here are the ones that file asserted.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import utils

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
utils.set_search_paths(TOPDIR)

from qtpy.QtWidgets import QApplication

import chisurf.core.fio  # noqa: F401 - registers the readers the tool imports

app = QApplication.instance() or QApplication(sys.argv)


class Tests(unittest.TestCase):
    """The cone model, with and without a known donor-acceptor anisotropy."""

    def setUp(self):
        from chisurf.plugins.calculator.kappa2_dist.k2dgui import Kappa2Dist
        self.tool = Kappa2Dist()
        self.model = self.tool._model

    def tearDown(self):
        self.tool.close()
        self.tool.deleteLater()
        QApplication.processEvents()

    def test_defaults(self):
        """The anisotropies, the histogram step and its bin count."""
        self.assertEqual(self.model.r_0, 0.380)
        self.assertEqual(self.model.r_Dinf, 0.050)
        self.assertEqual(self.model.r_Ainf, 0.100)
        self.assertEqual(self.model.step, 1.5)
        self.assertEqual(self.model.n_bins, 131)
        self.assertEqual(self.model.r_ADinf, 0.005)
        self.assertEqual(self.model.model_type, "cone")
        self.assertFalse(self.model.rAD_known)

    def test_cone_model_without_a_known_rAD(self):
        """Restricted motion widens the distribution; it does not move <k2>.

        The mean over isotropically distributed *relative* orientations is 2/3
        whatever the cones do — see test/fitting/test_kappa2_distribution.py,
        where the same invariant is pinned directly on the sampler. The values
        this file asserted before the port (0.7545, 0.1907) came from the
        octant sampling that test's docstring records as the bug it found: it
        skewed the mean, which is exactly the quantity that must not move.
        """
        self.tool._do_compute()

        self.assertAlmostEqual(self.model.k2_mean, 2.0 / 3.0, places=2)
        self.assertAlmostEqual(self.model.k2_sd, 0.217, places=2)
        self.assertAlmostEqual(self.model.Rapp_mean, 0.993, places=2)
        self.assertAlmostEqual(self.model.RappSD, 0.0517, places=3)

    def test_a_known_rAD_narrows_the_distribution(self):
        """A measured donor-acceptor anisotropy constrains the cone further.

        With rAD known the sampling is deterministic, so these are exact
        rather than sampled: the distribution is narrower (0.207 against
        0.217) and its mean is pulled off 2/3, which is what knowing the
        relative orientation does.
        """
        self.model.rAD_known = True
        self.tool._do_compute()

        self.assertAlmostEqual(self.model.k2_mean, 0.6304, places=3)
        self.assertAlmostEqual(self.model.k2_sd, 0.2072, places=3)
        self.assertAlmostEqual(self.model.Rapp_mean, 0.9840, places=3)
        self.assertAlmostEqual(self.model.RappSD, 0.0503, places=3)
        self.assertLess(self.model.k2_sd, 0.217)


if __name__ == "__main__":
    unittest.main()
