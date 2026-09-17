"""Model-backed decay fitting: recovering the truth, with linkable parameters.

:mod:`chisurf.core.fluorescence.decay_fit_model` fits a bare decay array through
BFF's ``tcspc_lifetime`` model rather than a standalone scipy optimiser, so the
result is a live ``Fit`` whose parameters behave like any other fit's.
These tests pin both halves of that claim: the numbers must be right, *and* the
parameters must support the ordinary bounds/linking surface.

A mis-configured model can fail silently (a flat background instead of a decay),
so the first test asserts the model is not flat before trusting any recovered
parameter.
"""

import numpy as np
import pytest

from chisurf.core.fluorescence.decay_fit_model import (
    build_fret_fit,
    build_lifetime_fit,
    fit_fret_model,
    fit_lifetime_model,
)

TRUE_TAUS = (4.0, 1.2)
TRUE_AMPS = (0.7, 0.3)
N_BINS = 1024
DT = 0.032


def _simulate(
    taus=TRUE_TAUS, amps=TRUE_AMPS, n_photons=2e6, seed=0, n_bins=N_BINS, dt=DT, background=10.0
):
    """Build a Poisson-noised, IRF-convolved multi-exponential decay plus its IRF."""
    t = np.arange(n_bins, dtype=float) * dt
    irf = np.exp(-0.5 * ((t - 1.0) / 0.25) ** 2) * 1e4
    irf[irf < 1e-3] = 0.0

    pure = np.zeros_like(t)
    for a, tau in zip(amps, taus):
        pure += a * np.exp(-t / tau)
    conv = np.convolve(pure, irf / irf.sum())[:n_bins]
    conv = conv / conv.sum() * n_photons + background
    y = np.random.default_rng(seed).poisson(conv).astype(float)
    return y, irf


def test_model_actually_computes_a_decay():
    """Guard the silent failure mode: a mis-wired model returns flat background."""
    y, irf = _simulate()
    fit = build_lifetime_fit(
        y,
        bin_width=DT,
        irf=irf,
        n_components=2,
        initial_lifetimes=TRUE_TAUS,
        tau_bounds=(0.05, 20.0),
    )
    fit.model.update()
    model_y = np.asarray(fit.model.y, dtype=float)

    assert model_y.max() > 10 * max(model_y.min(), 1e-12), "model is flat"
    assert int(np.argmax(model_y)) > 10, "peak at channel 0 — the IRF was not applied"


def test_recovers_known_lifetimes_from_a_poor_start():
    y, irf = _simulate()
    result = fit_lifetime_model(
        y,
        bin_width=DT,
        irf=irf,
        n_components=2,
        initial_lifetimes=(8.0, 0.4),
        tau_bounds=(0.05, 20.0),
        fit_background=True,
    )

    np.testing.assert_allclose(result["lifetimes"], sorted(TRUE_TAUS), rtol=0.05)
    assert result["chi2_reduced"] < 2.0, result["chi2_reduced"]


def test_an_unmodelled_background_biases_the_lifetimes_upward():
    """Why `fit_background` matters: the decay must not absorb the baseline.

    The simulated data carry a background of 10 counts/bin. Denied a term for it,
    the fit stretches both lifetimes to cover the raised tail.
    """
    y, irf = _simulate()
    kw = dict(
        bin_width=DT, irf=irf, n_components=2, initial_lifetimes=(8.0, 0.4), tau_bounds=(0.05, 20.0)
    )
    denied = fit_lifetime_model(y, **kw)
    fitted = fit_lifetime_model(y, fit_background=True, **kw)

    assert np.all(denied["lifetimes"] > fitted["lifetimes"])
    assert denied["chi2_reduced"] > fitted["chi2_reduced"]
    assert fitted["background"] > 0.0


def test_amplitudes_are_recovered_and_normalized():
    y, irf = _simulate()
    result = fit_lifetime_model(
        y,
        bin_width=DT,
        irf=irf,
        n_components=2,
        initial_lifetimes=(8.0, 0.4),
        tau_bounds=(0.05, 20.0),
        fit_background=True,
    )

    amps = result["amplitudes"]
    assert np.all(np.isfinite(amps))
    assert amps.sum() == pytest.approx(1.0, abs=1e-6)
    # sorted by lifetime, so the 1.2 ns (0.3) component comes first.
    np.testing.assert_allclose(amps, [0.3, 0.7], atol=0.05)


def test_result_shape_matches_the_scipy_fitter():
    """It must be able to stand in for `fit_lifetime_components`."""
    from chisurf.core.fluorescence import decay_fit

    y, irf = _simulate(n_photons=2e5)
    scipy_result = decay_fit.fit_lifetime_components(
        y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0)
    )
    model_result = fit_lifetime_model(
        y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0)
    )

    shared = {
        "lifetimes",
        "amplitudes",
        "lifetime_spectrum",
        "reconstruction",
        "weighted_residuals",
        "chi2_reduced",
    }
    assert shared <= set(scipy_result), "the scipy fitter's contract changed"
    assert shared <= set(model_result)
    for key in ("lifetimes", "amplitudes"):
        assert model_result[key].shape == scipy_result[key].shape
    assert model_result["lifetime_spectrum"].size == 2 * 2
    # Interleaved [a0, tau0, a1, tau1], amplitude first.
    np.testing.assert_allclose(model_result["lifetime_spectrum"][1::2], model_result["lifetimes"])


def test_the_two_fitters_agree_on_the_lifetimes():
    """The point of the migration is a different parameterisation, not a different answer."""
    from chisurf.core.fluorescence import decay_fit

    y, irf = _simulate()
    scipy_result = decay_fit.fit_lifetime_components(
        y,
        bin_width=DT,
        irf=irf,
        n_components=2,
        tau_bounds=(0.05, 20.0),
        include_background=True,
        include_scatter=True,
    )
    model_result = fit_lifetime_model(
        y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0), fit_background=True
    )

    np.testing.assert_allclose(model_result["lifetimes"], scipy_result["lifetimes"], rtol=0.05)
    np.testing.assert_allclose(model_result["lifetimes"], sorted(TRUE_TAUS), rtol=0.05)


def test_the_two_fitters_report_amplitudes_in_different_conventions():
    """A migration trap: the same fit reports 0.3 one way and 0.11 the other.

    ``fit_lifetime_components`` builds its design matrix from **unit-sum** decay
    columns, so its amplitudes are *photon fractions* — the share of detected
    photons a component contributes. ``Lifetime.amplitudes`` are the
    *pre-exponential* amplitudes of ``exp(-t/tau)``, ChiSurf's ``lifetime_spectrum``
    convention. They are related by ``f_i = a_i*tau_i / sum(a_j*tau_j)``, and for
    the simulated truth (0.3 at 1.2 ns, 0.7 at 4.0 ns) that is 0.11 / 0.89 — so
    reading one as the other silently mislabels a minor component as negligible.
    """
    from chisurf.core.fluorescence import decay_fit

    y, irf = _simulate()
    scipy_result = decay_fit.fit_lifetime_components(
        y,
        bin_width=DT,
        irf=irf,
        n_components=2,
        tau_bounds=(0.05, 20.0),
        include_background=True,
        include_scatter=True,
    )
    model_result = fit_lifetime_model(
        y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0), fit_background=True
    )

    pre_exp = model_result["amplitudes"]
    taus = model_result["lifetimes"]
    np.testing.assert_allclose(pre_exp, [0.3, 0.7], atol=0.05)

    photon_fractions = scipy_result["amplitudes"] / scipy_result["amplitudes"].sum()
    np.testing.assert_allclose(photon_fractions, [0.114, 0.886], atol=0.05)

    # The two are the same answer under the documented conversion.
    converted = pre_exp * taus / np.sum(pre_exp * taus)
    np.testing.assert_allclose(converted, photon_fractions, atol=0.05)


def test_fits_the_generated_irf_when_none_is_measured():
    """Without a measured IRF the prompt's own shape becomes fitted parameters.

    ``Convolve`` generates a generalized-normal prompt from ``iw``/``ik`` when no
    IRF curve is stored, so the model reaches the same joint width/skew/shift fit
    the standalone fitter does — but as ``FittingParameter``s.
    """
    y, _ = _simulate()  # true prompt: Gaussian, sigma = 0.25 ns, centred at 1 ns
    result = fit_lifetime_model(
        y,
        bin_width=DT,
        irf=None,
        n_components=2,
        initial_lifetimes=(8.0, 0.4),
        tau_bounds=(0.05, 20.0),
        fit_background=True,
        fit_irf=True,
        irf_width=0.2,
        irf_skew=0.0,
    )

    np.testing.assert_allclose(result["lifetimes"], sorted(TRUE_TAUS), rtol=0.05)
    assert result["irf_width"] == pytest.approx(0.25, rel=0.15)
    assert abs(result["irf_skew"]) < 0.2, "a symmetric prompt must not fit as skewed"


def _parameters(fit):
    return {
        p.canonical_id: p for p in fit.model.parameters_all if not getattr(p, "is_output", False)
    }


def test_irf_shape_is_free_only_when_requested():
    y, irf = _simulate()
    shape = ("instrument.irf_width", "instrument.irf_shape")

    fixed = _parameters(build_lifetime_fit(y, bin_width=DT, irf=None))
    assert all(fixed[k].fixed for k in shape)

    generated = _parameters(build_lifetime_fit(y, bin_width=DT, irf=None, fit_irf=True))
    assert not any(generated[k].fixed for k in shape)

    # A measured IRF is data, not a model: its shape stays fixed.
    measured = _parameters(build_lifetime_fit(y, bin_width=DT, irf=irf, fit_irf=True))
    assert all(measured[k].fixed for k in shape)


def test_the_irf_timeshift_stays_free():
    """Pinning it biased the lifetimes: a measured IRF's timing genuinely drifts."""
    y, irf = _simulate()
    for kw in ({}, dict(irf=irf), dict(irf=irf, fit_irf=True)):
        shift = _parameters(build_lifetime_fit(y, bin_width=DT, **kw))["instrument.timeshift"]
        assert not shift.fixed, f"timeshift was pinned for {kw}"


def test_parameters_are_fitting_parameters_with_bounds():
    y, irf = _simulate()
    result = fit_lifetime_model(y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0))
    from chisurf.core.fitting.parameter import FittingParameter

    problem = result["model"].problem
    parameters = _parameters(result["fit"])
    for k in range(2):
        p = parameters[f"lifetime.tau.{k}"]
        assert isinstance(p, FittingParameter)
        port = problem.get_parameter(f"lifetime.tau.{k}")
        assert (port.get_lower_bound(), port.get_upper_bound()) == (0.05, 20.0)


def test_more_components_than_a_search_offers_by_default():
    y, irf = _simulate()
    fit = build_lifetime_fit(y, bin_width=DT, irf=irf, n_components=5)
    assert fit.model.structure == "lifetime.components.5"
    assert np.asarray(fit.model.y).max() > 0


def test_a_fitted_lifetime_can_be_linked_to_another_fit():
    """The whole reason for the migration: live cross-fit parameter linking."""
    y, irf = _simulate()
    a = fit_lifetime_model(y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0))
    b = fit_lifetime_model(y, bin_width=DT, irf=irf, n_components=2, tau_bounds=(0.05, 20.0))

    target = _parameters(a["fit"])["lifetime.tau.0"]
    follower = _parameters(b["fit"])["lifetime.tau.0"]
    follower.link = target

    assert follower.is_linked
    target.value = 2.345
    assert follower.value == pytest.approx(2.345), "the link did not propagate"

    follower.link = None
    assert not follower.is_linked


def test_periodic_convolution_is_requested_when_a_period_is_given():
    y, irf = _simulate()
    aperiodic = build_lifetime_fit(y, bin_width=DT, irf=irf).model
    periodic = build_lifetime_fit(y, bin_width=DT, irf=irf, period=25.0).model

    assert aperiodic.get_scalar("periodic_excitation") == 0.0
    assert periodic.get_scalar("periodic_excitation") == 1.0
    assert periodic.get_scalar("period") == pytest.approx(25.0)
    assert not np.allclose(np.asarray(aperiodic.y), np.asarray(periodic.y))


def test_fit_range_masks_the_optimised_window():
    y, irf = _simulate()
    fit = build_lifetime_fit(y, bin_width=DT, irf=irf, start_bin=40, stop_bin=900)

    assert fit.xmin == 40
    assert fit.xmax == 900
    # The model is still evaluated over the whole axis; only residuals are masked.
    assert np.asarray(fit.model.y, dtype=float).size == N_BINS


def test_rejects_an_unusable_decay():
    with pytest.raises(ValueError):
        build_lifetime_fit(np.ones(3), bin_width=DT)
    with pytest.raises(ValueError):
        build_lifetime_fit(np.ones(64), bin_width=0.0)
    with pytest.raises(ValueError):
        build_lifetime_fit(np.ones(64), bin_width=DT, tau_bounds=(5.0, 1.0))


# --------------------------------------------------------------------------
# FRET: fitted distances rather than lifetimes converted to efficiencies
# --------------------------------------------------------------------------

R0 = 52.0
TAU_D0 = 4.0


def _simulate_fret(
    distances=(40.0, 65.0),
    fractions=(0.6, 0.4),
    x_donor_only=0.0,
    n_photons=2e6,
    seed=1,
    n_bins=N_BINS,
    dt=DT,
    background=5.0,
):
    """Build a donor decay quenched by FRET at known distances, plus its IRF.

    Each state decays with tau_i = tau_D0 * (1 - E_i), the single-distance
    relation the model must invert.
    """
    t = np.arange(n_bins, dtype=float) * dt
    irf = np.exp(-0.5 * ((t - 1.0) / 0.25) ** 2) * 1e4
    irf[irf < 1e-3] = 0.0

    pure = np.zeros_like(t)
    for r, x in zip(distances, fractions):
        e = 1.0 / (1.0 + (r / R0) ** 6)
        pure += (1.0 - x_donor_only) * x * np.exp(-t / (TAU_D0 * (1.0 - e)))
    if x_donor_only > 0:
        pure += x_donor_only * np.exp(-t / TAU_D0)

    conv = np.convolve(pure, irf / irf.sum())[:n_bins]
    conv = conv / conv.sum() * n_photons + background
    y = np.random.default_rng(seed).poisson(conv).astype(float)
    return y, irf


def test_fret_fit_recovers_known_distances():
    y, irf = _simulate_fret()
    result = fit_fret_model(
        y,
        bin_width=DT,
        irf=irf,
        n_states=2,
        donor_lifetime=TAU_D0,
        forster_radius=R0,
        sigma=2.0,
        fit_donor_only=False,
        fit_background=True,
    )

    np.testing.assert_allclose(result["distances"], [40.0, 65.0], rtol=0.15)
    assert result["chi2_reduced"] < 3.0, result["chi2_reduced"]


def test_fret_efficiencies_follow_the_fitted_distances():
    y, irf = _simulate_fret()
    result = fit_fret_model(
        y,
        bin_width=DT,
        irf=irf,
        n_states=2,
        donor_lifetime=TAU_D0,
        forster_radius=R0,
        sigma=2.0,
        fit_donor_only=False,
        fit_background=True,
    )

    expected = 1.0 / (1.0 + (result["distances"] / R0) ** 6)
    np.testing.assert_allclose(result["efficiencies"], expected)
    # The 40 A state is high-FRET, the 65 A state low-FRET.
    assert result["efficiencies"][0] > 0.75 > result["efficiencies"][1]


def test_fret_distances_are_fitting_parameters():
    """The point of the FRET migration: distances/fractions are linkable."""
    from chisurf.core.fitting.parameter import FittingParameter

    y, irf = _simulate_fret()
    fit = build_fret_fit(
        y, bin_width=DT, irf=irf, n_states=2, donor_lifetime=TAU_D0, forster_radius=R0
    )
    assert fit.model.structure == "tcspc_fret_gaussian.components.2"
    parameters = _parameters(fit)
    problem = fit.model.problem
    means = [parameters[f"distance.mean.{k}"] for k in range(2)]
    assert all(isinstance(p, FittingParameter) for p in means)
    for k in range(2):
        port = problem.get_parameter(f"distance.mean.{k}")
        assert (port.get_lower_bound(), port.get_upper_bound()) == (10.0, 120.0)

    follower, target = means[1], means[0]
    follower.link = target
    target.value = 47.5
    assert follower.value == pytest.approx(47.5)


def test_fret_calibration_is_held_fixed():
    """R0 and tau_D0 are calibration, not data: fitting them is ill-conditioned."""
    y, irf = _simulate_fret()
    parameters = _parameters(
        build_fret_fit(
            y, bin_width=DT, irf=irf, n_states=2, donor_lifetime=TAU_D0, forster_radius=R0
        )
    )
    assert parameters["fret.forster_radius"].fixed
    assert parameters["donor.tau.0"].fixed
    assert parameters["fret.forster_radius"].value == pytest.approx(R0)
    assert parameters["fret.tau0"].value == pytest.approx(TAU_D0)

    freed = _parameters(
        build_fret_fit(
            y,
            bin_width=DT,
            irf=irf,
            n_states=2,
            donor_lifetime=TAU_D0,
            forster_radius=R0,
            fit_donor_lifetime=True,
        )
    )
    assert not freed["donor.tau.0"].fixed


def test_fret_donor_only_fraction_is_recovered():
    y, irf = _simulate_fret(x_donor_only=0.25)
    result = fit_fret_model(
        y,
        bin_width=DT,
        irf=irf,
        n_states=2,
        donor_lifetime=TAU_D0,
        forster_radius=R0,
        sigma=2.0,
        fit_donor_only=True,
        x_donor_only=0.1,
        fit_background=True,
    )

    assert result["donor_only_fraction"] == pytest.approx(0.25, abs=0.15)


def test_fret_rejects_bad_calibration():
    y, _ = _simulate_fret()
    with pytest.raises(ValueError):
        build_fret_fit(y, bin_width=DT, forster_radius=0.0)
    with pytest.raises(ValueError):
        build_fret_fit(y, bin_width=DT, distance_bounds=(100.0, 10.0))
