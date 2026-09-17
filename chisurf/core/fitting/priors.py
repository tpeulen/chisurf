r"""Prior probability distributions for fitting parameters.

This module generalises the ChiSurf fit objective from plain (weighted)
least-squares to *maximum-a-posteriori* (MAP) estimation and Bayesian
sampling.  Every :class:`~chisurf.core.parameter.Parameter` may carry an
optional :class:`Prior` describing prior belief about its value.

Two consumers use a prior:

* **Least-squares / Levenberg-Marquardt (MAP).**  A prior contributes extra
  *prior residuals* appended to the data-residual vector.  Because the
  optimiser minimises the sum of squared residuals, appending
  :math:`r_k = \sqrt{-2\,[\ln p(\theta) - \ln p(\theta^\ast)]}` (with the
  sign taken from the mode :math:`\theta^\ast`) makes it minimise
  :math:`\chi^2 - 2\ln p(\theta)`, i.e. the negative log-posterior, without
  any change to the optimiser itself.  For a Gaussian prior this reduces to
  the familiar Tikhonov/ridge residual :math:`(\theta-\mu)/\sigma`.  This is
  the same trick used for the Poisson ``2I*`` deviance residuals in
  :func:`chisurf.core.fitting.deviance_residuals`.

* **MCMC / posterior sampling.**  The sampler evaluates
  :meth:`Prior.lnpdf` directly (summed into
  :func:`chisurf.core.fitting.fit.lnprior`).

**Bounds are priors.**  A hard box constraint ``lb <= theta <= ub`` is the
degenerate :class:`UniformPrior`: uniform log-density inside the interval and
:math:`-\infty` outside.  Its :meth:`~Prior.support` drives the optimiser's
hard bounds, while smooth priors report an unbounded (or truncated) support
and instead push through their residual/log-density contribution.  A parameter
therefore needs only one concept -- ``prior`` -- to express both bounds and
soft prior belief.
"""

from __future__ import annotations

import abc
import math

import numpy as np

from chisurf import typing

__all__ = [
    "Prior",
    "UniformPrior",
    "NormalPrior",
    "TruncatedNormalPrior",
    "HalfNormalPrior",
    "LogNormalPrior",
    "ExponentialPrior",
    "CallablePrior",
    "as_prior",
    "PRIOR_REGISTRY",
    "prior_from_state",
]

#: Registry mapping the serialised ``kind`` tag onto its :class:`Prior` class.
#: Populated by the :func:`_register` decorator applied to each concrete prior.
PRIOR_REGISTRY: typing.Dict[str, typing.Type[Prior]] = {}


def _register(cls: typing.Type[Prior]) -> typing.Type[Prior]:
    """Register a concrete :class:`Prior` subclass by its ``kind`` tag."""
    PRIOR_REGISTRY[cls.kind] = cls
    return cls


class Prior(abc.ABC):
    """Abstract base class for a scalar parameter prior.

    Subclasses implement :meth:`lnpdf` (the log prior density up to an additive
    constant) and may override :meth:`residuals`, :meth:`support` and
    :meth:`mode`.  The default :meth:`residuals` implementation derives a
    signed deviance residual from :meth:`lnpdf` and :meth:`mode`, so a subclass
    only needs to override it when a cheaper closed form exists (e.g. the linear
    residual of a Gaussian prior).
    """

    #: Short, stable tag used for (de-)serialisation and the registry.
    kind: str = "prior"

    @abc.abstractmethod
    def lnpdf(self, x: float) -> float:
        """Return the log prior density at ``x`` (up to an additive constant).

        Parameters
        ----------
        x : float
            Parameter value at which to evaluate the log density.

        Returns
        -------
        float
            The log density, or ``-inf`` outside the support.
        """
        raise NotImplementedError

    def mode(self) -> float:
        """Return the value that maximises the prior density.

        Used as the reference point for the generic deviance residual. The
        default is ``0.0``; subclasses with a well-defined mode override it.
        """
        return 0.0

    def support(self) -> typing.Tuple[float, float]:
        """Return the ``(lower, upper)`` hard support of the prior.

        The optimiser uses this as hard bounds. Smooth, unbounded priors
        return ``(-inf, +inf)`` and rely on their residual contribution.
        """
        return (float("-inf"), float("inf"))

    def residuals(self, x: float) -> np.ndarray:
        """Return the prior-residual contribution for a least-squares fit.

        The returned entries are appended to the data-residual vector so that
        the optimiser minimises the negative log-posterior. The default is a
        generic signed deviance residual
        ``sign(x - mode) * sqrt(-2 * (lnpdf(x) - lnpdf(mode)))``. Priors that
        only impose a hard support (e.g. :class:`UniformPrior`) return an empty
        array because the constraint is handled by :meth:`support`.

        Parameters
        ----------
        x : float
            Current parameter value.

        Returns
        -------
        numpy.ndarray
            Residual entries (length 0 or 1 for the built-in priors).
        """
        lp = self.lnpdf(x)
        if not math.isfinite(lp):
            # Outside support: a large but finite penalty so the optimiser is
            # pushed back into the feasible region instead of seeing NaN.
            return np.array([1e12], dtype=np.float64)
        lp0 = self.lnpdf(self.mode())
        dev = -2.0 * (lp - lp0)
        dev = max(dev, 0.0)
        sign = 1.0 if x >= self.mode() else -1.0
        return np.array([sign * math.sqrt(dev)], dtype=np.float64)

    # -- serialisation ----------------------------------------------------

    @abc.abstractmethod
    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return a JSON-serialisable ``dict`` describing this prior.

        The dict must contain a ``"kind"`` key matching :attr:`kind` plus the
        distribution parameters, so that :func:`prior_from_state` can rebuild
        the object.
        """
        raise NotImplementedError

    @classmethod
    def from_state(cls, state: typing.Dict[str, typing.Any]) -> Prior:
        """Reconstruct a prior from a :meth:`get_state` dictionary."""
        return prior_from_state(state)

    def combine(self, other: PriorLike) -> Prior:
        """Return the prior proportional to the product of two prior densities.

        Combining priors is how independent prior beliefs about the same
        parameter are merged. For **conjugate** same-family pairs the result is
        returned in closed form (e.g. two Gaussians combine into a single
        Gaussian with the precision-weighted mean), which keeps repeated
        combination cheap and exact. For all other pairs a generic
        :class:`ProductPrior` is returned, whose log density is the sum of the
        components' and whose least-squares residual is the concatenation of the
        components' residuals.

        Parameters
        ----------
        other : Prior, callable or dict
            The other prior (coerced via :func:`as_prior`).

        Returns
        -------
        Prior
            The combined prior.
        """
        return _combine_priors(self, other)

    def __mul__(self, other: PriorLike) -> Prior:
        """Alias for :meth:`combine` so ``prior_a * prior_b`` reads naturally."""
        return self.combine(other)

    def __repr__(self) -> str:
        """Return a compact ``kind(params)`` representation."""
        try:
            params = {k: v for k, v in self.get_state().items() if k != "kind"}
            inner = ", ".join(
                f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v!r}"
                for k, v in params.items()
            )
        except Exception:
            inner = ""
        return f"{type(self).__name__}({inner})"


@_register
class UniformPrior(Prior):
    """Uniform (box) prior -- the prior form of a hard bound.

    The log density is constant inside ``[lb, ub]`` and ``-inf`` outside. This
    is the canonical representation of a parameter bound: the optimiser reads
    the interval from :meth:`support` and enforces it as a hard constraint, so
    :meth:`residuals` contributes nothing.
    """

    kind = "uniform"

    def __init__(self, lb: float = float("-inf"), ub: float = float("inf")):
        """Initialise a uniform prior on ``[lb, ub]``.

        Parameters
        ----------
        lb, ub : float
            Lower and upper bounds. Either may be infinite for a one-sided or
            improper (fully flat) prior.
        """
        lb = float(lb)
        ub = float(ub)
        if ub < lb:
            lb, ub = ub, lb
        self.lb = lb
        self.ub = ub

    def lnpdf(self, x: float) -> float:
        """Return ``-log(ub - lb)`` inside the interval, ``-inf`` outside."""
        if x < self.lb or x > self.ub:
            return float("-inf")
        width = self.ub - self.lb
        if math.isfinite(width) and width > 0.0:
            return -math.log(width)
        return 0.0

    def support(self) -> typing.Tuple[float, float]:
        """Return the box interval ``(lb, ub)`` used as hard optimiser bounds."""
        return (self.lb, self.ub)

    def mode(self) -> float:
        """Return the interval midpoint (or a finite endpoint / ``0``)."""
        if math.isfinite(self.lb) and math.isfinite(self.ub):
            return 0.5 * (self.lb + self.ub)
        if math.isfinite(self.lb):
            return self.lb
        if math.isfinite(self.ub):
            return self.ub
        return 0.0

    def residuals(self, x: float) -> np.ndarray:
        """Return an empty array; the bound is enforced via :meth:`support`."""
        return np.empty(0, dtype=np.float64)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return ``{"kind": "uniform", "lb": ..., "ub": ...}``."""
        return {"kind": self.kind, "lb": self.lb, "ub": self.ub}


@_register
class NormalPrior(Prior):
    r"""Gaussian prior :math:`\mathcal{N}(\mu, \sigma^2)`.

    Contributes the Tikhonov/ridge residual :math:`(x - \mu)/\sigma` to a
    least-squares fit and the Gaussian log density to a sampler.
    """

    kind = "normal"

    def __init__(self, mu: float = 0.0, sigma: float = 1.0):
        """Initialise a Gaussian prior.

        Parameters
        ----------
        mu : float
            Mean (and mode) of the prior.
        sigma : float
            Standard deviation; must be strictly positive.
        """
        self.mu = float(mu)
        self.sigma = float(sigma)
        if not (self.sigma > 0.0):
            raise ValueError("NormalPrior sigma must be > 0")

    def lnpdf(self, x: float) -> float:
        """Return the Gaussian log density at ``x``."""
        z = (x - self.mu) / self.sigma
        return -0.5 * z * z - math.log(self.sigma) - 0.5 * math.log(2.0 * math.pi)

    def mode(self) -> float:
        """Return the mean ``mu``."""
        return self.mu

    def residuals(self, x: float) -> np.ndarray:
        """Return the single residual ``[(x - mu) / sigma]``."""
        return np.array([(x - self.mu) / self.sigma], dtype=np.float64)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return ``{"kind": "normal", "mu": ..., "sigma": ...}``."""
        return {"kind": self.kind, "mu": self.mu, "sigma": self.sigma}


@_register
class TruncatedNormalPrior(NormalPrior):
    r"""Gaussian prior truncated to ``[lb, ub]``.

    Behaves like :class:`NormalPrior` for the residual/log-density inside the
    interval but reports the truncation interval as its hard :meth:`support`,
    combining a soft Gaussian pull with hard bounds.
    """

    kind = "truncated_normal"

    def __init__(
        self,
        mu: float = 0.0,
        sigma: float = 1.0,
        lb: float = float("-inf"),
        ub: float = float("inf"),
    ):
        """Initialise a truncated Gaussian prior.

        Parameters
        ----------
        mu, sigma : float
            Mean and standard deviation of the underlying Gaussian.
        lb, ub : float
            Truncation bounds. Reported via :meth:`support`.
        """
        super().__init__(mu=mu, sigma=sigma)
        lb = float(lb)
        ub = float(ub)
        if ub < lb:
            lb, ub = ub, lb
        self.lb = lb
        self.ub = ub

    def lnpdf(self, x: float) -> float:
        """Return the Gaussian log density inside ``[lb, ub]``, ``-inf`` outside."""
        if x < self.lb or x > self.ub:
            return float("-inf")
        return super().lnpdf(x)

    def support(self) -> typing.Tuple[float, float]:
        """Return the truncation interval ``(lb, ub)``."""
        return (self.lb, self.ub)

    def mode(self) -> float:
        """Return ``mu`` clamped to the truncation interval."""
        return min(max(self.mu, self.lb), self.ub)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return the mean, sigma and truncation bounds."""
        return {
            "kind": self.kind,
            "mu": self.mu,
            "sigma": self.sigma,
            "lb": self.lb,
            "ub": self.ub,
        }


@_register
class HalfNormalPrior(Prior):
    r"""Half-normal prior on ``x >= loc`` (a soft positivity prior).

    Density :math:`\propto \exp[-\tfrac12((x-\mathrm{loc})/\sigma)^2]` for
    ``x >= loc`` and zero below. The mode is at ``loc``.
    """

    kind = "half_normal"

    def __init__(self, sigma: float = 1.0, loc: float = 0.0):
        """Initialise a half-normal prior.

        Parameters
        ----------
        sigma : float
            Scale of the underlying Gaussian; must be strictly positive.
        loc : float
            Left edge / mode of the distribution.
        """
        self.sigma = float(sigma)
        self.loc = float(loc)
        if not (self.sigma > 0.0):
            raise ValueError("HalfNormalPrior sigma must be > 0")

    def lnpdf(self, x: float) -> float:
        """Return the half-normal log density (``-inf`` below ``loc``)."""
        if x < self.loc:
            return float("-inf")
        z = (x - self.loc) / self.sigma
        return -0.5 * z * z - math.log(self.sigma) + 0.5 * math.log(2.0 / math.pi)

    def mode(self) -> float:
        """Return the left edge ``loc``, where the density is maximal."""
        return self.loc

    def support(self) -> typing.Tuple[float, float]:
        """Return ``(loc, +inf)``."""
        return (self.loc, float("inf"))

    def residuals(self, x: float) -> np.ndarray:
        """Return ``[(x - loc) / sigma]`` inside the support."""
        if x < self.loc:
            return np.array([1e12], dtype=np.float64)
        return np.array([(x - self.loc) / self.sigma], dtype=np.float64)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return ``{"kind": "half_normal", "sigma": ..., "loc": ...}``."""
        return {"kind": self.kind, "sigma": self.sigma, "loc": self.loc}


@_register
class LogNormalPrior(Prior):
    r"""Log-normal prior on ``x > 0``.

    ``ln(x)`` is Gaussian with mean ``mu`` and standard deviation ``sigma``.
    Appropriate for positive scale parameters (rates, amplitudes, times) where
    the uncertainty is multiplicative. The least-squares residual is
    ``(ln(x) - mu)/sigma``.
    """

    kind = "lognormal"

    def __init__(self, mu: float = 0.0, sigma: float = 1.0):
        """Initialise a log-normal prior.

        Parameters
        ----------
        mu : float
            Mean of ``ln(x)``.
        sigma : float
            Standard deviation of ``ln(x)``; must be strictly positive.
        """
        self.mu = float(mu)
        self.sigma = float(sigma)
        if not (self.sigma > 0.0):
            raise ValueError("LogNormalPrior sigma must be > 0")

    def lnpdf(self, x: float) -> float:
        """Return the log-normal log density (``-inf`` for ``x <= 0``)."""
        if x <= 0.0:
            return float("-inf")
        lx = math.log(x)
        z = (lx - self.mu) / self.sigma
        return -0.5 * z * z - lx - math.log(self.sigma) - 0.5 * math.log(2.0 * math.pi)

    def mode(self) -> float:
        """Return the mode ``exp(mu - sigma**2)`` of the log-normal density."""
        return math.exp(self.mu - self.sigma * self.sigma)

    def support(self) -> typing.Tuple[float, float]:
        """Return ``(0, +inf)``."""
        return (0.0, float("inf"))

    def residuals(self, x: float) -> np.ndarray:
        """Return ``[(ln(x) - mu) / sigma]`` for ``x > 0``."""
        if x <= 0.0:
            return np.array([1e12], dtype=np.float64)
        return np.array([(math.log(x) - self.mu) / self.sigma], dtype=np.float64)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return ``{"kind": "lognormal", "mu": ..., "sigma": ...}``."""
        return {"kind": self.kind, "mu": self.mu, "sigma": self.sigma}


@_register
class ExponentialPrior(Prior):
    r"""Exponential prior on ``x >= loc`` with mean ``scale``.

    Density :math:`\propto \exp[-(x-\mathrm{loc})/\mathrm{scale}]`. A weak
    positivity/shrinkage prior. Because the negative log density is linear in
    ``x``, the least-squares residual is the generic deviance
    :math:`\sqrt{2(x-\mathrm{loc})/\mathrm{scale}}`.
    """

    kind = "exponential"

    def __init__(self, scale: float = 1.0, loc: float = 0.0):
        """Initialise an exponential prior.

        Parameters
        ----------
        scale : float
            Mean of the distribution above ``loc``; must be strictly positive.
        loc : float
            Left edge / mode of the distribution.
        """
        self.scale = float(scale)
        self.loc = float(loc)
        if not (self.scale > 0.0):
            raise ValueError("ExponentialPrior scale must be > 0")

    def lnpdf(self, x: float) -> float:
        """Return the exponential log density (``-inf`` below ``loc``)."""
        if x < self.loc:
            return float("-inf")
        return -(x - self.loc) / self.scale - math.log(self.scale)

    def mode(self) -> float:
        """Return the left edge ``loc``."""
        return self.loc

    def support(self) -> typing.Tuple[float, float]:
        """Return ``(loc, +inf)``."""
        return (self.loc, float("inf"))

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return ``{"kind": "exponential", "scale": ..., "loc": ...}``."""
        return {"kind": self.kind, "scale": self.scale, "loc": self.loc}


@_register
class GammaPrior(Prior):
    r"""Gamma prior on ``x > loc`` with shape ``alpha`` and rate ``beta``.

    Density :math:`\propto (x-\mathrm{loc})^{\alpha-1}\,e^{-\beta (x-\mathrm{loc})}`.
    Conjugate for the rate/precision of exponential and Gaussian likelihoods, so
    :meth:`combine` of two gammas is again a gamma.
    """

    kind = "gamma"

    def __init__(self, alpha: float = 1.0, beta: float = 1.0, loc: float = 0.0):
        """Initialise a gamma prior.

        Parameters
        ----------
        alpha : float
            Shape parameter; must be strictly positive.
        beta : float
            Rate parameter (inverse scale); must be strictly positive.
        loc : float
            Left edge of the support.
        """
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.loc = float(loc)
        if not (self.alpha > 0.0 and self.beta > 0.0):
            raise ValueError("GammaPrior alpha and beta must be > 0")

    def lnpdf(self, x: float) -> float:
        """Return the gamma log density (``-inf`` at or below ``loc``)."""
        t = x - self.loc
        if t <= 0.0:
            return float("-inf")
        return (
            (self.alpha - 1.0) * math.log(t)
            - self.beta * t
            + self.alpha * math.log(self.beta)
            - math.lgamma(self.alpha)
        )

    def mode(self) -> float:
        """Return the density mode ``loc + (alpha-1)/beta`` (``loc`` if ``alpha<1``)."""
        if self.alpha >= 1.0:
            return self.loc + (self.alpha - 1.0) / self.beta
        return self.loc

    def support(self) -> typing.Tuple[float, float]:
        """Return ``(loc, +inf)``."""
        return (self.loc, float("inf"))

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return the shape, rate and location."""
        return {"kind": self.kind, "alpha": self.alpha, "beta": self.beta, "loc": self.loc}


@_register
class BetaPrior(Prior):
    r"""Beta prior on ``0 < x < 1`` with shapes ``alpha``, ``beta``.

    Density :math:`\propto x^{\alpha-1}(1-x)^{\beta-1}`. Conjugate for the
    success probability of Bernoulli/binomial likelihoods and a natural prior
    for fractions/branching ratios, so :meth:`combine` of two betas is a beta.
    """

    kind = "beta"

    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        """Initialise a beta prior.

        Parameters
        ----------
        alpha, beta : float
            Shape parameters; both must be strictly positive.
        """
        self.alpha = float(alpha)
        self.beta = float(beta)
        if not (self.alpha > 0.0 and self.beta > 0.0):
            raise ValueError("BetaPrior alpha and beta must be > 0")

    def lnpdf(self, x: float) -> float:
        """Return the beta log density (``-inf`` outside the open unit interval)."""
        if x <= 0.0 or x >= 1.0:
            return float("-inf")
        log_b = (
            math.lgamma(self.alpha) + math.lgamma(self.beta) - math.lgamma(self.alpha + self.beta)
        )
        return (self.alpha - 1.0) * math.log(x) + (self.beta - 1.0) * math.log1p(-x) - log_b

    def mode(self) -> float:
        """Return the density mode ``(alpha-1)/(alpha+beta-2)`` when defined."""
        if self.alpha > 1.0 and self.beta > 1.0:
            return (self.alpha - 1.0) / (self.alpha + self.beta - 2.0)
        return 0.5

    def support(self) -> typing.Tuple[float, float]:
        """Return ``(0, 1)``."""
        return (0.0, 1.0)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return the two shape parameters."""
        return {"kind": self.kind, "alpha": self.alpha, "beta": self.beta}


class CallablePrior(Prior):
    """The most general prior: a user callback returning the log density.

    This is the escape hatch beneath the predefined families -- any callable
    ``logpdf(x) -> float`` defines a valid (unnormalised) prior. An optional
    ``residual`` callable can supply a closed-form least-squares residual;
    otherwise the generic signed deviance from :meth:`Prior.residuals` is used,
    referenced to ``mode``.

    A callback cannot be JSON-serialised, so :meth:`get_state` returns only the
    ``"callable"`` tag: callback priors are **runtime-only** and are dropped
    (with a warning) when a project is saved and reloaded.
    """

    kind = "callable"

    def __init__(
        self,
        logpdf: typing.Callable[[float], float],
        mode: float = 0.0,
        support: typing.Tuple[float, float] = (float("-inf"), float("inf")),
        residual: typing.Optional[typing.Callable[[float], float]] = None,
        label: str = "",
    ):
        """Wrap a callable as a prior.

        Parameters
        ----------
        logpdf : callable
            ``logpdf(x) -> float`` returning the log prior density (up to an
            additive constant).
        mode : float, optional
            Reference point for the generic deviance residual.
        support : (float, float), optional
            Hard support reported to the optimiser.
        residual : callable, optional
            ``residual(x) -> float`` giving an explicit least-squares residual.
        label : str, optional
            Human-readable label for display/repr.
        """
        if not callable(logpdf):
            raise TypeError("CallablePrior requires a callable logpdf")
        self._logpdf = logpdf
        self._mode = float(mode)
        self._support = (float(support[0]), float(support[1]))
        self._residual = residual
        self.label = str(label)

    def lnpdf(self, x: float) -> float:
        """Evaluate the wrapped callable; non-finite/failed calls yield ``-inf``."""
        try:
            v = float(self._logpdf(x))
        except Exception:
            return float("-inf")
        return v if math.isfinite(v) else float("-inf")

    def mode(self) -> float:
        """Return the configured reference mode."""
        return self._mode

    def support(self) -> typing.Tuple[float, float]:
        """Return the configured hard support."""
        return self._support

    def residuals(self, x: float) -> np.ndarray:
        """Return the explicit residual if supplied, else the generic deviance."""
        if self._residual is not None:
            try:
                return np.array([float(self._residual(x))], dtype=np.float64)
            except Exception:
                return np.array([1e12], dtype=np.float64)
        return super().residuals(x)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return only the tag: a callback cannot be reconstructed from JSON."""
        return {"kind": self.kind, "label": self.label}


@_register
class ProductPrior(Prior):
    """Generic product of several priors (their densities multiplied).

    The fallback returned by :meth:`Prior.combine` when no closed-form conjugate
    simplification applies. The log density is the sum of the components' log
    densities; the least-squares residual is the concatenation of the
    components' residuals (so combining priors is additive in chi²); the support
    is the intersection of the components' supports.
    """

    kind = "product"

    def __init__(self, priors: typing.Sequence[PriorLike]):
        """Initialise from a sequence of priors (flattening nested products).

        Parameters
        ----------
        priors : sequence of Prior, callable or dict
            The component priors. Nested :class:`ProductPrior` instances are
            flattened.
        """
        flat: typing.List[Prior] = []
        for p in priors:
            pr = as_prior(p)
            if pr is None:
                continue
            if isinstance(pr, ProductPrior):
                flat.extend(pr.priors)
            else:
                flat.append(pr)
        self.priors = flat

    def lnpdf(self, x: float) -> float:
        """Return the sum of the components' log densities."""
        total = 0.0
        for p in self.priors:
            total += p.lnpdf(x)
            if not math.isfinite(total):
                return float("-inf")
        return total

    def support(self) -> typing.Tuple[float, float]:
        """Return the intersection of the components' supports."""
        lb, ub = float("-inf"), float("inf")
        for p in self.priors:
            lo, hi = p.support()
            lb = max(lb, lo)
            ub = min(ub, hi)
        return (lb, ub)

    def mode(self) -> float:
        """Return a representative point (the first component's mode)."""
        return self.priors[0].mode() if self.priors else 0.0

    def residuals(self, x: float) -> np.ndarray:
        """Return the concatenation of the components' residuals."""
        pieces = [np.asarray(p.residuals(x), dtype=np.float64).ravel() for p in self.priors]
        pieces = [pc for pc in pieces if pc.size]
        if not pieces:
            return np.empty(0, dtype=np.float64)
        return np.concatenate(pieces)

    def get_state(self) -> typing.Dict[str, typing.Any]:
        """Return the serialised component priors (callback components excluded)."""
        return {
            "kind": self.kind,
            "priors": [p.get_state() for p in self.priors],
        }


#: Anything acceptable where a prior is expected: a :class:`Prior`, a callable
#: ``logpdf(x) -> float`` (wrapped as :class:`CallablePrior`), or a state dict.
PriorLike = typing.Union[Prior, typing.Callable[[float], float], typing.Dict[str, typing.Any]]


def as_prior(obj: typing.Optional[PriorLike]) -> typing.Optional[Prior]:
    """Coerce a prior-like object into a :class:`Prior` (or ``None``).

    Parameters
    ----------
    obj : Prior, callable, dict or None
        A prior, a ``logpdf`` callable (wrapped as :class:`CallablePrior`), a
        :meth:`Prior.get_state` dict, or ``None``.

    Returns
    -------
    Prior or None
        The coerced prior, or ``None`` if ``obj`` is ``None`` / unrecognised.
    """
    if obj is None:
        return None
    if isinstance(obj, Prior):
        return obj
    if isinstance(obj, dict):
        return prior_from_state(obj)
    if callable(obj):
        return CallablePrior(obj)
    return None


def _combine_priors(a: PriorLike, b: PriorLike) -> Prior:
    """Combine two priors, using closed-form conjugates where possible.

    See :meth:`Prior.combine` for semantics.
    """
    pa = as_prior(a)
    pb = as_prior(b)
    if pa is None:
        return pb if pb is not None else UniformPrior()
    if pb is None:
        return pa

    # Normal x Normal -> Normal (precision-weighted mean).
    if type(pa) is NormalPrior and type(pb) is NormalPrior:
        ta = 1.0 / (pa.sigma * pa.sigma)
        tb = 1.0 / (pb.sigma * pb.sigma)
        tau = ta + tb
        mu = (pa.mu * ta + pb.mu * tb) / tau
        return NormalPrior(mu=mu, sigma=math.sqrt(1.0 / tau))

    # Normal x Uniform -> Truncated Normal (soft pull, hard bounds).
    for x, y in ((pa, pb), (pb, pa)):
        if type(x) is NormalPrior and isinstance(y, UniformPrior):
            return TruncatedNormalPrior(mu=x.mu, sigma=x.sigma, lb=y.lb, ub=y.ub)

    # Gamma x Gamma -> Gamma (shapes add minus one, rates add); needs same loc.
    if type(pa) is GammaPrior and type(pb) is GammaPrior and pa.loc == pb.loc:
        return GammaPrior(
            alpha=pa.alpha + pb.alpha - 1.0,
            beta=pa.beta + pb.beta,
            loc=pa.loc,
        )

    # Beta x Beta -> Beta (both shapes add minus one).
    if type(pa) is BetaPrior and type(pb) is BetaPrior:
        return BetaPrior(alpha=pa.alpha + pb.alpha - 1.0, beta=pa.beta + pb.beta - 1.0)

    return ProductPrior([pa, pb])


def prior_from_state(
    state: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Optional[Prior]:
    """Rebuild a :class:`Prior` from a :meth:`Prior.get_state` dictionary.

    Parameters
    ----------
    state : dict or None
        A dictionary containing a ``"kind"`` key plus the distribution
        parameters. ``None`` (or a dict without a recognised ``kind``) yields
        ``None`` (no prior).

    Returns
    -------
    Prior or None
        The reconstructed prior, or ``None`` if ``state`` does not describe a
        registered prior.
    """
    if not isinstance(state, dict):
        return None
    kind = state.get("kind")
    cls = PRIOR_REGISTRY.get(str(kind)) if kind is not None else None
    if cls is None:
        return None
    kwargs = {k: v for k, v in state.items() if k != "kind"}
    try:
        return cls(**kwargs)
    except (TypeError, ValueError):
        return None
