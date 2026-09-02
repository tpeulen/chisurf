"""Tests for the Poisson maximum-likelihood (2I*) fit objective.

Covers the ``deviance_residuals`` helper, the ``noise_model`` selector plumbed
through :class:`~chisurf.core.fitting.fit.Fit`, and an end-to-end fit that
minimises the ``2I*`` deviance via the existing least-squares engine.
"""
import utils
import pathlib

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import numpy as np

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.models
import chisurf.core.models.parse
import chisurf.core.fitting
import chisurf.core.fitting.fit


def _two_i_star(y, mu):
    y = np.asarray(y, float)
    mu = np.asarray(mu, float)
    pos = y > 0
    ylog = np.zeros_like(y)
    ylog[pos] = y[pos] * np.log(y[pos] / mu[pos])
    return 2.0 * np.sum(mu - y + ylog)


def test_normalize_noise_model_aliases():
    n = chisurf.core.fitting.normalize_noise_model
    assert n("mle") == "poisson"
    assert n("2istar") == "poisson"
    assert n("poisson") == "poisson"
    assert n("neyman") == "default"
    assert n("wls") == "default"
    assert n(None) == "default"
    assert n("something-unknown") == "default"


def test_deviance_residuals_sum_equals_two_i_star():
    y = np.array([0.0, 5.0, 40.0, 25.0, 12.0, 0.0, 3.0])
    mu = np.array([0.5, 6.0, 38.0, 27.0, 10.0, 0.2, 2.0])
    r = chisurf.core.fitting.deviance_residuals(y, mu)
    assert np.all(np.isfinite(r))
    # sum of squared deviance residuals == 2I*  (Laurence & Chromy identity)
    assert np.isclose(np.sum(r ** 2), _two_i_star(y, mu))
    # residual sign follows (model - data)
    assert np.all(np.sign(r[mu != y]) == np.sign((mu - y)[mu != y]))


def test_deviance_residuals_zero_and_perfect_bins():
    # A perfect fit gives exactly zero deviance.
    y = np.array([0.0, 10.0, 100.0])
    r = chisurf.core.fitting.deviance_residuals(y, y.copy())
    assert np.allclose(r, 0.0)
    # An empty data bin contributes 2*mu to 2I* and is finite.
    r0 = chisurf.core.fitting.deviance_residuals(np.array([0.0]), np.array([4.0]))
    assert np.isclose(r0[0] ** 2, 2.0 * 4.0)
    # A positive count against a vanishing model stays finite (large penalty).
    rbig = chisurf.core.fitting.deviance_residuals(np.array([5.0]), np.array([0.0]))
    assert np.isfinite(rbig[0]) and rbig[0] < 0.0


def _make_fit(noise_model, y_data):
    x_data = np.linspace(1.0, 32.0, y_data.size)
    data = chisurf.core.data.DataCurve(
        x=x_data, y=y_data, ey=np.sqrt(np.clip(y_data, 1.0, None))
    )
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.model.func = "c+a*x**2"
    fit.fit_range = 0, y_data.size
    for f in fit.grouped_fits:
        f.noise_model = noise_model
    fit.model.update()
    return fit


def test_calculate_weighted_residuals_poisson_matches_helper():
    x = np.linspace(1.0, 10.0, 12)
    y = 3.0 + 1.2 * x ** 2
    model = chisurf.core.curve.Curve(x=x, y=y * 0.9)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(y))
    wr_default = chisurf.core.fitting.calculate_weighted_residuals(
        data, model, 0, y.size, noise_model="default"
    )
    wr_poisson = chisurf.core.fitting.calculate_weighted_residuals(
        data, model, 0, y.size, noise_model="poisson"
    )
    assert np.allclose(wr_default, (y - y * 0.9) / np.sqrt(y))
    assert np.allclose(wr_poisson, chisurf.core.fitting.deviance_residuals(y, y * 0.9))


def test_fit_noise_model_default_is_backwards_compatible():
    # Fit with no noise_model argument keeps the historical WLS behaviour.
    y = 3.1 + 1.2 * np.linspace(1.0, 32.0, 24) ** 2
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(
            [chisurf.core.data.DataCurve(x=np.linspace(1, 32, 24), y=y, ey=np.ones_like(y))]
        ),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    assert all(f.noise_model == "default" for f in fit.grouped_fits)


def test_poisson_fit_uses_deviance_residuals_and_recovers_parameters():
    rng = np.random.default_rng(3)
    x = np.linspace(1.0, 32.0, 48)
    true_c, true_a = 20.0, 1.5
    mu = true_c + true_a * x ** 2
    y = rng.poisson(mu).astype(float)

    fit = _make_fit("poisson", y)

    # The reported weighted residuals are the signed Poisson deviance residuals,
    # evaluated over the active fit window [xmin, xmax).
    xmin, xmax = fit.xmin, fit.xmax
    mu = np.asarray(fit.model.y[xmin:xmax], dtype=float)
    yy = y[xmin:xmax]
    ml = min(mu.size, yy.size)
    wres = np.asarray(fit.selected_fit.weighted_residuals.y, dtype=float)
    expected = chisurf.core.fitting.deviance_residuals(yy[:ml], mu[:ml])
    assert np.allclose(wres[:ml], expected)

    # chi2 equals 2I* (sum of squared deviance residuals) over the window.
    assert np.isclose(fit.chi2, _two_i_star(yy[:ml], mu[:ml]))

    fit.run()
    fit.run()
    assert abs(fit.model.parameter_dict["c"].value - true_c) < 8.0
    assert abs(fit.model.parameter_dict["a"].value - true_a) < 0.2
    # A good Poisson fit has reduced 2I* close to 1.
    assert 0.4 < fit.chi2r < 2.0
