"""Live PIE burst analysis: photons in, bursts with E and S and the accumulators the view draws.

The contract is the live part of the [live-recording spec](okf/specs/live-recording.md), "Live PIE
analysis". Per batch of photons:

1. each photon is assigned a class from the Instrument setup -- DD (donor detector, prompt
   window), DA (acceptor detector, prompt), AA (acceptor detector, delay) or other;
2. bursts are searched with tttrlib's ``StreamingBurstDetector``: the sliding-window rule (``m``
   photons within ``T``, at least ``L`` photons), photon for photon the same as the offline
   ``TTTR.burst_search`` that burst selection runs, with an open burst carried across batches;
3. each finished burst is counted into DD/DA/AA; background rates per class come from the photons
   outside bursts; E and S follow (raw, or corrected when the setup carries gamma, beta, alpha,
   delta -- Lee et al. 2005, [10.1529/biophysj.104.054114](https://doi.org/10.1529/biophysj.104.054114));
4. accumulators are updated: the 2-D E-S histogram, the burst count, a count-rate trace per
   class and a micro-time histogram per detector. The view redraws from these and never re-reads
   photons.

Displayed E and S use the background known when the burst closed. :meth:`PieBurstAnalyzer.results`
recomputes every burst with the final background, which is what the run stores and what
:func:`analyze_offline` -- the same rule over a whole file -- reproduces exactly.

tttrlib is adding a ``StreamingPieBurstAnalyzer`` with this contract; :func:`make_analyzer` uses it
when the installed tttrlib has it and this implementation otherwise (which stays as the test
oracle).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import tttrlib

__all__ = [
    "BurstParameters",
    "CLASS_NAMES",
    "PieBurstAnalyzer",
    "PieSetup",
    "analyze_offline",
    "classify",
    "make_analyzer",
]

#: Photon classes, in code order.
CLASS_NAMES = ("DD", "DA", "AA", "other")
DD, DA, AA, OTHER = 0, 1, 2, 3


@dataclass(frozen=True)
class PieSetup:
    """Which photons are DD, DA and AA, and the corrections if known.

    Attributes
    ----------
    donor_channels, acceptor_channels : tuple of int
        Routing channels of the donor (green) and acceptor (red) detectors.
    prompt, delay : (int, int)
        Micro-time channel ranges ``[lo, hi)`` of the donor- and acceptor-excitation windows.
    gamma, beta, alpha, delta : float or None
        Detection-efficiency ratio, excitation normalisation, donor leakage into the acceptor
        channel, acceptor direct excitation by the donor laser. ``None`` means not calibrated;
        E and S are then the raw (background-corrected) values.
    name : str
        Where the setup came from (the workspace row), for display.
    """

    donor_channels: tuple = (0,)
    acceptor_channels: tuple = (1,)
    prompt: tuple = (0, 2000)
    delay: tuple = (2000, 4000)
    gamma: float | None = None
    beta: float | None = None
    alpha: float | None = None
    delta: float | None = None
    name: str = ""

    @property
    def corrected(self) -> bool:
        return all(v is not None for v in (self.gamma, self.beta, self.alpha, self.delta))

    @classmethod
    def default_for(cls, n_micro: int, name: str = "default PIE (half periods)") -> PieSetup:
        """Donor channel 0, acceptor channel 1, the period split into two halves."""
        half = int(n_micro) // 2
        return cls(prompt=(0, half), delay=(half, int(n_micro)), name=name)

    @classmethod
    def from_setup(cls, setup: dict, name: str = "") -> PieSetup:
        """Read the shared channel-definition JSON (``windows``, ``detectors``), plain or under ``data``.

        The donor detector is the one named ``green``/``donor``, the acceptor ``red``/``acceptor``;
        the windows ``prompt`` and ``delayed``/``delay``. Corrections are read from ``corrections``
        (or top level) as ``gamma``, ``beta``, ``alpha``/``crosstalk``, ``delta``/``direct``.
        """
        data = setup.get("data", setup) if isinstance(setup, dict) else {}
        windows = data.get("windows") or {}
        detectors = data.get("detectors") or {}

        def detector(*names):
            for key, value in detectors.items():
                if str(key).lower() in names:
                    return tuple(int(c) for c in (value.get("chs") or value.get("channels") or ()))
            return None

        donor = detector("green", "donor", "d")
        acceptor = detector("red", "acceptor", "a")
        if not donor or not acceptor:
            raise ValueError("the setup names no green/donor and red/acceptor detectors")
        prompt = windows.get("prompt") or windows.get("donor")
        delay = windows.get("delayed") or windows.get("delay") or windows.get("acceptor")
        if not prompt or not delay:
            raise ValueError("the setup has no prompt and delay windows")
        corr = data.get("corrections") or data.get("fret") or data

        def value(*keys):
            for k in keys:
                if isinstance(corr, dict) and corr.get(k) is not None:
                    return float(corr[k])
            return None

        return cls(
            donor_channels=donor,
            acceptor_channels=acceptor,
            prompt=(int(prompt[0]), int(prompt[1])),
            delay=(int(delay[0]), int(delay[1])),
            gamma=value("gamma"),
            beta=value("beta"),
            alpha=value("alpha", "crosstalk", "leakage"),
            delta=value("delta", "direct", "direct_excitation"),
            name=name,
        )


@dataclass(frozen=True)
class BurstParameters:
    """The sliding-window burst criterion: ``window_photons`` within ``window_time_s``, at least
    ``min_photons`` photons. The same three numbers burst selection's search takes."""

    min_photons: int = 30
    window_photons: int = 10
    window_time_s: float = 5e-4


def classify(setup: PieSetup, micro: np.ndarray, channel: np.ndarray) -> np.ndarray:
    """Class code per photon (``DD``, ``DA``, ``AA``, ``OTHER``)."""
    micro = np.asarray(micro)
    channel = np.asarray(channel)
    donor = np.isin(channel, setup.donor_channels)
    acceptor = np.isin(channel, setup.acceptor_channels)
    prompt = (micro >= setup.prompt[0]) & (micro < setup.prompt[1])
    delay = (micro >= setup.delay[0]) & (micro < setup.delay[1])
    codes = np.full(len(micro), OTHER, dtype=np.uint8)
    codes[donor & prompt] = DD
    codes[acceptor & prompt] = DA
    codes[acceptor & delay] = AA
    return codes


def fret(setup: PieSetup, dd, da, aa) -> tuple[np.ndarray, np.ndarray]:
    """E and S from background-corrected DD, DA, AA (arrays); NaN where undefined."""
    dd = np.asarray(dd, dtype=float)
    da = np.asarray(da, dtype=float)
    aa = np.asarray(aa, dtype=float)
    if setup.corrected:
        g, b, a, d = setup.gamma, setup.beta, setup.alpha, setup.delta
        fa = da - a * dd - d * aa
        num_s = g * dd + fa
        den_e, den_s = num_s, num_s + aa / b
    else:
        fa = da
        num_s = dd + da
        den_e, den_s = num_s, num_s + aa
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(den_e > 0, fa / den_e, np.nan)
        s = np.where(den_s > 0, num_s / den_s, np.nan)
    return e, s


#: Columns of a run's burst table, in order (the burst-selection names where one exists).
BURST_COLUMNS = (
    "First Photon",
    "Last Photon",
    "Duration (ms)",
    "Mean Macro Time (ms)",
    "Number of Photons",
    "Number of Photons (DD)",
    "Number of Photons (DA)",
    "Number of Photons (AA)",
    "Background (DD)",
    "Background (DA)",
    "Background (AA)",
    "E",
    "S",
)


@dataclass
class _Accumulators:
    e_edges: np.ndarray
    s_edges: np.ndarray
    es: np.ndarray
    rate_bin_s: float
    rate_t: deque = field(default_factory=lambda: deque(maxlen=600))
    rate: list = field(default_factory=lambda: [deque(maxlen=600) for _ in range(3)])
    decay_donor: np.ndarray | None = None
    decay_acceptor: np.ndarray | None = None


class PieBurstAnalyzer:
    """The live PIE analysis in Python: same contract as tttrlib's coming streaming class.

    Parameters
    ----------
    setup : PieSetup
    macro_clock_s : float
        Seconds per macro-time tick of the photons pushed.
    n_micro : int
        Micro-time channels per period (decay accumulators).
    burst : BurstParameters
    es_bins : int
        Bins per axis of the E-S histogram over ``[-0.1, 1.1]``.
    rate_bin_s : float
        Bin width of the count-rate trace.

    Notes
    -----
    Not thread-safe: one thread pushes; :meth:`snapshot` copies what the view needs.
    Memory is bounded: photons are kept only from the start of the last finished burst on (that
    burst, the gap since, and an open burst).
    """

    implementation = "python"

    def __init__(
        self,
        setup: PieSetup,
        macro_clock_s: float,
        n_micro: int,
        burst: BurstParameters = BurstParameters(),
        *,
        es_bins: int = 60,
        rate_bin_s: float = 0.1,
    ):
        self.setup = setup
        self.clock = float(macro_clock_s)
        self.n_micro = int(n_micro)
        self.params = burst
        self._detector = tttrlib.StreamingBurstDetector(
            int(burst.window_photons), float(burst.window_time_s), self.clock
        )
        self._detector.set_min_photons(int(burst.min_photons))
        edges = np.linspace(-0.1, 1.1, es_bins + 1)
        self.acc = _Accumulators(
            e_edges=edges,
            s_edges=edges.copy(),
            es=np.zeros((es_bins, es_bins), dtype=np.int64),
            rate_bin_s=float(rate_bin_s),
            decay_donor=np.zeros(self.n_micro, dtype=np.int64),
            decay_acceptor=np.zeros(self.n_micro, dtype=np.int64),
        )
        self.n_photons = 0
        self._base = 0  # global index of the first kept photon
        self._codes = np.zeros(0, dtype=np.uint8)
        self._macro = np.zeros(0, dtype=np.uint64)
        self._n_done = 0  # bursts already counted
        self.class_totals = np.zeros(3, dtype=np.int64)
        self.class_in_bursts = np.zeros(3, dtype=np.int64)
        self.burst_ticks = 0
        self.first_macro: int | None = None
        self.last_macro = 0
        self.bursts: list[tuple] = []  # (start, stop, t_start, t_stop, dd, da, aa)
        self.live_es: list[tuple] = []  # (E, S) as displayed
        self._rate_counts = np.zeros(3, dtype=np.int64)
        self._rate_next: float | None = None
        #: total photons per whole second of the run (the quality checker's stability trace)
        self._per_second = np.zeros(0, dtype=np.int64)

    # -- feeding ----------------------------------------------------------------------------
    def push(self, macro, micro, channel) -> int:
        """Add one batch (time ordered, after the previous one); returns the bursts it closed."""
        macro = np.asarray(macro, dtype=np.uint64)
        if len(macro) == 0:
            return 0
        micro = np.asarray(micro)
        channel = np.asarray(channel)
        codes = classify(self.setup, micro, channel)
        if self.first_macro is None:
            self.first_macro = int(macro[0])
        self.last_macro = int(macro[-1])
        self.n_photons += len(macro)
        self.class_totals += np.bincount(codes, minlength=4)[:3]
        self._update_decays(micro, channel)
        self._update_rates(macro, codes)
        self._update_seconds(macro)
        self._codes = np.concatenate([self._codes, codes])
        self._macro = np.concatenate([self._macro, macro])
        self._detector.push_np(macro)
        return self._collect()

    def finish(self) -> int:
        """Close an open burst at the end of the measurement; returns the bursts it closed."""
        self._detector.flush()
        return self._collect()

    def _collect(self) -> int:
        idx = np.asarray(self._detector.get_burst_indices(), dtype=np.int64).reshape(-1, 2)
        new = idx[self._n_done :]
        for start, stop in new:
            a, b = int(start) - self._base, int(stop) - self._base + 1
            counts = np.bincount(self._codes[a:b], minlength=4)
            t0, t1 = int(self._macro[a]), int(self._macro[b - 1])
            dd, da, aa = (int(c) for c in counts[:3])
            self.class_in_bursts += counts[:3]
            self.burst_ticks += t1 - t0
            self.bursts.append((int(start), int(stop), t0, t1, dd, da, aa))
            e, s = self._fret_one(t1 - t0, dd, da, aa)
            self.live_es.append((e, s))
            if math.isfinite(e) and math.isfinite(s):
                i = np.searchsorted(self.acc.e_edges, e, side="right") - 1
                j = np.searchsorted(self.acc.s_edges, s, side="right") - 1
                if 0 <= i < self.acc.es.shape[0] and 0 <= j < self.acc.es.shape[1]:
                    self.acc.es[i, j] += 1
        self._n_done = len(idx)
        if len(new):
            # The sliding-window search may start a burst a few photons before the previous one
            # ended (TTTR.burst_search does the same offline), but starts are ordered: keep from the
            # start of the last burst, not from its end.
            keep_from = int(new[-1][0]) - self._base
            self._codes = self._codes[keep_from:]
            self._macro = self._macro[keep_from:]
            self._base += keep_from
        return len(new)

    def _update_decays(self, micro, channel) -> None:
        micro = np.clip(np.asarray(micro, dtype=np.int64), 0, self.n_micro - 1)
        donor = np.isin(channel, self.setup.donor_channels)
        acceptor = np.isin(channel, self.setup.acceptor_channels)
        self.acc.decay_donor += np.bincount(micro[donor], minlength=self.n_micro)[: self.n_micro]
        self.acc.decay_acceptor += np.bincount(micro[acceptor], minlength=self.n_micro)[
            : self.n_micro
        ]

    def _update_rates(self, macro, codes) -> None:
        t = (macro.astype(np.float64) - float(self.first_macro)) * self.clock
        width = self.acc.rate_bin_s
        if self._rate_next is None:
            self._rate_next = width
        start = 0
        while start < len(t):
            end = int(np.searchsorted(t, self._rate_next, side="left"))
            self._rate_counts += np.bincount(codes[start:end], minlength=4)[:3]
            if end >= len(t):
                break
            self.acc.rate_t.append(self._rate_next)
            for k in range(3):
                self.acc.rate[k].append(self._rate_counts[k] / width / 1000.0)  # kHz
            self._rate_counts[:] = 0
            self._rate_next += width
            start = end

    def _update_seconds(self, macro) -> None:
        second = ((macro - np.uint64(self.first_macro)).astype(np.float64) * self.clock).astype(
            np.int64
        )
        counts = np.bincount(second)
        if counts.size > self._per_second.size:
            self._per_second = np.concatenate(
                [self._per_second, np.zeros(counts.size - self._per_second.size, dtype=np.int64)]
            )
        self._per_second[: counts.size] += counts

    def trace_1s(self) -> tuple[np.ndarray, np.ndarray]:
        """Total count rate in 1 s bins: bin centres (s) and kHz (the last bin is partial)."""
        n = self._per_second.size
        return (np.arange(n) + 0.5), self._per_second.astype(float) * 1e-3

    # -- background and FRET ------------------------------------------------------------------
    def background_rates(self) -> np.ndarray:
        """Per-class background rate (per macro tick) from the photons outside bursts."""
        if self.first_macro is None:
            return np.zeros(3)
        outside_ticks = (self.last_macro - self.first_macro) - self.burst_ticks
        if outside_ticks <= 0:
            return np.zeros(3)
        return (self.class_totals - self.class_in_bursts) / float(outside_ticks)

    def background_per_s(self) -> dict[str, float]:
        """Counts per second outside bursts, per stream (``DD``, ``DA``, ``AA``)."""
        rates = self.background_rates() / self.clock
        return {"DD": float(rates[0]), "DA": float(rates[1]), "AA": float(rates[2])}

    def _fret_one(self, ticks: int, dd: int, da: int, aa: int) -> tuple[float, float]:
        bg = self.background_rates() * ticks
        e, s = fret(self.setup, [dd - bg[0]], [da - bg[1]], [aa - bg[2]])
        return float(e[0]), float(s[0])

    # -- results ------------------------------------------------------------------------------
    @property
    def burst_count(self) -> int:
        return len(self.bursts)

    def elapsed_s(self) -> float:
        if self.first_macro is None:
            return 0.0
        return (self.last_macro - self.first_macro) * self.clock

    def results(self) -> dict[str, np.ndarray]:
        """The burst table (:data:`BURST_COLUMNS`), every burst with the final background."""
        return burst_table(self.setup, self.bursts, self.background_rates(), self.clock)

    def snapshot(self) -> dict[str, Any]:
        """Plain copies for the view (cheap: no photon arrays)."""
        es = self.acc.es.copy()
        return {
            "es": es,
            "e_edges": self.acc.e_edges,
            "s_edges": self.acc.s_edges,
            "e_marginal": es.sum(axis=1),
            "s_marginal": es.sum(axis=0),
            "burst_count": self.burst_count,
            "photons": self.n_photons,
            "elapsed_s": self.elapsed_s(),
            "burst_rate_hz": self.burst_count / self.elapsed_s() if self.elapsed_s() > 0 else 0.0,
            "rate_t": np.asarray(self.acc.rate_t, dtype=float),
            "rate": [np.asarray(r, dtype=float) for r in self.acc.rate],
            "decay_donor": self.acc.decay_donor.copy(),
            "decay_acceptor": self.acc.decay_acceptor.copy(),
            "background_khz": self.background_rates() / self.clock / 1000.0,
            "implementation": self.implementation,
        }


def burst_table(
    setup: PieSetup, bursts: Sequence[tuple], bg_rate: np.ndarray, clock: float
) -> dict:
    """Columns of :data:`BURST_COLUMNS` for *bursts* ``(start, stop, t0, t1, dd, da, aa)``."""
    b = np.asarray(bursts, dtype=np.float64).reshape(-1, 7)
    ticks = b[:, 3] - b[:, 2]
    bg = np.outer(ticks, np.asarray(bg_rate, dtype=float))
    e, s = fret(setup, b[:, 4] - bg[:, 0], b[:, 5] - bg[:, 1], b[:, 6] - bg[:, 2])
    return {
        "First Photon": b[:, 0].astype(np.int64),
        "Last Photon": b[:, 1].astype(np.int64),
        "Duration (ms)": ticks * clock * 1e3,
        "Mean Macro Time (ms)": (b[:, 2] + b[:, 3]) / 2.0 * clock * 1e3,
        "Number of Photons": (b[:, 1] - b[:, 0] + 1).astype(np.int64),
        "Number of Photons (DD)": b[:, 4].astype(np.int64),
        "Number of Photons (DA)": b[:, 5].astype(np.int64),
        "Number of Photons (AA)": b[:, 6].astype(np.int64),
        "Background (DD)": bg[:, 0],
        "Background (DA)": bg[:, 1],
        "Background (AA)": bg[:, 2],
        "E": e,
        "S": s,
    }


def analyze_offline(tttr, setup: PieSetup, burst: BurstParameters = BurstParameters()) -> dict:
    """The same analysis over a whole recorded file, written independently of the live path.

    Uses ``TTTR.burst_search`` (what burst selection runs) and whole-array counting; the guard test
    holds the live :meth:`PieBurstAnalyzer.results` equal to this.
    """
    macro = np.asarray(tttr.macro_times, dtype=np.int64)
    codes = classify(setup, np.asarray(tttr.micro_times), np.asarray(tttr.routing_channels))
    idx = np.asarray(
        tttr.burst_search(
            int(burst.min_photons), int(burst.window_photons), float(burst.window_time_s)
        )
    ).reshape(-1, 2)
    onehot = np.zeros((len(codes) + 1, 3), dtype=np.int64)
    for k in range(3):
        onehot[1:, k] = np.cumsum(codes == k)
    rows = []
    for start, stop in idx:
        counts = onehot[stop + 1] - onehot[start]
        rows.append((start, stop, macro[start], macro[stop], *counts))
    totals = onehot[-1]
    inside = np.sum([r[4:] for r in rows], axis=0) if rows else np.zeros(3)
    burst_ticks = sum(r[3] - r[2] for r in rows)
    outside = (macro[-1] - macro[0]) - burst_ticks if len(macro) else 0
    bg = (totals - inside) / float(outside) if outside > 0 else np.zeros(3)
    return burst_table(setup, rows, bg, float(tttr.header.macro_time_resolution))


def make_analyzer(
    setup: PieSetup, macro_clock_s: float, n_micro: int, burst: BurstParameters, **kw
):
    """tttrlib's ``StreamingPieBurstAnalyzer`` when the installed tttrlib has it, else Python.

    The tttrlib class is being added with this contract; until its Python binding is settled the
    adapter is the one thing to write here (the guard test compares both).
    """
    if hasattr(tttrlib, "StreamingPieBurstAnalyzer"):
        # FALLBACK (2026-10-26): wire tttrlib.StreamingPieBurstAnalyzer here once it is released;
        # until then the Python implementation is used even when the name exists.
        pass
    return PieBurstAnalyzer(setup, macro_clock_s, n_micro, burst, **kw)
