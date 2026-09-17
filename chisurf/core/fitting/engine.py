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
/ ``makeInference`` / ``posterior``. Their discrete-table kernels do not transfer
to a continuous fluorescence posterior; their linear-Gaussian one does, and it
is ``IMP.bff.InferenceCanonicalForm`` / ``IMP.bff.InferenceGaussianElimination``.
:mod:`chisurf.core.fitting.factorgraph` took the model and
:mod:`chisurf.core.fitting.sample` the inference; this is the query.

**Targets are declared, not assumed.** A profile scan of one parameter should
not scan the other nine. Nothing is computed that was not asked for.

**Conditioning** (``condition``) holds a parameter and answers for the rest at
their best position given it -- the same question for every engine, answered
two ways:

- in **closed form** by the engines that assume a Gaussian posterior
  (``gaussian``, and ``laplace`` whenever the answer is certified): the
  conditional of a Gaussian in canonical form, a Schur complement computed in
  ``IMP.bff``, with no re-fit;
- by **re-optimisation** -- fix the parameter, run the optimiser -- where the
  posterior is not Gaussian in those parameters: ``profile`` and ``mcmc``
  always, since not assuming a Gaussian is what they are for, and ``laplace``
  when the closed-form answer fails its certificate (a bound in the way, or a
  model visibly non-linear between the optimum and the conditional mode).
  Every conditioned marginal says which in ``diagnostics["conditioning"]``.
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
    "GaussianEngine",
    "ProfileEngine",
    "SamplingEngine",
    "StoredEngine",
    "AutoEngine",
    "get_engine",
    "ENGINES",
    "gaussian_validity",
    "marginal_asymmetry",
    "sample_asymmetry",
    "asymmetry_threshold",
    "ASYMMETRY_FLOOR",
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
    quantiles: typing.Dict[float, float], target: float, tolerance: float = 0.02
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
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    low, high = 0.02425, 1 - 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


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
        named parameter is held and the rest are reported at their best position
        given it. Engines that assume a Gaussian posterior answer in closed form
        (a Schur complement); ``profile`` and ``mcmc`` re-optimise, because they
        exist for posteriors that are not Gaussian. See the module notes.

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
                "call run() before reading results; the query changed since the last run"
                if self._marginals
                else "call run() before reading results"
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

    def _symmetry_diagnostics(
        self,
        name: str,
        p_value: float,
    ) -> typing.Dict[str, typing.Any]:
        """Return diagnostics flagging a symmetric interval on a skewed posterior.

        Called wherever an engine builds a ``value ± sd`` marginal. When a chain
        is on the fit the evidence is free, and quoting a symmetric interval
        without checking it is the quiet failure this closes: the number looks
        the same either way.

        Parameters
        ----------
        name : str
            Parameter whose marginal is being built.
        p_value : float
            Coverage of the interval being quoted.

        Returns
        -------
        dict
            ``{"asymmetry": ...}`` when a chain shows the posterior is skewed;
            empty otherwise, including when there is no chain -- absence of
            evidence is not evidence of symmetry.
        """
        try:
            evidence = marginal_asymmetry(self.fit, name, p_value=p_value)
        except Exception:
            return {}
        if evidence is None or evidence.get("gaussian_ok", True):
            return {}
        return {"asymmetry": evidence, "warning": evidence["note"]}

    def _apply_evidence(self):
        """Fix every conditioned parameter and re-optimise the rest.

        Conditioning is not just pinning a value: the remaining parameters have
        to move to their best position *given* it, or the answer is the
        unconditioned one with a parameter overwritten. That re-fit is what a
        profile scan does at each of its points. It is the path for posteriors
        that are not Gaussian in the held parameters; where they are, the
        Gaussian engines answer the same question in closed form.

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
        before = [(p, float(p.value)) for p in self.model.parameters_all if hasattr(p, "value")]
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

    def _restore_evidence(self, restore) -> None:
        """Undo :meth:`_apply_evidence`, including the re-fit it performed.

        Putting the parameter values back is only half of it: the re-fit also
        recomputed the model curve, the weighted residuals and chi2. Without a
        final ``update`` the fit is left in a state no fit can legitimately be
        in -- the unconditioned parameters under the conditioned curve -- and
        everything downstream (the chi2 display, plots, the next covariance)
        reads it.
        """
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
        try:
            self.fit.update()
        except Exception:
            pass


def _single(form, name: str) -> typing.Tuple[float, float]:
    """Return the mean and standard deviation of one variable of a canonical form."""
    single = form.marginal([name])
    return float(single.get_mean()[0]), float(math.sqrt(single.get_covariance()[0]))


def _curvature_form(engine, **options):
    """Return the canonical form of the quadratic approximation at the optimum.

    The covariance over the parameters the model responds to, held as an
    ``IMP.bff.InferenceCanonicalForm`` whose mass is the Laplace evidence. The
    caller holds the structure frozen.

    Parameters
    ----------
    engine : PosteriorEngine
        Engine whose fit and model are evaluated.
    **options
        Passed to :func:`chisurf.core.fitting.fit.covariance_matrix`.

    Returns
    -------
    IMP.bff.InferenceCanonicalForm or None
        ``None`` when the curvature is unusable.
    """
    import IMP.bff

    names = engine.parameter_names
    values = np.asarray(engine.model.parameter_values, dtype=np.float64)
    try:
        cov, used = cs.core.fitting.fit.covariance_matrix(engine.fit, model=engine.model, **options)
    except Exception as e:
        cs.logging.warning(f"{engine.method} engine: no covariance ({e})")
        return None
    cov = np.atleast_2d(np.asarray(cov, dtype=np.float64))
    used = [int(u) for u in used]
    if cov.size == 0 or len(used) != cov.shape[0]:
        return None
    # ``covariance_matrix`` drops parameters the model does not respond to;
    # those directions carry no information and simply are not in the scope.
    keep = [k for k, u in enumerate(used) if 0 <= u < len(names)]
    if not keep:
        return None
    sub = cov[np.ix_(keep, keep)]
    scope = [names[used[k]] for k in keep]
    mean = np.array([values[used[k]] for k in keep], dtype=np.float64)
    try:
        return IMP.bff.InferenceCanonicalForm.from_moments(
            scope, mean, np.ascontiguousarray(sub).ravel(), _laplace_log_evidence(engine, sub)
        )
    except ValueError as e:
        cs.logging.warning(f"{engine.method} engine: covariance not usable ({e})")
        return None


def _laplace_log_evidence(engine, cov: np.ndarray) -> float:
    r"""Return the Laplace evidence at the current parameters, or 0 when undefined.

    ``-chi2/2 + (d/2) ln(2 pi) + (1/2) ln det Sigma``. As a form's mass it makes
    ``get_log_normalizer()`` the evidence, which marginalising leaves unchanged.
    """
    try:
        chi2 = float((np.asarray(engine.model.weighted_residuals, dtype=np.float64) ** 2).sum())
        sign, logdet = np.linalg.slogdet(cov)
        if sign <= 0 or not np.isfinite(logdet):
            return 0.0
        return -0.5 * chi2 + 0.5 * (cov.shape[0] * math.log(2.0 * math.pi) + logdet)
    except Exception:
        return 0.0


class LaplaceEngine(PosteriorEngine):
    r"""The quadratic approximation at the optimum.

    Free (the covariance is computed for the error bars anyway) and right
    whenever the posterior really is close to a parabola in :math:`\\chi^2`.
    The only engine that is always available.

    ``condition`` is answered in closed form -- the Gaussian conditional, a
    Schur complement in ``IMP.bff`` -- when one Jacobian at the conditional mode
    certifies that a re-fit would return the same answer
    (:meth:`_closed_form_condition`); otherwise, or with ``run(closed_form=False)``,
    the held parameter is fixed and the rest re-optimised. The marginals say
    which in ``diagnostics["conditioning"]``, with the reason for a re-fit.
    """

    method = "laplace"

    def run(self, **options) -> LaplaceEngine:
        """Compute the covariance at the current parameters.

        Parameters
        ----------
        **options
            ``p_value`` sets the interval coverage (default 0.68).
            ``closed_form`` (default ``True``) answers a conditioned query in
            closed form when that answer is certified; ``False`` always
            re-optimises.

        Returns
        -------
        LaplaceEngine
            ``self``.
        """
        from chisurf.core.fitting import factorgraph

        p_value = float(options.get("p_value", 0.68))
        conditioning = {}
        if self._evidence:
            if options.get("closed_form", True):
                refused = self._closed_form_condition(p_value)
                if refused is None:
                    self._ran = True
                    return self
                conditioning = {"conditioning": "re_optimised", "why": refused}
            else:
                conditioning = {"conditioning": "re_optimised", "why": "closed_form=False"}
        restore = self._apply_evidence()
        try:
            with factorgraph.frozen_structure(self.fit, self.model):
                names = self.parameter_names
                values = np.asarray(self.model.parameter_values, dtype=np.float64)
                # Explicitly over *this* engine's model: the default is
                # ``fit.model``, which for a group is one member.
                cov, used = cs.core.fitting.fit.covariance_matrix(self.fit, model=self.model)
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
                        name=name,
                        value=value,
                        sd=sd,
                        method=self.method,
                        low=value - z * sd,
                        high=value + z * sd,
                        p_value=p_value,
                        diagnostics={**self._symmetry_diagnostics(name, p_value), **conditioning},
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

    #: Largest Newton step, in conditional standard deviations, that still
    #: certifies the closed-form conditional mode as the optimum a re-fit finds.
    CERTIFY_STEP = 1e-3

    #: Largest relative change of the conditional curvature between the optimum
    #: and the conditional mode that still certifies the closed-form width.
    CERTIFY_CURVATURE = 1e-6

    def _closed_form_condition(self, p_value: float) -> typing.Optional[str]:
        """Answer the conditioned query in closed form, if that answer is certified.

        The closed form is the conditional of the Gaussian at the optimum: a
        Schur complement of its canonical form, computed in ``IMP.bff``. It is
        the answer a re-fit gives exactly when the objective is quadratic in the
        parameters between the optimum and the conditional mode -- a model linear
        in them, with no bound in the way. That is checked rather than assumed,
        with one Jacobian at the conditional mode instead of a fit:

        - the mode is inside every bound;
        - it is stationary: the Newton step there is below
          :attr:`CERTIFY_STEP` conditional standard deviations, so a re-fit
          would not move;
        - the curvature there equals the conditional precision to
          :attr:`CERTIFY_CURVATURE`, so a re-fit's covariance would not change.

        Parameters
        ----------
        p_value : float
            Interval coverage of the marginals.

        Returns
        -------
        str or None
            ``None`` when the query was answered (marginals, joints and evidence
            are set); otherwise why not, and the caller re-optimises.
        """
        from chisurf.core.fitting import factorgraph

        with factorgraph.frozen_structure(self.fit, self.model):
            form = _curvature_form(self)
            if form is None:
                return "no usable curvature at the optimum"
            scope = list(form.get_names())
            held = dict(self._evidence)
            unknown = sorted(k for k in held if k not in scope)
            if unknown:
                return f"not in the curvature: {unknown}"
            conditional = form.condition(list(held), [float(v) for v in held.values()])
            free = list(conditional.get_names())
            if not free:
                return "nothing is left free"
            if not conditional.get_is_proper():
                return "the conditional precision is singular"
            mean = np.asarray(conditional.get_mean(), dtype=np.float64)
            d = len(free)
            cov = np.asarray(conditional.get_covariance(), dtype=np.float64).reshape(d, d)
            precision = np.asarray(conditional.get_precision(), dtype=np.float64).reshape(d, d)
            sd = np.sqrt(np.diag(cov))

            point = dict(zip(free, mean))
            point.update({k: float(v) for k, v in held.items()})
            for name, value in point.items():
                p = self._parameter(name)
                if p is not None and getattr(p, "bounds_on", False):
                    lb, ub = p.bounds
                    if (lb is not None and value < lb) or (ub is not None and value > ub):
                        return f"{name} = {value:.6g} at the conditional mode is outside its bounds"

            before = [(p, float(p.value)) for p in self.model.parameters_all if hasattr(p, "value")]
            try:
                for name, value in point.items():
                    self._parameter(name).value = value
                xk = np.asarray(self.model.parameter_values, dtype=np.float64)
                f0, jacobian = cs.core.fitting.fit.approx_grad(xk, self.fit, model=self.model)
            finally:
                for p, value in before:
                    try:
                        p.value = value
                    except (TypeError, ValueError):
                        continue
                try:
                    self.fit.update()
                except Exception:
                    pass
            residuals = np.asarray(f0, dtype=np.float64).ravel()
            index = {n: i for i, n in enumerate(self.parameter_names)}
            j_free = np.asarray(jacobian, dtype=np.float64)[[index[n] for n in free]]
            step = cov @ (j_free @ residuals)
            worst_step = float(np.max(np.abs(step) / sd))
            curvature = j_free @ j_free.T
            change = float(np.linalg.norm(curvature - precision) / np.linalg.norm(precision))
            if not (worst_step <= self.CERTIFY_STEP):
                return f"not stationary at the conditional mode (Newton step {worst_step:.3g} sd)"
            if not (change <= self.CERTIFY_CURVATURE):
                return f"the curvature changes by {change:.3g} between optimum and conditional mode"

        certificate = {
            "conditioning": "closed_form",
            "newton_step_sd": worst_step,
            "curvature_change": change,
        }
        z = _normal_quantile(0.5 + 0.5 * p_value)
        self._marginals = {}
        for name in self._targets:
            if name in free:
                k = free.index(name)
                value, width = float(mean[k]), float(sd[k])
                self._marginals[name] = Marginal(
                    name=name,
                    value=value,
                    sd=width,
                    method=self.method,
                    low=value - z * width,
                    high=value + z * width,
                    p_value=p_value,
                    diagnostics={**self._symmetry_diagnostics(name, p_value), **certificate},
                )
            elif name in held or self._parameter(name) is None:
                # Held, so no marginal of its own -- or not a parameter at all.
                self._marginals[name] = Marginal(name=name, p_value=p_value)
            else:
                # Free but outside the curvature: the model does not respond to it.
                value = float(self._parameter(name).value)
                self._marginals[name] = Marginal(
                    name=name, value=value, method=self.method, p_value=p_value,
                    diagnostics=dict(certificate),
                )
        self._joints = {}
        for key in self._joint_targets:
            if any(n not in free for n in key):
                continue
            block = conditional.marginal(list(key))
            self._joints[key] = Joint(
                names=key,
                mean=np.asarray(block.get_mean(), dtype=np.float64),
                covariance=np.asarray(block.get_covariance(), dtype=np.float64).reshape(len(key), len(key)),
                method=self.method,
            )
        chi2 = float(residuals @ residuals)
        sign, logdet = np.linalg.slogdet(cov)
        self._log_evidence = (
            -0.5 * chi2 + 0.5 * (d * math.log(2.0 * math.pi) + logdet) if sign > 0 else float("nan")
        )
        return None

    def _laplace_evidence(self, cov: np.ndarray) -> float:
        r"""Return the Laplace approximation to :math:`\ln p(D)`.

        ``-chi2/2 + (d/2)ln(2 pi) + (1/2)ln det Sigma`` at the optimum.
        """
        try:
            chi2 = float((np.asarray(self.model.weighted_residuals, dtype=np.float64) ** 2).sum())
            d = cov.shape[0]
            sign, logdet = np.linalg.slogdet(cov)
            if sign <= 0 or not np.isfinite(logdet):
                return float("nan")
            return -0.5 * chi2 + 0.5 * (d * math.log(2.0 * math.pi) + logdet)
        except Exception:
            return float("nan")


class GaussianEngine(PosteriorEngine):
    r"""The quadratic approximation, held in canonical form so queries are free.

    :class:`LaplaceEngine` computes the covariance at the optimum and slices it,
    and answers ``condition`` by fixing the parameter and running the optimiser
    again -- one full re-fit per conditional query. That is the right answer, but
    for a Gaussian it is also an expensive way to get it: the constrained minimum
    of a quadratic is exactly its conditional mode, so conditioning is
    :math:`h_A \mapsto h_A - K_{AB}v` and marginalising is a Schur complement.

    This engine builds the canonical form :math:`(K, h, g)` **once** and then
    answers every marginal, joint and conditional in closed form. Ask for twenty
    conditionals and it costs one curvature evaluation, not twenty fits.
    ``LaplaceEngine`` answers ``condition`` the same way when it can certify
    that the answer is the re-fit's; this engine does not check -- it is the
    Gaussian's answer by definition.

    The approximation is the Gaussian, not the algebra. Where the posterior is
    not close to quadratic this is wrong in exactly the way ``laplace`` is wrong,
    and a chain remains the way to find out -- but the two now disagree only
    about the *model*, never about the arithmetic.

    The form and its algebra are ``IMP.bff.InferenceCanonicalForm``.
    """

    method = "gaussian"

    def __init__(self, fit, model=None):
        """Bind the engine and clear the cached form."""
        super().__init__(fit, model=model)
        self._form = None

    def form(self, **options):
        """Return the posterior's canonical form, building it once.

        Parameters
        ----------
        **options
            Passed to :func:`chisurf.core.fitting.fit.covariance_matrix`.

        Returns
        -------
        IMP.bff.InferenceCanonicalForm or None
            The form, or ``None`` when the curvature is unusable.
        """
        if self._form is None:
            from chisurf.core.fitting import factorgraph

            with factorgraph.frozen_structure(self.fit, self.model):
                self._form = _curvature_form(self, **options)
        return self._form

    def run(self, **options) -> GaussianEngine:
        """Build the form and answer every declared target from it.

        Parameters
        ----------
        **options
            ``p_value`` sets the interval coverage (default 0.68); the rest go
            to the curvature evaluation.

        Returns
        -------
        GaussianEngine
            ``self``.
        """
        p_value = float(options.pop("p_value", 0.68))
        self._form = None
        form = self.form(**options)
        if form is None:
            self._marginals = {n: Marginal(name=n) for n in self._targets}
            self._joints, self._log_evidence, self._ran = {}, float("nan"), True
            return self

        # Conditioning is a closed-form update, so the evidence is applied here
        # rather than by re-fitting the model.
        conditioning = {}
        if self._evidence:
            names = list(form.get_names())
            known = {k: float(v) for k, v in self._evidence.items() if k in names}
            if known:
                form = form.condition(list(known), list(known.values()))
            conditioning = {"conditioning": "closed_form"}

        scope = list(form.get_names())
        self._marginals = {}
        for name in self._targets:
            if name not in scope:
                # Either unknown, or conditioned -- a held parameter has no
                # marginal of its own, which is the correct answer.
                self._marginals[name] = Marginal(name=name, p_value=p_value)
                continue
            mean, sd = _single(form, name)
            z = _normal_quantile(0.5 + 0.5 * p_value)
            self._marginals[name] = Marginal(
                name=name,
                value=mean,
                sd=sd,
                method=self.method,
                low=mean - z * sd,
                high=mean + z * sd,
                p_value=p_value,
                diagnostics={**self._symmetry_diagnostics(name, p_value), **conditioning},
            )

        self._joints = {}
        for key in self._joint_targets:
            if any(n not in scope for n in key):
                continue
            block = form.marginal(list(key))
            self._joints[key] = Joint(
                names=key,
                mean=np.asarray(block.get_mean(), dtype=np.float64),
                covariance=np.asarray(block.get_covariance(), dtype=np.float64).reshape(
                    len(key), len(key)
                ),
                method=self.method,
            )

        self._log_evidence = form.get_log_normalizer()
        self._ran = True
        return self

    def conditional(
        self, assignments: typing.Dict[str, float], targets: typing.Sequence[str] = None
    ) -> typing.List[Marginal]:
        """Return marginals under an arbitrary conditioning, without re-running.

        The reason to hold the posterior in canonical form: a conditional query
        is a matrix update, so a sweep over many held values -- which is what a
        profile scan *is* -- costs one curvature evaluation in total.

        Parameters
        ----------
        assignments : dict
            Variable name to held value.
        targets : sequence of str, optional
            Which marginals to return; defaults to everything left.

        Returns
        -------
        list of Marginal
            The conditional marginals.
        """
        form = self.form()
        if form is None:
            return []
        known = {k: float(v) for k, v in assignments.items() if k in list(form.get_names())}
        conditioned = form.condition(list(known), list(known.values())) if known else form
        scope = list(conditioned.get_names())
        wanted = list(targets) if targets else scope
        out = []
        for name in wanted:
            if name not in scope:
                out.append(Marginal(name=name))
                continue
            mean, sd = _single(conditioned, name)
            out.append(
                Marginal(
                    name=name,
                    value=mean,
                    sd=sd,
                    method=self.method,
                    low=mean - sd,
                    high=mean + sd,
                    p_value=0.68,
                )
            )
        return out

    def conditional_scan(
        self,
        name: str,
        points: int = 41,
        span: float = 3.0,
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        r"""Sweep one parameter over its range and report what the rest become.

        The question a correlated fit provokes -- *"if this lifetime really were
        4.2 ns, what would the amplitudes have to be?"* -- asked at every value
        at once. A profile scan answers it by re-fitting at each point; in
        canonical form each answer is a matrix update, so the whole sweep costs
        **one** curvature evaluation however many points it has.

        Results are also reported in standardised units, where the picture is
        easiest to read: for a Gaussian the conditional mean of :math:`Y` given
        :math:`X = x` is
        :math:`\mu_Y + \rho\,\sigma_Y (x - \mu_X)/\sigma_X`, so plotting
        :math:`(\text{mean} - \mu_Y)/\sigma_Y` against
        :math:`(x - \mu_X)/\sigma_X` gives a line **whose slope is exactly the
        correlation**. The conditional width
        :math:`\sigma_Y\sqrt{1 - \rho^2}` does not depend on where the sweep is,
        so it is reported once per target: it is what the data still does not
        know once the swept parameter is pinned down.

        Parameters
        ----------
        name : str
            Parameter to hold at each value.
        points : int, optional
            Number of held values.
        span : float, optional
            Half-width of the sweep, in standard deviations of ``name``.

        Returns
        -------
        dict or None
            ``held`` (the values), ``held_z`` (the same in sd units),
            ``centre``/``sd`` of the swept parameter, and ``targets``: one entry
            per other parameter with ``name``, ``mean`` (array), ``z`` (the
            standardised shift), ``sd`` (the conditional width, a scalar),
            ``marginal``/``marginal_sd`` and ``correlation``. ``None`` when the
            curvature is unusable or ``name`` is not in it.
        """
        form = self.form()
        if form is None or name not in list(form.get_names()):
            return None
        scope = list(form.get_names())
        index = scope.index(name)
        covariance = np.asarray(form.get_covariance(), dtype=np.float64).reshape(len(scope), len(scope))
        mean = np.asarray(form.get_mean(), dtype=np.float64)
        centre = float(mean[index])
        sd = float(math.sqrt(max(covariance[index, index], 0.0)))
        if not (sd > 0.0) or not np.isfinite(sd):
            return None

        points = max(2, int(points))
        held_z = np.linspace(-abs(span), abs(span), points)
        held = centre + sd * held_z

        targets = []
        for j, other in enumerate(scope):
            if other == name:
                continue
            sd_other = float(math.sqrt(max(covariance[j, j], 0.0)))
            if not (sd_other > 0.0):
                continue
            rho = float(covariance[index, j] / (sd * sd_other))
            rho = float(np.clip(rho, -1.0, 1.0))
            mu_other = float(mean[j])
            # The closed form, rather than one condition() call per point: they
            # agree exactly, and this keeps a long sweep free.
            z = rho * held_z
            targets.append(
                {
                    "name": other,
                    "mean": mu_other + sd_other * z,
                    "z": z,
                    "sd": sd_other * math.sqrt(max(1.0 - rho * rho, 0.0)),
                    "marginal": mu_other,
                    "marginal_sd": sd_other,
                    "correlation": rho,
                }
            )
        return {
            "name": name,
            "held": held,
            "held_z": held_z,
            "centre": centre,
            "sd": sd,
            "targets": targets,
        }

    def exact_conditional_scan(
        self,
        name: str,
        points: int = 13,
        span: float = 3.0,
        check_cancel: typing.Callable = None,
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        r"""Run the same sweep, re-fitting at every point instead of assuming.

        :meth:`conditional_scan` is exact *for a Gaussian posterior*, and a
        fluorescence posterior often is not one: lifetimes, amplitude fractions,
        distances and FRET efficiencies are bounded, and a parameter near its
        bound or a weak component has a visibly skewed posterior. There the true
        conditional is **curved**, and the straight line the Gaussian draws is
        wrong in a way no amount of algebra will reveal.

        This computes the honest answer the only way there is: hold the
        parameter, re-optimise everything else, repeat. That costs one fit per
        point — thousands of times the Gaussian sweep — so it is a separate
        call, not the default.

        The two are directly comparable: the returned ``z`` are standardised on
        the *same* marginal scale as :meth:`conditional_scan`, so plotting them
        together shows exactly where the quadratic approximation stops being
        trustworthy. See :func:`gaussian_validity`.

        Parameters
        ----------
        name : str
            Parameter to hold.
        points : int, optional
            Number of held values. Each costs a full re-fit, so this defaults far
            lower than the Gaussian sweep's.
        span : float, optional
            Half-width of the sweep, in standard deviations of ``name``.
        check_cancel : callable, optional
            Polled between points; the scan stops early and returns what it has
            when this returns ``True``.

        Returns
        -------
        dict or None
            As :meth:`conditional_scan`, plus ``chi2`` (the profile chi² at each
            point) and ``exact=True``. Points where the re-fit failed are
            ``nan``. ``None`` when there is no usable curvature to standardise
            against.
        """
        reference = self.conditional_scan(name, points=points, span=span)
        if reference is None:
            return None

        parameter = self._parameter(name)
        if parameter is None:
            return None
        targets = [t["name"] for t in reference["targets"]]
        by_name = {t["name"]: t for t in reference["targets"]}

        # Snapshot everything before touching it: this walks the optimiser over
        # the whole sweep and must put the fit back exactly as it was found.
        before = [(p, float(p.value)) for p in self.model.parameters_all if hasattr(p, "value")]
        was_fixed = bool(getattr(parameter, "fixed", False))

        means = {t: np.full(len(reference["held"]), np.nan) for t in targets}
        chi2 = np.full(len(reference["held"]), np.nan)
        try:
            parameter.fixed = True
            for i, held in enumerate(reference["held"]):
                if check_cancel is not None and check_cancel():
                    break
                parameter.value = float(held)
                try:
                    self.fit.run()
                except Exception:
                    continue
                current = {n: v for n, v in zip(self.parameter_names, self.model.parameter_values)}
                for t in targets:
                    if t in current:
                        means[t][i] = float(current[t])
                try:
                    chi2[i] = float(self.fit.chi2r)
                except (TypeError, ValueError, AttributeError):
                    pass
        finally:
            parameter.fixed = was_fixed
            for p, value in before:
                try:
                    p.value = value
                except (TypeError, ValueError):
                    continue
            try:
                self.fit.update()
            except Exception:
                pass

        out = []
        for t in targets:
            base = by_name[t]
            sd = base["marginal_sd"]
            out.append(
                {
                    "name": t,
                    "mean": means[t],
                    # Standardised on the same scale as the Gaussian sweep, which is
                    # the only way the two curves can be laid over each other.
                    "z": (means[t] - base["marginal"]) / sd if sd > 0 else means[t] * np.nan,
                    "sd": base["sd"],
                    "marginal": base["marginal"],
                    "marginal_sd": sd,
                    "correlation": base["correlation"],
                }
            )
        return {
            "name": name,
            "held": reference["held"],
            "held_z": reference["held_z"],
            "centre": reference["centre"],
            "sd": reference["sd"],
            "targets": out,
            "chi2": chi2,
            "exact": True,
        }


#: Smallest interval asymmetry worth reporting, however many draws prove it.
#: The ratio is (upper arm)/(lower arm) of the central interval, so 1.0 is
#: symmetric and 1.10 means one arm is a tenth longer than the other. Below this
#: the symmetric interval is wrong by less than the width of a plotted line, and
#: saying so would be noise in the user's face rather than information.
ASYMMETRY_FLOOR = 1.10

#: Sampling noise in the asymmetry ratio, as a multiple of ``1/sqrt(n_eff)``.
#: Calibrated against true Gaussians at 2k-30k draws and autocorrelation times of
#: 1 and 10: the 99th percentile of the observed ratio tracks
#: ``1 + 2.4/sqrt(n_eff)`` across all of them. A fixed cut cannot do this job --
#: at 2000 draws a genuine Gaussian reaches 1.17 by chance, while at 30000 the
#: floor is 1.04 and a real 1.21 skew would go unreported.
ASYMMETRY_NOISE = 2.4


def asymmetry_threshold(effective_draws: float) -> float:
    """Return the asymmetry ratio worth reporting for a chain of this quality.

    Two conditions have to hold before a skew is worth putting in front of
    someone: it must be **detectable** (above the sampling noise for the number
    of *effective* draws in hand) and **material** (big enough to change a quoted
    interval). This returns the larger of the two.

    Parameters
    ----------
    effective_draws : float
        Effective sample size of the chain for this parameter.

    Returns
    -------
    float
        The ratio at or above which the asymmetry is reported.
    """
    if not np.isfinite(effective_draws) or effective_draws <= 1.0:
        return float("inf")
    detectable = 1.0 + ASYMMETRY_NOISE / math.sqrt(effective_draws)
    return max(ASYMMETRY_FLOOR, detectable)


def marginal_asymmetry(
    fit,
    name: str,
    p_value: float = 0.68,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    r"""Measure how skewed a parameter's posterior actually is, from a chain.

    A covariance error bar is symmetric by construction; the posterior it
    approximates need not be, and in fluorescence usually is not -- lifetimes,
    amplitudes, distances and FRET efficiencies are bounded below, and a
    parameter near its bound has a one-sided posterior. Reporting
    :math:`\pm\sigma` for one of those is not merely imprecise: it is wrong on
    both ends at once, and nothing about the number says so.

    Whenever a sampling run has left a chain on the fit, the evidence is already
    in hand and costs nothing to read: the two arms of the central interval, and
    the skewness. This returns them so that an engine quoting a symmetric
    interval can *say* that it is quoting one.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose stored chain is consulted.
    name : str
        Parameter name; the group's ``fit:`` prefix is tolerated on either side.
    p_value : float, optional
        Coverage of the interval whose arms are compared.

    Returns
    -------
    dict or None
        ``lower``/``upper`` (the two arms), ``asymmetry`` (their ratio),
        ``skew``, ``median``, ``gaussian_ok`` and a human-readable ``note``.
        ``None`` when there is no chain to look at, which is not evidence of
        symmetry and must not be reported as such.
    """
    chain = getattr(fit, "sampling_chain", None)
    if not isinstance(chain, dict) or chain.get("parameter_values") is None:
        return None
    draws = np.atleast_2d(np.asarray(chain["parameter_values"], dtype=np.float64))
    names = [str(n) for n in chain.get("parameter_names", [])]
    if draws.shape[0] < 32 or len(names) != draws.shape[1]:
        return None

    short = str(name).split(":")[-1]
    index = None
    for i, candidate in enumerate(names):
        if candidate == str(name) or candidate.split(":")[-1] == short:
            index = i
            break
    if index is None:
        return None

    column = draws[:, index]
    column = column[np.isfinite(column)]
    if column.size < 32:
        return None

    # The threshold is set by the *effective* draw count, not the raw one: an
    # autocorrelated chain of 30000 knows far less than 30000 independent draws
    # and its asymmetry estimate is correspondingly noisier.
    from chisurf.core.fitting import diagnostics as _dg

    chains = chain.get("chains")
    try:
        effective = float(_dg.effective_sample_size(np.asarray(chains, dtype=np.float64))[index])
    except Exception:
        effective = float(column.size)
    if not np.isfinite(effective) or effective <= 1.0:
        effective = float(column.size)

    return sample_asymmetry(column, effective, p_value=p_value)


def sample_asymmetry(
    column: np.ndarray,
    effective_draws: typing.Optional[float] = None,
    p_value: float = 0.68,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    """Summarise one column of draws as a possibly-asymmetric interval.

    The arithmetic behind :func:`marginal_asymmetry`, separated from the job of
    finding the column. A *derived* quantity -- a FRET efficiency, a mean
    lifetime -- has no column of its own until one is computed for it, but once
    it exists it deserves exactly the same reading, and doing it twice would let
    the two answers drift apart.

    Parameters
    ----------
    column : numpy.ndarray
        Draws of a single scalar quantity. Non-finite entries are dropped.
    effective_draws : float, optional
        Effective sample size behind those draws, which sets how small a skew is
        distinguishable from sampling noise. Defaults to the raw count, which is
        optimistic for an autocorrelated chain.
    p_value : float, optional
        Coverage of the interval whose two arms are compared.

    Returns
    -------
    dict or None
        As :func:`marginal_asymmetry`. ``None`` when there are too few draws, or
        when the quantity is so concentrated that both arms collapse to zero.
    """
    column = np.asarray(column, dtype=np.float64).ravel()
    column = column[np.isfinite(column)]
    if column.size < 32:
        return None
    if effective_draws is None or not np.isfinite(effective_draws) or effective_draws <= 1.0:
        effective_draws = float(column.size)

    tail = 0.5 * (1.0 - float(p_value))
    low, median, high = np.percentile(column, [100.0 * tail, 50.0, 100.0 * (1.0 - tail)])
    lower, upper = float(median - low), float(high - median)
    if not (lower > 0.0 and upper > 0.0):
        return None
    asymmetry = upper / lower
    spread = float(column.std())
    skew = float(np.mean((column - column.mean()) ** 3) / spread**3) if spread > 0 else 0.0

    # Compared symmetrically, so a ratio of 0.8 counts the same as 1.25.
    ratio = max(asymmetry, 1.0 / asymmetry)
    threshold = asymmetry_threshold(effective_draws)
    gaussian_ok = ratio < threshold
    note = (
        ""
        if gaussian_ok
        else f"posterior is skewed ({median:.6g} +{upper:.3g} -{lower:.3g}); "
        f"a symmetric interval misstates both ends"
    )
    return {
        "lower": lower,
        "upper": upper,
        "median": float(median),
        "asymmetry": float(asymmetry),
        "skew": float(skew),
        "gaussian_ok": bool(gaussian_ok),
        "note": note,
        "p_value": float(p_value),
        "threshold": float(threshold),
        "effective_draws": float(effective_draws),
    }


def gaussian_validity(
    approximate: typing.Dict[str, typing.Any],
    exact: typing.Dict[str, typing.Any],
    tolerance: float = 0.25,
) -> typing.Dict[str, typing.Any]:
    r"""Say how far the quadratic approximation can be trusted.

    Compares a :meth:`~GaussianEngine.conditional_scan` against an
    :meth:`~GaussianEngine.exact_conditional_scan` of the same parameter and
    reports the range over which they agree.

    The answer is given as a *range*, not a yes/no, because that is the useful
    form: a posterior is almost always near-Gaussian close to the optimum and
    stops being so somewhere further out. Knowing the interval within which the
    straight line is honest is what tells you whether a 1σ error bar is fine and
    a 3σ one is fiction.

    Parameters
    ----------
    approximate, exact : dict
        Scans of the same parameter. The grids need not match: the Gaussian
        curve has a closed form, so it is evaluated on the *exact* scan's grid
        rather than the two being lined up. That matters in practice, because
        the cheap sweep is naturally run at many more points than the one that
        re-fits.
    tolerance : float, optional
        How far the two may differ, in units of the target's own marginal
        standard deviation, before the approximation is called broken.

    Returns
    -------
    dict
        ``valid_to`` (the largest ``|z|`` at which every target still agrees,
        ``inf`` when they agree everywhere tested), ``worst`` (the largest
        disagreement seen), ``worst_target``, and ``verdict``.
    """
    held_z = np.asarray(exact["held_z"], dtype=np.float64)
    correlations = {t["name"]: float(t["correlation"]) for t in approximate["targets"]}

    worst = 0.0
    worst_target = ""
    # The largest |z| out to which *every* target still agrees.
    ok = np.ones(held_z.size, dtype=bool)
    for other in exact["targets"]:
        rho = correlations.get(other["name"])
        if rho is None:
            continue
        # The Gaussian prediction in standardised units is exactly rho * z, so
        # it can be evaluated wherever the re-fit was actually done.
        difference = np.abs(rho * held_z - np.asarray(other["z"], dtype=np.float64))
        finite = np.isfinite(difference)
        if not finite.any():
            continue
        ok &= ~(finite & (difference > tolerance))
        peak = float(np.nanmax(difference[finite]))
        if peak > worst:
            worst, worst_target = peak, str(other["name"])

    # Walk outwards from the centre: the approximation is valid up to the first
    # radius at which any target disagrees, not merely wherever it happens to.
    order = np.argsort(np.abs(held_z))
    valid_to = float("inf")
    for i in order:
        if not ok[i]:
            valid_to = float(abs(held_z[i]))
            break

    if valid_to == float("inf"):
        verdict = (
            "the quadratic approximation holds everywhere tested — Gaussian intervals are fine here"
        )
    elif valid_to >= 2.0:
        verdict = f"holds to about {valid_to:.1f}σ — a 1σ interval is fine, further out is not"
    elif valid_to >= 1.0:
        verdict = (
            f"breaks down beyond {valid_to:.1f}σ — quote a profile or sampled interval, not ±σ"
        )
    else:
        verdict = (
            "breaks down inside 1σ — the posterior is not Gaussian and "
            "the ±σ error bar is misleading"
        )
    return {
        "valid_to": valid_to,
        "worst": worst,
        "worst_target": worst_target,
        "tolerance": float(tolerance),
        "verdict": verdict,
    }


class ProfileEngine(PosteriorEngine):
    """A chi² scan that re-optimises everything else at each point.

    Copes with asymmetric and skewed intervals that the quadratic approximation
    cannot, at the cost of a full re-fit per scan point, and only one parameter
    at a time -- so it has no joint answer and no evidence.

    ``condition`` re-optimises, deliberately: a closed-form conditional assumes
    the posterior is Gaussian in the held parameters, and not assuming that is
    this engine's reason to exist.
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
                    intervals = cs.core.fitting.support_plane.confidence_intervals_from_scan_result(
                        scan, p_values=(p_value,)
                    )
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
                sd = (high - low) / 2.0 if np.isfinite(low) and np.isfinite(high) else float("nan")
                self._marginals[name] = Marginal(
                    name=name,
                    value=value,
                    sd=sd,
                    method=method,
                    low=low,
                    high=high,
                    p_value=p_value,
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

    ``condition`` fixes the parameter and samples the rest, for the reason
    :class:`ProfileEngine` re-optimises: the chain is for posteriors that are not
    Gaussian, where a closed-form conditional would be the wrong answer.
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

        # the samplers the registry holds (chisurf.core.fitting.sample.SAMPLERS)
        import inspect

        from chisurf.core.registry import catalog

        try:
            key = catalog.resolve("sampler", backend)
            sampler = (
                cs.core.fitting.sample.sampler_function(key)
                if key in cs.core.fitting.sample.SAMPLERS
                else None
            )
            if sampler is not None and "sampler" in inspect.signature(sampler).parameters:
                options.setdefault("sampler", key)
        except ValueError:
            sampler = None
        if sampler is None:
            raise ValueError(f"unknown sampling backend {backend!r}")

        restore = self._apply_evidence()
        runs = []
        try:
            for _ in range(n_runs):
                runs.append(sampler(fit=self.fit, steps=steps, model=self.model, **options))
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
                np.isfinite(entry["rhat"])
                and entry["rhat"] <= dg.RHAT_THRESHOLD
                and np.isfinite(entry["ess"])
                and entry["ess"] >= dg.ESS_THRESHOLD
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
                    "ess": entry["ess"],
                    "rhat": entry["rhat"],
                    "tau": entry["tau"],
                    "mcse": entry["mcse"],
                    "converged": bool(converged),
                    "burn_in": burn,
                },
            )

        self._joints = {}
        for key in self._joint_targets:
            cols = [index.get(n) for n in key]
            if any(c is None for c in cols):
                continue
            sub = flat[:, cols]
            self._joints[key] = Joint(
                names=key,
                mean=sub.mean(axis=0),
                covariance=np.cov(sub, rowvar=False).reshape(len(cols), len(cols)),
                method=self.method,
                samples=sub,
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
                        name=name,
                        value=value,
                        method="profile",
                        low=low,
                        high=high,
                        p_value=p_value,
                        sd=(high - low) / 2.0
                        if np.isfinite(low) and np.isfinite(high)
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
                    name=name,
                    value=value,
                    sd=err,
                    method="laplace",
                    low=value - err,
                    high=value + err,
                    p_value=p_value,
                    diagnostics=self._symmetry_diagnostics(name, p_value),
                )
            else:
                self._marginals[name] = Marginal(name=name, value=value, p_value=p_value)

        self._joints = {}
        self._log_evidence = float("nan")
        self._ran = True
        return self

    def _stored_chain(self, p_value: float) -> typing.Dict[str, Marginal]:
        """Return marginals from a stored sampling report, keyed by name.

        Falls back to the draws themselves when there is no report. The report
        is a *summary*, and it is not the only thing a run leaves behind: a chain
        restored from file, reweighted, or produced by anything that did not also
        write diagnostics would otherwise be ignored, and the fit would quote a
        symmetric ``value ± sd`` while the asymmetric answer sat unused on the
        same object. Quantiles read from draws carry no convergence verdict, so
        they are marked ``converged: None`` rather than being claimed as checked.
        """
        from chisurf.core.fitting import diagnostics as dg

        report = getattr(self.fit, "sampling_diagnostics", None)
        if not isinstance(report, dict):
            return self._chain_quantiles(p_value)
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
                name=str(e.get("name")),
                value=float(e.get("mean", float("nan"))),
                sd=float(e.get("sd", float("nan"))),
                method="mcmc",
                quantiles=quantiles,
                low=float(lo),
                high=float(hi),
                p_value=p_value,
                diagnostics={"ess": ess, "rhat": rhat, "converged": True},
            )
        # Deliberately *not* falling back to the draws here. An empty result
        # means the report exists and rejected every parameter for failing its
        # R-hat / effective-sample-size checks, and reading the same draws
        # directly would launder exactly the chain that was just refused. The
        # fallback above applies only when no verdict was ever recorded.
        return out

    def _chain_quantiles(self, p_value: float) -> typing.Dict[str, Marginal]:
        """Return marginals computed directly from stored draws.

        Parameters
        ----------
        p_value : float
            Coverage of the reported interval.

        Returns
        -------
        dict
            Name to :class:`Marginal`, empty when the fit carries no draws.
        """
        chain = getattr(self.fit, "sampling_chain", None)
        if not isinstance(chain, dict) or chain.get("parameter_values") is None:
            return {}
        draws = np.atleast_2d(np.asarray(chain["parameter_values"], dtype=np.float64))
        names = [str(n) for n in chain.get("parameter_names", [])]
        if draws.shape[0] < 32 or len(names) != draws.shape[1]:
            return {}

        tail = 0.5 * (1.0 - float(p_value))
        probabilities = (0.025, tail, 0.5, 1.0 - tail, 0.975)
        out = {}
        for i, name in enumerate(names):
            column = draws[:, i]
            column = column[np.isfinite(column)]
            if column.size < 32:
                continue
            quantiles = {float(q): float(np.quantile(column, q)) for q in probabilities}
            out[name] = Marginal(
                name=name,
                value=float(np.median(column)),
                sd=float(column.std(ddof=1)),
                method="mcmc",
                quantiles=quantiles,
                low=float(np.quantile(column, tail)),
                high=float(np.quantile(column, 1.0 - tail)),
                p_value=p_value,
                # No report means nothing checked R-hat or the effective sample
                # size, and saying "converged: True" here would be a claim
                # nobody made.
                diagnostics={"converged": None, "source": "draws"},
            )
        return out

    @staticmethod
    def _scan_interval(scan: dict, p_value: float) -> typing.Tuple[float, float]:
        """Return the profile crossings of a stored scan at ``p_value``."""
        try:
            intervals = cs.core.fitting.support_plane.confidence_intervals_from_scan_result(
                scan, p_values=(p_value,)
            )
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
    ORDER = ("mcmc", "profile", "gaussian", "laplace")

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
    "gaussian": GaussianEngine,
    "profile": ProfileEngine,
    "mcmc": SamplingEngine,
    "stored": StoredEngine,
    "auto": AutoEngine,
}


def get_engine(name: str, fit, model=None, **kwargs) -> PosteriorEngine:
    """Return an engine by name.

    Parameters
    ----------
    name : {"laplace", "gaussian", "profile", "mcmc", "stored", "auto"}
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
