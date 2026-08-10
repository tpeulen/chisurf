"""Tests for the Gopich-Szabo photon-by-photon likelihood.

Three levels of check, in increasing strength:

1. **Internal consistency** — shapes, conventions, refusals.
2. **Against an independent implementation** — the likelihood recomputed in the
   state basis with ``scipy.linalg.expm``, which shares no code with the
   spectral kernel.
3. **Against the reference MATLAB** — log-likelihoods produced by PAM's
   unmodified ``GP_logL.m`` under Octave and frozen into
   ``test/data/gopich_szabo/pam_gs_reference.npz``.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.burst.burst_gs.core import simulate_two_state
from scipy.linalg import expm

from chisurf.core.fluorescence.burst import gopich_szabo as gs
from chisurf.core.fluorescence.kinetics import (
    equilibrium_populations,
    generator_from_rate_matrix,
)

REFERENCE = pathlib.Path(__file__).parent.parent / "data" / "gopich_szabo" / "pam_gs_reference.npz"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def brute_force_log_likelihood(times, colors, generator, emission) -> float:
    """Recompute the likelihood in the state basis with a matrix exponential.

    Deliberately naive and deliberately *not* the spectral formulation the
    module uses, so agreement is evidence rather than tautology.
    """
    populations = equilibrium_populations(generator)
    vector = np.diag(emission[:, colors[0]]) @ populations
    log_scale = 0.0
    for i in range(1, len(times)):
        step = expm(generator * (times[i] - times[i - 1]))
        vector = np.diag(emission[:, colors[i]]) @ step @ vector
        magnitude = abs(vector.sum())
        vector /= magnitude
        log_scale += np.log(magnitude)
    return float(np.log(vector.sum()) + log_scale)


@pytest.fixture(scope="module")
def reference():
    """The frozen Octave/PAM reference set."""
    if not REFERENCE.exists():  # pragma: no cover - fixture is committed
        pytest.skip("PAM reference fixture is missing")
    return np.load(REFERENCE)


# ──────────────────────────────────────────────────────────────────────────────
# Conventions
# ──────────────────────────────────────────────────────────────────────────────
def test_the_flat_rate_order_round_trips():
    """``rates_from_rate_matrix`` inverts ``rate_matrix_from_rates``."""
    rates = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    matrix = gs.rate_matrix_from_rates(rates, 3)
    assert np.allclose(gs.rates_from_rate_matrix(matrix), rates)


def test_the_first_two_state_rate_is_one_to_two():
    """``[k12, k21]`` means what it reads as: element ``[target, source]``."""
    matrix = gs.rate_matrix_from_rates([7.0, 11.0], 2)
    assert matrix[1, 0] == 7.0     # 1 -> 2
    assert matrix[0, 1] == 11.0    # 2 -> 1


def test_a_wrong_number_of_rates_is_rejected():
    """Three states need six rates, not four."""
    with pytest.raises(ValueError, match="need 6 rates"):
        gs.rate_matrix_from_rates([1.0, 2.0, 3.0, 4.0], 3)


def test_colour_zero_is_the_donor():
    """``emission_from_efficiencies`` puts ``1 - E`` in column 0."""
    emission = gs.emission_from_efficiencies([0.25, 0.75])
    assert np.allclose(emission, [[0.75, 0.25], [0.25, 0.75]])


def test_an_emission_matrix_that_does_not_sum_to_one_is_rejected():
    """Colour probabilities are a distribution, not arbitrary weights."""
    bursts = gs.PhotonBursts.from_lists(
        [np.array([0.0, 1e-5, 2e-5])], [np.array([0, 1, 0], dtype=np.int32)], 2
    )
    with pytest.raises(ValueError, match="sum to one"):
        gs.log_likelihood(bursts, gs.rate_matrix_from_rates([1e3, 1e3], 2),
                          np.array([[0.5, 0.9], [0.5, 0.1]]))


def test_single_photon_bursts_are_dropped():
    """A burst with one photon has no gap and so carries no kinetic evidence."""
    bursts = gs.PhotonBursts.from_lists(
        [np.array([0.0]), np.array([0.0, 1e-5, 2e-5])],
        [np.array([0], dtype=np.int32), np.array([0, 1, 0], dtype=np.int32)],
        2,
    )
    assert len(bursts) == 1
    assert bursts.n_photons == 3


def test_bursts_with_no_usable_photons_are_refused():
    """An empty photon set is an error, not a zero likelihood."""
    with pytest.raises(ValueError, match="enough photons"):
        gs.PhotonBursts.from_lists([np.array([0.0])], [np.array([0], dtype=np.int32)], 2)


# ──────────────────────────────────────────────────────────────────────────────
# Against an independent implementation
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "rates,efficiencies",
    [
        ([3000.0, 1200.0], [0.2, 0.8]),
        ([5e4, 2e4], [0.35, 0.9]),
        ([1e3, 2e2, 5e2, 8e2, 3e2, 1.5e3], [0.15, 0.5, 0.85]),
    ],
)
def test_the_spectral_kernel_matches_a_matrix_exponential(rates, efficiencies):
    """The eigenbasis recursion equals a naive ``expm`` propagation."""
    rng = np.random.default_rng(5)
    n_states = len(efficiencies)
    matrix = gs.rate_matrix_from_rates(rates, n_states)
    emission = gs.emission_from_efficiencies(efficiencies)
    times = np.sort(rng.uniform(0.0, 1e-3, 200))
    colors = rng.integers(0, 2, 200).astype(np.int32)

    ours = gs.log_likelihood(gs.PhotonBursts.from_lists([times], [colors], 2), matrix, emission)
    theirs = brute_force_log_likelihood(
        times, colors, generator_from_rate_matrix(matrix), emission
    )
    assert ours == pytest.approx(theirs, abs=1e-9)


def test_a_non_reversible_cycle_matches_a_matrix_exponential():
    """A complex spectrum is handled exactly, not truncated to its real part.

    A pure three-state circulation has a complex-conjugate eigenvalue pair. The
    reference implementation takes ``real()`` of the transformed emission
    matrices while keeping the eigenvalues complex, which is self-inconsistent
    and lands ~24 log units away on this very case (see
    ``test_the_reference_disagrees_only_on_a_complex_spectrum``).
    """
    rng = np.random.default_rng(5)
    matrix = np.zeros((3, 3))
    matrix[1, 0] = matrix[2, 1] = matrix[0, 2] = 1e3
    eigenvalues = np.linalg.eigvals(generator_from_rate_matrix(matrix))
    assert np.abs(eigenvalues.imag).max() > 1.0, "this scheme must have a complex spectrum"

    emission = gs.emission_from_efficiencies([0.1, 0.5, 0.9])
    times = np.sort(rng.uniform(0.0, 1e-3, 200))
    colors = rng.integers(0, 2, 200).astype(np.int32)
    ours = gs.log_likelihood(gs.PhotonBursts.from_lists([times], [colors], 2), matrix, emission)
    theirs = brute_force_log_likelihood(
        times, colors, generator_from_rate_matrix(matrix), emission
    )
    assert ours == pytest.approx(theirs, abs=1e-9)


def test_three_colours_match_a_matrix_exponential():
    """The general ``(n_states, n_colors)`` emission path is exact too."""
    rng = np.random.default_rng(9)
    matrix = gs.rate_matrix_from_rates([2e3, 1e3], 2)
    emission = np.array([[0.6, 0.3, 0.1], [0.2, 0.5, 0.3]])
    times = np.sort(rng.uniform(0.0, 1e-3, 250))
    colors = rng.integers(0, 3, 250).astype(np.int32)
    ours = gs.log_likelihood(gs.PhotonBursts.from_lists([times], [colors], 3), matrix, emission)
    theirs = brute_force_log_likelihood(
        times, colors, generator_from_rate_matrix(matrix), emission
    )
    assert ours == pytest.approx(theirs, abs=1e-9)


def test_bursts_are_independent():
    """The total is the sum over bursts, so splitting a set changes nothing."""
    rng = np.random.default_rng(13)
    matrix = gs.rate_matrix_from_rates([2e3, 1e3], 2)
    emission = gs.emission_from_efficiencies([0.2, 0.8])
    times = [np.sort(rng.uniform(0.0, 1e-3, 60)) for _ in range(4)]
    colors = [rng.integers(0, 2, 60).astype(np.int32) for _ in range(4)]

    together = gs.log_likelihood(gs.PhotonBursts.from_lists(times, colors, 2), matrix, emission)
    apart = sum(
        gs.log_likelihood(gs.PhotonBursts.from_lists([t], [c], 2), matrix, emission)
        for t, c in zip(times, colors)
    )
    assert together == pytest.approx(apart, abs=1e-9)


def test_the_multi_dataset_likelihood_is_the_sum():
    """Two photon sets sharing a rate matrix add their log-likelihoods."""
    rng = np.random.default_rng(17)
    matrix = gs.rate_matrix_from_rates([2e3, 1e3], 2)
    emission = gs.emission_from_efficiencies([0.2, 0.8])
    bursts = gs.PhotonBursts.from_lists(
        [np.sort(rng.uniform(0.0, 1e-3, 80))],
        [rng.integers(0, 2, 80).astype(np.int32)],
        2,
    )
    one = gs.log_likelihood(bursts, matrix, emission)
    both = gs.log_likelihood_multi([(bursts, emission), (bursts, emission)], matrix)
    assert both == pytest.approx(2.0 * one, abs=1e-9)


# ──────────────────────────────────────────────────────────────────────────────
# Against the reference MATLAB, via Octave
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("case", ["2state", "2state_fast", "3state_chain"])
def test_the_reference_matlab_agrees_on_a_real_spectrum(reference, case):
    """PAM's ``GP_logL.m`` and this module agree to round-off where both are valid."""
    emission = gs.emission_from_efficiencies(reference[f"{case}_efficiencies"])
    bursts = gs.PhotonBursts.from_lists(
        [reference[f"{case}_times"]], [reference[f"{case}_colors"].astype(np.int32)], 2
    )
    ours = gs.log_likelihood(bursts, reference[f"{case}_generator"], emission)
    assert ours == pytest.approx(float(reference[f"{case}_octave_logl"]), rel=1e-12)


def test_the_reference_disagrees_only_on_a_complex_spectrum(reference):
    """Pin the one case where the reference implementation is wrong.

    On a non-reversible cycle PAM discards the imaginary part of the
    transformed emission matrices, which is a genuine error rather than a
    convention difference: an independent ``expm`` propagation lands on this
    module's value, not on PAM's. Pinned so that a future change which
    "restores agreement with PAM" is caught as the regression it would be.
    """
    case = "3state_cycle"
    emission = gs.emission_from_efficiencies(reference[f"{case}_efficiencies"])
    generator = reference[f"{case}_generator"]
    times = reference[f"{case}_times"]
    colors = reference[f"{case}_colors"].astype(np.int32)

    ours = gs.log_likelihood(gs.PhotonBursts.from_lists([times], [colors], 2),
                             generator, emission)
    arbiter = brute_force_log_likelihood(times, colors, generator, emission)
    pam = float(reference[f"{case}_octave_logl"])

    assert ours == pytest.approx(arbiter, abs=1e-9)
    assert abs(ours - pam) > 10.0


# ──────────────────────────────────────────────────────────────────────────────
# Recovery of known parameters
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_a_fit_recovers_simulated_rates_and_efficiencies():
    """The whole point: known kinetics in, the same kinetics out."""
    bursts = simulate_two_state(3000.0, 1000.0, [0.25, 0.75], 50e3, 300, 200, seed=7)
    result = gs.fit(bursts, n_states=2, initial_rates=[1e3, 1e3],
                    initial_efficiencies=[0.3, 0.7])
    assert result.success
    assert result.rate_matrix[1, 0] == pytest.approx(3000.0, rel=0.15)
    assert result.rate_matrix[0, 1] == pytest.approx(1000.0, rel=0.15)
    assert result.efficiencies[0] == pytest.approx(0.25, abs=0.03)
    assert result.efficiencies[1] == pytest.approx(0.75, abs=0.03)


@pytest.mark.slow
def test_fixing_the_efficiencies_still_recovers_the_rates():
    """With E known from a static measurement only the rates are free."""
    bursts = simulate_two_state(3000.0, 1000.0, [0.25, 0.75], 50e3, 200, 200, seed=11)
    result = gs.fit(bursts, n_states=2, initial_rates=[5e2, 5e2],
                    initial_efficiencies=[0.25, 0.75], fix_efficiencies=True)
    assert result.n_parameters == 2
    assert result.rate_matrix[1, 0] == pytest.approx(3000.0, rel=0.2)
    assert result.rate_matrix[0, 1] == pytest.approx(1000.0, rel=0.2)
    assert np.allclose(result.efficiencies, [0.25, 0.75])


def test_the_true_parameters_beat_wrong_ones():
    """A cheap sanity check that the surface points the right way."""
    bursts = simulate_two_state(3000.0, 1000.0, [0.2, 0.8], 50e3, 40, 150, seed=3)
    truth = gs.log_likelihood(
        bursts, gs.rate_matrix_from_rates([3000.0, 1000.0], 2),
        gs.emission_from_efficiencies([0.2, 0.8]),
    )
    wrong = gs.log_likelihood(
        bursts, gs.rate_matrix_from_rates([3000.0, 1000.0], 2),
        gs.emission_from_efficiencies([0.5, 0.55]),
    )
    assert truth > wrong


# ──────────────────────────────────────────────────────────────────────────────
# Viterbi
# ──────────────────────────────────────────────────────────────────────────────
def test_viterbi_finds_a_clean_switch():
    """Photons that are obviously donor then obviously acceptor decode as such."""
    rng = np.random.default_rng(2)
    n = 400
    times = np.arange(n) * 1e-5
    colors = np.concatenate(
        [(rng.random(n // 2) < 0.02).astype(np.int32),
         (rng.random(n // 2) < 0.98).astype(np.int32)]
    )
    bursts = gs.PhotonBursts.from_lists([times], [colors], 2)
    path = gs.viterbi(bursts, gs.rate_matrix_from_rates([200.0, 200.0], 2),
                      gs.emission_from_efficiencies([0.02, 0.98]))
    assert path[: n // 2].mean() < 0.02
    assert path[n // 2:].mean() > 0.98


def test_viterbi_returns_one_state_per_photon():
    """The path aligns photon-for-photon with the flat burst layout."""
    rng = np.random.default_rng(4)
    times = [np.sort(rng.uniform(0.0, 1e-3, 50)) for _ in range(3)]
    colors = [rng.integers(0, 2, 50).astype(np.int32) for _ in range(3)]
    bursts = gs.PhotonBursts.from_lists(times, colors, 2)
    path = gs.viterbi(bursts, gs.rate_matrix_from_rates([1e3, 1e3], 2),
                      gs.emission_from_efficiencies([0.2, 0.8]))
    assert path.shape == (bursts.n_photons,)
    assert set(np.unique(path)) <= {0, 1}


# ──────────────────────────────────────────────────────────────────────────────
# Transition-state model
# ──────────────────────────────────────────────────────────────────────────────
def test_the_transition_state_keeps_the_effective_rates():
    """Doubling the entry rates is what preserves the two-state exchange."""
    matrix, efficiencies = gs.transition_state_model(3000.0, 1000.0, 1e-5, [0.2, 0.8])
    assert matrix[1, 0] == 6000.0
    assert matrix[1, 2] == 2000.0
    assert matrix[0, 1] == matrix[2, 1] == pytest.approx(1.0 / (2.0 * 1e-5))
    assert efficiencies[1] == pytest.approx(0.5)


def test_an_instantaneous_transition_state_is_refused():
    """Zero duration is the two-state model; building it as three states is a bug."""
    with pytest.raises(ValueError, match="must be positive"):
        gs.transition_state_model(1e3, 1e3, 0.0, [0.2, 0.8])


def test_a_transition_far_faster_than_the_photons_costs_nothing():
    """The scan is flat where the data cannot resolve the crossing.

    A crossing much shorter than the mean interphoton time leaves no trace, so
    the likelihood must return to the instantaneous baseline rather than
    inventing support for it. This is what makes the scan an honest upper bound.
    """
    bursts = simulate_two_state(3000.0, 1000.0, [0.2, 0.8], 50e3, 40, 150, seed=19)
    transits, delta, baseline = gs.transition_time_scan(
        bursts, 3000.0, 1000.0, [0.2, 0.8], transit_times=[1e-9, 1e-8]
    )
    assert np.isfinite(baseline)
    assert np.all(np.abs(delta) < 1.0)


def test_the_transition_scan_disfavours_an_absurdly_long_crossing():
    """A crossing as long as the dwell time itself must be rejected by the data."""
    bursts = simulate_two_state(3000.0, 1000.0, [0.2, 0.8], 50e3, 60, 200, seed=23)
    _, delta, _ = gs.transition_time_scan(
        bursts, 3000.0, 1000.0, [0.2, 0.8], transit_times=[1e-9, 1e-3]
    )
    assert delta[1] < delta[0] - 10.0


# ──────────────────────────────────────────────────────────────────────────────
# Result object
# ──────────────────────────────────────────────────────────────────────────────
def test_the_result_serialises_and_scores():
    """``to_dict`` is JSON-ready and the information criteria are consistent."""
    bursts = simulate_two_state(3000.0, 1000.0, [0.2, 0.8], 50e3, 20, 120, seed=29)
    result = gs.fit(bursts, n_states=2, max_iterations=60)
    payload = result.to_dict()
    assert set(payload) >= {"rates", "efficiencies", "log_likelihood", "bic", "aic"}
    assert payload["bic"] == pytest.approx(
        result.n_parameters * np.log(result.n_photons) - 2.0 * result.log_likelihood
    )
    assert payload["aic"] < payload["bic"]  # many photons, so BIC penalises harder


def test_no_exchange_reduces_to_a_static_mixture():
    """With every rate zero the answer must be the static two-species likelihood.

    This is the limit that makes the dynamic fit comparable to a static one:
    ``logL`` at zero rates is exactly what a mixture model would report, so the
    likelihood ratio between them is meaningful rather than an artefact of
    changing formalism.
    """
    bursts = gs.PhotonBursts.from_lists(
        [np.array([0.0, 1e-5, 2e-5, 3e-5])],
        [np.array([0, 1, 0, 1], dtype=np.int32)],
        2,
    )
    value = gs.log_likelihood(bursts, np.zeros((2, 2)), gs.emission_from_efficiencies([0.2, 0.8]))
    # Two equally-weighted static species emitting d, a, d, a.
    expected = np.log(0.5 * (0.8 * 0.2 * 0.8 * 0.2) + 0.5 * (0.2 * 0.8 * 0.2 * 0.8))
    assert value == pytest.approx(expected, abs=1e-12)


def test_a_defective_rate_matrix_backs_the_optimiser_off():
    """A non-diagonalisable generator returns ``-inf`` instead of noise.

    An irreversible chain with equal rates has a repeated eigenvalue and only
    one eigenvector, so the spectral propagator does not exist. Returning
    ``-inf`` is what keeps an optimiser away from it; computing something from
    the ill-conditioned inverse would hand back a plausible-looking number.
    """
    bursts = gs.PhotonBursts.from_lists(
        [np.array([0.0, 1e-5, 2e-5, 3e-5])],
        [np.array([0, 1, 0, 1], dtype=np.int32)],
        2,
    )
    chain = np.zeros((3, 3))
    chain[1, 0] = chain[2, 1] = 1e3
    value = gs.log_likelihood(bursts, chain, gs.emission_from_efficiencies([0.2, 0.5, 0.8]))
    assert value == float("-inf")


def test_a_rejected_scheme_falls_through_instead_of_reporting_impossible():
    """A compiled engine that will not take the scheme must not answer ``-inf``.

    ``-inf`` is reserved for a model that genuinely has no likelihood -- the
    defective generator above. A *setup* failure is a different thing, and
    conflating the two is how the no-exchange limit came to report "forbidden"
    for parameters whose likelihood is perfectly well defined: the photon
    library's ``set_scheme`` returns False for an all-zero rate matrix, and the
    delegation used to return ``-inf`` on that.

    The failure mode this pins is silent by construction -- the optimiser sees a
    finite value everywhere else and a wall at the static limit -- so the test
    forces the rejection rather than waiting for a version of the library that
    happens to exhibit it.
    """
    bursts = gs.PhotonBursts.from_lists(
        [np.array([0.0, 1e-5, 2e-5, 3e-5])],
        [np.array([0, 1, 0, 1], dtype=np.int32)],
        2,
    )
    emission = gs.emission_from_efficiencies([0.2, 0.8])
    rates = np.array([[0.0, 1e3], [1e3, 0.0]])

    reference = gs.log_likelihood(bursts, rates, emission)
    assert np.isfinite(reference)

    tttrlib = pytest.importorskip("tttrlib")
    if not hasattr(tttrlib, "GopichSzabo"):
        pytest.skip("the compiled engine is not present to reject anything")

    class _Rejecting(tttrlib.GopichSzabo):
        """Stands in for a library build that will not accept this scheme."""

        def set_scheme(self, *args, **kwargs):
            return False

    original = tttrlib.GopichSzabo
    tttrlib.GopichSzabo = _Rejecting
    try:
        fallen_through = gs.log_likelihood(bursts, rates, emission)
    finally:
        tttrlib.GopichSzabo = original

    assert fallen_through == pytest.approx(reference, rel=1e-9), (
        "a rejected scheme did not fall through to the in-tree implementation"
    )
