"""The in-tree ensemble samplers must reproduce a posterior we know in closed form.

An MCMC sampler cannot be tested by asserting on the numbers it happens to
return: the only meaningful test is that the chain has the distribution it claims
to have. Both samplers are therefore run against Gaussians whose mean, variance
and correlation are known analytically, and the recovered moments are compared
against them.

The bar is set from the Monte-Carlo error of the runs below, not tightened until
it passes: a bound that a correct sampler fails one run in twenty is not a test,
it is a coin toss in the suite. Every run is seeded.
"""
import numpy as np
import pytest

from chisurf.core.fitting.ensemble import (
    AdaptiveCovarianceMove,
    CovarianceMove,
    DifferentialMove,
    EnsembleSampler,
    EnsembleSliceSampler,
    EnsembleState,
    walkers_independent,
)

#: Both samplers are exercised through the same tests wherever the API is shared.
SAMPLERS = [EnsembleSampler, EnsembleSliceSampler]

#: A slice step costs several evaluations and decorrelates far better, so the two
#: samplers are given step counts of comparable *cost* rather than equal counts.
STEPS = {EnsembleSampler: 6000, EnsembleSliceSampler: 800}

MU = np.array([1.0, -2.0, 0.5])
RHO = 0.95
COV = np.array([
    [1.0, RHO, RHO ** 2],
    [RHO, 1.0, RHO],
    [RHO ** 2, RHO, 1.0],
])
PRECISION = np.linalg.inv(COV)


def _log_prob(x):
    """Return the log-density of the correlated reference Gaussian at ``x``."""
    d = np.asarray(x) - MU
    return -0.5 * float(d @ PRECISION @ d)


def _log_prob_vectorized(x):
    """Return the log-density of the reference Gaussian for many positions."""
    d = np.asarray(x) - MU
    return -0.5 * np.einsum("ij,jk,ik->i", d, PRECISION, d)


def _log_prob_with_blobs(x):
    """Return the log-density plus two derived quantities as blobs."""
    return _log_prob(x), float(np.sum(x)), float(x[0])


def _start(nwalkers=16, ndim=3, seed=0):
    """Return an initial ensemble spread around the reference mean."""
    return MU[:ndim] + 0.5 * np.random.default_rng(seed).standard_normal((nwalkers, ndim))


@pytest.mark.parametrize("cls", SAMPLERS)
def test_a_correlated_gaussian_is_recovered(cls):
    """Mean, variance and correlation must all come back, not just the mean.

    A sampler with a too-short move gets the mean right and the width wrong, so
    the width is the assertion that matters.
    """
    sampler = cls(16, 3, _log_prob, seed=3)
    steps = STEPS[cls]
    sampler.run_mcmc(_start(), steps)
    chain = sampler.get_chain(flat=True, discard=steps // 4)

    assert np.allclose(chain.mean(axis=0), MU, atol=0.1)
    assert np.allclose(np.var(chain, axis=0), np.diag(COV), rtol=0.15)
    assert np.corrcoef(chain.T)[0, 1] == pytest.approx(RHO, abs=0.02)


@pytest.mark.parametrize("cls", SAMPLERS)
def test_the_chain_is_reproducible_from_its_seed(cls):
    """A seeded run must be repeatable, or a failure cannot be investigated."""
    start = _start(12, 3, seed=1)
    a = cls(12, 3, _log_prob_vectorized, vectorize=True, seed=7)
    b = cls(12, 3, _log_prob_vectorized, vectorize=True, seed=7)
    a.run_mcmc(start, 40)
    b.run_mcmc(start, 40)
    assert np.array_equal(a.get_chain(), b.get_chain())
    assert np.array_equal(a.get_log_prob(), b.get_log_prob())


@pytest.mark.parametrize("cls", SAMPLERS)
def test_blobs_are_stored_next_to_the_positions_they_belong_to(cls):
    """The blob of a stored state must be the blob *of that state*.

    This is what lets a chain carry the data misfit and the prior separately;
    an off-by-one between chain and blobs would silently mislabel both.
    """
    sampler = cls(12, 3, _log_prob_with_blobs, seed=2)
    sampler.run_mcmc(_start(12, 3, seed=2), 30)
    chain = sampler.get_chain(flat=True)
    blobs = sampler.get_blobs(flat=True)

    assert blobs.shape == (len(chain), 2)
    assert np.allclose(blobs[:, 0], chain.sum(axis=1))
    assert np.allclose(blobs[:, 1], chain[:, 0])


@pytest.mark.parametrize("cls", SAMPLERS)
def test_a_run_can_be_continued_from_the_state_it_returned(cls):
    """Chunked sampling is how progress and cancellation work, so it must append."""
    sampler = cls(12, 3, _log_prob_with_blobs, seed=4)
    state = sampler.run_mcmc(_start(12, 3, seed=4), 20)
    assert isinstance(state, EnsembleState)
    sampler.run_mcmc(state, 20)

    assert sampler.iteration == 40
    assert sampler.get_chain().shape == (40, 12, 3)
    assert sampler.get_blobs().shape == (40, 12, 2)
    # ``run_mcmc(None, ...)`` resumes where the sampler left off.
    sampler.run_mcmc(None, 5)
    assert sampler.iteration == 45


@pytest.mark.parametrize("cls", SAMPLERS)
def test_thinning_stores_every_nth_step_and_takes_the_rest(cls):
    """``thin_by`` counts stored states, not steps -- the accounting that bit before."""
    sampler = cls(12, 3, _log_prob, seed=5)
    sampler.run_mcmc(_start(12, 3, seed=5), 10, thin_by=4)
    assert sampler.iteration == 10
    assert sampler.get_chain().shape == (10, 12, 3)


@pytest.mark.parametrize("cls", SAMPLERS)
def test_a_forbidden_region_is_never_entered(cls):
    """A ``-inf`` log-probability is a hard wall, not a steep hill."""
    limit = 2.0

    def log_prob(x):
        return -np.inf if np.any(np.abs(x) > limit) else 0.0

    sampler = cls(12, 3, log_prob, seed=6)
    start = np.random.default_rng(6).uniform(-1.0, 1.0, (12, 3))
    sampler.run_mcmc(start, 200 if cls is EnsembleSampler else 60)
    assert np.max(np.abs(sampler.get_chain(flat=True))) <= limit


@pytest.mark.parametrize("cls", SAMPLERS)
def test_walkers_that_span_nothing_are_refused(cls):
    """Identical walkers cannot explore anything; that must fail loudly."""
    sampler = cls(12, 3, _log_prob, seed=8)
    degenerate = np.tile(MU, (12, 1))
    assert not walkers_independent(degenerate)
    with pytest.raises(ValueError, match="condition number"):
        sampler.run_mcmc(degenerate, 5)
    # ...unless the caller insists, which a resumed chunk legitimately does.
    sampler.run_mcmc(degenerate, 2, skip_initial_state_check=True)
    assert sampler.iteration == 2


def test_the_stretch_move_needs_enough_walkers_to_span_the_space():
    """Fewer than ``2 * ndim`` walkers trap the ensemble in a subspace."""
    with pytest.raises(ValueError, match="cannot span"):
        EnsembleSampler(6, 5, _log_prob)
    # The requirement can be waived deliberately.
    EnsembleSampler(6, 5, _log_prob, live_dangerously=True)


def test_the_stretch_acceptance_fraction_is_in_a_usable_range():
    """A sampler accepting almost nothing or almost everything is misconfigured."""
    sampler = EnsembleSampler(16, 3, _log_prob, seed=9)
    sampler.run_mcmc(_start(), 500)
    acceptance = float(np.mean(sampler.acceptance_fraction))
    assert 0.15 < acceptance < 0.9
    # One evaluation per walker per step, plus the initial state.
    assert sampler.n_evaluations == 16 * (500 + 1)


@pytest.mark.parametrize(
    "move", [DifferentialMove(), CovarianceMove(), AdaptiveCovarianceMove()]
)
def test_every_slice_direction_proposal_samples_the_same_posterior(move):
    """The direction may be chosen freely; the invariant distribution may not change."""
    sampler = EnsembleSliceSampler(16, 3, _log_prob, moves=move, seed=10)
    sampler.run_mcmc(_start(), 600)
    chain = sampler.get_chain(flat=True, discard=150)
    assert np.allclose(chain.mean(axis=0), MU, atol=0.15)
    assert np.allclose(np.var(chain, axis=0), np.diag(COV), rtol=0.2)


def test_the_slice_sampler_moves_every_walker_and_tunes_its_scale():
    """Slice sampling has no rejection, and its length scale is learnt, not set."""
    sampler = EnsembleSliceSampler(16, 3, _log_prob, seed=12)
    sampler.run_mcmc(_start(), 300)
    assert np.all(sampler.acceptance_fraction > 0.99)
    assert sampler.mu != 1.0
    # Tuning is finite: it must stop by itself, or the chain never becomes valid.
    assert not sampler.tuning
    # Each step costs more than one evaluation per walker -- that is the trade.
    assert sampler.n_evaluations > 300 * 16


def test_the_slice_sampler_is_not_slower_per_evaluation_than_the_stretch_move():
    """Its extra evaluations must buy a longer move, or it is not worth having.

    Cost is counted in log-probability evaluations, the only currency in which
    the two are comparable.
    """
    from chisurf.core.fitting import diagnostics as dg

    def ess_per_eval(cls, steps):
        sampler = cls(16, 3, _log_prob, seed=13)
        sampler.run_mcmc(_start(), steps)
        chains = sampler.get_chain().transpose(1, 0, 2)
        burn = chains.shape[1] // 4
        ess = dg.effective_sample_size(chains[:, burn:, :])
        return float(np.min(ess)) / sampler.n_evaluations

    stretch = ess_per_eval(EnsembleSampler, 4000)
    slice_ = ess_per_eval(EnsembleSliceSampler, 500)
    # Measured at ~1.5x the stretch move on this rho=0.95 posterior. The claim
    # under test is only that the extra evaluations are not wasted, so the bound
    # is the break-even point rather than the measured value.
    assert slice_ > stretch


def test_a_pool_and_the_serial_path_agree():
    """The ``map``-based parallel path must not change the chain it produces."""
    class SerialPool:
        """Minimal stand-in with the ``map`` interface a real pool provides."""

        def map(self, fn, iterable):
            """Apply ``fn`` to every element, like ``multiprocessing.Pool.map``."""
            return [fn(x) for x in iterable]

    start = _start(12, 3, seed=14)
    a = EnsembleSampler(12, 3, _log_prob, seed=15)
    b = EnsembleSampler(12, 3, _log_prob, pool=SerialPool(), seed=15)
    a.run_mcmc(start, 30)
    b.run_mcmc(start, 30)
    assert np.array_equal(a.get_chain(), b.get_chain())


def test_the_walker_spread_is_never_zero_in_any_direction():
    """A dimension with no spread is a dimension the ensemble cannot sample.

    The moves are built from differences between walkers, so a parameter whose
    walkers all start at the same value stays there for the whole run and is
    reported as a delta-function posterior. Relative scales produce exactly
    that whenever the value they are relative to is zero.
    """
    # ``sample`` decorates at import time with a helper from ``factorgraph``,
    # which ``fit`` is what pulls in -- importing it alone raises.
    import chisurf.core.fitting.fit  # noqa: F401
    import chisurf.core.fitting.sample as sample

    class _Model:
        """Model whose parameters would all get a zero relative spread."""

        # value 0 (no relative scale), and bounds that coincide (no range).
        parameter_values = [0.0, 5.0, 0.0]
        parameter_bounds = [(None, None), (5.0, 5.0), (0.0, 0.0)]

    start = sample._ensemble_walker_start(
        _Model(), nwalkers=12, std=1e-3, random=np.random.default_rng(0)
    )
    spread = start.std(axis=0)
    # The bounded-but-pinned parameters cannot move off their bound, but the
    # unbounded one must have room.
    assert spread[0] > 0.0
    assert np.all(np.isfinite(start))
