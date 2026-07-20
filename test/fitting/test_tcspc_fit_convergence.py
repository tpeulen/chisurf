"""End-to-end headless TCSPC fit: does a lifetime fit recover known parameters?

The repository had no working headless fit fixture — ``test_reference_models.py``
uses ``model.data`` and a writable ``lifetime_spectrum``, neither of which exists
any more — so nothing exercised the optimiser against a known answer. This does.

Getting a ``LifetimeModel`` to compute at all needs four non-obvious settings,
and **every one of them fails silently**, leaving a flat background instead of a
decay:

1. ``convolve.stop`` is in TIME units (``value // dt``) and defaults to 0, which
   disables the convolution entirely.
2. ``convolve.dt`` is its own parameter defaulting to 1.0, so every other
   "time" is divided by the wrong step.
3. ``_process_irf`` subtracts ``lamp_background`` and clips at zero, so a
   sum-normalised IRF (peak ~0.04) is annihilated — supply the IRF in counts.
4. ``irf_stop`` defaults to 1, leaving a one-channel IRF. Its *setter* is broken
   (it wraps the value in ``np.array([v])``, which the parameter rejects), so
   the backing ``_irf_stop`` parameter has to be written directly.

Autoscaling is enabled by *fixing* ``n0`` (``autoscale = self._n0.fixed``).
"""
import numpy as np
import pytest

import chisurf.core.data
from chisurf.core.fitting.fit import Fit
import chisurf.core.models.tcspc.lifetime as lifetime_model

TRUE_TAUS = (4.0, 1.2)
TRUE_AMPS = (0.7, 0.3)
N_CHANNELS = 1024
DT = 0.032
BACKGROUND = 10.0


def _build(start, n_channels=N_CHANNELS, dt=DT, n_photons=2e6, seed=0):
    """Simulate a two-exponential decay and wire up a fittable model."""
    t = np.arange(n_channels) * dt

    # IRF in COUNTS: lamp_background is subtracted and clipped, so a
    # sum-normalised IRF would be wiped out.
    irf_y = np.exp(-0.5 * ((t - 1.0) / 0.25) ** 2) * 1e4
    irf_y[irf_y < 1e-3] = 0.0

    pure = np.zeros_like(t)
    for a, tau in zip(TRUE_AMPS, TRUE_TAUS):
        pure += a * np.exp(-t / tau)
    conv = np.convolve(pure, irf_y / irf_y.sum())[:n_channels]
    conv = conv / conv.sum() * n_photons + BACKGROUND
    y = np.random.default_rng(seed).poisson(conv).astype(float)

    data = chisurf.core.data.DataCurve(x=t, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    fit = Fit(model_class=lifetime_model.LifetimeModel, data=data,
              xmin=0, xmax=n_channels - 1)
    m = fit.model

    c = m.convolve
    c._irf = chisurf.core.data.DataCurve(x=t, y=irf_y, ey=np.ones_like(irf_y))
    c.lamp_background = 0.0
    c.dt = dt                       # defaults to 1.0
    c.start, c.stop = 0.0, n_channels * dt   # TIME units; default stop=0 disables
    c._irf_start.value = 0.0        # setters are broken (wrap in np.array)
    c._irf_stop.value = n_channels * dt
    c.rep_rate = 40.0
    c.mode = 'per'
    c.do_convolution = True
    c._n0.fixed = True              # autoscale = self._n0.fixed

    # The model ships with one default component; configure in place rather than
    # appending, or a duplicate lifetime adds a spurious degeneracy.
    while len(m.lifetimes) < len(start):
        m.lifetimes.append()
    for k, (a, tau) in enumerate(start):
        m.lifetimes._amplitudes[k].value = a
        pt = m.lifetimes._lifetimes[k]
        pt.value = tau
        pt.lb, pt.ub, pt.bounds_on = 0.01, 50.0, True

    m.generic.background = BACKGROUND
    m.find_parameters()
    return fit, m


def _chi2r(m):
    w = np.asarray(m.weighted_residuals, dtype=float)
    return float(np.sum(w ** 2) / len(w))


def test_fixture_is_self_consistent():
    """At the true parameters the model must actually match the data."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.update_model()
    y = np.asarray(m.y, dtype=float)

    assert y.max() > 10 * y.min(), "model is flat — the convolution did not run"
    assert int(np.argmax(y)) > 10, "model peak at channel 0 — IRF was not applied"
    assert _chi2r(m) < 5.0, f"fixture not self-consistent, chi2r={_chi2r(m):.1f}"


def test_fit_recovers_known_lifetimes():
    """The whole point: a fit from a poor start must find the truth."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])   # far from (4.0, 1.2)
    assert _chi2r(m) > 100, "starting guess was not actually poor"

    fit.run()

    taus = sorted(p.value for p in m.lifetimes._lifetimes)
    amps = np.asarray(m.lifetimes.amplitudes, dtype=float)
    assert np.all(np.isfinite(amps)), f"amplitudes became non-finite: {amps}"

    np.testing.assert_allclose(taus, sorted(TRUE_TAUS), rtol=0.05)
    assert _chi2r(m) < 2.0, f"fit did not converge, chi2r={_chi2r(m):.3f}"


@pytest.mark.xfail(
    reason=(
        "Known, separate defect: a parameter sitting exactly ON a bound has zero "
        "derivative under the sin/arcsin transform, so the optimiser jumps. "
        "`scatter` defaults to 0.0 with bounds (0.0, 100.0) -- i.e. exactly at its "
        "lower bound -- and starting a fit at the optimum drives it 0 -> 7.8, "
        "taking chi2r 1.55 -> 1765 while every other parameter stays put. "
        "d/dx[lower + (delta/2)(sin x + 1)] = (delta/2) cos x, which is 0 at "
        "x = -pi/2, the internal coordinate of the lower bound. The usual remedy "
        "is to inset starting values slightly inside their bounds. Fixing it is a "
        "behaviour change to every bounded fit and needs its own validation."
    ),
    strict=True,
)
def test_fit_does_not_destroy_a_good_solution():
    """Starting at the optimum must not make things worse.

    This is the regression that caught the infinite-bounds bug: unbounded
    parameters were NaN in the optimiser's internal coordinates, so a fit
    started at the truth walked away from it. It still fails for the unrelated
    at-the-bound reason documented above.
    """
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.update_model()
    before = _chi2r(m)

    fit.run()
    after = _chi2r(m)

    assert np.isfinite(after), "fit produced a non-finite chi2r from a good start"
    assert after < before * 10, (
        f"fit destroyed a good solution: chi2r {before:.3f} -> {after:.3f}")


def test_amplitudes_stay_finite():
    """Amplitudes must not collapse to zero (0/0 in the |a|/sum|a| normalisation)."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()
    raw = np.asarray([p.value for p in m.lifetimes._amplitudes], dtype=float)
    assert np.abs(raw).sum() > 0, f"all amplitudes collapsed to zero: {raw}"
    assert np.all(np.isfinite(m.lifetimes.amplitudes))
