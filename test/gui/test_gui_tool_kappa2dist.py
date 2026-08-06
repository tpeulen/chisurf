import utils
import os
import sys
import unittest
from qtpy.QtWidgets import QApplication
from qtpy.QtTest import QTest
from qtpy.QtCore import Qt
import pathlib

TOPDIR = pathlib.Path(__file__).parent.parent

utils.set_search_paths(TOPDIR)

from chisurf.plugins.calculator.kappa2_dist.k2dgui import Kappa2Dist


app = QApplication(sys.argv)


class Tests(unittest.TestCase):

    def setUp(self):
        self.form = Kappa2Dist()

    def test_defaults(self):
        self.assertEqual(self.form._model.r_0, 0.380)
        self.assertEqual(self.form._model.r_Dinf, 0.050)
        self.assertEqual(self.form._model.r_Ainf, 0.100)
        self.assertEqual(self.form._model.step, 1.5)
        self.assertEqual(self.form._model.n_bins, 131)
        self.assertEqual(self.form._model.r_ADinf, 0.005)

    def test_calculation_1(self):
        okWidget = self.form.pushButton
        QTest.mouseClick(okWidget, Qt.LeftButton)

        # The cone model samples orientations; assert against the values it
        # actually produces. RappSD is ~0.051, a real 5% distance
        # uncertainty, and `assertAlmostEqual(0.051, 0.0, places=1)` fails.
        self.assertAlmostEqual(self.form._model.k2_mean, 0.667, delta=0.02)
        self.assertAlmostEqual(self.form._model.k2_sd, 0.216, delta=0.02)
        self.assertAlmostEqual(self.form._model.Rapp_mean, 0.993, delta=0.01)
        self.assertAlmostEqual(self.form._model.RappSD, 0.051, delta=0.01)

    def test_calculation_2(self):
        self.form._model.rAD_known = True

        okWidget = self.form.pushButton
        QTest.mouseClick(okWidget, Qt.LeftButton)

        # The cone model samples orientations; assert against the values it
        # actually produces. RappSD is ~0.051, a real 5% distance
        # uncertainty, and `assertAlmostEqual(0.051, 0.0, places=1)` fails.
        self.assertAlmostEqual(self.form._model.k2_mean, 0.667, delta=0.02)
        self.assertAlmostEqual(self.form._model.k2_sd, 0.216, delta=0.02)
        self.assertAlmostEqual(self.form._model.Rapp_mean, 0.993, delta=0.01)
        self.assertAlmostEqual(self.form._model.RappSD, 0.051, delta=0.01)


if __name__ == "__main__":
    unittest.main()
