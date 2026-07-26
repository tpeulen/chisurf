"""Kinetic consistency check for fitted PDA models (PRD-50, scope item 5).

Two things need to hold for the check to mean anything:

* the resampler's *generative* forward model must agree with the convolution
  the ``tttrlib.Pda`` engine evaluates -- otherwise the bootstrap reference
  distribution is drawn from a different process than the one being tested;
* the check must pass a correctly specified scheme and reject a wrong one.

Both are asserted here. The first is the sharper test: it converges as
``1/sqrt(n)`` and so catches convention errors (notably that ``pF`` is the
*signal* photon distribution, with background added on top rather than carved
out of it) that a pass/reject test would not.
"""
from __future__ import annotations

import numpy as np
import pytest

# Absolute package import: ``test`` and ``test.gui`` are real packages, so this
# works from the repo root without needing ``test/gui`` on PYTHONPATH (a bare
# sibling import would only collect when that directory happens to be on it).
from test.gui.test_pda2c_model_editor import _make_pda_fit, _resolve

TRUE_KEX = 2.0


def _total_variation(a, b):
    """Total-variation distance between two count matrices."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return 0.5 * float(np.abs(a / a.sum() - b / b.sum()).sum())


def _gaussian_model_fit(background=(0.0, 0.0)):
    """Build a Gaussian PDA model at a fixed distance, with its engine primed."""
    model_class = _resolve("chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel")
    fit = _make_pda_fit(model_class)
    m = fit.model
    m.distances._means[0].value = 52.0
    m.distances._sigmas[0].value = 6.0
    m.nuisance.BG, m.nuisance.BR = background
    m.update()
    m.get_wres(fit)
    return fit, m


@pytest.mark.parametrize("background", [(0.0, 0.0), (2.0, 1.5)])
def test_resampler_converges_to_the_engine_histogram(qapp, background):
    """Sampling the forward model must reproduce what the engine convolves.

    Checked as a Monte-Carlo convergence: the total-variation distance has to
    *fall* roughly as ``1/sqrt(n)``. A mismatched convention plateaus instead --
    carving the background out of ``pF`` sticks at ~0.29 forever.
    """
    from chisurf.core.models.pda2c.consistency import resample_s1s2

    fit, m = _gaussian_model_fit(background)
    ny, nx = fit.data.pda["shape"]
    engine = np.asarray(m.pda.get_S1S2_matrix(), dtype=float)[:ny, :nx]

    def sampled(n):
        return resample_s1s2(
            pF=m.pda.getPF(),
            amplitudes=m.pda.get_amplitudes(),
            probabilities=m.pda.get_probabilities_ch1(),
            n_bursts=n,
            background_ch1=m.pda.background_ch1,
            background_ch2=m.pda.background_ch2,
            seed=3,
            n_max=ny - 1,
        )

    tv_small = _total_variation(sampled(20_000), engine)
    tv_large = _total_variation(sampled(500_000), engine)

    assert tv_large < 0.02, f"resampler does not match the engine (TV={tv_large:.4f})"
    # 25x the bursts is 5x the precision; allow generous slack for one seed.
    assert tv_large < 0.5 * tv_small, "distance is not shrinking; a convention differs"


def test_resampler_reproduces_the_engine_burst_size(qapp):
    """Mean burst size is the mean of pF *plus* both backgrounds.

    Pins the convention directly, independent of the histogram shape.
    """
    from chisurf.core.models.pda2c.consistency import resample_s1s2

    fit, m = _gaussian_model_fit(background=(2.0, 1.5))
    ny, nx = fit.data.pda["shape"]
    pF = np.asarray(m.pda.getPF(), dtype=float)
    expected = float(pF @ np.arange(pF.size) / pF.sum()) + 2.0 + 1.5

    s1s2 = resample_s1s2(
        pF=pF,
        amplitudes=m.pda.get_amplitudes(),
        probabilities=m.pda.get_probabilities_ch1(),
        n_bursts=200_000,
        background_ch1=2.0,
        background_ch2=1.5,
        seed=5,
        n_max=ny - 1,
    )
    green, red = np.indices(s1s2.shape)
    mean_n = float((s1s2 * (green + red)).sum() / s1s2.sum())
    assert mean_n == pytest.approx(expected, rel=0.02)


def _dynamic_fit(free_kex, total=2e5, seed=1):
    """Fit the dynamic model to data generated at ``TRUE_KEX``; see PRD-50."""
    import chisurf.core.fluorescence.tcspc as tcspc

    model_class = _resolve("chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel")
    fit = _make_pda_fit(model_class)
    m = fit.model
    st = m.states
    st._R1.value, st._s1.value = 40.0, 4.0
    st._R2.value, st._s2.value = 62.0, 4.0
    st._x1.value, st._kex.value = 0.5, TRUE_KEX
    m.update()
    m.get_wres(fit)

    s1s2 = np.asarray(m.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * total
    noisy = np.random.default_rng(seed).poisson(s1s2).astype(float)
    fit.data.pda["s1s2"] = noisy
    fit.data.y = noisy.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    for p in m.parameters_all:
        p.fixed = True
    for p in (st._x1, st._R1, st._R2):
        p.fixed = False
    st._x1.value, st._R1.value, st._R2.value = 0.42, 43.0, 58.0
    st._kex.fixed = not free_kex
    st._kex.value = TRUE_KEX * 4.0 if free_kex else 0.0
    m.find_parameters()
    fit.run()
    return fit, m


def test_consistency_check_accepts_the_correct_kinetic_scheme(qapp):
    """A correctly specified scheme must not be rejected.

    The measured score has to land inside the bootstrap distribution, not just
    below some threshold -- that is what shows the reference distribution is
    the right one.
    """
    from chisurf.core.models.pda2c.consistency import kinetic_consistency_check

    fit, m = _dynamic_fit(free_kex=True)
    result = kinetic_consistency_check(fit, n_resamples=100, seed=7)

    assert result["consistent"], f"correct scheme rejected (p={result['p_value']:.4f})"
    assert result["p_value"] > 0.05
    median = float(np.median(result["chi2_resampled"]))
    assert result["chi2_measured"] == pytest.approx(median, rel=0.5)


def test_consistency_check_rejects_the_wrong_kinetic_scheme(qapp):
    """The static (K_ex = 0) scheme fitted to dynamic data must be rejected."""
    from chisurf.core.models.pda2c.consistency import kinetic_consistency_check

    fit, m = _dynamic_fit(free_kex=False)
    result = kinetic_consistency_check(fit, n_resamples=100, seed=7)

    assert not result["consistent"], f"wrong scheme accepted (p={result['p_value']:.4f})"
    # The bootstrap floor with 100 resamples is 1/101.
    assert result["p_value"] == pytest.approx(1.0 / 101.0)
    assert result["chi2_measured"] > 10.0 * float(np.median(result["chi2_resampled"]))


def test_p_value_is_never_zero(qapp):
    """The (k+1)/(n+1) correction keeps the p-value inside what n resamples resolve."""
    from chisurf.core.models.pda2c.consistency import kinetic_consistency_check

    fit, m = _dynamic_fit(free_kex=False)
    result = kinetic_consistency_check(fit, n_resamples=20, seed=1)
    assert result["p_value"] >= 1.0 / 21.0


def test_rejects_a_non_pda_model(qapp):
    """A model with no engine is a programming error, not a silent pass."""
    import chisurf.core.data
    import chisurf.core.fitting.fit as fit_module
    import chisurf.core.models.parse
    from chisurf.core.models.pda2c.consistency import kinetic_consistency_check

    x = np.linspace(0.0, 5.0, 32)
    data = chisurf.core.data.DataCurve(x=x, y=np.ones_like(x), ey=np.ones_like(x))
    fit = fit_module.Fit(
        data=data, model_class=chisurf.core.models.parse.ParseModel
    )
    with pytest.raises(TypeError, match="not a PDA model"):
        kinetic_consistency_check(fit, n_resamples=2)
