"""Correctness checks for the covariance-based parameter error estimates.

Regression tests for three defects in ``covariance_matrix`` / ``approx_grad``:

* the covariance was inverted from ``0.5 * J'J`` instead of ``J'J``, inflating
  every reported error by exactly ``sqrt(2)``;
* the finite-difference step was *absolute* (``1e-12``, and the machine epsilon
  for ``Fit.grad``), so for parameters of large magnitude the perturbed model
  was bit-identical to the unperturbed one, the partial derivative evaluated to
  exactly zero, and the parameter was silently dropped from the covariance --
  leaving it with no error estimate at all;
* the failure path built ``np.zeros_like((n, n))``, a length-2 vector, instead
  of an ``n x n`` matrix.

The reference is the analytic least-squares covariance ``sigma^2 (X'X)^-1``,
which is exact for the linear model used here.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit as fit_module
import chisurf.core.fitting.sample
import chisurf.core.models.parse


def _quadratic_fit(scale: float = 1.0, seed: int = 1):
    """Fit ``c + a*x**2`` to noisy data scaled by ``scale``.

    Scaling the data (and hence the fitted parameters and sigma) leaves the
    *relative* uncertainties unchanged, so the analytic reference scales with
    it exactly -- which is what makes this a clean probe of step-size handling.

    Returns
    -------
    tuple
        The fit and the analytic standard deviations of its free parameters.
    """
    rng = np.random.default_rng(seed)
    sigma = 0.05 * scale
    x = np.linspace(0.0, 5.0, 64)
    y = scale * (3.1 + 1.2 * x ** 2) + rng.normal(0.0, sigma, x.size)

    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * sigma)
    fit = fit_module.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()

    # The analytic covariance must be built over exactly the points the
    # weighted residuals cover.
    n = len(fit.model.weighted_residuals)
    columns = {'c': np.ones(n), 'a': x[:n] ** 2}
    design = np.column_stack([columns[p.name] for p in fit.model.parameters])
    covariance = sigma ** 2 * np.linalg.inv(design.T @ design)
    return fit, np.sqrt(np.diag(covariance))


def test_covariance_matches_the_analytic_least_squares_result():
    """The covariance must be ``(J'J)^-1`` -- not twice it."""
    fit, analytic_std = _quadratic_fit()
    cov_m, used = fit.covariance_matrix

    assert used == [0, 1], "no parameter may be dropped for a well-scaled fit"
    errors = np.sqrt(np.diag(cov_m))
    # The spurious factor 1/2 showed up here as a uniform sqrt(2) inflation.
    np.testing.assert_allclose(errors, analytic_std, rtol=1e-6)


def test_update_error_estimates_writes_the_analytic_errors():
    """The errors published on the parameters are the analytic ones."""
    fit, analytic_std = _quadratic_fit()
    fit.update_error_estimates()
    for parameter, expected in zip(fit.model.parameters, analytic_std):
        assert parameter.error_estimate == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("scale", [1.0, 1e3, 1e6, 1e9])
def test_covariance_is_independent_of_parameter_magnitude(scale):
    """Large parameter values must not silently lose their error estimates.

    With the previous absolute step of ``1e-12`` every parameter was dropped
    from ``scale = 1e6`` upwards, because ``x + 1e-12 == x`` in double
    precision once ``x`` exceeds roughly ``1e4``.
    """
    fit, analytic_std = _quadratic_fit(scale=scale)
    cov_m, used = fit.covariance_matrix

    assert used == [0, 1], f"parameters dropped from the covariance at scale {scale}"
    errors = np.sqrt(np.diag(cov_m))
    np.testing.assert_allclose(errors, analytic_std, rtol=1e-6)


@pytest.mark.parametrize("scale", [1.0, 1e6])
def test_grad_is_not_identically_zero(scale):
    """``Fit.grad`` used to pass the machine epsilon, making every step a no-op."""
    fit, _ = _quadratic_fit(scale=scale)
    grad = np.asarray(fit.grad, dtype=float)

    assert grad.shape[0] == fit.model.n_free
    assert np.all(np.abs(grad).sum(axis=1) > 0.0), "gradient vanished for a free parameter"


@pytest.mark.parametrize("noise_model", ["default", "poisson"])
def test_covariance_matches_the_poisson_fisher_information(noise_model):
    """Counting-noise errors must equal the Fisher information of the counts.

    The ``poisson`` noise model minimises the ``2I*`` deviance rather than a
    weighted sum of squares, but ``sum(residuals**2)`` is still the objective,
    so ``(J'J)^-1`` remains the right covariance for both -- this pins that down
    against the analytic Poisson information matrix.
    """
    rng = np.random.default_rng(7)
    a_true, tau_true = 5000.0, 4.0
    x = np.linspace(0.05, 25.0, 256)
    y = rng.poisson(a_true * np.exp(-x / tau_true)).astype(float)

    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    fit = fit_module.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.noise_model = noise_model
    for f in fit:
        f.noise_model = noise_model
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'a*exp(-x/tau)'
    fit.model.find_parameters()
    values = fit.model.parameters_all_dict
    values['a'].value, values['tau'].value = 4000.0, 3.0
    fit.run()
    fit.update_error_estimates()

    fitted = dict(zip(fit.model.parameter_names, fit.model.parameter_values))
    a, tau = fitted['a'], fitted['tau']
    assert a == pytest.approx(a_true, rel=0.05)
    assert tau == pytest.approx(tau_true, rel=0.05)

    n = len(fit.model.weighted_residuals)
    xx = x[:n]
    mu = a * np.exp(-xx / tau)
    derivatives = {'a': mu / a, 'tau': mu * xx / tau ** 2}
    order = [p.name for p in fit.model.parameters]
    information = np.array([
        [np.sum(derivatives[j] * derivatives[k] / mu) for k in order]
        for j in order
    ])
    fisher_std = np.sqrt(np.diag(np.linalg.inv(information)))

    for parameter, expected in zip(fit.model.parameters, fisher_std):
        # A percent is tight enough to catch a scale error (the factor sqrt(2)
        # this file guards against is 41%) while tolerating the O(1/sqrt(N))
        # difference between the Gauss-Newton and the exact information matrix.
        assert parameter.error_estimate == pytest.approx(expected, rel=1e-2)


def test_covariance_errors_agree_with_the_sampled_posterior():
    """The linearised errors must match the width the sampler actually finds."""
    np.random.seed(5)
    fit, analytic_std = _quadratic_fit()
    fit.update_error_estimates()

    r = chisurf.core.fitting.sample.walk_mcmc(
        fit=fit, steps=8000, step_size=0.01, temp=1.0, thin=1
    )
    samples = np.asarray(r['parameter_values'], dtype=float)
    samples = samples[len(samples) // 5:]

    for i, parameter in enumerate(fit.model.parameters):
        assert samples[:, i].std() == pytest.approx(parameter.error_estimate, rel=0.25)
