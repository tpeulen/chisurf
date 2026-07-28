"""Contract tests for the support-plane scans (RF-628, RF-633..RF-635)."""
import utils
import unittest
import pathlib

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import numpy as np

import chisurf.core.data
import chisurf.core.models.parse
import chisurf.core.fitting.fit
import chisurf.core.fitting.support_plane as support_plane


def make_fit(n_points: int = 32):
    """Build a linear-in-parameters ParseModel fit ``c + a * x**2``.

    Parameters
    ----------
    n_points : int, optional
        Number of data points.

    Returns
    -------
    chisurf.core.fitting.fit.FitGroup
        A fit whose model exposes the free parameters ``a`` and ``c``.
    """
    x_data = np.linspace(0, 32, n_points)
    y_data = 3.1 + 1.2 * x_data ** 2.0
    data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel
    )
    fit.model.func = 'c+a*x**2'
    fit.fit_range = 0, len(fit.model.y) - 1
    fit.model.update_model()
    fit.run()
    return fit


def make_noisy_fit(sign: float = 1.0, n_points: int = 64):
    """Build ``c + sign * a * x**2`` on data with a deterministic residual.

    The model is linear in ``a``, so the chi² profile of ``a`` is an exact
    parabola around the best fit and the confidence interval is exactly
    symmetric — an analytic reference for the adaptive scan.  A non-zero
    residual is required because the F-test threshold scales with chi²_min.

    Parameters
    ----------
    sign : float, optional
        Sign of the quadratic amplitude, i.e. the sign of the fitted ``a``.
    n_points : int, optional
        Number of data points.

    Returns
    -------
    chisurf.core.fitting.fit.FitGroup
        A converged fit whose model exposes the free parameters ``a`` and ``c``.
    """
    x_data = np.linspace(0, 32, n_points)
    sigma = 5.0
    residual = sigma * np.sin(np.arange(n_points) * 1.7)
    y_data = 3.1 + sign * 1.2 * x_data ** 2.0 + residual
    data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.full_like(y_data, sigma))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel
    )
    fit.model.func = 'c+a*x**2'
    fit.fit_range = 0, len(fit.model.y) - 1
    fit.model.update_model()
    fit.run()
    return fit


class AdaptiveScanBoundaryTests(unittest.TestCase):
    """A limit must truncate the scan, not coarsen it (RF-628)."""

    def test_positive_parameter_keeps_a_symmetric_interval(self):
        """The auto lower clamp must not swallow the whole lower side."""
        fit = make_noisy_fit(sign=+1.0)
        v0 = fit.model.parameters_all_dict['a'].value
        self.assertGreater(v0, 0.0)
        r = support_plane.adaptive_scan_parameter(fit=fit, parameter_name='a', p_value=0.99)
        low, high = r['crossings']
        self.assertIsNotNone(low)
        self.assertIsNotNone(high)
        self.assertAlmostEqual((high - v0) / (v0 - low), 1.0, places=2)

    def test_sign_of_the_parameter_does_not_change_the_interval(self):
        """The same data fitted as ``-a`` must give the same half-widths."""
        positive = make_noisy_fit(sign=+1.0)
        negative = make_noisy_fit(sign=-1.0)
        widths = []
        for fit in (positive, negative):
            v0 = fit.model.parameters_all_dict['a'].value
            r = support_plane.adaptive_scan_parameter(fit=fit, parameter_name='a', p_value=0.99)
            low, high = r['crossings']
            widths.append((abs(v0 - low), abs(high - v0)))
        for reference, measured in zip(widths[1], widths[0]):
            self.assertAlmostEqual(measured / reference, 1.0, places=3)

    def test_scan_stops_at_a_declared_lower_limit(self):
        """A limit inside the interval truncates the side without coarsening it."""
        fit = make_noisy_fit(sign=+1.0)
        v0 = fit.model.parameters_all_dict['a'].value
        limit = v0 - 2.0e-3
        r = support_plane.adaptive_scan_parameter(
            fit=fit, parameter_name='a', scan_range=(limit, None), p_value=0.99
        )
        values = np.asarray(r['parameter_values'])
        self.assertGreaterEqual(float(values.min()), limit - 1e-12)
        self.assertGreater(int((values < v0).sum()), 10)
        self.assertIsNone(r['crossings'][0])

    def test_limit_at_the_optimum_leaves_that_side_unscanned(self):
        """``p_min == v0`` is a limit, not an invitation to scan below it."""
        fit = make_noisy_fit(sign=+1.0)
        v0 = fit.model.parameters_all_dict['a'].value
        r = support_plane.adaptive_scan_parameter(
            fit=fit, parameter_name='a', scan_range=(v0, None), p_value=0.99
        )
        values = np.asarray(r['parameter_values'])
        self.assertEqual(int((values < v0).sum()), 0)
        self.assertIsNone(r['crossings'][0])


class SupportPlaneScanRangeTests(unittest.TestCase):
    """The scan window must honour every end the caller pinned."""

    def test_lower_end_of_scan_range_is_kept(self):
        """A pinned lower end survives an open upper end (RF-633)."""
        fit = make_fit()
        r = support_plane.scan_parameter(
            fit=fit, parameter_name='a', scan_range=(1.0, None),
            rel_range=0.2, n_steps=5
        )
        values = r['parameter_values']
        self.assertAlmostEqual(float(values[0]), 1.0, places=12)
        self.assertGreater(float(values[-1]), 1.0)

    def test_upper_end_of_scan_range_is_kept(self):
        """A pinned upper end survives an open lower end (RF-633)."""
        fit = make_fit()
        r = support_plane.scan_parameter(
            fit=fit, parameter_name='a', scan_range=(None, 2.0),
            rel_range=0.2, n_steps=5
        )
        values = r['parameter_values']
        self.assertAlmostEqual(float(values[-1]), 2.0, places=12)
        self.assertLess(float(values[0]), 2.0)

    def test_both_ends_open_uses_relative_window(self):
        """Without a scan_range the window stays the relative one."""
        fit = make_fit()
        v0 = fit.model.parameters_all_dict['a'].value
        r = support_plane.scan_parameter(
            fit=fit, parameter_name='a', scan_range=(None, None),
            rel_range=0.2, n_steps=5
        )
        values = r['parameter_values']
        self.assertAlmostEqual(float(values[0]), v0 * 0.8, places=12)
        self.assertAlmostEqual(float(values[-1]), v0 * 1.2, places=12)

    def test_inverted_scan_range_is_ordered(self):
        """An inverted (p_min > p_max) pair comes back ascending."""
        fit = make_fit()
        r = support_plane.scan_parameter(
            fit=fit, parameter_name='a', scan_range=(2.0, 1.0),
            rel_range=0.2, n_steps=5
        )
        values = r['parameter_values']
        self.assertAlmostEqual(float(values[0]), 1.0, places=12)
        self.assertAlmostEqual(float(values[-1]), 2.0, places=12)


class SupportPlaneScanWindowTests(unittest.TestCase):
    """The default window must not collapse or invert (RF-634)."""

    def test_zero_valued_parameter_scans_a_finite_window(self):
        """A parameter at zero has no relative scale, so the span is absolute."""
        fit = make_fit()
        fit.model.parameters_all_dict['a'].value = 0.0
        r = support_plane.scan_parameter(
            fit=fit, parameter_name='a', rel_range=0.2, n_steps=5
        )
        values = r['parameter_values']
        self.assertAlmostEqual(float(values[0]), -0.2, places=12)
        self.assertAlmostEqual(float(values[-1]), 0.2, places=12)
        self.assertEqual(len(np.unique(values)), 5)

    def test_negative_parameter_gives_an_ascending_axis(self):
        """A negative value keeps the window magnitude but ascends."""
        fit = make_fit()
        fit.model.parameters_all_dict['a'].value = -2.0
        r = support_plane.scan_parameter(
            fit=fit, parameter_name='a', rel_range=0.2, n_steps=5
        )
        values = r['parameter_values']
        self.assertAlmostEqual(float(values[0]), -2.4, places=12)
        self.assertAlmostEqual(float(values[-1]), -1.6, places=12)
        self.assertTrue(np.all(np.diff(values) > 0))

    def test_default_window_helper(self):
        """The window helper is symmetric, ascending and zero-safe."""
        self.assertEqual(support_plane._default_scan_window(1.0, 0.2), (0.8, 1.2))
        self.assertEqual(support_plane._default_scan_window(-2.0, 0.2), (-2.4, -1.6))
        self.assertEqual(support_plane._default_scan_window(0.0, 0.2), (-0.2, 0.2))


class SupportPlaneScanRestoreTests(unittest.TestCase):
    """A raising fit must not leave the parameter frozen (RF-635)."""

    def test_failing_fit_restores_parameter_state(self):
        """State is restored through a `finally`, not only on success."""
        fit = make_fit()
        parameter = fit.model.parameters_all_dict['a']
        value_before = parameter.value
        fixed_before = parameter.fixed
        self.assertFalse(fixed_before)

        original_run = fit.run
        calls = {'n': 0}

        def failing_run(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 3:
                raise RuntimeError('fit blew up')
            return original_run(*args, **kwargs)

        fit.run = failing_run
        try:
            with self.assertRaises(RuntimeError):
                support_plane.scan_parameter(
                    fit=fit, parameter_name='a', rel_range=0.2, n_steps=5
                )
        finally:
            fit.run = original_run

        self.assertEqual(parameter.fixed, fixed_before)
        self.assertAlmostEqual(parameter.value, value_before, places=12)


if __name__ == '__main__':
    unittest.main()
