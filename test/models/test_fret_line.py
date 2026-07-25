"""The model-driven FRET-line generator.

A FRET line is the locus a population must occupy in the plane of efficiency
against donor lifetime. These tests check that the generator produces a line
obeying the relations that define one, and that it agrees with the independent
analytic implementation in :mod:`chisurf.core.fluorescence.fret.lines`.

They used to assert frozen coefficient strings and lifetime arrays instead —
values that pinned one implementation on one distance axis, and that were
computed with ``np.logspace(np.log(1), np.log(500))``. ``logspace`` takes base-10
exponents, so that "1 to 500 Å" axis actually ran to 10**6.2 ≈ 1.6 million Å.
The axis is also a module global, and nothing put it back, so those tests
silently changed the grid for every test that ran after them.
"""

import unittest

import numpy as np

import chisurf.core.fluorescence.fret.fret_line
import chisurf.core.models
from chisurf.core.fluorescence.fret.fret_line import FRETLineGenerator

#: Donor-acceptor distance axis used throughout: 1 to 500 Å, log-spaced.
RDA_AXIS = np.logspace(np.log10(1.0), np.log10(500.0), 128)


class Tests(unittest.TestCase):

    def setUp(self):
        """Pin the distance axis these tests compute on."""
        self._rda_axis = chisurf.core.models.tcspc.fret.rda_axis
        chisurf.core.models.tcspc.fret.rda_axis = RDA_AXIS

    def tearDown(self):
        """Put the module-global distance axis back.

        Every distance distribution in the process is built on this global, so
        leaving one test's axis in place changes the grid for every test that
        runs afterwards — in another file, with a traceback pointing anywhere
        but here.
        """
        chisurf.core.models.tcspc.fret.rda_axis = self._rda_axis

    # ── helpers ──
    def _gaussian_line(self, n_points=20, parameter_range=(20.0, 100.0)):
        """A generator over a single Gaussian distance distribution."""
        fl = FRETLineGenerator(n_points=n_points, parameter_range=parameter_range)
        fl.model = chisurf.core.models.tcspc.fret.GaussianModel
        fl.model.gaussians.append(55.0, 10, 1.0)
        fl.model.find_parameters()
        fl.model.parameter_dict['xDOnly'].value = 0.0
        fl.parameter_name = 'R(G,1)'
        return fl

    def _tau_d0(self, fl):
        """The donor-only lifetime the line is anchored on."""
        return fl.donor_species_averaged_lifetime

    # ── the relations that define a FRET line ──
    def test_lifetime_averages_obey_their_inequality(self):
        """The fluorescence average is never below the species average.

        ``<tau>_F = sum(a tau^2) / sum(a tau) >= <tau>_x`` by Cauchy-Schwarz, with
        equality only for a single lifetime. Both stay below the donor-only
        lifetime, because FRET can only shorten the donor decay.
        """
        fl = self._gaussian_line()
        tau_d0 = self._tau_d0(fl)
        self.assertGreaterEqual(fl.fret_fluorescence_averaged_lifetime,
                                fl.fret_species_averaged_lifetime)
        self.assertGreater(fl.fret_species_averaged_lifetime, 0.0)
        self.assertLess(fl.fret_fluorescence_averaged_lifetime, tau_d0 * 1.001)

    def test_efficiency_follows_the_species_averaged_lifetime(self):
        """``E = 1 - <tau>_x / tau_D(0)`` — the definition the line rests on."""
        fl = self._gaussian_line()
        expected = 1.0 - fl.fret_species_averaged_lifetime / self._tau_d0(fl)
        self.assertAlmostEqual(fl.transfer_efficiency, expected, places=10)
        self.assertGreaterEqual(fl.transfer_efficiency, 0.0)
        self.assertLessEqual(fl.transfer_efficiency, 1.0)

    def test_moving_the_acceptor_away_lengthens_the_lifetime(self):
        """A larger mean distance means less transfer: tau up, E down."""
        fl = self._gaussian_line()
        fl.model.parameter_dict['R(G,1)'].value = 40.0
        tau_close = fl.fret_species_averaged_lifetime
        efficiency_close = fl.transfer_efficiency

        fl.model.parameter_dict['R(G,1)'].value = 70.0
        self.assertGreater(fl.fret_species_averaged_lifetime, tau_close)
        self.assertLess(fl.transfer_efficiency, efficiency_close)

    def test_swept_line_is_monotonic_and_within_bounds(self):
        """Sweeping the distance walks the line from high to low efficiency."""
        fl = self._gaussian_line(n_points=25, parameter_range=(20.0, 120.0))
        fl.update()
        tau_d0 = self._tau_d0(fl)

        self.assertEqual(len(fl.parameter_values), 25)
        self.assertEqual(len(fl.species_averaged_lifetimes), 25)
        self.assertEqual(len(fl.fluorescence_averaged_lifetimes), 25)
        self.assertTrue(np.all(np.diff(fl.species_averaged_lifetimes) > 0))
        self.assertTrue(np.all(np.diff(fl.fret_efficiencies) < 0))
        self.assertTrue(np.all(fl.fluorescence_averaged_lifetimes
                               >= fl.species_averaged_lifetimes - 1e-9))
        self.assertTrue(np.all(fl.species_averaged_lifetimes <= tau_d0 * 1.001))
        self.assertTrue(np.all((fl.fret_efficiencies >= -1e-9)
                               & (fl.fret_efficiencies <= 1.0 + 1e-9)))

    def test_conversion_function_is_a_polynomial_in_tau_f(self):
        """The exported string is the tau_x(tau_f) polynomial, not a fixed hash."""
        fl = self._gaussian_line()
        fl.update()
        string = fl.conversion_function_string

        self.assertEqual(string.count('*x^'), fl.polynomial_degree + 1)
        for power in range(fl.polynomial_degree + 1):
            self.assertIn(f'*x^{power}', string)
        # the same polynomial, reused by the two derived export strings
        self.assertIn(string, fl.transfer_efficency_string)
        self.assertIn(string, fl.fdfa_string)

        coefficients = np.asarray(fl.polynom_coefficients, dtype=float)
        self.assertEqual(coefficients.size, fl.polynomial_degree + 1)
        self.assertTrue(np.all(np.isfinite(coefficients)))

    # ── agreement with the independent analytic implementation ──
    def test_static_line_matches_the_analytic_line(self):
        """The generated static line is the one the analytic module computes.

        Compared at matched lifetime rather than at matched mean distance: the
        two discretize P(R) differently, so equal R is not the same point on the
        line, while equal tau_f is.
        """
        from chisurf.core.fluorescence.fret.lines import static_fret_line

        fl = chisurf.core.fluorescence.fret.fret_line.StaticFRETLine(
            n_points=40, parameter_range=(20.0, 120.0)
        )
        fl.update()
        tau_d0 = self._tau_d0(fl)
        analytic = static_fret_line(
            tau_d0,
            r0=fl.model.parameters_all_dict['R0'].value,
            sigma=fl.sigma,
            distance_range=(10.0, 200.0),
            n_points=400,
        )
        inside = ((fl.fluorescence_averaged_lifetimes > 0.2)
                  & (fl.fluorescence_averaged_lifetimes < 0.95 * tau_d0))
        self.assertTrue(inside.any())
        difference = np.abs(
            fl.fret_efficiencies[inside]
            - analytic.efficiency_at(fl.fluorescence_averaged_lifetimes[inside])
        )
        self.assertLess(float(np.max(difference)), 0.02)

    # ── the concrete generators ──
    def test_static_fret_line_defaults(self):
        """Fixed model constants are reachable, and the sweep respects its range."""
        fl = chisurf.core.fluorescence.fret.fret_line.StaticFRETLine(
            n_points=50, parameter_range=(10, 100)
        )
        # R0 and t0 are fixed parameters, so they live in parameters_all_dict;
        # parameter_dict holds only what a fit would vary.
        self.assertAlmostEqual(fl.model.parameters_all_dict['R0'].value, 52.0, places=5)
        self.assertAlmostEqual(fl.model.parameters_all_dict['t0'].value, 4.0, places=5)

        fl.sigma = 6.0
        self.assertAlmostEqual(fl.model.parameters_all_dict['s(G,1)'].value, 6.0, places=5)

        fl.update()
        self.assertEqual(len(fl.parameter_values), 50)
        self.assertGreaterEqual(fl.parameter_values[0], 10)
        self.assertLessEqual(fl.parameter_values[-1], 100)
        x, y = fl.conversion_function
        self.assertEqual((len(x), len(y)), (50, 50))

    def test_dynamic_fret_line_defaults(self):
        """The two limiting states are set up as asked, and the sweep is a fraction."""
        fl = chisurf.core.fluorescence.fret.fret_line.DynamicFRETLine(
            distance_1=40.0, distance_2=80.0, sigma_1=6.0, sigma_2=6.0,
            n_points=50, parameter_range=(0, 1)
        )
        self.assertAlmostEqual(fl.model.parameters_all_dict['R0'].value, 52.0, places=5)
        self.assertAlmostEqual(fl.model.parameters_all_dict['t0'].value, 4.0, places=5)
        self.assertAlmostEqual(fl.model.parameter_dict['R(G,1)'].value, 40.0, places=5)
        self.assertAlmostEqual(fl.model.parameter_dict['R(G,2)'].value, 80.0, places=5)
        self.assertAlmostEqual(fl.model.parameters_all_dict['s(G,1)'].value, 6.0, places=5)
        self.assertAlmostEqual(fl.model.parameters_all_dict['s(G,2)'].value, 6.0, places=5)

        fl.update()
        self.assertEqual(len(fl.parameter_values), 50)
        self.assertGreaterEqual(fl.parameter_values[0], 0)
        self.assertLessEqual(fl.parameter_values[-1], 1)
        x, y = fl.conversion_function
        self.assertEqual((len(x), len(y)), (50, 50))
        self.assertTrue(np.all(x >= y - 1e-9))     # <tau>_F >= <tau>_x along the line

    def test_dynamic_line_lies_between_its_two_states(self):
        """Mixing two states cannot leave the interval their lifetimes span."""
        fl = chisurf.core.fluorescence.fret.fret_line.DynamicFRETLine(
            distance_1=40.0, distance_2=80.0, sigma_1=6.0, sigma_2=6.0,
            n_points=20, parameter_range=(0, 1)
        )
        fl.update()
        tau_x = fl.species_averaged_lifetimes
        self.assertTrue(np.all(tau_x >= min(tau_x[0], tau_x[-1]) - 1e-9))
        self.assertTrue(np.all(tau_x <= max(tau_x[0], tau_x[-1]) + 1e-9))

    def test_orientation_mode_aliases(self):
        """Orientation-mode spellings map onto the canonical modes."""
        from chisurf.core.models.tcspc.fret import OrientationParameter

        self.assertEqual(OrientationParameter(orientation_mode='slow_isotropic').mode, 'slow')
        self.assertEqual(OrientationParameter(orientation_mode='fast_isotropic').mode, 'fast')


if __name__ == '__main__':
    unittest.main()
