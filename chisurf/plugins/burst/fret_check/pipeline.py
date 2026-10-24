"""Basic smFRET processing: photon streams, burst search, burst table, E/S.

The heavy lifting is tttrlib's (burst search, apparent and accurate E/S, 2CDE);
this module only routes photons into the streams of the detected
:class:`~chisurf.plugins.burst.fret_check.detect.Experiment` and reduces them per burst.

Streams (Dex/Aex = donor/acceptor excitation, Dem/Aem = emission)::

    DD  Dex Dem    DA  Dex Aem    AA  Aex Aem    (AD Aex Dem: dropped)

Without alternation every photon is under donor excitation and AA is empty.
"""
from __future__ import annotations

import dataclasses

import numpy as np

from .detect import Experiment

__all__ = ["BurstSettings", "Bursts", "photon_streams", "find_bursts", "analyse"]

STREAMS = ("DD", "DA", "AA")


@dataclasses.dataclass
class BurstSettings:
    """All-photon sliding-window burst search (Eggeling/Seidel, Nir et al.)."""

    algorithm: str = "sliding_window"
    #: Minimum photons per burst.
    min_photons: int = 30
    #: m photons ...
    m: int = 10
    #: ... within T seconds.
    T: float = 500e-6
    #: Two-channel-kernel width for FRET-/ALEX-2CDE, seconds.
    cde_tau: float = 100e-6


@dataclasses.dataclass
class Bursts:
    """The burst table: one entry per burst, all arrays of equal length."""

    start: np.ndarray  # first photon index
    stop: np.ndarray  # last photon index (inclusive)
    t_start: np.ndarray  # s
    duration: np.ndarray  # s
    counts: dict[str, np.ndarray]  # per stream
    background: dict[str, float]  # counts/s per stream, outside bursts
    E: np.ndarray
    S: np.ndarray | None
    fret_2cde: np.ndarray | None = None
    alex_2cde: np.ndarray | None = None
    #: Further per-burst columns under ChiSurf/Seidel ``.bur`` names
    #: (per-detector counts, anisotropies, lifetimes, TGX-TRR, ...).
    extra: dict = dataclasses.field(default_factory=dict)

    @property
    def n(self) -> int:
        return int(self.start.size)

    @property
    def size(self) -> np.ndarray:
        return sum(self.counts.values())

    @property
    def count_rate(self) -> np.ndarray:
        """Photons per second inside the burst (kHz × 1e3)."""
        return self.size / np.maximum(self.duration, 1e-9)

    def columns(self) -> dict[str, np.ndarray]:
        """The burst table under ChiSurf/Seidel ``.bur`` names (ndX's defaults)."""
        n_green = self.counts["DD"] + self.counts["DA"]
        cols = {
            "Mean Macro Time (ms)": (self.t_start + 0.5 * self.duration) * 1e3,
            "Duration (ms)": self.duration * 1e3,
            "Number of Photons": self.size,
            "Count Rate (KHz)": self.count_rate * 1e-3,
            "Number of Photons (green)": self.counts["DD"],
            "Number of Photons (red)": self.counts["DA"],
            "Green Count Rate (KHz)": self.counts["DD"] / np.maximum(self.duration, 1e-9) * 1e-3,
            "Red Count Rate (KHz)": self.counts["DA"] / np.maximum(self.duration, 1e-9) * 1e-3,
            "Proximity ratio": self.E,
        }
        if "AA" in self.counts:
            cols["Number of Photons (yellow)"] = self.counts["AA"]
            cols["Yellow Count Rate (KHz)"] = self.counts["AA"] / np.maximum(self.duration, 1e-9) * 1e-3
        if self.S is not None:
            cols["Stoichiometry"] = self.S
        if self.fret_2cde is not None:
            cols["FRET-2CDE"] = self.fret_2cde
        if self.alex_2cde is not None:
            cols["ALEX-2CDE"] = self.alex_2cde
        cols.update(self.extra)
        cols["First Photon"] = self.start.astype(float)
        cols["Last Photon"] = self.stop.astype(float)
        del n_green
        return cols


def photon_streams(data, exp: Experiment) -> np.ndarray:
    """A per-photon stream index: 0 DD, 1 DA, 2 AA, -1 not used."""
    routing = np.asarray(data.routing_channels)
    micro = np.asarray(data.micro_times)
    if exp.alex_period and (micro.size == 0 or int(micro.max()) < 1):
        # µsALEX kept only in the macro time: the phase is the micro time.
        micro = np.asarray(data.macro_times).astype(np.int64) % int(exp.alex_period)
    donor = np.isin(routing, exp.donor_channels)
    acceptor = np.isin(routing, exp.acceptor_channels)
    stream = np.full(routing.size, -1, np.int8)
    if exp.excitation == "alternating" and exp.windows:
        win = {w.name: w for w in exp.windows}
        dex = (micro >= win["donor"].start) & (micro < win["donor"].stop)
        aex = (micro >= win["acceptor"].start) & (micro < win["acceptor"].stop)
        stream[donor & dex] = 0
        stream[acceptor & dex] = 1
        stream[acceptor & aex] = 2
    else:
        stream[donor] = 0
        stream[acceptor] = 1
    return stream


def _merge(intervals: np.ndarray) -> np.ndarray:
    """Merge overlapping / touching ``[start, stop]`` photon intervals."""
    if intervals.size == 0:
        return intervals.reshape(0, 2)
    order = np.argsort(intervals[:, 0], kind="stable")
    iv = intervals[order]
    run_max = np.maximum.accumulate(iv[:, 1])
    new = np.ones(len(iv), bool)
    new[1:] = iv[1:, 0] > run_max[:-1]
    group = np.cumsum(new) - 1
    starts = iv[new, 0]
    stops = np.zeros(group[-1] + 1, iv.dtype)
    np.maximum.at(stops, group, iv[:, 1])
    return np.stack([starts, stops], axis=1)


def find_bursts(data, settings: BurstSettings) -> np.ndarray:
    """Burst photon ranges ``(n, 2)``, inclusive, merged and size-filtered."""
    raw = np.asarray(
        data.burst_search(L=settings.min_photons, m=settings.m, T=settings.T, mode=settings.algorithm)
    ).reshape(-1, 2)
    merged = _merge(raw.astype(np.int64))
    keep = (merged[:, 1] - merged[:, 0] + 1) >= settings.min_photons
    return merged[keep]


def _background(stream, macro_s, bursts, duration_s) -> dict[str, float]:
    """Counts/s per stream outside the bursts."""
    inside = np.zeros(stream.size + 1, np.int64)
    np.add.at(inside, bursts[:, 0], 1)
    np.add.at(inside, bursts[:, 1] + 1, -1)
    in_burst = np.cumsum(inside)[:-1] > 0
    t_bursts = float(np.sum(macro_s[bursts[:, 1]] - macro_s[bursts[:, 0]])) if bursts.size else 0.0
    t_out = max(duration_s - t_bursts, 1e-9)
    return {k: float(np.sum((stream == i) & ~in_burst)) / t_out for i, k in enumerate(STREAMS)}


#: 2CDE kernel reach in units of tau: tttrlib's Laplace window is 5 tau
#: (Gaussian 3 tau); a little more makes the burst neighbourhoods exact.
CDE_REACH = 6.0


def _near_bursts(data, bursts, tau):
    """``(subset, bursts_in_subset)``: only the photons a burst's 2CDE can see.

    A burst photon's kernel densities depend on photons within the kernel's
    reach (:data:`CDE_REACH` x tau), so the photons within that reach of any
    burst give the same 2CDE as the whole stream -- typically a tenth of it.
    Returns ``(data, bursts)`` unchanged when that would not save much.
    """
    import tttrlib  # noqa: PLC0415

    macro = np.asarray(data.macro_times)
    res = float(data.header.macro_time_resolution)
    reach = int(np.ceil(CDE_REACH * tau / res))
    lo = np.searchsorted(macro, macro[bursts[:, 0]].astype(np.int64) - reach, side="left")
    hi = np.searchsorted(macro, macro[bursts[:, 1]].astype(np.int64) + reach, side="right")
    marks = np.zeros(macro.size + 1, np.int64)
    np.add.at(marks, lo, 1)
    np.add.at(marks, hi, -1)
    idx = np.flatnonzero(np.cumsum(marks)[:-1] > 0)
    if idx.size > 0.7 * macro.size:
        return data, bursts
    subset = tttrlib.TTTR(np.ascontiguousarray(macro[idx], np.uint64),
                          np.ascontiguousarray(np.asarray(data.micro_times)[idx], np.uint16),
                          np.ascontiguousarray(np.asarray(data.routing_channels)[idx], np.int8),
                          np.ascontiguousarray(np.asarray(data.event_types)[idx], np.int8))
    subset.header.set_macro_time_resolution(res)
    subset.header.set_micro_time_resolution(float(data.header.micro_time_resolution))
    remapped = np.stack([np.searchsorted(idx, bursts[:, 0]), np.searchsorted(idx, bursts[:, 1])], axis=1)
    return subset, remapped.astype(np.int64)


def _two_cde(data, exp, bursts, tau):
    import tttrlib  # noqa: PLC0415

    fret = alex = None
    if bursts.size == 0:
        return fret, alex
    data, bursts = _near_bursts(data, bursts, tau)
    try:
        two = tttrlib.TwoCDE(data)
        if exp.excitation == "alternating" and exp.windows:
            win = {w.name: w for w in exp.windows}
            d = [[win["donor"].start, win["donor"].stop]]
            two.set_donor(exp.donor_channels, d)
            two.set_acceptor(exp.acceptor_channels, d)
        else:
            two.set_donor(exp.donor_channels)
            two.set_acceptor(exp.acceptor_channels)
        two.compute(bursts, tau, tttrlib.TwoCDE.FRET_2CDE, tttrlib.TwoCDE.LAPLACE)
        fret = np.asarray(two.get_two_cde(), float).copy()
        if exp.excitation == "alternating" and exp.windows:
            two = tttrlib.TwoCDE(data)
            win = {w.name: w for w in exp.windows}
            chans = exp.donor_channels + exp.acceptor_channels
            two.set_donor_excitation(chans, [[win["donor"].start, win["donor"].stop]])
            two.set_acceptor_excitation(exp.acceptor_channels, [[win["acceptor"].start, win["acceptor"].stop]])
            two.compute(bursts, tau, tttrlib.TwoCDE.ALEX_2CDE, tttrlib.TwoCDE.LAPLACE)
            alex = np.asarray(two.get_two_cde(), float).copy()
    except (TypeError, ValueError, RuntimeError, NotImplementedError):
        # 2CDE is a QC extra; a binding mismatch must not stop the analysis.
        pass
    return fret, alex


def _burst_sum(values, bursts):
    """Per-burst sums of a per-photon array (inclusive photon ranges)."""
    c = np.concatenate([[0.0], np.cumsum(values, dtype=np.float64)])
    return c[bursts[:, 1] + 1] - c[bursts[:, 0]]


def _half_rise(micro, n_bins=512):
    """Micro-time channel where a decay first reaches half its maximum: the
    IRF offset tttrlib's ``get_decay_irf_offset`` uses."""
    if micro.size < 100:
        return 0.0
    hi = int(micro.max()) + 1
    h, edges = np.histogram(micro, bins=min(n_bins, hi), range=(0, hi))
    k = int(np.argmax(h >= 0.5 * h.max()))
    return float(edges[k])


def burst_details(data, exp: Experiment, stream, bursts, macro_s, g_factor=1.0, irf_offsets=None):
    """Per-detector counts, anisotropies, mean-arrival lifetimes and TGX-TRR.

    Lifetimes are the mean arrival time of each stream's burst photons after
    the half-rise of that stream's whole decay -- a model-free estimate that
    needs no IRF file (``Tau (green)``: DD, ``Tau (yellow)``: AA). They are
    only computed with a TCSPC micro time (not for µsALEX, whose micro time
    is the alternation phase).
    """
    routing = np.asarray(data.routing_channels)
    micro = np.asarray(data.micro_times).astype(np.float64)
    extra = {}
    dur = np.maximum(macro_s[bursts[:, 1]] - macro_s[bursts[:, 0]], 1e-12)
    # Per detector, per excitation.
    for c in exp.donor_channels + exp.acceptor_channels:
        on = routing == c
        extra[f"Number of Photons (ch {c})"] = _burst_sum(on & (stream >= 0), bursts)
    # Anisotropies (G factor, no l1/l2 or background correction).
    if exp.polarization:
        for label, (par, perp), stream_ids in (("green", exp.donor_pol, (0,)),
                                               ("red", exp.acceptor_pol, (2,) if exp.excitation == "alternating" else (1,))):
            sel = np.isin(stream, stream_ids)
            i_par = _burst_sum(sel & (routing == par), bursts)
            i_perp = _burst_sum(sel & (routing == perp), bursts)
            den = i_par + 2.0 * g_factor * i_perp
            extra[f"r Experimental ({label})"] = np.divide(i_par - g_factor * i_perp, den,
                                                           out=np.full(den.shape, np.nan), where=den > 0)
    # Lifetimes from the mean arrival time.
    tcspc = exp.micro_time_resolution_s > 0 and exp.micro_time_resolution_s < 1e-9 and not exp.alex_period
    if tcspc:
        dt_ns = exp.micro_time_resolution_s * 1e9
        for label, sid in (("green", 0), ("yellow", 2)):
            sel = stream == sid
            if not sel.any():
                continue
            # The decay's half-rise; a chunked analysis fixes it once
            # (``irf_offsets``) so every chunk measures from the same point.
            if irf_offsets is not None and label in irf_offsets:
                offset = irf_offsets[label]
            else:
                offset = _half_rise(micro[sel])
                if irf_offsets is not None:
                    irf_offsets[label] = offset
            n = _burst_sum(sel, bursts)
            mean = np.divide(_burst_sum(np.where(sel, micro, 0.0), bursts), n, out=np.full(n.shape, np.nan),
                             where=n > 0)
            extra[f"Tau ({label})"] = (mean - offset) * dt_ns
    # TGX-TRR: mean macro time of donor-excited minus acceptor-excited photons
    # (bleaching/blinking of one dye shifts it away from 0).
    if exp.excitation == "alternating":
        g = (stream == 0) | (stream == 1)
        r = stream == 2
        ng, nr = _burst_sum(g, bursts), _burst_sum(r, bursts)
        tg = np.divide(_burst_sum(np.where(g, macro_s, 0.0), bursts), ng, out=np.full(ng.shape, np.nan), where=ng > 0)
        tr = np.divide(_burst_sum(np.where(r, macro_s, 0.0), bursts), nr, out=np.full(nr.shape, np.nan), where=nr > 0)
        extra["TGX-TRR"] = (tg - tr) * 1e3  # ms
        extra["|TGX-TRR| / Duration"] = np.abs(tg - tr) / dur
    return extra


def analyse(data, exp: Experiment, settings: BurstSettings | None = None, progress=None,
            irf_offsets: dict | None = None) -> Bursts:
    """Burst search and the per-burst table for one measurement.

    ``progress(fraction, message)``, when given, hears each stage.
    ``irf_offsets``: a dict shared across the chunks of one file -- the first
    chunk fills in each decay's half-rise, the others use it.
    """
    import tttrlib  # noqa: PLC0415

    say = progress or (lambda fraction, message: None)
    settings = settings or BurstSettings()
    say(0.0, "photon streams")
    stream = photon_streams(data, exp)
    macro_s = np.asarray(data.macro_times, dtype=np.float64) * exp.macro_time_resolution_s
    say(0.1, "burst search")
    bursts = find_bursts(data, settings)
    say(0.3, f"{len(bursts)} bursts: counting photons")

    counts = {}
    for i, k in enumerate(STREAMS):
        c = np.concatenate([[0], np.cumsum(stream == i)])
        counts[k] = (c[bursts[:, 1] + 1] - c[bursts[:, 0]]).astype(float)
    alternating = exp.excitation == "alternating"
    if not alternating:
        counts.pop("AA")
    es = tttrlib.apparent_es(counts["DD"], counts["DA"], counts["AA"] if alternating else None)
    say(0.4, "FRET-2CDE / ALEX-2CDE")
    fret, alex = _two_cde(data, exp, bursts, settings.cde_tau)
    say(0.85, "lifetimes, anisotropies, TGX-TRR")
    return Bursts(
        start=bursts[:, 0],
        stop=bursts[:, 1],
        t_start=macro_s[bursts[:, 0]] - (macro_s[0] if macro_s.size else 0.0),
        duration=macro_s[bursts[:, 1]] - macro_s[bursts[:, 0]],
        counts=counts,
        background=_background(stream, macro_s, bursts, exp.duration_s),
        E=np.asarray(es["E"], float),
        S=np.asarray(es["S"], float) if es.get("S") is not None else None,
        fret_2cde=fret,
        alex_2cde=alex,
        extra=burst_details(data, exp, stream, bursts, macro_s, irf_offsets=irf_offsets),
    )
