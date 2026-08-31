"""High-level H2MM analysis: state scan, model selection, and diagnostics.

Pure compute (numpy only) shared by the backend service and the CLI.  Given
engine-ready :class:`~chisurf.plugins.burst.burst_h2mm.core.h2mm.BurstPhotons`,
it fits a range of state counts, selects the best by BIC/ICL, and derives
Viterbi state paths, dwell times, and transition tables.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .engines import (
    DECODER_KEEPS_DWELLS,
    decode,
    fit_one,
    normalize_decoder,
    posterior,
    viterbi,
)
from .engines import optimize as _h2mm_optimize
from .h2mm import BurstPhotons, H2mmModel, prepare_bursts

logger = logging.getLogger(__name__)


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
    is_edge : bool
        Whether the dwell touches its burst's first or last photon. Such a dwell
        is **censored**: the molecule was already in that state when the burst
        began, or still in it when the burst ended, so its measured duration is
        a lower bound set by the burst — not the time the state lasted. A state
        slower than a burst produces nothing but edge dwells, whose "dwell
        times" are burst durations.
    """

    burst: int
    state: int
    dur: int
    n_photons: int
    e: float
    s: float
    start: int
    stop: int
    is_edge: bool = False


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
        State populations counted from ``path`` (photon fraction per state), so
        they always match the decoded assignment the rest of the result carries.
        With ``decoder="viterbi"`` this is **biased**: the argmax resolves every
        ambiguous photon the same way, inflating well-separated states and
        erasing ambiguous ones. Prefer :attr:`posterior_populations`.
    posterior_populations : numpy.ndarray
        State populations from the per-photon posterior γ (its column means) —
        the **unbiased** occupancy estimate, independent of which decoder ran.
        All-``nan`` if γ could not be computed.
    stoichiometry : numpy.ndarray
        Per-state apparent stoichiometry ``S``, shape ``(n_states,)``. All-``nan``
        when the data has no acceptor-excitation stream (< 3 streams).
    dwell_times : dict
        Maps ``state -> numpy.ndarray`` of dwell durations (base time units),
        **every** dwell including the censored ones at burst edges. For the
        distribution of how long a state lasts, use
        :meth:`dwell_time_arrays`, which drops them.
    dwells : list of Dwell
        Every decoded dwell with its measured E/S (for per-state dwell
        histograms and E–S scatter plots). Derived from
        :attr:`dwell_path`, not necessarily from :attr:`path`.
    transitions : list of Transition
        Within-burst transitions for the transition-density plot.
    trans_rates : numpy.ndarray
        Transition matrix converted to rates (1/s) using ``base_time_s``;
        diagonal is zero.
    path : numpy.ndarray
        Per-photon state from the selected ``decoder``, length ``n_photons``
        (aligned with the engine photon layout / :class:`~.photons.PhotonMeta`).
    decoder : str
        Which decoder produced :attr:`path` — ``"viterbi"``, ``"jitter"`` or
        ``"ffbs"``.
    decoder_seed : int
        Seed of the draw (meaningless for ``"viterbi"``).
    n_underflow : int
        Photons whose posterior row carried no information and were drawn
        uniformly. Non-zero means the model gives part of the data (near-)zero
        probability — treat the decode with suspicion.
    dwell_path : numpy.ndarray
        The path :attr:`dwells` and :attr:`transitions` were derived from. Equal
        to :attr:`path` except under ``decoder="jitter"``, whose independent
        per-photon draws shatter a dwell into single photons — dwell statistics
        then come from Viterbi instead, and :attr:`dwell_decoder` says so.
    dwell_decoder : str
        Decoder that produced :attr:`dwell_path`.
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
    divisors: int = 1
    donor_streams: tuple[int, ...] = (0,)
    acceptor_streams: tuple[int, ...] = (1,)
    aex_streams: tuple[int, ...] | None = None
    posterior_populations: np.ndarray | None = None
    decoder: str = "viterbi"
    decoder_seed: int = 0
    n_underflow: int = 0
    dwell_path: np.ndarray | None = None
    dwell_decoder: str = "viterbi"

    def dwell_time_arrays(self, *, include_edges: bool = False) -> dict:
        """Per-state dwell durations (base time units), censored ones dropped.

        A dwell that touches its burst's first or last photon did not *end* —
        the burst did. Its duration is therefore a lower bound, and a state
        slower than a burst produces nothing else: histogramming those numbers
        plots the burst-duration distribution and calls it a dwell time, which
        is how a slow state comes out looking like the photon-selection
        settings. Only dwells with a transition at both ends are observed
        durations, so they are what this returns.

        Parameters
        ----------
        include_edges : bool, optional
            Keep the censored dwells (the raw :attr:`dwell_times` content).

        Returns
        -------
        dict
            ``state -> numpy.ndarray`` of durations. A state with no complete
            dwell maps to an empty array — a real answer ("this state was never
            seen to end"), not a missing key.
        """
        n_states = int(self.best.model.n_states)
        out = {s: [] for s in range(n_states)}
        for d in self.dwells:
            if d.is_edge and not include_edges:
                continue
            if 0 <= int(d.state) < n_states:
                out[int(d.state)].append(int(d.dur))
        return {s: np.asarray(v, dtype=np.int64) for s, v in out.items()}


def _obs_sum(model: H2mmModel, streams) -> np.ndarray:
    """Sum the emission matrix over one or more stream indices (per state)."""
    if streams is None:
        return np.zeros(model.n_states, dtype=np.float64)
    cols = np.atleast_1d(np.asarray(streams, dtype=int))
    cols = cols[(cols >= 0) & (cols < model.n_streams)]
    if cols.size == 0:
        return np.zeros(model.n_states, dtype=np.float64)
    return model.obs[:, cols].sum(axis=1)


def state_fret(model: H2mmModel, acceptor_stream=1, donor_stream=0) -> np.ndarray:
    """Return apparent per-state FRET ``E = A / (A + D)`` from the emission matrix.

    ``donor_stream`` / ``acceptor_stream`` may be a single index or a sequence of
    indices (the latter for nanotime-divisor streams, where a role spans several
    micro-time bins).
    """
    a = _obs_sum(model, acceptor_stream)
    d = _obs_sum(model, donor_stream)
    denom = a + d
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(denom > 0, a / denom, np.nan)
    return e


def state_stoichiometry(
    model: H2mmModel,
    donor_stream=0,
    acceptor_stream=1,
    aex_stream=2,
) -> np.ndarray:
    """Return apparent per-state stoichiometry ``S`` from the emission matrix.

    ``S = (D + A) / (D + A + A_ex)`` where ``D`` / ``A`` are the donor- and
    acceptor-emission streams under donor excitation and ``A_ex`` is the
    acceptor-emission stream under acceptor (direct) excitation — the µsALEX/PIE
    stoichiometry. Each argument may be a single index or a sequence of indices
    (nanotime-divisor streams). Returns all-``nan`` when ``aex_stream`` is ``None``
    or resolves to no valid stream (no acceptor-excitation channel defined).
    """
    n_states = model.n_states
    if aex_stream is None:
        return np.full(n_states, np.nan, dtype=np.float64)
    aex_cols = np.atleast_1d(np.asarray(aex_stream, dtype=int))
    aex_cols = aex_cols[(aex_cols >= 0) & (aex_cols < model.n_streams)]
    if aex_cols.size == 0:  # no acceptor-excitation channel defined
        return np.full(n_states, np.nan, dtype=np.float64)
    aex = model.obs[:, aex_cols].sum(axis=1)
    dex = _obs_sum(model, donor_stream) + _obs_sum(model, acceptor_stream)
    denom = dex + aex
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(denom > 0, dex / denom, np.nan)
    return s


@dataclass
class Uncertainty:
    """Bootstrap confidence intervals for the selected model's parameters.

    All arrays are in **E-ascending state order** (sort each replicate's states by
    apparent FRET, then take percentiles), so index ``r`` is the ``r``-th lowest-E
    state — align to the native model order with ``numpy.argsort(analysis.fret)``.

    Attributes
    ----------
    n_boot : int
        Number of bootstrap resamples that contributed.
    ci : tuple of float
        The (low, high) percentiles used for the intervals.
    fret_lo, fret_hi, fret_std : numpy.ndarray
        Per-state apparent-FRET interval and standard deviation.
    stoich_lo, stoich_hi, stoich_std : numpy.ndarray
        Per-state stoichiometry interval / std (all-``nan`` without an Aex stream).
    escape_lo, escape_hi, escape_std : numpy.ndarray
        Per-state one-step escape probability ``1 − trans[i, i]`` interval / std.
    """

    n_boot: int
    ci: tuple[float, float]
    fret_lo: np.ndarray
    fret_hi: np.ndarray
    fret_std: np.ndarray
    stoich_lo: np.ndarray
    stoich_hi: np.ndarray
    stoich_std: np.ndarray
    escape_lo: np.ndarray
    escape_hi: np.ndarray
    escape_std: np.ndarray


def _subset_bursts(data: BurstPhotons, idx: np.ndarray) -> BurstPhotons:
    """Build a new :class:`BurstPhotons` from the bursts ``idx`` (with repeats).

    Rebuilds each selected burst's ``(times, streams)`` from the CSR arrays (the
    absolute macro-time origin is irrelevant to H2MM — only inter-photon gaps
    matter) so a bootstrap resample can be re-fitted with the normal pipeline.
    """
    offsets = np.asarray(data.burst_offsets)
    streams_all = np.asarray(data.streams)
    gap = np.asarray(data.gap_slot)
    uniq = np.asarray(data.unique_dt)
    times_list: list[np.ndarray] = []
    strm_list: list[np.ndarray] = []
    for b in idx:
        s, e = int(offsets[b]), int(offsets[b + 1])
        n = e - s
        if n <= 0:
            continue
        t = np.zeros(n, dtype=np.int64)
        if n > 1 and uniq.size:
            slots = gap[s : e - 1]
            dt = np.where(slots >= 0, uniq[np.clip(slots, 0, len(uniq) - 1)], 0)
            t[1:] = np.cumsum(dt.astype(np.int64))
        times_list.append(t)
        strm_list.append(streams_all[s:e].astype(np.int32))
    return prepare_bursts(times_list, strm_list, n_streams=int(data.n_streams))


def bootstrap_uncertainty(
    data: BurstPhotons,
    n_states: int,
    *,
    n_boot: int = 20,
    engine: str = "em",
    n_restarts: int = 1,
    max_iter: int = 300,
    tol: float = 1e-7,
    seed: int = 0,
    donor_streams=(0,),
    acceptor_streams=(1,),
    aex_streams=None,
    ci: tuple[float, float] = (2.5, 97.5),
    progress=None,
) -> Uncertainty:
    """Bootstrap the selected ``n_states`` model over bursts to size its errors.

    Draws ``n_boot`` burst resamples (with replacement), refits an ``n_states``
    model to each, and returns per-state percentile confidence intervals for E, S
    and the escape probability. Replicates are aligned by sorting each fit's states
    on apparent FRET (label-switching is otherwise unidentifiable). This is the
    burstH2MM uncertainty step; it is compute-heavy (``n_boot`` extra fits), so
    callers typically run it on demand rather than with every analysis.

    ``progress``, if given, is called ``progress(done, n_boot)`` after each resample.
    """
    rng = np.random.default_rng(seed)
    n_b = int(data.n_bursts)
    e_samples: list[np.ndarray] = []
    s_samples: list[np.ndarray] = []
    esc_samples: list[np.ndarray] = []
    for b in range(int(n_boot)):
        idx = rng.integers(0, n_b, n_b)
        sub = _subset_bursts(data, idx)
        fit = fit_one(sub, n_states, engine, n_restarts=n_restarts,
                      max_iter=max_iter, tol=tol, seed=int(rng.integers(0, 2**31 - 1)))
        e = state_fret(fit, acceptor_streams, donor_streams)
        order = np.argsort(e)
        e_samples.append(e[order])
        s_samples.append(state_stoichiometry(fit, donor_streams, acceptor_streams, aex_streams)[order])
        esc_samples.append((1.0 - np.diag(fit.trans))[order])
        if progress is not None:
            progress(b + 1, int(n_boot))

    e_arr = np.asarray(e_samples, dtype=np.float64)
    s_arr = np.asarray(s_samples, dtype=np.float64)
    esc_arr = np.asarray(esc_samples, dtype=np.float64)
    lo, hi = ci

    def _pct(a, q):
        return np.nanpercentile(a, q, axis=0) if a.size else np.full(n_states, np.nan)

    def _std(a):
        return np.nanstd(a, axis=0) if a.size else np.full(n_states, np.nan)

    with warnings.catch_warnings():
        # Stoichiometry columns are all-NaN without an Aex stream; that is expected.
        warnings.simplefilter("ignore", RuntimeWarning)
        return Uncertainty(
            n_boot=int(n_boot),
            ci=(float(lo), float(hi)),
            fret_lo=_pct(e_arr, lo), fret_hi=_pct(e_arr, hi), fret_std=_std(e_arr),
            stoich_lo=_pct(s_arr, lo), stoich_hi=_pct(s_arr, hi), stoich_std=_std(s_arr),
            escape_lo=_pct(esc_arr, lo), escape_hi=_pct(esc_arr, hi), escape_std=_std(esc_arr),
        )


@dataclass
class LikelihoodScan:
    """A one-parameter profile of the log-likelihood around the fitted value.

    Holding every other parameter fixed, one parameter (a state's E or S) is swept
    over ``values`` and the model log-likelihood recomputed at each — the burstH2MM
    ``ll_*_scatter`` diagnostic. The confidence interval is where the deviance
    ``2·(logL_max − logL)`` stays below ``threshold`` (χ²₁: 3.84 → 95 %). A flat
    profile (CI spanning the whole scan window) flags a poorly-identified state.

    Attributes
    ----------
    state : int
        State index the parameter belongs to.
    param : str
        ``"E"`` or ``"S"``.
    values : numpy.ndarray
        Swept parameter grid.
    loglik : numpy.ndarray
        Model log-likelihood at each grid point.
    mle : float
        The fitted (maximum-likelihood) value of the parameter.
    ci : tuple of float
        ``(low, high)`` confidence interval at ``threshold`` deviance.
    threshold : float
        Deviance threshold used for the interval (default 3.84).
    """

    state: int
    param: str
    values: np.ndarray
    loglik: np.ndarray
    mle: float
    ci: tuple[float, float]
    threshold: float


def fixed_loglik(model: H2mmModel, data: BurstPhotons) -> float:
    """Forward log-likelihood of a *fixed* model (one EM map, no parameter update).

    ``optimize(..., max_iter=1, tol=0.0)`` runs a single E-step whose reported
    ``loglik`` is that of the input model — the same fixed-model forward
    log-likelihood the A/B tests check against ``H2MM_C``.
    """
    return float(_h2mm_optimize(model, data, max_iter=1, tol=0.0).loglik)


def _rescale_group(row: np.ndarray, cols: np.ndarray, new_total: float) -> None:
    """Rescale ``row[cols]`` in place to sum to ``new_total`` (spread evenly if 0)."""
    cur = float(row[cols].sum())
    if cur > 0:
        row[cols] *= new_total / cur
    elif cols.size:
        row[cols] = new_total / cols.size


def _model_with_state_e(
    model: H2mmModel, state: int, new_e: float, donor: np.ndarray, acceptor: np.ndarray
) -> H2mmModel:
    """Copy ``model`` with state ``state``'s apparent E set to ``new_e``.

    The donor+acceptor (donor-excitation) probability mass is preserved and split
    ``(1−E) : E`` between the donor and acceptor stream groups; other streams
    (e.g. acceptor-excitation) are untouched, so the emission row stays normalised.
    """
    obs = np.array(model.obs, dtype=np.float64, copy=True)
    row = obs[state]
    dex = float(row[donor].sum() + row[acceptor].sum())
    _rescale_group(row, donor, (1.0 - new_e) * dex)
    _rescale_group(row, acceptor, new_e * dex)
    return H2mmModel(prior=np.array(model.prior, copy=True),
                     trans=np.array(model.trans, copy=True), obs=obs)


def _model_with_state_s(
    model: H2mmModel, state: int, new_s: float,
    donor: np.ndarray, acceptor: np.ndarray, aex: np.ndarray,
) -> H2mmModel:
    """Copy ``model`` with state ``state``'s stoichiometry S set to ``new_s``.

    The colour mass (donor + acceptor + Aex) is split ``S : (1−S)`` between the
    donor-excitation block (donor+acceptor, internal E kept) and the Aex block.
    """
    obs = np.array(model.obs, dtype=np.float64, copy=True)
    row = obs[state]
    total = float(row[donor].sum() + row[acceptor].sum() + row[aex].sum())
    dex = float(row[donor].sum() + row[acceptor].sum())
    new_dex = new_s * total
    if dex > 0:
        row[donor] *= new_dex / dex
        row[acceptor] *= new_dex / dex
    else:
        _rescale_group(row, np.concatenate([donor, acceptor]), new_dex)
    _rescale_group(row, aex, (1.0 - new_s) * total)
    return H2mmModel(prior=np.array(model.prior, copy=True),
                     trans=np.array(model.trans, copy=True), obs=obs)


def _ci_from_scan(values: np.ndarray, loglik: np.ndarray, threshold: float) -> tuple[float, float]:
    """Confidence interval where deviance ``2·(max−logL)`` first exceeds ``threshold``.

    Linearly interpolates the crossing on each side of the peak; if the profile
    never crosses within the window the interval is the window edge (a flat,
    poorly-identified direction).
    """
    values = np.asarray(values, dtype=np.float64)
    loglik = np.asarray(loglik, dtype=np.float64)
    imax = int(np.argmax(loglik))
    dev = 2.0 * (loglik[imax] - loglik)

    def _cross(order):
        prev_v, prev_d = values[imax], 0.0
        for i in order:
            if dev[i] >= threshold:
                denom = dev[i] - prev_d
                frac = (threshold - prev_d) / denom if denom > 0 else 0.0
                return prev_v + frac * (values[i] - prev_v)
            prev_v, prev_d = values[i], dev[i]
        return values[order[-1]] if len(order) else values[imax]

    lo = _cross(list(range(imax - 1, -1, -1)))
    hi = _cross(list(range(imax + 1, len(values))))
    return float(min(lo, hi)), float(max(lo, hi))


def profile_likelihood(
    data: BurstPhotons,
    model: H2mmModel,
    *,
    donor_streams=(0,),
    acceptor_streams=(1,),
    aex_streams=None,
    n_points: int = 25,
    half_width: float = 0.25,
    threshold: float = 3.84,
    progress=None,
) -> list[LikelihoodScan]:
    """Profile the log-likelihood in each state's E (and S) around the fit.

    For every state the apparent E is swept over a ``±half_width`` window (clipped
    to ``[0, 1]``) with all other parameters held fixed, and the model
    log-likelihood recomputed (:func:`fixed_loglik`); the same is done for S when an
    acceptor-excitation stream is present. This is the burstH2MM likelihood-based
    uncertainty — it exposes *unidentifiable* directions (a flat profile) that a
    data bootstrap can miss.

    ``progress`` is called ``progress(done, total)`` after each evaluated point.
    """
    donor = np.atleast_1d(np.asarray(donor_streams, dtype=int))
    acceptor = np.atleast_1d(np.asarray(acceptor_streams, dtype=int))
    aex = np.atleast_1d(np.asarray(aex_streams, dtype=int)) if aex_streams is not None else None
    n_states = model.n_states

    e0 = state_fret(model, acceptor, donor)
    s0 = (state_stoichiometry(model, donor, acceptor, aex)
          if aex is not None else np.full(n_states, np.nan))

    jobs: list[tuple[int, str]] = [(i, "E") for i in range(n_states) if np.isfinite(e0[i])]
    if aex is not None:
        jobs += [(i, "S") for i in range(n_states) if np.isfinite(s0[i])]
    total = len(jobs) * int(n_points)
    done = 0

    scans: list[LikelihoodScan] = []
    for state, param in jobs:
        centre = e0[state] if param == "E" else s0[state]
        grid = np.clip(np.linspace(centre - half_width, centre + half_width, int(n_points)), 0.0, 1.0)
        grid = np.unique(grid)
        ll = np.empty(grid.shape[0], dtype=np.float64)
        for k, v in enumerate(grid):
            if param == "E":
                m = _model_with_state_e(model, state, float(v), donor, acceptor)
            else:
                m = _model_with_state_s(model, state, float(v), donor, acceptor, aex)
            ll[k] = fixed_loglik(m, data)
            done += 1
            if progress is not None:
                progress(done, total)
        scans.append(LikelihoodScan(
            state=state, param=param, values=grid, loglik=ll,
            mle=float(centre), ci=_ci_from_scan(grid, ll, threshold), threshold=float(threshold)))
    return scans


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
    donor_streams,
    acceptor_streams,
    aex_streams,
) -> tuple[float, float]:
    """Measured ``(E, S)`` for the photons of a single dwell.

    ``streams`` is the per-photon stream slice of the dwell; ``E`` and ``S`` use
    the same definitions as :func:`state_fret` / :func:`state_stoichiometry` but
    from photon *counts* rather than the model emission matrix. Each role argument
    is a set of stream indices (one, or several for nanotime-divisor streams).
    """
    d = int(np.count_nonzero(np.isin(streams, donor_streams)))
    a = int(np.count_nonzero(np.isin(streams, acceptor_streams)))
    dex = d + a
    e = a / dex if dex > 0 else np.nan
    if not aex_streams:
        return e, np.nan
    aex = int(np.count_nonzero(np.isin(streams, aex_streams)))
    s = dex / (dex + aex) if (dex + aex) > 0 else np.nan
    return e, s


def _dwells_and_transitions(
    model: H2mmModel,
    data: BurstPhotons,
    fret: np.ndarray,
    path: np.ndarray,
    donor_streams=(0,),
    acceptor_streams=(1,),
    aex_streams=None,
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
        e, s = _measured_es(streams_all[g0:g1], donor_streams, acceptor_streams, aex_streams)
        # Censored at a burst boundary: one end of this dwell is the burst, not
        # a transition. Decided here, where the burst bounds are, so every
        # consumer shares one definition of "edge".
        edge = g0 == int(offsets[b]) or g1 == int(offsets[b + 1])
        dwells.append(
            Dwell(burst=b, state=st, dur=int(dur), n_photons=int(g1 - g0),
                  e=float(e), s=float(s), start=int(g0), stop=int(g1),
                  is_edge=bool(edge))
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
    divisors: int = 1,
    decoder: str = "viterbi",
    decoder_seed: int = 0,
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
    divisors : int
        Nanotime divisors: number of micro-time bins per base stream in ``data``
        (``data.n_streams == n_base * divisors``, contiguous per-base blocks). The
        FRET/stoichiometry roles sum the emission matrix over each block. ``1``
        (default) means no nanotime splitting.
    decoder : str
        How to assign one state per photon (see :mod:`.engines`):
        ``"viterbi"`` (most likely path, the default), ``"jitter"`` (draw each
        photon from its posterior — faithful photon distribution), or ``"ffbs"``
        (draw whole paths — faithful *and* keeps dwell structure). The unbiased
        occupancy is reported as ``posterior_populations`` whichever is chosen.
        With ``"jitter"``, dwells and transitions are still derived from a
        Viterbi path, because independent per-photon draws shatter them.
    decoder_seed : int
        Seed for the sampling decoders; results are reproducible and independent
        of thread count.
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

    # With nanotime divisors each base stream (donor, acceptor, optional Aex) is a
    # contiguous block of ``divisors`` streams; the FRET/stoichiometry roles sum
    # over the block. An Aex block — needed for stoichiometry — is present only for
    # µsALEX/PIE data with three or more base streams; otherwise S is absent.
    div = max(int(divisors), 1)
    n_base = int(data.n_streams) // div
    donor_streams = tuple(range(donor_stream * div, donor_stream * div + div))
    acceptor_streams = tuple(range(acceptor_stream * div, acceptor_stream * div + div))
    aex_streams = tuple(range(2 * div, 3 * div)) if n_base >= 3 else None

    fret = state_fret(best.model, acceptor_streams, donor_streams)
    stoich = state_stoichiometry(best.model, donor_streams, acceptor_streams, aex_streams)

    decoder = normalize_decoder(decoder)
    path, n_underflow = decode(best.model, data, decoder, decoder_seed)

    # The unbiased occupancy, independent of which decoder ran. Counting a
    # Viterbi path answers the "distribution over states" question with a
    # one-directional bias; the posterior column means do not. If γ cannot be
    # had it stays nan rather than silently becoming the counts -- which is the
    # biased answer this exists to avoid.
    try:
        gamma, gamma_underflow = posterior(best.model, data)
        posterior_pops = np.asarray(gamma.mean(axis=0), dtype=np.float64)
        if decoder == "viterbi":
            n_underflow = gamma_underflow
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("H2MM posterior unavailable (%s: %s)", type(exc).__name__, exc)
        posterior_pops = np.full(best.model.n_states, np.nan, dtype=np.float64)

    # Dwells need a path with intact temporal structure. A marginal draw has
    # none -- it flips roughly one photon in ten of a solidly occupied state,
    # turning one dwell into dozens -- so dwell statistics come from Viterbi
    # instead, and the result records that they did.
    if DECODER_KEEPS_DWELLS.get(decoder, True):
        dwell_path, dwell_decoder = path, decoder
    else:
        dwell_path, _icl = viterbi(best.model, data)
        dwell_decoder = "viterbi"

    dwell_durs, dwells, transitions, populations = _dwells_and_transitions(
        best.model, data, fret, dwell_path,
        donor_streams=donor_streams, acceptor_streams=acceptor_streams, aex_streams=aex_streams,
    )
    # Populations must describe the assignment the rest of the result carries,
    # which under "jitter" is `path`, not the Viterbi path the dwells came from.
    if dwell_decoder != decoder:
        counts = np.bincount(np.asarray(path, dtype=np.int64),
                             minlength=best.model.n_states).astype(np.float64)
        populations = counts / counts.sum() if counts.sum() > 0 else counts
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
        divisors=div,
        donor_streams=donor_streams,
        acceptor_streams=acceptor_streams,
        aex_streams=aex_streams,
        posterior_populations=posterior_pops,
        decoder=decoder,
        decoder_seed=int(decoder_seed),
        n_underflow=int(n_underflow),
        dwell_path=np.asarray(dwell_path, dtype=np.int64),
        dwell_decoder=dwell_decoder,
    )
