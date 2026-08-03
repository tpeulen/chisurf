"""The per-state physics: p(R), efficiencies, channel branching and micro-time patterns.

The distance distribution is checked against a Monte-Carlo of the situation it
claims to describe — two dyes in three-dimensional Gaussian clouds — rather than
against its own formula, because a transcription slip in the formula would
otherwise be tested against itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.lines import gaussian_distance_distribution
from chisurf.core.fluorescence.mfd.moments import pattern_moments
from chisurf.core.fluorescence.mfd.patterns import (
    ChannelResponse,
    FretState,
    Optics,
    acceptor_lifetime_spectrum,
    donor_lifetime_spectrum_of_state,
    noncentral_chi_distance_distribution,
    red_probability,
    state_efficiency,
)

N_CHANNELS = 4096
PERIOD = 13.6
DT = PERIOD / N_CHANNELS


def _response(centre: int = 300, width: float = 8.0, **kwargs) -> ChannelResponse:
    """Return a Gaussian instrument response for the tests."""
    channels = np.arange(N_CHANNELS)
    return ChannelResponse(
        irf=np.exp(-0.5 * ((channels - centre) / width) ** 2), dt=DT, **kwargs
    )


# ──────────────────────────────────────────────────────────────────────────────
# The distance distribution
# ──────────────────────────────────────────────────────────────────────────────
def test_distance_distribution_matches_two_gaussian_clouds():
    """p(R) is the separation of two 3-D Gaussian clouds, not a Gaussian in R."""
    rng = np.random.default_rng(20260803)
    d, sigma_d, sigma_a = 50.0, 4.0, 5.0
    sigma = float(np.hypot(sigma_d, sigma_a))
    donor = rng.normal([0.0, 0.0, 0.0], sigma_d, size=(400_000, 3))
    acceptor = rng.normal([d, 0.0, 0.0], sigma_a, size=(400_000, 3))
    sampled = np.linalg.norm(acceptor - donor, axis=1)

    weights, r = noncentral_chi_distance_distribution(d, sigma, n_points=401, n_sigma=5)
    weights, r = weights[0], r[0]
    mean = float(weights @ r)
    std = float(np.sqrt(weights @ (r * r) - mean * mean))
    assert mean == pytest.approx(sampled.mean(), rel=2e-3)
    assert std == pytest.approx(sampled.std(), rel=5e-3)


def test_distance_distribution_is_skewed_above_its_nominal_mean():
    """The separation of two clouds sits *above* the separation of their centres.

    A Gaussian in R would put it exactly at the centre separation. The offset is
    small at long distances and large at short ones, which is precisely where a
    Gaussian would also start leaking weight to unphysically small R.
    """
    sigma = 6.0
    for d in (20.0, 50.0, 100.0):
        weights, r = noncentral_chi_distance_distribution(d, sigma, n_points=401)
        assert float(weights[0] @ r[0]) > d
    weights, r = noncentral_chi_distance_distribution(20.0, sigma, n_points=401)
    assert r[0].min() > 0.0
    assert float(weights[0] @ r[0]) - 20.0 > 1.0


def test_distance_distribution_is_normalised_and_collapses():
    """Truncating the sampled range must not leak probability; sigma=0 is a delta."""
    weights, r = noncentral_chi_distance_distribution(50.0, 6.0, n_points=41, n_sigma=2)
    assert float(weights.sum()) == pytest.approx(1.0)
    weights, r = noncentral_chi_distance_distribution(50.0, 0.0)
    assert weights.shape == r.shape == (1, 1)
    assert float(r[0, 0]) == 50.0


def test_it_differs_from_the_gaussian_it_is_often_mistaken_for():
    """If the two agreed there would be no reason for this function to exist."""
    gauss_w, gauss_r = gaussian_distance_distribution(30.0, 6.0, n_points=401)
    chi_w, chi_r = noncentral_chi_distance_distribution(30.0, 6.0, n_points=401)
    gauss_mean = float(gauss_w[0] @ gauss_r[0])
    chi_mean = float(chi_w[0] @ chi_r[0])
    assert chi_mean - gauss_mean > 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Efficiency
# ──────────────────────────────────────────────────────────────────────────────
def test_burst_efficiency_is_the_average_of_E_not_E_of_the_average():
    """``∫p(R)E(R)`` and ``E(∫p(R)R)`` differ, and the difference bends the line.

    Below R₀ the efficiency curve is concave, so averaging pulls the burst
    efficiency *down*; above R₀ it is convex and pulls it up. Collapsing the two is
    how a linker width comes to be mistaken for a distance error.
    """
    optics = Optics(r0=52.0, sigma=6.4)
    below = state_efficiency(FretState(distance=35.0), optics)
    assert below < 1.0 / (1.0 + (35.0 / 52.0) ** 6)
    above = state_efficiency(FretState(distance=80.0), optics)
    assert above > 1.0 / (1.0 + (80.0 / 52.0) ** 6)


def test_efficiency_is_monotonic_in_distance():
    """A basic property the whole FRET axis rests on."""
    optics = Optics(r0=52.0, sigma=6.0)
    distances = np.linspace(20.0, 110.0, 25)
    e = [state_efficiency(FretState(distance=d), optics) for d in distances]
    assert np.all(np.diff(e) < 0)
    assert e[0] > 0.95 and e[-1] < 0.05


# ──────────────────────────────────────────────────────────────────────────────
# Channel branching
# ──────────────────────────────────────────────────────────────────────────────
def test_red_probability_is_the_efficiency_for_an_ideal_instrument():
    """With γ=1 and no leakage or direct excitation, PR *is* E."""
    optics = Optics(gamma=1.0, alpha=0.0, delta=0.0)
    for e in (0.0, 0.25, 0.5, 0.9, 1.0):
        assert float(red_probability(e, optics)) == pytest.approx(e)


def test_each_correction_moves_the_axis_the_way_it_should():
    """Leakage and direct excitation raise a low-FRET burst; γ scales the ratio."""
    base = Optics(gamma=1.0)
    e = 0.2
    plain = float(red_probability(e, base))
    assert float(red_probability(e, Optics(gamma=1.0, alpha=0.05))) > plain
    assert float(red_probability(e, Optics(gamma=1.0, delta=0.05))) > plain
    assert float(red_probability(e, Optics(gamma=2.0))) > plain
    assert float(red_probability(e, Optics(gamma=0.5))) < plain
    # A donor-only molecule is pushed off zero by leakage and direct excitation
    # alone — which is what makes them identifiable from that population.
    assert float(red_probability(0.0, Optics(alpha=0.05))) == pytest.approx(0.05 / 1.05)
    assert float(red_probability(0.0, Optics(delta=0.05))) == pytest.approx(0.05 / 1.05)


def test_red_probability_stays_a_probability():
    """Extreme corrections may not produce a value outside [0, 1]."""
    p = red_probability([0.0, 0.5, 1.0], Optics(gamma=50.0, alpha=0.9, delta=0.9))
    assert np.all((p >= 0.0) & (p <= 1.0))


# ──────────────────────────────────────────────────────────────────────────────
# Lifetime spectra and patterns
# ──────────────────────────────────────────────────────────────────────────────
def test_donor_spectrum_spans_the_distance_distribution():
    """A distributed distance gives distributed lifetimes, not one average."""
    optics = Optics(r0=52.0, tau_d0=4.0, sigma=6.0)
    amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
        FretState(distance=52.0), optics
    )
    assert amplitudes.size == lifetimes.size == 81
    assert float(amplitudes.sum()) == pytest.approx(1.0)
    assert lifetimes.min() < 1.0 < lifetimes.max() < optics.tau_d0
    # Unquenched donor: every component is the donor-only lifetime.
    far, far_tau = donor_lifetime_spectrum_of_state(FretState(distance=400.0), optics)
    assert far_tau.min() == pytest.approx(optics.tau_d0, rel=1e-3)


def test_acceptor_emission_arrives_after_the_donor():
    """The sensitized acceptor rises with the donor and falls with its own lifetime."""
    optics = Optics(r0=52.0, tau_d0=4.0, tau_a=3.0, sigma=6.0)
    response = _response()
    donor_a, donor_t = donor_lifetime_spectrum_of_state(
        FretState(distance=52.0), optics
    )
    donor_mean, _ = response.signal_moments(donor_a, donor_t)
    acceptor_a, acceptor_t = acceptor_lifetime_spectrum(donor_a, donor_t, optics)
    acceptor_mean, _ = response.signal_moments(acceptor_a, acceptor_t)
    assert acceptor_mean > donor_mean + 1.0


def test_acceptor_spectrum_survives_a_degenerate_lifetime():
    """A donor component equal to the acceptor lifetime must not divide by zero."""
    optics = Optics(tau_d0=4.0, tau_a=2.0)
    amplitudes, lifetimes = acceptor_lifetime_spectrum(
        np.array([1.0]), np.array([2.0]), optics
    )
    assert np.all(np.isfinite(amplitudes))
    pattern = _response().pattern(amplitudes, lifetimes)
    assert np.all(np.isfinite(pattern)) and pattern.sum() == pytest.approx(1.0)


def test_components_are_photon_weighted_not_amplitude_weighted():
    """A component's share of the photons is ``a·τ``, not ``a``.

    Equal amplitudes of a 0.5 ns and a 4 ns lifetime do *not* contribute equally:
    the long one emits eight times as many photons. Weighting by amplitude instead
    would drag every distance distribution towards its high-FRET tail.
    """
    response = _response(centre=0, width=0.5)
    mean, _ = pattern_moments(
        response.decay(np.array([1.0, 1.0]), np.array([0.5, 4.0])), DT
    )
    # Amplitude-weighted would sit near (0.5 + 4)/2; photon-weighted is far later.
    assert mean > 3.0


def test_a_later_response_shifts_the_mean_sub_linearly():
    """Delaying the response by k channels moves ``⟨t⟩`` by *less* than k·dt.

    The window is periodic, so shifting a pattern later pushes some of its tail past
    the end, where it reappears at the start. The recorded mean therefore moves by
    the shift **minus** one whole period for every unit of mass that wrapped::

        ⟨t⟩(shifted) = ⟨t⟩ + k·dt − T · (mass in the last k channels)

    This is the identity that makes a naive "shift the IRF, shift the lifetime"
    calibration wrong near the end of the window, and it is exact.
    """
    optics = Optics()
    amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
        FretState(distance=52.0), optics
    )
    shift = 700
    early = _response(centre=200)
    late = _response(centre=200 + shift)

    early_pattern = early.pattern(amplitudes, lifetimes)
    assert early_pattern.sum() == pytest.approx(1.0)
    assert late.pattern(amplitudes, lifetimes).sum() == pytest.approx(1.0)

    early_mean, _ = early.signal_moments(amplitudes, lifetimes)
    late_mean, _ = late.signal_moments(amplitudes, lifetimes)
    wrapped_mass = float(early_pattern[-shift:].sum())

    assert late_mean - early_mean == pytest.approx(
        shift * DT - PERIOD * wrapped_mass, rel=1e-6
    )
    # And the effect is real rather than rounding: a measurable fraction wrapped.
    assert 0.0 < wrapped_mass < 0.05
    assert late_mean - early_mean < shift * DT


def test_scatter_pulls_the_mean_towards_the_response():
    """Scattered excitation light has the response's own timing, i.e. the earliest."""
    optics = Optics()
    amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
        FretState(distance=90.0), optics
    )
    clean = _response()
    scattered = _response(scatter_fraction=0.3)
    clean_mean, _ = clean.signal_moments(amplitudes, lifetimes)
    scattered_mean, _ = scattered.signal_moments(amplitudes, lifetimes)
    irf_mean, _ = pattern_moments(clean.irf, DT)
    assert irf_mean < scattered_mean < clean_mean


def test_background_is_flat_and_late():
    """Uncorrelated background sits at the middle of the window, by construction."""
    response = _response()
    mean, variance = response.background_moments()
    assert mean == pytest.approx((PERIOD - DT) / 2.0, rel=1e-6)
    assert variance == pytest.approx(PERIOD**2 / 12.0, rel=1e-3)


def test_empty_or_impossible_inputs_are_refused():
    """Refusals, not NaNs propagating into a fitted distance."""
    with pytest.raises(ValueError):
        ChannelResponse(irf=np.zeros(8), dt=DT)
    with pytest.raises(ValueError):
        ChannelResponse(irf=np.array([]), dt=DT)
    response = _response()
    with pytest.raises(ValueError):
        response.decay([1.0, 2.0], [1.0])
