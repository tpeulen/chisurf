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
    # One component per distance sample and nothing else: the producer node also
    # emits a donor-only block scaled by ``x_donly``, which this module drops
    # because incomplete labelling is its own MFD *species* rather than a term
    # inside one state — and because every invariant below ("every lifetime is
    # quenched") would otherwise be false of a zero-amplitude passenger.
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


# ──────────────────────────────────────────────────────────────────────────────
# The anisotropy axis
# ──────────────────────────────────────────────────────────────────────────────
def _sharp_response(**kwargs):
    """Return a near-delta response, so a steady-state anisotropy is not smeared."""
    channels = np.arange(N_CHANNELS)
    return ChannelResponse(
        irf=np.exp(-0.5 * ((channels - 20) / 1.0) ** 2), dt=DT, **kwargs
    )


def _anisotropy_from_split(p_parallel, g_factor=1.0, l1=0.0, l2=0.0):
    """Invert a parallel/perpendicular split back to the anisotropy that made it."""
    numerator = p_parallel - g_factor * (1.0 - p_parallel)
    denominator = p_parallel + 2.0 * g_factor * (1.0 - p_parallel)
    value = numerator / denominator
    return value / (1.0 - l1 - l2) if (l1 or l2) else value


@pytest.mark.parametrize("tau", [1.0, 2.0, 4.0])
@pytest.mark.parametrize("rho", [0.2, 1.0, 5.0])
def test_the_polarized_split_predicts_the_perrin_relation(tau, rho):
    """Perrin comes *out* of the model rather than being put into it.

    The forward model builds the parallel and perpendicular patterns from ``r(t)``
    and integrates them; that the result satisfies ``r_ss = r₀/(1 + τ/ρ)`` is then a
    check on the machinery. A model that took the steady-state anisotropy as a
    parameter would satisfy Perrin by construction and could never be wrong.
    """
    from chisurf.core.fluorescence.mfd.patterns import (
        perrin_anisotropy,
        polarized_patterns,
    )

    optics = Optics(r0_anisotropy=0.38)
    _, _, p_parallel = polarized_patterns(
        _sharp_response(), [1.0], [tau], rho, optics
    )
    recovered = _anisotropy_from_split(p_parallel)
    assert recovered == pytest.approx(
        float(perrin_anisotropy(tau, rho, 0.38)), abs=0.01
    )


def test_the_g_factor_divides_the_perpendicular_channel():
    """G is a detection sensitivity, and the round trip is what pins its placement.

    ``tttrlib``'s ``DecayFit23`` fits ``x_vh[0] = 1/g``, so the perpendicular
    channel records ``1/G`` of what an equally sensitive one would. Multiplying
    instead — which this module's own docstring described for a while — leaves the
    recovered anisotropy varying with an instrument constant it must not depend on.
    """
    from chisurf.core.fluorescence.mfd.patterns import (
        perrin_anisotropy,
        polarized_patterns,
    )

    truth = float(perrin_anisotropy(2.0, 1.0, 0.38))
    recovered = []
    for g_factor in (0.7, 1.0, 1.4):
        _, _, p_parallel = polarized_patterns(
            _sharp_response(), [1.0], [2.0], 1.0,
            Optics(r0_anisotropy=0.38, g_factor=g_factor),
        )
        recovered.append(_anisotropy_from_split(p_parallel, g_factor))
    assert all(r == pytest.approx(truth, abs=0.01) for r in recovered)
    # And the split really did move — otherwise the test would pass on a no-op.
    assert max(recovered) - min(recovered) < 0.005


def test_polarization_mixing_inverts_exactly():
    """l1 and l2 enter the amplitudes, not as a 2x2 mixing of an ideal pair."""
    from chisurf.core.fluorescence.mfd.patterns import (
        perrin_anisotropy,
        polarized_patterns,
    )

    truth = float(perrin_anisotropy(2.0, 1.0, 0.38))
    for l1, l2 in ((0.0, 0.0), (0.05, 0.03), (0.08, 0.0)):
        _, _, p_parallel = polarized_patterns(
            _sharp_response(), [1.0], [2.0], 1.0,
            Optics(r0_anisotropy=0.38, g_factor=1.2, l1=l1, l2=l2),
        )
        assert _anisotropy_from_split(
            p_parallel, 1.2, l1, l2
        ) == pytest.approx(truth, abs=0.01)


def test_a_faster_rotor_depolarises_more():
    """The direction of the effect, so a sign slip cannot hide behind a round trip."""
    from chisurf.core.fluorescence.mfd.patterns import polarized_patterns

    optics = Optics(r0_anisotropy=0.38)
    splits = [
        polarized_patterns(_sharp_response(), [1.0], [2.0], rho, optics)[2]
        for rho in (0.1, 1.0, 10.0)
    ]
    assert splits[0] < splits[1] < splits[2]
    # A freely rotating dye is unpolarized; a frozen one keeps r0.
    assert splits[0] == pytest.approx(0.5, abs=0.02)


def test_the_parallel_pattern_decays_faster_than_the_perpendicular():
    """VV carries ``1 + 2r`` and VH ``1 − r``, so the anisotropy makes VV arrive early."""
    from chisurf.core.fluorescence.mfd.moments import pattern_moments
    from chisurf.core.fluorescence.mfd.patterns import polarized_patterns

    parallel, perpendicular, _ = polarized_patterns(
        _sharp_response(), [1.0], [3.0], 1.0, Optics(r0_anisotropy=0.38)
    )
    assert pattern_moments(parallel, DT)[0] < pattern_moments(perpendicular, DT)[0]


# ──────────────────────────────────────────────────────────────────────────────
# The producers own the algebra — and these pin that they still say the same
# thing the closed forms this module used to carry did.
# ──────────────────────────────────────────────────────────────────────────────
def test_the_quenched_spectrum_is_the_producers_and_matches_the_closed_form():
    """``FretSpectrum`` against ``τ(R) = τ_D₀ / (1 + (R₀/R)⁶)``, to machine precision.

    The node works in *rates* — a transfer rate set by ``R₀`` and the reference
    lifetime ``τ_D₀`` it was determined at, added to the donor's own rate. For a
    single-exponential donor that is algebraically the same thing as scaling one
    lifetime by a quench factor, and this is the fixture that says so, so a future
    change to either spelling cannot pass unnoticed.
    """
    optics = Optics(r0=52.0, tau_d0=4.0, sigma=6.0)
    for distance in (30.0, 45.0, 52.0, 70.0, 120.0):
        amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
            FretState(distance=distance), optics
        )
        weights, r = noncentral_chi_distance_distribution(distance, optics.sigma)
        closed = optics.tau_d0 / (1.0 + (optics.r0 / r[0]) ** 6)
        assert lifetimes == pytest.approx(closed, abs=1e-14)
        assert amplitudes == pytest.approx(weights[0], abs=1e-15)


def test_a_multiexponential_donor_adds_rates_rather_than_scaling_lifetimes():
    """One ``R₀`` for the pair, therefore one transfer rate for every component.

    Scaling each donor component's lifetime by a common quench factor — which is
    what a closed form in ``τ`` does — gives each component *its own* Förster
    radius, which is not what a Förster radius is. The producer adds the transfer
    rate ``k_T`` to each component's own rate instead, so the two spellings agree
    only when the donor is single-exponential and this is the case that shows the
    difference is real rather than a rounding.
    """
    optics = Optics(r0=52.0, tau_d0=4.0, sigma=0.0)
    donor = [(0.5, 2.0), (0.5, 6.0)]
    _, lifetimes = donor_lifetime_spectrum_of_state(
        FretState(distance=52.0), optics, donor=donor
    )
    k_transfer = (1.0 / optics.tau_d0) * (optics.r0 / 52.0) ** 6
    assert lifetimes == pytest.approx(
        [1.0 / (1.0 / 2.0 + k_transfer), 1.0 / (1.0 / 6.0 + k_transfer)], rel=1e-12
    )
    # And it is *not* the common-quench-factor answer, which would be tau_i / 2.
    assert lifetimes[0] != pytest.approx(1.0, rel=1e-3)


@pytest.mark.parametrize("g_factor", [0.7, 1.0, 1.4, 2.0])
@pytest.mark.parametrize("l1, l2", [(0.0, 0.0), (0.05, 0.03), (0.1, 0.1)])
def test_the_polarised_split_does_not_depend_on_the_g_factor(g_factor, l1, l2):
    """The recovered anisotropy is a property of the dye, not of the detectors.

    ``AnisotropySpectrum``'s ``g`` port divides its *ideal* perpendicular spectrum
    **before** the ``l₁``/``l₂`` mixing, which leaves the mixing terms carrying a
    stray factor of ``G``; at ``G = 2``, ``l₁ = l₂ = 0.1`` that is a factor-of-two
    error in the recovered anisotropy. So the node is driven at ``g = 1`` — where
    its union-of-ideal-pairs form is *identically* the Schaffer/Eggeling amplitude
    form — and ``G`` is applied afterwards to the whole perpendicular channel,
    which is what a detection sensitivity is. This test is what pins that choice:
    it fails on the node's own ordering.
    """
    from chisurf.core.fluorescence.mfd.patterns import (
        perrin_anisotropy,
        polarized_patterns,
    )

    _, _, p_parallel = polarized_patterns(
        _sharp_response(), [1.0], [2.0], 1.0,
        Optics(r0_anisotropy=0.38, g_factor=g_factor, l1=l1, l2=l2),
    )
    recovered = _anisotropy_from_split(p_parallel, g_factor, l1, l2)
    assert recovered == pytest.approx(
        float(perrin_anisotropy(2.0, 1.0, 0.38)), abs=0.002
    )


def test_the_anisotropy_multiplies_a_photons_own_age_not_its_micro_time():
    """A wrapped photon is a period older than its micro time says, and ``r`` knows.

    The polarisation is built as a *spectrum* and each product component is then
    folded onto the laser period, so a photon detected at micro time ``t`` that is
    really ``t + T`` old carries ``r(t + T)``. Multiplying ``r(t)`` into an
    already-folded decay — the arrangement a time-domain split has to use — gives
    those photons the anisotropy of a younger photon and so over-polarises the
    tail. Here the window is short enough that 3% of the donor's photons wrap, and
    the parallel share differs measurably from the naive answer.
    """
    from chisurf.core.fluorescence.anisotropy.decay import vm_rt_to_vv_vh
    from chisurf.core.fluorescence.mfd.patterns import polarized_patterns

    optics = Optics(r0_anisotropy=0.38, g_factor=1.2, l1=0.05, l2=0.03)
    response = _response()
    amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
        FretState(distance=52.0), Optics()
    )
    _, _, p_parallel = polarized_patterns(
        response, amplitudes, lifetimes, 1.0, optics
    )

    decay = response.decay(amplitudes, lifetimes)
    vv, vh = vm_rt_to_vv_vh(
        np.arange(decay.size) * DT, decay, np.array([0.38, 1.0]),
        g_factor=1.2, l1=0.05, l2=0.03,
    )
    naive = float(vv.sum() / (vv.sum() + vh.sum()))

    # Close, because the two are the same physics discretised differently ...
    assert p_parallel == pytest.approx(naive, abs=1e-3)
    # ... but not equal, and the folded-product answer is the smaller one: the
    # wrapped photons are old, hence depolarised, hence less parallel.
    assert p_parallel < naive
