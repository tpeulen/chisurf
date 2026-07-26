"""MCMC convergence diagnostics (PRD-69, phase 1).

The estimators are pinned against an AR(1) process, whose integrated
autocorrelation time ``(1+phi)/(1-phi)`` is known in closed form -- validating
against a reimplementation of the same formula would prove nothing.
"""
import numpy as np
import pytest

from chisurf.core.fitting import diagnostics as dg


def _ar1(phi: float, n: int, n_chains: int = 4, seed: int = 0) -> np.ndarray:
    """Return ``(n_chains, n, 1)`` draws of a stationary AR(1) process.

    The chains start from the stationary distribution, so there is no burn-in
    transient to confuse the autocorrelation estimate.

    Parameters
    ----------
    phi : float
        Lag-1 autocorrelation; the true autocorrelation time is
        ``(1+phi)/(1-phi)``.
    n : int
        Draws per chain.
    n_chains : int, optional
        Number of independent chains.
    seed : int, optional
        Seed of the random-number generator.

    Returns
    -------
    numpy.ndarray
        The chains, shaped for :mod:`chisurf.core.fitting.diagnostics`.
    """
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(1.0 - phi * phi)
    out = np.empty((n_chains, n))
    for c in range(n_chains):
        x = rng.normal(0.0, 1.0)
        for i in range(n):
            x = phi * x + sigma * rng.normal()
            out[c, i] = x
    return out[:, :, np.newaxis]


def test_as_chains_normalises_every_accepted_shape():
    """1-D, 2-D and 3-D inputs must all reach ``(chains, draws, parameters)``."""
    assert dg.as_chains(np.zeros(7)).shape == (1, 7, 1)
    assert dg.as_chains(np.zeros((7, 3))).shape == (1, 7, 3)
    assert dg.as_chains(np.zeros((2, 7, 3))).shape == (2, 7, 3)
    with pytest.raises(ValueError):
        dg.as_chains(np.zeros((2, 2, 2, 2)))


def test_autocovariance_matches_the_direct_sum():
    """The FFT shortcut must agree with the O(n^2) definition."""
    rng = np.random.default_rng(3)
    x = rng.normal(size=64)
    got = dg.autocovariance(x)
    centred = x - x.mean()
    want = np.array([
        float((centred[:len(x) - k] * centred[k:]).sum() / len(x))
        for k in range(len(x))
    ])
    assert np.allclose(got, want, atol=1e-12)


@pytest.mark.parametrize("phi", [0.0, 0.5, 0.8])
def test_autocorrelation_time_recovers_the_ar1_value(phi):
    """Tau must approach the analytic ``(1+phi)/(1-phi)``."""
    chains = _ar1(phi, n=20000, n_chains=4, seed=1)
    expected = (1.0 + phi) / (1.0 - phi)
    got = float(dg.autocorrelation_time(chains)[0])
    assert got == pytest.approx(expected, rel=0.15)


def test_effective_sample_size_is_the_draw_count_for_white_noise():
    """An uncorrelated chain must have ESS close to its number of draws."""
    chains = _ar1(0.0, n=8000, n_chains=4, seed=2)
    ess = float(dg.effective_sample_size(chains)[0])
    assert ess == pytest.approx(32000, rel=0.15)


def test_effective_sample_size_falls_with_correlation():
    """A correlated chain must carry fewer independent samples."""
    white = float(dg.effective_sample_size(_ar1(0.0, 8000, 4, 4))[0])
    correlated = float(dg.effective_sample_size(_ar1(0.9, 8000, 4, 4))[0])
    assert correlated < white / 5.0
    # ESS can never exceed the number of draws actually taken.
    assert white <= 32000 + 1


def test_split_rhat_is_one_for_well_mixed_chains():
    """Chains from the same distribution must agree."""
    chains = _ar1(0.5, n=6000, n_chains=4, seed=5)
    rhat = float(dg.split_rhat(chains)[0])
    assert 0.99 < rhat < 1.01


def test_split_rhat_detects_chains_stuck_in_different_places():
    """Offset chains are the textbook non-convergence R-hat must catch."""
    chains = _ar1(0.5, n=2000, n_chains=4, seed=6)
    chains = chains.copy()
    chains[0] += 10.0
    chains[1] += 5.0
    assert float(dg.split_rhat(chains)[0]) > 1.5


def test_split_rhat_detects_drift_within_a_single_chain():
    """Splitting is what lets one drifting chain be caught on its own."""
    n = 4000
    drift = np.linspace(0.0, 20.0, n)
    chains = _ar1(0.3, n=n, n_chains=1, seed=7)
    chains = chains + drift[np.newaxis, :, np.newaxis]
    assert float(dg.split_rhat(chains)[0]) > 1.5


def test_a_frozen_chain_is_reported_as_a_failure_not_as_perfect():
    """Constant chains that disagree are the worst case, not R-hat 1."""
    stuck = np.zeros((2, 100, 1))
    stuck[1] = 1.0
    assert not np.isfinite(dg.split_rhat(stuck)[0])
    # Identical constant chains are degenerate but consistent.
    same = np.zeros((2, 100, 1))
    assert float(dg.split_rhat(same)[0]) == 1.0


def test_mcse_shrinks_as_the_square_root_of_the_sample():
    """Four times the draws must roughly halve the Monte-Carlo error."""
    short = float(dg.mcse(_ar1(0.5, 2000, 4, 8))[0])
    long_ = float(dg.mcse(_ar1(0.5, 8000, 4, 8))[0])
    assert long_ == pytest.approx(short / 2.0, rel=0.35)


def test_suggest_burn_in_scales_with_the_autocorrelation_time():
    """A stickier chain needs to discard more of its start."""
    fast = dg.suggest_burn_in(_ar1(0.1, 4000, 4, 9))
    slow = dg.suggest_burn_in(_ar1(0.95, 4000, 4, 9))
    assert slow > fast
    assert slow <= 2000  # never more than half the chain


def test_summarize_reports_the_ar1_moments_and_diagnostics():
    """The summary must recover a known mean/sd and carry the diagnostics."""
    chains = _ar1(0.5, n=8000, n_chains=4, seed=10) * 2.0 + 3.0
    summary = dg.summarize(chains, names=['x'])
    assert len(summary) == 1
    e = summary[0]
    assert e['name'] == 'x'
    assert e['mean'] == pytest.approx(3.0, abs=0.1)
    assert e['sd'] == pytest.approx(2.0, rel=0.1)
    assert e['quantiles']['0.5'] == pytest.approx(3.0, abs=0.15)
    assert e['ess'] > 1000
    assert 0.99 < e['rhat'] < 1.01
    assert e['burn_in'] >= 0
    assert e['n_chains'] == 4


def test_summarize_names_extra_parameters_rather_than_dropping_them():
    """A short name list must not silently truncate the summary."""
    chains = np.random.default_rng(0).normal(size=(2, 500, 3))
    summary = dg.summarize(chains, names=['a'])
    assert [e['name'] for e in summary] == ['a', 'p1', 'p2']


def test_convergence_warnings_are_silent_on_a_good_chain():
    """A well-mixed, long chain must produce no complaints."""
    chains = _ar1(0.5, n=8000, n_chains=4, seed=11)
    assert dg.convergence_warnings(dg.summarize(chains)) == []


def test_convergence_warnings_name_the_offending_parameter():
    """A failure must be actionable, not just a boolean."""
    chains = _ar1(0.5, n=1000, n_chains=4, seed=12)
    chains = chains.copy()
    chains[0] += 10.0
    messages = dg.convergence_warnings(dg.summarize(chains, names=['tau1']))
    assert messages
    assert any('tau1' in m for m in messages)
    assert any('R-hat' in m for m in messages)


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf])
def test_a_non_finite_draw_leaves_the_sample_size_undefined_not_maximal(bad):
    """One bad draw must not read as ``n`` perfectly independent samples.

    A single ``nan``/``inf`` contaminates the FFT autocovariance, which used to
    fall through the constant-parameter branch and report the *raw* draw count
    beside a ``nan`` R-hat -- the best possible verdict next to a refusal.
    """
    chains = _ar1(0.5, n=1000, n_chains=4, seed=13)
    chains = chains.copy()
    chains[2, 17, 0] = bad
    assert np.isnan(dg.effective_sample_size(chains)[0])
    assert np.isnan(dg.autocorrelation_time(chains)[0])
    assert np.isnan(dg.mcse(chains)[0])
    e = dg.summarize(chains, names=['x'], burn_in=0)[0]
    assert np.isnan(e['ess']) and np.isnan(e['tau']) and np.isnan(e['mcse'])
    # The clean chain is untouched: a finite ESS is still reported.
    assert dg.effective_sample_size(_ar1(0.5, n=1000, n_chains=4, seed=13))[0] > 0.0


@pytest.mark.parametrize('value', [0.0, 1.0, 0.5, 2.5, 1.234, 0.001, 3.7])
def test_a_frozen_parameter_gets_one_verdict_whatever_its_value(value):
    """A bit-identical chain must not be graded by floating-point luck.

    The constant-parameter guard used to test the pooled *variance*, which the
    FFT autocovariance returns as a ~1e-31 rounding residual rather than an
    exact zero. Whether the residual happened to cancel decided between the
    best possible verdict (``ess`` = every draw, no warning at all) and the
    worst (``ess`` = one per chain) for chains that never moved at all.
    """
    chains = np.full((4, 2000, 1), value)
    assert np.isnan(dg.effective_sample_size(chains)[0])
    assert np.isnan(dg.autocorrelation_time(chains)[0])
    assert np.isnan(dg.mcse(chains)[0])

    e = dg.summarize(chains, names=['tau1'], burn_in=0)[0]
    assert e['frozen'] is True
    assert np.isnan(e['ess']) and np.isnan(e['tau']) and np.isnan(e['mcse'])
    assert np.isnan(e['ess_bulk']) and np.isnan(e['ess_tail'])

    # And it is said out loud: R-hat is 1.0 here, so nothing else would.
    messages = dg.convergence_warnings([e])
    assert any('never moved' in m and 'tau1' in m for m in messages)


def test_a_moving_parameter_is_not_reported_as_frozen():
    """The frozen verdict must not leak onto an ordinary, well-mixed chain."""
    e = dg.summarize(_ar1(0.5, n=2000, n_chains=4, seed=7), names=['x'])[0]
    assert e['frozen'] is False
    assert np.isfinite(e['ess']) and e['ess'] > 0.0
    assert dg.convergence_warnings([e]) == []


def test_short_chains_degrade_instead_of_raising():
    """Two draws are not enough to diagnose anything, and must not crash."""
    tiny = np.zeros((1, 2, 2))
    assert np.all(np.isnan(dg.split_rhat(tiny)))
    assert dg.suggest_burn_in(tiny) == 0
    assert len(dg.summarize(tiny, names=['a', 'b'])) == 2


# -- rank-normalised statistics (Vehtari et al. 2021, as Stan computes them) --

def test_rank_normalisation_produces_normal_scores():
    """The transform must map any distribution onto standard normal scores."""
    rng = np.random.default_rng(0)
    heavy = rng.standard_cauchy(size=(4, 2000))       # no finite variance
    z = dg.rank_normalize(heavy)
    assert z.shape == heavy.shape
    assert np.all(np.isfinite(z))
    # Pooled scores are standard normal by construction.
    assert float(z.mean()) == pytest.approx(0.0, abs=0.02)
    assert float(z.std()) == pytest.approx(1.0, rel=0.05)
    # Order is preserved: it is a monotone transform.
    order_before = np.argsort(heavy.ravel())
    assert np.all(np.diff(z.ravel()[order_before]) >= -1e-12)


def test_ties_share_their_average_rank():
    """Otherwise the transform depends on the order the draws arrived in."""
    x = np.array([[1.0, 2.0, 2.0, 3.0]])
    z = dg.rank_normalize(x)
    assert z[0, 1] == pytest.approx(z[0, 2])
    assert z[0, 0] < z[0, 1] < z[0, 3]


def test_rank_normalised_rhat_survives_an_infinite_variance_target():
    """The plain statistic is undefined on a Cauchy; the rank one is not."""
    rng = np.random.default_rng(1)
    chains = rng.standard_cauchy(size=(4, 4000))[:, :, np.newaxis]
    robust = dg.rank_normalized_rhat(chains)[0]
    assert np.isfinite(robust)
    # Four chains from the same Cauchy have converged, and it says so.
    assert robust < 1.05


def test_the_folded_statistic_catches_a_difference_in_spread():
    """Two chains with the same centre and different width.

    A location-based R-hat compares means, and these agree perfectly -- so the
    plain statistic sees nothing wrong. Folding about the median is what makes
    the difference in scale visible.
    """
    rng = np.random.default_rng(2)
    narrow = rng.normal(0.0, 1.0, size=(2, 4000))
    wide = rng.normal(0.0, 4.0, size=(2, 4000))
    chains = np.concatenate([narrow, wide], axis=0)[:, :, np.newaxis]

    plain = dg.split_rhat(chains)[0]
    robust = dg.rank_normalized_rhat(chains)[0]
    assert plain < 1.02, "the location statistic is expected to miss this"
    assert robust > 1.05, "the folded statistic must catch it"


def test_tail_ess_is_reported_separately_from_bulk():
    """The quantiles a credible interval is made of are governed by the tail."""
    chains = _ar1(0.5, n=4000, n_chains=4, seed=4)
    bulk, tail = dg.bulk_tail_ess(chains)
    assert np.all(np.isfinite(bulk)) and np.all(np.isfinite(tail))
    assert bulk[0] > 1000 and tail[0] > 100

    # ``summarize`` discards a burn-in first, so compare on the same draws.
    summary = dg.summarize(chains, names=['x'], burn_in=0)[0]
    assert summary['ess_bulk'] == pytest.approx(bulk[0])
    assert summary['ess_tail'] == pytest.approx(tail[0])
    # Both the robust and the plain R-hat are reported, so a disagreement is
    # visible rather than silently resolved.
    assert 'rhat_plain' in summary


def test_a_poor_tail_is_reported_even_when_the_bulk_is_fine():
    """A chain can be trustworthy about its mean and not about its interval."""
    rng = np.random.default_rng(4)
    # Bulk mixes well; the tails are visited in long, rare excursions.
    base = rng.normal(size=(4, 4000))
    spikes = np.zeros_like(base)
    for c in range(4):
        start = rng.integers(0, 3500)
        spikes[c, start:start + 400] = 8.0
    chains = (base + spikes)[:, :, np.newaxis]

    bulk, tail = dg.bulk_tail_ess(chains)
    assert tail[0] < bulk[0]
    messages = dg.convergence_warnings(dg.summarize(chains, names=['x']))
    assert any('tail' in m for m in messages)


def test_the_warnings_name_which_effective_sample_size_failed():
    """"ESS is low" is not actionable; which one it is, is."""
    chains = _ar1(0.99, n=600, n_chains=2, seed=5)
    messages = dg.convergence_warnings(dg.summarize(chains, names=['tau1']))
    assert messages
    assert any('bulk' in m or 'tail' in m for m in messages)
    assert any('tau1' in m for m in messages)


# -- rank plots and ESS growth (the display-side diagnostics) -------------

def _ar1_chains(rho, n_chains=8, n_draws=1200, seed=0, shift=0.0):
    """Return AR(1) chains with a known autocorrelation time."""
    rng = np.random.default_rng(seed)
    out = np.zeros((n_chains, n_draws, 1))
    for c in range(n_chains):
        v = 0.0
        for t in range(n_draws):
            v = rho * v + rng.normal(0.0, 1.0)
            out[c, t, 0] = v
    out[0] += shift
    return out


def test_rank_histograms_are_flat_when_the_chains_agree():
    """Every chain holds an equal share of the pooled ranks, by construction."""
    rng = np.random.default_rng(0)
    chains = rng.normal(size=(4, 2000, 2))
    counts, edges, expected = dg.rank_histogram(chains, bins=20)

    assert counts.shape == (2, 4, 20)
    assert edges.shape == (21,)
    assert expected == pytest.approx(2000 / 20)
    # Each chain's draws are all accounted for, in every parameter.
    assert np.allclose(counts.sum(axis=2), 2000)
    # And the pooled total per bin is the same for every bin.
    assert np.allclose(counts.sum(axis=1), 4 * expected, rtol=0.0, atol=1e-9)


def test_a_chain_sampling_elsewhere_shows_as_structure():
    """The failure a rank plot exists to make visible."""
    rng = np.random.default_rng(1)
    chains = rng.normal(size=(4, 2000, 1))
    chains[0] += 1.5
    counts, _, expected = dg.rank_histogram(chains, bins=20)
    off = counts[0, 0]
    # The shifted chain holds far too few low ranks and far too many high ones.
    assert off[0] < 0.5 * expected
    assert off[-1] > 1.5 * expected


def test_ties_are_shared_rather_than_given_to_whichever_sorted_first():
    """A parameter pinned at a bound must not fake a perfect split."""
    chains = np.zeros((2, 100, 1))
    counts, _, expected = dg.rank_histogram(chains, bins=10)
    # Every draw identical: the average rank is the same for all, so each chain
    # lands wholly in one bin -- but the *same* bin, not different ones.
    assert counts[0].sum() == 200
    occupied = np.nonzero(counts[0].sum(axis=0))[0]
    assert occupied.size == 1


def test_the_uniformity_threshold_is_calibrated_not_a_fixed_percentage():
    """A converged run must read as flat whatever its shape.

    A fixed percentage cannot do this: the more cells a histogram has, the
    further from flat its worst one is by chance alone. Every one of these is
    converged, and every one must say so.
    """
    for n_chains, n_draws in ((4, 2000), (8, 750), (20, 300)):
        rng = np.random.default_rng(n_chains)
        chains = rng.normal(size=(n_chains, n_draws, 1))
        counts, _, _ = dg.rank_histogram(chains, bins=20)
        z, z_null = dg.rank_uniformity(counts[0], n_draws, 20)
        assert z < 1.5 * z_null, (n_chains, n_draws, z, z_null)


def test_autocorrelation_is_accounted_for_in_the_noise_level():
    """Otherwise a converged but slow chain reports its own memory as structure."""
    chains = _ar1_chains(rho=0.9, seed=2)
    counts, _, _ = dg.rank_histogram(chains, bins=20)
    tau = float(dg.within_chain_tau(chains)[0])
    assert tau > 5.0, "AR(1) at rho=0.9 is strongly autocorrelated"

    naive, z_null = dg.rank_uniformity(counts[0], chains.shape[1], 20)
    corrected, _ = dg.rank_uniformity(counts[0], chains.shape[1], 20, tau=tau)
    assert corrected < naive
    assert corrected < 1.5 * z_null, "a converged chain must not be flagged"


def test_the_correction_does_not_hide_a_split_run():
    """The trap: correcting by the *pooled* ESS would explain the fault away.

    A run whose chains disagree has a terrible pooled effective sample size --
    precisely *because* they disagree. Inflating the noise level by that would
    let every badly split run excuse itself. The within-chain autocorrelation is
    unaffected by where the other chains sat, so it does not.
    """
    chains = _ar1_chains(rho=0.9, seed=3, shift=6.0)
    counts, _, _ = dg.rank_histogram(chains, bins=20)
    tau = float(dg.within_chain_tau(chains)[0])
    z, z_null = dg.rank_uniformity(counts[0], chains.shape[1], 20, tau=tau)
    assert z > 2.5 * z_null, (z, z_null)

    # And the pooled figure really would have hidden it.
    pooled_tau = chains.shape[1] / max(
        float(dg.effective_sample_size(chains)[0]) / chains.shape[0], 1e-9)
    hidden, _ = dg.rank_uniformity(
        counts[0], chains.shape[1], 20, tau=pooled_tau)
    assert hidden < z


def test_effective_sample_size_grows_linearly_when_it_should():
    """The signature of a healthy chain, and the reason to plot the curve."""
    rng = np.random.default_rng(4)
    chains = rng.normal(size=(4, 2000, 1))
    draws, ess = dg.ess_evolution(chains, points=8)
    assert draws.size >= 4
    assert ess.shape == (draws.size, 1)
    # Efficiency stays roughly constant instead of decaying.
    efficiency = ess[:, 0] / (draws * chains.shape[0])
    assert efficiency.min() > 0.5 * efficiency.max()
    assert np.all(np.diff(ess[:, 0]) > -0.2 * ess[0, 0]), "must not fall away"


def test_effective_sample_size_flattens_for_a_stuck_chain():
    """And the failure the curve shows that a single final number does not."""
    # A random walk never forgets where it started: more draws buy almost
    # nothing, which shows as a curve that bends over.
    rng = np.random.default_rng(5)
    walk = np.cumsum(rng.normal(size=(4, 2000, 1)), axis=1)
    draws, ess = dg.ess_evolution(walk, points=8)
    efficiency = ess[:, 0] / (draws * walk.shape[0])
    assert efficiency[-1] < 0.5 * efficiency[0], efficiency


def test_ess_evolution_refuses_a_chain_too_short_to_judge():
    """Below a handful of draws the estimator reports noise, not a number."""
    draws, ess = dg.ess_evolution(np.zeros((2, 4, 1)), points=5)
    assert draws.size == 0 and ess.shape[0] == 0
