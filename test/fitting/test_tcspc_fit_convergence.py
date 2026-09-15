"""End-to-end headless TCSPC fit: does a lifetime fit recover known parameters?

A two-exponential decay convolved with a measured IRF, fitted through
ChiSurf's fit object on the described lifetime model (BFF's
``tcspc_lifetime``). From a poor start the fit must find the truth, from the
truth it must not walk away, and the amplitudes must stay finite on the way.
"""
import numpy as np
import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.curve
import chisurf.core.data
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.description import for_family

TRUE_TAUS = (4.0, 1.2)
TRUE_AMPS = (0.7, 0.3)
N_CHANNELS = 1024
DT = 0.032
PERIOD = 25.0
BACKGROUND = 10.0


def _build(start, n_photons=2e6, seed=0):
    t = np.arange(N_CHANNELS) * DT
    irf_y = np.exp(-0.5 * ((t - 1.0) / 0.25) ** 2) * 1e4
    pure = sum(a * np.exp(-t / tau) for a, tau in zip(TRUE_AMPS, TRUE_TAUS))
    conv = np.convolve(pure, irf_y / irf_y.sum())[:N_CHANNELS]
    conv = conv / conv.sum() * n_photons + BACKGROUND
    y = np.random.default_rng(seed).poisson(conv).astype(float)

    fit = Fit(model_class=for_family("tcspc_lifetime"),
              data=chisurf.core.data.DataCurve(x=t, y=y, ey=np.sqrt(np.maximum(y, 1.0))),
              xmin=0, xmax=N_CHANNELS - 1)
    m = fit.model
    m.set_dataset("response", chisurf.core.curve.Curve(x=t, y=irf_y))
    m.set_scalar("period", PERIOD)
    m.set_scalar("periodic_excitation", 0.0)
    m.set_scalar("autoscale", 1.0)
    assert m.problem is not None, m.missing
    m.structure = "lifetime.components.2"
    parameters = {p.canonical_id: p for p in m.parameters_all}
    for k, (a, tau) in enumerate(start):
        parameters[f"lifetime.amplitude.{k}"].value = a
        parameters[f"lifetime.tau.{k}"].value = tau
    parameters["instrument.background"].value = BACKGROUND
    # np.convolve samples each channel at its left edge, half a channel off the
    # bin-integrated instrument: the shift is fitted rather than assumed.
    parameters["instrument.timeshift"].fixed = False
    m.update()
    return fit, m


def _chi2r(fit):
    fit.model.update()
    return float(fit.chi2r)


def _taus(m):
    return sorted(p.value for p in m.parameters_all if p.canonical_id in ("lifetime.tau.0", "lifetime.tau.1"))


def test_fixture_is_self_consistent():
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    y = np.asarray(m.y, dtype=float)
    assert y.max() > 10 * y.min(), "model is flat -- the convolution did not run"
    assert int(np.argmax(y)) > 10, "model peak at channel 0 -- the IRF was not applied"
    assert _chi2r(fit) < 5.0


def test_fit_recovers_known_lifetimes():
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    assert _chi2r(fit) > 100, "starting guess was not actually poor"
    fit.run()
    amplitudes = [p.value for p in m.parameters_all if p.canonical_id.startswith("lifetime.amplitude.")]
    assert np.all(np.isfinite(amplitudes)) and np.abs(amplitudes).sum() > 0
    np.testing.assert_allclose(_taus(m), sorted(TRUE_TAUS), rtol=0.05)
    assert _chi2r(fit) < 2.0


def test_fit_does_not_destroy_a_good_solution():
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    before = _chi2r(fit)
    fit.run()
    after = _chi2r(fit)
    assert np.isfinite(after) and after < before * 10
