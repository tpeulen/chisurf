"""Accurate FRET: corrected E/S with uncertainties, and automatic calibration.

Where :mod:`chisurf.core.fluorescence.burst.es` *applies* correction factors and
:mod:`chisurf.core.fluorescence.fret.calibration` *holds* them (as fitting
parameters with light-path priors), this module closes the loop: it determines
the factors **from the data itself**, without hand-drawn gates, and reports the
accurate efficiency together with its uncertainty.

Three things are added here.

**Accurate E/R with error bars.** :func:`accurate_fret` returns the corrected
efficiency and stoichiometry plus the propagated uncertainty of the population
mean — the systematic part contributed by ``alpha``/``delta``/``gamma`` and the
statistical part from the burst scatter — and converts the efficiency into a
distance with its own error (Hellenkamp *et al.*, Nat. Methods 15, 669, 2018,
whose benchmark study showed that these systematics, not counting statistics,
dominate the spread between laboratories).

**Automatic correction factors.** :func:`auto_calibrate` finds the donor-only,
acceptor-only and FRET populations by fitting a Gaussian mixture to the
stoichiometry (no manual thresholds), estimates ``alpha`` from the donor-only and
``delta`` from the acceptor-only bursts, and recovers ``gamma``/``beta`` from the
``1/S`` vs ``E`` fit over the FRET sub-populations. Because the classification
itself depends on the factors, the whole chain is iterated to self-consistency.

**The optics are the prior.** ``gamma``, ``alpha`` and ``delta`` are not free
inventions of the fit: they follow from the excitation and emission probabilities
of the light path — which laser excites which dye, and which fraction of each
dye's emission reaches each detector. The light-path calculator computes those
probabilities and
:func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`
turns them into Gaussian priors whose width is the optical-model uncertainty.
:func:`auto_calibrate` starts from those values and returns the
**precision-weighted posterior**: an informative dataset moves the factors away
from the optics, a poor one leaves them there, and a factor the data cannot
identify at all (no donor-only bursts, say) simply keeps the optical value with
the optical uncertainty.

**Lifetime-assisted ``gamma``.** The E–S route needs at least two FRET
populations of different efficiency; a single-population sample does not
identify ``gamma``. If a per-burst donor lifetime is available, the *static FRET
line* supplies the missing information: a static population must lie on the line,
so ``gamma`` is whatever makes the intensity-based efficiency agree with the
lifetime-based one (:func:`gamma_from_lifetime`). The same comparison run *after*
calibration is a dynamics test — a population sitting above the static line
exchanges within the burst.

All functions are Qt-free, vectorized over bursts and usable head-less.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.burst.es import corrected_es
from chisurf.core.fluorescence.fret.calibration import (
    CalibrationParameters,
    direct_excitation_from_acceptor_only,
    global_es_correction,
    leakage_from_donor_only,
)
from chisurf.core.fluorescence.fret.lines import FretLine, static_fret_line

__all__ = [
    "PopulationSplit",
    "AutoCalibration",
    "gaussian_mixture_1d",
    "classify_es_populations",
    "split_fret_subpopulations",
    "efficiency_uncertainty",
    "distance_from_efficiency",
    "accurate_fret",
    "beta_from_stoichiometry",
    "gamma_from_lifetime",
    "auto_calibrate",
]


# ---------------------------------------------------------------------------
# 1-D Gaussian mixture (the automatic gate)
# ---------------------------------------------------------------------------


def gaussian_mixture_1d(
    x,
    n_components: int,
    *,
    n_iterations: int = 300,
    tolerance: float = 1e-7,
    sigma_floor: float = 1e-3,
    init: str = "auto",
    seed: int = 0,
) -> dict:
    """Fit a one-dimensional Gaussian mixture by expectation-maximization.

    Deterministic and dependency-free, so automatic population gating does not
    pull in a machine-learning stack and gives the same answer on every run.

    Two initializations are tried and the better likelihood is kept, because
    neither alone is safe here. Quantile-spaced starts follow the density and
    handle overlapping components, but when one population dominates (a burst
    measurement is mostly doubly labelled molecules) every start lands inside it
    and the small reference populations get swallowed by one broad component —
    which then puts the class boundary in the wrong place. Range-spaced starts
    cover the axis instead, which is what separates a sparse population at
    ``S ≈ 0`` from a dense one at ``S ≈ 0.5``.

    Parameters
    ----------
    x : array_like
        Samples (non-finite values are ignored).
    n_components : int
        Number of Gaussian components.
    n_iterations : int, optional
        Maximum EM iterations.
    tolerance : float, optional
        Convergence threshold on the relative log-likelihood change.
    sigma_floor : float, optional
        Lower bound on the component widths (keeps EM from collapsing onto a
        single burst).
    init : str, optional
        ``"auto"`` (try both and keep the better), ``"quantile"`` or ``"range"``.
    seed : int, optional
        Unused placeholder kept for signature stability; the fit is
        deterministic.

    Returns
    -------
    dict
        ``{"weights", "means", "sigmas", "responsibilities", "log_likelihood",
        "bic", "labels"}``; ``labels`` is the most-likely component per sample.
    """
    del seed  # deterministic initialization; kept for call-site compatibility
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    k = max(1, int(n_components))
    if x.size == 0:
        raise ValueError("gaussian_mixture_1d needs at least one finite sample")

    starts = []
    if init in ("auto", "quantile"):
        starts.append(np.quantile(x, (np.arange(k) + 0.5) / k))
    if init in ("auto", "range") and k > 1:
        lo, hi = float(np.min(x)), float(np.max(x))
        starts.append(np.linspace(lo, hi, k) if hi > lo else np.full(k, lo))
    if not starts:
        starts.append(np.quantile(x, (np.arange(k) + 0.5) / k))

    best = None
    for start in starts:
        fit = _em_1d(
            x, start, n_iterations=n_iterations, tolerance=tolerance, sigma_floor=sigma_floor
        )
        if best is None or fit["log_likelihood"] > best["log_likelihood"]:
            best = fit
    return best


def _em_1d(x, means, *, n_iterations: int, tolerance: float, sigma_floor: float) -> dict:
    """One expectation-maximization run of a 1-D Gaussian mixture from ``means``.

    The EM itself is not written here. A 1-D mixture of Gaussians is exactly
    :class:`~chisurf.core.ml.mixture.GaussianMixture` at
    ``covariance_type="spherical"`` with one feature, so this is the adapter
    that keeps the gating call sites' parameter surface (``sigma_floor``, a
    relative ``tolerance``, mean-sorted output) over the one shared estimator.
    Holding a second copy of the algorithm here is what let the two disagree:
    the copy this replaces normalised its responsibilities with a bare
    ``exp(log_p - log_p.max(axis=1))``, which is ``nan`` for a sample no
    component can explain, where the shared kernel returns a uniform
    responsibility.

    Two deliberate differences from the body this replaces, neither of which
    moves a converged fit:

    * ``tolerance`` is applied as an absolute gain in the total
      log-likelihood rather than a relative one, so a run stops **no earlier**
      than before -- the same fixed point from the same start, with the
      iteration count as the only visible change.
    * a component that collects no mass keeps the weight the data gives it
      (effectively zero) rather than the old ``1e-6`` floor; its width is held
      at ``sigma_floor`` by the shared estimator's ridge.
    """
    from chisurf.core.ml import GaussianMixture

    k = int(np.size(means))
    n = int(x.size)
    start = np.asarray(means, dtype=float).reshape(k, 1)
    spread = float(np.std(x)) or 1.0
    sigma_start = max(spread / max(k, 1), sigma_floor)

    fitted = GaussianMixture(
        n_components=k,
        covariance_type="spherical",
        means_init=start,
        covariances_init=np.full(k, sigma_start**2),
        weights_init=np.full(k, 1.0 / k),
        init_params="random",
        # The estimator's ridge is additive on the variance, so it *is* the
        # width floor this call site asks for.
        reg_covar=float(sigma_floor) ** 2,
        max_iter=int(n_iterations),
        tol=float(tolerance),
        n_init=1,
    ).fit(x[:, None])

    resp = fitted.predict_proba(x[:, None])
    fitted_means = fitted.means_.ravel()
    sigmas = np.maximum(np.sqrt(np.maximum(fitted.covariances_, 0.0)), sigma_floor)
    log_likelihood = float(fitted.lower_bound_)

    n_free = 3 * k - 1
    bic = n_free * np.log(max(n, 2)) - 2.0 * log_likelihood
    order = np.argsort(fitted_means)
    return {
        "weights": np.asarray(fitted.weights_)[order],
        "means": fitted_means[order],
        "sigmas": np.asarray(sigmas)[order],
        "responsibilities": resp[:, order],
        "labels": np.argmax(resp[:, order], axis=1),
        "log_likelihood": log_likelihood,
        "bic": float(bic),
        "n_iter": int(fitted.n_iter_),
    }


def _best_mixture(x, *, max_components: int = 4, min_weight: float = 0.02) -> dict:
    """Pick the component number by BIC, dropping negligible components.

    Parameters
    ----------
    x : array_like
        Samples.
    max_components : int, optional
        Largest number of components tried.
    min_weight : float, optional
        Components holding less than this fraction of the data are rejected
        (the smaller model is used instead).

    Returns
    -------
    dict
        The chosen :func:`gaussian_mixture_1d` result, with the tried BIC values
        under ``"bic_by_k"``.
    """
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    best = None
    bics: dict[int, float] = {}
    for k in range(1, int(max_components) + 1):
        if x.size < 5 * k:
            break
        try:
            fit = gaussian_mixture_1d(x, k)
        except ValueError:
            break
        bics[k] = fit["bic"]
        if np.min(fit["weights"]) < min_weight and k > 1:
            continue
        if best is None or fit["bic"] < best["bic"]:
            best = fit
    if best is None:
        best = gaussian_mixture_1d(x, 1)
    best["bic_by_k"] = bics
    return best


# ---------------------------------------------------------------------------
# population classification
# ---------------------------------------------------------------------------


@dataclass
class PopulationSplit:
    """Which bursts are donor-only, acceptor-only and doubly labelled.

    Attributes
    ----------
    donor_only, acceptor_only, fret : numpy.ndarray
        Boolean masks over the bursts.
    fret_labels : numpy.ndarray
        Sub-population index for the FRET bursts (``-1`` for every burst that is
        not a FRET burst), as used by the ``1/S`` vs ``E`` fit.
    thresholds : tuple of float
        The stoichiometry boundaries that separate the three classes — derived
        from the fitted mixture, or the fixed values when the mixture was not
        used.
    method : str
        ``"mixture"`` or ``"threshold"``.
    components : dict
        Diagnostics of the stoichiometry mixture (means, weights, sigmas).
    """

    donor_only: np.ndarray
    acceptor_only: np.ndarray
    fret: np.ndarray
    fret_labels: np.ndarray
    thresholds: tuple[float, float]
    method: str = "mixture"
    components: dict = field(default_factory=dict)

    @property
    def counts(self) -> dict:
        """Number of bursts per class (``donor_only``/``acceptor_only``/``fret``)."""
        return {
            "donor_only": int(np.count_nonzero(self.donor_only)),
            "acceptor_only": int(np.count_nonzero(self.acceptor_only)),
            "fret": int(np.count_nonzero(self.fret)),
            "fret_populations": int(len(np.unique(self.fret_labels[self.fret_labels >= 0]))),
        }


def classify_es_populations(
    stoichiometry,
    efficiency=None,
    *,
    donor_only_above: float = 0.75,
    acceptor_only_below: float = 0.25,
    max_components: int = 4,
    max_fret_populations: int = 3,
    min_population: int = 20,
    reference_sigma: float = 2.0,
    method: str = "auto",
) -> PopulationSplit:
    """Find donor-only, acceptor-only and FRET bursts without manual gates.

    The stoichiometry separates the three species: a donor-only molecule has
    ``S ≈ 1`` (nothing is emitted under acceptor excitation), an acceptor-only
    molecule ``S ≈ 0``, and a doubly labelled molecule sits in between. Rather
    than cutting at fixed values — which biases every downstream factor when the
    populations are shifted — a Gaussian mixture is fitted to the stoichiometry
    and each *component* is assigned to a class by its centre. The cut is then
    placed where the neighbouring components cross.

    Parameters
    ----------
    stoichiometry : array_like
        Per-burst stoichiometry ``S`` (apparent or corrected).
    efficiency : array_like, optional
        Per-burst efficiency; when given, the FRET bursts are additionally split
        into sub-populations (:func:`split_fret_subpopulations`), which is what
        makes the ``gamma``/``beta`` fit possible.
    donor_only_above : float, optional
        A mixture component centred above this stoichiometry is donor-only.
    progress : callable, optional
        Called as ``progress(step, total, message)`` after each refinement
        iteration and each bootstrap resample, so a caller can drive a bar.
        The work is not uniform -- the classification runs once per iteration
        and the bootstrap once per resample -- so the steps are counted, not
        timed. Returning ``False`` asks the calibration to stop early and
        return what it has; anything else continues. Exceptions raised by the
        callback are not caught: a cancel that has to be signalled by raising
        is the caller's business, not this function's.
    acceptor_only_below : float, optional
        A mixture component centred below this stoichiometry is acceptor-only.
    max_components : int, optional
        Largest number of stoichiometry components tried.
    max_fret_populations : int, optional
        Largest number of FRET sub-populations tried.
    min_population : int, optional
        Classes with fewer bursts than this are treated as absent.
    reference_sigma : float, optional
        Half-width, in units of the fitted component's own standard deviation, of
        the **core** each reference class is restricted to. The two jobs differ:
        the FRET class must be *complete* (it only has to contain the molecules
        whose efficiency is wanted), while the donor-only and acceptor-only
        classes must be *pure* — they define ``alpha`` and ``delta``, and a
        doubly labelled burst leaking into them biases those factors directly.
        Cutting at the midpoint between components serves neither; the core cut
        buys purity with bursts the ratio estimators do not miss. ``0`` restores
        the plain midpoint cut.
    method : str, optional
        ``"auto"`` (mixture, falling back to thresholds) or ``"threshold"``.

    Returns
    -------
    PopulationSplit
        The masks, sub-population labels and the thresholds actually used.
    """
    s = np.asarray(stoichiometry, dtype=float).ravel()
    finite = np.isfinite(s)
    lo, hi = float(acceptor_only_below), float(donor_only_above)
    used_method = "threshold"
    components: dict = {}

    #: Core cuts of the reference classes (see ``reference_sigma``); None = midpoint.
    donor_core = acceptor_core = None
    if method != "threshold" and np.count_nonzero(finite) >= 5 * 3:
        try:
            fit = _best_mixture(s[finite], max_components=max_components)
            means, sigmas = fit["means"], fit["sigmas"]
            # Class per component, then the cut where neighbouring components meet.
            klass = np.where(means >= hi, 1, np.where(means <= lo, -1, 0))
            if np.any(klass == 0):
                fret_means = means[klass == 0]
                if np.any(klass == -1):
                    index = int(np.argmax(np.where(klass == -1, means, -np.inf)))
                    lo = float(0.5 * (means[index] + np.min(fret_means)))
                    if reference_sigma > 0:
                        acceptor_core = float(means[index] + reference_sigma * sigmas[index])
                if np.any(klass == 1):
                    index = int(np.argmin(np.where(klass == 1, means, np.inf)))
                    hi = float(0.5 * (np.max(fret_means) + means[index]))
                    if reference_sigma > 0:
                        donor_core = float(means[index] - reference_sigma * sigmas[index])
                used_method = "mixture"
                components = {
                    "means": means.tolist(),
                    "weights": fit["weights"].tolist(),
                    "sigmas": sigmas.tolist(),
                    "bic_by_k": fit.get("bic_by_k", {}),
                }
        except Exception:  # pragma: no cover - degenerate data falls back
            used_method = "threshold"

    # The FRET class keeps the midpoint cuts (completeness); the reference classes
    # are restricted to the core of their own component (purity).
    donor_only = finite & (s > max(hi, donor_core if donor_core is not None else hi))
    acceptor_only = finite & (s < min(lo, acceptor_core if acceptor_core is not None else lo))
    fret = finite & ~(s > hi) & ~(s < lo)
    if np.count_nonzero(donor_only) < min_population:
        donor_only = np.zeros_like(donor_only)
    if np.count_nonzero(acceptor_only) < min_population:
        acceptor_only = np.zeros_like(acceptor_only)

    fret_labels = np.full(s.shape, -1, dtype=int)
    if efficiency is not None and np.count_nonzero(fret) >= min_population:
        e = np.asarray(efficiency, dtype=float).ravel()
        sub = split_fret_subpopulations(
            e[fret], max_populations=max_fret_populations, min_population=min_population
        )
        fret_labels[fret] = sub
    elif np.any(fret):
        fret_labels[fret] = 0

    return PopulationSplit(
        donor_only=donor_only,
        acceptor_only=acceptor_only,
        fret=fret,
        fret_labels=fret_labels,
        thresholds=(lo, hi),
        method=used_method,
        components=components,
    )


def split_fret_subpopulations(
    efficiency,
    *,
    max_populations: int = 3,
    min_population: int = 20,
    min_separation: float = 0.05,
    min_fraction: float = 0.1,
) -> np.ndarray:
    """Split doubly-labelled bursts into efficiency sub-populations.

    The detection factor ``gamma`` is identified by how the stoichiometry varies
    *between* populations of different efficiency, so a sample containing several
    FRET states calibrates itself. This finds those states with a
    BIC-selected Gaussian mixture over the efficiency.

    Parameters
    ----------
    efficiency : array_like
        Per-burst FRET efficiency of the doubly labelled bursts.
    max_populations : int, optional
        Largest number of sub-populations tried.
    min_population : int, optional
        Sub-populations smaller than this are merged into their neighbour.
    min_separation : float, optional
        Sub-populations whose centres are closer than this in efficiency are
        merged (they carry no independent information for the ``gamma`` fit).
    min_fraction : float, optional
        Sub-populations holding less than this fraction of the bursts are merged
        into their neighbour. Shot noise smears a two-state sample into a
        continuum, and a mixture will happily place a small extra component in
        the valley between the real states; that component is a selection on
        noise, not a species, and its centre lies off the ``1/S`` vs ``E`` line
        it would otherwise be fitted to.

    Returns
    -------
    numpy.ndarray
        Sub-population index per burst, numbered by increasing efficiency.
    """
    e = np.asarray(efficiency, dtype=float).ravel()
    labels = np.zeros(e.size, dtype=int)
    finite = np.isfinite(e)
    if np.count_nonzero(finite) < 2 * min_population or max_populations < 2:
        return labels
    fit = _best_mixture(e[finite], max_components=int(max_populations))
    lab = np.zeros(e.size, dtype=int)
    lab[finite] = fit["labels"]

    # Merge components that are too small or too close to be independent.
    means = fit["means"]
    n_finite = int(np.count_nonzero(finite))
    floor = max(int(min_population), int(np.ceil(float(min_fraction) * n_finite)))
    keep: list[int] = []
    for i in range(means.size):
        n_i = int(np.count_nonzero(lab[finite] == i))
        if n_i < floor:
            continue
        if keep and abs(means[i] - means[keep[-1]]) < min_separation:
            continue
        keep.append(i)
    if len(keep) < 2:
        return labels
    remap = {c: j for j, c in enumerate(keep)}
    out = np.zeros(e.size, dtype=int)
    for i in range(means.size):
        target = remap.get(i)
        if target is None:
            # Attach to the nearest kept component.
            target = int(np.argmin([abs(means[i] - means[c]) for c in keep]))
        out[lab == i] = target
    return out


# ---------------------------------------------------------------------------
# accurate efficiency, uncertainty and distance
# ---------------------------------------------------------------------------


def efficiency_uncertainty(
    efficiency,
    f_dd,
    f_aa=None,
    *,
    gamma: float = 1.0,
    sigma_gamma: float = 0.0,
    sigma_alpha: float = 0.0,
    sigma_delta: float = 0.0,
    sigma_statistical=None,
) -> dict:
    """Propagate the calibration uncertainties into the FRET efficiency.

    With ``E = F_DA / (F_DA + gamma·F_DD)`` and
    ``F_DA = I_DA − B_DA − alpha·F_DD − delta·F_AA`` the partial derivatives are

    ``dE/dgamma = −E(1−E)/gamma``, ``dE/dalpha = −(1−E)²/gamma`` and
    ``dE/ddelta = −(1−E)²·F_AA/(gamma·F_DD)``,

    so the systematic error is largest at intermediate efficiency for ``gamma``
    and at low efficiency for the leakage/direct-excitation terms — the reason
    inter-laboratory FRET values scatter most for mid-range distances
    (Hellenkamp 2018).

    Parameters
    ----------
    efficiency : array_like
        Corrected efficiency (per burst or a population mean).
    f_dd : array_like
        Background-corrected donor signal under donor excitation.
    f_aa : array_like, optional
        Background-corrected acceptor signal under acceptor excitation
        (only needed for the ``delta`` term).
    gamma : float, optional
        Detection factor the efficiency was computed with.
    sigma_gamma, sigma_alpha, sigma_delta : float, optional
        Standard uncertainties of the correction factors.
    sigma_statistical : array_like, optional
        Statistical uncertainty of the efficiency (e.g. the standard error of a
        population mean) added in quadrature.

    Returns
    -------
    dict
        ``{"total", "systematic", "statistical", "terms"}`` with ``terms``
        holding the individual ``gamma``/``alpha``/``delta`` contributions.
    """
    e = np.asarray(efficiency, dtype=float)
    dd = np.asarray(f_dd, dtype=float)
    g = float(gamma) if gamma else 1.0
    one_minus = 1.0 - e
    d_gamma = np.abs(e * one_minus / g) * float(sigma_gamma)
    d_alpha = np.abs(one_minus**2 / g) * float(sigma_alpha)
    if f_aa is None:
        d_delta = np.zeros_like(e)
    else:
        aa = np.asarray(f_aa, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(dd != 0, aa / (g * dd), 0.0)
        d_delta = np.abs(one_minus**2 * ratio) * float(sigma_delta)
    systematic = np.sqrt(d_gamma**2 + d_alpha**2 + d_delta**2)
    statistical = (
        np.zeros_like(systematic)
        if sigma_statistical is None
        else np.abs(np.asarray(sigma_statistical, dtype=float))
    )
    return {
        "total": np.sqrt(systematic**2 + statistical**2),
        "systematic": systematic,
        "statistical": statistical,
        "terms": {"gamma": d_gamma, "alpha": d_alpha, "delta": d_delta},
    }


def distance_from_efficiency(
    efficiency, r0: float, *, sigma_efficiency=None, sigma_r0: float = 0.0
) -> dict:
    """Donor–acceptor distance from the accurate efficiency, with its error.

    ``R = R0 (1/E − 1)^{1/6}``. Because of the sixth root, the *relative*
    distance error is small in the middle of the dynamic range and diverges as
    ``E`` approaches 0 or 1:

    ``sigma_R/R = sqrt((sigma_R0/R0)² + (sigma_E / (6·E·(1−E)))²)``.

    Parameters
    ----------
    efficiency : array_like
        Accurate FRET efficiency.
    r0 : float
        Förster radius (Å), itself calibration-dependent (it scales with the
        donor quantum yield and the orientation factor).
    sigma_efficiency : array_like, optional
        Uncertainty of the efficiency.
    sigma_r0 : float, optional
        Uncertainty of the Förster radius.

    Returns
    -------
    dict
        ``{"distance", "sigma"}`` in Å (``NaN`` outside ``0 < E < 1``).
    """
    e = np.asarray(efficiency, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        valid = (e > 0.0) & (e < 1.0)
        r = np.where(
            valid, float(r0) * (1.0 / np.where(valid, e, 0.5) - 1.0) ** (1.0 / 6.0), np.nan
        )
    sigma = np.zeros_like(r)
    rel_r0 = (float(sigma_r0) / float(r0)) if r0 else 0.0
    if sigma_efficiency is None:
        rel_e = np.zeros_like(r)
    else:
        se = np.abs(np.asarray(sigma_efficiency, dtype=float))
        with np.errstate(divide="ignore", invalid="ignore"):
            rel_e = np.where(valid, se / (6.0 * e * (1.0 - e)), np.nan)
    sigma = r * np.sqrt(rel_r0**2 + rel_e**2)
    return {"distance": r, "sigma": sigma}


def accurate_fret(
    i_dd,
    i_da,
    i_aa=None,
    *,
    calibration=None,
    tau_f=None,
    line: FretLine | None = None,
    uncertainties: dict | None = None,
    labels=None,
) -> dict:
    """Accurate per-burst FRET efficiency, stoichiometry, distance and errors.

    Applies the calibration (:class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`,
    a plain mapping, or the defaults), propagates the factor uncertainties into
    the efficiency, converts it into a distance and — when a donor lifetime and a
    FRET line are supplied — reports how far each population sits from the line.

    Parameters
    ----------
    i_dd, i_da : array_like
        Per-burst donor and acceptor counts under donor excitation.
    i_aa : array_like, optional
        Per-burst acceptor counts under acceptor excitation (ALEX/PIE).
    calibration : CalibrationParameters or dict, optional
        Correction factors; defaults to an uncorrected calibration.
    tau_f : array_like, optional
        Per-burst fluorescence-averaged donor lifetime (ns).
    line : FretLine, optional
        Static FRET line used to compare the intensity- and lifetime-based
        efficiencies (the dynamics test).
    uncertainties : dict, optional
        ``{"gamma": …, "alpha": …, "delta": …, "r0": …}`` standard uncertainties
        of the factors; defaults to zero (statistical error only).
    labels : array_like, optional
        Population label per burst for the population summary; when omitted all
        bursts form one population.

    Returns
    -------
    dict
        ``{"E", "S", "fc", "sigma_E", "distance", "sigma_distance",
        "deviation", "populations", "calibration"}``. ``populations`` is a list
        of per-population summaries (mean E/S/lifetime/distance and their
        uncertainties).
    """
    factors = _as_factor_dict(calibration)
    # A factor whose uncertainty could not be estimated must not poison the
    # error propagation with NaN — it contributes nothing instead.
    unc = {"gamma": 0.0, "alpha": 0.0, "delta": 0.0, "r0": 0.0}
    for key, value in (uncertainties or {}).items():
        unc[key] = float(value) if value is not None and np.isfinite(value) else 0.0

    es = corrected_es(
        i_dd,
        i_da,
        i_aa,
        gamma=factors["gamma"],
        alpha=factors["alpha"],
        beta=factors["beta"],
        delta=factors["delta"],
        bg_dd=factors["bg_dd"],
        bg_da=factors["bg_da"],
        bg_aa=factors["bg_aa"],
    )
    e = np.asarray(es["E"], dtype=float)
    f_dd = np.asarray(i_dd, dtype=float) - factors["bg_dd"]
    f_aa = None if i_aa is None else np.asarray(i_aa, dtype=float) - factors["bg_aa"]

    sigma = efficiency_uncertainty(
        e,
        f_dd,
        f_aa,
        gamma=factors["gamma"],
        sigma_gamma=unc["gamma"],
        sigma_alpha=unc["alpha"],
        sigma_delta=unc["delta"],
    )
    dist = distance_from_efficiency(
        e, factors["r0"], sigma_efficiency=sigma["total"], sigma_r0=unc["r0"]
    )
    deviation = None
    if line is not None and tau_f is not None:
        deviation = line.deviation(e, tau_f)

    if labels is None:
        labels = np.zeros(e.shape, dtype=int)
    populations = _population_summary(
        e,
        es["S"],
        tau_f,
        np.asarray(labels),
        factors,
        unc,
        line,
        sigma_systematic=sigma["systematic"],
    )
    return {
        "E": e,
        "S": es["S"],
        "fc": es["fc"],
        "sigma_E": sigma["total"],
        "sigma_E_systematic": sigma["systematic"],
        "distance": dist["distance"],
        "sigma_distance": dist["sigma"],
        "deviation": deviation,
        "populations": populations,
        "calibration": factors,
    }


def _population_summary(
    e, s, tau_f, labels, factors, unc, line, sigma_systematic=None
) -> list[dict]:
    """Per-population mean efficiency, stoichiometry, lifetime and distance.

    One dictionary per label holding the population mean, its statistical error
    (standard error of the mean), the systematic error contributed by the
    calibration factors and the resulting distance. The systematic part is the
    mean of the per-burst propagation, so the ``delta`` term (which depends on
    the acceptor-excitation signal of each burst) is included.
    """
    out: list[dict] = []
    for u in np.unique(labels):
        m = labels == u
        n = int(np.count_nonzero(m & np.isfinite(e)))
        if n == 0:
            continue
        e_m = float(np.nanmean(e[m]))
        sem = float(np.nanstd(e[m]) / max(np.sqrt(n), 1.0))
        if sigma_systematic is None:
            sys_err = 0.0
        else:
            sys_err = float(np.nanmean(np.asarray(sigma_systematic, dtype=float)[m]))
        total = float(np.hypot(sys_err, sem))
        dist = distance_from_efficiency(
            e_m, factors["r0"], sigma_efficiency=total, sigma_r0=unc["r0"]
        )
        entry = {
            "label": u.item() if hasattr(u, "item") else u,
            "n": n,
            "E": e_m,
            "sigma_E": total,
            "sigma_E_statistical": sem,
            "sigma_E_systematic": sys_err,
            "S": float(np.nanmean(s[m])) if s is not None else float("nan"),
            "distance": float(np.atleast_1d(dist["distance"])[0]),
            "sigma_distance": float(np.atleast_1d(dist["sigma"])[0]),
        }
        if tau_f is not None:
            t = np.asarray(tau_f, dtype=float)[m]
            t = t[np.isfinite(t)]
            entry["tau_f"] = float(np.mean(t)) if t.size else float("nan")
            if line is not None and np.isfinite(entry["tau_f"]):
                entry["E_line"] = float(line.efficiency_at(entry["tau_f"]))
                entry["deviation"] = entry["E"] - entry["E_line"]
        out.append(entry)
    return out


#: Accepted spellings per factor (``CalibrationParameters.as_dict`` uses the
#: parameter names ``Bg_DD``/``R0``, callers often the lower-case attribute names).
_FACTOR_ALIASES = {
    "gamma": ("gamma",),
    "alpha": ("alpha",),
    "beta": ("beta",),
    "delta": ("delta",),
    "bg_dd": ("bg_dd", "Bg_DD"),
    "bg_da": ("bg_da", "Bg_DA"),
    "bg_aa": ("bg_aa", "Bg_AA"),
    "r0": ("r0", "R0"),
}


def _as_factor_dict(calibration) -> dict:
    """Normalize a calibration object/mapping into a plain factor dictionary.

    Parameters
    ----------
    calibration : CalibrationParameters, mapping or None
        The calibration to read. ``None`` yields the uncorrected defaults.

    Returns
    -------
    dict
        ``gamma``/``alpha``/``beta``/``delta``, the three backgrounds and ``r0``.
    """
    factors = {
        "gamma": 1.0,
        "alpha": 0.0,
        "beta": 1.0,
        "delta": 0.0,
        "bg_dd": 0.0,
        "bg_da": 0.0,
        "bg_aa": 0.0,
        "r0": 52.0,
    }
    if calibration is None:
        return factors
    source = calibration.as_dict() if hasattr(calibration, "as_dict") else dict(calibration)
    for key, names in _FACTOR_ALIASES.items():
        for name in names:
            if source.get(name) is not None:
                factors[key] = float(source[name])
                break
    return factors


# ---------------------------------------------------------------------------
# factor estimators that need more than the reference samples
# ---------------------------------------------------------------------------


def beta_from_stoichiometry(
    i_dd,
    i_da,
    i_aa,
    *,
    gamma: float,
    alpha: float = 0.0,
    delta: float = 0.0,
    bg_dd: float = 0.0,
    bg_da: float = 0.0,
    bg_aa: float = 0.0,
    target: float = 0.5,
) -> float:
    """Excitation-flux ratio ``beta`` from a single doubly-labelled population.

    ``beta`` only rescales the stoichiometry axis, so with one FRET population it
    cannot be fitted — but it can be *defined*: a 1:1 labelled molecule should
    come out at ``S = 0.5``. This is the conventional fallback when the
    ``1/S``-vs-``E`` fit is unavailable (a single-species sample); it assumes the
    population really is 1:1 labelled and does not affect ``E`` in any way.

    Parameters
    ----------
    i_dd, i_da, i_aa : array_like
        Per-burst counts of the doubly labelled population.
    gamma : float
        Detection factor (from the E-S fit or the lifetime).
    alpha, delta : float, optional
        Leakage and direct-excitation factors.
    bg_dd, bg_da, bg_aa : float, optional
        Channel backgrounds.
    target : float, optional
        Stoichiometry the population should be centred on (0.5 for 1:1).

    Returns
    -------
    float
        ``beta``; ``1.0`` when the population carries no acceptor signal.
    """
    f_dd = np.asarray(i_dd, dtype=float) - bg_dd
    f_aa = np.asarray(i_aa, dtype=float) - bg_aa
    f_da = np.asarray(i_da, dtype=float) - bg_da - alpha * f_dd - delta * f_aa
    num = float(np.mean(gamma * f_dd + f_da))
    den = float(np.mean(f_aa))
    t = float(np.clip(target, 1e-6, 1.0 - 1e-6))
    if num <= 0 or den <= 0:
        return 1.0
    return float(den / (num * (1.0 / t - 1.0)))


def gamma_from_lifetime(
    i_dd,
    i_da,
    tau_f,
    *,
    line: FretLine | None = None,
    i_aa=None,
    alpha: float = 0.0,
    delta: float = 0.0,
    bg_dd: float = 0.0,
    bg_da: float = 0.0,
    bg_aa: float = 0.0,
    labels=None,
    donor_lifetime: float | None = None,
    r0: float = 52.0,
    linker_sigma: float = 6.0,
    min_population: int = 20,
    efficiency_window: tuple[float, float] = (0.05, 0.95),
) -> dict:
    """Estimate the detection factor ``gamma`` from the donor lifetime and FRET line.

    A structurally static population must lie on the static FRET line, so its
    lifetime already fixes the efficiency:

        ``E_line = line(⟨tau_f⟩)``  and  ``E = F_DA / (F_DA + gamma·F_DD)``

    which solves for ``gamma = (F_DA/F_DD)·(1 − E_line)/E_line``. This identifies
    ``gamma`` from a **single** population, where the ``1/S``-vs-``E`` route needs
    two — and it works without acceptor-excitation (ALEX) data at all. Several
    populations give one estimate each; they are combined by burst count, and
    their spread is reported as the uncertainty.

    The estimate assumes the populations are static. Run it on a known-rigid
    sample, or compare its ``gamma`` against the E-S value: a mismatch is itself
    the evidence for sub-burst dynamics.

    Parameters
    ----------
    i_dd, i_da : array_like
        Per-burst donor and acceptor counts under donor excitation.
    tau_f : array_like
        Per-burst fluorescence-averaged donor lifetime in presence of the
        acceptor (ns).
    line : FretLine, optional
        The static FRET line. Built from ``donor_lifetime``, ``r0`` and
        ``linker_sigma`` when omitted.
    i_aa : array_like, optional
        Acceptor counts under acceptor excitation (for the ``delta`` correction).
    alpha, delta : float, optional
        Leakage and direct-excitation factors.
    bg_dd, bg_da, bg_aa : float, optional
        Channel backgrounds.
    labels : array_like, optional
        Population label per burst; one ``gamma`` is estimated per label.
    donor_lifetime : float, optional
        Donor-only lifetime (ns) used to build the line when ``line`` is None.
    r0 : float, optional
        Förster radius (Å) for the generated line.
    linker_sigma : float, optional
        Linker width (Å) for the generated line.
    min_population : int, optional
        Populations with fewer bursts are ignored.
    efficiency_window : tuple of float, optional
        Only populations whose line efficiency falls inside this window are
        used. Near the ends of the line the efficiency barely changes with the
        lifetime, so ``gamma = (F_DA/F_DD)(1−E)/E`` is numerically worthless
        there — and a donor-only population that slipped through the gating
        would otherwise dominate the estimate.

    Returns
    -------
    dict
        ``{"gamma", "sigma", "populations", "line"}``; ``gamma`` is ``NaN`` when
        no population qualified.
    """
    if line is None:
        if donor_lifetime is None:
            raise ValueError("gamma_from_lifetime needs either a line or a donor_lifetime")
        line = static_fret_line(float(donor_lifetime), r0=float(r0), sigma=float(linker_sigma))

    f_dd = np.asarray(i_dd, dtype=float) - bg_dd
    f_aa = None if i_aa is None else np.asarray(i_aa, dtype=float) - bg_aa
    f_da = np.asarray(i_da, dtype=float) - bg_da - alpha * f_dd
    if f_aa is not None and delta:
        f_da = f_da - delta * f_aa
    t = np.asarray(tau_f, dtype=float)
    if labels is None:
        labels = np.zeros(f_dd.shape, dtype=int)
    labels = np.asarray(labels)

    entries: list[dict] = []
    for u in np.unique(labels):
        m = (labels == u) & np.isfinite(t) & np.isfinite(f_dd) & np.isfinite(f_da)
        n = int(np.count_nonzero(m))
        if n < min_population:
            continue
        tau_mean = float(np.mean(t[m]))
        e_line = float(line.efficiency_at(tau_mean))
        dd = float(np.mean(f_dd[m]))
        da = float(np.mean(f_da[m]))
        e_lo, e_hi = float(efficiency_window[0]), float(efficiency_window[1])
        if not (e_lo <= e_line <= e_hi) or dd <= 0 or da <= 0:
            continue
        g = (da / dd) * (1.0 - e_line) / e_line
        entries.append({"label": u, "n": n, "tau_f": tau_mean, "E_line": e_line, "gamma": float(g)})

    if not entries:
        return {"gamma": float("nan"), "sigma": float("nan"), "populations": [], "line": line}
    weights = np.array([p["n"] for p in entries], dtype=float)
    values = np.array([p["gamma"] for p in entries], dtype=float)
    gamma = float(np.sum(weights * values) / np.sum(weights))
    if values.size > 1:
        var = float(np.sum(weights * (values - gamma) ** 2) / np.sum(weights))
        sigma = float(np.sqrt(var / values.size))
    else:
        sigma = float("nan")
    return {"gamma": gamma, "sigma": sigma, "populations": entries, "line": line}


# ---------------------------------------------------------------------------
# the automatic calibration
# ---------------------------------------------------------------------------


@dataclass
class AutoCalibration:
    """Result of :func:`auto_calibrate`.

    Attributes
    ----------
    calibration : CalibrationParameters
        The calibrated group (also updated in place when one was passed in).
    factors : dict
        ``alpha``/``beta``/``gamma``/``delta`` (and backgrounds) after calibration.
    uncertainties : dict
        Standard uncertainty per factor (bootstrap; ``NaN`` when not estimated).
    split : PopulationSplit
        The final automatic population assignment.
    gamma_estimates : dict
        Every ``gamma`` that was available: ``"es"`` (population fit),
        ``"lifetime"`` (static FRET line), ``"prior"`` (light path) and the
        ``"posterior"`` that was adopted.
    populations : list of dict
        Per-FRET-population summary (mean E/S/lifetime/distance).
    iterations : int
        Self-consistency iterations actually run.
    converged : bool
        Whether the factors stopped changing within the tolerance.
    messages : list of str
        What the procedure did and what it could not do.
    """

    calibration: CalibrationParameters
    factors: dict
    uncertainties: dict = field(default_factory=dict)
    split: PopulationSplit | None = None
    gamma_estimates: dict = field(default_factory=dict)
    populations: list = field(default_factory=list)
    iterations: int = 0
    converged: bool = False
    messages: list = field(default_factory=list)

    def report(self) -> str:
        """Human-readable summary of the calibration and how it was obtained."""
        lines = ["Automatic FRET calibration", "=========================="]
        for key in ("alpha", "delta", "gamma", "beta"):
            u = self.uncertainties.get(key, float("nan"))
            unc = "" if not np.isfinite(u) else f" ± {u:.4f}"
            lines.append(f"  {key:<6s} = {self.factors.get(key, float('nan')):.4f}{unc}")
        if self.split is not None:
            c = self.split.counts
            lines.append(
                f"  bursts: {c['donor_only']} donor-only, {c['acceptor_only']} "
                f"acceptor-only, {c['fret']} FRET in {c['fret_populations']} population(s)"
            )
            lines.append(
                f"  stoichiometry cuts ({self.split.method}): "
                f"{self.split.thresholds[0]:.3f} / {self.split.thresholds[1]:.3f}"
            )
        for key in ("prior", "es", "lifetime", "data", "posterior"):
            value = self.gamma_estimates.get(key)
            if value is not None and np.isfinite(value):
                label = {
                    "prior": "light path",
                    "es": "E-S population fit",
                    "lifetime": "static FRET line",
                    "data": "data (adopted)",
                    "posterior": "posterior",
                }[key]
                lines.append(f"  gamma [{label}] = {value:.4f}")
        for p in self.populations:
            tau = f", tau_f = {p['tau_f']:.3f} ns" if "tau_f" in p else ""
            dev = f", off-line by {p['deviation']:+.3f}" if "deviation" in p else ""
            lines.append(
                f"  population {p['label']}: n = {p['n']}, E = {p['E']:.3f} "
                f"± {p['sigma_E']:.3f}, R = {p['distance']:.1f} Å{tau}{dev}"
            )
        lines.extend(f"  ! {m}" for m in self.messages)
        lines.append(
            f"  {'converged' if self.converged else 'not converged'} "
            f"after {self.iterations} iteration(s)"
        )
        return "\n".join(lines)


def auto_calibrate(
    i_dd,
    i_da,
    i_aa=None,
    *,
    calibration=None,
    lightpath: dict | None = None,
    tau_f=None,
    line: FretLine | None = None,
    donor_lifetime: float | None = None,
    linker_sigma: float = 6.0,
    gamma_source: str = "auto",
    n_iterations: int = 6,
    tolerance: float = 1e-3,
    n_bootstrap: int = 0,
    seed: int = 0,
    use_priors: bool = True,
    assume_one_to_one: bool = True,
    min_population: int = 20,
    max_fret_populations: int = 3,
    donor_only_above: float = 0.75,
    acceptor_only_below: float = 0.25,
    progress=None,
) -> AutoCalibration:
    """Determine all FRET correction factors automatically from one measurement.

    The procedure, iterated until the factors stop moving (the classification
    depends on the factors and vice versa):

    1. correct ``E``/``S`` with the current factors and find the donor-only,
       acceptor-only and FRET bursts (:func:`classify_es_populations`);
    2. ``alpha`` from the donor-only bursts and ``delta`` from the acceptor-only
       bursts (the standard reference-sample estimators, but on populations
       found in the same file);
    3. ``gamma`` and ``beta`` from the ``1/S = Omega + Sigma·E`` fit over the
       FRET sub-populations when there are at least two of them;
    4. otherwise — or when asked — ``gamma`` from the donor lifetime and the
       static FRET line (:func:`gamma_from_lifetime`), with ``beta`` fixed by the
       1:1 labelling assumption;
    5. finally every optics-derived factor is combined with its light-path prior
       (:func:`_combine_with_optics_priors`), so the returned factors are
       posteriors: data where the data speaks, excitation/emission probabilities
       where it does not.

    Parameters
    ----------
    i_dd, i_da : array_like
        Per-burst donor and acceptor counts under donor excitation.
    i_aa : array_like, optional
        Per-burst acceptor counts under acceptor excitation. Without it the
        populations cannot be separated by stoichiometry and only the
        lifetime route is available.
    calibration : CalibrationParameters, optional
        Group to refine in place (its backgrounds and priors are used); a fresh
        one is created when omitted.
    lightpath : dict, optional
        Optics prior. Keyword arguments for
        :func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`
        — the ``matrices`` payload of the light-path calculator plus the dye,
        detector and laser labels (and optionally the prior widths). The computed
        excitation/emission probabilities seed the factors and become their
        priors. When omitted, any priors already attached to ``calibration`` are
        used instead.
    tau_f : array_like, optional
        Per-burst fluorescence-averaged donor lifetime (ns) enabling the
        lifetime-assisted route and the FRET-line diagnostics.
    line : FretLine, optional
        Static FRET line; built from ``donor_lifetime``/``r0``/``linker_sigma``
        when omitted.
    donor_lifetime : float, optional
        Donor-only lifetime (ns) for the generated line.
    linker_sigma : float, optional
        Linker width (Å) for the generated line.
    gamma_source : str, optional
        ``"auto"`` (E-S fit, lifetime as fallback), ``"es"``, ``"lifetime"`` or
        ``"combined"`` (precision-weighted mean of both).
    n_iterations : int, optional
        Maximum self-consistency iterations.
    tolerance : float, optional
        Convergence threshold on the largest factor change.
    n_bootstrap : int, optional
        Bootstrap resamples for the factor uncertainties (0 = skip).
    seed : int, optional
        Bootstrap RNG seed.
    use_priors : bool, optional
        Combine the data estimates with the light-path (optics) priors. With
        ``False`` the factors are pure data estimates.
    assume_one_to_one : bool, optional
        Allow the ``S = 0.5`` fallback for ``beta`` when the E-S fit is
        unavailable.
    min_population : int, optional
        Smallest population accepted for an estimate.
    max_fret_populations : int, optional
        Largest number of FRET sub-populations searched.
    donor_only_above, acceptor_only_below : float, optional
        Stoichiometry cut-offs used to *label* the fitted mixture components.

    Returns
    -------
    AutoCalibration
        Factors, uncertainties, population split and diagnostics; call
        :meth:`AutoCalibration.report` for a printable summary.

    Examples
    --------
    >>> import numpy as np
    >>> rng = np.random.default_rng(0)
    >>> n = 500
    >>> dd = rng.poisson(300, n).astype(float)      # doctest: +SKIP
    >>> res = auto_calibrate(dd, dd, dd)            # doctest: +SKIP
    >>> res.factors["gamma"] > 0                    # doctest: +SKIP
    True
    """
    calib = calibration if calibration is not None else CalibrationParameters()
    messages: list[str] = []
    if lightpath:
        from chisurf.core.fluorescence.fret.calibration import set_priors_from_lightpath

        optics = set_priors_from_lightpath(calib, **lightpath)
        messages.append(
            "light path: gamma {gamma:.4f}, alpha {alpha:.4f}, delta {delta:.4f} "
            "(prior means)".format(**optics)
        )
    dd = np.asarray(i_dd, dtype=float)
    da = np.asarray(i_da, dtype=float)
    aa = None if i_aa is None else np.asarray(i_aa, dtype=float)
    tau = None if tau_f is None else np.asarray(tau_f, dtype=float)

    if line is None and tau is not None:
        base = donor_lifetime if donor_lifetime is not None else float(np.nanmax(tau))
        line = static_fret_line(float(base), r0=float(calib.r0), sigma=float(linker_sigma))
        if donor_lifetime is None:
            messages.append(
                f"donor-only lifetime not given; the static line uses the longest "
                f"observed lifetime ({base:.2f} ns) as tau_D(0)"
            )

    split = None
    gamma_estimates: dict = {
        "es": float("nan"),
        "lifetime": float("nan"),
        "prior": float("nan"),
        "posterior": float("nan"),
    }
    previous = np.array([calib.alpha, calib.delta, calib.gamma, calib.beta])
    converged = False
    iteration = 0
    #: Notes of the *last* iteration only — earlier passes still work with the
    #: seed factors and their complaints are usually resolved by convergence.
    iteration_messages: list[str] = []

    #: Steps a caller can watch: one per refinement iteration, one per
    #: bootstrap resample. Counted rather than timed -- an iteration that
    #: converges early simply leaves the bar short, which is honest.
    _total_steps = int(n_iterations) + int(n_bootstrap)
    _step = 0

    def _tick(message: str) -> bool:
        """Report one step; False when the caller asked to stop."""
        nonlocal _step
        _step += 1
        if progress is None:
            return True
        return progress(_step, _total_steps, message) is not False

    cancelled = False
    for iteration in range(1, int(n_iterations) + 1):
        iteration_messages = []
        es = corrected_es(
            dd,
            da,
            aa,
            gamma=calib.gamma,
            alpha=calib.alpha,
            beta=calib.beta,
            delta=calib.delta,
            bg_dd=calib.bg_dd,
            bg_da=calib.bg_da,
            bg_aa=calib.bg_aa,
        )
        e_cur = np.asarray(es["E"], dtype=float)
        if aa is None:
            if iteration == 1:
                messages.append(
                    "no acceptor-excitation channel: every burst is taken to be "
                    "doubly labelled — singly labelled bursts left in the data bias "
                    "gamma, so gate them out first"
                )
            split = PopulationSplit(
                donor_only=np.zeros(dd.shape, dtype=bool),
                acceptor_only=np.zeros(dd.shape, dtype=bool),
                fret=np.ones(dd.shape, dtype=bool),
                fret_labels=split_fret_subpopulations(
                    e_cur,
                    max_populations=max_fret_populations,
                    min_population=min_population,
                ),
                thresholds=(0.0, 1.0),
                method="none",
            )
        else:
            split = classify_es_populations(
                es["S"],
                e_cur,
                donor_only_above=donor_only_above,
                acceptor_only_below=acceptor_only_below,
                max_fret_populations=max_fret_populations,
                min_population=min_population,
            )

        estimated = _estimate_alpha_delta(calib, dd, da, aa, split, iteration_messages)
        gamma_es, beta_es = _estimate_gamma_beta_es(calib, dd, da, aa, split)
        gamma_estimates["es"] = gamma_es
        if tau is not None and line is not None:
            lt = gamma_from_lifetime(
                dd,
                da,
                tau,
                line=line,
                i_aa=aa,
                alpha=calib.alpha,
                delta=calib.delta,
                bg_dd=calib.bg_dd,
                bg_da=calib.bg_da,
                bg_aa=calib.bg_aa,
                labels=np.where(split.fret, split.fret_labels, -1),
                min_population=min_population,
            )
            gamma_estimates["lifetime"] = lt["gamma"]
            gamma_estimates["lifetime_sigma"] = lt["sigma"]

        gamma = _select_gamma(gamma_source, gamma_estimates, iteration_messages)
        estimated["gamma"] = bool(np.isfinite(gamma) and gamma > 0)
        if estimated["gamma"]:
            calib.gamma = float(np.clip(gamma, 0.01, 100.0))
        if np.isfinite(beta_es) and beta_es > 0:
            calib.beta = float(beta_es)
        elif aa is not None and assume_one_to_one and np.any(split.fret):
            m = split.fret
            calib.beta = float(
                beta_from_stoichiometry(
                    dd[m],
                    da[m],
                    aa[m],
                    gamma=calib.gamma,
                    alpha=calib.alpha,
                    delta=calib.delta,
                    bg_dd=calib.bg_dd,
                    bg_da=calib.bg_da,
                    bg_aa=calib.bg_aa,
                )
            )
            iteration_messages.append(
                "only one FRET population: beta defined by centring it at S = 0.5 "
                "(1:1 labelling assumed)"
            )

        current = np.array([calib.alpha, calib.delta, calib.gamma, calib.beta])
        if not _tick(f"refining the correction factors (pass {iteration})"):
            cancelled = True
            messages.append(f"stopped by the caller after {iteration} iteration(s)")
            previous = current
            break
        if np.max(np.abs(current - previous)) < float(tolerance):
            converged = True
            previous = current
            break
        previous = current

    messages.extend(iteration_messages)
    gamma_estimates["data"] = float(calib.gamma)

    # The data uncertainty first (bootstrap), then the optics prior: the
    # posterior weight of each side is only meaningful once both widths exist.
    uncertainties = _bootstrap_uncertainties(
        calib,
        dd,
        da,
        aa,
        tau,
        line,
        split,
        n_bootstrap=0 if cancelled else n_bootstrap,
        seed=seed,
        min_population=min_population,
        tick=_tick,
    )
    if not np.isfinite(uncertainties.get("gamma", float("nan"))):
        uncertainties["gamma"] = float(gamma_estimates.get("lifetime_sigma", float("nan")))
    if use_priors:
        posterior = _combine_with_optics_priors(calib, uncertainties, estimated, messages)
        uncertainties.update({k: v for k, v in posterior["sigma"].items() if v is not None})
        gamma_estimates["prior"] = posterior["prior"].get("gamma", float("nan"))
    gamma_estimates["posterior"] = float(calib.gamma)

    final = accurate_fret(
        dd,
        da,
        aa,
        calibration=calib,
        tau_f=tau,
        line=line,
        uncertainties=uncertainties,
        labels=np.where(split.fret, split.fret_labels, -1) if split is not None else None,
    )
    populations = [p for p in final["populations"] if p["label"] != -1]

    return AutoCalibration(
        calibration=calib,
        factors=_as_factor_dict(calib),
        uncertainties=uncertainties,
        split=split,
        gamma_estimates=gamma_estimates,
        populations=populations,
        iterations=iteration,
        converged=converged,
        messages=messages,
    )


def _estimate_alpha_delta(calib, dd, da, aa, split, messages) -> dict:
    """Set ``alpha``/``delta`` from the automatically found reference populations.

    Returns
    -------
    dict
        Which of the two the data actually identified — the factors that were
        not identified are later filled in from the optics prior.
    """
    estimated = {"alpha": False, "delta": False}
    if np.any(split.donor_only):
        m = split.donor_only
        calib.alpha = float(
            leakage_from_donor_only(dd[m], da[m], bg_dd=calib.bg_dd, bg_da=calib.bg_da)
        )
        estimated["alpha"] = True
    else:
        messages.append("no donor-only population in the data")
    if aa is not None and np.any(split.acceptor_only):
        m = split.acceptor_only
        calib.delta = float(
            direct_excitation_from_acceptor_only(
                da[m],
                aa[m],
                dd[m],
                alpha=calib.alpha,
                bg_dd=calib.bg_dd,
                bg_da=calib.bg_da,
                bg_aa=calib.bg_aa,
            )
        )
        estimated["delta"] = True
    else:
        messages.append("no acceptor-only population in the data")
    return estimated


def _estimate_gamma_beta_es(calib, dd, da, aa, split) -> tuple[float, float]:
    """``gamma``/``beta`` from the ``1/S`` vs ``E`` fit; ``NaN`` when not identifiable."""
    if aa is None:
        return float("nan"), float("nan")
    m = split.fret & (split.fret_labels >= 0)
    if np.count_nonzero(m) < 2 or len(np.unique(split.fret_labels[m])) < 2:
        return float("nan"), float("nan")
    try:
        est = global_es_correction(
            dd[m], da[m], aa[m], split.fret_labels[m], alpha=calib.alpha, delta=calib.delta
        )
    except ValueError:
        return float("nan"), float("nan")
    gamma = est["gamma"] if np.isfinite(est["gamma"]) and est["gamma"] > 0 else float("nan")
    beta = est["beta"] if np.isfinite(est["beta"]) and est["beta"] > 0 else float("nan")
    return float(gamma), float(beta)


def _select_gamma(source: str, estimates: dict, messages) -> float:
    """Choose the ``gamma`` estimate according to ``gamma_source``."""
    es = estimates.get("es", float("nan"))
    lt = estimates.get("lifetime", float("nan"))
    if source == "es":
        return es
    if source == "lifetime":
        return lt
    if source == "combined":
        vals = [v for v in (es, lt) if np.isfinite(v)]
        return float(np.mean(vals)) if vals else float("nan")
    # auto: the population fit when identifiable, the lifetime line otherwise.
    if np.isfinite(es):
        return es
    if np.isfinite(lt):
        if messages is not None:
            messages.append(
                "fewer than two FRET populations: gamma taken from the donor "
                "lifetime and the static FRET line"
            )
        return lt
    if messages is not None:
        messages.append("gamma could not be determined from the data; prior value kept")
    return float("nan")


def _prior_of(parameter) -> tuple[float, float] | None:
    """Return ``(mu, sigma)`` of a fitting parameter's prior, or None."""
    from chisurf.core.fitting.priors import as_prior

    prior = as_prior(getattr(parameter, "prior", None))
    if prior is None or not hasattr(prior, "mu") or not hasattr(prior, "sigma"):
        return None
    return float(prior.mu), float(prior.sigma)


def _combine_with_optics_priors(calib, data_sigma: dict, estimated: dict, messages: list) -> dict:
    """Precision-weight every optics-derived factor with its light-path prior.

    ``gamma``, ``alpha`` and ``delta`` are predicted by the excitation/emission
    probabilities of the light path; that prediction is the prior mean and the
    optical-model uncertainty its width. The posterior is the usual Gaussian
    combination

        ``x_post = (x_data/sd² + mu_prior/sp²) / (1/sd² + 1/sp²)``,
        ``sigma_post = 1/sqrt(1/sd² + 1/sp²)``,

    which degrades gracefully in both directions: a factor the data did not
    identify falls back to the optics with the optical uncertainty, and a sharp
    data estimate overrides an uncertain optical model.

    Parameters
    ----------
    calib : CalibrationParameters
        Updated in place with the posterior values.
    data_sigma : dict
        Bootstrap uncertainty per factor (``NaN`` when not estimated).
    estimated : dict
        Whether each factor was actually estimated from the data.
    messages : list
        Diagnostics are appended here.

    Returns
    -------
    dict
        ``{"prior": {factor: mu}, "prior_sigma": {...}, "sigma": {factor:
        posterior sigma}}``.
    """
    out = {"prior": {}, "prior_sigma": {}, "sigma": {}}
    for name, parameter in (
        ("gamma", calib._gamma),
        ("alpha", calib._alpha),
        ("delta", calib._delta),
    ):
        prior = _prior_of(parameter)
        sigma_d = float(data_sigma.get(name, float("nan")))
        if prior is None:
            out["sigma"][name] = sigma_d
            if not estimated.get(name):
                messages.append(
                    f"{name} was neither identified by the data nor constrained by "
                    f"the light path; it keeps its current value"
                )
            continue
        mu, sigma_p = prior
        out["prior"][name] = mu
        out["prior_sigma"][name] = sigma_p
        if not estimated.get(name):
            setattr(calib, name, mu)
            out["sigma"][name] = sigma_p
            messages.append(
                f"{name} not identifiable from the data; the light-path value "
                f"{mu:.4f} ± {sigma_p:.4f} is used"
            )
            continue
        value = float(getattr(calib, name))
        if not np.isfinite(sigma_d) or sigma_d <= 0:
            sigma_d = max(abs(value) * 0.1, 1e-6)
        w_d, w_p = 1.0 / sigma_d**2, 1.0 / max(sigma_p, 1e-9) ** 2
        setattr(calib, name, float((value * w_d + mu * w_p) / (w_d + w_p)))
        out["sigma"][name] = float(np.sqrt(1.0 / (w_d + w_p)))
        messages.append(
            f"{name}: data {value:.4f} ± {sigma_d:.4f} combined with the light-path "
            f"prior {mu:.4f} ± {sigma_p:.4f} → {float(getattr(calib, name)):.4f}"
        )
    return out


def _bootstrap_uncertainties(
    calib,
    dd,
    da,
    aa,
    tau,
    line,
    split,
    *,
    n_bootstrap: int,
    seed: int,
    min_population: int,
    tick=None,
) -> dict:
    """Bootstrap the factor uncertainties with the population assignment fixed.

    Resampling *within* each class (rather than re-running the classification)
    is the statistically correct treatment once the split is accepted, and keeps
    the cost linear in the number of resamples.
    """
    out = {k: float("nan") for k in ("alpha", "delta", "gamma", "beta", "r0")}
    if not n_bootstrap or split is None:
        return out
    rng = np.random.default_rng(int(seed))
    collected = {"alpha": [], "delta": [], "gamma": [], "beta": []}
    idx_d = np.flatnonzero(split.donor_only)
    idx_a = np.flatnonzero(split.acceptor_only)
    idx_f = np.flatnonzero(split.fret)

    for _resample in range(int(n_bootstrap)):
        if tick is not None and not tick(
            f"bootstrapping the uncertainties ({_resample + 1}/{int(n_bootstrap)})"
        ):
            break
        if idx_d.size:
            s = rng.integers(0, idx_d.size, idx_d.size)
            collected["alpha"].append(
                leakage_from_donor_only(
                    dd[idx_d[s]], da[idx_d[s]], bg_dd=calib.bg_dd, bg_da=calib.bg_da
                )
            )
        if aa is not None and idx_a.size:
            s = rng.integers(0, idx_a.size, idx_a.size)
            collected["delta"].append(
                direct_excitation_from_acceptor_only(
                    da[idx_a[s]],
                    aa[idx_a[s]],
                    dd[idx_a[s]],
                    alpha=calib.alpha,
                    bg_dd=calib.bg_dd,
                    bg_da=calib.bg_da,
                    bg_aa=calib.bg_aa,
                )
            )
        if idx_f.size:
            s = rng.integers(0, idx_f.size, idx_f.size)
            j = idx_f[s]
            labels = split.fret_labels[j]
            if aa is not None and len(np.unique(labels)) >= 2:
                try:
                    est = global_es_correction(
                        dd[j], da[j], aa[j], labels, alpha=calib.alpha, delta=calib.delta
                    )
                    if np.isfinite(est["gamma"]):
                        collected["gamma"].append(est["gamma"])
                    if np.isfinite(est["beta"]):
                        collected["beta"].append(est["beta"])
                except ValueError:
                    pass
            elif tau is not None and line is not None:
                lt = gamma_from_lifetime(
                    dd[j],
                    da[j],
                    tau[j],
                    line=line,
                    i_aa=None if aa is None else aa[j],
                    alpha=calib.alpha,
                    delta=calib.delta,
                    bg_dd=calib.bg_dd,
                    bg_da=calib.bg_da,
                    bg_aa=calib.bg_aa,
                    labels=labels,
                    min_population=min_population,
                )
                if np.isfinite(lt["gamma"]):
                    collected["gamma"].append(lt["gamma"])

    for key, values in collected.items():
        if len(values) > 2:
            out[key] = float(np.std(np.asarray(values, dtype=float)))
    return out
