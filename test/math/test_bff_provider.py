"""The compiled provider supplies coherent numerical arrays and fit callbacks."""

import IMP.bff as bff
import numpy as np
import pytest
from scipy import optimize, stats

from chisurf.core.math import special
from chisurf.core.math.numerics import curve_fit


def test_provider_python_and_binary_exports_agree():
    """Distribution arrays and residual directors belong to the same provider."""
    names = ("fdtr_array", "fdtrc_array", "fdtri_array", "FitResidualFunction", "FitMinimizer")
    assert all(hasattr(bff, name) for name in names)
    assert hasattr(bff._IMP_bff, "fdtr_array")
    assert hasattr(bff._IMP_bff, "FitResidualFunction_evaluate")


@pytest.mark.parametrize(
    "function,oracle,argument",
    [
        (special.fdtr, stats.f.cdf, 2.5),
        (special.fdtrc, stats.f.sf, 2.5),
        (special.fdtri, stats.f.ppf, 0.95),
    ],
)
def test_scalar_f_distribution_agrees_with_oracle(function, oracle, argument):
    """The native scalar spelling retains precision and a scalar result."""
    got = function(3, 20, argument)
    assert isinstance(got, float)
    np.testing.assert_allclose(got, oracle(argument, 3, 20), rtol=1e-12)


def test_f_distribution_broadcasts_parameters_and_preserves_shape():
    """Array paths preserve broadcasting instead of flattening the user result."""
    values = np.array([[0.1, 1.0, 3.0], [0.2, 2.0, 20.0]])
    numerator_dof = np.array([1.0, 3.0, 7.0])
    np.testing.assert_allclose(
        special.fdtr(numerator_dof, 20, values), stats.f.cdf(values, numerator_dof, 20), rtol=1e-12
    )
    np.testing.assert_allclose(
        special.fdtrc(numerator_dof, 20, values), stats.f.sf(values, numerator_dof, 20), rtol=1e-12
    )


def test_exponential_fit_recovers_lifetime_through_residual_director():
    """A real Python model fits through native MINPACK and agrees with SciPy."""

    def exponential(time, amplitude, lifetime, offset):
        """Return an analytic single exponential with an additive baseline."""
        return amplitude * np.exp(-time / lifetime) + offset

    time = np.linspace(0, 8, 256)
    truth = np.array([3.0, 1.7, 0.2])
    measured = exponential(time, *truth)
    options = dict(p0=[1.0, 1.0, 0.0], bounds=([0, 0.1, -1], [10, 10, 1]))
    got, covariance = curve_fit(exponential, time, measured, **options)
    expected, _ = optimize.curve_fit(exponential, time, measured, **options)
    np.testing.assert_allclose(got, truth, rtol=1e-6, atol=1e-9)
    np.testing.assert_allclose(got, expected, rtol=1e-6, atol=1e-9)
    assert covariance.shape == (3, 3)
    assert np.isfinite(covariance).all()
