"""Parameter-space sampling backends (Metropolis and ensemble MCMC)."""
from __future__ import annotations

import math
import typing

import numpy as np

import chisurf as cs
import chisurf.core.fitting
import chisurf.core.fitting.ensemble

#: Relative forward-difference step for the conditional Jacobian of a local fit.
#: The square root of the machine epsilon balances truncation against
#: cancellation error, as in :data:`chisurf.core.fitting.fit.FINITE_DIFFERENCE_STEP`.
FINITE_DIFF = float(np.sqrt(np.finfo(float).eps))


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def walk_mcmc(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        step_size: float,
        temp: float = 1.0,
        thin: int = 1,
        chi2max: float = np.inf,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        n_adapt: int = None,
        target_acceptance: float = 0.3,
        model: cs.core.models.Model = None
) -> dict:
    """Sample the free parameters of a fit with a Metropolis random walk.

    The chain targets the posterior ``exp(lnprob / temp)``, where
    :func:`chisurf.core.fitting.fit.lnprob` returns the log-posterior
    (``-chi2/2`` plus a flat prior inside ``bounds``).

    Proposals are Gaussian. Their widths start out at ``step_size`` relative to
    each parameter's initial value and are then tuned during a warm-up phase
    (see Notes), because a width that is right for a loosely constrained
    parameter can be orders of magnitude too wide for a well determined one.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose free parameters are sampled.
    steps : int
        Number of Markov-chain steps to take. ``steps // thin`` states are
        returned. Warm-up steps are additional to this.
    step_size : float
        Initial width of the Gaussian proposal, relative to the parameter value.
    temp : float, optional
        Sampling temperature. Values above one flatten the posterior.
    thin : int, optional
        Record the chain state only every ``thin`` steps.
    chi2max : float, optional
        Hard cutoff on chi²; proposals above it are always rejected.
    callback : callable, optional
        Called as ``callback(n_recorded, n_samples)`` after each recorded state.
    check_cancel : callable, optional
        Polled once per step; sampling stops early when it returns ``True``.
    n_adapt : int, optional
        Number of warm-up steps used to tune the proposal widths. Defaults to
        half the chain length (bounded to ``[200, 2000]``); pass ``0`` to sample
        with the proposal widths implied by ``step_size`` alone.
    target_acceptance : float, optional
        Acceptance rate the warm-up aims for.
    model : chisurf.core.models.Model, optional
        Model to sample; defaults to ``fit.model``, which for a
        :class:`~chisurf.core.fitting.fit.FitGroup` is the *selected member's*
        model. Pass
        :func:`chisurf.core.fitting.factorgraph.posterior_model` for the joint
        posterior of a group.

    Returns
    -------
    dict
        ``chi2r`` (the *data* misfit, priors excluded), ``lnprior``,
        ``parameter_values``, ``parameter_names`` and the ``acceptance_rate``
        of the recorded chain.

    Notes
    -----
    Rejected proposals re-record the *current* state rather than being skipped,
    as required for the chain to converge to the target distribution.

    Adaptation runs entirely within the warm-up: the widths are re-derived once
    from the spread of the warm-up states and continuously rescaled by a
    Robbins-Monro recursion towards ``target_acceptance``. They are then frozen,
    so the recorded chain is a plain (time-homogeneous) Markov chain whose
    stationary distribution is the posterior -- adapting while recording would
    break that guarantee.
    """
    if model is None:
        model = fit.model
    dim = model.n_free
    state_initial = np.asarray(model.parameter_values, dtype=np.float64)
    thin = max(1, int(thin))
    n_samples = max(1, int(steps) // thin)
    # initialize arrays. The data misfit and the prior are recorded apart so the
    # reported chi2 stays a pure goodness-of-fit number even with informative
    # priors in play (and so the chain can be reweighted under another prior).
    lnprior = np.empty(n_samples)
    chi2 = np.empty(n_samples)
    parameter = np.empty((n_samples, dim))
    n_recorded = 0
    n_accepted = 0
    state_prev = np.copy(state_initial)
    bounds = model.parameter_bounds

    # Proposal width is relative to the starting value; parameters that start
    # at (numerically) zero would never move, so fall back to an absolute step.
    proposal_scale = np.abs(state_initial) * step_size
    proposal_scale[proposal_scale < 1e-15] = step_size

    def _lnprob(state):
        """Return ``(lnpost, lnprior, chi2)`` of a parameter vector."""
        lnlike, lnpr, c2 = cs.core.fitting.fit.lnprob_parts(
            parameter_values=state,
            fit=fit,
            chi2max=chi2max,
            bounds=bounds,
            model=model
        )
        return lnlike + lnpr, lnpr, c2

    def _metropolis_step(state, parts, width):
        """Take one Metropolis step.

        Returns the (possibly unchanged) state, its ``(lnpost, lnprior, chi2)``
        parts, whether the proposal was accepted, and the acceptance probability
        of the proposal.
        """
        proposal = state + np.random.normal(0.0, 1.0, dim) * width
        parts_proposal = _lnprob(proposal)
        if not np.isfinite(parts_proposal[0]):
            return state, parts, False, 0.0
        delta = (parts_proposal[0] - parts[0]) / temp
        alpha = 1.0 if delta >= 0.0 else float(np.exp(delta))
        # Moves towards a higher posterior (a lower chi2) are always taken,
        # downhill moves only with probability exp(delta).
        if delta > np.log(np.random.rand()):
            return proposal, parts_proposal, True, alpha
        return state, parts, False, alpha

    parts_prev = _lnprob(state_prev)

    n_steps = n_samples * thin
    if n_adapt is None:
        n_adapt = min(2000, max(200, n_steps // 2))
    n_adapt = max(0, int(n_adapt))

    cancelled = False
    if n_adapt > 0:
        warmup = np.empty((n_adapt, dim))
        log_scale = 0.0
        n_warm = 0
        for i in range(n_adapt):
            state_prev, parts_prev, _, alpha = _metropolis_step(
                state_prev, parts_prev, proposal_scale * np.exp(log_scale)
            )
            warmup[i] = state_prev
            n_warm += 1
            # Robbins-Monro: shrink the step while proposals are rejected too
            # often, widen it while they are accepted too often.
            log_scale += (alpha - target_acceptance) / (i + 1) ** 0.6
            # Once the chain has moved around, the spread of the states it has
            # visited is a far better per-parameter width than a fixed fraction
            # of the starting value.
            if i == n_adapt // 2:
                spread = warmup[:n_warm].std(axis=0)
                usable = spread > 1e-12
                if usable.any():
                    proposal_scale = np.where(usable, spread, proposal_scale)
                    log_scale = 0.0
            if check_cancel and check_cancel():
                cancelled = True
                break
        proposal_scale = proposal_scale * np.exp(log_scale)

    i_step = 0
    for i_step in range(1, n_steps + 1):
        if cancelled:
            break

        state_prev, parts_prev, accepted, _ = _metropolis_step(
            state_prev, parts_prev, proposal_scale
        )
        n_accepted += int(accepted)

        # Record the state of the chain -- on rejection this repeats the
        # previous state, which is what keeps the samples distributed
        # according to the posterior.
        if i_step % thin == 0:
            parameter[n_recorded] = state_prev
            lnprior[n_recorded] = parts_prev[1]
            chi2[n_recorded] = parts_prev[2]
            n_recorded += 1
            if callback:
                callback(n_recorded, n_samples)

        if check_cancel and check_cancel():
            break

    parameter = parameter[:n_recorded]
    lnprior = lnprior[:n_recorded]
    chi2 = chi2[:n_recorded]
    dof = float(model.n_points - model.n_free - 1.0)

    return {
        'chi2r': chi2 / dof,
        'lnprior': lnprior,
        'parameter_values': parameter,
        'parameter_names': model.parameter_names,
        'acceptance_rate': n_accepted / float(max(1, i_step)),
        # One chain, with its per-draw structure kept so that the split R-hat
        # and the autocorrelation time can be computed from it.
        'chains': parameter[np.newaxis, :, :],
    }


def _seed_block_covariances(
        fit: cs.core.fitting.fit.Fit,
        blocks: list[np.ndarray],
        state: np.ndarray,
        step_size: float,
        model: cs.core.models.Model = None
) -> list[np.ndarray]:
    """Return an initial proposal covariance for each block.

    The curvature of the objective at the optimum is very nearly the ideal
    preconditioner, and :attr:`chisurf.core.fitting.fit.Fit.covariance_matrix`
    already computes it for the error bars -- it was simply never used by the
    sampler. Where it is unavailable or not positive definite for a block, fall
    back to a diagonal scaled by the parameter values, which is what the
    unblocked sampler has always done.

    Parameters
    ----------
    fit : Fit
        Fit supplying the covariance at the current parameters.
    blocks : list of numpy.ndarray
        Index arrays into the free-parameter vector, one per block.
    state : numpy.ndarray
        Current parameter vector, used for the fallback scale.
    step_size : float
        Relative proposal width used by the fallback.
    model : chisurf.core.models.Model, optional
        Model being sampled. ``fit.covariance_matrix`` is defined over
        ``fit.model``, so its indices only mean anything when that is what is
        being sampled; for any other model (e.g. a group's global model) the
        curvature seed is skipped and warm-up adaptation supplies the
        covariance instead.

    Returns
    -------
    tuple
        ``(covariances, from_curvature)`` -- one ``(k, k)`` covariance per
        block, and a flag per block saying whether it came from the curvature or
        from the fallback diagonal. The flag decides whether warm-up is allowed
        to replace the block's *shape*: an exact curvature cannot be improved on
        by a short chain, a diagonal guess can.
    """
    full = None
    try:
        if model is not None and model is not fit.model:
            raise ValueError("covariance indices belong to a different model")
        cov, used = fit.covariance_matrix
        cov = np.asarray(cov, dtype=np.float64)
        used = list(used)
        if cov.ndim == 2 and cov.shape[0] == len(used) == cov.shape[1]:
            full = np.zeros((state.size, state.size), dtype=np.float64)
            # ``covariance_matrix`` drops parameters the model does not respond
            # to, so scatter the sub-matrix back into full-vector coordinates.
            idx = np.array(used, dtype=int)
            keep = idx < state.size
            idx = idx[keep]
            sub = cov[np.ix_(keep.nonzero()[0], keep.nonzero()[0])]
            full[np.ix_(idx, idx)] = sub
    except Exception:
        full = None

    fallback = np.abs(state) * step_size
    fallback[fallback < 1e-15] = step_size

    out = []
    from_curvature = []
    for block in blocks:
        k = block.size
        cov_b = None
        if full is not None:
            candidate = full[np.ix_(block, block)]
            if np.all(np.isfinite(candidate)) and np.all(np.diag(candidate) > 0.0):
                try:
                    np.linalg.cholesky(
                        candidate + 1e-12 * np.eye(k) * np.trace(candidate) / k
                    )
                    cov_b = candidate
                except np.linalg.LinAlgError:
                    cov_b = None
        from_curvature.append(cov_b is not None)
        if cov_b is None:
            cov_b = np.diag(fallback[block] ** 2)
        out.append(cov_b)
    return out, from_curvature


def _cholesky_or_diagonal(cov: np.ndarray) -> np.ndarray:
    """Return a Cholesky factor of ``cov``, falling back to its diagonal.

    An adapted empirical covariance can be singular early in a warm-up (fewer
    samples than dimensions, or a parameter that has not moved). Rather than
    fail, ridge it and, if that still fails, drop the correlations -- a diagonal
    proposal is worse but always valid.
    """
    k = cov.shape[0]
    scale = float(np.trace(cov)) / max(1, k)
    for ridge in (0.0, 1e-10, 1e-6, 1e-3):
        try:
            return np.linalg.cholesky(cov + ridge * scale * np.eye(k))
        except np.linalg.LinAlgError:
            continue
    return np.diag(np.sqrt(np.maximum(np.diag(cov), 1e-30)))


#: Optimal scaling of a random-walk Metropolis on a Gaussian target whose
#: proposal covariance matches the posterior's, from Roberts & Rosenthal. Once a
#: block's covariance has been adapted, this is the right place to restart its
#: scale search from -- not 1.0, which is too wide by ``sqrt(d)``.
OPTIMAL_RWM_SCALING = 2.38


class _DualAveraging:
    r"""Nesterov dual averaging of a log step size towards a target acceptance.

    The scheme Stan uses to tune its step size, and a strict improvement on
    Robbins-Monro here for one reason: it reports the *running average* of the
    iterates rather than the last one, so the value handed to the recording
    phase is a converged estimate instead of wherever the last few random
    acceptances happened to leave it.

    Notes
    -----
    This is the same technique measured to *degrade* a finite-difference HMC
    (see ``okf/references/autodiff-assessment.md``), and the distinction matters:
    there, rejections came from gradient noise that a smaller step could not
    reduce, so the search ran away downwards. A random-walk acceptance rate
    responds to the step size monotonically and without noise of that kind, so
    the assumption dual averaging makes actually holds.
    """

    def __init__(self, log_eps: float, target: float,
                 gamma: float = 0.05, t0: float = 10.0, kappa: float = 0.75):
        """Start averaging around ``log_eps``, aiming at ``target`` acceptance.

        Parameters
        ----------
        log_eps : float
            Initial log step size.
        target : float
            Desired acceptance probability.
        gamma, t0, kappa : float, optional
            Nesterov's shrinkage, stability and decay constants; Stan's defaults.
        """
        self.target = float(target)
        self.gamma = float(gamma)
        self.t0 = float(t0)
        self.kappa = float(kappa)
        self.restart(log_eps)

    def restart(self, log_eps: float) -> None:
        """Re-centre the search on ``log_eps`` and forget the history.

        Called whenever the proposal covariance changes, because that makes
        every previous acceptance measurement describe a different proposal.
        """
        # Stan centres the search at ``log(10 * eps)`` because its initial step
        # size comes from a crude doubling heuristic and needs room to grow
        # upwards. Here the initial scale is already the theoretical optimum for
        # the seeded covariance, so the same inflation just starts the search a
        # decade too wide.
        self.mu = float(log_eps)
        self.log_eps = float(log_eps)
        self.log_eps_bar = float(log_eps)
        self.h_bar = 0.0
        self.counter = 0

    def update(self, alpha: float) -> float:
        """Fold in one acceptance probability and return the new log step size."""
        self.counter += 1
        eta = 1.0 / (self.counter + self.t0)
        self.h_bar = (1.0 - eta) * self.h_bar + eta * (self.target - float(alpha))
        self.log_eps = self.mu - np.sqrt(self.counter) / self.gamma * self.h_bar
        weight = self.counter ** (-self.kappa)
        self.log_eps_bar = weight * self.log_eps + (1.0 - weight) * self.log_eps_bar
        return self.log_eps

    def final(self) -> float:
        """Return the averaged log step size to sample with."""
        return float(self.log_eps_bar)


def _adaptation_windows(
        n_adapt: int,
        init_buffer: int = 75,
        term_buffer: int = 50,
        base_window: int = 25,
) -> tuple[int, int, list[int]]:
    """Return ``(init_buffer, term_buffer, window_ends)`` for a warm-up.

    Stan's windowed schedule. The warm-up is split into three phases:

    - an **initial buffer** that tunes only the step size, letting the chain
      reach the typical set before any covariance is estimated from it;
    - a sequence of **doubling windows**, each ending in a covariance update.
      Each estimate uses only its own window, so the badly-scaled early draws
      are discarded rather than averaged in forever, and each window is twice as
      long as the last because a better proposal earns a better estimate;
    - a **terminal buffer** that re-tunes the step size against the final
      covariance without changing it again.

    Parameters
    ----------
    n_adapt : int
        Warm-up sweeps available.
    init_buffer, term_buffer, base_window : int, optional
        Phase sizes; shrunk proportionally when the warm-up is too short.

    Returns
    -------
    tuple
        The two buffer lengths and the sweep indices at which the covariance is
        re-estimated. The list is empty when the warm-up is too short to
        estimate one at all, leaving step-size adaptation only.
    """
    n_adapt = int(n_adapt)
    if n_adapt < 20:
        return n_adapt, 0, []
    if init_buffer + base_window + term_buffer > n_adapt:
        init_buffer = int(round(0.15 * n_adapt))
        term_buffer = int(round(0.10 * n_adapt))
        base_window = n_adapt - init_buffer - term_buffer
        if base_window < 2:
            return n_adapt, 0, []

    ends: list[int] = []
    start, window = init_buffer, base_window
    last = n_adapt - term_buffer
    while start + window <= last:
        end = start + window
        # Absorb a remainder too small for another doubling into this window
        # rather than leaving it to a stunted one.
        if end + 2 * window > last:
            end = last
        ends.append(end)
        start = end
        window *= 2
    return init_buffer, term_buffer, ends


def _regularised_covariance(draws: np.ndarray) -> np.ndarray | None:
    """Return a shrunk sample covariance, or ``None`` if unusable.

    Stan's regularisation with a weight worth five observations, but shrinking
    towards ``diag(cov)`` rather than towards the identity. The difference is not
    cosmetic. Stan samples in a standardised unconstrained space where every
    coordinate is O(1), so a ``1e-3 * I`` ridge is negligible; ChiSurf's
    parameters carry physical units and range over many orders of magnitude, so
    the same absolute ridge silently *dominates* the covariance of any
    finely-scaled parameter, inflating its proposal until nothing is accepted.
    Shrinking towards the diagonal regularises the same failure -- a window
    holding fewer draws than the block has dimensions gives a singular
    estimate -- while being invariant to the units each parameter is measured in.

    A chain proposing in a degenerate subspace does not raise; it just stops
    exploring, which is much harder to notice than an exception.

    Parameters
    ----------
    draws : numpy.ndarray
        ``(n_draws, k)`` window of visited states.

    Returns
    -------
    numpy.ndarray or None
        The ``(k, k)`` regularised covariance.
    """
    n = int(draws.shape[0])
    if n < 3:
        return None
    cov = np.atleast_2d(np.cov(draws, rowvar=False))
    if not np.all(np.isfinite(cov)):
        return None
    variance = np.diag(cov)
    if not np.all(variance > 0.0):
        return None
    weight = n / (n + 5.0)
    return weight * cov + (1.0 - weight) * np.diag(variance)


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def sample_differential_evolution(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        n_chains: int = None,
        thin: int = 1,
        chi2max: float = np.inf,
        temp: float = 1.0,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        n_adapt: int = None,
        jitter: float = 1e-4,
        snooker: float = 0.1,
        model: cs.core.models.Model = None,
        seed: int = None
) -> dict:
    r"""Sample with Differential-Evolution MCMC (ter Braak).

    A population of chains proposes moves from the *differences between other
    chains*:

    .. math::

        x^\ast_i = x_i + \gamma\,(x_j - x_k) + \varepsilon ,
        \qquad \gamma = \frac{2.38}{\sqrt{2d}} ,

    with :math:`j \ne k \ne i` drawn from the population and
    :math:`\varepsilon` a small Gaussian jitter that keeps the chain
    irreducible. Because the
    difference vectors are themselves distributed like the target, the proposal
    acquires the posterior's correlation structure **for free** -- no covariance
    to estimate, no per-parameter scale to tune, and no gradient.

    That is the practical answer to "why not Hamiltonian Monte Carlo": HMC and
    NUTS need :math:`
    abla \log p`, which ChiSurf cannot supply (see the
    [autodiff assessment](/references/autodiff-assessment.md)), and a systematic
    benchmark of gradient-free samplers found differential evolution at a ~25 %
    acceptance target to outperform every alternative tested -- including the
    affine-invariant stretch move that :func:`sample_ensemble` uses.

    Two refinements from the literature are included. Every tenth generation
    uses :math:`\gamma = 1`, which turns the difference vector into a direct
    mode-to-mode jump and is what lets the population escape a local optimum.
    And a fraction of moves are **snooker** updates, which propose along the line
    joining the current state to another chain and scale by a random factor --
    this is what extends the method past the roughly ``2d`` chains plain DE
    otherwise wants.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose free parameters are sampled.
    steps : int
        Recorded generations. Each generation moves every chain once, so the
        returned sample holds ``steps * n_chains`` draws.
    n_chains : int, optional
        Population size. Defaults to ``max(8, 2*d)``; the snooker updates make
        smaller populations workable.
    thin : int, optional
        Record every ``thin`` generations.
    chi2max : float, optional
        Hard cutoff on chi².
    temp : float, optional
        Sampling temperature.
    callback : callable, optional
        Called as ``callback(recorded, total)``.
    check_cancel : callable, optional
        Polled per generation; stops early when it returns ``True``.
    n_adapt : int, optional
        Warm-up generations, discarded. The proposal is not tuned during them --
        DE has nothing to tune -- they simply let the population spread out.
    jitter : float, optional
        Relative width of the additive noise.
    snooker : float, optional
        Fraction of proposals that use a snooker update.
    model : chisurf.core.models.Model, optional
        Model to sample; defaults to ``fit.model``.
    seed : int, optional
        Seed for the sampler's own generator.

    Returns
    -------
    dict
        ``chi2r``, ``lnprior``, ``parameter_values``, ``parameter_names``,
        ``chains`` (one per population member) and ``acceptance_rate``.

    Notes
    -----
    The population is a valid Markov chain on the *product* space, so the
    per-member chains are correlated with one another and their cross-chain
    R-hat is optimistic in the same way an ensemble sampler's is. Use
    independent runs for the decisive convergence check.
    """
    if model is None:
        model = fit.model
    rng = np.random.default_rng(seed)
    dim = model.n_free
    thin = max(1, int(thin))
    n_samples = max(1, int(steps) // thin)
    bounds = model.parameter_bounds
    start = np.asarray(model.parameter_values, dtype=np.float64)

    if n_chains is None:
        n_chains = max(8, 2 * dim)
    n_chains = max(4, int(n_chains))

    def _lnprob(vector):
        """Return ``(lnpost, lnprior, chi2)`` of a parameter vector."""
        lnlike, lnpr, c2 = cs.core.fitting.fit.lnprob_parts(
            parameter_values=list(vector), fit=fit, chi2max=chi2max,
            bounds=bounds, model=model
        )
        return lnlike + lnpr, lnpr, c2

    # Seed the population around the current point. The spread has to be big
    # enough that the initial difference vectors are meaningful -- a population
    # started at a single point can never move, since every difference is zero.
    scale = np.abs(start) * max(jitter, 1e-3) * 10.0
    scale[scale < 1e-12] = max(jitter, 1e-3)
    population = start + rng.normal(0.0, 1.0, (n_chains, dim)) * scale
    population[0] = start
    for c in range(n_chains):
        for j in range(dim):
            lo, hi = bounds[j]
            if lo is not None and np.isfinite(lo):
                population[c, j] = max(population[c, j], lo)
            if hi is not None and np.isfinite(hi):
                population[c, j] = min(population[c, j], hi)

    parts = [_lnprob(population[c]) for c in range(n_chains)]
    gamma0 = 2.38 / math.sqrt(2.0 * max(1, dim))
    noise = np.abs(start) * jitter
    noise[noise < 1e-15] = jitter

    n_accepted = 0
    n_proposed = 0

    def _generation(generation_index):
        """Move every chain once."""
        nonlocal n_accepted, n_proposed
        # Every tenth generation jumps with gamma = 1: the difference between
        # two chains then becomes a direct mode-to-mode move, which is how the
        # population crosses between separated optima.
        gamma = 1.0 if (generation_index % 10 == 9) else gamma0
        order = rng.permutation(n_chains)
        for c in order:
            others = [o for o in range(n_chains) if o != c]
            if rng.random() < snooker and n_chains >= 4:
                z, j, k = rng.choice(others, size=3, replace=False)
                direction = population[c] - population[z]
                norm = float(direction @ direction)
                if norm <= 0.0:
                    continue
                # Project the two helper chains onto the line through z and
                # scale along it; the Jacobian of that map enters the
                # acceptance ratio below.
                proj = ((population[j] - population[k]) @ direction) / norm
                step = rng.uniform(1.2, 2.2) * proj * direction
                proposal = population[c] + step
                new_norm = float((proposal - population[z]) @ (proposal - population[z]))
                if new_norm <= 0.0:
                    continue
                log_jacobian = 0.5 * (dim - 1) * (math.log(new_norm) - math.log(norm))
            else:
                j, k = rng.choice(others, size=2, replace=False)
                proposal = (population[c] + gamma * (population[j] - population[k])
                            + rng.normal(0.0, 1.0, dim) * noise)
                log_jacobian = 0.0

            candidate = _lnprob(proposal)
            n_proposed += 1
            if not np.isfinite(candidate[0]):
                continue
            delta = (candidate[0] - parts[c][0]) / temp + log_jacobian
            if delta > math.log(rng.random()):
                population[c] = proposal
                parts[c] = candidate
                n_accepted += 1

    cancelled = False
    if n_adapt is None:
        n_adapt = min(500, max(50, (n_samples * thin) // 4))
    for g in range(max(0, int(n_adapt))):
        _generation(g)
        if check_cancel and check_cancel():
            cancelled = True
            break
    n_accepted = 0
    n_proposed = 0

    recorded = np.empty((n_samples, n_chains, dim))
    lnprior = np.empty((n_samples, n_chains))
    chi2 = np.empty((n_samples, n_chains))
    n_recorded = 0
    for g in range(1, n_samples * thin + 1):
        if cancelled:
            break
        _generation(g)
        if g % thin == 0:
            recorded[n_recorded] = population
            for c in range(n_chains):
                lnprior[n_recorded, c] = parts[c][1]
                chi2[n_recorded, c] = parts[c][2]
            n_recorded += 1
            if callback:
                callback(n_recorded, n_samples)
        if check_cancel and check_cancel():
            break

    recorded = recorded[:n_recorded]
    lnprior = lnprior[:n_recorded]
    chi2 = chi2[:n_recorded]
    model.parameter_values = list(start)
    model.update_model()

    dof = float(model.n_points - model.n_free - 1.0)
    # ``chains`` is one row per population member; the flat view stacks them.
    chains = recorded.transpose(1, 0, 2) if n_recorded else recorded.reshape(0, 0, dim)
    return {
        'chi2r': chi2.reshape(-1) / dof,
        'lnprior': lnprior.reshape(-1),
        'parameter_values': recorded.reshape(-1, dim),
        'parameter_names': model.parameter_names,
        'chains': chains,
        'acceptance_rate': n_accepted / float(max(1, n_proposed)),
        'n_chains': n_chains,
    }


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def walk_mcmc_blocked(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        step_size: float = 0.1,
        temp: float = 1.0,
        thin: int = 1,
        chi2max: float = np.inf,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        n_adapt: int = None,
        blocks: typing.Sequence[typing.Sequence[int]] = None,
        model: cs.core.models.Model = None
) -> dict:
    """Sample a fit block by block, with a per-block correlated proposal.

    Two things separate this from :func:`walk_mcmc`. The proposal is a **full
    covariance** per block rather than a diagonal, seeded from the curvature at
    the optimum and then adapted, so correlated parameters (amplitude/lifetime
    pairs, and anything a global fit shares) are proposed along the directions
    the posterior actually extends in. And a move touches **one block** rather
    than the whole vector, so under the selective update of
    :class:`~chisurf.core.models.global_model.globalfit.GlobalFitModel` a block
    confined to one dataset costs one local model evaluation instead of all of
    them.

    Blocks come from the fit's factor graph
    (:meth:`~chisurf.core.fitting.factorgraph.FactorGraph.sampling_blocks`):
    variables are grouped by the set of datasets that depend on them. For a
    single-dataset fit that is one block, and this reduces to an ordinary
    random walk with a correlated proposal.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose free parameters are sampled.
    steps : int
        Number of recorded sweeps (a sweep proposes every block once). Warm-up
        sweeps are additional.
    step_size : float
        Relative proposal width used when no usable covariance is available.
    temp : float, optional
        Sampling temperature; values above one flatten the posterior.
    thin : int, optional
        Record the chain state only every ``thin`` sweeps.
    chi2max : float, optional
        Hard cutoff on chi²; proposals above it are always rejected.
    callback : callable, optional
        Called as ``callback(n_recorded, n_samples)`` after each recorded state.
    check_cancel : callable, optional
        Polled once per sweep; sampling stops early when it returns ``True``.
    n_adapt : int, optional
        Warm-up sweeps used to adapt the block covariances. Defaults to half the
        chain (bounded to ``[200, 2000]``); ``0`` disables adaptation.
    blocks : sequence of sequence of int, optional
        Explicit blocks as index arrays into the free-parameter vector. Defaults
        to the factor graph's partition.
    model : chisurf.core.models.Model, optional
        Model to sample. Defaults to ``fit.model``, which for a
        :class:`~chisurf.core.fitting.fit.FitGroup` is the *selected member's*
        model. Pass
        :func:`chisurf.core.fitting.factorgraph.posterior_model` to sample a
        group's joint posterior, which is where the blocking actually pays.

    Returns
    -------
    dict
        ``chi2r``, ``lnprior``, ``parameter_values``, ``parameter_names``,
        ``chains``, ``acceptance_rate``, plus ``block_acceptance`` and
        ``block_sizes`` per block.

    Notes
    -----
    Adaptation happens entirely within the warm-up and is frozen before
    recording, so the recorded chain is a time-homogeneous Markov chain whose
    stationary distribution is the posterior. Adapting while recording would
    break that guarantee.
    """
    if model is None:
        model = fit.model
    dim = model.n_free
    state = np.asarray(model.parameter_values, dtype=np.float64)
    thin = max(1, int(thin))
    n_samples = max(1, int(steps) // thin)
    bounds = model.parameter_bounds

    if blocks is None:
        blocks = _default_blocks(fit, dim, model)
    block_idx = [np.asarray(b, dtype=int) for b in blocks if len(b)]
    if not block_idx:
        block_idx = [np.arange(dim, dtype=int)]

    def _lnprob(vector):
        """Return ``(lnpost, lnprior, chi2)`` of a parameter vector."""
        lnlike, lnpr, c2 = cs.core.fitting.fit.lnprob_parts(
            parameter_values=vector, fit=fit, chi2max=chi2max,
            bounds=bounds, model=model
        )
        return lnlike + lnpr, lnpr, c2

    cov, seeded_from_curvature = _seed_block_covariances(
        fit, block_idx, state, step_size, model
    )
    factor = [_cholesky_or_diagonal(c) for c in cov]
    # The optimal scaling of a random-walk Metropolis falls with the dimension
    # of the move, so each block gets the target appropriate to its own size.
    target = [
        0.44 if idx.size == 1 else max(0.234, 0.44 / np.sqrt(idx.size))
        for idx in block_idx
    ]
    # Once a block's covariance describes the posterior, 2.38/sqrt(d) is the
    # optimal multiplier -- so start there rather than at 1.0, which is too wide
    # by that same factor and costs the whole init buffer to walk back down.
    def _initial_log_scale(size: int) -> float:
        """Return the theoretically optimal starting log scale for a block."""
        return float(np.log(OPTIMAL_RWM_SCALING / np.sqrt(max(1, size))))

    log_scale = [_initial_log_scale(idx.size) for idx in block_idx]
    adapters = [
        _DualAveraging(log_scale[b], target[b]) for b in range(len(block_idx))
    ]

    parts = _lnprob(state)
    accepted = np.zeros(len(block_idx), dtype=np.int64)
    proposed = np.zeros(len(block_idx), dtype=np.int64)

    def _sweep(current, current_parts, adapt=False):
        """Propose every block once; return the new state and its parts."""
        for b, idx in enumerate(block_idx):
            trial = current.copy()
            draw = factor[b] @ np.random.normal(0.0, 1.0, idx.size)
            trial[idx] = current[idx] + np.exp(log_scale[b]) * draw
            trial_parts = _lnprob(trial)
            proposed[b] += 1
            if np.isfinite(trial_parts[0]):
                delta = (trial_parts[0] - current_parts[0]) / temp
                alpha = 1.0 if delta >= 0.0 else float(np.exp(delta))
                if delta > np.log(np.random.rand()):
                    current, current_parts = trial, trial_parts
                    accepted[b] += 1
            else:
                alpha = 0.0
            if adapt:
                log_scale[b] = adapters[b].update(alpha)
        return current, current_parts

    cancelled = False
    if n_adapt is None:
        # A short warm-up, deliberately. What is being adapted is one scale per
        # block, which dual averaging settles in a hundred sweeps or so; the
        # previous default spent *half* the chain on it, and since warm-up draws
        # are discarded that came straight out of the effective sample size.
        # Measured across four posteriors, shortening it from 2000 to 200 sweeps
        # on a 4000-step chain improved effective samples per evaluation by
        # 1.4x-1.6x on every one of them.
        n_adapt = int(np.clip((n_samples * thin) // 20, 100, 500))
    n_adapt = max(0, int(n_adapt))

    if n_adapt > 0:
        # Stan's windowed schedule: an initial buffer that only tunes the scale,
        # then doubling windows each ending in a covariance update, then a
        # terminal buffer that re-tunes the scale against the final covariance.
        init_buffer, _, window_ends = _adaptation_windows(n_adapt)
        pending = set(window_ends)
        warmup = np.empty((n_adapt, dim))
        # Every estimate uses all draws since the end of the initial buffer,
        # growing rather than sliding. Stan slides -- each window's metric comes
        # from that window alone -- and that does *not* transfer to a random
        # walk. NUTS moves nearly independently each iteration, so a short
        # window still spans the posterior; a random walk moves by one proposal,
        # so a short window measures how far the chain travelled, not how wide
        # the target is. Measured here: a sliding second window estimated the
        # scale 600x too small, and because a narrower proposal then travels
        # even less, every later window shrank again. Growing windows cannot
        # collapse that way, and still discard the badly-scaled transient that
        # the initial buffer exists to absorb.
        window_start = init_buffer
        for i in range(n_adapt):
            state, parts = _sweep(state, parts, adapt=True)
            warmup[i] = state
            if (i + 1) in pending:
                # Once the chain has explored, the empirical covariance of where
                # it has been beats any a-priori guess -- including the curvature
                # at the optimum, which only describes the posterior locally.
                visited = warmup[window_start:i + 1]
                for b, idx in enumerate(block_idx):
                    if seeded_from_curvature[b]:
                        # The curvature at the optimum *is* the posterior
                        # covariance for a near-Gaussian posterior, and a
                        # warm-up chain cannot beat it -- measured, replacing it
                        # cost 40x-80x the effective samples per evaluation.
                        # Only the scale is worth adapting for these blocks.
                        continue
                    empirical = _regularised_covariance(visited[:, idx])
                    if empirical is None:
                        continue
                    # Take the *shape* and throw the *size* away. A warm-up
                    # chain that has not mixed spreads less than the posterior
                    # it is exploring, so its empirical covariance is biased
                    # low -- measured here at 10x too narrow in every direction
                    # at once, i.e. almost purely a scale error with the
                    # correlation structure intact. Adopting it wholesale
                    # therefore *destroys* a good curvature seed; adopting only
                    # its shape keeps the one thing warm-up genuinely learns.
                    # The size is then re-derived by the acceptance-rate
                    # adaptation below, which is what that is for.
                    current = np.exp(2.0 * log_scale[b]) * (
                        factor[b] @ factor[b].T
                    )
                    size = float(np.trace(current))
                    empirical_size = float(np.trace(empirical))
                    if not (empirical_size > 0.0 and np.isfinite(size) and size > 0.0):
                        continue
                    empirical = empirical * (size / empirical_size)
                    factor[b] = _cholesky_or_diagonal(empirical)
                    # The factor now carries the whole proposal, so the scale
                    # restarts at one. Every acceptance measured before this
                    # described a different proposal, so its history goes too.
                    log_scale[b] = 0.0
                    adapters[b].restart(0.0)
            if check_cancel and check_cancel():
                cancelled = True
                break
        # Sample with the *averaged* step size, not the last iterate -- that is
        # the whole point of dual averaging over Robbins-Monro.
        for b in range(len(block_idx)):
            log_scale[b] = adapters[b].final()
        accepted[:] = 0
        proposed[:] = 0

    parameter = np.empty((n_samples, dim))
    lnprior = np.empty(n_samples)
    chi2 = np.empty(n_samples)
    n_recorded = 0

    n_sweeps = n_samples * thin
    for i_sweep in range(1, n_sweeps + 1):
        if cancelled:
            break
        state, parts = _sweep(state, parts)
        if i_sweep % thin == 0:
            parameter[n_recorded] = state
            lnprior[n_recorded] = parts[1]
            chi2[n_recorded] = parts[2]
            n_recorded += 1
            if callback:
                callback(n_recorded, n_samples)
        if check_cancel and check_cancel():
            break

    parameter = parameter[:n_recorded]
    lnprior = lnprior[:n_recorded]
    chi2 = chi2[:n_recorded]
    dof = float(model.n_points - model.n_free - 1.0)
    with np.errstate(divide='ignore', invalid='ignore'):
        per_block = np.where(proposed > 0, accepted / np.maximum(proposed, 1), np.nan)

    return {
        'chi2r': chi2 / dof,
        'lnprior': lnprior,
        'parameter_values': parameter,
        'parameter_names': model.parameter_names,
        'chains': parameter[np.newaxis, :, :],
        'acceptance_rate': float(accepted.sum() / max(1, proposed.sum())),
        'block_acceptance': per_block,
        'block_sizes': [int(idx.size) for idx in block_idx],
    }


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def sample_independent_components(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        step_size: float = 0.1,
        temp: float = 1.0,
        thin: int = 1,
        chi2max: float = np.inf,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        n_adapt: int = None,
        model: cs.core.models.Model = None,
        seed: int = None
) -> dict:
    r"""Sample each independent sub-problem separately and merge them exactly.

    When a fit's factor graph falls into several connected components, the
    posterior factorises **exactly**:

    .. math::

        p(\theta \mid D) \;=\; \prod_c p_c(\theta_c),

    because no factor -- no dataset likelihood, no prior -- links a parameter in
    one component to a parameter in another. Sampling all of them jointly is
    then pure waste: a random walk's cost for a given effective sample size
    grows roughly with the square of the dimension it moves in, and in a global
    fit every joint proposal re-evaluates every dataset. Sampling each component
    on its own replaces one :math:`D`-dimensional problem with several
    :math:`d_c`-dimensional ones, each touching only its own data.

    The merge is analytic, not a further approximation. Independence means any
    pairing of draws from different components is itself a draw from the joint,
    so the components' chains are shuffled independently and stacked side by
    side. The data misfit and the log-prior are additive over components, which
    lets both be reconstructed in closed form from the per-component runs (see
    Notes) without a single extra model evaluation.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose free parameters are sampled.
    steps : int
        Recorded sweeps per component.
    step_size : float
        Relative proposal width used when no usable covariance is available.
    temp : float, optional
        Sampling temperature.
    thin : int, optional
        Record only every ``thin`` sweeps.
    chi2max : float, optional
        Hard cutoff on chi².
    callback : callable, optional
        Called as ``callback(done, total)`` over the whole run.
    check_cancel : callable, optional
        Polled during sampling; stops early when it returns ``True``.
    n_adapt : int, optional
        Warm-up sweeps per component.
    model : chisurf.core.models.Model, optional
        Model to sample; defaults to ``fit.model``. Pass
        :func:`chisurf.core.fitting.factorgraph.posterior_model` for a group's
        joint posterior, which is where components normally appear.
    seed : int, optional
        Seed for the independent shuffle used to merge the components.

    Returns
    -------
    dict
        The same keys as :func:`walk_mcmc_blocked`, plus ``n_components`` and
        ``component_sizes``. Falls back to :func:`walk_mcmc_blocked` when there
        is only one component, since there is then nothing to decompose.

    Notes
    -----
    Each component is sampled from the *same* reference state
    :math:`\theta^0`, with the other components held there. Their datasets
    contribute a constant to :math:`\chi^2`, which cancels in the Metropolis
    ratio, so each component's chain is exactly its own marginal posterior.

    Because :math:`\chi^2` is a sum over datasets and each dataset belongs to
    exactly one component, run *c* reports
    :math:`\chi^2_{\mathrm{run},c} = \chi^2_c(\theta_c) + [\chi^2_0 - \chi^2_c(\theta^0_c)]`.
    Summing over the :math:`C` components and cancelling gives the joint value
    for a merged draw,

    .. math::

        \chi^2(\theta) \;=\; \sum_c \chi^2_{\mathrm{run},c} \;-\; (C-1)\,\chi^2_0 ,

    and the log-prior, being a sum over parameters, obeys the same identity.
    Both are therefore exact, not reconstructed by re-evaluation.
    """
    if model is None:
        model = fit.model

    components = _component_blocks(fit, model)
    if len(components) < 2:
        return walk_mcmc_blocked(
            fit=fit, steps=steps, step_size=step_size, temp=temp, thin=thin,
            chi2max=chi2max, callback=callback, check_cancel=check_cancel,
            n_adapt=n_adapt, model=model,
        )

    reference = np.asarray(model.parameter_values, dtype=np.float64)
    lnlike_0, lnprior_0, chi2_0 = cs.core.fitting.fit.lnprob_parts(
        parameter_values=list(reference), fit=fit, chi2max=np.inf,
        bounds=model.parameter_bounds, model=model
    )

    results = []
    n_total = len(components)
    for c, (indices, blocks) in enumerate(components):
        # Every component starts from the same reference, so the constant the
        # other components contribute is identical across runs -- which is what
        # makes the closed-form merge below exact.
        model.parameter_values = list(reference)
        model.update_model()
        r = walk_mcmc_blocked(
            fit=fit, steps=steps, step_size=step_size, temp=temp, thin=thin,
            chi2max=chi2max, check_cancel=check_cancel, n_adapt=n_adapt,
            model=model, blocks=blocks,
        )
        results.append((indices, r))
        if callback:
            callback(c + 1, n_total)
        if check_cancel and check_cancel():
            break

    model.parameter_values = list(reference)
    model.update_model()

    return _merge_components(
        results, reference, chi2_0, lnprior_0, model, seed=seed
    )


def _shared_and_private(fit, model):
    """Split a global fit's variables into shared ones and per-dataset private ones.

    A variable is **shared** when more than one dataset likelihood depends on it
    -- i.e. it is the separator that couples the fit -- and **private** when
    exactly one does. Returns ``None`` when the split is not usable (no shared
    variables, no local fits, or a variable the graph cannot place).

    Returns
    -------
    tuple or None
        ``(shared_indices, [(local_fit, private_indices), ...])`` as index
        arrays into the model's free-parameter vector.
    """
    from chisurf.core.fitting import factorgraph

    local_fits = list(getattr(model, "fits", []) or [])
    if not local_fits:
        return None
    graph = factorgraph.build_factor_graph(fit, model=model)

    shared, private = [], {}
    for key in graph.variables:
        datasets = {
            graph.factors[f].fit_index for f in graph.factors_of(key)
            if graph.factors[f].kind == factorgraph.LIKELIHOOD
            and graph.factors[f].fit_index is not None
        }
        index = graph.index_of(key)
        if index is None:
            return None
        if len(datasets) > 1:
            shared.append(index)
        elif len(datasets) == 1:
            private.setdefault(next(iter(datasets)), []).append(index)
        else:
            # A free parameter no dataset depends on cannot be profiled out.
            return None
    if not shared:
        return None

    # A local model's own free-parameter list may still contain a *shared*
    # parameter -- the link master lives on one of the datasets -- so the
    # profile must be told which positions of that list it may move. Optimising
    # the whole list would re-optimise the shared parameter and silently undo
    # every proposal, leaving a flat target and a chain that diffuses away.
    joint_params = list(model.parameters)
    position = {id(p): i for i, p in enumerate(joint_params)}
    groups = []
    for k, local in enumerate(local_fits):
        joint_idx = sorted(private.get(k, []))
        if not joint_idx:
            continue
        local_params = list(local.model.parameters)
        local_pos, ordered_joint = [], []
        for i, p in enumerate(local_params):
            j = position.get(id(p))
            if j is not None and j in joint_idx:
                local_pos.append(i)
                ordered_joint.append(j)
        if len(ordered_joint) != len(joint_idx):
            return None
        groups.append((
            local,
            np.array(ordered_joint, dtype=int),
            np.array(local_pos, dtype=int),
        ))
    if not groups:
        return None
    return np.array(sorted(shared), dtype=int), groups


def _restricted_wres(x, local_model, positions, include_priors=True):
    """Weighted residuals of one local model with only ``positions`` varied."""
    values = list(local_model.parameter_values)
    for pos, v in zip(positions, x):
        values[pos] = v
    return cs.core.fitting.fit.get_wres(values, local_model, include_priors)


def _profile_locals(groups, model, include_priors: bool = True):
    r"""Optimise each dataset's private parameters and Laplace-marginalise them.

    At fixed shared parameters the datasets are conditionally independent, so
    each one's private parameters can be optimised on their own. The Gaussian
    (Laplace) integral around that optimum is the dataset's contribution to the
    collapsed target,

    .. math::

        \ln \hat{Z}_k = -\tfrac12 \chi^2_k(\hat\theta_k)
                        + \tfrac12 \ln\det\!\left(2\pi\Sigma_k\right).

    :math:`\Sigma_k` must be the **conditional** covariance of the private
    parameters at fixed shared ones, so it is built from the Jacobian of the
    *restricted* residuals rather than from ``Fit.covariance_matrix`` (which is
    the marginal covariance over everything the local model varies, including a
    shared parameter when the link master happens to live on that dataset).

    Returns
    -------
    tuple or None
        ``(ln_z_total, [(joint_indices, theta_hat, cholesky_of_sigma), ...])``,
        or ``None`` when a dataset's curvature is unusable.
    """
    total = 0.0
    draws = []
    for local, joint_idx, positions in groups:
        local_model = local.model
        all_bounds = local_model.parameter_bounds
        bounds = [all_bounds[i] for i in positions]
        x0 = [local_model.parameter_values[i] for i in positions]
        try:
            fitted, _ = cs.core.math.optimization.leastsqbound(
                func=_restricted_wres,
                x0=x0,
                args=(local_model, positions, include_priors),
                bounds=bounds,
            )[:2]
        except Exception:
            return None
        fitted = np.atleast_1d(np.asarray(fitted, dtype=np.float64))
        residuals = np.asarray(
            _restricted_wres(fitted, local_model, positions, include_priors),
            dtype=np.float64,
        )
        chi2 = float((residuals ** 2).sum())
        if not np.isfinite(chi2):
            return None

        # Conditional curvature: J^T J over the private parameters only.
        d = fitted.size
        jac = np.empty((residuals.size, d), dtype=np.float64)
        for j in range(d):
            step = FINITE_DIFF * max(abs(float(fitted[j])), 1.0)
            shifted = fitted.copy()
            shifted[j] += step
            r_shifted = np.asarray(
                _restricted_wres(shifted, local_model, positions, include_priors),
                dtype=np.float64,
            )
            if r_shifted.size != residuals.size:
                return None
            jac[:, j] = (r_shifted - residuals) / step
        # Restore the optimum, which the finite differences moved away from.
        _restricted_wres(fitted, local_model, positions, include_priors)

        hessian = jac.T @ jac
        if not np.all(np.isfinite(hessian)):
            return None
        try:
            chol_h = np.linalg.cholesky(
                hessian + 1e-12 * np.eye(d) * max(1.0, float(np.trace(hessian)) / d)
            )
        except np.linalg.LinAlgError:
            return None
        logdet_h = 2.0 * float(np.log(np.diag(chol_h)).sum())
        # ln det(2*pi*Sigma) = d*ln(2*pi) - ln det(H)
        total += -0.5 * chi2 + 0.5 * (d * math.log(2.0 * math.pi) - logdet_h)

        sigma = np.linalg.inv(hessian + 1e-12 * np.eye(d))
        draws.append((joint_idx, fitted, _cholesky_or_diagonal(sigma)))
    return total, draws


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def sample_marginal_shared(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        step_size: float = 0.1,
        temp: float = 1.0,
        thin: int = 1,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        n_adapt: int = None,
        model: cs.core.models.Model = None,
        seed: int = None
) -> dict:
    r"""Sample only a global fit's *shared* parameters, integrating the rest out.

    Linking a parameter across datasets lowers the dimension of a fit, but it
    does **not** make it easier to sample -- it makes it harder, because the
    shared parameter is strongly correlated with every dataset's private
    parameters and a conditional (block) move can only shift it a little before
    the locals object. Measured on six datasets, linking one parameter cut the
    dimension from 12 to 7 and cost a factor of ~50 in effective samples per
    model evaluation, with the shared parameter's autocorrelation time going
    from 1 to 20.

    Collapsing removes exactly that pathology. At fixed shared parameters the
    datasets are conditionally independent, so each one's private parameters can
    be optimised alone and integrated out analytically (Laplace), leaving a
    target over the shared parameters only:

    .. math::

        p(\theta_S \mid D) \;\propto\; \pi(\theta_S)\,
        \prod_k \int L_k(\theta_S, \theta_k)\,\pi_k(\theta_k)\,\mathrm{d}\theta_k .

    That is a genuinely low-dimensional posterior -- usually one to three
    parameters however many datasets there are. Private parameters are then
    drawn from their conditional Gaussian at each recorded shared state, so the
    result is still a full joint sample.

    **This is exact when each dataset's model is linear in its private
    parameters** -- which covers amplitudes, offsets and scaling factors, i.e.
    most nuisance parameters in fluorescence decay and FCS models. For private
    parameters that enter non-linearly the Laplace integral is an approximation,
    and the marginals should be checked against
    :func:`walk_mcmc_blocked` before being relied on.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose shared parameters are sampled.
    steps : int
        Recorded steps of the shared-parameter chain.
    step_size : float
        Relative proposal width before adaptation.
    temp : float, optional
        Sampling temperature.
    thin : int, optional
        Record only every ``thin`` steps.
    callback : callable, optional
        Called as ``callback(done, total)``.
    check_cancel : callable, optional
        Polled per step; stops early when it returns ``True``.
    n_adapt : int, optional
        Warm-up steps used to adapt the shared-parameter proposal covariance.
    model : chisurf.core.models.Model, optional
        Model to sample; pass
        :func:`chisurf.core.fitting.factorgraph.posterior_model` for a group.
    seed : int, optional
        Seed for the conditional draws of the private parameters.

    Returns
    -------
    dict
        The usual sampling keys, plus ``shared_names``, ``n_shared`` and
        ``collapsed`` (always *True*). Falls back to
        :func:`sample_independent_components` when the fit has no shared
        parameters to collapse onto.
    """
    if model is None:
        model = fit.model

    split = _shared_and_private(fit, model)
    if split is None:
        return sample_independent_components(
            fit=fit, steps=steps, step_size=step_size, temp=temp, thin=thin,
            callback=callback, check_cancel=check_cancel, n_adapt=n_adapt,
            model=model, seed=seed,
        )
    shared_idx, groups = split

    rng = np.random.default_rng(seed)
    thin = max(1, int(thin))
    n_samples = max(1, int(steps) // thin)
    reference = np.asarray(model.parameter_values, dtype=np.float64)
    names = list(model.parameter_names)
    bounds = model.parameter_bounds
    k_shared = shared_idx.size

    def _target(shared_values):
        """Collapsed log-target at a shared-parameter vector."""
        for i, v in zip(shared_idx, shared_values):
            lo, hi = bounds[i]
            if lo is not None and v < lo:
                return None
            if hi is not None and v > hi:
                return None
        state = np.asarray(model.parameter_values, dtype=np.float64)
        state[shared_idx] = shared_values
        model.parameter_values = list(state)
        model.update_model()
        profiled = _profile_locals(groups, model)
        if profiled is None:
            return None
        ln_z, draws = profiled
        prior = cs.core.fitting.fit.lnprior(
            list(model.parameter_values), fit, bounds=bounds, model=model
        )
        # ``lnprior`` covers every free parameter, but the private ones were
        # already folded into ln_z by _profile_locals; only the shared prior
        # belongs in the collapsed target.
        shared_prior = 0.0
        params = list(model.parameters)
        for i in shared_idx:
            pr = cs.core.fitting.fit._smooth_prior(params[i])
            if pr is not None:
                shared_prior += pr.lnpdf(float(params[i].value))
        if not np.isfinite(prior):
            return None
        return ln_z + shared_prior, draws

    start = reference[shared_idx].copy()
    current = _target(start)
    if current is None:
        cs.logging.warning(
            "collapsed sampling: could not profile the local fits; "
            "falling back to a joint chain"
        )
        model.parameter_values = list(reference)
        model.update_model()
        return sample_independent_components(
            fit=fit, steps=steps, step_size=step_size, temp=temp, thin=thin,
            callback=callback, check_cancel=check_cancel, n_adapt=n_adapt,
            model=model, seed=seed,
        )

    scale = np.abs(start) * step_size
    scale[scale < 1e-15] = step_size
    factor = np.diag(scale)
    log_scale = 0.0
    target_acceptance = 0.44 if k_shared == 1 else max(0.234, 0.44 / np.sqrt(k_shared))

    if n_adapt is None:
        n_adapt = min(500, max(100, (n_samples * thin) // 2))
    n_adapt = max(0, int(n_adapt))

    def _step(state, parts, adapt=None):
        """One Metropolis step in the collapsed (shared-only) space."""
        proposal = state + np.exp(log_scale) * (factor @ rng.normal(size=k_shared))
        candidate = _target(proposal)
        if candidate is None:
            alpha = 0.0
        else:
            delta = (candidate[0] - parts[0]) / temp
            alpha = 1.0 if delta >= 0.0 else float(np.exp(delta))
            if delta > np.log(rng.random()):
                return proposal, candidate, True, alpha
        return state, parts, False, alpha

    state = start
    cancelled = False
    if n_adapt > 0:
        warm = np.empty((n_adapt, k_shared))
        for i in range(n_adapt):
            state, current, _, alpha = _step(state, current)
            warm[i] = state
            log_scale += (alpha - target_acceptance) / (i + 1) ** 0.6
            if i == n_adapt // 2 and i > 2 * k_shared:
                empirical = np.atleast_2d(np.cov(warm[:i + 1], rowvar=False))
                if np.all(np.isfinite(empirical)) and np.all(np.diag(empirical) > 0):
                    factor = _cholesky_or_diagonal(empirical)
                    log_scale = 0.0
            if check_cancel and check_cancel():
                cancelled = True
                break

    joint = np.tile(reference, (n_samples, 1))
    chi2 = np.empty(n_samples)
    lnprior_out = np.empty(n_samples)
    n_recorded = 0
    n_accepted = 0
    n_steps = n_samples * thin

    for i_step in range(1, n_steps + 1):
        if cancelled:
            break
        state, current, accepted, _ = _step(state, current)
        n_accepted += int(accepted)
        if i_step % thin == 0:
            # The recorded state is the shared vector plus a conditional draw of
            # every dataset's private parameters -- Rao-Blackwellised, so the
            # locals carry no autocorrelation of their own.
            draw = np.asarray(model.parameter_values, dtype=np.float64)
            draw[shared_idx] = state
            for indices, theta, chol in current[1]:
                draw[indices] = theta + chol @ rng.normal(size=theta.size)
            joint[n_recorded] = draw
            _, lp, c2 = cs.core.fitting.fit.lnprob_parts(
                parameter_values=list(draw), fit=fit, bounds=bounds, model=model
            )
            chi2[n_recorded] = c2
            lnprior_out[n_recorded] = lp
            n_recorded += 1
            if callback:
                callback(n_recorded, n_samples)
        if check_cancel and check_cancel():
            break

    model.parameter_values = list(reference)
    model.update_model()

    joint = joint[:n_recorded]
    chi2 = chi2[:n_recorded]
    lnprior_out = lnprior_out[:n_recorded]
    dof = float(model.n_points - model.n_free - 1.0)

    return {
        'chi2r': chi2 / dof,
        'lnprior': lnprior_out,
        'parameter_values': joint,
        'parameter_names': names,
        'chains': joint[np.newaxis, :, :],
        'acceptance_rate': n_accepted / float(max(1, n_steps)),
        'shared_names': [names[i] for i in shared_idx],
        'n_shared': int(k_shared),
        'collapsed': True,
    }


def _component_blocks(
        fit: cs.core.fitting.fit.Fit,
        model: cs.core.models.Model
) -> list:
    """Return ``(indices, blocks)`` per independent component of the fit.

    ``indices`` are the component's positions in the free-parameter vector and
    ``blocks`` its sampling blocks, both as index arrays, so each component can
    be handed straight to :func:`walk_mcmc_blocked`.
    """
    try:
        from chisurf.core.fitting import factorgraph
        graph = factorgraph.build_factor_graph(fit, model=model)
        components = graph.connected_components()
        if len(components) < 2:
            return []
        blocks_all = graph.sampling_blocks()
        out = []
        for component in components:
            indices = sorted(
                i for i in (graph.index_of(k) for k in component)
                if i is not None
            )
            blocks = [
                [graph.index_of(k) for k in b]
                for b in blocks_all if set(b) <= component
            ]
            blocks = [[i for i in b if i is not None] for b in blocks]
            blocks = [b for b in blocks if b]
            covered = sorted(i for b in blocks for i in b)
            if not indices or covered != indices:
                # A block straddling components would break the independence
                # argument the merge rests on; refuse rather than approximate.
                return []
            out.append((np.array(indices, dtype=int), blocks))
        return out
    except Exception as e:
        cs.logging.warning(f"independent-component sampling unavailable ({e})")
        return []


def _merge_components(
        results: list,
        reference: np.ndarray,
        chi2_0: float,
        lnprior_0: float,
        model: cs.core.models.Model,
        seed: int = None
) -> dict:
    """Stack per-component chains into one joint chain.

    Draws from independent components may be paired arbitrarily, so each
    component's chain is shuffled independently before being stacked -- without
    that, the ordering of the chains would show up as a spurious correlation
    between components that the posterior does not have.
    """
    rng = np.random.default_rng(seed)
    n_draws = min(r['parameter_values'].shape[0] for _, r in results)
    joint = np.tile(reference, (n_draws, 1))
    chi2 = np.zeros(n_draws, dtype=np.float64)
    lnprior = np.zeros(n_draws, dtype=np.float64)
    acceptance, sizes, block_sizes, block_acceptance = [], [], [], []

    dof = float(model.n_points - model.n_free - 1.0)
    for indices, r in results:
        order = rng.permutation(n_draws)
        joint[:, indices] = np.asarray(
            r['parameter_values'], dtype=np.float64
        )[:n_draws][order][:, indices]
        chi2 += np.asarray(r['chi2r'], dtype=np.float64)[:n_draws][order] * dof
        lnprior += np.asarray(r['lnprior'], dtype=np.float64)[:n_draws][order]
        acceptance.append(float(r['acceptance_rate']))
        sizes.append(int(indices.size))
        block_sizes.extend(r.get('block_sizes', []))
        block_acceptance.extend(np.atleast_1d(r.get('block_acceptance', [])))

    # Undo the (C-1)-fold double counting of the shared reference state.
    overlap = len(results) - 1
    chi2 -= overlap * float(chi2_0)
    lnprior -= overlap * float(lnprior_0)

    return {
        'chi2r': chi2 / dof,
        'lnprior': lnprior,
        'parameter_values': joint,
        'parameter_names': model.parameter_names,
        'chains': joint[np.newaxis, :, :],
        'acceptance_rate': float(np.mean(acceptance)) if acceptance else float('nan'),
        'block_sizes': block_sizes,
        'block_acceptance': np.asarray(block_acceptance, dtype=float),
        'n_components': len(results),
        'component_sizes': sizes,
    }


def _default_blocks(
        fit: cs.core.fitting.fit.Fit,
        dim: int,
        model: cs.core.models.Model = None
) -> list[np.ndarray]:
    """Return the factor graph's sampling blocks as parameter-vector indices.

    Falls back to a single block covering every parameter -- i.e. an ordinary
    full-vector random walk -- when no graph can be built.
    """
    try:
        from chisurf.core.fitting import factorgraph
        graph = factorgraph.build_factor_graph(
            fit, model=model if model is not None else fit.model
        )
        out = []
        for block in graph.sampling_blocks():
            idx = [graph.index_of(k) for k in block]
            idx = [i for i in idx if i is not None and 0 <= i < dim]
            if idx:
                out.append(np.array(sorted(idx), dtype=int))
        covered = sorted(int(i) for b in out for i in b)
        if covered == list(range(dim)):
            return out
        cs.logging.warning(
            "blocked sampling: factor graph covers %d of %d parameters; "
            "falling back to a single block", len(covered), dim
        )
    except Exception as e:
        cs.logging.warning(f"blocked sampling: no factor graph ({e})")
    return [np.arange(dim, dtype=int)]


def _ensemble_log_prob(parameter_values, fit, model=None, bounds=None, chi2max=np.inf):
    """Log-posterior plus ``(lnprior, chi2)`` for one walker state.

    Returning the two terms as sampler *blobs* keeps the data misfit and the
    prior separable in the stored chain instead of only their sum, so a chain
    can afterwards be reweighted under a different prior without resampling.

    Parameters
    ----------
    parameter_values : array_like
        Free-parameter vector to evaluate.
    fit : chisurf.core.fitting.fit.Fit
        Fit supplying the priors and the default bounds.
    model : chisurf.core.models.Model, optional
        Model to evaluate; defaults to ``fit.model``.
    bounds : list of tuple, optional
        Box bounds checked before the model is evaluated.
    chi2max : float, optional
        Hard cutoff on chi²; above it the log-likelihood is ``-inf``.

    Returns
    -------
    tuple of float
        ``(log_posterior, lnprior, chi2)``.
    """
    lnlike, lnpr, c2 = cs.core.fitting.fit.lnprob_parts(
        parameter_values=parameter_values,
        fit=fit,
        chi2max=chi2max,
        bounds=bounds,
        model=model,
    )
    if not np.isfinite(lnpr):
        return -np.inf, -np.inf, np.inf
    return lnlike + lnpr, lnpr, c2


def _ensemble_walker_start(
        model,
        nwalkers: int,
        std: float,
        random: np.random.Generator
) -> np.ndarray:
    """Spread walkers around the current parameter values, inside the bounds.

    An ensemble sampler learns its step size from the spread of its own
    walkers, so a badly chosen initial spread is not a cosmetic detail: all
    walkers on top of each other cannot move at all, and a spread of ``1e-3``
    applied to a parameter of order ``1e6`` is the same thing numerically.
    The scale is therefore taken from the bounded range where the parameter has
    one, and relative to the value otherwise.

    Parameters
    ----------
    model : chisurf.core.models.Model
        Model whose free parameters are sampled.
    nwalkers : int
        Number of walkers to place.
    std : float
        Relative spread used for parameters without finite bounds.
    random : numpy.random.Generator
        Random generator to draw the offsets from.

    Returns
    -------
    numpy.ndarray
        Initial walker positions, shape ``(nwalkers, ndim)``, each within the
        model's parameter bounds.
    """
    p0 = np.asarray(model.parameter_values, dtype=np.float64)
    ndim = len(p0)
    bounds = list(model.parameter_bounds)
    lower = np.array(
        [b[0] if b[0] is not None else -np.inf for b in bounds], dtype=np.float64
    )
    upper = np.array(
        [b[1] if b[1] is not None else np.inf for b in bounds], dtype=np.float64
    )

    spread = np.where(
        np.isfinite(lower) & np.isfinite(upper),
        (upper - lower) * 1e-4,
        np.where(np.abs(p0) > 1e-15, np.abs(p0) * std, std),
    )
    # A dimension in which every walker sits at the same value cannot be
    # sampled at all: the moves are built from differences between walkers, so
    # a direction with no spread has no component and the parameter stays at
    # its starting value for the whole run -- reported afterwards as a
    # delta-function posterior. It happens whenever the scale is taken
    # relative to something that is zero (a parameter at 0, or bounds that
    # coincide), so the relative scale is floored by the absolute one.
    spread = np.where(spread > 0.0, spread, std)
    start = p0[None, :] + spread[None, :] * random.standard_normal((nwalkers, ndim))
    return np.clip(start, lower, upper)


def _sample_ensemble(
        sampler,
        start: np.ndarray,
        fit,
        model,
        steps: int,
        thin: int,
        substeps: int = None,
        progress_bar=None,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None
) -> dict:
    """Drive an ensemble sampler in chunks and return its chain as a result dict.

    The run is broken into chunks of ``substeps`` so that a long sampling run
    stays cancellable and reports progress, and so that a partially finished
    chain can be written to disk by ``callback``.

    Parameters
    ----------
    sampler : chisurf.core.fitting.ensemble.EnsembleSampler or EnsembleSliceSampler
        Sampler to drive.
    start : numpy.ndarray
        Initial walker positions.
    fit : chisurf.core.fitting.fit.Fit
        Fit the sampler was built for; supplies the degrees of freedom.
    model : chisurf.core.models.Model
        Model being sampled; supplies the parameter names.
    steps : int
        Number of steps taken by each walker.
    thin : int
        Store only every ``thin``-th step.
    substeps : int, optional
        Steps per chunk. Defaults to the ``optimization.sampling.substeps``
        setting.
    progress_bar : object, optional
        Anything with ``setMaximum``/``setValue``.
    callback : callable, optional
        Called as ``callback(done, total, sampler=...)`` after every chunk.
    check_cancel : callable, optional
        Polled after every chunk; a true return ends the run early.

    Returns
    -------
    dict
        See :func:`ensemble_result`.
    """
    if substeps is None:
        try:
            substeps = int(
                cs.core.settings.cs_settings['optimization']['sampling'].get('substeps', 100)
            )
        except (KeyError, TypeError):
            substeps = 100

    if progress_bar is not None and hasattr(progress_bar, 'setMaximum'):
        progress_bar.setMaximum(steps)

    # ``run_mcmc`` counts its ``nsteps`` in *stored* states when thinning, so
    # the loop below is driven in stored states and only the progress reporting
    # is converted back to raw steps.
    thin = max(1, int(thin))
    n_stored = max(1, int(steps) // thin)
    stored_per_chunk = max(1, int(substeps) // thin)

    state = start
    current_stored = 0
    while current_stored < n_stored:
        n_to_run = min(stored_per_chunk, n_stored - current_stored)
        state = sampler.run_mcmc(
            state,
            nsteps=n_to_run,
            thin_by=thin,
            # The ensemble is checked for degeneracy once, on the way in. The
            # continuation chunks carry the sampler's own state, which no
            # longer has to look independent -- walkers legitimately collapse
            # together on a narrow posterior -- so re-checking there would
            # abort a healthy run halfway through.
            skip_initial_state_check=current_stored > 0,
        )
        current_stored += n_to_run
        current_step = current_stored * thin

        if progress_bar is not None:
            try:
                progress_bar.setValue(current_step)
            except Exception:
                pass

        if callback:
            try:
                callback(current_step, steps, sampler=sampler)
            except Exception:
                pass

        if check_cancel and check_cancel():
            break

    return ensemble_result(sampler, fit, model=model)


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def sample_ensemble(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        nwalkers: int = None,
        thin: int = 10,
        std: float = 1e-3,
        chi2max: float = np.inf,
        progress_bar = None,
        substeps: int = None,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        model: cs.core.models.Model = None,
        seed=None,
        stretch_scale: float = 2.0
) -> dict:
    """Sample the parameter space with an affine-invariant ensemble of walkers.

    Each walker is moved along the line joining it to another walker (the
    *stretch* move of :class:`chisurf.core.fitting.ensemble.EnsembleSampler`),
    so the proposal takes its scale and its correlations from the ensemble
    itself and no covariance has to be supplied. That makes this the sampler to
    reach for when nothing is known about the shape of the posterior, at the
    price of needing many walkers.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to sample.
    steps : int
        Number of steps taken by each walker.
    nwalkers : int, optional
        Number of walkers. Defaults to ``max(2 * n_free + 2, 10)``, which is
        the smallest ensemble that can span the parameter space.
    thin : int, optional
        Store only every ``thin``-th step.
    std : float, optional
        Relative spread of the initial walker positions for parameters without
        finite bounds.
    chi2max : float, optional
        Hard cutoff on chi²; above it a state is rejected outright.
    progress_bar : object, optional
        Anything with ``setMaximum``/``setValue``.
    substeps : int, optional
        Steps per chunk between progress reports and cancellation checks.
    callback : callable, optional
        Called as ``callback(done, total, sampler=...)`` after every chunk, used
        to write partial chains.
    check_cancel : callable, optional
        Polled after every chunk; a true return ends the run early.
    model : chisurf.core.models.Model, optional
        Model to sample; defaults to ``fit.model``.
    seed : int or numpy.random.Generator, optional
        Seed for a reproducible run.
    stretch_scale : float, optional
        The stretch parameter ``a``; larger values propose bolder moves.

    Returns
    -------
    dict
        See :func:`ensemble_result`.

    Notes
    -----
    ``steps`` counts the steps actually taken by each walker, so ``steps //
    thin`` states per walker are returned.
    """
    model = fit.model if model is None else model
    ndim = len(model.parameter_values)
    if nwalkers is None:
        nwalkers = max(2 * ndim + 2, 10)
    random = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)

    sampler = cs.core.fitting.ensemble.EnsembleSampler(
        nwalkers=int(nwalkers),
        ndim=ndim,
        log_prob_fn=_ensemble_log_prob,
        args=[fit],
        kwargs={'model': model, 'bounds': model.parameter_bounds, 'chi2max': chi2max},
        stretch_scale=stretch_scale,
        seed=random,
    )
    start = _ensemble_walker_start(model, int(nwalkers), std, random)
    return _sample_ensemble(
        sampler, start, fit, model, steps, thin,
        substeps=substeps, progress_bar=progress_bar,
        callback=callback, check_cancel=check_cancel,
    )


@cs.core.fitting.factorgraph.frozen('fit', 'model')
def sample_ensemble_slice(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        nwalkers: int = None,
        thin: int = 1,
        std: float = 1e-3,
        chi2max: float = np.inf,
        progress_bar = None,
        substeps: int = None,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None,
        model: cs.core.models.Model = None,
        seed=None,
        moves=None,
        tune: bool = True
) -> dict:
    """Sample the parameter space by ensemble *slice* sampling.

    Like :func:`sample_ensemble` the direction of each move comes from the other
    walkers, but the walker is then moved by one-dimensional slice sampling
    along that direction
    (:class:`chisurf.core.fitting.ensemble.EnsembleSliceSampler`): there is no
    accept/reject and no step size, and every walker moves at every step. Each
    step costs several model evaluations rather than one, and buys a much longer
    move -- the trade that pays off on a strongly correlated or badly scaled
    posterior, where the stretch move creeps.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to sample.
    steps : int
        Number of steps taken by each walker.
    nwalkers : int, optional
        Number of walkers. Defaults to ``max(2 * n_free + 2, 10)``.
    thin : int, optional
        Store only every ``thin``-th step. A slice step decorrelates far better
        than a stretch step, so thinning is rarely needed here.
    std : float, optional
        Relative spread of the initial walker positions for parameters without
        finite bounds.
    chi2max : float, optional
        Hard cutoff on chi²; above it a state is outside every slice.
    progress_bar : object, optional
        Anything with ``setMaximum``/``setValue``.
    substeps : int, optional
        Steps per chunk between progress reports and cancellation checks.
    callback : callable, optional
        Called as ``callback(done, total, sampler=...)`` after every chunk.
    check_cancel : callable, optional
        Polled after every chunk; a true return ends the run early.
    model : chisurf.core.models.Model, optional
        Model to sample; defaults to ``fit.model``.
    seed : int or numpy.random.Generator, optional
        Seed for a reproducible run.
    moves : object or list, optional
        Direction proposals, see
        :class:`chisurf.core.fitting.ensemble.EnsembleSliceSampler`.
    tune : bool, optional
        Adapt the length scale of the proposals. Adaptation stops on its own
        once the expansion statistics settle.

    Returns
    -------
    dict
        See :func:`ensemble_result`.
    """
    model = fit.model if model is None else model
    ndim = len(model.parameter_values)
    if nwalkers is None:
        nwalkers = max(2 * ndim + 2, 10)
    random = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)

    sampler = cs.core.fitting.ensemble.EnsembleSliceSampler(
        nwalkers=int(nwalkers),
        ndim=ndim,
        log_prob_fn=_ensemble_log_prob,
        args=[fit],
        kwargs={'model': model, 'bounds': model.parameter_bounds, 'chi2max': chi2max},
        moves=moves,
        tune=tune,
        seed=random,
    )
    start = _ensemble_walker_start(model, int(nwalkers), std, random)
    return _sample_ensemble(
        sampler, start, fit, model, steps, thin,
        substeps=substeps, progress_bar=progress_bar,
        callback=callback, check_cancel=check_cancel,
    )


def ensemble_result(
        sampler,
        fit: cs.core.fitting.fit.Fit,
        model: cs.core.models.Model = None
) -> dict:
    """Extract the flattened chain of an ensemble sampler as a result dict.

    Shared by :func:`sample_ensemble`, :func:`sample_ensemble_slice` and the
    intermediate-save callback in
    :func:`chisurf.core.fitting.fit.sample_fit`, so a partially written chain
    has exactly the same columns as a finished one.

    Parameters
    ----------
    sampler : chisurf.core.fitting.ensemble.EnsembleSampler or EnsembleSliceSampler
        Sampler to read the chain from.
    fit : chisurf.core.fitting.fit.Fit
        Fit the sampler was built for; supplies the degrees of freedom.
    model : chisurf.core.models.Model, optional
        Model that was sampled; supplies the parameter names. Defaults to
        ``fit.model``.

    Returns
    -------
    dict
        ``chi2r`` (data misfit only), ``lnprior``, ``parameter_values``,
        ``parameter_names``, the per-walker ``chains``, the
        ``acceptance_rate`` and the number of model evaluations
        ``n_evaluations``.

    Notes
    -----
    ``chains`` is one entry per *walker*. An ensemble sampler's walkers are not
    independent chains, so a split R-hat computed across them is optimistic --
    see :mod:`chisurf.core.fitting.diagnostics`. It is still worth reporting
    (a large value is conclusive) but the decisive comparison is across the
    independent runs that :func:`chisurf.core.fitting.fit.sample_fit` performs.
    """
    model = fit.model if model is None else model
    dof = float(model.n_points - model.n_free - 1.0)
    chain = sampler.get_chain(flat=True)
    blobs = sampler.get_blobs(flat=True)
    if blobs is None:
        # No blobs (e.g. a sampler built elsewhere): fall back to the summed
        # log-probability and report no prior contribution.
        lnpost = sampler.get_log_prob(flat=True)
        lnprior = np.zeros_like(lnpost)
        chi2 = -2.0 * lnpost
    else:
        blobs = np.asarray(blobs, dtype=np.float64).reshape(len(chain), -1)
        lnprior = blobs[:, 0]
        chi2 = blobs[:, 1]

    # get_chain() is (n_steps, n_walkers, ndim); the diagnostics want one row
    # per chain, so the walker axis comes first.
    per_walker = np.asarray(sampler.get_chain(), dtype=np.float64)
    per_walker = per_walker.transpose(1, 0, 2) if per_walker.ndim == 3 else None

    try:
        acceptance = float(np.mean(sampler.acceptance_fraction))
    except Exception:
        acceptance = float('nan')

    return {
        'chi2r': chi2 / dof,
        'lnprior': lnprior,
        'parameter_values': chain,
        'parameter_names': model.parameter_names,
        'chains': per_walker,
        'acceptance_rate': acceptance,
        'n_evaluations': int(getattr(sampler, 'n_evaluations', 0)),
    }
