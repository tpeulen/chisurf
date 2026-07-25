r"""One query API over every way ChiSurf can quantify a parameter's uncertainty.

ChiSurf can answer "what does the data actually support for this parameter?"
three ways -- the covariance at the optimum, a profile :math:`\chi^2` scan, and a
sampled posterior. All three are useful, all three had a completely different
calling convention, return shape and storage location, and a caller had to know
which one it wanted before it could ask anything.

This module puts them behind one protocol. Declare what should be computed, run,
read the answer:

.. code-block:: python

    engine = LaplaceEngine(fit)
    engine.add_target('tau1')
    engine.run()
    print(engine.marginal('tau1').interval(0.68))

The estimator becomes a choice of engine rather than different code at every
call site, and an answer (:class:`Marginal`, :class:`Joint`) carries the method
that produced it so a report or a plot can consume it without knowing.

Notes
-----
The shape of the interface is the one mature probabilistic graphical-model
toolkits settled on -- one model, many engines, ``setEvidence`` / ``addTarget``
/ ``makeInference`` / ``posterior``. Their discrete sum-product kernels do not
transfer to a continuous fluorescence posterior, but the query API does.
:mod:`chisurf.core.fitting.factorgraph` took the model and
:mod:`chisurf.core.fitting.sample` the inference; this is the query.

**Targets are declared, not assumed.** A profile scan of one parameter should
not scan the other nine. Nothing is computed that was not asked for.

**Conditioning** (``condition``) fixes a parameter and re-optimises the rest.
That is exactly what a profile scan does natively, and it is what the other two
engines do by construction -- so it means the same thing everywhere.
"""
from __future__ import annotations

import abc
import dataclasses
import math

import numpy as np

import chisurf as cs
from chisurf import typing

__all__ = [
    "Marginal",
    "Joint",
    "PosteriorEngine",
    "LaplaceEngine",
    "ProfileEngine",
    "SamplingEngine",
    "StoredEngine",
    "AutoEngine",
    "get_engine",
    "ENGINES",
]


@dataclasses.dataclass(frozen=True)
class Marginal:
    """What a single parameter's posterior looks like, whoever computed it.

    Attributes
    ----------
    name : str
        Parameter name.
    value : float
        Point estimate -- the optimum for a covariance or profile answer, the
        posterior mean for a sampled one.
    sd : float
        Standard deviation, or ``nan`` when the engine does not produce one.
    method : str
        Which engine produced this: ``laplace``, ``profile`` or ``mcmc``.
    quantiles : dict
        Probability (as ``float``) to value, when the engine has a sample.
    low, high : float
        The engine's native interval, at :attr:`p_value` coverage.
    p_value : float
        Coverage of ``low``/``high``.
    diagnostics : dict
        Engine-specific extras -- effective sample size and R-hat for a chain,
        the scan grid for a profile.
    """

    name: str
    value: float = float("nan")
    sd: float = float("nan")
    method: str = "none"
    quantiles: typing.Dict[float, float] = dataclasses.field(default_factory=dict)
    low: float = float("nan")
    high: float = float("nan")
    p_value: float = 0.68
    diagnostics: typing.Dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def interval(self, p: float = 0.68) -> typing.Tuple[float, float]:
        """Return the central credible/confidence interval at coverage ``p``.

        Uses the engine's stored quantiles when it has them, so a sampled
        posterior gives a genuinely asymmetric interval; falls back to the
        native interval when ``p`` matches it, and to a Gaussian ``value ± z·sd``
        otherwise.

        Parameters
        ----------
        p : float, optional
            Central probability mass.

        Returns
        -------
        tuple of float
            ``(low, high)``, either of which may be ``nan``.
        """
        if self.quantiles:
            lo = _closest(self.quantiles, 0.5 - 0.5 * p)
            hi = _closest(self.quantiles, 0.5 + 0.5 * p)
            if lo is not None and hi is not None:
                return lo, hi
        if abs(p - self.p_value) < 1e-9 and np.isfinite(self.low):
            return self.low, self.high
        if np.isfinite(self.sd):
            z = _normal_quantile(0.5 + 0.5 * p)
            return self.value - z * self.sd, self.value + z * self.sd
        return float("nan"), float("nan")

    def as_dict(self) -> typing.Dict[str, typing.Any]:
        """Return a JSON-friendly dictionary of this marginal."""
        return {
            "name": self.name,
            "value": self.value,
            "sd": self.sd,
            "method": self.method,
            "low": self.low,
            "high": self.high,
            "p_value": self.p_value,
            "quantiles": {str(k): v for k, v in self.quantiles.items()},
            "diagnostics": dict(self.diagnostics),
        }


@dataclasses.dataclass(frozen=True)
class Joint:
    """A joint answer over several parameters.

    Attributes
    ----------
    names : tuple of str
        The parameters, in the order of :attr:`mean` and :attr:`covariance`.
    mean : numpy.ndarray
        Point estimate per parameter.
    covariance : numpy.ndarray
        Covariance matrix.
    method : str
        Which engine produced this.
    samples : numpy.ndarray or None
        The draws themselves when the engine had them.
    """

    names: typing.Tuple[str, ...]
    mean: np.ndarray
    covariance: np.ndarray
    method: str = "none"
    samples: typing.Optional[np.ndarray] = None

    @property
    def correlation(self) -> np.ndarray:
        """Return the correlation matrix implied by :attr:`covariance`.

        This is the number a global fit is usually really after: a pair at
        ``±1`` is not two measurements but one.
        """
        sd = np.sqrt(np.diag(self.covariance))
        with np.errstate(divide="ignore", invalid="ignore"):
            corr = self.covariance / np.outer(sd, sd)
        return np.where(np.isfinite(corr), corr, np.nan)


def _closest(
        quantiles: typing.Dict[float, float],
        target: float,
        tolerance: float = 0.02
) -> typing.Optional[float]:
    """Return the stored quantile nearest ``target``, or ``None`` if none is close."""
    best, gap = None, tolerance
    for q, v in quantiles.items():
        d = abs(float(q) - target)
        if d <= gap:
            best, gap = float(v), d
    return best


def _normal_quantile(p: float) -> float:
    """Return the standard-normal quantile of ``p`` (Acklam's rational approximation).

    Used only to widen a Gaussian ``sd`` to a requested coverage, so a few
    decimal places are ample and pulling in SciPy for it is not warranted.
    """
    if not (0.0 < p < 1.0):
        return float("nan")
    # Symmetric about 1/2; solve for the upper tail and mirror.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    low, high = 0.02425, 1 - 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


class PosteriorEngine(abc.ABC):
    """Base class for every way of quantifying a fit's parameter uncertainty.

    Subclasses implement :meth:`run` and at least :meth:`marginal`. The rest --
    target bookkeeping, conditioning, parameter lookup -- is shared.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to query.
    model : chisurf.core.models.Model, optional
        Model whose parameters are queried. Defaults to
        :func:`chisurf.core.fitting.factorgraph.posterior_model`, so a
        :class:`~chisurf.core.fitting.fit.FitGroup` is queried about its *joint*
        posterior rather than its selected member's.
    """

    #: Short tag identifying the estimator in a :class:`Marginal`.
    method: str = "none"

    def __init__(self, fit, model=None):
        """Bind the engine to a fit (and optionally an explicit model)."""
        from chisurf.core.fitting import factorgraph
        self.fit = fit
        self.model = model if model is not None else factorgraph.posterior_model(fit)
        self._targets: typing.List[str] = []
        self._joint_targets: typing.List[typing.Tuple[str, ...]] = []
        self._evidence: typing.Dict[str, float] = {}
        self._marginals: typing.Dict[str, Marginal] = {}
        self._joints: typing.Dict[typing.Tuple[str, ...], Joint] = {}
        self._log_evidence: float = float("nan")
        self._ran = False

    # -- declaring the query ---------------------------------------------

    def condition(self, name: str, value: float) -> PosteriorEngine:
        """Fix a parameter at a value, to be marginalised over no longer.

        The counterpart of setting evidence on a graphical-model engine: the
        named parameter is held and everything else re-optimised around it.
        That is what a profile scan does natively, and what the other engines do
        by construction, so it means the same thing whichever engine is used.

        Parameters
        ----------
        name : str
            Parameter to condition on.
        value : float
            Value to hold it at.

        Returns
        -------
        PosteriorEngine
            ``self``, so calls chain.
        """
        self._evidence[str(name)] = float(value)
        self._ran = False
        return self

    def erase_evidence(self) -> PosteriorEngine:
        """Drop every conditioned parameter."""
        self._evidence.clear()
        self._ran = False
        return self

    def add_target(self, name: str) -> PosteriorEngine:
        """Request the marginal of one parameter.

        Only declared targets are computed -- a profile scan of one parameter
        should not scan the other nine.
        """
        name = str(name)
        if name not in self._targets:
            self._targets.append(name)
        self._ran = False
        return self

    def add_joint_target(self, names: typing.Sequence[str]) -> PosteriorEngine:
        """Request the joint answer over several parameters."""
        key = tuple(str(n) for n in names)
        if key not in self._joint_targets:
            self._joint_targets.append(key)
        self._ran = False
        return self

    def add_all_targets(self) -> PosteriorEngine:
        """Request the marginal of every free parameter."""
        for name in self.parameter_names:
            self.add_target(name)
        return self

    # -- reading the answer ----------------------------------------------

    @abc.abstractmethod
    def run(self, **options) -> PosteriorEngine:
        """Compute the declared targets.

        Returns
        -------
        PosteriorEngine
            ``self``, so calls chain.
        """
        raise NotImplementedError

    def marginal(self, name: str) -> Marginal:
        """Return the marginal of a parameter.

        Parameters
        ----------
        name : str
            Parameter name; must have been declared with :meth:`add_target`.

        Returns
        -------
        Marginal
            The answer. Its ``method`` is ``"none"`` when the engine could not
            produce one -- an unconverged chain, or a scan that did not bracket
            the minimum.

        Raises
        ------
        RuntimeError
            If :meth:`run` has not been called.
        """
        self._require_run()
        return self._marginals.get(str(name), Marginal(name=str(name)))

    def marginals(self) -> typing.List[Marginal]:
        """Return every computed marginal, in the order they were declared."""
        self._require_run()
        return [self.marginal(n) for n in self._targets]

    def joint(self, names: typing.Sequence[str]) -> typing.Optional[Joint]:
        """Return the joint answer over ``names``, or ``None`` if unavailable."""
        self._require_run()
        return self._joints.get(tuple(str(n) for n in names))

    def log_evidence(self) -> float:
        """Return the log marginal likelihood, or ``nan`` when not available.

        Only engines that integrate over the parameters can report this; a
        profile scan, which maximises rather than integrates, cannot.
        """
        self._require_run()
        return self._log_evidence

    # -- helpers ----------------------------------------------------------

    @property
    def parameter_names(self) -> typing.List[str]:
        """Names of the free parameters this engine can be asked about."""
        return list(self.model.parameter_names)

    def _require_run(self) -> None:
        """Raise unless :meth:`run` has been called since the last change."""
        if not self._ran:
            raise RuntimeError(
                "call run() before reading results; the query changed since the "
                "last run" if self._marginals else "call run() before reading results"
            )

    def _parameter(self, name: str):
        """Return the free parameter object called ``name``, or ``None``."""
        for p, n in zip(self.model.parameters, self.parameter_names):
            if n == str(name):
                return p
        return None

    def _owner(self, parameter) -> typing.Tuple[typing.Any, str]:
        """Return the fit that owns a parameter and the name it knows it by.

        A group's parameter names are prefixed (``3:tau``) because they have to
        be unique across members, but a member only knows its own (``tau``) and
        a per-fit operation such as a chi² scan looks the name up in that
        member's model. Resolving the owner is therefore not cosmetic: scanning
        the group would simply fail to find the parameter.
        """
        for local in list(getattr(self.model, "fits", []) or []):
            local_model = getattr(local, "model", None)
            if local_model is None:
                continue
            for q in local_model.parameters:
                if q is parameter:
                    return local, str(q.name)
        return self.fit, str(getattr(parameter, "name", ""))

    def _apply_evidence(self):
        """Fix every conditioned parameter and re-optimise the rest.

        Conditioning is not just pinning a value: the remaining parameters have
        to move to their best position *given* it, or the answer is the
        unconditioned one with a parameter overwritten. That re-fit is what a
        profile scan does at each of its points, and doing it here is what makes
        ``condition`` mean the same thing for every engine.

        A conditioned parameter is ``fixed``, so it leaves the free-parameter
        vector entirely -- and therefore has no marginal, which is the correct
        answer for something held at a known value.

        Returns
        -------
        tuple or None
            Opaque restore token for :meth:`_restore_evidence`.
        """
        if not self._evidence:
            return None
        # Snapshot every free value *before* fixing anything, so the re-fit can
        # be undone whatever it moves.
        before = [(p, float(p.value)) for p in self.model.parameters_all
                  if hasattr(p, "value")]
        fixed = []
        for name, value in self._evidence.items():
            p = self._parameter(name)
            if p is None:
                continue
            fixed.append((p, bool(p.fixed)))
            p.value = value
            p.fixed = True
        if fixed:
            try:
                self.fit.run()
            except Exception as e:
                cs.logging.warning(f"conditioning: re-fit failed ({e})")
        return before, fixed

    @staticmethod
    def _restore_evidence(restore) -> None:
        """Undo :meth:`_apply_evidence`, including the re-fit it performed."""
        if restore is None:
            return
        before, fixed = restore
        for p, was_fixed in fixed:
            p.fixed = was_fixed
        for p, value in before:
            try:
                p.value = value
            except Exception:
                pass


class LaplaceEngine(PosteriorEngine):
    r"""The quadratic approximation at the optimum.

    Free (the covariance is computed for the error bars anyway) and right
    whenever the posterior really is close to a parabola in :math:`\\chi^2`.
    The only engine that is always available.
    """

    method = "laplace"

    def run(self, **options) -> LaplaceEngine:
        """Compute the covariance at the current parameters.

        Parameters
        ----------
        **options
            ``p_value`` sets the interval coverage (default 0.68).

        Returns
        -------
        LaplaceEngine
            ``self``.
        """
        from chisurf.core.fitting import factorgraph
        p_value = float(options.get("p_value", 0.68))
        restore = self._apply_evidence()
        try:
            with factorgraph.frozen_structure(self.fit, self.model):
                names = self.parameter_names
                values = np.asarray(self.model.parameter_values, dtype=np.float64)
                # Explicitly over *this* engine's model: the default is
                # ``fit.model``, which for a group is one member.
                cov, used = cs.core.fitting.fit.covariance_matrix(
                    self.fit, model=self.model
                )
                cov = np.atleast_2d(np.asarray(cov, dtype=np.float64))
                index = {n: i for i, n in enumerate(names)}
                position = {int(u): k for k, u in enumerate(list(used))}

                self._marginals = {}
                z = _normal_quantile(0.5 + 0.5 * p_value)
                for name in self._targets:
                    i = index.get(name)
                    if i is None:
                        self._marginals[name] = Marginal(name=name)
                        continue
                    k = position.get(i)
                    sd = float(np.sqrt(cov[k, k])) if k is not None and cov.size else float("nan")
                    value = float(values[i]) if i < values.size else float("nan")
                    self._marginals[name] = Marginal(
                        name=name, value=value, sd=sd, method=self.method,
                        low=value - z * sd, high=value + z * sd, p_value=p_value,
                    )

                self._joints = {}
                for key in self._joint_targets:
                    rows = [position.get(index.get(n)) for n in key]
                    if any(r is None for r in rows):
                        continue
                    sub = cov[np.ix_(rows, rows)]
                    mean = np.array([values[index[n]] for n in key], dtype=np.float64)
                    self._joints[key] = Joint(
                        names=key, mean=mean, covariance=sub, method=self.method
                    )

                self._log_evidence = self._laplace_evidence(cov)
        finally:
            self._restore_evidence(restore)
        self._ran = True
        return self

    def _laplace_evidence(self, cov: np.ndarray) -> float:
        r"""Return the Laplace approximation to :math:`\ln p(D)`.

        ``-chi2/2 + (d/2)ln(2 pi) + (1/2)ln det Sigma`` at the optimum.
        """
        try:
            chi2 = float(
                (np.asarray(self.model.weighted_residuals, dtype=np.float64) ** 2).sum()
            )
            d = cov.shape[0]
            sign, logdet = np.linalg.slogdet(cov)
            if sign <= 0 or not np.isfinite(logdet):
                return float("nan")
            return -0.5 * chi2 + 0.5 * (d * math.log(2.0 * math.pi) + logdet)
        except Exception:
            return float("nan")


class ProfileEngine(PosteriorEngine):
    """A chi² scan that re-optimises everything else at each point.

    Copes with asymmetric and skewed intervals that the quadratic approximation
    cannot, at the cost of a full re-fit per scan point, and only one parameter
    at a time -- so it has no joint answer and no evidence.
    """

    method = "profile"

    def run(self, **options) -> ProfileEngine:
        """Scan each declared target.

        Parameters
        ----------
        **options
            ``p_value`` (default 0.68) and anything
            :meth:`chisurf.core.fitting.fit.Fit.adaptive_chi2_scan` accepts.

        Returns
        -------
        ProfileEngine
            ``self``.
        """
        p_value = float(options.pop("p_value", 0.68))
        restore = self._apply_evidence()
        try:
            values = np.asarray(self.model.parameter_values, dtype=np.float64)
            index = {n: i for i, n in enumerate(self.parameter_names)}
            self._marginals = {}
            for name in self._targets:
                i = index.get(name)
                value = float(values[i]) if i is not None and i < values.size else float("nan")
                p = self._parameter(name)
                owner, local_name = self._owner(p) if p is not None else (self.fit, name)
                try:
                    scan = owner.adaptive_chi2_scan(
                        parameter_name=local_name, p_value=max(p_value, 0.9), **options
                    )
                except Exception as e:
                    cs.logging.warning(f"profile scan of {name} failed: {e}")
                    self._marginals[name] = Marginal(name=name, value=value)
                    continue
                low = high = float("nan")
                method = "none"
                try:
                    intervals = cs.core.fitting.support_plane.\
                        confidence_intervals_from_scan_result(scan, p_values=(p_value,))
                except Exception:
                    intervals = []
                if intervals:
                    lo, hi = intervals[0].get("crossings", (None, None))
                    if lo is not None or hi is not None:
                        low = float(lo) if lo is not None else float("nan")
                        high = float(hi) if hi is not None else float("nan")
                        method = self.method
                # A profile interval is generally asymmetric, so quoting one
                # standard deviation means the half-width only when it is not.
                sd = (high - low) / 2.0 if np.isfinite(low) and np.isfinite(high) \
                    else float("nan")
                self._marginals[name] = Marginal(
                    name=name, value=value, sd=sd, method=method,
                    low=low, high=high, p_value=p_value,
                    diagnostics={"scan": scan},
                )
        finally:
            self._restore_evidence(restore)
        self._joints = {}
        self._log_evidence = float("nan")
        self._ran = True
        return self


class SamplingEngine(PosteriorEngine):
    """A sampled posterior — the only engine with genuine joint answers.

    Assumes nothing beyond convergence of the chain, and is the only engine that
    reports whether its own answer is trustworthy: a marginal from a chain that
    failed its R-hat / effective-sample-size checks is **refused** rather than
    returned, because a quantile of an unconverged chain is a number without a
    meaning.
    """

    method = "mcmc"

    def run(self, **options) -> SamplingEngine:
        """Sample the posterior and summarise the declared targets.

        Parameters
        ----------
        **options
            ``steps`` (default 3000), ``n_runs`` (default 2), ``p_value``
            (default 0.68), ``method`` (default ``blocked``; ``de`` needs
            neither a gradient nor a covariance and is the robust choice away
            from the optimum), plus anything the chosen sampler accepts.

        Returns
        -------
        SamplingEngine
            ``self``.
        """
        from chisurf.core.fitting import diagnostics as dg

        p_value = float(options.pop("p_value", 0.68))
        steps = int(options.pop("steps", 3000))
        n_runs = max(2, int(options.pop("n_runs", 2)))
        backend = str(options.pop("method", "blocked"))
        options.setdefault("thin", 1)

        sampler = {
            "blocked": cs.core.fitting.sample.sample_independent_components,
            "collapsed": cs.core.fitting.sample.sample_marginal_shared,
            "de": cs.core.fitting.sample.sample_differential_evolution,
            "mcmc": cs.core.fitting.sample.walk_mcmc,
        }.get(backend)
        if sampler is None:
            raise ValueError(f"unknown sampling backend {backend!r}")

        restore = self._apply_evidence()
        runs = []
        try:
            for _ in range(n_runs):
                runs.append(sampler(
                    fit=self.fit, steps=steps, model=self.model, **options
                ))
        finally:
            self._restore_evidence(restore)

        chains = cs.core.fitting.fit.pool_chains(runs)
        names = list(runs[0]["parameter_names"]) if runs else self.parameter_names
        if chains is None:
            self._marginals = {n: Marginal(name=n) for n in self._targets}
            self._joints, self._log_evidence, self._ran = {}, float("nan"), True
            return self

        summary = dg.summarize(chains, names=names)
        by_name = {e["name"]: e for e in summary}
        burn = summary[0]["burn_in"] if summary else 0
        kept = chains[:, burn:, :]
        flat = kept.reshape(-1, kept.shape[2])
        index = {n: i for i, n in enumerate(names)}

        self._marginals = {}
        for name in self._targets:
            entry = by_name.get(name)
            if entry is None:
                self._marginals[name] = Marginal(name=name)
                continue
            converged = (
                np.isfinite(entry["rhat"]) and entry["rhat"] <= dg.RHAT_THRESHOLD
                and np.isfinite(entry["ess"]) and entry["ess"] >= dg.ESS_THRESHOLD
            )
            quantiles = {float(k): float(v) for k, v in entry["quantiles"].items()}
            lo = _closest(quantiles, 0.5 - 0.5 * p_value)
            hi = _closest(quantiles, 0.5 + 0.5 * p_value)
            self._marginals[name] = Marginal(
                name=name,
                value=float(entry["mean"]),
                sd=float(entry["sd"]),
                # Refuse to label an unconverged answer as an answer.
                method=self.method if converged else "none",
                quantiles=quantiles if converged else {},
                low=float(lo) if converged and lo is not None else float("nan"),
                high=float(hi) if converged and hi is not None else float("nan"),
                p_value=p_value,
                diagnostics={
                    "ess": entry["ess"], "rhat": entry["rhat"],
                    "tau": entry["tau"], "mcse": entry["mcse"],
                    "converged": bool(converged), "burn_in": burn,
                },
            )

        self._joints = {}
        for key in self._joint_targets:
            cols = [index.get(n) for n in key]
            if any(c is None for c in cols):
                continue
            sub = flat[:, cols]
            self._joints[key] = Joint(
                names=key, mean=sub.mean(axis=0),
                covariance=np.cov(sub, rowvar=False).reshape(len(cols), len(cols)),
                method=self.method, samples=sub,
            )

        self._log_evidence = float("nan")
        self._ran = True
        return self


class StoredEngine(PosteriorEngine):
    """Whatever has *already* been computed, without computing anything new.

    The other engines produce an answer; this one reports the answers lying
    around from earlier work -- the covariance error estimates a fit leaves on
    its parameters, a profile scan's ``scan_result``, and the convergence report
    a sampling run leaves on the fit. That is a genuinely different operation
    from running an estimator, and it is what a summary table wants: reading it
    must never kick off a chi² scan or an MCMC run.

    Answers are ranked the same way as :class:`AutoEngine` -- a sampled
    posterior outranks a profile scan outranks the quadratic approximation --
    and an unconverged chain is skipped rather than quoted.
    """

    method = "stored"

    def __init__(self, fit, model=None):
        """Bind to the model whose *names* the stored results are keyed by.

        Stored answers come from per-fit operations -- a scan on a member's
        parameter, a sampling run over whatever model was sampled -- so the
        default is ``fit.model`` rather than the group's global model, whose
        prefixed names would match nothing.
        """
        super().__init__(fit, model=model if model is not None else getattr(fit, "model", None))

    def run(self, **options) -> StoredEngine:
        """Collect the stored answers for the declared targets.

        Parameters
        ----------
        **options
            ``p_value`` sets the requested coverage (default 0.68).

        Returns
        -------
        StoredEngine
            ``self``.
        """
        p_value = float(options.get("p_value", 0.68))
        chain = self._stored_chain(p_value)
        self._marginals = {}
        for name in self._targets:
            p = self._parameter(name)
            if p is None:
                self._marginals[name] = Marginal(name=name, p_value=p_value)
                continue
            try:
                value = float(p.value)
            except (TypeError, ValueError):
                self._marginals[name] = Marginal(name=name, p_value=p_value)
                continue

            entry = chain.get(name)
            if entry is not None:
                self._marginals[name] = entry
                continue

            scan = getattr(p, "scan_result", None)
            if isinstance(scan, dict):
                low, high = self._scan_interval(scan, p_value)
                if np.isfinite(low) or np.isfinite(high):
                    self._marginals[name] = Marginal(
                        name=name, value=value, method="profile",
                        low=low, high=high, p_value=p_value,
                        sd=(high - low) / 2.0 if np.isfinite(low) and np.isfinite(high)
                        else float("nan"),
                        diagnostics={"scan": scan},
                    )
                    continue

            try:
                err = float(p.error_estimate)
            except (TypeError, ValueError):
                err = float("nan")
            if np.isfinite(err):
                self._marginals[name] = Marginal(
                    name=name, value=value, sd=err, method="laplace",
                    low=value - err, high=value + err, p_value=p_value,
                )
            else:
                self._marginals[name] = Marginal(
                    name=name, value=value, p_value=p_value
                )

        self._joints = {}
        self._log_evidence = float("nan")
        self._ran = True
        return self

    def _stored_chain(self, p_value: float) -> typing.Dict[str, Marginal]:
        """Return marginals from a stored sampling report, keyed by name."""
        from chisurf.core.fitting import diagnostics as dg
        report = getattr(self.fit, "sampling_diagnostics", None)
        if not isinstance(report, dict):
            return {}
        out = {}
        for e in report.get("parameters") or []:
            rhat, ess = e.get("rhat", float("nan")), e.get("ess", 0.0)
            if not (np.isfinite(rhat) and rhat <= dg.RHAT_THRESHOLD):
                continue
            if not (np.isfinite(ess) and ess >= dg.ESS_THRESHOLD):
                continue
            quantiles = {float(k): float(v) for k, v in (e.get("quantiles") or {}).items()}
            lo = _closest(quantiles, 0.5 - 0.5 * p_value)
            hi = _closest(quantiles, 0.5 + 0.5 * p_value)
            if lo is None or hi is None:
                continue
            out[str(e.get("name"))] = Marginal(
                name=str(e.get("name")), value=float(e.get("mean", float("nan"))),
                sd=float(e.get("sd", float("nan"))), method="mcmc",
                quantiles=quantiles, low=float(lo), high=float(hi),
                p_value=p_value,
                diagnostics={"ess": ess, "rhat": rhat, "converged": True},
            )
        return out

    @staticmethod
    def _scan_interval(scan: dict, p_value: float) -> typing.Tuple[float, float]:
        """Return the profile crossings of a stored scan at ``p_value``."""
        try:
            intervals = cs.core.fitting.support_plane.\
                confidence_intervals_from_scan_result(scan, p_values=(p_value,))
        except Exception:
            return float("nan"), float("nan")
        if not intervals:
            return float("nan"), float("nan")
        lo, hi = intervals[0].get("crossings", (None, None))
        return (
            float(lo) if lo is not None else float("nan"),
            float(hi) if hi is not None else float("nan"),
        )


class AutoEngine(PosteriorEngine):
    """The best answer available per parameter, without being told which.

    Runs the engines in decreasing order of fidelity and takes, for each
    parameter, the first that produced a real answer: a sampled posterior
    outranks a profile scan (which handles one parameter at a time) which
    outranks the quadratic approximation. Nothing is *computed* that is not
    already there -- only the engines named in ``use`` are run, and by default
    that is the free one.
    """

    method = "auto"

    #: Engines in decreasing order of fidelity.
    ORDER = ("mcmc", "profile", "laplace")

    def __init__(self, fit, model=None, use=("laplace",)):
        """Bind the engine and choose which estimators may be run.

        Parameters
        ----------
        fit, model
            See :class:`PosteriorEngine`.
        use : sequence of str, optional
            Which estimators to run. Defaults to ``("laplace",)`` -- the one
            that costs nothing.
        """
        super().__init__(fit, model=model)
        self.use = tuple(str(u) for u in use)

    def run(self, **options) -> AutoEngine:
        """Run the selected engines and merge their answers by fidelity."""
        answers: typing.Dict[str, typing.List[Marginal]] = {}
        joints: typing.Dict[typing.Tuple[str, ...], Joint] = {}
        evidence = float("nan")

        for tag in self.ORDER:
            if tag not in self.use:
                continue
            engine = ENGINES[tag](self.fit, model=self.model)
            engine._targets = list(self._targets)
            engine._joint_targets = list(self._joint_targets)
            engine._evidence = dict(self._evidence)
            try:
                engine.run(**options)
            except Exception as e:
                cs.logging.warning(f"{tag} engine failed: {e}")
                continue
            for name in self._targets:
                answers.setdefault(name, []).append(engine.marginal(name))
            for key in self._joint_targets:
                j = engine.joint(key)
                if j is not None and key not in joints:
                    joints[key] = j
            if not np.isfinite(evidence):
                evidence = engine.log_evidence()

        rank = {tag: i for i, tag in enumerate(self.ORDER)}
        self._marginals = {}
        for name in self._targets:
            candidates = [m for m in answers.get(name, []) if m.method in rank]
            if candidates:
                self._marginals[name] = min(candidates, key=lambda m: rank[m.method])
            else:
                fallback = answers.get(name) or [Marginal(name=name)]
                self._marginals[name] = fallback[0]
        self._joints = joints
        self._log_evidence = evidence
        self._ran = True
        return self


#: Engine tag -> class, for :func:`get_engine` and the ``auto`` merge.
ENGINES: typing.Dict[str, typing.Type[PosteriorEngine]] = {
    "laplace": LaplaceEngine,
    "profile": ProfileEngine,
    "mcmc": SamplingEngine,
    "stored": StoredEngine,
    "auto": AutoEngine,
}


def get_engine(name: str, fit, model=None, **kwargs) -> PosteriorEngine:
    """Return an engine by name.

    Parameters
    ----------
    name : {"laplace", "profile", "mcmc", "stored", "auto"}
        Which estimator to use.
    fit : chisurf.core.fitting.fit.Fit
        Fit to query.
    model : chisurf.core.models.Model, optional
        Model to query; see :class:`PosteriorEngine`.
    **kwargs
        Forwarded to the engine's constructor.

    Returns
    -------
    PosteriorEngine
        The engine.

    Raises
    ------
    ValueError
        If ``name`` is not a known engine.
    """
    try:
        cls = ENGINES[str(name)]
    except KeyError:
        raise ValueError(
            f"unknown posterior engine {name!r}; expected one of {sorted(ENGINES)}"
        ) from None
    return cls(fit, model=model, **kwargs)
