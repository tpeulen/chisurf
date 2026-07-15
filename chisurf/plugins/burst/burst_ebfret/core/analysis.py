"""High-level ebFRET analysis: scan state counts, select a model, decode paths.

Wraps the empirical-Bayes fit
(:func:`~chisurf.plugins.burst.burst_ebfret.core.ebayes.ebayes`) with a scan
over candidate state counts, evidence-based model selection, and per-trace
Viterbi decoding into dwell segments and a transition-count matrix — the
practical outputs a user wants from binned-trace HMM analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .ebayes import EbayesResult, ebayes
from .viterbi import viterbi

__all__ = ["StateFit", "Dwell", "EbfretAnalysis", "analyse"]


@dataclass
class StateFit:
    """One recovered HMM state.

    Attributes
    ----------
    index : int
        State index (sorted ascending by mean).
    mean : float
        Emission mean (FRET efficiency).
    precision : float
        Emission precision ``E[lambda] = a / b``.
    std : float
        Emission standard deviation ``1 / sqrt(precision)``.
    occupancy : float
        Fraction of decoded frames assigned to this state.
    """

    index: int
    mean: float
    precision: float
    std: float
    occupancy: float


@dataclass
class Dwell:
    """A contiguous residence in a single state within one trace.

    Attributes
    ----------
    trace : int
        Index of the trace this dwell belongs to.
    state : int
        Decoded state index.
    start : int
        First frame of the dwell.
    length : int
        Number of frames.
    """

    trace: int
    state: int
    start: int
    length: int


@dataclass
class EbfretAnalysis:
    """Result of a full ebFRET analysis at the selected state count.

    Attributes
    ----------
    n_states : int
        Selected number of states.
    states : list of StateFit
        Per-state emission summary, sorted by mean.
    transition_counts : numpy.ndarray
        Viterbi transition-count matrix, shape ``(K, K)``.
    dwells : list of Dwell
        Decoded dwell segments across all traces.
    evidence : float
        Summed lower bound of the selected model.
    scan : dict
        Mapping ``{K: evidence}`` over the scanned state counts.
    fit : EbayesResult
        The underlying empirical-Bayes fit for the selected ``K``.
    """

    n_states: int
    states: list[StateFit]
    transition_counts: np.ndarray
    dwells: list[Dwell] = field(default_factory=list)
    evidence: float = float("nan")
    scan: dict[int, float] = field(default_factory=dict)
    fit: EbayesResult | None = None

    @property
    def state_means(self) -> np.ndarray:
        """State emission means, sorted ascending."""
        return np.array([s.mean for s in self.states])


def _decode(fit: EbayesResult, traces: list[np.ndarray]) -> tuple[list[np.ndarray], np.ndarray]:
    """Viterbi-decode every trace and accumulate a transition-count matrix."""
    order = np.argsort(fit.prior.m)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.shape[0])  # original -> sorted index
    paths: list[np.ndarray] = []
    n_states = fit.prior.n_states
    trans = np.zeros((n_states, n_states), dtype=int)
    for result, trace in zip(fit.traces, traces):
        states, _ = viterbi(trace, result.posterior)
        states = rank[states]  # relabel to ascending-mean order
        paths.append(states)
        for prev, nxt in zip(states[:-1], states[1:]):
            if prev != nxt:
                trans[prev, nxt] += 1
    return paths, trans


def _dwells(paths: list[np.ndarray]) -> list[Dwell]:
    """Segment decoded paths into contiguous dwell records."""
    out: list[Dwell] = []
    for t, states in enumerate(paths):
        if states.size == 0:
            continue
        start = 0
        for i in range(1, states.size):
            if states[i] != states[start]:
                out.append(Dwell(t, int(states[start]), start, i - start))
                start = i
        out.append(Dwell(t, int(states[start]), start, states.size - start))
    return out


def analyse(
    traces: list[np.ndarray],
    *,
    min_states: int = 2,
    max_states: int = 4,
    max_iter: int = 20,
    threshold: float = 1e-4,
    vbem_max_iter: int = 100,
    vbem_threshold: float = 1e-5,
    seed: int = 0,
) -> EbfretAnalysis:
    """Scan state counts, pick the highest-evidence model, and decode it.

    Parameters
    ----------
    traces : list of numpy.ndarray
        FRET-efficiency traces.
    min_states, max_states : int, optional
        Inclusive range of state counts to scan.
    max_iter, threshold : int, float, optional
        Empirical-Bayes loop controls.
    vbem_max_iter, vbem_threshold : int, float, optional
        Per-trace VBEM controls.
    seed : int, optional
        Prior-initialisation seed.

    Returns
    -------
    EbfretAnalysis
        Selected model with per-state summary, transition counts and dwells.

    Notes
    -----
    Model selection uses the summed variational lower bound (evidence), which
    already penalises complexity; the highest-evidence ``K`` in the scan wins.
    """
    traces = [np.asarray(t, dtype=float).ravel() for t in traces]
    scan: dict[int, float] = {}
    fits: dict[int, EbayesResult] = {}
    for k in range(min_states, max_states + 1):
        fit = ebayes(
            traces,
            k,
            max_iter=max_iter,
            threshold=threshold,
            vbem_max_iter=vbem_max_iter,
            vbem_threshold=vbem_threshold,
            seed=seed,
        )
        scan[k] = fit.evidence
        fits[k] = fit

    best_k = max(scan, key=scan.get)
    fit = fits[best_k]
    paths, trans = _decode(fit, traces)
    dwells = _dwells(paths)

    order = np.argsort(fit.prior.m)
    total = sum(p.size for p in paths) or 1
    occupancy = np.zeros(best_k)
    for p in paths:
        for s in range(best_k):
            occupancy[s] += int(np.count_nonzero(p == s))
    occupancy /= total

    precision = (fit.prior.a / fit.prior.b)[order]
    means = fit.prior.m[order]
    states = [
        StateFit(
            index=i,
            mean=float(means[i]),
            precision=float(precision[i]),
            std=float(1.0 / np.sqrt(precision[i])),
            occupancy=float(occupancy[i]),
        )
        for i in range(best_k)
    ]
    return EbfretAnalysis(
        n_states=best_k,
        states=states,
        transition_counts=trans,
        dwells=dwells,
        evidence=fit.evidence,
        scan=scan,
        fit=fit,
    )
