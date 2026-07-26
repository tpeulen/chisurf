"""Three-colour PDA model — PRD-65 stage 2.

The stage-2 acceptance criterion is deliberately stronger than "recovers three
distances": a method whose entire justification is that it observes the three
distances *jointly* has to be shown recovering their **correlation**, with an
uncorrelated control that does not invent one.
"""

from __future__ import annotations

import numpy as np
import pytest

# ── transfer efficiencies ──────────────────────────────────────────────────


def test_pathways_compete_for_the_same_excited_donor():
    """Opening B->R lowers E_BG even though R_BG did not move.

    The three-colour trap: reading a two-colour formula off one dye pair of a
    three-colour construct overestimates the distance, because the second
    acceptor is quietly draining the donor.
    """
    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSetup,
        distances_to_matrix,
        transfer_efficiencies,
    )

    setup = ThreeColorSetup.from_scalars(r0_bg=50.0, r0_br=50.0, r0_gr=50.0)
    alone = transfer_efficiencies(distances_to_matrix([50.0, 1e9, 60.0]), setup)[0, 1]
    competing = transfer_efficiencies(distances_to_matrix([50.0, 50.0, 60.0]), setup)[0, 1]

    assert alone == pytest.approx(0.5)  # ordinary two-colour result at R = R0
    assert competing == pytest.approx(1.0 / 3.0)
    assert competing < alone


def test_two_colour_limit_of_the_green_red_pair():
    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSetup,
        distances_to_matrix,
        transfer_efficiencies,
    )

    setup = ThreeColorSetup.from_scalars(r0_gr=52.0)
    assert transfer_efficiencies(distances_to_matrix([1e9, 1e9, 52.0]), setup)[1, 2] == pytest.approx(0.5)
    assert transfer_efficiencies(distances_to_matrix([1e9, 1e9, 1e9]), setup)[1, 2] == pytest.approx(0.0, abs=1e-9)
    assert transfer_efficiencies(distances_to_matrix([1e9, 1e9, 1.0]), setup)[1, 2] == pytest.approx(1.0, abs=1e-9)


def test_channel_probabilities_are_distributions():
    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSetup,
        blue_channel_probabilities,
        green_channel_probabilities,
    )

    setup = ThreeColorSetup.from_scalars(r0_bg=49.0, r0_br=55.0, r0_gr=52.0)
    r = np.linspace(20.0, 90.0, 25)
    blue = blue_channel_probabilities(r, r[::-1], r, setup)
    green = green_channel_probabilities(r, setup)

    assert blue.shape == (25, 3) and green.shape == (25, 2)
    assert np.allclose(blue.sum(axis=1), 1.0)
    assert np.allclose(green.sum(axis=1), 1.0)
    assert np.all(blue >= 0.0) and np.all(green >= 0.0)


def test_red_channel_is_fed_by_both_routes():
    """Direct B->R and the B->G->R relay both land in red — the identifiability.

    With the relay closed (G and R far apart) the red channel sees only direct
    transfer; opening it must add signal that the direct route cannot explain.
    """
    from chisurf.core.fluorescence.c3pda import ThreeColorSetup, blue_channel_probabilities

    setup = ThreeColorSetup.from_scalars(r0_bg=50.0, r0_br=50.0, r0_gr=50.0)
    relay_closed = blue_channel_probabilities(50.0, 50.0, 1e9, setup)
    relay_open = blue_channel_probabilities(50.0, 50.0, 30.0, setup)

    assert relay_open[..., 2] > relay_closed[..., 2]
    assert relay_open[..., 1] < relay_closed[..., 1]  # green gives its energy on
    # the blue channel cannot tell the difference: it lost the photon either way
    assert relay_open[..., 0] == pytest.approx(relay_closed[..., 0])


def test_detection_crosstalk_moves_counts_between_channels():
    from chisurf.core.fluorescence.c3pda import ThreeColorSetup, blue_channel_probabilities

    clean = ThreeColorSetup.from_scalars()
    leaky = ThreeColorSetup.from_scalars(crosstalk_bg=0.2, crosstalk_gr=0.1)
    args = (50.0, 60.0, 55.0)
    assert blue_channel_probabilities(*args, leaky)[..., 1] > (
        blue_channel_probabilities(*args, clean)[..., 1]
    )


# ── species: covariance handling ───────────────────────────────────────────


def test_cholesky_round_trips_the_user_facing_statistics():
    from chisurf.core.fluorescence.c3pda import (
        cholesky_to_statistics,
        covariance_from_statistics,
        covariance_to_cholesky,
    )

    sigmas = np.array([5.0, 7.0, 6.0])
    correlations = np.array([0.6, -0.3, 0.1])
    covariance = covariance_from_statistics(sigmas, correlations)
    back_sigmas, back_correlations = cholesky_to_statistics(covariance_to_cholesky(covariance))

    assert np.allclose(back_sigmas, sigmas)
    assert np.allclose(back_correlations, correlations)


def test_inconsistent_correlations_are_repaired_not_fatal():
    """Three pairwise correlations can be mutually impossible; don't crash on it."""
    from chisurf.core.fluorescence.c3pda import (
        covariance_from_statistics,
        covariance_to_cholesky,
        nearest_positive_definite,
    )

    impossible = covariance_from_statistics([5.0, 5.0, 5.0], [-0.9, -0.9, -0.9])
    assert np.min(np.linalg.eigvalsh(impossible)) < 0.0  # genuinely not a covariance

    repaired = nearest_positive_definite(impossible)
    assert np.min(np.linalg.eigvalsh(repaired)) > 0.0
    covariance_to_cholesky(impossible)  # must not raise


# ── quadrature ─────────────────────────────────────────────────────────────


def test_gauss_hermite_reproduces_the_gaussian_moments():
    """The quadrature must integrate the species it stands for, exactly."""
    from chisurf.core.fluorescence.c3pda import covariance_from_statistics, gauss_hermite_grid
    from chisurf.core.fluorescence.c3pda.species import covariance_to_cholesky

    means = np.array([55.0, 48.0, 62.0])
    covariance = covariance_from_statistics([6.0, 5.0, 7.0], [0.5, -0.2, 0.3])
    points, weights = gauss_hermite_grid(means, covariance_to_cholesky(covariance), n_nodes=7)

    assert weights.sum() == pytest.approx(1.0)
    assert np.allclose(weights @ points, means, atol=1e-8)

    centred = points - means
    recovered = (weights[:, None, None] * centred[:, :, None] * centred[:, None, :]).sum(axis=0)
    assert np.allclose(recovered, covariance, atol=1e-7)


def test_quadrature_beats_a_uniform_grid_at_equal_node_count():
    """The PRD's largest lever, measured on a quantity the model actually uses.

    Comparing means would prove nothing — a symmetric uniform grid gets those
    exact by symmetry whatever its quadrature quality. The honest comparison is
    a *nonlinear* functional of the distances, so this integrates the mean FRET
    efficiency over the species and scores both schemes against a dense
    reference at the same node budget per axis.
    """
    from chisurf.core.fluorescence.c3pda import (
        covariance_from_statistics,
        distances_to_matrix,
        gauss_hermite_grid,
        transfer_efficiencies,
    )
    from chisurf.core.fluorescence.c3pda.species import covariance_to_cholesky

    setup = _setup()
    means = np.array([55.0, 48.0, 62.0])
    covariance = covariance_from_statistics([6.0, 5.0, 7.0], [0.5, -0.2, 0.3])
    cholesky = covariance_to_cholesky(covariance)

    def mean_efficiency(points, weights):
        pairs = np.stack([points[:, 1], points[:, 2], points[:, 0]], axis=1)
        e = transfer_efficiencies(distances_to_matrix(pairs), setup)
        return float(weights @ (e[:, 0, 1] + e[:, 0, 2] + e[:, 1, 2]))

    reference = mean_efficiency(*gauss_hermite_grid(means, cholesky, n_nodes=40))
    quadrature = mean_efficiency(*gauss_hermite_grid(means, cholesky, n_nodes=5))

    # Uniform grid with the same nodes per axis, spanning +-4 sigma, weighted by
    # the true density — the scheme the quadrature replaces.
    sigmas = np.sqrt(np.diag(covariance))
    axes = [np.linspace(m - 4 * s, m + 4 * s, 5) for m, s in zip(means, sigmas)]
    grid = np.stack([g.ravel() for g in np.meshgrid(*axes, indexing="ij")], axis=1)
    delta = grid - means
    density = np.exp(-0.5 * np.einsum("ij,jk,ik->i", delta, np.linalg.inv(covariance), delta))
    uniform = mean_efficiency(grid, density / density.sum())

    quad_error = abs(quadrature - reference)
    grid_error = abs(uniform - reference)
    assert quad_error < grid_error / 10.0, (quad_error, grid_error)


def test_truncation_drops_corner_nodes_without_moving_the_mean():
    from chisurf.core.fluorescence.c3pda import gauss_hermite_grid

    cholesky = np.diag([6.0, 5.0, 7.0])
    means = np.array([55.0, 48.0, 62.0])
    full, w_full = gauss_hermite_grid(means, cholesky, n_nodes=9, truncate=0.0)
    cut, w_cut = gauss_hermite_grid(means, cholesky, n_nodes=9, truncate=1e-6)

    assert cut.shape[0] < full.shape[0]
    assert np.allclose(w_cut @ cut, w_full @ full, atol=1e-6)


# ── the assembled model ────────────────────────────────────────────────────


def _setup():
    from chisurf.core.fluorescence.c3pda import ThreeColorSetup

    return ThreeColorSetup.from_scalars(r0_bg=49.0, r0_br=52.0, r0_gr=51.0)


def test_collapsing_joins_both_excitation_periods():
    """Two bursts agreeing on blue but not green are different bursts."""
    from chisurf.core.fluorescence.c3pda import BurstCounts

    counts = BurstCounts(
        blue=[[5, 3, 2], [5, 3, 2], [5, 3, 2]],
        green=[[4, 1], [4, 1], [2, 3]],
    )
    collapsed = counts.collapsed()
    assert collapsed.blue.shape[0] == 2
    assert collapsed.multiplicity.sum() == 3
    assert sorted(collapsed.multiplicity.tolist()) == [1.0, 2.0]


def test_collapsing_does_not_change_the_likelihood():
    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSpecies,
        simulate_bursts,
        total_log_likelihood,
    )

    setup = _setup()
    species = [ThreeColorSpecies(1.0, np.array([50.0, 45.0, 65.0]), np.eye(3) * 25.0)]
    counts = simulate_bursts(400, species, setup, seed=1)

    full = total_log_likelihood(counts, species, setup, n_nodes=5)
    collapsed = total_log_likelihood(counts.collapsed(), species, setup, n_nodes=5)
    assert full == pytest.approx(collapsed, rel=1e-10)


def test_the_two_periods_are_mixed_jointly_not_separately():
    """Averaging blue and green separately would erase the joint information.

    A molecule is at one distance triple during both pulses. Mixing the periods
    independently models one that re-randomises between them, which is a
    strictly different (and larger) likelihood for a broad species. The test
    pins the distinction rather than trusting the implementation reads right.
    """
    import numpy as np
    from scipy.special import logsumexp

    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSpecies,
        blue_channel_probabilities,
        burst_log_likelihood,
        green_channel_probabilities,
        simulate_bursts,
        total_log_likelihood,
    )

    setup = _setup()
    wide = np.diag([100.0, 100.0, 100.0])  # broad species -> the two differ most
    species = [ThreeColorSpecies(1.0, np.array([50.0, 50.0, 60.0]), wide)]
    counts = simulate_bursts(200, species, setup, seed=5).collapsed()

    joint = total_log_likelihood(counts, species, setup, n_nodes=7)

    points, weights = species[0].quadrature(n_nodes=7)
    p_blue = blue_channel_probabilities(points[:, 1], points[:, 2], points[:, 0], setup)
    p_green = green_channel_probabilities(points[:, 0], setup)
    log_w = np.log(weights)[:, None]
    separate = float(
        np.sum(
            counts.multiplicity
            * (
                logsumexp(log_w + burst_log_likelihood(counts.blue, p_blue), axis=0)
                + logsumexp(log_w + burst_log_likelihood(counts.green, p_green), axis=0)
            )
        )
    )
    assert not np.isclose(joint, separate, rtol=1e-6)


def test_likelihood_peaks_at_the_truth():
    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSpecies,
        simulate_bursts,
        total_log_likelihood,
    )

    setup = _setup()
    truth = np.array([52.0, 46.0, 68.0])
    covariance = np.diag([16.0, 16.0, 16.0])
    species = [ThreeColorSpecies(1.0, truth, covariance)]
    counts = simulate_bursts(3000, species, setup, seed=2).collapsed()

    best = total_log_likelihood(counts, species, setup, n_nodes=5)
    for offset in ([8.0, 0, 0], [0, 8.0, 0], [0, 0, 8.0], [-8.0, 0, 0]):
        moved = [ThreeColorSpecies(1.0, truth + np.array(offset), covariance)]
        assert total_log_likelihood(counts, moved, setup, n_nodes=5) < best


@pytest.mark.slow
def test_recovers_three_distances_and_their_correlation():
    """PRD-65 stage-2 acceptance.

    Fits a synthetic three-colour burst set for the three mean distances *and*
    the R_GR/R_BG correlation. The correlated case must recover a clearly
    positive coefficient and the uncorrelated control must not invent one —
    a method sold on measuring joint motion has to be shown doing it.
    """
    from scipy.optimize import minimize

    from chisurf.core.fluorescence.c3pda import (
        ThreeColorSpecies,
        covariance_from_statistics,
        simulate_bursts,
        total_log_likelihood,
    )

    setup = _setup()
    truth = np.array([52.0, 46.0, 68.0])
    sigmas = np.array([6.0, 6.0, 6.0])

    def fit(true_rho, seed):
        covariance = covariance_from_statistics(sigmas, [true_rho, 0.0, 0.0])
        truth_species = [ThreeColorSpecies(1.0, truth, covariance)]
        counts = simulate_bursts(
            6000, truth_species, setup, photons_blue=40.0, photons_green=35.0, seed=seed
        ).collapsed()

        def negative_log_likelihood(x):
            means = x[:3]
            rho = np.tanh(x[3])  # keeps the correlation in (-1, 1)
            trial = [
                ThreeColorSpecies(1.0, means, covariance_from_statistics(sigmas, [rho, 0.0, 0.0]))
            ]
            return -total_log_likelihood(counts, trial, setup, n_nodes=5)

        start = np.array([48.0, 50.0, 62.0, 0.0])  # deliberately off
        result = minimize(negative_log_likelihood, start, method="Nelder-Mead",
                          options={"xatol": 1e-2, "fatol": 1e-2, "maxiter": 2000})
        return result.x[:3], float(np.tanh(result.x[3]))

    # Measured: (52.09, 46.04, 67.23) with rho = +0.767 against a truth of
    # (52, 46, 68) and 0.8; the control lands on rho = -0.000. Seeds are fixed,
    # so these bounds are tight on purpose — a loose one would pass on a model
    # that had stopped measuring correlation at all.
    means_corr, rho_corr = fit(0.8, seed=11)
    assert np.allclose(means_corr, truth, atol=1.5), means_corr
    assert rho_corr > 0.6, rho_corr

    means_flat, rho_flat = fit(0.0, seed=12)
    assert np.allclose(means_flat, truth, atol=1.5), means_flat
    assert abs(rho_flat) < 0.15, rho_flat
