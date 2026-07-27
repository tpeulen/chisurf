"""Three-colour PDA forward model — PRD-65 stage 1.

Two things need proving before anything is built on top of this module: that the
convolution factorisation of the background sum is *exact* (not merely fast),
and that the whole construction reduces to the validated two-colour engine when
the third channel is switched off.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

# ── the zero-background term ───────────────────────────────────────────────


def test_multinomial_matches_scipy():
    from chisurf.core.fluorescence.pda3c import log_multinomial_pmf

    counts = np.array([7, 3, 5])
    p = np.array([0.5, 0.2, 0.3])
    expected = stats.multinomial.logpmf(counts, n=counts.sum(), p=p)
    assert log_multinomial_pmf(counts, p) == pytest.approx(expected)


def test_multinomial_broadcasts_to_the_full_grid():
    """The (points x bursts) grid comes out of one broadcast, not a loop."""
    from chisurf.core.fluorescence.pda3c import log_multinomial_pmf

    counts = np.array([[7, 3, 5], [2, 2, 2], [0, 0, 9]])
    p = np.array([[0.5, 0.2, 0.3], [0.2, 0.5, 0.3]])
    grid = log_multinomial_pmf(counts[None, :, :], p[:, None, :])
    assert grid.shape == (2, 3)
    for i in range(2):
        for j in range(3):
            assert grid[i, j] == pytest.approx(log_multinomial_pmf(counts[j], p[i]))


def test_impossible_channel_is_finite_when_it_saw_nothing():
    """p=0 with a zero count is a channel that cannot fire and did not — not a nan."""
    from chisurf.core.fluorescence.pda3c import log_multinomial_pmf

    assert np.isfinite(log_multinomial_pmf([4, 0], [1.0, 0.0]))
    assert log_multinomial_pmf([4, 1], [1.0, 0.0]) == -np.inf


def test_a_negative_probability_is_impossible_not_certain():
    """A row that left the simplex must not outscore one that stayed on it.

    Flooring a negative entry to one would score its photons for free, which
    lifts the "log probability" above zero — an optimiser handed that is being
    paid to leave the physical region.
    """
    from chisurf.core.fluorescence.pda3c import log_multinomial_pmf

    counts = [6, 2, 3]
    assert log_multinomial_pmf(counts, [-0.1, 0.6, 0.5]) == -np.inf
    # ... and the whole row goes, not just the offending channel: with one
    # entry negative the rest no longer sums to one either.
    assert log_multinomial_pmf([0, 2, 3], [-0.1, 0.6, 0.5]) == -np.inf
    # a valid row is a log probability, i.e. never positive
    assert log_multinomial_pmf(counts, [0.2, 0.3, 0.5]) < 0.0


def test_a_negative_probability_only_kills_its_own_row():
    """Rejection is per model point, not per call."""
    from chisurf.core.fluorescence.pda3c import log_multinomial_pmf

    counts = np.array([[6, 2, 3]])
    p = np.array([[-0.1, 0.6, 0.5], [0.2, 0.3, 0.5]])
    grid = log_multinomial_pmf(counts[None, :, :], p[:, None, :])
    assert grid[0, 0] == -np.inf
    assert np.isfinite(grid[1, 0])
    assert grid[1, 0] == pytest.approx(log_multinomial_pmf(counts[0], p[1]))


def test_the_burst_path_also_rejects_a_negative_probability():
    """The background path must not resurrect what the multinomial rejected."""
    from chisurf.core.fluorescence.pda3c import burst_log_likelihood

    out = burst_log_likelihood([[6, 2, 3]], [[-0.1, 0.6, 0.5]], background=[0.2, 0.2, 0.2])
    assert out[0, 0] == -np.inf


# ── the background factorisation ───────────────────────────────────────────


@pytest.mark.parametrize(
    "counts, background",
    [
        ([4, 3, 2], [0.5, 0.4, 0.3]),
        ([6, 1, 0], [1.2, 0.2, 0.7]),
        ([3, 3], [0.8, 0.9]),
        ([5, 4], [0.0, 1.5]),  # one clean channel
    ],
)
def test_convolution_equals_the_nested_sum(counts, background):
    """The whole point: collapsing the K-fold sum changes nothing but the cost."""
    from chisurf.core.fluorescence.pda3c import (
        burst_log_likelihood,
        burst_log_likelihood_reference,
    )

    counts = np.array([counts])
    k = counts.shape[1]
    p = np.array([np.full(k, 1.0 / k), np.linspace(0.2, 0.6, k) / np.linspace(0.2, 0.6, k).sum()])

    fast = burst_log_likelihood(counts, p, background=background)
    slow = burst_log_likelihood_reference(counts, p, background=background)
    assert np.allclose(fast, slow, rtol=1e-10, atol=1e-12)


def test_convolution_equals_the_nested_sum_with_a_photon_number_distribution():
    from chisurf.core.fluorescence.pda3c import (
        burst_log_likelihood,
        burst_log_likelihood_reference,
    )

    n = np.arange(0, 21)
    pn = stats.poisson.pmf(n, mu=8.0)
    pn /= pn.sum()

    counts = np.array([[4, 3, 2], [5, 1, 1]])
    p = np.array([[0.5, 0.3, 0.2], [0.2, 0.2, 0.6]])
    background = np.array([0.6, 0.4, 0.5])

    fast = burst_log_likelihood(counts, p, background, photon_number_pmf=pn)
    slow = burst_log_likelihood_reference(counts, p, background, photon_number_pmf=pn)
    assert np.allclose(fast, slow, rtol=1e-9, atol=1e-12)


def test_zero_background_is_exactly_the_multinomial():
    """The fast path and the correction compose: no background, no correction."""
    from chisurf.core.fluorescence.pda3c import burst_log_likelihood, log_multinomial_pmf

    counts = np.array([[6, 3, 1]])
    p = np.array([[0.6, 0.3, 0.1]])
    assert burst_log_likelihood(counts, p, background=[0.0, 0.0, 0.0])[0, 0] == pytest.approx(
        log_multinomial_pmf(counts[0], p[0])
    )


def test_the_two_internal_background_paths_agree():
    """The vectorised GEMM path must equal the per-burst convolution it replaces.

    They are separately tested against the nested sum, but only on inputs small
    enough for the nested sum to run. This compares them to each other on inputs
    where it cannot, which is where the fast path actually gets used.
    """
    from chisurf.core.fluorescence.pda3c import (
        burst_log_likelihood,
        log_background_correction,
        log_multinomial_pmf,
    )

    rng = np.random.default_rng(19)
    counts = rng.integers(0, 30, size=(40, 3))
    p = rng.dirichlet(np.ones(3), size=6)
    background = np.array([0.9, 0.7, 1.1])

    fast = burst_log_likelihood(counts, p, background)
    for i in range(p.shape[0]):
        for j in range(counts.shape[0]):
            slow = log_multinomial_pmf(counts[j], p[i]) + log_background_correction(
                counts[j], background, p[i]
            )
            assert fast[i, j] == pytest.approx(slow, rel=1e-9)


def test_chunking_does_not_change_the_result(monkeypatch):
    """Peak memory is bounded by chunking bursts; the answer must not notice."""
    from chisurf.core.fluorescence.pda3c import likelihood as lk

    rng = np.random.default_rng(23)
    counts = rng.integers(0, 20, size=(37, 3))
    p = rng.dirichlet(np.ones(3), size=4)
    background = np.array([0.5, 0.5, 0.5])

    whole = lk.burst_log_likelihood(counts, p, background)
    monkeypatch.setattr(lk, "_KERNEL_ELEMENT_BUDGET", 32)
    chunked = lk.burst_log_likelihood(counts, p, background)
    assert np.allclose(whole, chunked)


def test_background_series_starts_at_one():
    from chisurf.core.fluorescence.pda3c import background_series

    u = background_series(count=5, rate=0.7, p=0.4)
    assert u[0] == pytest.approx(1.0)
    assert u.size <= 6  # never more terms than photons


def test_truncation_tolerance_does_not_move_the_answer():
    """Tightening the cutoff must not move a well-fitting burst's likelihood."""
    from chisurf.core.fluorescence.pda3c import burst_log_likelihood

    counts = np.array([[9, 6, 4]])
    p = np.array([[0.5, 0.3, 0.2]])
    background = np.array([1.0, 0.8, 0.6])
    tight = burst_log_likelihood(counts, p, background, tolerance=1e-15)
    loose = burst_log_likelihood(counts, p, background, tolerance=1e-8)
    assert tight == pytest.approx(loose, rel=1e-7)


def test_truncation_survives_a_channel_the_model_says_is_nearly_impossible():
    """Regression: the cutoff cannot be taken on Poisson tail mass alone.

    A channel with ``p = 0.009`` that collected 27 photons is absurd as signal,
    so the likelihood there is carried entirely by the background explanation —
    and those terms *grow* by ~2000x per step before the Poisson factor turns
    them over. Truncating on ``Pois(b; B)`` alone throws the dominant terms away
    and shifted this burst's log-likelihood by 3. The cutoff now uses an
    effective rate ``B * F/(N p)``, which is ~1 near the optimum and large
    exactly here.

    It matters even though the absolute likelihood is tiny: MCMC and
    support-plane scans read the *shape* of the surface away from the optimum.
    """
    from chisurf.core.fluorescence.pda3c import (
        burst_log_likelihood,
        log_background_correction,
        log_multinomial_pmf,
    )

    counts = np.array([[12, 27, 5]])
    p = np.array([[0.35262815, 0.00895504, 0.63841681]])
    background = np.array([0.9, 0.7, 1.1])

    fast = burst_log_likelihood(counts, p, background)[0, 0]
    exact = log_multinomial_pmf(counts[0], p[0]) + log_background_correction(
        counts[0], background, p[0]
    )
    assert fast == pytest.approx(exact, rel=1e-9)


# ── normalisation ──────────────────────────────────────────────────────────


def test_the_likelihood_is_a_normalised_distribution_over_counts():
    """With P(n) supplied, summing over every count vector must give one.

    This is the check that the background convolution is a *probability*
    statement and not merely an algebraic identity — a sign or an off-by-one in
    the falling factorials would still pass the reference comparison (both
    implementations share the definition) but would break normalisation.
    """
    from chisurf.core.fluorescence.pda3c import burst_log_likelihood

    n_max = 14
    n = np.arange(n_max + 1)
    pn = stats.poisson.pmf(n, mu=4.0)
    pn /= pn.sum()

    p = np.array([[0.55, 0.25, 0.20]])
    background = np.array([0.4, 0.3, 0.2])

    total = 0.0
    grid = range(n_max + 6)  # counts may exceed n_max via background
    for f0 in grid:
        for f1 in grid:
            for f2 in grid:
                ll = burst_log_likelihood(np.array([[f0, f1, f2]]), p, background, pn)[0, 0]
                if np.isfinite(ll):
                    total += float(np.exp(ll))
    assert total == pytest.approx(1.0, abs=2e-3)


# ── burst collapsing ───────────────────────────────────────────────────────


def test_collapsing_bursts_is_exact():
    from chisurf.core.fluorescence.pda3c import burst_log_likelihood, collapse_bursts

    rng = np.random.default_rng(7)
    counts = rng.integers(0, 5, size=(400, 3))
    p = np.array([[0.5, 0.3, 0.2], [0.3, 0.3, 0.4]])
    background = np.array([0.3, 0.3, 0.3])

    full = burst_log_likelihood(counts, p, background).sum(axis=1)
    unique, multiplicity = collapse_bursts(counts)
    collapsed = (burst_log_likelihood(unique, p, background) * multiplicity).sum(axis=1)

    assert unique.shape[0] < counts.shape[0], "no duplicates to collapse in this fixture"
    assert np.allclose(full, collapsed)


def test_collapsing_actually_saturates():
    """The saving is the point: distinct vectors grow far slower than bursts."""
    from chisurf.core.fluorescence.pda3c import collapse_bursts

    rng = np.random.default_rng(11)
    small = collapse_bursts(rng.integers(0, 6, size=(500, 3)))[0].shape[0]
    large = collapse_bursts(rng.integers(0, 6, size=(50_000, 3)))[0].shape[0]
    assert large <= 6 ** 3
    assert large / 50_000 < small / 500


# ── the two-colour reduction ───────────────────────────────────────────────


def test_two_channel_case_reproduces_the_pda_engine_s1s2():
    """PRD-65 stage-1 acceptance: with one channel dropped, agree with tttrlib.

    The strongest available check on a brand-new forward model is an
    independently validated one. Marginalising this likelihood over the
    photon-number distribution gives the joint count distribution P(F0, F1),
    which is exactly what ``tttrlib.Pda`` builds as its S1S2 matrix — a
    different algorithm (probability convolution over the photon-number axis)
    for the same quantity.
    """
    import tttrlib

    from chisurf.core.fluorescence.pda3c import burst_log_likelihood

    n_max = 12
    n = np.arange(n_max + 1)
    pf = stats.poisson.pmf(n, mu=5.0).astype(float)
    pf /= pf.sum()

    p_green = 0.62
    background = np.array([0.35, 0.25])

    # The count grid needs headroom over the support of pF: background pushes
    # observed totals past n_max, and a grid cut at n_max drops that mass (~3e-3
    # here) from both matrices in ways that do not cancel under renormalisation.
    grid_max = 30

    pda = tttrlib.Pda(
        hist2d_nmax=grid_max,
        hist2d_nmin=0,
        background_ch1=float(background[0]),
        background_ch2=float(background[1]),
        pF=pf,
    )
    pda.set_probability_spectrum_ch1([1.0, p_green])
    engine = np.asarray(pda.s1s2, dtype=float)

    ny, nx = engine.shape
    ours = np.zeros_like(engine)
    for f0 in range(ny):
        for f1 in range(nx):
            ll = burst_log_likelihood(
                np.array([[f0, f1]]),
                np.array([[p_green, 1.0 - p_green]]),
                background,
                photon_number_pmf=pf,
            )[0, 0]
            if np.isfinite(ll):
                ours[f0, f1] = float(np.exp(ll))

    # Both are probability distributions over the same grid; compare where the
    # engine has support, on total variation rather than element-wise ratios
    # (the far tail holds values below double precision's useful range).
    engine_sum = engine.sum()
    assert engine_sum > 0.9, "engine matrix is not normalised as expected"
    total_variation = 0.5 * np.abs(ours / ours.sum() - engine / engine_sum).sum()
    assert total_variation < 1e-6, f"total variation {total_variation:.2e} too large"
