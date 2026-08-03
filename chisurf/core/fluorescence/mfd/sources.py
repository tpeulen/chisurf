"""Scoring sources: the ways a model is compared with the same bursts.

One model core, several ways of asking it to account for the data. They are
selectable and combinable, and their *agreement* is itself a test — a rate that the
fast path and the photon-by-photon reference disagree on is a rate nobody should
report.

* :func:`histogram_residuals` — the marginalized 2D histograms. Cost independent of
  the number of bursts. The fast path, and the default.
* :func:`pooled_decay_residuals` — real decays pooled per histogram bin, which
  recovers the shape the mean micro time discards.
* :func:`burstwise_log_likelihood` — every burst's counts and individual micro
  times. The information bound the other two are measured against.

**The summed deviance over marginals is an M-estimator, not a likelihood.** The
same bursts appear in every marginal and in every source, so the score
double-counts the data; its curvature reports uncertainties that are too small,
sometimes by a large factor. The optimum is still the optimum — but the errors are
not errors. :func:`uncertainty_is_valid` is what enforces that in code, and the
model layer calls it rather than relying on anyone having read this paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from chisurf.core.fitting import deviance_residuals

__all__ = [
    "SOURCES",
    "ScoreResult",
    "burstwise_log_likelihood",
    "histogram_residuals",
    "pooled_decay_residuals",
    "uncertainty_is_valid",
]

#: The scoring sources, by the name a view spec or a CLI uses.
SOURCES = ("histogram", "pooled_decay", "burstwise")

#: Sources whose curvature is a valid basis for a parameter uncertainty. The
#: histogram source is excluded on purpose: it double-counts bursts across
#: marginals, so its curvature is not the curvature of a likelihood.
_LIKELIHOOD_SOURCES = frozenset({"burstwise"})


@dataclass
class ScoreResult:
    """What a scoring source returns.

    Attributes
    ----------
    residuals : numpy.ndarray
        Signed residuals whose sum of squares is the score, so an ordinary
        least-squares optimizer minimises the right thing.
    n_points : int
        Independent points behind the score, for a reduced chi-square.
    summary : dict
        What was masked, excluded or approximated.
    """

    residuals: np.ndarray
    n_points: int
    summary: dict[str, Any]

    @property
    def score(self) -> float:
        """Return the sum of squared residuals."""
        return float(np.sum(self.residuals**2))


def histogram_residuals(
    observed: np.ndarray,
    model: np.ndarray,
    *,
    floor: float = 1e-9,
    mask_empty_model: bool = True,
) -> ScoreResult:
    """Score a model histogram against the observed one with the Poisson deviance.

    Never ``χ²`` on bins holding single-digit counts, which is most of a 2D burst
    histogram: the shared ``2I*`` deviance residuals
    (:func:`chisurf.core.fitting.deviance_residuals`) are used, so their sum of
    squares *is* the Poisson maximum-likelihood objective and a plain
    Levenberg–Marquardt minimises it unchanged.

    Bins where the model predicts nothing but the data hold counts are the honest
    problem here. They are masked, and **the masked fraction is reported** — a
    model that explains 60% of the bursts and masks the rest would otherwise score
    beautifully.

    Parameters
    ----------
    observed, model : numpy.ndarray
        Same shape. The model is rescaled to the observed total, because the
        histogram source constrains the *shape*; the burst count is nuisance.
    floor : float
        Model values below this count as zero.
    mask_empty_model : bool
        Mask data-bearing bins the model puts no weight in. With this off they
        dominate the score and the fit chases them.

    Returns
    -------
    ScoreResult
    """
    data = np.asarray(observed, dtype=float).ravel()
    prediction = np.asarray(model, dtype=float).ravel()
    if data.shape != prediction.shape:
        raise ValueError("the observed and model histograms must have the same shape")

    total_model = prediction.sum()
    total_data = data.sum()
    if total_model > 0:
        prediction = prediction * (total_data / total_model)

    empty = prediction <= floor
    conflict = empty & (data > 0)
    if mask_empty_model:
        keep = ~empty
    else:
        keep = np.ones_like(empty)
        prediction = np.maximum(prediction, floor)

    residuals = deviance_residuals(data[keep], prediction[keep])
    n_conflict = int(conflict.sum())
    summary = {
        "n_bins": int(data.size),
        "n_scored": int(keep.sum()),
        "n_masked_empty_model": int(empty.sum()) if mask_empty_model else 0,
        "n_masked_with_counts": n_conflict if mask_empty_model else 0,
        "masked_counts_fraction": (
            float(data[conflict].sum() / total_data) if total_data > 0 else 0.0
        ),
    }
    return ScoreResult(residuals=residuals, n_points=int(keep.sum()), summary=summary)


def pooled_decay_residuals(
    observed: np.ndarray,
    model: np.ndarray,
    *,
    floor: float = 1e-9,
) -> ScoreResult:
    """Score pooled per-bin decays, ``(bin × micro-time channel)``.

    A bin holding a within-burst mixture and a bin holding a single intermediate
    lifetime have the *same* mean micro time and different decays, so this is where
    the shape the mean discards comes back. Cost scales with bins × channels rather
    than with bursts × photons.

    **Pooling on a coordinate conditions on it.** If the lifetime axis is one of the
    pooling coordinates then the model must reproduce the same conditioning, or
    every pooled decay tilts in a way that reads as a lifetime shift. The model side
    of this is built by :mod:`~chisurf.core.fluorescence.mfd.fit`, which pools its
    prediction through the identical map.

    Parameters
    ----------
    observed, model : numpy.ndarray
        ``(n_bins, n_channels)`` decays.
    floor : float
        Model values below this are masked.

    Returns
    -------
    ScoreResult
    """
    data = np.asarray(observed, dtype=float)
    prediction = np.asarray(model, dtype=float)
    if data.shape != prediction.shape:
        raise ValueError("the observed and model decays must have the same shape")

    residuals = []
    n_masked = 0
    for row in range(data.shape[0]):
        d = data[row]
        m = prediction[row]
        total_m, total_d = m.sum(), d.sum()
        if total_m <= 0 or total_d <= 0:
            n_masked += 1
            continue
        # Each pooled decay is scored on its shape: the number of bursts in a bin is
        # already the histogram source's business, and counting it twice is exactly
        # the double-counting this module warns about.
        m = m * (total_d / total_m)
        keep = m > floor
        residuals.append(deviance_residuals(d[keep], m[keep]))

    stacked = np.concatenate(residuals) if residuals else np.zeros(0)
    return ScoreResult(
        residuals=stacked,
        n_points=int(stacked.size),
        summary={"n_bins": int(data.shape[0]), "n_masked_bins": n_masked},
    )


def burstwise_log_likelihood(
    log_probabilities: np.ndarray,
) -> ScoreResult:
    """Turn per-burst log-probabilities into residuals an optimizer can minimise.

    The maximum-likelihood reference: no binning, no compression, the full decay
    shape of every burst. This is the information bound the other two sources are
    measured against, and the only source whose curvature is a legitimate
    uncertainty.

    Residuals are ``√(2 (ℓ_max − ℓ_b))`` per burst, so their sum of squares is
    ``2 (ℓ_max − ℓ)`` — the same convention as the deviance, so the two can be
    combined without one silently outweighing the other.

    Parameters
    ----------
    log_probabilities : numpy.ndarray
        ``(n_bursts,)`` log-probability of each burst under the model.

    Returns
    -------
    ScoreResult
    """
    values = np.asarray(log_probabilities, dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("no burst has a finite log-probability under this model")
    reference = float(values[finite].max())
    residuals = np.sqrt(np.maximum(2.0 * (reference - values[finite]), 0.0))
    return ScoreResult(
        residuals=residuals,
        n_points=int(finite.sum()),
        summary={
            "n_bursts": int(values.size),
            "n_non_finite": int((~finite).sum()),
            "log_likelihood": float(values[finite].sum()),
        },
    )


def uncertainty_is_valid(sources) -> bool:
    """Return whether a parameter uncertainty may be read off this score's curvature.

    ``False`` for any combination that includes the histogram or pooled-decay
    sources. Those score the same bursts through several marginals, so the summed
    deviance is an M-estimator: its optimum is meaningful and its curvature is not.
    Uncertainties then have to come from the burst-wise source or from a bootstrap
    over bursts.

    This exists as a function rather than as a sentence in a docstring because the
    footnote version of this rule is routinely not read, and the failure it prevents
    — confidently narrow error bars — looks exactly like success.

    Parameters
    ----------
    sources : iterable of str
        The scoring sources in use.

    Returns
    -------
    bool
    """
    names = {str(s) for s in sources}
    unknown = names - set(SOURCES)
    if unknown:
        raise ValueError(f"unknown scoring source(s): {sorted(unknown)}")
    return bool(names) and names <= _LIKELIHOOD_SOURCES
