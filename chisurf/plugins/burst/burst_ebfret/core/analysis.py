"""High-level ebFRET analysis: scan state counts, select a model, decode paths.

A headless convenience over the faithful port of ebFRET's analysis loop: for
each number of states it guesses the prior as the main window does
(:func:`~chisurf.plugins.burst.burst_ebfret.core.hmm.guess_prior`), runs the
empirical-Bayes iterations
(:func:`~chisurf.plugins.burst.burst_ebfret.core.ebayes.run_ebayes`), and then
selects the number of states with the highest summed lower bound. The Viterbi
paths the loop already computed are turned into dwell segments and a
transition-count matrix -- outputs ebFRET's GUI leaves to its exports, and
that ChiSurf records in the measurement's container.

State indices in these results are **0-based and ordered by ascending mean**,
unlike the 1-based, unordered state numbers of the ebFRET port itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .ebayes import run_ebayes
from .hmm import guess_prior
from .model import Analysis

__all__ = ["StateFit", "Dwell", "EbfretAnalysis", "analyse", "write_container"]


@dataclass
class StateFit:
    """One recovered HMM state.

    Attributes
    ----------
    index : int
        State index (sorted ascending by mean).
    mean : float
        Emission mean of the prior (FRET efficiency).
    precision : float
        Expected emission precision under the prior, ``nu W``.
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
        Decoded state index (0-based, ascending mean).
    start : int
        First frame of the dwell (0-based).
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
    fit : Analysis
        The ebFRET analysis (prior, posteriors, statistics, Viterbi paths) for
        the selected ``K``.
    evidence_history : list of float
        Summed lower bound per empirical-Bayes iteration of the selected ``K``.
    """

    n_states: int
    states: list[StateFit]
    transition_counts: np.ndarray
    dwells: list[Dwell] = field(default_factory=list)
    evidence: float = float("nan")
    scan: dict[int, float] = field(default_factory=dict)
    fit: Analysis | None = None
    evidence_history: list[float] = field(default_factory=list)

    @property
    def state_means(self) -> np.ndarray:
        """State emission means, sorted ascending."""
        return np.array([s.mean for s in self.states])


def _dwells(paths: list[np.ndarray]) -> list[Dwell]:
    """Segment decoded paths into contiguous dwell records.

    Parameters
    ----------
    paths : list of numpy.ndarray
        0-based state per frame, one array per trace.

    Returns
    -------
    list of Dwell
    """
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
    restarts: int = 2,
    seed: int = 0,
) -> EbfretAnalysis:
    """Scan state counts, pick the highest-evidence model, and decode it.

    Parameters
    ----------
    traces : list of numpy.ndarray
        FRET-efficiency traces.
    min_states, max_states : int, optional
        Inclusive range of state counts to scan.
    max_iter : int, optional
        Empirical-Bayes iteration limit (the loop stops once ``it > max_iter``).
    threshold : float, optional
        ebFRET's *Precision*: relative convergence threshold of the summed
        lower bound, and the margin a restart must win by.
    vbem_max_iter, vbem_threshold : int, float, optional
        Per-trace VBEM controls (ebFRET uses 100 and 1e-5).
    restarts : int, optional
        ebFRET's *Restarts*: one uninformative guess plus ``restarts - 1``
        guesses drawn from the prior, per trace.
    seed : int, optional
        Seed of the random restarts, so a run is reproducible.

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
    fits: dict[int, Analysis] = {}
    histories: dict[int, list[float]] = {}
    for k in range(min_states, max_states + 1):
        fit = Analysis(states=k, prior=guess_prior(traces, k))
        gen = run_ebayes(
            fit,
            traces,
            restarts=restarts,
            precision=threshold,
            max_iter=max_iter,
            rng=np.random.default_rng(seed + k),
            vb_threshold=vbem_threshold,
            vb_max_iter=vbem_max_iter,
        )
        history: list[float] = []
        while True:
            try:
                next(gen)
            except StopIteration as stop:
                history = list(stop.value or [])
                break
        scan[k] = history[-1] if history else float("nan")
        fits[k] = fit
        histories[k] = history

    best_k = max(scan, key=lambda k: -np.inf if np.isnan(scan[k]) else scan[k])
    fit = fits[best_k]
    mu = np.asarray(fit.prior.mu, dtype=float)
    order = np.argsort(mu)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)

    paths: list[np.ndarray] = []
    trans = np.zeros((best_k, best_k), dtype=int)
    for vit in fit.viterbi:
        if vit is None:
            paths.append(np.zeros(0, dtype=int))
            continue
        states = rank[np.asarray(vit.state, dtype=int) - 1]
        paths.append(states)
        for prev, nxt in zip(states[:-1], states[1:]):
            if prev != nxt:
                trans[prev, nxt] += 1
    dwells = _dwells(paths)

    total = sum(p.size for p in paths) or 1
    occupancy = (
        np.array(
            [sum(int(np.count_nonzero(p == s)) for p in paths) for s in range(best_k)], dtype=float
        )
        / total
    )
    precision = np.asarray(fit.prior.nu, dtype=float) * np.asarray(fit.prior.W, dtype=float)
    states = [
        StateFit(
            index=i,
            mean=float(mu[order[i]]),
            precision=float(precision[order[i]]),
            std=float(1.0 / np.sqrt(precision[order[i]])),
            occupancy=float(occupancy[i]),
        )
        for i in range(best_k)
    ]
    return EbfretAnalysis(
        n_states=best_k,
        states=states,
        transition_counts=trans,
        dwells=dwells,
        evidence=scan[best_k],
        scan=scan,
        fit=fit,
        evidence_history=histories[best_k],
    )


def write_container(
    source,
    analysis: EbfretAnalysis,
    *,
    parameters: dict | None = None,
    out_dir=None,
) -> str:
    """Write an ebFRET analysis into the measurement's container.

    Three grains, and the dwell table is the one that matters: it is *finer*
    than a trace and carries the trace it belongs to as a key, which is the
    shape no companion format could hold. The same shape as H2MM's dwells, for
    the same reason.

    Parameters
    ----------
    source : str or pathlib.Path
        The instrument file, or the container itself.
    analysis : EbfretAnalysis
        The run to record.
    parameters : dict, optional
        The settings. Their hash is the identity of the run.
    out_dir : str or pathlib.Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import (
        container_for,
        write_burst_artifact,
    )
    from chisurf.core.fio.pto import Measurement, is_measurement

    # ebFRET starts from binned traces, not photons, so the source is created
    # here rather than through the shared opener -- which would embed the `.dat`
    # under `tttr_photon_stream` and say something about the file that is false
    # in the one field a reader consults to decide how to open it.
    target = container_for(source)
    if not is_measurement(target):
        # As a context manager, because `close()` alone does not commit: the
        # README and the traces would be written and then dropped, and the
        # container would come back holding only the tables added afterwards.
        with Measurement.create(source, artifact_kind="trace_data"):
            pass
    source = target

    states = analysis.states
    written = write_burst_artifact(
        source,
        store_from_arrays(
            {
                "State": np.array([s.index for s in states], dtype=np.int32),
                "E": np.array([s.mean for s in states], dtype=float),
                "Std": np.array([s.std for s in states], dtype=float),
                "Precision": np.array([s.precision for s in states], dtype=float),
                "Occupancy": np.array([s.occupancy for s in states], dtype=float),
                # The evidence is a property of the model, so it repeats down the
                # table rather than living in a header nothing can query.
                "Evidence": np.full(len(states), float(analysis.evidence)),
            }
        ),
        name="ebfret states",
        artifact_kind="fit_result",
        operation_type="model_fitting",
        row_grain="state",
        parameters=parameters,
        derived_from="bursts",
        units={
            "State": "dimensionless",
            "E": "dimensionless",
            "Std": "dimensionless",
            "Precision": "dimensionless",
            "Occupancy": "dimensionless",
            "Evidence": "dimensionless",
        },
        out_dir=out_dir,
    )

    counts = np.asarray(analysis.transition_counts, dtype=float)
    if counts.size:
        n = counts.shape[0]
        pairs = [(s, t) for s in range(n) for t in range(n)]
        write_burst_artifact(
            source,
            store_from_arrays(
                {
                    "From": np.array([s for s, _ in pairs], dtype=np.int32),
                    "To": np.array([t for _, t in pairs], dtype=np.int32),
                    "Count": np.array([counts[s, t] for s, t in pairs], dtype=float),
                }
            ),
            name="ebfret transitions",
            artifact_kind="parameter_table",
            operation_type="model_fitting",
            row_grain="pair",
            parameters=parameters,
            derived_from="ebfret states",
            source_row_column="State",
            target_row_column="From",
            units={"From": "dimensionless", "To": "dimensionless", "Count": "counts"},
            out_dir=out_dir,
        )

    dwells = analysis.dwells
    if dwells:
        write_burst_artifact(
            source,
            store_from_arrays(
                {
                    # The key. A dwell subdivides a trace, so the join is declared
                    # rather than counted -- exactly H2MM's dwell case.
                    "Trace": np.array([d.trace for d in dwells], dtype=np.int32),
                    "State": np.array([d.state for d in dwells], dtype=np.int32),
                    "Start": np.array([d.start for d in dwells], dtype=np.int64),
                    "Length": np.array([d.length for d in dwells], dtype=np.int64),
                }
            ),
            name="ebfret dwells",
            artifact_kind="dwell_table",
            operation_type="model_fitting",
            row_grain="dwell",
            parameters=parameters,
            derived_from="ebfret states",
            source_row_column="State",
            target_row_column="State",
            units={
                "Trace": "dimensionless",
                "State": "dimensionless",
                "Start": "dimensionless",
                "Length": "dimensionless",
            },
            out_dir=out_dir,
        )
    return written
