"""MCMC over the C++ objective graph — the four-crossing sampler path.

The samplers in :mod:`chisurf.core.fitting.sample` drive a Python
``_lnprob`` once per proposal, which for a graph-eligible fit means
hundreds of thousands of SWIG crossings per run for arithmetic the graph
already does in C++. ``IMP.bff.MCMCSampler`` is the 1:1 port of those
samplers (stretch, differential evolution, blocked Metropolis) over the
same ``Port``/``Node`` runtime the optimiser uses, so a fit whose
objective builds as a graph can sample entirely in C++.

The boundary contract, set by the owner (2026-09-02): the SWIG boundary
is crossed only at

* the **begin** — the graph is built and the sampler configured;
* **state updates** — a progress callback once per segment;
* **intermediate saving** — the partial chain read off once per segment;
* the **end** — the finished chain, log-priors and chi-squares.

Per *step* nothing crosses. That is delivered by driving
:meth:`MCMCSampler.run` in segments from Python — a second ``run()``
continues the chain where the first left off, byte-identically to one
long call — rather than by a per-step observer, which would be a
crossing per step by construction. Cancellation is polled between
segments, exactly as the chunked ensemble driver already does it.

A fit the graph refuses samples in Python as before: this module returns
``None`` and the caller falls through to its own loop. The refusal path
must never be a C++ loop around a Python callback — measured on the
optimiser as a regression, not a speed-up.

Two semantic notes, both deliberate:

* **Priors ride the ports.** A distribution prior mirrors its JSON spec
  onto the parameter's own port; the same spec is copied onto the
  private graph port here, and the C++ sampler evaluates it kind for
  kind. A *callback* prior is runtime-only Python and has no spec — a
  fit carrying one is refused (falls back to Python), never silently
  sampled without its prior.
* **Chain parity is statistical, not stream.** The C++ sampler draws
  from ``std::mt19937_64``; the Python samplers from numpy generators.
  Same seed does not mean same chain across the two implementations,
  and a test asserting that would fail by construction. Moments and
  acceptance are the contract.
"""

from __future__ import annotations

import typing

import numpy as np

import chisurf as cs
import chisurf.core.fitting.minimizer

try:
    import IMP.bff as _bff

    if not hasattr(_bff, "MCMCSampler"):
        _bff = None
except Exception:
    _bff = None


def have_sampler() -> bool:
    """Whether the C++ sampler is importable in this environment."""
    return _bff is not None


def _kernel_entry(algorithm: str) -> dict:
    """The IMP.bff registry entry of a sampler kernel (category ``sampler``)."""
    entries = _bff.registry("sampler") if hasattr(_bff, "registry") else {}
    if algorithm in entries:
        return entries[algorithm]
    for entry in entries.values():
        if algorithm in entry.get("aliases", ()):
            return entry
    return {}


# Warm-up defaults come from the kernel's registry entry, where the C++ side
# declares them. They must still be set *explicitly* because the C++ derives
# its default from the first run() call's n_steps -- which under segmented
# driving is the segment length, not the run length.
def _default_n_adapt(algorithm: str, steps: int) -> int:
    rule = _kernel_entry(algorithm).get("default_warmup") or {}
    if rule.get("rule") == "clip":
        return min(
            int(rule["max"]), max(int(rule["min"]), int(steps) // int(rule.get("divisor", 1)))
        )
    return int(rule.get("value", 0))


def _seed_int(seed) -> int:
    """A C++-consumable seed that keeps every existing reproducibility
    contract: an int is used as given, a Generator contributes one draw,
    and no seed draws from numpy's global stream so ``np.random.seed``
    still governs the run.
    """
    if isinstance(seed, (int, np.integer)):
        return int(seed) & 0xFFFFFFFF
    if isinstance(seed, np.random.Generator):
        return int(seed.integers(2**32))
    return int(np.random.randint(2**32))


def _substeps(substeps) -> int:
    if substeps is not None:
        return max(1, int(substeps))
    try:
        return max(
            1, int(cs.core.settings.cs_settings["optimization"]["sampling"].get("substeps", 100))
        )
    except (KeyError, TypeError):
        return 100


def sample_via_graph(
    fit,
    model,
    algorithm: str,
    steps: int,
    thin: int = 1,
    chi2max: float = np.inf,
    temp: float = 1.0,
    seed=None,
    callback: typing.Callable = None,
    check_cancel: typing.Callable = None,
    n_adapt: int = None,
    substeps: int = None,
    # per-algorithm tunables; None keeps the C++ (== chisurf) default
    step_size: float = None,
    nwalkers: int = None,
    stretch_scale: float = None,
    walker_start_std: float = None,
    n_chains: int = None,
    jitter: float = None,
    snooker: float = None,
    blocks: list[list[int]] = None,
    use_curvature: bool = True,
) -> dict | None:
    """Sample *fit* through the C++ graph, or return ``None`` to refuse.

    Returns the same dict the Python samplers return -- ``chi2r``,
    ``lnprior``, ``parameter_values``, ``parameter_names``, ``chains``,
    ``acceptance_rate`` plus per-algorithm extras -- so no consumer of a
    sampling result can tell which side produced it.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        The fit; supplies data, window, mask and noise model to the graph.
    model : chisurf.core.models.Model
        The model whose free parameters are sampled.
    algorithm : str
        ``"stretch"``, ``"de"`` or ``"metropolis"`` (canonical names).
    steps, thin, chi2max, temp, seed, callback, check_cancel
        Exactly the Python samplers' contract. ``callback`` is called once
        per segment as ``callback(n_recorded, n_target)``; when it accepts
        a ``result`` keyword it also receives the partial result dict for
        intermediate saving.
    n_adapt : int, optional
        Warm-up steps; the per-algorithm default when ``None``.
    substeps : int, optional
        Steps per segment; ``optimization.sampling.substeps`` when ``None``.
    blocks : list of list of int, optional
        An explicit block partition for ``"metropolis"``.

    Returns
    -------
    dict or None
        The result, or ``None`` when the fit cannot run on the graph --
        the caller then runs its own Python loop.
    """
    if _bff is None or model is None or steps <= 0:
        return None

    built = cs.core.fitting.minimizer.graph_objective(fit, model, allow_priors=True)
    if built is None:
        return None
    m, free = built
    surface = getattr(m, "_sampler_surface", None)
    if surface is None:
        return None  # the director fallback: not a graph
    node, ports, out_name = surface

    # Priors: copy each free parameter's serialisable spec onto its
    # private graph port. A live prior with no spec is a callback prior
    # the C++ cannot evaluate -- refuse rather than drop it silently.
    for p, port in zip(free, ports):
        own_port = getattr(p, "_port", None)
        spec = getattr(own_port, "prior", None) if own_port is not None else None
        if spec is not None:
            port.prior = spec
        elif getattr(p, "_prior", None) is not None:
            return None  # runtime-only (callback/product) prior

    lower = np.empty(len(free))
    upper = np.empty(len(free))
    for i, (lb, ub) in enumerate(model.parameter_bounds):
        lower[i] = -np.inf if lb is None else float(lb)
        upper[i] = np.inf if ub is None else float(ub)

    s = _bff.MCMCSampler(algorithm, _seed_int(seed))
    s.set_parameter_ports(ports)
    s.set_objective(node, out_name)
    s.set_bounds(list(lower), list(upper))
    s.set_temp(float(temp))
    if np.isfinite(chi2max):
        s.set_chi2max(float(chi2max))
    s.set_n_adapt(int(n_adapt) if n_adapt is not None else _default_n_adapt(algorithm, int(steps)))
    if step_size is not None:
        s.set_step_size(float(step_size))
    if nwalkers is not None:
        s.set_number_of_walkers(int(nwalkers))
    if stretch_scale is not None:
        s.set_stretch_scale(float(stretch_scale))
    if walker_start_std is not None:
        s.set_walker_start_std(float(walker_start_std))
    if n_chains is not None:
        s.set_number_of_chains(int(n_chains))
    if jitter is not None:
        s.set_jitter(float(jitter))
    if snooker is not None:
        s.set_snooker(float(snooker))
    if blocks:
        flat = [int(i) for block in blocks for i in block]
        sizes = [len(block) for block in blocks]
        s.set_blocks(flat, sizes)
    if (
        _kernel_entry(algorithm).get("uses_covariance_seed")
        and use_curvature
        and not _kernel_entry(algorithm).get("requires_gradient")
    ):
        # The curvature at the optimum is very nearly the ideal
        # preconditioner (chisurf's _seed_block_covariances), and without it
        # a strongly correlated posterior mixes so badly that 4000 steps
        # under-estimate its width several-fold. One crossing, at begin.
        # walk_mcmc passes use_curvature=False: a *diagonal* proposal is
        # that sampler's documented contract, and the blocked sampler's
        # measured mixing advantage over it is pinned by a test.
        full = _curvature_covariance(fit, model, len(free))
        if full is not None:
            s.set_proposal_covariance([list(map(float, row)) for row in full])

    # The graph and its keepalive tuple must outlive the sampler's use of
    # the node; parking the minimizer on the sampler object does that.
    s._graph_owner = m

    # ------------------------------------------------------------- run
    # Segments: `substeps` *recorded* states each, so thinning does not
    # shrink a segment's wall-clock share. Each pass crosses the boundary
    # once for run() and, when the caller wants progress or a partial
    # save, once more for the reads -- never per step.
    steps = int(steps)
    thin = max(1, int(thin))
    seg_states = _substeps(substeps)
    n_target = steps // thin
    done_steps = 0
    try:
        while done_steps < steps:
            seg = min(seg_states * thin, steps - done_steps)
            s.run(int(seg), thin)
            done_steps += seg
            if callback is not None:
                recorded = int(s.iteration)
                try:
                    callback(recorded, n_target, result=_result(s, model, algorithm))
                except TypeError:
                    callback(recorded, n_target)
            if check_cancel is not None and check_cancel():
                break
    except Exception:
        # A graph that fails mid-run (a MCMCSamplerConfigurationError, an
        # objective that stopped evaluating) must not kill sampling
        # outright when the Python loop can still do the job.
        if int(getattr(s, "iteration", 0)) == 0:
            return None
        raise

    return _result(s, model, algorithm)


def _curvature_covariance(fit, model, n: int) -> np.ndarray | None:
    """The fit's covariance scattered into full free-vector coordinates.

    Mirrors the `full` half of ``sample._seed_block_covariances``:
    ``covariance_matrix`` drops parameters the model does not respond to, so
    the submatrix is scattered back by its own index list. The indices only
    mean anything for ``fit.model`` -- for any other model (a group's global
    model) the seed is skipped and warm-up adaptation supplies the shape.
    """
    try:
        if model is not fit.model:
            return None
        cov, used = fit.covariance_matrix
        cov = np.asarray(cov, dtype=np.float64)
        used = list(used)
        if cov.ndim != 2 or cov.shape[0] != len(used) or cov.shape[0] != cov.shape[1]:
            return None
        full = np.zeros((n, n), dtype=np.float64)
        idx = np.array(used, dtype=int)
        keep = idx < n
        idx = idx[keep]
        sub = cov[np.ix_(keep.nonzero()[0], keep.nonzero()[0])]
        full[np.ix_(idx, idx)] = sub
        if not np.any(np.diag(full) > 0.0):
            return None
        return full
    except Exception:
        return None


def _result(sampler, model, algorithm: str) -> dict:
    """The Python samplers' result dict, read off the C++ sampler.

    Usable mid-run (for intermediate saving) as well as at the end: every
    read is of the recorded chain so far.
    """
    chain = np.asarray(sampler.chain, dtype=float)
    if chain.ndim != 2:
        chain = chain.reshape(-1, int(sampler.get_number_of_parameters()))
    n_walkers = max(1, len(sampler.walkers))
    n_rec = chain.shape[0] // n_walkers if n_walkers else 0
    ndim = chain.shape[1] if chain.size else len(model.parameter_names)

    dof = float(model.n_points - model.n_free - 1.0)
    chi2 = np.asarray(sampler.chi2, dtype=float)

    result = {
        "chi2r": chi2 / dof,
        "lnprior": np.asarray(sampler.lnprior, dtype=float),
        "parameter_values": chain,
        "parameter_names": list(model.parameter_names),
        "acceptance_rate": float(sampler.acceptance_rate),
        # The C++ flat order is walker-major within a step (chisurf's
        # flat=True reshape), so per-walker chains for the split R-hat
        # are one reshape + transpose away.
        "chains": (
            chain.reshape(n_rec, n_walkers, ndim).transpose(1, 0, 2)
            if n_rec * n_walkers == chain.shape[0] and chain.size
            else chain[np.newaxis, :, :]
        ),
        "n_evaluations": int(sampler.n_evaluations),
    }
    entry = _kernel_entry(algorithm)
    if entry.get("population") == "chains":
        result["n_chains"] = n_walkers
    if entry.get("uses_blocks"):
        rates = np.asarray(sampler.block_acceptance_rates, dtype=float)
        if rates.size:
            result["block_acceptance"] = rates
            result["block_sizes"] = list(sampler.get_block_sizes())
    return result
