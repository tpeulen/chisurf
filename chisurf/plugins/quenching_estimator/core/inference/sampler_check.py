"""The optional MCMC check of the Laplace error bars (what the prototype's cell 40 ran).

The Laplace error bars assume the best fit sits in one smooth valley. The check explores the
same posterior with a real sampler and compares: an affine-invariant **stretch-move ensemble**
(the sampler behind chisurf's ``ensemble``/``emcee`` entry in
:data:`chisurf.core.fitting.sample.SAMPLERS`; the prototype used IMP.bff's ``MCMCSampler("stretch")``),
started around the best fit, first half of every run discarded as burn-in. Exactly as in the
prototype (``LocalPosterior``, notebook cell 36), the posterior sampled is the **data set's
own**: its free parameters, the titration slopes and the model error held at the joint fit's
best values, the Gaussian likelihood on the inliers and the stickiness ridge prior.

The comparison (cell 49's table): per fitted parameter the best fit and the 68 % interval of
both methods in natural units, how much of the narrower interval the two share, and a verdict
("agree" at half or more). The result is plain numbers (a stage's ``numbers``/``plots``, no
declared table), because every column of a declared table needs a vocabulary term -- and none
exists for a sampler comparison yet.

The declared setting (``settings/analysis/fit_parameters.yaml: sampler_check``) is off by
default; :class:`~.stages.Analysis` turns it on with ``sampler_check=True``, a dict of options,
or ``fit_overrides={"sampler_check": {"enabled": True, ...}}``, and runs it for the blocks a
stage declares under ``sampler_check:`` (stage A: the AF488 data set, as in cell 49).
"""

from __future__ import annotations

import numpy as np

from . import graph_fit as _gf

__all__ = ["block_posterior", "interval_overlap", "interval_verdict", "resolve",
           "sampler_check", "text"]

#: Share of the narrower 68 % interval the two methods must share to agree.
AGREE_ABOVE = 0.5


def block_posterior(view):
    """One data set's posterior with the slopes and the model error held at the best fit.

    Parameters
    ----------
    view : graph_fit.BlockResult

    Returns
    -------
    tuple
        ``(log_prob, names, lo, hi, best)``: the log posterior of a free-parameter vector
        (``-inf`` outside the bounds), the internal names in vector order, the bounds and the
        best fit.
    """
    block = view.block
    names = [n for n in block.free if n != "ln_model_error"]
    index = [block.free.index(n) for n in names]
    lo, hi = block.lo[index], block.hi[index]
    best = block.best_x[index]
    K = view.graph.thetas(view.graph.u)[1]          # the slopes at the joint fit's best
    s = block.s
    use = block.use
    tau_x = block.tau_x
    sigma = np.sqrt(block.sigma_meas ** 2 + s ** 2)
    groups, ridge_sd = block.groups, block.ridge_sd

    def log_prob(x):
        if np.any(x < lo) or np.any(x > hi):
            return -np.inf
        full = block.best_x.copy()
        full[index] = x
        th = block.theta(full, K, s)
        z = ((block.predictions(th) - tau_x) / sigma)[use]
        ridge = _gf.ridge(th, groups, ridge_sd)
        value = -0.5 * float(z @ z) - 0.5 * float(ridge @ ridge)
        return float(value) if np.isfinite(value) else -1e300

    return log_prob, names, lo, hi, best


def interval_overlap(first, second):
    """The share of the narrower 68 % interval the two have in common.

    Parameters
    ----------
    first, second : tuple
        ``(low, high)`` of each interval, in comparable units (log for log-scale parameters).

    Returns
    -------
    float
        In [0, 1]; 0 when an interval is empty or the two are disjoint.
    """
    overlap = min(first[1], second[1]) - max(first[0], second[0])
    smaller = min(first[1] - first[0], second[1] - second[0])
    if not np.isfinite(smaller) or smaller <= 0.0:
        return 0.0
    return float(np.clip(overlap, 0.0, None) / smaller)


def interval_verdict(overlap, agree_above=AGREE_ABOVE):
    """``"agree"`` when the intervals share at least *agree_above* of the narrower one."""
    return "agree" if overlap >= agree_above else "mismatch"


def resolve(flag=None, declared=None):
    """The check's options from the :class:`~.stages.Analysis` flag and the declared setting.

    Parameters
    ----------
    flag : None, bool or dict, optional
        None follows the declaration's ``enabled``; a dict adds options over the declared
        ones (on unless it sets ``enabled: false``); True forces the check on with the
        declared numbers.
    declared : dict, optional
        The declared ``sampler_check`` setting.

    Returns
    -------
    dict or None
        The options to run with, or None when the check is off.
    """
    declared = dict(declared or {})
    if flag is None:
        return declared if declared.get("enabled") else None
    if isinstance(flag, dict):
        if not flag.get("enabled", True):
            return None
        return {**declared, **flag, "enabled": True}
    return {**declared, "enabled": True} if flag and declared else None


def sampler_check(view, steps=None, runs=None, walkers=None, start_spread=None,
                  first_seed=None, cancel=None, progress=None):
    """The cell-40-style comparison of one data set's MCMC and Laplace 68 % intervals.

    Parameters
    ----------
    view : graph_fit.BlockResult
        A view of a solved graph (its block's posterior is sampled).
    steps, runs, walkers : int, optional
        Steps per walker, independent runs and walkers per run; the declared numbers by
        default. Burn-in is the first half of every run.
    start_spread : float, optional
        Spread of the walker starts around the best fit, as a share of each parameter's range
        (the declared ``start_spread`` by default).
    first_seed : int, optional
        Seed of the first run (the declared ``first_seed`` by default); run *k* uses
        ``first_seed + k``, so a run is reproducible.
    cancel : callable, optional
        Checked between runs; raises :class:`~..tasks.CancelledError`.
    progress : callable, optional
        ``progress(done, total, message)`` after each run.

    Returns
    -------
    dict
        ``block``, ``dye``, ``sampler``, ``steps``, ``runs``, ``walkers``, ``burn_in``,
        ``n_samples``, ``acceptance``, ``parameters`` (rows of ``parameter``, ``best_fit``,
        ``laplace_low_68``, ``laplace_high_68``, ``sampler_low_68``, ``sampler_high_68``,
        ``overlap``, ``verdict``), ``mismatches``, ``verdict``.
    """
    fs = view.graph.settings
    declared = fs["sampler_check"]
    steps = int(declared["steps"] if steps is None else steps)
    runs = int(declared["runs"] if runs is None else runs)
    walkers = int(declared["walkers"] if walkers is None else walkers)
    if start_spread is None:
        start_spread = float(declared.get("start_spread", 0.002))
    if first_seed is None:
        first_seed = int(declared.get("first_seed", 100))

    log_prob, names, lo, hi, best = block_posterior(view)
    specs = _gf._spec_map(fs)
    # chisurf's emcee: the affine-invariant stretch-move ensemble sampler (lazy import keeps
    # the inference stack import-light, like describe_graph's IMP.bff import).
    from chisurf.core.fitting.ensemble import EnsembleSampler

    chains, acceptances = [], []
    for k in range(runs):
        _gf._check(cancel)
        seed = first_seed + k
        start = np.clip(best + start_spread * (hi - lo)
                        * np.random.default_rng(seed).standard_normal((walkers, len(names))),
                        lo + 1e-9 * (hi - lo), hi - 1e-9 * (hi - lo))
        sampler = EnsembleSampler(nwalkers=walkers, ndim=len(names), log_prob_fn=log_prob,
                                  seed=seed)
        sampler.run_mcmc(start, steps)
        chains.append(sampler.get_chain(discard=steps // 2, flat=True))
        acceptances.append(float(np.mean(sampler.acceptance_fraction)))
        if progress:
            progress(k + 1, runs, f"{view.label}: sampler run {k + 1}/{runs}")
    samples = np.concatenate(chains)

    estimates = {str(r["parameter"]): r for r in view.estimates}
    rows = []
    for i, name in enumerate(names):
        spec = specs[name]
        e = estimates[spec.label]
        q = np.percentile(samples[:, i], [16.0, 84.0])
        s_low, s_high = float(spec.to_natural(q[0])), float(spec.to_natural(q[1]))
        to_internal = np.log if spec.log else (lambda v: v)
        laplace = (to_internal(e["low_68"]), to_internal(e["high_68"]))
        sampler_interval = (to_internal(s_low), to_internal(s_high))
        overlap = interval_overlap(laplace, sampler_interval)
        rows.append(dict(parameter=spec.label, best_fit=float(e["value"]),
                         laplace_low_68=float(e["low_68"]), laplace_high_68=float(e["high_68"]),
                         sampler_low_68=s_low, sampler_high_68=s_high,
                         overlap=overlap, verdict=interval_verdict(overlap)))
    mismatches = [r["parameter"] for r in rows if r["verdict"] != "agree"]
    return dict(
        block=view.label, dye=view.dye, sampler="ensemble (stretch move)",
        steps=steps, runs=runs, walkers=walkers, burn_in=steps // 2,
        n_samples=int(len(samples)), acceptance=float(np.mean(acceptances)),
        parameters=rows, mismatches=mismatches,
        verdict="agree" if not mismatches else "mismatch: " + ", ".join(mismatches),
    )


def text(result):
    """Plain words about a check: whether the sampler saw Laplace's error bars.

    Parameters
    ----------
    result : dict
        :func:`sampler_check`'s result.

    Returns
    -------
    str
    """
    head = (f"MCMC check of {result['block']}: {result['n_samples']} samples "
            f"({result['runs']} run(s) x {result['walkers']} walkers x {result['steps']} steps, "
            f"first half discarded, acceptance {100 * result['acceptance']:.0f} %) against the "
            f"Laplace error bars.")
    if result["verdict"] == "agree":
        return (head + f" Verdict: {result['verdict']} -- the 68 % intervals share at least "
                f"{100 * AGREE_ABOVE:.0f} % of the narrower interval for every fitted "
                f"parameter, so the valley is as smooth as Laplace assumes.")
    return (head + f" Verdict: {result['verdict']}: "
            + ", ".join(result["mismatches"])
            + " -- there the posterior is not the one smooth valley the Laplace approximation "
              "assumes (the estimates' notes say how well the data determine each parameter).")
