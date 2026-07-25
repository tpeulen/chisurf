"""Parameter-space sampling backends (Metropolis and ensemble MCMC)."""
from __future__ import annotations

import typing

import numpy as np

import chisurf as cs
import chisurf.core.fitting


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
        target_acceptance: float = 0.3
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
    dim = fit.model.n_free
    state_initial = np.asarray(fit.model.parameter_values, dtype=np.float64)
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
    bounds = fit.model.parameter_bounds

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
            bounds=bounds
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
    dof = float(fit.model.n_points - fit.model.n_free - 1.0)

    return {
        'chi2r': chi2 / dof,
        'lnprior': lnprior,
        'parameter_values': parameter,
        'parameter_names': fit.model.parameter_names,
        'acceptance_rate': n_accepted / float(max(1, i_step)),
        # One chain, with its per-draw structure kept so that the split R-hat
        # and the autocorrelation time can be computed from it.
        'chains': parameter[np.newaxis, :, :],
    }


def _seed_block_covariances(
        fit: cs.core.fitting.fit.Fit,
        blocks: list[np.ndarray],
        state: np.ndarray,
        step_size: float
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

    Returns
    -------
    list of numpy.ndarray
        One ``(k, k)`` covariance per block.
    """
    full = None
    try:
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
        if cov_b is None:
            cov_b = np.diag(fallback[block] ** 2)
        out.append(cov_b)
    return out


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

    cov = _seed_block_covariances(fit, block_idx, state, step_size)
    factor = [_cholesky_or_diagonal(c) for c in cov]
    # The optimal scaling of a random-walk Metropolis falls with the dimension
    # of the move, so each block gets the target appropriate to its own size.
    log_scale = [0.0] * len(block_idx)
    target = [
        0.44 if idx.size == 1 else max(0.234, 0.44 / np.sqrt(idx.size))
        for idx in block_idx
    ]

    parts = _lnprob(state)
    accepted = np.zeros(len(block_idx), dtype=np.int64)
    proposed = np.zeros(len(block_idx), dtype=np.int64)

    def _sweep(current, current_parts, adapt_step=None):
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
            if adapt_step is not None:
                # Robbins-Monro on the log scale: shrink while proposals are
                # rejected too often, widen while they are accepted too often.
                log_scale[b] += (alpha - target[b]) / adapt_step
        return current, current_parts

    cancelled = False
    if n_adapt is None:
        n_adapt = min(2000, max(200, (n_samples * thin) // 2))
    n_adapt = max(0, int(n_adapt))

    if n_adapt > 0:
        warmup = np.empty((n_adapt, dim))
        n_warm = 0
        for i in range(n_adapt):
            state, parts = _sweep(state, parts, adapt_step=(i + 1) ** 0.6)
            warmup[i] = state
            n_warm += 1
            # Once the chain has explored, the empirical covariance of where it
            # has been beats any a-priori guess -- including the curvature at
            # the optimum, which only describes the posterior locally.
            if i == n_adapt // 2 and n_warm > 2 * dim:
                visited = warmup[:n_warm]
                for b, idx in enumerate(block_idx):
                    empirical = np.cov(visited[:, idx], rowvar=False)
                    empirical = np.atleast_2d(empirical)
                    if np.all(np.isfinite(empirical)) and np.all(np.diag(empirical) > 0):
                        factor[b] = _cholesky_or_diagonal(empirical)
                        log_scale[b] = 0.0
            if check_cancel and check_cancel():
                cancelled = True
                break
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


def sample_emcee(
        fit: cs.core.fitting.fit.Fit,
        steps: int,
        nwalkers: int,
        thin: int = 10,
        std: float = 1e-3,
        chi2max: float = np.inf,
        progress_bar = None,
        substeps: int = None,
        callback: typing.Callable = None,
        check_cancel: typing.Callable = None
) -> dict:
    """Sample the parameter space by emcee using a number of 'walkers'.

    :param fit: the fit to be samples
    :param steps: the number of steps of each walker
    :param thin: an integer (only every ith step is saved)
    :param nwalkers: the number of walkers
    :param chi2max: maximum allowed chi2
    :param std: the standard deviation of the parameters used to randomize the initial set of the walkers
    :return: a dict with the *data* ``chi2r``, the ``lnprior``, the sampled
        ``parameter_values`` and the ``parameter_names``

    Notes
    -----
    ``steps`` counts the steps actually taken by each walker, so
    ``steps // thin`` states per walker are returned. Note that the underlying
    ensemble sampler counts ``nsteps`` in *stored* states when it thins, hence
    the loop below iterates in stored states rather than in raw steps.
    """
    # Imported lazily so that a missing ``emcee`` only disables ensemble
    # sampling rather than breaking the whole fitting stack (and, transitively,
    # every model widget that imports it).
    import emcee

    if substeps is None:
        try:
            substeps = int(cs.core.settings.cs_settings['optimization']['sampling'].get('substeps', 100))
        except (KeyError, TypeError):
            substeps = 100

    model = fit.model
    ndim = fit.n_free  # Number of free parameters to be sampled (number of dimensions)
    kw = {
        'bounds': fit.model.parameter_bounds,
        'chi2max': chi2max
    }

    def _log_prob(parameter_values, fit, bounds=None, chi2max=np.inf):
        """Log-posterior plus ``(lnprior, chi2)`` blobs for one walker state.

        Returning the two terms as emcee *blobs* keeps the data misfit and the
        prior separable in the stored chain, instead of only their sum.
        """
        lnlike, lnpr, c2 = cs.core.fitting.fit.lnprob_parts(
            parameter_values=parameter_values,
            fit=fit,
            chi2max=chi2max,
            bounds=bounds
        )
        if not np.isfinite(lnpr):
            return -np.inf, -np.inf, np.inf
        return lnlike + lnpr, lnpr, c2

    sampler = emcee.EnsembleSampler(
        nwalkers=nwalkers,
        ndim=ndim,
        log_prob_fn=_log_prob,
        args=[fit],
        kwargs=kw
    )
    # Initialize walkers with a robust standard deviation estimate
    p0 = np.array(model.parameter_values)
    bounds = np.array(kw['bounds'])
    std_input = std # input float, e.g., 1e-3
    std_vec = np.zeros(ndim)

    for i in range(ndim):
        lb, ub = bounds[i]
        # 1. Use width of narrow bounds as scale if finite
        if lb is not None and ub is not None and np.isfinite(lb) and np.isfinite(ub):
            # Use 1/1000th of the range as jitter
            std_vec[i] = (ub - lb) * 1e-4
        # 2. Else use relative scale if parameter is non-zero
        elif abs(p0[i]) > 1e-15:
            std_vec[i] = abs(p0[i]) * std_input
        # 3. Last fallback: use absolute input value
        else:
            std_vec[i] = std_input

    if progress_bar is not None and hasattr(progress_bar, 'setMaximum'):
        progress_bar.setMaximum(steps)

    previous_state = []
    for _ in range(nwalkers):
        p = p0 + std_vec * np.random.randn(ndim)
        # Ensure initial state stays within user-provided bounds.
        # Clip lb if lb > -inf and ub if ub < inf.
        for j in range(ndim):
            lb, ub = bounds[j]
            if lb is not None and np.isfinite(lb):
                p[j] = max(p[j], lb)
            if ub is not None and np.isfinite(ub):
                p[j] = min(p[j], ub)
        previous_state.append(p)

    # ``run_mcmc`` counts ``nsteps`` in stored states when ``thin_by`` is used,
    # so the loop below is driven in stored states and only the progress
    # reporting is converted back to raw steps.
    thin = max(1, int(thin))
    n_stored = max(1, int(steps) // thin)
    stored_per_chunk = max(1, int(substeps) // thin)

    current_stored = 0
    while current_stored < n_stored:
        n_to_run = min(stored_per_chunk, n_stored - current_stored)
        previous_state = sampler.run_mcmc(
            previous_state,
            nsteps=n_to_run,
            thin_by=thin,
            skip_initial_state_check=True
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

    return emcee_result(sampler, fit)


def emcee_result(sampler, fit: cs.core.fitting.fit.Fit) -> dict:
    """Extract the flattened chain of an ensemble sampler as a result dict.

    Shared by :func:`sample_emcee` and the intermediate-save callback in
    :func:`chisurf.core.fitting.fit.sample_fit`, so a partially written chain
    has exactly the same columns as a finished one.

    Parameters
    ----------
    sampler : emcee.EnsembleSampler
        Sampler to read the chain from.
    fit : chisurf.core.fitting.fit.Fit
        Fit the sampler was built for; supplies the degrees of freedom and the
        parameter names.

    Returns
    -------
    dict
        ``chi2r`` (data misfit only), ``lnprior``, ``parameter_values``,
        ``parameter_names``, the per-walker ``chains`` and the
        ``acceptance_rate``.

    Notes
    -----
    ``chains`` is one entry per *walker*. An ensemble sampler's walkers are not
    independent chains, so a split R-hat computed across them is optimistic --
    see :mod:`chisurf.core.fitting.diagnostics`. It is still worth reporting
    (a large value is conclusive) but the decisive comparison is across the
    independent runs that :func:`chisurf.core.fitting.fit.sample_fit` performs.
    """
    model = fit.model
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
    }
