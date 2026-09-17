"""Titration: a concentration series of FRET histograms, and the isotherm in it.

This is the one ALEX-Suite analysis with no ChiSurf equivalent. A titration is a
set of measurements of the same sample at different ligand concentrations; each
gives a FRET-efficiency histogram, and the *populations do not move* — only their
relative amounts do. So the series is fitted with **one** set of Gaussian
components whose centres and widths are shared across every concentration and
whose amplitudes are free per concentration. The bound fraction read off those
amplitudes, plotted against concentration, is a binding isotherm.

Sharing the shape is the whole point, and it is what the old program's "Two
populations, fixed x0 and sigma" preset did. Fitting each histogram
independently lets a noisy condition move a peak by more than the amplitude
change you are trying to measure, and the isotherm then reports that noise as
affinity.

The amplitudes enter linearly, so they are not searched: for any trial
``(mu, sigma)`` they are the non-negative least-squares solution, and only the
shape parameters go to the optimiser (variable projection). That is both faster
and much better conditioned than searching all ``K + 2*K*n_conditions``
parameters at once, and it is what keeps a two-component fit of six conditions
from wandering into a local minimum where one component has collapsed.

Qt-free.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import numpy as np

from chisurf.plugins.burst.alex_suite.api.histograms import (
    Corrections,
    Thresholds,
    es_histograms,
)

__all__ = [
    "Condition",
    "Stack",
    "SharedGaussianFit",
    "BindingFit",
    "TitrationResult",
    "build_stack",
    "fit_shared_gaussians",
    "fit_binding",
    "run_titration",
    "BINDING_MODELS",
]

#: Binding models offered by :func:`fit_binding`, by name.
BINDING_MODELS = ("hill", "one_site")


@dataclass(frozen=True)
class Condition:
    """One point of a titration: a concentration and the bursts measured at it.

    Attributes
    ----------
    concentration : float
        Ligand concentration, in whatever unit the whole series uses (the fitted
        ``K_d`` comes back in the same one).
    source : str or pathlib.Path or dict
        A burst table, as accepted by
        :func:`~chisurf.plugins.burst.alex_suite.api.histograms.load_channels`.
    label : str
        Display name; defaults to the concentration.
    """

    concentration: float
    source: str | pathlib.Path | dict
    label: str = ""

    def display(self) -> str:
        """Return the label, falling back to the concentration."""
        return self.label or f"{self.concentration:g}"


@dataclass
class Stack:
    """The stack plot: one E histogram per concentration, on a common axis.

    Attributes
    ----------
    concentrations : ndarray
        One value per condition, in the order given.
    labels : list of str
        Display names, parallel to ``concentrations``.
    centres : ndarray
        Shared E bin centres.
    histograms : ndarray
        ``(n_conditions, n_bins)``, each row area-normalised to 1 unless
        ``normalise=False`` was passed to :func:`build_stack`.
    counts : ndarray
        Bursts behind each row, before normalisation.
    """

    concentrations: np.ndarray
    labels: list[str]
    centres: np.ndarray
    histograms: np.ndarray
    counts: np.ndarray

    def __len__(self) -> int:
        """Return the number of conditions."""
        return len(self.concentrations)


@dataclass
class SharedGaussianFit:
    """A multi-Gaussian fit with shared shape and per-condition amplitudes.

    Attributes
    ----------
    centres, widths : ndarray
        ``(n_components,)`` — shared across every condition.
    amplitudes : ndarray
        ``(n_conditions, n_components)`` peak heights.
    fractions : ndarray
        ``(n_conditions, n_components)`` component *areas*, normalised to 1 per
        condition. This is what the isotherm is fitted to.
    curves : ndarray
        ``(n_conditions, n_bins)`` model histograms.
    components : ndarray
        ``(n_conditions, n_components, n_bins)`` individual components.
    chi2r : float
        Reduced sum of squared residuals over the whole series.
    """

    centres: np.ndarray
    widths: np.ndarray
    amplitudes: np.ndarray
    fractions: np.ndarray
    curves: np.ndarray
    components: np.ndarray
    chi2r: float = 0.0


@dataclass
class BindingFit:
    """A binding isotherm fitted to one component's fraction vs concentration.

    Attributes
    ----------
    model : str
        ``"hill"`` or ``"one_site"``.
    kd : float
        Dissociation constant, in the concentration unit of the series.
    hill : float
        Hill coefficient (exactly 1 for ``"one_site"``).
    f_min, f_max : float
        Fraction at zero and at saturating concentration.
    curve_x, curve_y : ndarray
        A smooth curve for plotting, over the measured concentration range.
    chi2r : float
        Reduced sum of squared residuals.
    """

    model: str
    kd: float
    hill: float
    f_min: float
    f_max: float
    curve_x: np.ndarray = field(default_factory=lambda: np.empty(0))
    curve_y: np.ndarray = field(default_factory=lambda: np.empty(0))
    chi2r: float = 0.0

    def evaluate(self, concentration) -> np.ndarray:
        """Return the fitted fraction at the given concentration(s)."""
        return _binding_curve(
            np.asarray(concentration, dtype=float),
            self.kd,
            self.hill,
            self.f_min,
            self.f_max,
        )


@dataclass
class TitrationResult:
    """Everything :func:`run_titration` produces."""

    stack: Stack
    fit: SharedGaussianFit
    binding: BindingFit | None
    component: int = -1


# ── the stack ───────────────────────────────────────────────────────────────


def build_stack(
    conditions,
    *,
    corrections: Corrections = Corrections(),
    thresholds: Thresholds = Thresholds(),
    bins: int = 81,
    e_limits: tuple[float, float] = (0.0, 1.0),
    normalise: bool = True,
    hints: dict | None = None,
) -> Stack:
    """Build one E histogram per condition on a common axis.

    Conditions are sorted by concentration, because a stack plot that is not
    monotonic in the titrant reads as noise.

    Parameters
    ----------
    conditions : sequence of Condition
        One per ligand concentration.
    corrections, thresholds : Corrections, Thresholds
        Applied identically to every condition — that is the point of a series.
    bins : int
        Number of E bins.
    e_limits : tuple of float
        Efficiency range.
    normalise : bool
        Area-normalise each row, so conditions with different burst counts are
        comparable. Turn it off to see the raw counts.
    hints : dict, optional
        Column-naming hints.

    Returns
    -------
    Stack

    Raises
    ------
    ValueError
        If fewer than two conditions were given.
    """
    ordered = sorted(conditions, key=lambda c: float(c.concentration))
    if len(ordered) < 2:
        raise ValueError("a titration needs at least two conditions")

    rows, counts = [], []
    centres = None
    for condition in ordered:
        hist = es_histograms(
            condition.source,
            corrections=corrections,
            thresholds=thresholds,
            bins=(bins, bins),
            e_limits=e_limits,
            hints=hints,
        )
        centres = hist.e_centres
        row = np.asarray(hist.e_hist, dtype=float)
        counts.append(float(row.sum()))
        if normalise:
            width = centres[1] - centres[0] if centres.size > 1 else 1.0
            area = row.sum() * width
            row = row / area if area > 0 else row
        rows.append(row)

    return Stack(
        concentrations=np.array([c.concentration for c in ordered], dtype=float),
        labels=[c.display() for c in ordered],
        centres=np.asarray(centres, dtype=float),
        histograms=np.vstack(rows),
        counts=np.asarray(counts, dtype=float),
    )


# ── the shared-shape fit ────────────────────────────────────────────────────


def _basis(centres: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Return the ``(n_bins, n_components)`` Gaussian design matrix."""
    x = centres[:, None]
    return np.exp(-0.5 * ((x - mu[None, :]) / sigma[None, :]) ** 2)


def _solve_amplitudes(design: np.ndarray, histograms: np.ndarray) -> np.ndarray:
    """Non-negative amplitudes per condition for a fixed Gaussian basis.

    Non-negative because a negative amount of a species is not a fit, it is a
    numerically convenient way to describe a baseline — and once one component
    goes negative the "fraction" the isotherm is read from stops being a
    fraction.
    """
    from scipy.optimize import nnls

    out = np.empty((histograms.shape[0], design.shape[1]))
    for i, row in enumerate(histograms):
        out[i], _ = nnls(design, row)
    return out


def fit_shared_gaussians(
    stack: Stack,
    n_components: int = 2,
    *,
    centres: np.ndarray | None = None,
    widths: np.ndarray | None = None,
    fix_centres: bool = False,
    fix_widths: bool = False,
    min_width: float = 0.01,
    max_width: float = 0.5,
) -> SharedGaussianFit:
    """Fit the whole series with shared centres/widths and free amplitudes.

    Parameters
    ----------
    stack : Stack
        From :func:`build_stack`.
    n_components : int
        Number of populations.
    centres, widths : ndarray, optional
        Starting values (and, with ``fix_*``, the fixed values). Default centres
        are spread evenly over the histogram range; default widths are a fifth of
        the spacing between them.
    fix_centres, fix_widths : bool
        Hold the shape parameters at their starting values — the old program's
        "fixed x0 and sigma" preset, useful when a control measurement has
        already established where the populations are.
    min_width, max_width : float
        Bounds on the shared widths.

    Returns
    -------
    SharedGaussianFit

    Raises
    ------
    ValueError
        If ``n_components`` is not positive, or a fixed starting value has the
        wrong length.
    """
    from scipy.optimize import least_squares

    if n_components < 1:
        raise ValueError("n_components must be >= 1")

    x = stack.centres
    lo, hi = float(x[0]), float(x[-1])
    if centres is None:
        centres = np.linspace(
            lo + (hi - lo) / (n_components + 1),
            hi - (hi - lo) / (n_components + 1),
            n_components,
        )
    centres = np.asarray(centres, dtype=float).ravel()
    if widths is None:
        spacing = (hi - lo) / max(n_components, 1)
        widths = np.full(n_components, np.clip(spacing / 5.0, min_width, max_width))
    widths = np.asarray(widths, dtype=float).ravel()
    if centres.size != n_components or widths.size != n_components:
        raise ValueError("centres/widths must have n_components entries")

    free_mu = not fix_centres
    free_sigma = not fix_widths

    def unpack(theta):
        i = 0
        mu = theta[i : i + n_components] if free_mu else centres
        i += n_components if free_mu else 0
        sigma = theta[i : i + n_components] if free_sigma else widths
        return np.asarray(mu, dtype=float), np.asarray(sigma, dtype=float)

    def residual(theta):
        mu, sigma = unpack(theta)
        design = _basis(x, mu, sigma)
        amplitudes = _solve_amplitudes(design, stack.histograms)
        model = amplitudes @ design.T
        return (model - stack.histograms).ravel()

    theta0, lower, upper = [], [], []
    if free_mu:
        theta0.append(centres)
        lower.append(np.full(n_components, lo))
        upper.append(np.full(n_components, hi))
    if free_sigma:
        theta0.append(np.clip(widths, min_width, max_width))
        lower.append(np.full(n_components, min_width))
        upper.append(np.full(n_components, max_width))

    if theta0:
        result = least_squares(
            residual,
            np.concatenate(theta0),
            bounds=(np.concatenate(lower), np.concatenate(upper)),
        )
        mu, sigma = unpack(result.x)
        residuals = result.fun
    else:
        mu, sigma = centres, widths
        residuals = residual(np.empty(0))

    # Sorting by centre makes "component 0" mean the same thing across runs, so
    # the isotherm is always read from the population the user picked and not
    # from whichever one the optimiser happened to list first.
    order = np.argsort(mu)
    mu, sigma = mu[order], sigma[order]

    design = _basis(x, mu, sigma)
    amplitudes = _solve_amplitudes(design, stack.histograms)
    components = amplitudes[:, :, None] * design.T[None, :, :]
    curves = components.sum(axis=1)

    areas = amplitudes * sigma[None, :] * np.sqrt(2.0 * np.pi)
    totals = areas.sum(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        fractions = np.where(totals > 0, areas / totals, 0.0)

    n_free = (n_components if free_mu else 0) + (n_components if free_sigma else 0)
    n_free += amplitudes.size
    dof = max(residuals.size - n_free, 1)
    return SharedGaussianFit(
        centres=mu,
        widths=sigma,
        amplitudes=amplitudes,
        fractions=fractions,
        curves=curves,
        components=components,
        chi2r=float(np.sum(residuals**2) / dof),
    )


# ── the isotherm ────────────────────────────────────────────────────────────


def _binding_curve(c, kd, hill, f_min, f_max):
    """Hill binding curve ``f_min + (f_max - f_min) * c^n / (Kd^n + c^n)``."""
    c = np.asarray(c, dtype=float)
    # c = 0 with n < 1 is 0**negative = inf; the limit of the ratio is 0 there
    # (no ligand, no complex), and writing it out is cheaper than nan-cleaning
    # a whole curve afterwards.
    powered = np.where(c > 0, np.power(np.maximum(c, 1e-300), hill), 0.0)
    kd_n = np.power(max(kd, 1e-300), hill)
    return f_min + (f_max - f_min) * powered / (kd_n + powered)


def fit_binding(
    concentrations,
    fractions,
    *,
    model: str = "hill",
    fix_baseline: bool = False,
) -> BindingFit:
    """Fit a binding isotherm to a component fraction vs concentration.

    Parameters
    ----------
    concentrations : array_like
        One per condition.
    fractions : array_like
        The fraction of the population that reports binding, one per condition.
    model : {"hill", "one_site"}
        ``"one_site"`` holds the Hill coefficient at 1.
    fix_baseline : bool
        Hold ``f_min``/``f_max`` at the first and last measured fraction instead
        of fitting them. Use it when the series does not reach saturation, where
        a free ``f_max`` and ``K_d`` trade off against each other and both come
        back meaningless with small error bars.

    Returns
    -------
    BindingFit

    Raises
    ------
    ValueError
        For an unknown model or fewer than three points.
    """
    from scipy.optimize import least_squares

    if model not in BINDING_MODELS:
        raise ValueError(f"model must be one of {BINDING_MODELS}, got {model!r}")
    c = np.asarray(concentrations, dtype=float)
    f = np.asarray(fractions, dtype=float)
    if c.size < 3:
        raise ValueError("a binding fit needs at least three concentrations")

    f_min0, f_max0 = float(f[0]), float(f[-1])
    positive = c[c > 0]
    kd0 = float(np.exp(np.mean(np.log(positive)))) if positive.size else 1.0

    free_hill = model == "hill"
    free_baseline = not fix_baseline

    def unpack(theta):
        i = 0
        kd = float(np.exp(theta[i]))
        i += 1
        hill = float(theta[i]) if free_hill else 1.0
        i += 1 if free_hill else 0
        if free_baseline:
            f_min, f_max = float(theta[i]), float(theta[i + 1])
        else:
            f_min, f_max = f_min0, f_max0
        return kd, hill, f_min, f_max

    def residual(theta):
        kd, hill, f_min, f_max = unpack(theta)
        return _binding_curve(c, kd, hill, f_min, f_max) - f

    theta0 = [np.log(max(kd0, 1e-300))]
    lower = [np.log(1e-12)]
    upper = [np.log(1e12)]
    if free_hill:
        theta0.append(1.0)
        lower.append(0.1)
        upper.append(10.0)
    if free_baseline:
        theta0 += [f_min0, f_max0]
        lower += [-1.0, -1.0]
        upper += [2.0, 2.0]

    result = least_squares(residual, theta0, bounds=(lower, upper))
    kd, hill, f_min, f_max = unpack(result.x)

    finite = c[c > 0]
    if finite.size:
        curve_x = np.logspace(np.log10(finite.min() / 10.0), np.log10(finite.max() * 10.0), 200)
    else:
        curve_x = np.linspace(0.0, 1.0, 200)
    dof = max(result.fun.size - len(theta0), 1)
    return BindingFit(
        model=model,
        kd=kd,
        hill=hill,
        f_min=f_min,
        f_max=f_max,
        curve_x=curve_x,
        curve_y=_binding_curve(curve_x, kd, hill, f_min, f_max),
        chi2r=float(np.sum(result.fun**2) / dof),
    )


def _reporting_component(concentrations, fractions) -> int:
    """Pick the population whose fraction reports binding.

    The one that *grows* with ligand, and among those the one that grows most.
    With two complementary populations the spans are equal and "largest change"
    is a coin toss, which half the time plots the free species and labels a
    falling curve with a K_d -- correct arithmetic, and unreadable as a binding
    isotherm.

    Falls back to the largest change when nothing increases (a competition
    experiment, or a series that only loses signal), because then there is no
    growing species to prefer.
    """
    fractions = np.asarray(fractions, dtype=float)
    span = fractions.max(axis=0) - fractions.min(axis=0)
    order = np.argsort(np.asarray(concentrations, dtype=float))
    rising = fractions[order][-1] > fractions[order][0]
    if rising.any():
        return int(np.argmax(np.where(rising, span, -np.inf)))
    return int(np.argmax(span))


def run_titration(
    conditions,
    *,
    n_components: int = 2,
    component: int = -1,
    binding_model: str = "hill",
    corrections: Corrections = Corrections(),
    thresholds: Thresholds = Thresholds(),
    bins: int = 81,
    e_limits: tuple[float, float] = (0.0, 1.0),
    fix_centres: bool = False,
    fix_widths: bool = False,
    hints: dict | None = None,
) -> TitrationResult:
    """Stack, fit and extract the isotherm in one call.

    Parameters
    ----------
    conditions : sequence of Condition
        One per ligand concentration.
    n_components : int
        Populations in the shared-shape fit.
    component : int
        Which component's fraction is the isotherm. ``-1`` (the default) means
        *the one that changes most* across the series — with two populations
        that is unambiguous, and it saves picking by eye.
    binding_model : {"hill", "one_site"}
        Isotherm model; ``"one_site"`` holds the Hill coefficient at 1.
    corrections, thresholds, bins, e_limits, fix_centres, fix_widths, hints
        Passed through to :func:`build_stack` and :func:`fit_shared_gaussians`.

    Returns
    -------
    TitrationResult
        ``binding`` is ``None`` when there were too few conditions to fit one.
    """
    stack = build_stack(
        conditions,
        corrections=corrections,
        thresholds=thresholds,
        bins=bins,
        e_limits=e_limits,
        hints=hints,
    )
    fit = fit_shared_gaussians(stack, n_components, fix_centres=fix_centres, fix_widths=fix_widths)

    index = component
    if index < 0:
        index = _reporting_component(stack.concentrations, fit.fractions)

    binding = None
    if len(stack) >= 3:
        binding = fit_binding(stack.concentrations, fit.fractions[:, index], model=binding_model)
    return TitrationResult(stack=stack, fit=fit, binding=binding, component=index)
