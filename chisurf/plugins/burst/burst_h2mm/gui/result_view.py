"""What the emtk H2MM windows draw, derived from a finished fit and from nothing else.

Every function takes the :class:`~chisurf.plugins.burst.burst_h2mm.core.analysis.H2mmAnalysis` that
:func:`~chisurf.plugins.burst.burst_h2mm.core.analysis.analyze` / ``run_analysis`` returned and gives back the
arrays the plots and tables show. With no analysis they return ``None`` (or an empty list): the windows then draw
an empty-state message, never a placeholder curve (PRD-153 rule 8a: no invented data).

The module is Qt-free and emtk-free so the parity tests can compare its output with the backend directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: Bins of a per-state dwell-time histogram (the Qt tool's ``_plot_dwell_times`` uses 30 as well).
DWELL_BINS = 30


@dataclass(frozen=True)
class DwellHistogram:
    """The histogram of one state's complete dwells, in milliseconds."""

    state: int
    centers_ms: np.ndarray
    counts: np.ndarray
    n_dwells: int


def n_states(ana: Any) -> int | None:
    """Number of states of the selected model (``None`` without a fit)."""
    if ana is None:
        return None
    return int(ana.best.n_states)


def rate_matrix(ana: Any) -> np.ndarray | None:
    """Transition rates in 1/s, row = from state, column = to state; ``None`` without a fit or a matrix."""
    if ana is None:
        return None
    rates = np.asarray(getattr(ana, "trans_rates", np.empty((0, 0))), dtype=np.float64)
    if rates.ndim != 2 or rates.shape[0] == 0:
        return None
    return rates


def transition_points(ana: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """FRET efficiency before and after every decoded within-burst transition (finite pairs only)."""
    if ana is None or not ana.transitions:
        return None
    before = np.array([t.e_from for t in ana.transitions], dtype=np.float64)
    after = np.array([t.e_to for t in ana.transitions], dtype=np.float64)
    good = np.isfinite(before) & np.isfinite(after)
    if not good.any():
        return None
    return before[good], after[good]


def transitions_in_gate(
    points: tuple[np.ndarray, np.ndarray] | None, x_range: tuple[float, float], y_range: tuple[float, float]
) -> tuple[int, int]:
    """How many of the *points* fall in the gate, and how many there are."""
    if points is None:
        return 0, 0
    x, y = points
    inside = (x >= x_range[0]) & (x <= x_range[1]) & (y >= y_range[0]) & (y <= y_range[1])
    return int(inside.sum()), int(x.size)


def dwell_histograms(ana: Any, bins: int = DWELL_BINS) -> tuple[list[DwellHistogram], list[int]]:
    """Per-state histograms of the dwells that ended inside their burst, and the states that have none.

    Dwells touching a burst edge are censored (the burst ended them, not the state) and are left out, exactly as in
    the Qt tool; a state with no complete dwell is returned in the second list so the window can name it.
    """
    if ana is None:
        return [], []
    base_ms = float(ana.base_time_s) * 1e3
    out: list[DwellHistogram] = []
    censored: list[int] = []
    for state, arr in sorted(ana.dwell_time_arrays().items()):
        if arr.size == 0:
            censored.append(int(state))
            continue
        counts, edges = np.histogram(arr * base_ms, bins=bins)
        out.append(DwellHistogram(int(state), (edges[:-1] + edges[1:]) / 2.0, counts.astype(np.float64), int(arr.size)))
    return out, censored


# --------------------------------------------------------------------------------------------------------------------
# Further plots (card H4): dwell FRET / E-S, model selection, per-state decays, burst state path, likelihood scan
# --------------------------------------------------------------------------------------------------------------------
#: Bins of the dwell-E histogram (the Qt tool uses 41 over [0, 1]).
DWELL_E_BINS = 41


@dataclass(frozen=True)
class DwellFret:
    """Measured per-dwell E histograms per state (weighted by dwell photons) and the model E per state."""

    has_alex: bool
    model_e: np.ndarray
    centers: np.ndarray
    counts: dict[int, np.ndarray]
    #: ``state -> (dwell E, dwell S)`` of the finite dwells (the E-S scatter of ALEX/PIE data).
    es_points: dict[int, tuple[np.ndarray, np.ndarray]]
    model_s: np.ndarray


def dwell_fret(ana: Any) -> DwellFret | None:
    """The dwell-E histograms (or E-S scatter data) of a fit; ``None`` without one."""
    if ana is None:
        return None
    fret = np.asarray(ana.fret, dtype=np.float64)
    stoich = np.asarray(getattr(ana, "stoichiometry", np.full_like(fret, np.nan)), dtype=np.float64)
    e = np.array([d.e for d in ana.dwells], dtype=np.float64)
    s = np.array([d.s for d in ana.dwells], dtype=np.float64)
    st = np.array([d.state for d in ana.dwells], dtype=np.int64)
    w = np.array([d.n_photons for d in ana.dwells], dtype=np.float64)
    counts: dict[int, np.ndarray] = {}
    es: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    centers = np.empty(0)
    for i in range(fret.shape[0]):
        m = (st == i) & np.isfinite(e)
        if m.any():
            c, edges = np.histogram(e[m], bins=DWELL_E_BINS, range=(0, 1), weights=w[m])
            counts[i] = c.astype(np.float64)
            centers = (edges[:-1] + edges[1:]) / 2.0
        ms = m & np.isfinite(s)
        if ms.any():
            es[i] = (e[ms], s[ms])
    return DwellFret(bool(np.isfinite(stoich).any()), fret, centers, counts, es, stoich)


def model_selection(ana: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """``(n_states, BIC, ICL)`` of every state count that was fitted."""
    if ana is None or not ana.scan:
        return None
    return (
        np.array([f.n_states for f in ana.scan], dtype=np.float64),
        np.array([f.bic for f in ana.scan], dtype=np.float64),
        np.array([f.icl for f in ana.scan], dtype=np.float64),
    )


@dataclass(frozen=True)
class BurstPath:
    """One burst's Viterbi path: time (ms), the E of the state each photon is in, the state and the stream per photon."""

    burst: int
    t_ms: np.ndarray
    e: np.ndarray
    state: np.ndarray
    stream: np.ndarray
    n_transitions: int


def dynamic_bursts(ana: Any) -> list[int]:
    """Bursts that contain at least one decoded transition (sorted)."""
    return sorted({int(t.burst) for t in ana.transitions}) if ana is not None else []


def burst_path(ana: Any, data: Any, burst: int) -> BurstPath | None:
    """The state path of *burst* (``None`` without a fit or for an unknown burst); the Qt tool's ``_update_burst_path``."""
    if ana is None or data is None or not (0 <= int(burst) < int(data.n_bursts)):
        return None
    offsets = np.asarray(data.burst_offsets)
    s, e = int(offsets[burst]), int(offsets[burst + 1])
    n = e - s
    gap = np.asarray(data.gap_slot)
    uniq = np.asarray(data.unique_dt)
    t = np.zeros(n, dtype=np.float64)
    if n > 1 and uniq.size:
        slots = gap[s : s + n - 1]
        dt = np.where(slots >= 0, uniq[np.clip(slots, 0, len(uniq) - 1)], 0)
        t[1:] = np.cumsum(dt)
    seg = np.asarray(ana.path[s:e], dtype=np.int64)
    fret = np.asarray(ana.fret, dtype=np.float64)
    return BurstPath(
        int(burst),
        t * (float(ana.base_time_s) * 1e3),
        np.where(np.isfinite(fret[seg]), fret[seg], np.nan),
        seg,
        np.asarray(data.streams)[s:e],
        int(np.count_nonzero(np.diff(seg))) if seg.size else 0,
    )


def state_decay_curves(ana: Any, bundle: Any):
    """Per-state decays by colour (``core.decays.state_decays``) or ``None`` when the photons carry no micro times."""
    meta = getattr(bundle, "meta", None)
    if ana is None or meta is None or getattr(meta, "micro_time", None) is None:
        return None
    from ..core.decays import colour_groups, state_decays

    path = np.asarray(ana.path, dtype=np.int64)
    micro = np.asarray(meta.micro_time)
    if micro.shape[0] != path.shape[0] or micro.size == 0 or int(micro.max()) <= 0:
        return None
    return state_decays(
        micro,
        meta.channel,
        bundle.data.streams,
        path,
        n_states=int(ana.fret.shape[0]),
        groups=colour_groups(ana, bundle.settings),
        micro_time_ns=getattr(bundle, "micro_time_ns", None),
    )


def scan_deviance(scan: Any) -> np.ndarray:
    """``2 (logL_max - logL)`` of a likelihood profile, the curve the scan window draws."""
    return 2.0 * (np.max(scan.loglik) - scan.loglik)
