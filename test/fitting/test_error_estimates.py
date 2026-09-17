"""Parameter error estimates, against scipy as an independent reference.

`covariance_matrix` returns ``(J'J)^-1`` for ``J = d(weighted residuals)/dp``.
That is the parameter covariance **only when the weights are real standard
deviations** -- which is what `calculate_weighted_residuals` assumes for its
``"default"`` noise model, and what ``curve_fit(absolute_sigma=True)`` gives.

`DataCurve` sets ``ey`` to **ones** whenever none is supplied, and that
includes an ordinary two-column ``x, y`` file. The residuals are then
unweighted, the covariance is in units of "a residual of 1", and the reported
errors were wrong by ``1/sqrt(chi2r)`` -- 22x too large on the case below.

So the errors are checked against ``scipy.optimize.curve_fit``, in both
regimes, rather than against themselves.
"""

import unittest

import numpy as np
from scipy.optimize import curve_fit

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.parse.parse import ParseModel

SIGMA = 0.05
N = 400
TRUE = (0.30, 2.00, 1.50)
START = (0.20, 1.50, 1.00)
EQUATION = "b+a1*exp(-x/t1)"


def model_f(x, b, a1, t1):
    return b + a1 * np.exp(-x / t1)


def sample():
    rng = np.random.default_rng(1)
    x = np.linspace(0.1, 10.0, N)
    y = model_f(x, *TRUE) + rng.normal(0.0, SIGMA, N)
    return x, y


def chisurf_fit(x, y, ey):
    data = DataCurve(x=x, y=y, ey=ey) if ey is not None else DataCurve(x=x, y=y)
    fit = Fit(model_class=ParseModel, data=data)
    model = fit.model
    model.func = EQUATION
    fit.fit_range = (0, len(x) - 1)
    for p, v in zip(model._parameters_equation, START):
        p.value = v
    fit.run()
    return fit, model


def errors_of(model):
    return np.array([float(p.error_estimate) for p in model.parameters])


class KnownSigmaTests(unittest.TestCase):
    """With real uncertainties the covariance is already right, and stays so."""

    def test_errors_match_scipy_absolute_sigma(self):
        x, y = sample()
        ey = np.full(N, SIGMA)
        _, model = chisurf_fit(x, y, ey)
        _, pcov = curve_fit(model_f, x, y, p0=START, sigma=ey, absolute_sigma=True)
        # 2%: chisurf's Jacobian is a finite difference, scipy's is too but
        # with a different step. This is not a tolerance on the statistics.
        np.testing.assert_allclose(errors_of(model), np.sqrt(np.diag(pcov)), rtol=0.02)

    def test_supplying_real_errors_is_not_rescaled(self):
        """The fix must not touch a dataset that carries its own sigma.

        Pinned separately because the scaling is applied on a *detected*
        condition, and a detector that fired too eagerly would silently move
        every published error bar.
        """
        x, y = sample()
        _, model = chisurf_fit(x, y, np.full(N, SIGMA))
        _, pcov = curve_fit(model_f, x, y, p0=START, sigma=np.full(N, SIGMA), absolute_sigma=True)
        got, want = errors_of(model), np.sqrt(np.diag(pcov))
        self.assertTrue(np.all(np.abs(got / want - 1.0) < 0.02), f"errors moved: {got} vs {want}")


class UnknownSigmaTests(unittest.TestCase):
    """Without uncertainties sigma must be estimated from the residuals."""

    def test_errors_match_scipy_when_no_ey_is_supplied(self):
        x, y = sample()
        _, model = chisurf_fit(x, y, None)
        _, pcov = curve_fit(model_f, x, y, p0=START, absolute_sigma=False)
        np.testing.assert_allclose(errors_of(model), np.sqrt(np.diag(pcov)), rtol=0.02)

    def test_unit_ey_is_treated_as_no_uncertainty(self):
        """An explicit array of ones is the same statement as supplying none."""
        x, y = sample()
        _, model = chisurf_fit(x, y, np.ones(N))
        _, pcov = curve_fit(model_f, x, y, p0=START, absolute_sigma=False)
        np.testing.assert_allclose(errors_of(model), np.sqrt(np.diag(pcov)), rtol=0.02)

    def test_the_unscaled_errors_would_have_been_far_too_large(self):
        """Guards the size of the defect, not just its direction.

        Without the correction the errors are ``1/sqrt(chi2r)`` too large.
        For this data that is a factor of about 22, so a test that only
        checked the sign of the change could pass on a 1% error.
        """
        x, y = sample()
        fit, model = chisurf_fit(x, y, None)
        chi2r = float(fit.chi2r)
        self.assertLess(chi2r, 0.01, "fixture no longer exercises the defect")
        unscaled = errors_of(model) / np.sqrt(chi2r)
        _, pcov = curve_fit(model_f, x, y, p0=START, absolute_sigma=False)
        ratio = unscaled / np.sqrt(np.diag(pcov))
        self.assertGreater(
            float(ratio.min()), 5.0, "the defect this guards is no longer reproduced"
        )


class ErrorsAreReportedPerParameterTests(unittest.TestCase):
    """The mapping from covariance columns to parameters."""

    def test_a_fixed_parameter_gets_no_error_and_the_rest_are_unaffected(self):
        x, y = sample()
        data = DataCurve(x=x, y=y, ey=np.full(N, SIGMA))
        fit = Fit(model_class=ParseModel, data=data)
        model = fit.model
        model.func = EQUATION
        fit.fit_range = (0, N - 1)
        by_name = {p.name: p for p in model._parameters_equation}
        by_name["b"].value = TRUE[0]
        by_name["b"].fixed = True
        by_name["a1"].value, by_name["t1"].value = START[1], START[2]
        fit.run()

        self.assertEqual([p.name for p in model.parameters], ["a1", "t1"])
        self.assertFalse(np.isfinite(by_name["b"].error_estimate))

        def held(x, a1, t1):
            return TRUE[0] + a1 * np.exp(-x / t1)

        _, pcov = curve_fit(held, x, y, p0=START[1:], sigma=np.full(N, SIGMA), absolute_sigma=True)
        np.testing.assert_allclose(
            [float(by_name["a1"].error_estimate), float(by_name["t1"].error_estimate)],
            np.sqrt(np.diag(pcov)),
            rtol=0.02,
        )

    def test_a_parameter_that_cannot_move_the_curve_reports_no_error(self):
        """It carries no covariance column, so it must not show a number."""
        x, y = sample()
        data = DataCurve(x=x, y=y, ey=np.full(N, SIGMA))
        fit = Fit(model_class=ParseModel, data=data)
        model = fit.model
        model.func = "b+a1*exp(-x/t1)+0*dead"
        fit.fit_range = (0, N - 1)
        fit.run()
        dead = {p.name: p for p in model._parameters_equation}["dead"]
        self.assertFalse(np.isfinite(dead.error_estimate))


if __name__ == "__main__":
    unittest.main()


class ResidualKernelTests(unittest.TestCase):
    """The C++ residual path must equal the numpy one it replaced.

    `calculate_weighted_residuals` needs the model's *curve*, not the model,
    so one kernel serves every model in the tree. That reach is exactly why it
    is checked against the previous implementation rather than against itself:
    a divergence here would be wrong for all of them at once, silently, in the
    innermost loop of every fit.
    """

    @staticmethod
    def numpy_reference(data, model, xmin, xmax, noise_model):
        """The implementation that was there before, verbatim in shape."""
        import chisurf.core.fitting as CF

        _, model_y = model[xmin:xmax]
        sliced = data[xmin:xmax]
        data_y, data_ey = sliced[1], sliced[3]
        ml = min(len(model_y), len(data_y))
        if CF.normalize_noise_model(noise_model) == "poisson":
            return CF.deviance_residuals(data_y[:ml], model_y[:ml])
        return np.array((data_y[:ml] - model_y[:ml]) / data_ey[:ml], dtype=np.float64)

    def test_it_matches_numpy_across_windows_lengths_and_noise_models(self):
        import chisurf.core.fitting as CF
        from chisurf.core.curve import Curve

        rng = np.random.default_rng(3)
        shapes = [(500, 500), (500, 400), (400, 500), (37, 37)]
        # Degenerate and hostile windows: empty, inverted, past the end, and
        # the negative `xmin` that means "from the end" to a Python slice and
        # would mean "clamp to zero" to a C++ window.
        windows = [(0, 500), (10, 200), (0, 10**6), (5, 5), (100, 50), (0, 1), (0, 0), (-5, 100)]
        checked = 0
        for n_data, n_model in shapes:
            for xmin, xmax in windows:
                for noise in ("default", "poisson"):
                    y = rng.uniform(1, 500, n_data)
                    data = DataCurve(x=np.arange(n_data, dtype=float), y=y, ey=np.sqrt(y))
                    model = Curve(x=np.arange(n_model, dtype=float), y=rng.uniform(1, 500, n_model))
                    want = self.numpy_reference(data, model, xmin, xmax, noise)
                    got = CF.calculate_weighted_residuals(data, model, xmin, xmax, noise)
                    with self.subTest(shape=(n_data, n_model), window=(xmin, xmax), noise=noise):
                        self.assertEqual(len(got), len(want))
                        np.testing.assert_array_equal(np.asarray(got), np.asarray(want))
                    checked += 1
        self.assertGreater(checked, 50)

    def test_the_cpp_kernel_is_actually_being_used(self):
        """Otherwise the comparison above passes by testing numpy twice."""
        import chisurf.core.fitting as CF

        self.assertIsNotNone(
            CF._bff_weighted_residuals,
            "bff's residual kernel did not resolve; every fit is on the numpy fallback",
        )

    def test_the_numpy_fallback_still_works(self):
        """It is the definition of the behaviour, and must stay reachable."""
        import chisurf.core.fitting as CF
        from chisurf.core.curve import Curve

        rng = np.random.default_rng(5)
        y = rng.uniform(1, 500, 128)
        data = DataCurve(x=np.arange(128, dtype=float), y=y, ey=np.sqrt(y))
        model = Curve(x=np.arange(128, dtype=float), y=rng.uniform(1, 500, 128))
        kernel = CF._bff_weighted_residuals
        try:
            CF._bff_weighted_residuals = None
            fallback = CF.calculate_weighted_residuals(data, model, 0, 128)
        finally:
            CF._bff_weighted_residuals = kernel
        native = CF.calculate_weighted_residuals(data, model, 0, 128)
        np.testing.assert_array_equal(np.asarray(fallback), np.asarray(native))
