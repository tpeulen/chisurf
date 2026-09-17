"""Qt-free orchestration behind the Gopich-Szabo plugin.

Turns burst tables and TTTR files into :class:`PhotonBursts`, runs the fit, the
transition-time scan and the H2MM cross-check, and packages the result for the
GUI, the CLI and the RPC service alike.

The kinetics themselves live in
:mod:`chisurf.core.fluorescence.burst.gopich_szabo`; nothing here does maths
that a headless caller could not reach directly.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.burst import gopich_szabo as gs
from chisurf.core.fluorescence.burst.photons import (
    StreamDef,
    extract_burst_photons,
    load_bur_dataframe,
    load_tttrs_for_dataframe,
    streams_from_dicts,
)

__all__ = [
    "H2MM_MEMORY_BUDGET",
    "GsAnalysis",
    "analyse",
    "choose_h2mm_tick",
    "compare_with_h2mm",
    "default_stream_dicts",
    "load_photons",
    "simulate_two_state",
]


def default_stream_dicts() -> list[dict]:
    """Return the default two-colour stream definition as plain dictionaries."""
    return [
        {"name": "donor", "channels": [0, 8], "micro_time_ranges": []},
        {"name": "acceptor", "channels": [1, 9], "micro_time_ranges": []},
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────────────────
def load_photons(
    bur_paths: Sequence[str | pathlib.Path],
    data_dir: str | pathlib.Path,
    streams: Sequence[StreamDef] | Sequence[dict] | None = None,
    file_type: str = "auto",
    macro_time_resolution: float | None = None,
    min_photons: int = 10,
    max_bursts: int = 0,
) -> tuple[gs.PhotonBursts, dict]:
    """Load bursts from ``.bur`` tables and their TTTR files.

    Parameters
    ----------
    bur_paths : sequence of path-like
        Burst tables.
    data_dir : path-like
        Directory the ``First File`` entries resolve against.
    streams : sequence, optional
        :class:`StreamDef` objects or their dictionary form; defaults to
        :func:`default_stream_dicts`. The **order defines the colour index**, so
        the first stream is colour 0 (the donor for a two-colour fit).
    file_type : str
        TTTR container type, ``"auto"`` to infer.
    macro_time_resolution : float, optional
        Seconds per macro-time tick. Read from the first file's header when
        omitted — the likelihood is in real time, so this is not optional
        information and a wrong value rescales every fitted rate.
    min_photons : int
        Bursts with fewer assigned photons are dropped. The default of 10 is
        higher than H2MM's because a continuous-time fit gains nothing from
        bursts too short to show a gap distribution.
    max_bursts : int
        Keep at most this many bursts (0 = all). Useful for a quick look.

    Returns
    -------
    bursts : PhotonBursts
        Arrival times in **seconds**.
    info : dict
        ``{"n_bursts", "n_photons", "macro_time_resolution", "stream_names",
        "photons_per_stream"}``.

    Raises
    ------
    ValueError
        If no burst survives, or the macro-time resolution cannot be determined.
    """
    if streams is None:
        streams = default_stream_dicts()
    stream_defs = [s if isinstance(s, StreamDef) else streams_from_dicts([s])[0] for s in streams]

    table = load_bur_dataframe([pathlib.Path(p) for p in bur_paths])
    tttrs = load_tttrs_for_dataframe(table, data_dir, file_type=file_type)
    if not tttrs:
        raise ValueError("none of the TTTR files referenced by the burst table could be loaded")

    if macro_time_resolution is None:
        # The first entry that actually knows: a file that failed to open comes
        # back as an empty object whose header reports a negative resolution.
        macro_time_resolution = 0.0
        for tttr in tttrs.values():
            resolution = float(getattr(tttr.header, "macro_time_resolution", 0.0))
            if np.isfinite(resolution) and resolution > 0.0:
                macro_time_resolution = resolution
                break
    macro_time_resolution = float(macro_time_resolution)
    if not np.isfinite(macro_time_resolution) or macro_time_resolution <= 0.0:
        raise ValueError(
            "the macro-time resolution is unknown; pass it explicitly, because "
            "every fitted rate is proportional to it"
        )

    times, stream_idx = extract_burst_photons(
        table, tttrs, stream_defs, min_photons=int(min_photons)
    )
    if max_bursts and len(times) > int(max_bursts):
        times = times[: int(max_bursts)]
        stream_idx = stream_idx[: int(max_bursts)]

    seconds = [t.astype(np.float64) * macro_time_resolution for t in times]
    bursts = gs.PhotonBursts.from_lists(
        seconds, stream_idx, n_colors=len(stream_defs), min_photons=int(min_photons)
    )
    counts = np.bincount(bursts.colors, minlength=len(stream_defs))
    info = {
        "n_bursts": len(bursts),
        "n_photons": bursts.n_photons,
        "macro_time_resolution": macro_time_resolution,
        "stream_names": [s.name for s in stream_defs],
        "photons_per_stream": counts.tolist(),
        # The measurements themselves, not the `.bur` tables that point at
        # them: a result belongs beside the photons it was fitted to, and a
        # `.bur` lives one directory down in `bi4_bur/`.
        "tttr_files": [str(getattr(tttr, "filename", "")) for tttr in tttrs.values()],
    }
    return bursts, info


def simulate_two_state(
    k_forward: float = 3000.0,
    k_backward: float = 1000.0,
    efficiencies: Sequence[float] = (0.25, 0.75),
    photon_rate: float = 50e3,
    n_bursts: int = 200,
    photons_per_burst: int = 200,
    seed: int = 1,
) -> gs.PhotonBursts:
    r"""Simulate coloured photons from a two-state interconverting molecule.

    Exact rather than approximate: the state trajectory is sampled by Gillespie
    between photon arrivals, so a fit of this data has a known right answer and
    the tool can be exercised — and verified — with no files at all.

    Parameters
    ----------
    k_forward, k_backward : float
        ``1 -> 2`` and ``2 -> 1`` rates in s\ :sup:`-1`.
    efficiencies : sequence of float
        Apparent FRET efficiency of each state.
    photon_rate : float
        Mean photon detection rate within a burst, s\ :sup:`-1`.
    n_bursts : int
        Number of bursts.
    photons_per_burst : int
        Photons per burst.
    seed : int
        Random seed.

    Returns
    -------
    PhotonBursts
    """
    rng = np.random.default_rng(int(seed))
    efficiencies = np.asarray(efficiencies, dtype=float)
    p_first = k_backward / (k_forward + k_backward)
    times: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    for _ in range(int(n_bursts)):
        n = int(photons_per_burst)
        arrival = np.cumsum(rng.exponential(1.0 / photon_rate, n))
        state = 0 if rng.random() < p_first else 1
        clock = 0.0
        nxt = clock + rng.exponential(1.0 / (k_forward if state == 0 else k_backward))
        states = np.empty(n, dtype=int)
        for i in range(n):
            while nxt < arrival[i]:
                clock = nxt
                state = 1 - state
                nxt = clock + rng.exponential(1.0 / (k_forward if state == 0 else k_backward))
            states[i] = state
        colors.append((rng.random(n) < efficiencies[states]).astype(np.int32))
        times.append(arrival)
    return gs.PhotonBursts.from_lists(times, colors, 2)


# ──────────────────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class GsAnalysis:
    """Everything one run of the tool produced.

    Attributes
    ----------
    fit : gopich_szabo.GsFitResult
        The maximum-likelihood fit.
    info : dict
        Data provenance from :func:`load_photons` (or the simulation settings).
    transit_times : numpy.ndarray
        Scanned transition durations in seconds (empty when not scanned).
    transit_delta : numpy.ndarray
        Log-likelihood relative to the instantaneous model, same length.
    state_path : numpy.ndarray
        Viterbi state per photon (empty when not decoded).
    h2mm : dict
        Cross-check against the discrete-time H2MM fit (empty when not run).
    """

    fit: gs.GsFitResult
    info: dict = field(default_factory=dict)
    transit_times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    transit_delta: np.ndarray = field(default_factory=lambda: np.zeros(0))
    state_path: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int32))
    h2mm: dict = field(default_factory=dict)

    def report(self) -> str:
        """Return a human-readable summary of the run."""
        lines: list[str] = []
        n = self.fit.rate_matrix.shape[0]
        lines.append(
            f"{self.info.get('n_bursts', self.fit.n_bursts)} bursts, "
            f"{self.fit.n_photons:,} photons, {n} states"
        )
        lines.append("")
        lines.append("Rates (s^-1):")
        for source in range(n):
            for target in range(n):
                if source == target:
                    continue
                lines.append(
                    f"  k({source + 1} -> {target + 1}) = "
                    f"{self.fit.rate_matrix[target, source]:>12,.1f}"
                )
        if self.fit.efficiencies.size:
            lines.append("")
            lines.append("FRET efficiencies:")
            for i, e in enumerate(self.fit.efficiencies):
                lines.append(f"  E({i + 1}) = {e:.4f}")
        if self.fit.relaxation_times.size:
            lines.append("")
            times = ", ".join(f"{t * 1e6:,.1f} us" for t in self.fit.relaxation_times)
            lines.append(f"Relaxation time(s): {times}")
        lines.append("")
        lines.append(f"logL = {self.fit.log_likelihood:,.2f}")
        lines.append(f"BIC  = {self.fit.bic:,.2f}   AIC = {self.fit.aic:,.2f}")
        if not self.fit.success:
            lines.append(f"Optimiser did not converge: {self.fit.message}")

        if self.transit_times.size:
            best = int(np.nanargmax(self.transit_delta))
            gain = float(self.transit_delta[best])
            lines.append("")
            lines.append("Transition-time scan:")
            if gain < 2.0:
                lines.append(
                    "  No support for a finite transition time. The scan bounds it "
                    f"below ~{self.transit_times[best] * 1e6:,.2f} us; a crossing faster "
                    "than the photon rate is invisible, so read this as an upper limit."
                )
            else:
                lines.append(
                    f"  Best at {self.transit_times[best] * 1e6:,.2f} us, "
                    f"gaining {gain:,.1f} log units over the instantaneous model."
                )
        if self.h2mm:
            lines.append("")
            lines.append("H2MM cross-check (discrete time, independent engine):")
            for key, value in self.h2mm.items():
                if isinstance(value, float):
                    lines.append(f"  {key}: {value:,.4g}")
                else:
                    lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Return a JSON-compatible summary of the whole run."""
        return {
            "fit": self.fit.to_dict(),
            "info": dict(self.info),
            "transit_times": np.asarray(self.transit_times, dtype=float).tolist(),
            "transit_delta": np.asarray(self.transit_delta, dtype=float).tolist(),
            "h2mm": dict(self.h2mm),
            "report": self.report(),
        }


def analyse(
    bursts: gs.PhotonBursts,
    n_states: int = 2,
    initial_rates=None,
    initial_efficiencies=None,
    fix_efficiencies: bool = False,
    method: str = "nelder-mead",
    max_iterations: int = 2000,
    scan_transition_time: bool = False,
    transit_points: int = 40,
    decode_states: bool = False,
    cross_check_h2mm: bool = False,
    info: dict | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> GsAnalysis:
    """Fit a kinetic scheme to coloured photons and run the optional extras.

    Parameters
    ----------
    bursts : PhotonBursts
        Two-colour photons with arrival times in seconds.
    n_states : int
        Number of kinetic states.
    initial_rates, initial_efficiencies : array_like, optional
        Starting values; see :func:`chisurf.core.fluorescence.burst.gopich_szabo.fit`.
    fix_efficiencies : bool
        Hold the efficiencies fixed and fit only rates.
    method : str
        Optimiser, ``"nelder-mead"`` or ``"l-bfgs-b"``.
    max_iterations : int
        Optimiser iteration cap.
    scan_transition_time : bool
        Also scan the log-likelihood against a finite transition duration. Two
        states only — the transition-state construction is defined for a single
        barrier.
    transit_points : int
        Points in that scan.
    decode_states : bool
        Also compute the Viterbi state path.
    cross_check_h2mm : bool
        Also fit the same photons with the discrete-time H2MM engine and report
        the comparison. This is the sharpest available check on either result.
    info : dict, optional
        Provenance carried into the result.
    progress : callable, optional
        ``progress(fraction, message)``.

    Returns
    -------
    GsAnalysis
    """
    if progress is not None:
        progress(0.02, "fitting")
    fit = gs.fit(
        bursts,
        n_states=int(n_states),
        initial_rates=initial_rates,
        initial_efficiencies=initial_efficiencies,
        fix_efficiencies=bool(fix_efficiencies),
        method=method,
        max_iterations=int(max_iterations),
        progress=(lambda f, t: progress(0.02 + 0.6 * f, t)) if progress else None,
    )
    result = GsAnalysis(fit=fit, info=dict(info or {}))

    if scan_transition_time:
        if int(n_states) != 2:
            result.info["transition_scan_skipped"] = (
                "the transition-state model is defined for two states only"
            )
        else:
            if progress is not None:
                progress(0.65, "scanning transition time")
            times, delta, _ = gs.transition_time_scan(
                bursts,
                float(fit.rate_matrix[1, 0]),
                float(fit.rate_matrix[0, 1]),
                fit.efficiencies,
                transit_times=np.logspace(-6.0, -3.0, int(transit_points)),
            )
            result.transit_times = times
            result.transit_delta = delta

    if decode_states:
        if progress is not None:
            progress(0.85, "decoding states")
        result.state_path = gs.viterbi(
            bursts, fit.rate_matrix, gs.emission_from_efficiencies(fit.efficiencies)
        )

    if cross_check_h2mm:
        if progress is not None:
            progress(0.92, "cross-checking against H2MM")
        result.h2mm = compare_with_h2mm(bursts, fit, n_states=int(n_states))

    if progress is not None:
        progress(1.0, "done")
    return result


#: Default ceiling on the H2MM propagator cache. 256 MB is comfortably below
#: what a laptop can spare and far below where swapping starts.
H2MM_MEMORY_BUDGET = 256 * 1024 * 1024


def choose_h2mm_tick(
    gaps,
    relaxation_times,
    n_states: int = 2,
    tick: float | None = None,
    memory_budget_bytes: int = H2MM_MEMORY_BUDGET,
):
    """Pick a discrete-time tick that resolves the kinetics without exhausting RAM.

    H2MM caches one propagator **and one rho tensor per distinct inter-photon
    gap**, and the rho tensor is ``n_states**4`` doubles. The number of distinct
    gaps is set by the tick: make it small enough and every gap in the dataset
    rounds to its own integer, so the cache grows as
    ``n_photons * n_states**4 * 8 * 2`` bytes. At five states and a million
    photons that is five gigabytes — allocated in one go, with no warning, from
    a *derived* parameter the user never set.

    That is not hypothetical: the natural choice of tick (a fortieth of the
    fitted relaxation time) becomes arbitrarily small whenever a fit wanders
    towards fast rates, which is exactly what an optimiser does while it is
    still searching. So the tick is chosen for resolution and then **coarsened
    until the cache fits**, which costs a little time resolution and prevents
    the machine from swapping itself to death.

    Parameters
    ----------
    gaps : array_like
        Within-burst inter-photon gaps in seconds.
    relaxation_times : array_like
        Fitted relaxation times in seconds; the fastest sets the resolution
        target. Empty falls back to 100 µs.
    n_states : int
        Number of H2MM states — the cache grows as its fourth power.
    tick : float, optional
        Requested tick in seconds. Still coarsened if it breaks the budget.
    memory_budget_bytes : int
        Ceiling on the estimated cache size.

    Returns
    -------
    tick : float
        The tick to use, in seconds.
    note : str
        Empty when the requested tick was kept, otherwise an explanation of the
        coarsening — which belongs in the report, because a coarsened tick is a
        real limit on what the cross-check can resolve.

    Raises
    ------
    ValueError
        If *tick* is not a positive duration, or there are no usable gaps.
    """
    gaps = np.asarray(gaps, dtype=float)
    gaps = gaps[np.isfinite(gaps) & (gaps > 0.0)]
    if gaps.size == 0:
        raise ValueError("there are no positive inter-photon gaps to discretise")

    if tick is None:
        relaxation_times = np.asarray(relaxation_times, dtype=float)
        relaxation_times = relaxation_times[
            np.isfinite(relaxation_times) & (relaxation_times > 0.0)
        ]
        fastest = float(relaxation_times.min()) if relaxation_times.size else 1e-4
        tick = fastest / 40.0
    tick = float(tick)
    if not np.isfinite(tick) or tick <= 0.0:
        # A non-positive tick still produces a monotone integer sequence, so
        # H2MM fits it happily and returns rates with the wrong sign. Refuse
        # rather than hand back confident nonsense.
        raise ValueError(f"the tick must be a positive duration in seconds, got {tick}")

    # Two float64 caches per distinct gap: the propagator (n^2) and rho (n^4).
    per_slot = 8.0 * (n_states**2 + n_states**4)
    max_slots = max(int(memory_budget_bytes / per_slot), 16)

    requested = tick
    for _ in range(64):
        # Distinct gaps cannot exceed the photon count, whatever the tick.
        slots = min(np.unique(np.round(gaps / tick)).size, gaps.size)
        if slots <= max_slots:
            break
        # Grow geometrically towards the budget rather than one step at a time.
        tick *= max(2.0, float(slots) / max_slots)
    else:  # pragma: no cover - 64 doublings exceed any real dynamic range
        raise ValueError("no tick keeps the H2MM propagator cache inside the budget")

    if tick > requested * 1.000001:
        note = (
            f"tick coarsened from {requested * 1e9:,.3g} ns to {tick * 1e9:,.3g} ns "
            f"to keep the H2MM cache under "
            f"{memory_budget_bytes / (1024 * 1024):,.0f} MB; the cross-check "
            "therefore resolves less than the continuous-time fit does"
        )
        return tick, note
    return tick, ""


def compare_with_h2mm(
    bursts: gs.PhotonBursts,
    fit: gs.GsFitResult,
    n_states: int = 2,
    tick: float | None = None,
    memory_budget_bytes: int = H2MM_MEMORY_BUDGET,
) -> dict:
    """Fit the same photons with H2MM and compare the two answers.

    The two methods share no code and parameterise time differently — H2MM
    fits a per-tick transition **probability**, this module a **rate** — so
    agreement is real evidence and disagreement is a warning worth acting on.

    The comparison needs a tick, since H2MM is discrete-time. It is chosen as
    a fortieth of the fastest fitted relaxation time — fine enough to resolve
    the kinetics — and then **coarsened if necessary to stay inside a memory
    budget**; see :func:`choose_h2mm_tick` for why that second step is not
    optional.

    Parameters
    ----------
    bursts : PhotonBursts
        The same photons that were fitted.
    fit : gopich_szabo.GsFitResult
        The continuous-time fit to compare against.
    n_states : int
        Number of states for the H2MM fit.
    tick : float, optional
        Tick period in seconds; derived from *fit* when omitted. Passed
        explicitly it is used as given, but still checked against the budget.
    memory_budget_bytes : int
        Ceiling on the propagator cache; see :func:`choose_h2mm_tick`.

    Returns
    -------
    dict
        Rates, efficiencies and the ratio between the two, or ``{"error": ...}``
        when the comparison could not be made. Never raises: a cross-check that
        fails must not take the fit down with it.
    """
    try:
        # `fit_states` from `.engines`, not `.h2mm`: the latter is the
        # fallback engine and would run here even where the C++ one is
        # available. `prepare_bursts` is a data structure, not compute.
        from chisurf.plugins.burst.burst_h2mm.core.engines import fit_states
        from chisurf.plugins.burst.burst_h2mm.core.h2mm import prepare_bursts
    except Exception as exc:  # pragma: no cover - H2MM plugin missing
        return {"error": f"the H2MM engine is unavailable: {exc}"}

    try:
        gaps = np.diff(bursts.times)
        # Only within-burst gaps are real; the step across a burst boundary is not.
        within = np.ones(gaps.shape, dtype=bool)
        within[bursts.offsets[1:-1] - 1] = False
        gaps = gaps[within & (gaps > 0)]

        tick, budget_note = choose_h2mm_tick(
            gaps,
            fit.relaxation_times,
            n_states=int(n_states),
            tick=tick,
            memory_budget_bytes=int(memory_budget_bytes),
        )

        times, colors = [], []
        for b in range(len(bursts)):
            start = int(bursts.offsets[b])
            stop = int(bursts.offsets[b + 1])
            ticks = np.round(bursts.times[start:stop] / tick).astype(np.int64)
            # A tick cannot hold two photons in a discrete-time model.
            ticks = np.maximum.accumulate(ticks)
            ticks[1:] = np.where(ticks[1:] <= ticks[:-1], ticks[:-1] + 1, ticks[1:])
            times.append(ticks)
            colors.append(bursts.colors[start:stop].astype(np.int32))

        data = prepare_bursts(times, colors, n_streams=bursts.n_colors)
        model = fit_states(data, n_states=int(n_states), n_restarts=1, max_iter=300)

        # trans is a per-tick probability matrix, [source, target]; the rate is
        # the off-diagonal probability divided by the tick.
        rates = np.asarray(model.trans, dtype=float) / tick
        efficiencies = np.asarray(model.obs, dtype=float)[:, 1]
        order = np.argsort(efficiencies)
        efficiencies = efficiencies[order]
        rates = rates[np.ix_(order, order)]

        ours = np.sort(fit.efficiencies)
        out = {
            "tick_s": tick,
            **({"note": budget_note} if budget_note else {}),
            "h2mm_efficiencies": efficiencies.tolist(),
            "gs_efficiencies": ours.tolist(),
            "max_efficiency_difference": float(np.max(np.abs(efficiencies - ours))),
        }
        if int(n_states) == 2:
            out["h2mm_k12"] = float(rates[0, 1])
            out["h2mm_k21"] = float(rates[1, 0])
            gs_order = np.argsort(fit.efficiencies)
            matrix = fit.rate_matrix[np.ix_(gs_order, gs_order)]
            out["gs_k12"] = float(matrix[1, 0])
            out["gs_k21"] = float(matrix[0, 1])
            for key in ("k12", "k21"):
                theirs = out[f"h2mm_{key}"]
                mine = out[f"gs_{key}"]
                out[f"ratio_{key}"] = float(theirs / mine) if mine else float("nan")
        return out
    except Exception as exc:
        return {"error": f"the H2MM cross-check failed: {exc}"}


def write_container(
    source: str | pathlib.Path,
    analysis: GsAnalysis,
    *,
    parameters: dict | None = None,
    out_dir: str | pathlib.Path | None = None,
) -> str:
    """Write a Gopich–Szabo kinetic fit into the measurement's container.

    Three grains, because a kinetic fit genuinely has three. A FRET efficiency
    belongs to a *state*; a rate belongs to a *pair* of states; a Viterbi label
    belongs to a *photon*. The CSV export flattens all of them into
    ``quantity,value`` rows named ``k_12_per_s`` and ``E_1`` — readable, and not
    a table anything can join, sort or plot.

    Parameters
    ----------
    source : str or pathlib.Path
        The instrument file, or the container itself.
    analysis : GsAnalysis
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
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    fit = analysis.fit
    efficiencies = np.atleast_1d(np.asarray(fit.efficiencies, dtype=float))
    n = int(fit.rate_matrix.shape[0])

    # The goodness-of-fit numbers describe the whole model, so they repeat down
    # the state table rather than living in a header nothing can query.
    states = {
        "State": np.arange(n, dtype=np.int32),
        "E": (efficiencies if efficiencies.size == n else np.full(n, float("nan"))),
        "log_likelihood": np.full(n, float(fit.log_likelihood)),
        "bic": np.full(n, float(fit.bic)),
        "aic": np.full(n, float(fit.aic)),
    }
    written = write_burst_artifact(
        source,
        store_from_arrays(states),
        name="gs states",
        artifact_kind="fit_result",
        operation_type="model_fitting",
        row_grain="state",
        parameters=parameters,
        derived_from="bursts",
        units={
            "State": "dimensionless",
            "E": "dimensionless",
            "log_likelihood": "dimensionless",
            "bic": "dimensionless",
            "aic": "dimensionless",
        },
        out_dir=out_dir,
    )

    # K[target, source] -- the column convention the kinetics module uses, and
    # the one worth naming here because the transpose is silently plausible.
    pairs = [(s, t) for s in range(n) for t in range(n) if s != t]
    if pairs:
        write_burst_artifact(
            source,
            store_from_arrays(
                {
                    "From": np.array([s for s, _ in pairs], dtype=np.int32),
                    "To": np.array([t for _, t in pairs], dtype=np.int32),
                    "k": np.array([float(fit.rate_matrix[t, s]) for s, t in pairs], dtype=float),
                }
            ),
            name="gs rates",
            artifact_kind="parameter_table",
            operation_type="model_fitting",
            row_grain="pair",
            parameters=parameters,
            derived_from="gs states",
            source_row_column="State",
            target_row_column="From",
            units={"From": "dimensionless", "To": "dimensionless", "k": "hertz"},
            out_dir=out_dir,
        )

    path = np.asarray(analysis.state_path)
    if path.size:
        write_burst_artifact(
            source,
            store_from_arrays({"State": path.astype(np.int32)}),
            name="gs state path",
            artifact_kind="state_trajectory",
            operation_type="model_fitting",
            row_grain="photon",
            parameters=parameters,
            derived_from="gs states",
            units={"State": "dimensionless"},
            out_dir=out_dir,
        )
    return written
