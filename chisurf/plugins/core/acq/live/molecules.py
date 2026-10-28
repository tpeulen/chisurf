"""Single-molecule trace analysis of a point measurement: states, bleaching steps, E, lifetime.

A point measurement parks the focus on one picked molecule and records until it has bleached
(``live.points``). Its recording is analysed with ChiSurf's shared tools, never a private fit:

* the trace is binned and segmented into states by the intensity-trace tool's model
  (:class:`chisurf.plugins.tttr.intensity_trace.model.IntensityTraceModel`: per-detector binning,
  the shared Gaussian HMM of :mod:`chisurf.plugins.core.hmm` with its dimmest-first state order, the
  BIC over state counts, dwell times);
* from the decoded path follow the **bleaching steps** (each visit to a level dimmer than every
  level before it), the **bleach time** (when the path reaches the dimmest level and stays), the
  **on-time**, the **mean intensity per state**, the **FRET efficiency** of the first level
  (before any bleaching: acceptor over the sum, background -- the final level -- subtracted) and a
  **fast lifetime** (the on-photons' mean arrival time after the decay's peak).

:func:`analyse_point` returns a :class:`MoleculeResult`; :func:`molecule_rows` turns results into
the per-molecule table the Record tool shows and stores in the image's container.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_log = logging.getLogger(__name__)

__all__ = ["MoleculeResult", "analyse_point", "bleaching_steps", "molecule_rows"]

#: Bin width of the analysed trace (s) and the largest state count the BIC tries.
WINDOW_MS = 20.0
MAX_STATES = 4
#: a level the path holds for fewer bins is a step's transition bin, not a state
MIN_STATE_BINS = 3


@dataclass
class MoleculeResult:
    """One analysed molecule.

    Attributes
    ----------
    index : int
        The point's index.
    point : (float, float)
        Its stage position (µm).
    photons : int
        Photons recorded at the point.
    n_states : int
        States the BIC chose.
    steps : int
        Bleaching steps (0: nothing bleached during the point).
    bleach_s : float or None
        When the path reached the final (dimmest) level; ``None`` if it never did.
    on_s : float
        Time before the bleach (the whole point when it did not bleach).
    state_khz : list of float
        Mean count rate per state, dimmest first (all detectors).
    efficiency : float or None
        FRET efficiency (proximity ratio, background-corrected) of the first level.
    stoichiometry : float or None
        ``None``: a point measurement without alternating excitation has none.
    lifetime_ns : float or None
        Mean arrival time of the on-photons after the decay's peak (a fast lifetime).
    time_s, counts, path_khz, labels
        The binned trace (per detector), the decoded path as the state's rate per bin, the
        detector labels -- what the Trace dock draws.
    message : str
        What went wrong, when it did.
    """

    index: int
    point: tuple
    photons: int = 0
    n_states: int = 0
    steps: int = 0
    bleach_s: float | None = None
    on_s: float = 0.0
    state_khz: list = field(default_factory=list)
    efficiency: float | None = None
    stoichiometry: float | None = None
    lifetime_ns: float | None = None
    time_s: np.ndarray = field(default_factory=lambda: np.zeros(0))
    counts: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    path_khz: np.ndarray = field(default_factory=lambda: np.zeros(0))
    labels: list = field(default_factory=list)
    message: str = ""


def bleaching_steps(states: np.ndarray, levels: np.ndarray) -> tuple[int, int | None]:
    """Bleaching steps of a decoded path, and the bin the final level starts at.

    A step is a visit to a level dimmer than every level the path had been at; the bleach is the
    start of the last run when that run is the dimmest level (a path ending brighter has not
    bleached). Blinking -- dim and back -- counts once, at its first dimming.

    Parameters
    ----------
    states : array of int
        The decoded path, states ordered dimmest first (the shared HMM's order).
    levels : array of float
        The rate of each state (the order's key).
    """
    from chisurf.plugins.core.hmm.core import state_segments

    segments = state_segments(states)
    if len(segments) < 2:
        return 0, None
    steps, lowest = 0, levels[segments[0][0]]
    for state, _start, _stop in segments[1:]:
        if levels[state] < lowest:
            steps += 1
            lowest = levels[state]
    last_state, last_start, _ = segments[-1]
    dimmest = int(np.argmin(levels))
    return steps, (last_start if last_state == dimmest and steps else None)


def analyse_point(ptu: str | Path, index: int, point, *, window_ms: float = WINDOW_MS,
                  max_states: int = MAX_STATES) -> MoleculeResult:
    """Analyse one point's recording (see the module notes)."""
    from chisurf.plugins.tttr.intensity_trace.model import IntensityTraceModel

    out = MoleculeResult(index=int(index), point=(float(point[0]), float(point[1])))
    trace = IntensityTraceModel(window_ms=float(window_ms))
    if not trace.load(str(ptu)):
        out.message = trace.message
        return out
    counts = np.asarray(trace.counts, float)
    window_s = float(window_ms) / 1e3
    out.time_s, out.counts, out.labels = np.asarray(trace.time_axis), counts, list(trace.labels)
    out.photons = int(counts.sum())
    if counts.shape[0] < 4:
        out.message = "too short to analyse"
        return out
    # the state count the BIC prefers (at most one state per two bins)
    curve = [(n, b) for n, b in trace.bic_curve(max_states=min(max_states, counts.shape[0] // 2))
             if np.isfinite(b)]
    trace.n_states = int(min(curve, key=lambda nb: nb[1])[0]) if curve else 1
    while True:
        trace.run_hmm()
        states = np.asarray(trace.states, int)
        # a state of a bin or two is the bin a step falls into (half bright), not a level: the
        # Gaussian HMM fits it a vanishing width that the BIC rewards -- take one state fewer
        held = np.bincount(states, minlength=trace.n_states)
        if trace.n_states <= 1 or held.min() >= MIN_STATE_BINS:
            break
        trace.n_states -= 1
    total = counts.sum(axis=1)
    levels = np.asarray([total[states == s].mean() if np.any(states == s) else 0.0
                         for s in range(trace.n_states)])
    out.n_states = int(trace.n_states)
    out.state_khz = [float(v / window_s / 1e3) for v in levels]
    out.path_khz = levels[states] / window_s / 1e3
    out.steps, start = bleaching_steps(states, levels)
    if start is not None:
        out.bleach_s = float(start * window_s)
    out.on_s = out.bleach_s if out.bleach_s is not None else float(len(states) * window_s)
    first = states == states[0]
    first &= np.arange(len(states)) < (start if start is not None else len(states))
    if counts.shape[1] >= 2 and np.any(first):
        background = (counts[states == states[-1]].mean(axis=0)
                      if start is not None else np.zeros(counts.shape[1]))
        donor, acceptor = (counts[first].mean(axis=0) - background)[:2]
        if donor + acceptor > 0:
            out.efficiency = float(np.clip(acceptor / (donor + acceptor), -0.2, 1.2))
    out.lifetime_ns = _fast_lifetime(ptu, out.on_s)
    return out


def _fast_lifetime(ptu, on_s: float) -> float | None:
    """Mean arrival time of the photons before *on_s* after the decay's peak (ns)."""
    try:
        from chisurf.core.fio.staging import open_tttr

        tttr = open_tttr(str(ptu), cache=False)
        macro = np.asarray(tttr.macro_times, np.int64)
        micro = np.asarray(tttr.micro_times, np.int64)
        res = float(tttr.header.micro_time_resolution)
        clock = float(tttr.header.macro_time_resolution)
    except Exception:  # noqa: BLE001 - no lifetime rather than no molecule
        _log.exception("lifetime of %s", ptu)
        return None
    if macro.size == 0 or res <= 0:
        return None
    on = micro[(macro - macro[0]) * clock < on_s]
    if on.size < 50:
        return None
    hist = np.bincount(on)
    peak = int(np.argmax(hist))
    after = on[on >= peak]
    return float((after.mean() - peak) * res * 1e9) if after.size else None


#: The per-molecule table's columns: key, title, format.
COLUMNS = (
    ("index", "#", "%d"),
    ("x_um", "x (µm)", "%.2f"),
    ("y_um", "y (µm)", "%.2f"),
    ("photons", "Photons", "%d"),
    ("bleach_s", "Bleach (s)", "%.2f"),
    ("steps", "Steps", "%d"),
    ("efficiency", "E", "%.2f"),
    ("stoichiometry", "S", "%.2f"),
    ("lifetime_ns", "τ (ns)", "%.2f"),
)


def molecule_rows(results: list[MoleculeResult]) -> dict[str, np.ndarray]:
    """The per-molecule table (one row per analysed point; NaN where a value does not apply)."""

    def num(v):
        return float("nan") if v is None else float(v)

    return {
        "index": np.asarray([r.index for r in results], np.int64),
        "x_um": np.asarray([r.point[0] for r in results], float),
        "y_um": np.asarray([r.point[1] for r in results], float),
        "photons": np.asarray([r.photons for r in results], np.int64),
        "n_states": np.asarray([r.n_states for r in results], np.int64),
        "steps": np.asarray([r.steps for r in results], np.int64),
        "bleach_s": np.asarray([num(r.bleach_s) for r in results], float),
        "on_s": np.asarray([r.on_s for r in results], float),
        "efficiency": np.asarray([num(r.efficiency) for r in results], float),
        "stoichiometry": np.asarray([num(r.stoichiometry) for r in results], float),
        "lifetime_ns": np.asarray([num(r.lifetime_ns) for r in results], float),
        "brightest_khz": np.asarray([max(r.state_khz) if r.state_khz else float("nan")
                                     for r in results], float),
    }


def summary(result: MoleculeResult) -> dict[str, Any]:
    """A short readable summary of one molecule (the table row's tooltip)."""
    rates = ", ".join(f"{v:.1f}" for v in result.state_khz)
    return {
        "states": f"{result.n_states} states ({rates} kHz)",
        "on": f"on {result.on_s:.2f} s",
    }
