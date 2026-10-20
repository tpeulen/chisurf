"""The Bayesian graph fit: titration slopes -> kQ of every dye -> the lifetimes on the protein.

One *block* is the measured lifetimes of one dye (one or both solvents) with the site model of
every measured site. A *graph* joins blocks through the titration slopes K_SV they read: a
dye's contact rates kQ are scaled from the reference dye's by the ratio of the titrations
(:func:`~.kq_scaling.kq_vector`), so every non-reference block reads its own dye's and the
reference dye's slopes, and the slopes carry their titration posterior as a Gaussian prior.

The solve has three steps, as in the MalE prototype (notebook chapter 6):

1. **Robust search** per block: ``n_starts`` L-BFGS-B searches from uniform random starts of the
   Student-t (nu = 3) log posterior with the model error s free and the stickiness ridge prior.
   The best search sets the model error s (the root of ``median(r^2/(sigma^2 + s^2)) = 0.455``,
   the median of chi-square(1); never below the floor) and the outlier mask (``|r| > 3`` error
   bars), and s is refined on the inliers.
2. **Joint fit**: all blocks and the slopes together, Gaussian likelihood on the inliers, the
   ridge prior and the slope prior as residuals, every parameter scaled to the unit box.
3. **Laplace**: the covariance of the unit-box parameters is the eigen-clipped inverse of
   ``J^T J`` (no direction gets more than ``max_variance``); intervals are the best fit +- one
   sd, mapped back. Prediction errors propagate through the same covariance. Leave one site
   out is one Newton step on the curvature without that site's residuals.

The quench-scale *profile* comes in two forms: :func:`laplace_samples` draws from the Laplace
Gaussian (what the prototype plotted), and :func:`profile_likelihood` refits the block's
sub-graph at fixed scale values (a real profile).

Optimisers come from :mod:`chisurf.core.math.numerics` (IMP.bff's L-BFGS-B, MINPACK least
squares, Brent root); no scipy. Every number is declared in
``settings/analysis/fit_parameters.yaml``. Theory: ``docs/concepts/quenching_inference.md``.
"""

from __future__ import annotations

import concurrent.futures as _futures
import contextlib as _contextlib
import multiprocessing as _mp
import os
import sys as _sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from chisurf.core.math import numerics as _numerics

from ..tasks import CancelledError
from . import columns as _columns
from . import kq_scaling as _kq
from . import site_model as _site_model

#: The fit declaration.
FIT_PARAMETERS = _columns.ANALYSIS_SETTINGS_DIR / "fit_parameters.yaml"

#: The declared result tables (estimates, predictions, leave-one-out, ...).
RESULT_COLUMNS = _columns.ANALYSIS_SETTINGS_DIR / "result_columns.yaml"


# --------------------------------------------------------------------------------------------
# settings


def settings(preset=None, overrides=None, path=FIT_PARAMETERS):
    """The declared fit settings, with a preset and explicit overrides applied.

    Parameters
    ----------
    preset : str, optional
        A key of the declaration's ``presets`` (``"full"``, ``"quick"``); none by default.
    overrides : dict, optional
        Keys of ``settings`` to replace (applied after the preset).
    path : str or pathlib.Path, optional
        Declaration file.

    Returns
    -------
    dict
        A fresh copy; changing it does not change the declaration.

    Raises
    ------
    KeyError
        For an unknown preset or an override of an undeclared key.
    """
    doc = _columns.declaration(path)
    out = _deep_copy(doc["settings"])
    if preset is not None:
        presets = doc.get("presets") or {}
        if preset not in presets:
            raise KeyError(f"fit preset {preset!r}: declared {sorted(presets)}")
        out.update(_deep_copy(presets[preset] or {}))
    for key, value in (overrides or {}).items():
        if key not in out:
            raise KeyError(f"fit setting {key!r} is not declared in {Path(path).name}")
        out[key] = value
    return out


def preset_names(path=FIT_PARAMETERS):
    """Names of the declared presets.

    Parameters
    ----------
    path : str or pathlib.Path, optional
        Declaration file.

    Returns
    -------
    list of str
    """
    return list(_columns.declaration(path).get("presets") or {})


def _deep_copy(value):
    """Copy nested dicts and lists of a parsed YAML document.

    Parameters
    ----------
    value : object

    Returns
    -------
    object
    """
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


@dataclass(frozen=True)
class ParameterSpec:
    """One declared fit parameter.

    Attributes
    ----------
    name : str
        Internal name, as the site model reads it (``ln_scale``, ``delta``, ...).
    label : str
        Reported name, the natural-unit quantity (``scale``, ``delta``, ...).
    log : bool
        The fit works on the natural log of the value.
    lower, upper : float
        Bounds of the internal value.
    free : bool
        False when the parameter is never fitted (tau0).
    """

    name: str
    label: str
    log: bool
    lower: float
    upper: float
    free: bool = True

    def to_natural(self, value):
        """Map an internal value to natural units.

        Parameters
        ----------
        value : float or numpy.ndarray

        Returns
        -------
        float or numpy.ndarray
        """
        return np.exp(value) if self.log else value


def parameter_specs(fit_settings=None):
    """The declared parameters in fit-vector order.

    Parameters
    ----------
    fit_settings : dict, optional
        From :func:`settings`; the declaration by default.

    Returns
    -------
    list of ParameterSpec
    """
    fs = fit_settings or settings()
    out = []
    for entry in fs["parameters"]:
        log = entry.get("scale", "linear") == "log"
        lower, upper = float(entry["lower"]), float(entry["upper"])
        out.append(
            ParameterSpec(
                name=("ln_" if log else "") + entry["name"],
                label=entry["name"],
                log=log,
                lower=float(np.log(lower)) if log else lower,
                upper=float(np.log(upper)) if log else upper,
                free=bool(entry.get("free", True)),
            )
        )
    return out


def _spec_map(fit_settings):
    """``{internal name: ParameterSpec}``.

    Parameters
    ----------
    fit_settings : dict

    Returns
    -------
    dict
    """
    return {p.name: p for p in parameter_specs(fit_settings)}


def internal_name(label, fit_settings=None):
    """Internal name of a reported parameter (``scale`` -> ``ln_scale``).

    Parameters
    ----------
    label : str
    fit_settings : dict, optional

    Returns
    -------
    str
    """
    for p in parameter_specs(fit_settings):
        if p.label == label or p.name == label:
            return p.name
    raise KeyError(f"no fit parameter {label!r}")


def fixed_values(dye, fit_settings=None):
    """The fixed parameters of a dye as internal values.

    Parameters
    ----------
    dye : str
    fit_settings : dict, optional

    Returns
    -------
    dict
        ``{internal name: value}`` in declared order.
    """
    fs = fit_settings or settings()
    specs = {p.label: p for p in parameter_specs(fs)}
    out = {}
    for label, value in (fs["fixed"].get(dye) or {}).items():
        p = specs[label]
        out[p.name] = float(np.log(value)) if p.log else float(value)
    return out


def free_names(dye, fixed=(), fit_settings=None):
    """The free parameters of a dye's block, in fit-vector order.

    Parameters
    ----------
    dye : str
    fixed : collection of str, optional
        Internal names held fixed.
    fit_settings : dict, optional

    Returns
    -------
    list of str
        tau0 is never free; ``dtau_shield`` only for the declared ``shielding_dyes``.
    """
    fs = fit_settings or settings()
    return [
        p.name
        for p in parameter_specs(fs)
        if p.free
        and p.name not in fixed
        and (p.name != "dtau_shield" or dye in fs["shielding_dyes"])
    ]


def model_error(residual_ns, sigma_meas, fit_settings=None):
    """The model's own error s from the residuals of a best fit.

    Parameters
    ----------
    residual_ns : numpy.ndarray
        Prediction minus measurement (ns).
    sigma_meas : numpy.ndarray
        Measurement errors (ns).
    fit_settings : dict, optional

    Returns
    -------
    float
        The s that makes ``median(r^2 / (sigma^2 + s^2))`` the median of chi-square(1), and
        never below the declared floor (0 when the residuals are already that small).
    """
    fs = fit_settings or settings()
    target = float(fs["model_error_median_chi2"])
    residual_ns, sigma_meas = np.asarray(residual_ns, float), np.asarray(sigma_meas, float)

    def f(s):
        return np.median(residual_ns**2 / (sigma_meas**2 + s * s)) - target

    lo, hi = (float(v) for v in fs["model_error_bracket"])
    s = 0.0 if f(lo) <= 0 else float(_numerics.root_scalar(f, bracket=[lo, hi]).root)
    return max(s, float(fs["model_error_floor"]))


def ridge(theta, groups, ridge_sd):
    """Stickiness prior residuals: each group's ln s around the common one.

    Parameters
    ----------
    theta : dict
    groups : sequence of str
    ridge_sd : float
        ln of the declared ridge factor.

    Returns
    -------
    numpy.ndarray
        One residual per group (Gaussian prior: ``exp(-r^2/2)``).
    """
    return np.array([(theta[f"ln_s_{g}"] - theta["ln_s_common"]) / ridge_sd for g in groups])


def clipped_inverse(H, max_variance):
    """Inverse of a curvature matrix with every eigen-variance capped.

    Parameters
    ----------
    H : numpy.ndarray
        Symmetric curvature (``J^T J``).
    max_variance : float
        No direction gets a variance above this; directions with curvature below
        ``1/max_variance`` get exactly this.

    Returns
    -------
    numpy.ndarray
    """
    vals, vecs = np.linalg.eigh(0.5 * (H + H.T))
    inv = np.where(vals > 1.0 / max_variance, 1.0 / np.clip(vals, 1e-300, None), max_variance)
    return (vecs * inv) @ vecs.T


# --------------------------------------------------------------------------------------------
# the titration context every block reads


@dataclass
class TitrationContext:
    """What the blocks need from the titrations.

    Attributes
    ----------
    K_mean, K_sd : dict
        ``{(dye, amino_acid): K_SV}`` posterior mean and sd (1/M).
    tau0 : dict
        ``{(dye, amino_acid): tau0}`` of the titrations (ns).
    textbook : dict
        Reference kQ per quenching residue (1/ns).
    kq_settings : dict
        The measurement-columns settings (``quenchers``, ``titrated``, ``reference_dye``,
        ``dyes``, ``model_titrations``).
    """

    K_mean: dict
    K_sd: dict
    tau0: dict
    textbook: dict
    kq_settings: dict

    @classmethod
    def from_posterior(cls, posterior, textbook=None, kq_settings=None):
        """Build from a :class:`~.titration.TitrationPosterior`.

        Parameters
        ----------
        posterior : TitrationPosterior
        textbook : dict, optional
            :func:`~.kq_scaling.textbook_kq` by default.
        kq_settings : dict, optional
            The measurement-columns settings by default.

        Returns
        -------
        TitrationContext
        """
        kq_settings = kq_settings or _columns.settings()
        return cls(
            K_mean=posterior.k_mean(),
            K_sd=posterior.k_sd(),
            tau0=posterior.tau0(),
            textbook=dict(textbook or _kq.textbook_kq(settings=kq_settings)),
            kq_settings=kq_settings,
        )

    @property
    def model_keys(self):
        """The slopes that enter the kQ vectors, ``[(dye, amino_acid), ...]``."""
        return _kq.model_keys(self.kq_settings)

    @property
    def reference_dye(self):
        """The dye every kQ is scaled from."""
        return self.kq_settings["reference_dye"]

    def kq(self, dye, K=None):
        """kQ vector of a dye at slopes K (the posterior means by default).

        Parameters
        ----------
        dye : str
        K : dict, optional

        Returns
        -------
        numpy.ndarray
        """
        return _kq.kq_vector(dye, self.K_mean if K is None else K, self.tau0, self.textbook,
                             self.kq_settings)


# --------------------------------------------------------------------------------------------
# a block


class Block:
    """One data set of the graph: the measured lifetimes of one dye.

    Parameters
    ----------
    label : str
        Name of the data set (``"AF488 in H2O"``).
    dye : str
    rows : numpy.ndarray
        Measured rows with fields ``site``, ``state``, ``tau_x``, ``sigma_meas`` (and
        ``solvent``), as in the ``site_lifetimes`` table.
    points : list of (Site, float)
        Site model and water rate of each row.
    tau0 : float
        Free-dye lifetime (ns) the predictions start from.
    context : TitrationContext
    fit_settings : dict
    groups : sequence of str
        The site model's residue groups.

    Attributes
    ----------
    fixed : dict
        Fixed internal values.
    free : list of str
        Free internal names (fit-vector order).
    lo, hi : numpy.ndarray
        Bounds of the free vector.
    k_keys : list of tuple
        The titration slopes this block reads.
    searches : list of (numpy.ndarray, float)
        After :func:`search`: every search's best x and log posterior, best first.
    best_x : numpy.ndarray
    s : float
        Model error (ns).
    use : numpy.ndarray
        Inlier mask of the rows.
    """

    def __init__(self, label, dye, rows, points, tau0, context, fit_settings, groups):
        self.label, self.dye, self.rows, self.points = label, dye, rows, points
        self.tau0 = float(tau0)
        self.context = context
        self.settings = fit_settings
        self.groups = list(groups)
        self.ridge_sd = float(np.log(fit_settings["ridge_factor"]))
        self.nu = float(fit_settings["student_t_nu"])
        self.fixed = fixed_values(dye, fit_settings)
        self.free = free_names(dye, self.fixed, fit_settings)
        specs = _spec_map(fit_settings)
        self.lo = np.array([specs[n].lower for n in self.free])
        self.hi = np.array([specs[n].upper for n in self.free])
        ref = context.reference_dye
        self.k_keys = [] if dye == ref else [k for k in context.model_keys if k[0] in (dye, ref)]
        self.tau_x = np.asarray(rows["tau_x"], float)
        self.sigma_meas = np.asarray(rows["sigma_meas"], float)
        self.searches, self.best_x, self.s, self.use = [], None, None, None
        self.starts = []

    def add_start(self, values):
        """Add a declared start to the search (beside the random ones).

        Parameters
        ----------
        values : dict
            Natural-unit values by reported name (``scale``, ``s_basic``, ...); a free
            parameter left out starts at the middle of its range, ``model_error`` at the
            declared floor.

        Returns
        -------
        numpy.ndarray
            The free vector added.
        """
        specs = _spec_map(self.settings)
        x = []
        for name, lo, hi in zip(self.free, self.lo, self.hi):
            spec = specs[name]
            if spec.label in values:
                v = float(values[spec.label])
                x.append(np.log(v) if spec.log else v)
            elif name == "ln_model_error":
                x.append(np.log(float(self.settings["model_error_floor"])))
            else:
                x.append(0.5 * (lo + hi))
        x = np.clip(np.array(x), self.lo, self.hi)
        self.starts.append(x)
        return x

    def theta(self, x, K=None, s=None):
        """The parameter set of a free vector.

        Parameters
        ----------
        x : sequence of float
            Free vector.
        K : dict, optional
            Titration slopes; the posterior means by default.
        s : float, optional
            Model error to store as ``ln_model_error``.

        Returns
        -------
        dict
            Site-model keys plus ``kq`` and ``ln_tau0``.
        """
        th = dict(self.fixed)
        th.update(zip(self.free, x))
        th.setdefault("ln_tau0", np.log(self.tau0))
        th["kq"] = self.context.kq(self.dye, K)
        if s is not None:
            th["ln_model_error"] = np.log(s)
        return th

    def predictions(self, theta):
        """Predicted lifetimes of every row (ns).

        Parameters
        ----------
        theta : dict

        Returns
        -------
        numpy.ndarray
        """
        return _site_model.predict(self.points, theta, np.exp(theta["ln_tau0"]))

    def robust_log_posterior(self, x):
        """Student-t log posterior with the model error free (the search objective).

        Parameters
        ----------
        x : numpy.ndarray
            Free vector.

        Returns
        -------
        float
            ``-1e300`` where the model is not finite.
        """
        th = self.theta(x)
        sigma = np.sqrt(self.sigma_meas**2 + np.exp(2 * th["ln_model_error"]))
        z = (self.predictions(th) - self.tau_x) / sigma
        value = (-np.log(sigma) - 0.5 * (self.nu + 1) * np.log1p(z * z / self.nu)).sum()
        value = value - 0.5 * (ridge(th, self.groups, self.ridge_sd) ** 2).sum()
        return float(value) if np.isfinite(value) else -1e300

    def start(self, seed):
        """A uniform random start in the bounds.

        Parameters
        ----------
        seed : int

        Returns
        -------
        numpy.ndarray
        """
        return np.random.default_rng(seed).uniform(self.lo, self.hi)

    def lean(self):
        """A copy for worker processes: site models without their source tables.

        Returns
        -------
        Block
        """
        out = object.__new__(Block)
        out.__dict__.update(self.__dict__)
        lean_sites = {}
        points = []
        for site, water in self.points:
            if id(site) not in lean_sites:
                copy = object.__new__(type(site))
                copy.__dict__.update({k: v for k, v in site.__dict__.items() if k != "table"})
                lean_sites[id(site)] = copy
            points.append((lean_sites[id(site)], water))
        out.points = points
        return out


def find_most_probable(block, seed, maxiter):
    """One robust search from a random start (or a given one).

    Parameters
    ----------
    block : Block
    seed : int or numpy.ndarray
        Seed of a uniform random start, or the start itself (a free vector).
    maxiter : int

    Returns
    -------
    tuple
        ``(x, log_posterior)``.
    """
    if np.ndim(seed):
        x0 = np.clip(np.asarray(seed, float), block.lo, block.hi)
    else:
        x0 = block.start(int(seed))
    sol = _numerics.minimize(
        lambda x: -block.robust_log_posterior(x),
        x0,
        method="L-BFGS-B",
        bounds=list(zip(block.lo, block.hi)),
        options=dict(maxiter=int(maxiter)),
    )
    return np.asarray(sol.x, float), -float(sol.fun)


# --------------------------------------------------------------------------------------------
# running many independent evaluations (worker processes, cooperative cancel)

_WORKER = {}


def _worker_init(payload):
    """Store the worker's payload (a block or a graph) once per process.

    Parameters
    ----------
    payload : dict
    """
    _WORKER.clear()
    _WORKER.update(payload)


def _worker_search(seed):
    """One search in a worker process.

    Parameters
    ----------
    seed : int

    Returns
    -------
    tuple
    """
    return find_most_probable(_WORKER["block"], seed, _WORKER["maxiter"])


def _worker_evaluate(u):
    """One graph evaluation in a worker process.

    Parameters
    ----------
    u : numpy.ndarray

    Returns
    -------
    tuple
    """
    return _WORKER["graph"].evaluate(u)


def default_workers():
    """Worker processes used when none are given: the CPU count.

    Returns
    -------
    int
    """
    return max(1, os.cpu_count() or 1)


def _check(cancel):
    """Raise :class:`CancelledError` when the caller asked to stop.

    Parameters
    ----------
    cancel : callable or None
    """
    if cancel is not None and cancel():
        raise CancelledError("quenching analysis cancelled")


@_contextlib.contextmanager
def _main_hidden():
    """Start worker processes without re-running the caller's ``__main__``.

    A spawned worker normally imports the parent's main script again, so a plain script
    without an ``if __name__ == "__main__":`` guard would start the analysis once more in
    every worker (and multiprocessing stops it). The workers here need nothing from
    ``__main__`` -- the work items are this module's functions and chisurf objects -- so
    while they start, ``__main__`` hides its file and spec and the workers skip it.
    ``ProcessPoolExecutor`` starts its processes in ``submit``, inside this block.
    """
    main = _sys.modules.get("__main__")
    saved = {k: getattr(main, k) for k in ("__file__", "__spec__") if hasattr(main, k)}
    try:
        for k in saved:
            if k == "__file__":
                delattr(main, k)
            else:
                setattr(main, k, None)
        yield
    finally:
        for k, v in saved.items():
            setattr(main, k, v)


class WorkerPool:
    """Worker processes that keep one payload over many maps.

    A joint fit evaluates its Jacobian dozens of times on the same graph; starting the worker
    processes (spawn: a fresh interpreter, the imports, the site models unpickled) costs more
    than one Jacobian, so the fit starts them once and maps every Jacobian onto them. The
    processes start on the first map that needs them and stop on :meth:`close` (or at the end
    of a ``with`` block).

    Parameters
    ----------
    payload : dict
        Handed to every worker once (:func:`_worker_init`).
    workers : int, optional
        Worker processes; the CPU count by default. 1 runs every map in process.
    """

    def __init__(self, payload, workers=None):
        self.payload = payload
        self.workers = default_workers() if workers is None else max(1, int(workers))
        self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def executor(self):
        """The process pool (started on first use).

        Returns
        -------
        concurrent.futures.ProcessPoolExecutor
        """
        if self._pool is None:
            self._pool = _futures.ProcessPoolExecutor(
                max_workers=self.workers, mp_context=_mp.get_context("spawn"),
                initializer=_worker_init, initargs=(self.payload,),
            )
        return self._pool

    def close(self):
        """Stop the worker processes."""
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None


def _map(function, worker_function, payload, items, workers, progress=None, cancel=None,
         label="", pool=None):
    """``[function(item) for item in items]``, in worker processes when ``workers > 1``.

    Parameters
    ----------
    function : callable
        In-process form.
    worker_function : callable
        Module-level form run in a worker (reads :data:`_WORKER`).
    payload : dict
        Handed to every worker once.
    items : sequence
    workers : int
    progress : callable, optional
        ``progress(done, total, label)`` after each item.
    cancel : callable, optional
        ``cancel() -> bool``; checked between items.
    label : str
    pool : WorkerPool, optional
        Running workers that already hold *payload*; they are kept running afterwards.

    Returns
    -------
    list
        Results in item order.
    """
    items = list(items)
    out = [None] * len(items)
    if pool is not None:
        workers = pool.workers
    elif workers is None:
        workers = default_workers()
    if workers <= 1 or len(items) <= 1:
        for i, item in enumerate(items):
            _check(cancel)
            out[i] = function(item)
            if progress:
                progress(i + 1, len(items), label)
        return out
    own = pool is None
    if own:
        pool = WorkerPool(payload, min(workers, len(items)))
    executor = pool.executor()
    try:
        with _main_hidden():
            index = {executor.submit(worker_function, item): i for i, item in enumerate(items)}
        done = 0
        pending = set(index)
        while pending:
            finished, pending = _futures.wait(pending, timeout=0.5,
                                              return_when=_futures.FIRST_COMPLETED)
            for fut in finished:
                out[index[fut]] = fut.result()
                done += 1
                if progress:
                    progress(done, len(items), label)
            if cancel is not None and cancel():
                for fut in pending:
                    fut.cancel()
                raise CancelledError("quenching analysis cancelled")
    finally:
        if own:
            pool.close()
    return out


def search(block, seed, fit_settings=None, workers=None, progress=None, cancel=None):
    """The robust multistart search of one block; sets its best fit, model error and inliers.

    Parameters
    ----------
    block : Block
    seed : int
        Start ``k`` uses ``seed + k``.
    fit_settings : dict, optional
        The block's by default.
    workers : int, optional
        Worker processes (1 = in process).
    progress : callable, optional
        ``progress(done, total, label)``.
    cancel : callable, optional

    Returns
    -------
    Block
        The same block, with ``searches``, ``best_x``, ``s`` and ``use`` set.
    """
    fs = fit_settings or block.settings
    maxiter = int(fs["search_maxiter"])
    seeds = [int(seed) + k for k in range(int(fs["n_starts"]))]
    seeds += [np.asarray(x, float) for x in block.starts]
    found = _map(
        lambda k: find_most_probable(block, k, maxiter), _worker_search,
        dict(block=block.lean(), maxiter=maxiter), seeds, workers, progress, cancel,
        label=f"{block.label}: search",
    )
    return settle(block, found, fs)


def settle(block, found, fit_settings=None):
    """Take a block's best search: its model error and inlier mask.

    Parameters
    ----------
    block : Block
    found : sequence of (x, log_posterior)
        Search results (any order).
    fit_settings : dict, optional

    Returns
    -------
    Block
        With ``searches`` (best first), ``best_x``, ``s`` and ``use`` set.
    """
    fs = fit_settings or block.settings
    found = sorted(((np.asarray(x, float), float(lp)) for x, lp in found), key=lambda f: -f[1])
    block.searches, block.best_x = found, np.asarray(found[0][0])
    th = block.theta(block.best_x)
    residual = block.predictions(th) - block.tau_x
    s = model_error(residual, block.sigma_meas, fs)
    block.use = np.abs(residual) / np.sqrt(block.sigma_meas**2 + s**2) <= fs["outlier_limit"]
    block.s = model_error(residual[block.use], block.sigma_meas[block.use], fs)
    return block


def adopt(block, values, fit_settings=None):
    """Settle a block at given parameters instead of searching (e.g. a stored run's).

    Parameters
    ----------
    block : Block
    values : dict
        Internal values of the block's free parameters; a missing ``ln_model_error`` takes
        the value of best robust log posterior on a grid over its range. ``model_error``
        (ns), when given, replaces the model error the search rule derives (the inlier mask
        stays the rule's).
    fit_settings : dict, optional

    Returns
    -------
    Block
        As :func:`settle` with one "search".
    """
    x = np.array([values.get(n, np.nan) for n in block.free], float)
    if "ln_model_error" in block.free and "ln_model_error" not in values:
        i = block.free.index("ln_model_error")
        grid = np.linspace(block.lo[i], block.hi[i], 201)

        def at(v):
            x[i] = v
            return block.robust_log_posterior(x)

        x[i] = max(grid, key=at)
    x = np.clip(x, block.lo, block.hi)
    settle(block, [(x, block.robust_log_posterior(x))], fit_settings)
    if "model_error" in values:
        block.s = float(values["model_error"])
    return block


# --------------------------------------------------------------------------------------------
# the graph


class Graph:
    """The joint posterior of several blocks and the titration slopes they read.

    Parameters are scaled to ``u`` in [0, 1] over their ranges (the slopes over
    ``K_mean +- k_range_sd * K_sd``), so all have comparable sizes for the fit and the errors.

    Parameters
    ----------
    blocks : sequence of Block
        Searched blocks (:func:`search`).
    fit_settings : dict, optional
        The first block's by default.

    Attributes
    ----------
    layout : list of tuple
        ``(block index or None, name, index in the block's free vector or None)`` per graph
        parameter; ``None`` marks a titration slope ``name = (dye, amino_acid)``.
    lo, hi : numpy.ndarray
        Ranges of the graph parameters.
    """

    def __init__(self, blocks, fit_settings=None):
        self.blocks = list(blocks)
        self.settings = fit_settings or self.blocks[0].settings
        context = self.blocks[0].context
        self.context = context
        self.k_keys = [k for k in context.model_keys if any(k in b.k_keys for b in self.blocks)]
        width = float(self.settings["k_range_sd"])
        self.u_clip = float(self.settings["u_clip"])
        self.layout, lo, hi = [], [], []
        for b, block in enumerate(self.blocks):
            for i, name in enumerate(block.free):
                if name != "ln_model_error":
                    self.layout.append((b, name, i))
                    lo.append(block.lo[i])
                    hi.append(block.hi[i])
        for key in self.k_keys:
            self.layout.append((None, key, None))
            lo.append(context.K_mean[key] - width * context.K_sd[key])
            hi.append(context.K_mean[key] + width * context.K_sd[key])
        self.lo, self.hi = np.array(lo), np.array(hi)
        self.u = self.cov = self.Jr = self.Jp = self.residual = self.prediction = None

    @property
    def n_parameters(self):
        """Graph parameters (block parameters without the model errors, plus slopes)."""
        return len(self.layout)

    def to_u(self, v):
        """Unit-box coordinates of parameter values (clipped inside the box).

        Parameters
        ----------
        v : numpy.ndarray

        Returns
        -------
        numpy.ndarray
        """
        return np.clip((v - self.lo) / (self.hi - self.lo), self.u_clip, 1 - self.u_clip)

    def to_v(self, u):
        """Parameter values of unit-box coordinates.

        Parameters
        ----------
        u : numpy.ndarray

        Returns
        -------
        numpy.ndarray
        """
        return self.lo + (self.hi - self.lo) * u

    def start(self):
        """The joint fit's start: every block's search best and the slope means (in u).

        Returns
        -------
        numpy.ndarray
        """
        v = [
            self.blocks[b].best_x[i] if b is not None else self.context.K_mean[name]
            for b, name, i in self.layout
        ]
        return self.to_u(np.array(v))

    def thetas(self, u):
        """Every block's parameter set (with its fixed model error) and the slopes.

        Parameters
        ----------
        u : numpy.ndarray

        Returns
        -------
        tuple
            ``(list of theta dicts, K dict)``.
        """
        v = self.to_v(u)
        K = dict(self.context.K_mean)
        xs = [block.best_x.copy() for block in self.blocks]
        for (b, name, i), value in zip(self.layout, v):
            if b is None:
                K[name] = value
            else:
                xs[b][i] = value
        return [block.theta(x, K, block.s) for block, x in zip(self.blocks, xs)], K

    def evaluate(self, u):
        """Residuals in error-bar units and all predictions.

        Parameters
        ----------
        u : numpy.ndarray

        Returns
        -------
        tuple
            ``(residuals, predictions)``: per block the inlier residuals then its ridge
            residuals, then the slope-prior residuals; predictions of every row, block order.
        """
        ths, K = self.thetas(u)
        residuals, predictions = [], []
        for block, th in zip(self.blocks, ths):
            p = block.predictions(th)
            sigma = np.sqrt(block.sigma_meas**2 + block.s**2)
            residuals += [((p - block.tau_x) / sigma)[block.use],
                          ridge(th, block.groups, block.ridge_sd)]
            predictions.append(p)
        K_mean, K_sd = self.context.K_mean, self.context.K_sd
        residuals.append(np.array([(K[k] - K_mean[k]) / K_sd[k] for k in self.k_keys]))
        return np.concatenate(residuals), np.concatenate(predictions)

    def jacobian(self, u, step=None, workers=1, cancel=None, pool=None):
        """Central differences of residuals and predictions with respect to u.

        Parameters
        ----------
        u : numpy.ndarray
        step : float, optional
            The declared ``jacobian_step`` by default.
        workers : int, optional
        cancel : callable, optional
        pool : WorkerPool, optional
            Running workers holding ``dict(graph=self.lean())`` (a joint fit's).

        Returns
        -------
        tuple
            ``(Jr, Jp)``.
        """
        step = float(self.settings["jacobian_step"]) if step is None else step
        shifted = []
        for i in range(len(u)):
            for sign in (+1, -1):
                v = u.copy()
                v[i] += sign * step
                shifted.append(v)
        payload = None if pool is not None else dict(graph=self.lean())
        out = _map(self.evaluate, _worker_evaluate, payload, shifted, workers, cancel=cancel,
                   label="jacobian", pool=pool)
        Jr = np.array([(out[2 * i][0] - out[2 * i + 1][0]) / (2 * step)
                       for i in range(len(u))]).T
        Jp = np.array([(out[2 * i][1] - out[2 * i + 1][1]) / (2 * step)
                       for i in range(len(u))]).T
        return Jr, Jp

    def lean(self):
        """A copy for worker processes (lean blocks, no fit state).

        Returns
        -------
        Graph
        """
        out = object.__new__(Graph)
        out.__dict__.update(self.__dict__)
        out.blocks = [b.lean() for b in self.blocks]
        out.u = out.cov = out.Jr = out.Jp = out.residual = out.prediction = None
        return out

    def residual_rows(self):
        """Where each block's inlier residuals sit in the residual vector.

        Returns
        -------
        list of numpy.ndarray
            Per block: the residual index of each row, ``-1`` for an outlier.
        """
        out, r0 = [], 0
        for block in self.blocks:
            n_use = int(block.use.sum())
            rows_r = np.full(len(block.rows), -1)
            rows_r[block.use] = np.arange(r0, r0 + n_use)
            out.append(rows_r)
            r0 += n_use + len(block.groups)
        return out

    def prediction_rows(self):
        """Where each block's predictions sit in the prediction vector.

        Returns
        -------
        list of numpy.ndarray
        """
        out, p0 = [], 0
        for block in self.blocks:
            out.append(np.arange(p0, p0 + len(block.rows)))
            p0 += len(block.rows)
        return out


@dataclass
class OptimizeSummary:
    """The joint fit's outcome.

    Attributes
    ----------
    x : numpy.ndarray
        Best u.
    cost : float
        ``0.5 * sum(r^2)`` there.
    status : int
        MINPACK's status of the first stage.
    nfev : int
        Its evaluations.
    minpack_cost : float
        Cost after the first stage (before the polish).
    """

    x: np.ndarray
    cost: float
    status: int
    nfev: int
    minpack_cost: float


def polish(graph, u, iterations, rtol, workers=None, cancel=None, hold=None, pool=None):
    """Projected Levenberg-Marquardt in the unit box.

    Each step solves ``(J^T J + mu diag(J^T J)) d = -J^T r`` on the parameters that are not
    held at a bound by their gradient, clips to the box, and is accepted when the cost falls
    (``mu`` shrinks) or retried with a larger ``mu``.

    Parameters
    ----------
    graph : Graph
    u : numpy.ndarray
        Start.
    iterations : int
        Accepted steps at most.
    rtol : float
        Stop when an accepted step lowers the cost by less than this (relative).
    workers : int, optional
    cancel : callable, optional
    hold : sequence of int, optional
        Coordinates kept where they are (a profile's fixed parameter).
    pool : WorkerPool, optional
        Running workers holding this graph (see :meth:`Graph.jacobian`).

    Returns
    -------
    dict
        ``u``, ``cost``, ``steps`` (accepted), ``costs`` (after each accepted step).
    """
    lo, hi = graph.u_clip, 1 - graph.u_clip
    held = np.zeros(len(u), bool)
    if hold is not None:
        held[list(hold)] = True
    r = graph.evaluate(u)[0]
    cost = 0.5 * float(r @ r)
    costs, mu, steps = [cost], 1e-3, 0
    while steps < iterations:
        _check(cancel)
        J, _ = graph.jacobian(u, workers=workers, cancel=cancel, pool=pool)
        g = J.T @ r
        free = ~(((u <= lo * 1.0001) & (g > 0)) | ((u >= hi - lo * 1e-4) & (g < 0)) | held)
        if not free.any():
            break
        A = J[:, free].T @ J[:, free]
        accepted = False
        for _ in range(12):
            d = np.linalg.solve(A + mu * np.diag(np.diag(A) + 1e-12), -g[free])
            trial = u.copy()
            trial[free] = np.clip(u[free] + d, lo, hi)
            r_t = graph.evaluate(trial)[0]
            cost_t = 0.5 * float(r_t @ r_t)
            if cost_t < cost:
                accepted = True
                break
            mu *= 4.0
        if not accepted:
            break
        gain = (cost - cost_t) / cost
        u, r, cost = trial, r_t, cost_t
        mu = max(mu / 3.0, 1e-9)
        steps += 1
        costs.append(cost)
        if gain < rtol:
            break
    return dict(u=u, cost=cost, steps=steps, costs=costs)


def joint_fit(graph, workers=None, cancel=None, max_nfev=None, start=None, minpack=None):
    """The joint least-squares fit of a graph and its Laplace approximation (in place).

    Parameters
    ----------
    graph : Graph
    workers : int, optional
        For the Jacobian.
    cancel : callable, optional
        Checked at every residual evaluation of the fit.
    max_nfev : int, optional
        The declared ``joint_max_nfev`` by default.
    start : numpy.ndarray, optional
        Start in u; the blocks' search bests and the slope means by default.
    minpack : bool, optional
        Run MINPACK's Levenberg-Marquardt first; False only polishes from *start* (to replay
        a known optimum, or for speed: MINPACK's forward-difference Jacobian runs in one
        process, the polish's in the workers). The declared ``joint_minpack`` by default.

    Returns
    -------
    Graph
        With ``u``, ``cov``, ``Jr``, ``Jp``, ``residual``, ``prediction``, ``fit``,
        ``polish`` set.
    """
    fs = graph.settings
    budget = int(fs["joint_max_nfev"] if max_nfev is None else max_nfev)

    def residuals(u):
        _check(cancel)
        return graph.evaluate(u)[0]

    # MINPACK's Levenberg-Marquardt works through a bounds transform, which makes a parameter
    # near its bound (static at 0.001, s_aromatic at 1) slow to move; the projected
    # Levenberg-Marquardt polish works in the unit box on central-difference Jacobians and
    # finishes the fit.
    u = graph.start() if start is None else np.asarray(start, float)
    status, nfev, first = 0, 0, float("nan")
    if minpack is None:
        minpack = bool(fs["joint_minpack"])
    if minpack:
        tol = float(fs["joint_tolerance"])
        sol = _numerics.least_squares(residuals, u, bounds=(0.0, 1.0), ftol=tol, xtol=tol,
                                      gtol=tol, diff_step=float(fs["joint_diff_step"]),
                                      max_nfev=budget)
        u, status, nfev, first = np.asarray(sol.x, float), int(sol.status), int(sol.nfev), \
            float(sol.cost)
    u = np.clip(u, graph.u_clip, 1 - graph.u_clip)
    with WorkerPool(dict(graph=graph.lean()), workers) as pool:
        graph.polish = polish(graph, u, int(fs["joint_polish_iterations"]),
                              float(fs["joint_polish_rtol"]), cancel=cancel, pool=pool)
        sol = OptimizeSummary(x=graph.polish["u"], cost=graph.polish["cost"], status=status,
                              nfev=nfev, minpack_cost=first)
        graph.fit = sol
        graph.u = np.asarray(sol.x, float)
        graph.residual, graph.prediction = graph.evaluate(graph.u)
        graph.Jr, graph.Jp = graph.jacobian(graph.u, cancel=cancel, pool=pool)
    graph.cov = clipped_inverse(graph.Jr.T @ graph.Jr, float(fs["max_variance"]))
    return graph


# --------------------------------------------------------------------------------------------
# results


@dataclass
class BlockResult:
    """One data set's view of a solved graph (what the prototype called a stage).

    Attributes
    ----------
    label, dye : str
    theta : dict
        Best-fit parameter set (with the graph's slopes in ``kq``).
    tau0 : float
    model_error : float
    table : numpy.ndarray
        Declared ``fit_predictions`` rows of this block.
    estimates : numpy.ndarray
        Declared ``fit_estimates`` rows of this block.
    loo : numpy.ndarray
        Declared ``leave_one_out`` rows (one per measured row).
    worst : list of (int, float)
        ``(site, max |z|)``, worst first.
    stats : dict
        ``rms``, ``median_abs_dev``, ``median_pred_sd``, ``mean_dark_fraction``, ``outliers``
        (sites), ``n_outlier_lifetimes`` (search mask), ``n_rows``.
    graph : Graph
    block : Block
    index : int
        Block index in the graph.
    """

    label: str
    dye: str
    theta: dict
    tau0: float
    model_error: float
    table: np.ndarray
    estimates: np.ndarray
    loo: np.ndarray
    worst: list
    stats: dict
    graph: object = field(repr=False)
    block: object = field(repr=False)
    index: int = 0

    @property
    def points(self):
        """The block's (Site, water) points."""
        return self.block.points

    @property
    def searches(self):
        """The block's searches, best first."""
        return self.block.searches

    def estimate(self, label):
        """One row of the estimates as a dict.

        Parameters
        ----------
        label : str
            Reported parameter name (``scale``, ``s_basic``, ``model_error``, ...).

        Returns
        -------
        dict
            ``value``, ``low``, ``high``, ``note``.
        """
        e = self.estimates
        row = e[e["parameter"] == label]
        if not len(row):
            raise KeyError(f"{self.label}: no estimate {label!r}")
        r = row[0]
        return dict(value=float(r["value"]), low=float(r["low_68"]),
                    high=float(r["high_68"]), note=str(r["note"]))


@dataclass
class GraphResult:
    """A solved graph and its views.

    Attributes
    ----------
    name : str
        Declared graph name.
    graph : Graph
    views : list of BlockResult
    k_table : numpy.ndarray
        Declared ``graph_titration_slopes``.
    structure : dict
        :func:`describe_graph` summary.
    """

    name: str
    graph: object = field(repr=False)
    views: list = field(default_factory=list)
    k_table: np.ndarray = None
    structure: dict = None

    def view(self, label):
        """The view of one block.

        Parameters
        ----------
        label : str

        Returns
        -------
        BlockResult
        """
        for v in self.views:
            if v.label == label:
                return v
        raise KeyError(f"graph {self.name!r} has no block {label!r}")


def make_result_table(name, rows):
    """A declared result table (``settings/analysis/result_columns.yaml``).

    Parameters
    ----------
    name : str
    rows : sequence of dict

    Returns
    -------
    numpy.ndarray
    """
    return _columns.make_table(name, rows, RESULT_COLUMNS)


def leave_one_out(graph, b, rows_p, rows_r):
    """Leave one site out (all its rows) by one Newton step on the curvature.

    Parameters
    ----------
    graph : Graph
        Solved.
    b : int
        Block index.
    rows_p, rows_r : numpy.ndarray
        The block's prediction and residual indices.

    Returns
    -------
    list of dict
        One per row, in row order: ``row``, ``site``, ``state``, ``solvent``, ``z``.
    """
    block = graph.blocks[b]
    max_variance = float(graph.settings["max_variance"])
    H = graph.Jr.T @ graph.Jr
    rows = block.rows
    sites = np.asarray(rows["site"]).astype(int)
    solvent = rows["solvent"] if "solvent" in rows.dtype.names else np.array([""] * len(rows))
    out = []
    for site in sorted(set(sites.tolist())):
        here = sites == site
        r_idx = rows_r[here & (rows_r >= 0)]
        Js, rs = graph.Jr[r_idx], graph.residual[r_idx]
        cov = clipped_inverse(H - Js.T @ Js, max_variance)
        step = cov @ (Js.T @ rs)
        for j in np.flatnonzero(here):
            jp = graph.Jp[rows_p[j]]
            without = graph.prediction[rows_p[j]] + jp @ step
            sigma = np.sqrt(block.sigma_meas[j] ** 2 + block.s**2 + jp @ cov @ jp)
            out.append(dict(row=int(j), site=int(site), state=str(rows["state"][j]),
                            solvent=str(solvent[j]), z=float((without - block.tau_x[j]) / sigma)))
    out.sort(key=lambda d: d["row"])
    return out


def _worst(loo_rows):
    """Max |z| per site, worst first.

    Parameters
    ----------
    loo_rows : list of dict

    Returns
    -------
    list of (int, float)
    """
    worst = {}
    for r in loo_rows:
        worst[r["site"]] = max(worst.get(r["site"], 0.0), abs(r["z"]))
    return sorted(worst.items(), key=lambda kv: -kv[1])


def block_views(graph, graph_name=""):
    """The per-block views of a solved graph.

    Parameters
    ----------
    graph : Graph
        After :func:`joint_fit`.
    graph_name : str, optional
        Recorded in the tables' ``graph`` column.

    Returns
    -------
    list of BlockResult
    """
    fs = graph.settings
    specs = _spec_map(fs)
    limit = float(fs["outlier_limit"])
    sd_u = np.sqrt(np.diag(graph.cov))
    u = graph.u
    v = graph.to_v(u)
    v_lo, v_hi = graph.to_v(np.clip(u - sd_u, 0, 1)), graph.to_v(np.clip(u + sd_u, 0, 1))
    pred_sd = np.sqrt(np.einsum("ij,jk,ik->i", graph.Jp, graph.cov, graph.Jp))
    ths, _ = graph.thetas(u)
    rows_ps, rows_rs = graph.prediction_rows(), graph.residual_rows()
    views = []
    for b, (block, th) in enumerate(zip(graph.blocks, ths)):
        rows_p, rows_r = rows_ps[b], rows_rs[b]
        tau0 = float(np.exp(th["ln_tau0"]))
        pred = graph.prediction[rows_p]
        psd = pred_sd[rows_p]
        sigma_total = np.sqrt(block.sigma_meas**2 + block.s**2)
        dark = np.array([site.lifetime(th, tau0, water)[1] for site, water in block.points])
        loo = leave_one_out(graph, b, rows_p, rows_r)
        z = np.array([r["z"] for r in loo])
        outlier = np.abs(z) > limit
        rows = block.rows
        solvent = rows["solvent"] if "solvent" in rows.dtype.names else [""] * len(rows)
        table = make_result_table("fit_predictions", [
            dict(graph=graph_name, block=block.label, dye=block.dye, solvent=str(solvent[j]),
                 state=str(rows["state"][j]), site=int(rows["site"][j]),
                 tau_x=float(block.tau_x[j]), sigma_meas=float(block.sigma_meas[j]),
                 sigma_total=float(sigma_total[j]), tau_pred=float(pred[j]),
                 pred_sd=float(psd[j]), pred_low=float(pred[j] - psd[j]),
                 pred_high=float(pred[j] + psd[j]), dark_fraction=float(dark[j]),
                 loo_z=float(z[j]), outlier=bool(outlier[j]), used=bool(block.use[j]))
            for j in range(len(rows))
        ])
        estimates = []
        others = [x for x, lp in block.searches[1:]
                  if lp > block.searches[0][1] - float(fs["note_other_regions_logp"])]
        for j, (bb, name, i) in enumerate(graph.layout):
            if bb != b:
                continue
            spec = specs[name]
            width = (v_hi[j] - v_lo[j]) / (graph.hi[j] - graph.lo[j])
            edge = min(v[j] - graph.lo[j], graph.hi[j] - v[j]) < (
                float(fs["note_edge"]) * (graph.hi[j] - graph.lo[j]))
            note = "not determined" if width > float(fs["note_not_determined_width"]) else (
                "at the edge of its range" if edge else "")
            if any(not (v_lo[j] <= x[i] <= v_hi[j]) for x in others):
                note = (note + "; " if note else "") + "other regions possible"
            estimates.append(dict(
                graph=graph_name, block=block.label, dye=block.dye, parameter=spec.label,
                value=float(spec.to_natural(v[j])), low_68=float(spec.to_natural(v_lo[j])),
                high_68=float(spec.to_natural(v_hi[j])), note=note))
        estimates.append(dict(graph=graph_name, block=block.label, dye=block.dye,
                              parameter="model_error", value=block.s, low_68=block.s,
                              high_68=block.s, note="from the residuals of the best fit"))
        for name, value in block.fixed.items():
            spec = specs[name]
            nat = float(spec.to_natural(value))
            estimates.append(dict(graph=graph_name, block=block.label, dye=block.dye,
                                  parameter=spec.label, value=nat, low_68=nat, high_68=nat,
                                  note="fixed (not determined by these data)"))
        d = pred - block.tau_x
        loo_table = make_result_table("leave_one_out", [
            dict(graph=graph_name, block=block.label, site=r["site"],
                 state=r["state"], solvent=r["solvent"], z=r["z"]) for r in loo
        ])
        views.append(BlockResult(
            label=block.label, dye=block.dye, theta=th, tau0=tau0, model_error=block.s,
            table=table, estimates=make_result_table("fit_estimates", estimates),
            loo=loo_table, worst=_worst(loo),
            stats=dict(
                rms=float(np.sqrt((d**2).mean())),
                median_abs_dev=float(np.median(np.abs(d))),
                median_pred_sd=float(np.median(psd)),
                mean_dark_fraction=float(dark.mean()),
                outliers=sorted({int(s) for s in np.asarray(rows["site"])[outlier]}),
                n_outlier_lifetimes=int((~block.use).sum()),
                n_rows=int(len(rows)),
            ),
            graph=graph, block=block, index=b,
        ))
    return views


def site_ranking_table(view, graph_name=""):
    """Sites ranked by their worst left-out |z|.

    Parameters
    ----------
    view : BlockResult
    graph_name : str, optional

    Returns
    -------
    numpy.ndarray
        Declared ``site_ranking``.
    """
    return make_result_table("site_ranking", [
        dict(graph=graph_name, block=view.label, site=int(s), max_abs_z=float(z))
        for s, z in view.worst
    ])


def searches_table(view, graph_name=""):
    """Every robust search of a block, best first.

    Parameters
    ----------
    view : BlockResult
    graph_name : str, optional

    Returns
    -------
    numpy.ndarray
        Declared ``searches``.
    """
    block = view.block
    i = block.free.index("ln_scale") if "ln_scale" in block.free else None
    return make_result_table("searches", [
        dict(graph=graph_name, block=view.label, rank=k + 1, log_posterior=float(lp),
             scale=float(np.exp(x[i])) if i is not None else float("nan"))
        for k, (x, lp) in enumerate(block.searches)
    ])


def k_table(graph, graph_name=""):
    """The titration slopes before and after the lifetimes are added.

    Parameters
    ----------
    graph : Graph
        Solved.
    graph_name : str, optional

    Returns
    -------
    numpy.ndarray
        Declared ``graph_titration_slopes``.
    """
    sd_u = np.sqrt(np.diag(graph.cov))
    v = graph.to_v(graph.u)
    v_lo = graph.to_v(np.clip(graph.u - sd_u, 0, 1))
    v_hi = graph.to_v(np.clip(graph.u + sd_u, 0, 1))
    rows = []
    for j, (b, key, _) in enumerate(graph.layout):
        if b is not None:
            continue
        rows.append(dict(graph=graph_name, dye=key[0], amino_acid=key[1],
                         ksv_titration=graph.context.K_mean[key],
                         ksv_titration_sd=graph.context.K_sd[key],
                         ksv_graph=float(v[j]), low_68=float(v_lo[j]), high_68=float(v_hi[j])))
    return make_result_table("graph_titration_slopes", rows)


def fit_graph(blocks, seed=None, fit_settings=None, workers=None, progress=None, cancel=None,
              name="", titrated=None):
    """Search every block, fit the graph jointly, take the Laplace approximation.

    Parameters
    ----------
    blocks : sequence of Block
        A block that is already settled (:func:`search`, :func:`settle`, :func:`adopt`) is
        not searched again.
    seed : int, optional
        Block ``b`` searches from ``seed + block_seed_stride * b``; declared ``seed`` by
        default.
    fit_settings : dict, optional
        The first block's by default.
    workers : int, optional
        Worker processes for the searches and the Jacobian.
    progress : callable, optional
        ``progress(fraction, message)`` with fraction in [0, 1].
    cancel : callable, optional
        ``cancel() -> bool``; raises :class:`~..tasks.CancelledError` at the next checkpoint.
    name : str, optional
        Graph name for the tables.
    titrated : sequence of tuple, optional
        Every titrated (dye, amino_acid), for :func:`describe_graph`.

    Returns
    -------
    GraphResult
    """
    blocks = list(blocks)
    fs = fit_settings or blocks[0].settings
    seed = int(fs["seed"] if seed is None else seed)
    stride = int(fs["block_seed_stride"])
    n_steps = len(blocks) + 1

    def report(fraction, message):
        if progress:
            progress(min(max(fraction, 0.0), 1.0), message)

    for b, block in enumerate(blocks):
        def inner(done, total, label, b=b):
            report((b + done / total) / n_steps, f"{label} {done}/{total}")
        if block.best_x is None:
            search(block, seed + stride * b, fs, workers, inner, cancel)
        report((b + 1) / n_steps,
               f"{block.label}: model error {block.s:.3f} ns, "
               f"{int((~block.use).sum())} outlier lifetime(s)")
    graph = Graph(blocks, fs)
    report(len(blocks) / n_steps, "joint fit")
    joint_fit(graph, workers=workers, cancel=cancel)
    views = block_views(graph, name)
    structure = describe_graph(graph, titrated) if titrated is not None else None
    report(1.0, f"graph solved: {len(blocks)} data set(s), {graph.n_parameters} parameters, "
                f"{len(graph.k_keys)} titration slopes")
    return GraphResult(name=name, graph=graph, views=views, k_table=k_table(graph, name),
                       structure=structure)


# --------------------------------------------------------------------------------------------
# derived quantities


def propagate(view, function, step=None):
    """Value and error of any quantity of one block's parameters.

    Parameters
    ----------
    view : BlockResult
    function : callable
        ``function(theta) -> numbers``.
    step : float, optional
        Central-difference step in u; the declared ``jacobian_step`` by default.

    Returns
    -------
    tuple
        ``(value, sd)`` arrays (linear propagation through the graph covariance).
    """
    graph, b = view.graph, view.index
    step = float(graph.settings["jacobian_step"]) if step is None else step
    value = np.asarray(function(view.theta), float)
    J = []
    for i in range(len(graph.u)):
        up, down = graph.u.copy(), graph.u.copy()
        up[i] += step
        down[i] -= step
        J.append((np.asarray(function(graph.thetas(up)[0][b]), float)
                  - np.asarray(function(graph.thetas(down)[0][b]), float)) / (2 * step))
    J = np.array(J).T
    return value, np.sqrt(np.einsum("ij,jk,ik->i", J, graph.cov, J))


def _layout_index(view, name):
    """Graph-parameter index of one of a block's parameters.

    Parameters
    ----------
    view : BlockResult
    name : str
        Internal name.

    Returns
    -------
    int
    """
    for k, (bb, nn, _) in enumerate(view.graph.layout):
        if bb == view.index and nn == name:
            return k
    raise KeyError(f"{view.label}: {name!r} is not a fitted parameter")


def laplace_samples(view, name="ln_scale", n=None, seed=None):
    """Random values of one parameter as the Laplace approximation sees it.

    This is *not* a profile likelihood: it is the Gaussian of the curvature at the best fit,
    clipped to the range. Two blocks with the same curvature give the same histogram whatever
    the likelihood does away from the best fit.

    Parameters
    ----------
    view : BlockResult
    name : str, optional
        Internal name (``ln_scale`` by default).
    n : int, optional
        The declared ``profile_samples`` by default.
    seed : int, optional
        The declared ``profile_seed`` by default.

    Returns
    -------
    numpy.ndarray
        Natural units.
    """
    graph = view.graph
    fs = graph.settings
    j = _layout_index(view, name)
    n = int(fs["profile_samples"] if n is None else n)
    seed = int(fs["profile_seed"] if seed is None else seed)
    rng = np.random.default_rng(seed)
    u = np.clip(graph.u[j] + np.sqrt(graph.cov[j, j]) * rng.standard_normal(n), 0, 1)
    values = graph.lo[j] + (graph.hi[j] - graph.lo[j]) * u
    return np.exp(values) if name.startswith("ln_") else values


def sample_summary(values):
    """Median and 68 % range of samples.

    Parameters
    ----------
    values : numpy.ndarray

    Returns
    -------
    dict
        ``median``, ``low``, ``high``, ``factor`` (high/low).
    """
    lo, med, hi = np.percentile(values, [16, 50, 84])
    return dict(median=float(med), low=float(lo), high=float(hi), factor=float(hi / lo))


def profile_likelihood(view, name="ln_scale", values=None, max_nfev=None, cancel=None,
                       progress=None, workers=None):
    """A real profile likelihood of one block parameter.

    At each fixed value the block's sub-graph (the block and the titration slopes it reads,
    other parameters free, model error and inliers as found by the search) is refitted. The
    other blocks of the graph are left out, so a slope shared with another block is held only
    by its titration prior here.

    Parameters
    ----------
    view : BlockResult
    name : str, optional
        Internal name (``ln_scale`` by default).
    values : sequence of float, optional
        Internal values to profile at; by default the declared number of points within
        ``+- span_sd`` Laplace sds of the best fit, clipped to the range.
    max_nfev : int, optional
        Evaluation budget of each refit (scipy units) when the declared
        ``profile_likelihood.method`` is ``minpack`` (one process); ``polish`` refits with
        the projected Levenberg-Marquardt polish instead (``polish_iterations`` steps,
        Jacobians in *workers* processes).
    cancel : callable, optional
    progress : callable, optional
        ``progress(done, total, label)``.
    workers : int, optional
        Worker processes of the ``polish`` refits.

    Returns
    -------
    dict
        ``values`` (natural units), ``deviance`` (``2 (cost - cost_best)``, chi-square(1)
        scale), ``best`` (natural), ``low``/``high`` (natural, where the deviance crosses 1 by
        linear interpolation; the range end when it does not), ``name``.
    """
    fs = view.graph.settings
    opts = fs["profile_likelihood"]
    sub = Graph([view.block], fs)
    k_full = {key: j for j, (b, key, _) in enumerate(view.graph.layout) if b is None}
    j_full = _layout_index(view, name)
    v_full = view.graph.to_v(view.graph.u)
    # the sub-graph starts at the full graph's best fit
    v0 = []
    for b, key, i in sub.layout:
        if b is None:
            v0.append(v_full[k_full[key]])
        else:
            v0.append(v_full[_layout_index(view, key)])
    v0 = np.array(v0)
    j = [k for k, (b, key, _) in enumerate(sub.layout) if b == 0 and key == name][0]
    sd = np.sqrt(view.graph.cov[j_full, j_full]) * (sub.hi[j] - sub.lo[j])
    if values is None:
        span = float(opts["span_sd"]) * max(sd, 1e-3 * (sub.hi[j] - sub.lo[j]))
        values = np.linspace(max(sub.lo[j], v0[j] - span), min(sub.hi[j], v0[j] + span),
                             int(opts["points"]))
    values = np.asarray(values, float)
    budget = int(opts["max_nfev"] if max_nfev is None else max_nfev)
    free = np.array([k != j for k in range(len(v0))])
    lo, hi = sub.lo[free], sub.hi[free]

    method = str(opts.get("method", "minpack"))
    if method not in ("minpack", "polish"):
        raise ValueError(f"profile_likelihood.method must be minpack or polish, not {method!r}")
    pool = WorkerPool(dict(graph=sub.lean()), workers if method == "polish" else 1)

    def cost_at(value, start_free):
        if method == "polish":
            # the free coordinates are the sub-graph's own unit box
            u = np.empty(len(v0))
            u[free] = start_free
            u[j] = (value - sub.lo[j]) / (sub.hi[j] - sub.lo[j])
            u = np.clip(u, sub.u_clip, 1 - sub.u_clip)
            out = polish(sub, u, int(opts["polish_iterations"]), float(fs["joint_polish_rtol"]),
                         cancel=cancel, hold=[j], pool=pool)
            return float(out["cost"]), np.asarray(out["u"], float)[free]

        def residuals(w):
            _check(cancel)
            v = v0.copy()
            v[free] = lo + (hi - lo) * w
            v[j] = value
            return sub.evaluate(sub.to_u(v))[0]

        sol = _numerics.least_squares(residuals, start_free, bounds=(0.0, 1.0),
                                      diff_step=float(fs["joint_diff_step"]), max_nfev=budget)
        return float(sol.cost), np.asarray(sol.x, float)

    w0 = np.clip((v0[free] - lo) / (hi - lo), sub.u_clip, 1 - sub.u_clip)
    with pool:
        best_cost, w_best = cost_at(v0[j], w0)
        costs, starts = _walk_profile(values, v0[j], w_best, cost_at, progress, view.label)
    return _profile_summary(fs, name, values, costs, best_cost)


def _walk_profile(values, centre, w_best, cost_at, progress, label):
    """Profile costs, walking out from the best fit in both directions with warm starts.

    Parameters
    ----------
    values : numpy.ndarray
        Fixed values (internal units).
    centre : float
        The best fit's value.
    w_best : numpy.ndarray
        Free coordinates at the best fit.
    cost_at : callable
        ``cost_at(value, start) -> (cost, free coordinates)``.
    progress : callable or None
    label : str

    Returns
    -------
    tuple
        ``(costs, starts)``.
    """
    order = np.argsort(np.abs(values - centre))
    costs = np.full(len(values), np.nan)
    starts = {}
    for count, k in enumerate(order):
        neighbour = [m for m in starts if (values[m] - centre) * (values[k] - centre) >= 0]
        start = starts[min(neighbour, key=lambda m: abs(values[m] - values[k]))] if neighbour \
            else w_best
        costs[k], starts[k] = cost_at(values[k], start)
        if progress:
            progress(count + 1, len(values), f"{label}: profile")
    return costs, starts


def _profile_summary(fs, name, values, costs, best_cost):
    """Deviance and 68 % crossings of a profile.

    Parameters
    ----------
    fs : dict
        Fit settings.
    name : str
        Internal name.
    values, costs : numpy.ndarray
    best_cost : float

    Returns
    -------
    dict
        See :func:`profile_likelihood`.
    """
    best_cost = min(best_cost, float(np.nanmin(costs)))
    deviance = 2.0 * (costs - best_cost)
    spec = _spec_map(fs)[name]
    i_min = int(np.argmin(deviance))

    def crossing(indices):
        prev = i_min
        for k in indices:
            if deviance[k] >= 1.0:
                t = (1.0 - deviance[prev]) / (deviance[k] - deviance[prev])
                return values[prev] + t * (values[k] - values[prev])
            prev = k
        return values[indices[-1]] if len(indices) else values[i_min]

    low = crossing(list(range(i_min - 1, -1, -1)))
    high = crossing(list(range(i_min + 1, len(values))))
    return dict(name=spec.label, values=spec.to_natural(values), deviance=deviance,
                best=float(spec.to_natural(values[i_min])), low=float(spec.to_natural(low)),
                high=float(spec.to_natural(high)))


def describe_graph(graph, titrated):
    """The posterior's structure as IMP.bff's :class:`InferenceFactorGraph`.

    Parameters
    ----------
    graph : Graph
    titrated : sequence of tuple
        Every titrated ``(dye, amino_acid)`` (each one a likelihood of the shared day-to-day
        error).

    Returns
    -------
    dict
        ``variables``, ``likelihoods``, ``priors``, ``treewidth``, ``components`` (list of
        ``{"dyes", "slopes"}``), ``text`` (IMP.bff's description), ``factor_graph`` (the
        object).
    """
    from . import site_table as _site_table

    bff = _site_table._bff()
    g, index = bff.InferenceFactorGraph(), 0

    def var(key):
        nonlocal index
        g.add_variable(key, key, index, -1, 1, "")
        index += 1

    titrated = sorted(set(tuple(t) for t in titrated))
    for key in ["day_abs", "day_rel"] + [f"K:{d}:{a}" for d, a in titrated]:
        var(key)
    for d, a in titrated:
        g.add_factor(f"titration:{d}:{a}", bff.INFERENCE_FACTOR_LIKELIHOOD,
                     [f"K:{d}:{a}", "day_abs", "day_rel"], -1, 0)
    specs = _spec_map(graph.settings)
    for b, block in enumerate(graph.blocks):
        names = [f"{block.dye}:{specs[n].label}" for n in block.free if n != "ln_model_error"]
        for key in names:
            var(key)
        g.add_factor(f"lifetimes:{block.label}", bff.INFERENCE_FACTOR_LIKELIHOOD,
                     names + [f"K:{d}:{a}" for d, a in block.k_keys], b, 0)
        g.add_factor(f"stickiness prior:{block.dye}", bff.INFERENCE_FACTOR_PRIOR,
                     [k for k in names if ":s_" in k], b, 0)
    components = []
    for part in g.connected_components():
        dyes = sorted({k.split(":")[0] for k in part if ":" in k and not k.startswith("K:")})
        components.append(dict(dyes=dyes, slopes=sum(k.startswith("K:") for k in part)))
    return dict(
        variables=int(g.get_number_of_variables()),
        likelihoods=int(g.get_number_of_likelihood_factors()),
        priors=int(g.get_number_of_factors_of_kind(bff.INFERENCE_FACTOR_PRIOR)),
        treewidth=int(g.get_treewidth()),
        components=components,
        text=str(g.describe()),
        factor_graph=g,
    )
