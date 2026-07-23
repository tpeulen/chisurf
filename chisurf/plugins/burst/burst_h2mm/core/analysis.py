"""High-level H2MM analysis: state scan, model selection, and diagnostics.

Pure compute (numpy only) shared by the backend service and the CLI.  Given
engine-ready :class:`~chisurf.plugins.burst.burst_h2mm.core.h2mm.BurstPhotons`,
it fits a range of state counts, selects the best by BIC/ICL, and derives
Viterbi state paths, dwell times, and transition tables.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .engines import fit_one, viterbi
from .h2mm import BurstPhotons, H2mmModel


@dataclass
class StateFit:
    """One fitted model at a given state count with selection scores."""

    n_states: int
    model: H2mmModel
    loglik: float
    bic: float
    icl: float


@dataclass
class Transition:
    """A within-burst state transition recovered by Viterbi decoding."""

    burst: int
    state_from: int
    state_to: int
    e_from: float
    e_to: float
    time: int


@dataclass
class Dwell:
    """One Viterbi-decoded dwell (a maximal same-state run within a burst).

    Unlike :attr:`H2mmAnalysis.fret` (the *model* per-state efficiency), the
    :attr:`e` / :attr:`s` here are **measured** from the photons that fall in the
    dwell — the quantities burstH2MM histograms per state.

    Attributes
    ----------
    burst : int
        Zero-based burst index the dwell belongs to.
    state : int
        Viterbi state of the dwell.
    dur : int
        Dwell duration in base time units (``0`` for a single-photon dwell).
    n_photons : int
        Photons in the dwell.
    e : float
        Measured apparent FRET ``E = A / (A + D)`` over the dwell's photons
        (``nan`` if it has no donor/acceptor photons).
    s : float
        Measured stoichiometry ``S = (D + A) / (D + A + A_ex)`` over the dwell
        (``nan`` when no acceptor-excitation stream is defined).
    start : int
        Global (CSR) index of the dwell's first photon.
    stop : int
        Global (CSR) index one past the dwell's last photon.
    """

    burst: int
    state: int
    dur: int
    n_photons: int
    e: float
    s: float
    start: int
    stop: int


@dataclass
class H2mmAnalysis:
    """Full result of an H2MM analysis run.

    Attributes
    ----------
    best : StateFit
        The selected model (minimum BIC by default).
    scan : list of StateFit
        Every state count that was fitted, in ascending order.
    fret : numpy.ndarray
        Per-state apparent FRET efficiency, shape ``(n_states,)``.
    populations : numpy.ndarray
        Viterbi state populations (photon fraction per state).
    stoichiometry : numpy.ndarray
        Per-state apparent stoichiometry ``S``, shape ``(n_states,)``. All-``nan``
        when the data has no acceptor-excitation stream (< 3 streams).
    dwell_times : dict
        Maps ``state -> numpy.ndarray`` of dwell durations (base time units).
    dwells : list of Dwell
        Every Viterbi-decoded dwell with its measured E/S (for per-state dwell
        histograms and E–S scatter plots).
    transitions : list of Transition
        Within-burst transitions for the transition-density plot.
    trans_rates : numpy.ndarray
        Transition matrix converted to rates (1/s) using ``base_time_s``;
        diagonal is zero.
    path : numpy.ndarray
        Per-photon Viterbi state, length ``n_photons`` (aligned with the engine
        photon layout / :class:`~.photons.PhotonMeta`).
    n_streams : int
        Number of photon streams in the fitted data.
    base_time_s : float
        Seconds per base time unit.
    n_photons : int
        Total photons analysed.
    n_bursts : int
        Total bursts analysed.
    """

    best: StateFit
    scan: list[StateFit]
    fret: np.ndarray
    populations: np.ndarray
    stoichiometry: np.ndarray
    dwell_times: dict[int, np.ndarray]
    dwells: list[Dwell]
    transitions: list[Transition]
    trans_rates: np.ndarray
    path: np.ndarray
    n_streams: int
    base_time_s: float
    n_photons: int
    n_bursts: int


def state_fret(model: H2mmModel, acceptor_stream: int = 1, donor_stream: int = 0) -> np.ndarray:
    """Return apparent per-state FRET ``E = A / (A + D)`` from the emission matrix."""
    a = model.obs[:, acceptor_stream]
    d = model.obs[:, donor_stream]
    denom = a + d
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(denom > 0, a / denom, np.nan)
    return e


def state_stoichiometry(
    model: H2mmModel,
    donor_stream: int = 0,
    acceptor_stream: int = 1,
    aex_stream: int | None = 2,
) -> np.ndarray:
    """Return apparent per-state stoichiometry ``S`` from the emission matrix.

    ``S = (D + A) / (D + A + A_ex)`` where ``D`` / ``A`` are the donor- and
    acceptor-emission streams under donor excitation and ``A_ex`` is the
    acceptor-emission stream under acceptor (direct) excitation — the µsALEX/PIE
    stoichiometry. Returns all-``nan`` when ``aex_stream`` is ``None`` or the
    model has too few streams (no acceptor-excitation channel defined).
    """
    n_states = model.n_states
    if aex_stream is None or model.n_streams <= aex_stream:
        return np.full(n_states, np.nan, dtype=np.float64)
    dex = model.obs[:, donor_stream] + model.obs[:, acceptor_stream]
    denom = dex + model.obs[:, aex_stream]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(denom > 0, dex / denom, np.nan)
    return s


def state_mean_nanotime(
    path: np.ndarray,
    micro_time: np.ndarray,
    streams: np.ndarray,
    n_states: int,
    donor_stream: int = 0,
) -> np.ndarray:
    """Mean donor micro-time (nanotime) per Viterbi state.

    The donor fluorescence lifetime shortens as FRET rises, so the per-state mean
    donor nanotime is the observable behind the burstH2MM **E–τ** (FRET-lifetime)
    plot: static states fall on the line ``τ/τ0 = 1 − E`` while dynamic averaging
    pulls a state off it.

    Parameters
    ----------
    path : numpy.ndarray
        Per-photon Viterbi state (length ``N``).
    micro_time : numpy.ndarray
        Per-photon TCSPC micro time (length ``N``, same order as ``path``).
    streams : numpy.ndarray
        Per-photon stream index (length ``N``).
    n_states : int
        Number of states.
    donor_stream : int
        Stream index of the donor-emission channel.

    Returns
    -------
    numpy.ndarray
        Mean donor micro-time per state, shape ``(n_states,)`` (``nan`` where a
        state has no donor photons).
    """
    path = np.asarray(path)
    micro_time = np.asarray(micro_time, dtype=np.float64)
    streams = np.asarray(streams)
    out = np.full(n_states, np.nan, dtype=np.float64)
    for s in range(n_states):
        m = (path == s) & (streams == donor_stream)
        if m.any():
            out[s] = float(micro_time[m].mean())
    return out


def scan_states(
    data: BurstPhotons,
    state_counts: Sequence[int],
    n_restarts: int = 2,
    max_iter: int = 500,
    tol: float = 1e-7,
    seed: int = 0,
    engine: str = "em",
    surrogates: dict[int, object] | None = None,
    refine_iters: int = 20,
    criterion: str = "bic",
    patience: int | None = None,
    progress=None,
) -> list[StateFit]:
    """Fit a model for each requested state count and score BIC/ICL.

    Each state count is fitted independently with ``n_restarts`` random restarts
    using the selected compute ``engine`` (see :mod:`.engines`); model selection
    always scores the fitted models by BIC/ICL.

    When ``patience`` is set, the scan stops fitting higher state counts once the
    ``criterion`` has risen for ``patience + 1`` consecutive counts past the
    running best.  The model-selection curve is typically U-shaped and the
    **over-fit high-``k`` fits are the most expensive** — a redundant state
    creates a flat likelihood ridge, so those fits usually run to ``max_iter``
    without converging.  ``patience=None`` (default) fits every requested count
    (exact, unchanged behaviour); ``patience=1`` gives a safe, ~1.6× faster scan.

    (State-splitting / warm-starting the ``k``-state fit from the ``(k-1)``-state
    solution was evaluated as a speed-up but rejected: a single split cannot undo
    the state merging in the smaller fit, so it reliably reached *worse* optima
    than random restarts on well-separated data — the robust version needs full
    split+merge SMEM, which is out of scope here.)

    ``progress``, if given, is called ``progress(done, total, fits)`` after each
    state-count fit (with the list of :class:`StateFit` so far) so a caller can
    drive a progress bar / live plots.
    """
    use_icl = criterion.lower() == "icl"
    ordered = sorted(int(k) for k in state_counts)
    total = len(ordered)
    fits: list[StateFit] = []
    best_score = np.inf
    worse = 0
    for k in ordered:
        # Per-EM-map progress so a long single fit still advances the bar:
        # overall "done" = completed fits + fraction of the current one.
        on_iter = None
        if progress is not None:
            completed = len(fits)

            def on_iter(done, mx, _c=completed):
                progress(_c + done / max(mx, 1), total, fits)

        model = fit_one(
            data, k, engine,
            surrogates=surrogates, refine_iters=refine_iters,
            n_restarts=n_restarts, max_iter=max_iter, tol=tol, seed=seed,
            on_iter=on_iter,
        )
        _, icl = viterbi(model, data)
        fits.append(
            StateFit(
                n_states=k,
                model=model,
                loglik=float(model.loglik),
                bic=float(model.bic),
                icl=float(icl),
            )
        )
        if progress is not None:
            progress(len(fits), total, fits)
        if patience is not None:
            score = float(icl) if use_icl else float(model.bic)
            if score < best_score:
                best_score = score
                worse = 0
            else:
                worse += 1
                if worse > patience:
                    break
    return fits


def _measured_es(
    streams: np.ndarray,
    donor_stream: int,
    acceptor_stream: int,
    aex_stream: int | None,
) -> tuple[float, float]:
    """Measured ``(E, S)`` for the photons of a single dwell.

    ``streams`` is the per-photon stream slice of the dwell; ``E`` and ``S`` use
    the same definitions as :func:`state_fret` / :func:`state_stoichiometry` but
    from photon *counts* rather than the model emission matrix.
    """
    d = int(np.count_nonzero(streams == donor_stream))
    a = int(np.count_nonzero(streams == acceptor_stream))
    dex = d + a
    e = a / dex if dex > 0 else np.nan
    if aex_stream is None:
        return e, np.nan
    aex = int(np.count_nonzero(streams == aex_stream))
    s = dex / (dex + aex) if (dex + aex) > 0 else np.nan
    return e, s


def _dwells_and_transitions(
    model: H2mmModel,
    data: BurstPhotons,
    fret: np.ndarray,
    path: np.ndarray,
    donor_stream: int = 0,
    acceptor_stream: int = 1,
    aex_stream: int | None = None,
) -> tuple[dict[int, list[int]], list[Dwell], list[Transition], np.ndarray]:
    """Derive dwell records, transitions, and photon populations via Viterbi.

    Returns ``(dwell_durations, dwells, transitions, populations)`` where
    ``dwell_durations`` keeps the legacy ``state -> [durations]`` mapping and
    ``dwells`` is the richer per-dwell record list with measured E/S.
    """
    n_states = model.n_states
    offsets = data.burst_offsets
    streams_all = np.asarray(data.streams)

    dwell_durs: dict[int, list[int]] = {s: [] for s in range(n_states)}
    dwells: list[Dwell] = []
    transitions: list[Transition] = []
    populations = np.zeros(n_states, dtype=np.float64)

    # We need macro times to measure dwell durations; reconstruct per burst
    # from gap_slot + unique_dt (cumulative), which mirrors the input times.
    unique_dt = data.unique_dt

    def _record_dwell(b: int, st: int, g0: int, g1: int, dur: int) -> None:
        """Append the dwell spanning global photon indices ``[g0, g1)``."""
        dwell_durs[st].append(int(dur))
        e, s = _measured_es(streams_all[g0:g1], donor_stream, acceptor_stream, aex_stream)
        dwells.append(
            Dwell(burst=b, state=st, dur=int(dur), n_photons=int(g1 - g0),
                  e=float(e), s=float(s), start=int(g0), stop=int(g1))
        )

    for b in range(data.n_bursts):
        s = int(offsets[b])
        e = int(offsets[b + 1])
        seg = path[s:e]
        for st in seg:
            populations[st] += 1

        # Rebuild relative macro times within the burst.
        t = np.zeros(e - s, dtype=np.int64)
        for rel in range(1, e - s):
            slot = data.gap_slot[s + rel - 1]
            t[rel] = t[rel - 1] + (int(unique_dt[slot]) if slot >= 0 else 0)

        run_start = 0
        for rel in range(1, e - s):
            if seg[rel] != seg[rel - 1]:
                _record_dwell(b, int(seg[rel - 1]), s + run_start, s + rel,
                              int(t[rel] - t[run_start]))
                transitions.append(
                    Transition(
                        burst=b,
                        state_from=int(seg[rel - 1]),
                        state_to=int(seg[rel]),
                        e_from=float(fret[seg[rel - 1]]),
                        e_to=float(fret[seg[rel]]),
                        time=int(t[rel]),
                    )
                )
                run_start = rel
        # Trailing dwell of the final run.
        _record_dwell(b, int(seg[-1]), s + run_start, e, int(t[e - s - 1] - t[run_start]))

    if populations.sum() > 0:
        populations /= populations.sum()
    return dwell_durs, dwells, transitions, populations


def analyze(
    data: BurstPhotons,
    state_counts: Sequence[int] = (1, 2, 3),
    criterion: str = "bic",
    base_time_s: float = 1.0,
    acceptor_stream: int = 1,
    donor_stream: int = 0,
    n_restarts: int = 2,
    max_iter: int = 500,
    tol: float = 1e-7,
    seed: int = 0,
    engine: str = "em",
    surrogates: dict[int, object] | None = None,
    refine_iters: int = 20,
    patience: int | None = None,
    progress=None,
) -> H2mmAnalysis:
    """Fit, select, and characterise an H2MM model over a range of states.

    Parameters
    ----------
    data : BurstPhotons
        Photon data in engine layout.
    state_counts : sequence of int
        State counts to scan (e.g. ``(1, 2, 3, 4)``).
    criterion : {"bic", "icl"}
        Model-selection criterion (minimised).
    base_time_s : float
        Seconds per base time unit, used to convert transition probabilities
        to rates.
    acceptor_stream, donor_stream : int
        Stream indices used to compute apparent per-state FRET.
    n_restarts, max_iter, tol, seed
        Passed through to the optimiser.
    engine : str
        Compute engine for the per-state-count fits (see :mod:`.engines`):
        ``"em"`` (exact, default), ``"em-float32"``, ``"surrogate"``, or
        ``"surrogate-refine"``.
    surrogates : dict, optional
        Mapping ``n_states -> SurrogateModel`` for the surrogate engines;
        missing entries fall back to exact EM.
    refine_iters : int
        EM polish maps for the ``surrogate-refine`` engine.
    patience : int, optional
        Early-stop the state-count scan once the criterion has risen for
        ``patience + 1`` consecutive counts (see :func:`scan_states`); ``None``
        scans every count.
    progress : callable, optional
        Called ``progress(done, total, fits)`` after each state-count fit (for
        progress bars / live plots).

    Returns
    -------
    H2mmAnalysis
        The selected model plus its diagnostics.
    """
    scan = scan_states(
        data, state_counts, n_restarts=n_restarts,
        max_iter=max_iter, tol=tol, seed=seed,
        engine=engine, surrogates=surrogates, refine_iters=refine_iters,
        criterion=criterion, patience=patience, progress=progress,
    )
    key = (lambda f: f.icl) if criterion.lower() == "icl" else (lambda f: f.bic)
    best = min(scan, key=key)

    # An acceptor-excitation (Aex) stream — needed for stoichiometry — is present
    # only for µsALEX/PIE data with three or more streams; otherwise S is absent.
    aex_stream = 2 if data.n_streams >= 3 else None

    fret = state_fret(best.model, acceptor_stream, donor_stream)
    stoich = state_stoichiometry(best.model, donor_stream, acceptor_stream, aex_stream)

    path, _ = viterbi(best.model, data)
    dwell_durs, dwells, transitions, populations = _dwells_and_transitions(
        best.model, data, fret, path,
        donor_stream=donor_stream, acceptor_stream=acceptor_stream, aex_stream=aex_stream,
    )
    dwell_arrays = {s: np.asarray(v, dtype=np.float64) for s, v in dwell_durs.items()}

    # Transition probabilities → rates (1/s); diagonal set to zero.
    trans = best.model.trans
    rates = (trans / base_time_s if base_time_s > 0 else trans).copy()
    np.fill_diagonal(rates, 0.0)

    return H2mmAnalysis(
        best=best,
        scan=scan,
        fret=fret,
        populations=populations,
        stoichiometry=stoich,
        dwell_times=dwell_arrays,
        dwells=dwells,
        transitions=transitions,
        trans_rates=rates,
        path=np.asarray(path, dtype=np.int64),
        n_streams=int(data.n_streams),
        base_time_s=base_time_s,
        n_photons=data.n_photons,
        n_bursts=data.n_bursts,
    )
