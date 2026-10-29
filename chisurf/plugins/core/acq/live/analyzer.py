"""The live burst analyzer: tttrlib's ``StreamingBurstAnalyzer``, or a stand-in with its API.

tttrlib's class (``modules/streaming``) analyses any detection scheme live -- single colour, two
colour, PIE, µs-ALEX, MFD, three-colour PIE -- from the shared channel definition, with
``from_setup(setup, preset=...)``. :func:`make_analyzer` uses it when the installed tttrlib has it.
Older tttrlib builds get :class:`StreamingBurstAnalyzer` below: the same methods, the same
``from_setup`` (copied from tttrlib's Python layer), the same table columns, sentinels, background
rule and histogram binning, computed with numpy per chunk. Its burst search is tttrlib's
``StreamingBurstDetector``, which equals the batch sliding-window search for any chunking.

The semantics both follow (tttrlib's header, ``StreamingBurstAnalyzer.h``):

* **Detectors** -- routing channels, optional half-open micro-time ranges. **Windows** --
  half-open micro-time ranges, or macro-time phase ranges of an alternation period (µs-ALEX).
  **Streams** -- every ``"<window> <detector>"`` and every ``"<detector>"``.
* **Search** -- the all-photon sliding window on the search channels (default every detector
  channel); photons of other detectors count when their macro time lies within the burst.
  Photon indices count the accepted photons (those on a detector or search channel).
* **Background** of a stream -- (its photons so far - its photons in recorded bursts) /
  (elapsed - time in bursts), evaluated when a burst closes, after that burst is moved out of the
  background; only quantities that ask subtract it.
"""

from __future__ import annotations

import numpy as np
import tttrlib

__all__ = [
    "PRESETS",
    "StreamingBurstAnalyzer",
    "analyze_offline",
    "make_analyzer",
    "native_available",
]

PRESETS = ("single_color", "two_color", "pie", "alex", "mfd", "three_color_pie")
_SENTINEL = -1.0


def native_available() -> bool:
    """Whether the installed tttrlib has the live analyzer (else the stand-in is used)."""
    return hasattr(tttrlib, "StreamingBurstAnalyzer")


def make_analyzer(setup: dict, preset: str, **kw):
    """``tttrlib.StreamingBurstAnalyzer.from_setup`` when the installed tttrlib has it, else the
    stand-in's -- the same call, the same object API."""
    # FALLBACK (2026-10-26): the stand-in serves tttrlib builds older than 12a52fc32; delete it once
    # every environment carries tttrlib's class.
    cls = tttrlib.StreamingBurstAnalyzer if native_available() else StreamingBurstAnalyzer
    return cls.from_setup(setup, preset, **kw)


def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:].lower()


def _edges(n: int, lo: float, hi: float) -> np.ndarray:
    return np.array([lo + (hi - lo) * i / n for i in range(n + 1)], dtype=float)


def _bin(x: float, edges: np.ndarray) -> int:
    """The half-open bin of *x* whose reported edges hold it (-1 outside)."""
    if not (x >= edges[0]) or not (x < edges[-1]):
        return -1
    return int(min(np.searchsorted(edges, x, side="right") - 1, len(edges) - 2))


class StreamingBurstAnalyzer:
    """Stand-in for ``tttrlib.StreamingBurstAnalyzer`` (same API; see the module docstring)."""

    PRESETS = PRESETS

    def __init__(self, macro_time_resolution: float = 1.0, micro_time_resolution: float = 0.0):
        if not macro_time_resolution > 0:
            raise ValueError("StreamingBurstAnalyzer: macro_time_resolution must be > 0")
        self._dt = float(macro_time_resolution)
        self._micro_dt = float(micro_time_resolution)
        self._detectors: list[tuple[str, list[int], list[tuple[int, int]]]] = []
        self._windows: list[tuple[str, bool, int, int, int]] = []  # name, phase, lo, hi, period
        self._search_channels: list[int] = []
        self._quantities: list[dict] = []
        self._fixed_bg: dict[int, float] = {}
        self._histograms: list[dict] = []
        self._trace_width = 0.0
        self._trace_max = 0
        self._decay_bins = 0
        self._decay_range = 0
        self._per_burst = False
        self._started = False
        self._revision = 0
        self.set_search(20, 10, 5e-4)

    # -- setup ----------------------------------------------------------------------------------
    def _setup_phase(self, what: str) -> None:
        if self._started:
            raise RuntimeError(
                f"StreamingBurstAnalyzer: {what} after the first photon; call clear() first"
            )

    def add_detector(self, name, channels, micro_time_ranges=()):
        self._setup_phase("add_detector")
        ranges = [int(x) for x in micro_time_ranges]
        if len(ranges) % 2:
            raise ValueError("StreamingBurstAnalyzer: micro_time_ranges must be lo/hi pairs")
        pairs = [(ranges[i], ranges[i + 1]) for i in range(0, len(ranges), 2)]
        self._detectors.append((str(name), [int(c) for c in channels], pairs))

    def add_window(self, name, lo, hi):
        self._setup_phase("add_window")
        self._windows.append((str(name), False, max(int(lo), 0), max(int(hi), 0), 0))

    def add_phase_window(self, name, period, lo, hi):
        self._setup_phase("add_phase_window")
        if int(period) <= 0:
            raise ValueError("StreamingBurstAnalyzer: period must be > 0")
        self._windows.append((str(name), True, int(lo), int(hi), int(period)))

    def set_search(self, min_photons, window_photons, window_time):
        self._setup_phase("set_search")
        if int(window_photons) < 1 or not float(window_time) > 0:
            raise ValueError("StreamingBurstAnalyzer: bad search")
        self._L, self._m, self._T = int(min_photons), int(window_photons), float(window_time)

    def set_search_mode(self, mode):
        self._setup_phase("set_search_mode")
        if mode in ("all_photons", "aps", "sliding_window"):
            return
        if mode == "dcbs":
            raise ValueError(
                "StreamingBurstAnalyzer: dual-channel burst search (DCBS) is not implemented yet; "
                "use the all-photon search, optionally on chosen channels (set_search_channels)"
            )
        raise ValueError(f"StreamingBurstAnalyzer: unknown search mode '{mode}'")

    def set_search_channels(self, channels):
        self._setup_phase("set_search_channels")
        self._search_channels = [int(c) for c in channels]

    def add_ratio(self, name, numerator, denominator, subtract_background):
        self._setup_phase("add_ratio")
        self._quantities.append(
            {
                "kind": "ratio",
                "names": [name],
                "a": [self._sid(s) for s in numerator],
                "b": [self._sid(s) for s in denominator],
                "bg": bool(subtract_background),
            }
        )

    def add_corrected_fret(
        self, name_e, name_s, dd, da, aa, gamma, beta, alpha, delta, subtract_background
    ):
        self._setup_phase("add_corrected_fret")
        if beta == 0:
            raise ValueError("StreamingBurstAnalyzer: beta must be non-zero")
        q = {
            "kind": "fret",
            "names": [name_e],
            "a": [self._sid(dd), self._sid(da)],
            "p": [float(gamma), float(beta), float(alpha), float(delta)],
            "bg": bool(subtract_background),
        }
        if aa:
            q["a"].append(self._sid(aa))
            q["names"].append(name_s)
        self._quantities.append(q)

    def add_anisotropy(self, name, parallel, perpendicular, g, l1, l2, subtract_background):
        self._setup_phase("add_anisotropy")
        self._quantities.append(
            {
                "kind": "aniso",
                "names": [name],
                "a": [self._sid(parallel), self._sid(perpendicular)],
                "p": [float(g), float(l1), float(l2)],
                "bg": bool(subtract_background),
            }
        )

    def add_mean_microtime(self, name, stream):
        self._setup_phase("add_mean_microtime")
        self._quantities.append(
            {"kind": "micro", "names": [name], "a": [self._sid(stream)], "bg": False}
        )

    def set_background_rate(self, stream, rate_cps):
        self._fixed_bg[self._sid(stream)] = float(rate_cps)

    def add_histogram(self, x, n_x, x_min, x_max, y="", n_y=0, y_min=0.0, y_max=0.0):
        if int(n_x) < 1 or not x_max > x_min or (y and (int(n_y) < 1 or not y_max > y_min)):
            raise ValueError("StreamingBurstAnalyzer: bad histogram geometry")
        h = {"x": x, "y": y or "", "x_edges": _edges(int(n_x), float(x_min), float(x_max))}
        h["y_edges"] = _edges(int(n_y), float(y_min), float(y_max)) if y else None
        h["counts"] = np.zeros((int(n_x), int(n_y)) if y else int(n_x))
        self._histograms.append(h)
        if self._started:
            self._bind(h)
            for row in self._rows:
                self._fill(h, row)
        self._revision += 1
        return len(self._histograms) - 1

    def set_trace(self, bin_width, max_bins):
        self._setup_phase("set_trace")
        if not bin_width > 0 or int(max_bins) < 1:
            raise ValueError("StreamingBurstAnalyzer: bad trace geometry")
        self._trace_width, self._trace_max = float(bin_width), int(max_bins)

    def set_decays(self, n_bins, micro_range, per_burst=False):
        self._setup_phase("set_decays")
        if int(n_bins) < 1 or int(micro_range) < 1:
            raise ValueError("StreamingBurstAnalyzer: bad decay geometry")
        self._decay_bins, self._decay_range, self._per_burst = (
            int(n_bins),
            int(micro_range),
            bool(per_burst),
        )

    # -- streams and columns --------------------------------------------------------------------
    def stream_names(self):
        n = [f"{w[0]} {d[0]}" for w in self._windows for d in self._detectors]
        return n + [d[0] for d in self._detectors]

    def _sid(self, name: str) -> int:
        names = self.stream_names()
        if name not in names:
            raise ValueError(
                f"StreamingBurstAnalyzer: no stream '{name}' (streams are '<window> <detector>' and '<detector>')"
            )
        return names.index(name)

    def table_names(self):
        n = [
            "First Photon",
            "Last Photon",
            "Duration (ms)",
            "Mean Macro Time (ms)",
            "Number of Photons",
            "Count Rate (KHz)",
        ]
        for d in self._detectors:
            name = d[0]
            n += [
                f"First Photon ({name})",
                f"Last Photon ({name})",
                f"Duration ({name}) (ms)",
                f"Mean Macrotime ({name}) (ms)",
                f"Number of Photons ({name})",
                f"{_capitalize(name)} Count Rate (KHz)",
            ]
        for w in self._windows:
            for d in self._detectors:
                stream, rng = f"S {w[0]} {d[0]}", f" | {w[2]}-{w[3]}"
                n += [f"{stream} (kHz){rng}", f"{stream} (photons){rng}", f"{stream} (ms){rng}"]
        n += [f"Mean Microtime ({d[0]}) (ns)" for d in self._detectors]
        for q in self._quantities:
            n += q["names"]
        return n

    # -- photons --------------------------------------------------------------------------------
    def _start(self) -> None:
        names = self.table_names()
        for h in self._histograms:
            self._bind(h, names)
        det_ch = sorted({c for d in self._detectors for c in d[1]})
        self._det_ch = np.array(det_ch, dtype=np.int64)
        if self._search_channels:
            self._search_ch = np.array(self._search_channels, dtype=np.int64)
        elif self._detectors:
            self._search_ch = self._det_ch
        else:
            self._search_ch = None  # every photon
        ns = len(self.stream_names())
        self._ns = ns
        self._detector = tttrlib.StreamingBurstDetector(self._m, self._T, self._dt)
        self._detector.set_min_photons(self._L)
        self._n_accepted = 0
        self._n_search = 0
        self._first = None
        self._last = 0
        self._total = np.zeros(ns, np.int64)
        self._in_bursts = np.zeros(ns, np.int64)
        self._burst_ticks = 0
        self._rows: list[list[float]] = []
        self._n_done = 0
        # buffers from the oldest photon an unrecorded burst may still need
        self._buf_macro = np.zeros(0, np.uint64)
        self._buf_micro = np.zeros(0, np.int64)
        self._buf_member = np.zeros((0, ns), bool)
        self._buf_index = np.zeros(0, np.int64)  # accepted index
        self._buf_search = np.zeros(0, bool)
        self._buf_cum = np.zeros((0, ns), np.int64)  # stream totals after each buffered photon
        self._search_pos = np.zeros(
            0, np.int64
        )  # buffer position of each search photon (from _search_base)
        self._search_base = 0
        self._trace: list[np.ndarray] = []
        self._trace_first = 0
        self._trace_ticks = (
            max(1, int(self._trace_width / self._dt)) if self._trace_width > 0 else 0
        )
        nb = self._decay_bins
        self._decay_all = np.zeros((ns, nb))
        self._decay_burst = np.zeros((ns, nb))
        self._burst_decays: list[np.ndarray] = []
        self._started = True
        self._revision += 1

    def _membership(self, macro, micro, channel) -> np.ndarray:
        nd, nw = len(self._detectors), len(self._windows)
        dmask = np.zeros((len(macro), nd), bool)
        for k, (_n, chs, ranges) in enumerate(self._detectors):
            on = np.isin(channel, chs)
            if ranges:
                inr = np.zeros(len(macro), bool)
                for lo, hi in ranges:
                    inr |= (micro >= lo) & (micro < hi)
                on &= inr
            dmask[:, k] = on
        wmask = np.zeros((len(macro), nw), bool)
        for k, (_n, phase, lo, hi, period) in enumerate(self._windows):
            v = (macro % np.uint64(period)).astype(np.int64) if phase else micro
            wmask[:, k] = (v >= lo) & (v < hi)
        member = np.zeros((len(macro), self._ns), bool)
        for w in range(nw):
            for d in range(nd):
                member[:, w * nd + d] = dmask[:, d] & wmask[:, w]
        for d in range(nd):
            member[:, nw * nd + d] = dmask[:, d]
        return member

    def push_np(self, macro_times, micro_times=None, channels=None):
        """Push one chunk of photons (macro times must not decrease)."""
        macro = np.ascontiguousarray(macro_times, dtype=np.uint64)
        n = len(macro)
        if n == 0:
            return
        if not self._started:
            self._start()
        micro = (
            np.zeros(n, np.int64)
            if micro_times is None
            else np.asarray(micro_times, dtype=np.int64)
        )
        channel = (
            np.zeros(n, np.int64) if channels is None else np.asarray(channels, dtype=np.int64)
        )
        valid = (channel >= 0) & (channel < 256)
        is_det = np.isin(channel, self._det_ch) & valid
        is_search = (
            np.isin(channel, self._search_ch) if self._search_ch is not None else np.ones(n, bool)
        ) & valid
        keep = is_det | is_search
        macro, micro, channel, is_search = macro[keep], micro[keep], channel[keep], is_search[keep]
        n = len(macro)
        if n == 0:
            return
        member = self._membership(macro, micro, channel)
        index = self._n_accepted + np.arange(n, dtype=np.int64)
        if self._first is None:
            self._first = int(macro[0])
        self._last = int(macro[-1])
        cum = np.cumsum(member, axis=0, dtype=np.int64) + self._total
        self._observe(macro, micro, member)
        self._total = cum[-1].copy()
        self._n_accepted += n
        start = len(self._buf_macro)
        self._buf_macro = np.concatenate([self._buf_macro, macro])
        self._buf_micro = np.concatenate([self._buf_micro, micro])
        self._buf_member = np.concatenate([self._buf_member, member])
        self._buf_index = np.concatenate([self._buf_index, index])
        self._buf_search = np.concatenate([self._buf_search, is_search])
        self._buf_cum = np.concatenate([self._buf_cum, cum])
        self._search_pos = np.concatenate([self._search_pos, start + np.flatnonzero(is_search)])
        search_macro = macro[is_search]
        self._n_search += len(search_macro)
        if len(search_macro):
            self._detector.push_np(search_macro)
        self._collect(closing_known=True)

    def flush(self):
        if not self._started:
            return
        self._detector.flush()
        self._collect(closing_known=False)

    def clear(self):
        self._started = False
        self._revision += 1
        for h in self._histograms:
            h["counts"][...] = 0

    def _observe(self, macro, micro, member) -> None:
        if self._trace_ticks:
            bins = (macro // np.uint64(self._trace_ticks)).astype(np.int64)
            for b in np.unique(bins):
                if not self._trace:
                    self._trace_first = int(b)
                while self._trace_first + len(self._trace) <= b:
                    self._trace.append(np.zeros(self._ns))
                while len(self._trace) > self._trace_max:
                    self._trace.pop(0)
                    self._trace_first += 1
                k = int(b) - self._trace_first
                if k >= 0:
                    self._trace[k] += member[bins == b].sum(axis=0)
        if self._decay_bins:
            ok = micro < self._decay_range
            db = micro[ok] * self._decay_bins // self._decay_range
            for s in range(self._ns):
                self._decay_all[s] += np.bincount(db[member[ok, s]], minlength=self._decay_bins)[
                    : self._decay_bins
                ]

    def _collect(self, closing_known: bool) -> None:
        idx = np.asarray(self._detector.get_burst_indices(), dtype=np.int64).reshape(-1, 2)
        for start, stop in idx[self._n_done :]:
            pos0 = int(self._search_pos[start - self._search_base])
            pos1 = int(self._search_pos[stop - self._search_base])
            if stop + 1 - self._search_base < len(self._search_pos):
                closing = int(self._search_pos[stop + 1 - self._search_base])
            else:  # closed by flush: every photon so far counts
                closing = len(self._buf_macro) - 1
            self._close(pos0, pos1, closing)
        self._n_done = len(idx)
        self._prune()

    def _close(self, pos0: int, pos1: int, closing: int) -> None:
        t0, t1 = int(self._buf_macro[pos0]), int(self._buf_macro[pos1])
        sel = np.zeros(len(self._buf_macro), bool)
        sel[pos0 : pos1 + 1] = self._buf_search[pos0 : pos1 + 1]
        # photons of non-search detectors within the burst, as far as they arrived when it closed
        extra = (~self._buf_search) & (self._buf_macro >= t0) & (self._buf_macro <= t1)
        extra[closing + 1 :] = False
        sel |= extra
        member = self._buf_member[sel]
        macro = self._buf_macro[sel].astype(np.int64)
        micro = self._buf_micro[sel]
        index = self._buf_index[sel]
        n_s = member.sum(axis=0)
        nd, nw = len(self._detectors), len(self._windows)
        ms = self._dt * 1e3
        micro_ns = self._micro_dt * 1e9 if self._micro_dt > 0 else 0.0
        count = int(self._buf_search[pos0 : pos1 + 1].sum() + extra.sum())
        dur = (t1 - t0) * ms
        v = [
            float(self._buf_index[pos0]),
            float(self._buf_index[pos1]),
            dur,
            (t1 + t0) / 2.0 * ms,
            float(count),
            count / dur if dur > 0 else np.nan,
        ]

        def span(s):
            m = member[:, s]
            return macro[m], index[m]

        for d in range(nd):
            s = nw * nd + d
            if n_s[s] == 0:
                v += [-1.0, -1.0, _SENTINEL, _SENTINEL, 0.0, _SENTINEL]
                continue
            mt, ix = span(s)
            d_ms = (mt[-1] - mt[0]) * ms
            v += [
                float(ix[0]),
                float(ix[-1]),
                d_ms,
                (mt[-1] + mt[0]) / 2.0 * ms,
                float(n_s[s]),
                n_s[s] / d_ms if d_ms > 0 else np.nan,
            ]
        for w in range(nw):
            for d in range(nd):
                s = w * nd + d
                if n_s[s] == 0:
                    v += [_SENTINEL, 0.0, _SENTINEL]
                    continue
                mt, _ix = span(s)
                d_ms = (mt[-1] - mt[0]) * ms
                v += [n_s[s] / d_ms if d_ms > 0 else np.nan, float(n_s[s]), d_ms]
        for d in range(nd):
            s = nw * nd + d
            v.append(
                micro[member[:, s]].sum() / n_s[s] * micro_ns
                if n_s[s] > 0 and micro_ns > 0
                else _SENTINEL
            )

        # this burst leaves the background before the quantities use it
        self._in_bursts += n_s
        self._burst_ticks += t1 - t0
        totals = self._buf_cum[closing]
        last = int(self._buf_macro[closing])
        span_ticks = t1 - t0

        def bg(s):
            if s in self._fixed_bg and self._fixed_bg[s] >= 0:
                return self._fixed_bg[s] * self._dt
            whole = last - self._first
            if whole <= self._burst_ticks:
                return 0.0
            k = totals[s] - self._in_bursts[s]
            return k / (whole - self._burst_ticks) if k > 0 else 0.0

        def cnt(s, sub):
            return float(n_s[s]) - (bg(s) * span_ticks if sub else 0.0)

        for q in self._quantities:
            kind, sub = q["kind"], q["bg"]
            if kind == "ratio":
                num = sum(cnt(s, sub) for s in q["a"])
                den = sum(cnt(s, sub) for s in q["b"])
                v.append(num / den if den != 0 else 0.0)
            elif kind == "fret":
                g, be, al, de = q["p"]
                has_s = len(q["a"]) > 2
                f_dd = cnt(q["a"][0], sub)
                f_aa = cnt(q["a"][2], sub) if has_s else 0.0
                f_da = cnt(q["a"][1], sub) - al * f_dd - de * f_aa
                e_den = f_da + g * f_dd
                v.append(f_da / e_den if e_den > 0 else 0.0)
                if has_s:
                    s_den = g * f_dd + f_da + f_aa / be
                    v.append((g * f_dd + f_da) / s_den if s_den != 0 else 0.0)
            elif kind == "aniso":
                fp, fs = cnt(q["a"][0], sub), cnt(q["a"][1], sub)
                g, l1, l2 = q["p"]
                den = fp * (1 - 3 * l2) + (2 - 3 * l1) * g * fs
                v.append((fp - g * fs) / den if den != 0 else 0.0)
            else:  # mean micro time
                s = q["a"][0]
                v.append(
                    micro[member[:, s]].sum() / n_s[s] * micro_ns
                    if n_s[s] > 0 and micro_ns > 0
                    else _SENTINEL
                )

        if self._decay_bins:
            ok = micro < self._decay_range
            db = micro[ok] * self._decay_bins // self._decay_range
            this = np.zeros((self._ns, self._decay_bins))
            for s in range(self._ns):
                this[s] = np.bincount(db[member[ok, s]], minlength=self._decay_bins)[
                    : self._decay_bins
                ]
            self._decay_burst += this
            if self._per_burst:
                self._burst_decays.append(this)
        self._rows.append(v)
        for h in self._histograms:
            self._fill(h, v)
        self._revision += 1

    def _prune(self) -> None:
        """Keep photons from the oldest one an unrecorded burst may still need."""
        n_buf_search = len(self._search_pos)
        if n_buf_search == 0:
            return
        # Bursts are ordered by their start: an open (or later) burst starts no earlier than the last
        # recorded one did. Before the first burst nothing is dropped.
        if not self._n_done:
            return
        last = np.asarray(self._detector.get_burst_indices(), dtype=np.int64).reshape(-1, 2)[-1]
        keep_search = max(0, int(last[0]) - self._search_base)
        cut_pos = int(self._search_pos[keep_search])
        # non-search photons may belong to a burst opening at that photon's time
        t_keep = self._buf_macro[cut_pos]
        first_needed = int(np.searchsorted(self._buf_macro, t_keep, side="left"))
        cut = min(cut_pos, first_needed)
        if cut <= 0:
            return
        self._buf_macro = self._buf_macro[cut:]
        self._buf_micro = self._buf_micro[cut:]
        self._buf_member = self._buf_member[cut:]
        self._buf_index = self._buf_index[cut:]
        self._buf_search = self._buf_search[cut:]
        self._buf_cum = self._buf_cum[cut:]
        dropped_search = int(np.searchsorted(self._search_pos, cut))
        self._search_pos = self._search_pos[dropped_search:] - cut
        self._search_base += dropped_search

    # -- histograms -----------------------------------------------------------------------------
    def _bind(self, h, names=None) -> None:
        names = names or self.table_names()
        if h["x"] not in names or (h["y"] and h["y"] not in names):
            raise ValueError(
                f"StreamingBurstAnalyzer: no column to histogram ({h['x']!r}, {h['y']!r})"
            )
        h["cx"] = names.index(h["x"])
        h["cy"] = names.index(h["y"]) if h["y"] else -1

    @staticmethod
    def _fill(h, row) -> None:
        ix = _bin(row[h["cx"]], h["x_edges"])
        if ix < 0:
            return
        if h["cy"] >= 0:
            iy = _bin(row[h["cy"]], h["y_edges"])
            if iy < 0:
                return
            h["counts"][ix, iy] += 1
        else:
            h["counts"][ix] += 1

    # -- live queries -----------------------------------------------------------------------------
    def burst_count(self):
        return len(self._rows) if self._started else 0

    def photon_count(self):
        return self._n_accepted if self._started else 0

    def revision(self):
        return self._revision

    def elapsed_seconds(self):
        return (
            (self._last - self._first) * self._dt
            if self._started and self._first is not None
            else 0.0
        )

    def burst_rate_hz(self):
        t = self.elapsed_seconds()
        return self.burst_count() / t if t > 0 else 0.0

    def background_rate(self, stream):
        """Background of *stream* (counts/s): the live estimate over the photons so far."""
        s = self._sid(stream)
        if s in self._fixed_bg and self._fixed_bg[s] >= 0:
            return self._fixed_bg[s]
        if not self._started or self._first is None:
            return 0.0
        whole = self._last - self._first
        if whole <= self._burst_ticks:
            return 0.0
        k = self._total[s] - self._in_bursts[s]
        return k / (whole - self._burst_ticks) / self._dt if k > 0 else 0.0

    def stream_photons(self, stream):
        return float(self._total[self._sid(stream)]) if self._started else 0.0

    def min_photons(self):
        return self._L

    def window_photons(self):
        return self._m

    def window_time(self):
        return self._T

    def macro_time_resolution(self):
        return self._dt

    def micro_time_resolution(self):
        return self._micro_dt

    def table_column(self, name):
        names = self.table_names()
        if name not in names:
            raise ValueError(f"StreamingBurstAnalyzer: no column '{name}'")
        c = names.index(name)
        return [r[c] for r in self._rows] if self._started else []

    # -- the Python layer (tttrlib's, copied) ------------------------------------------------------
    @classmethod
    def from_setup(cls, setup, preset="pie", *, min_photons=20, window_photons=10,
                   window_time=5e-4, macro_time_resolution=None, micro_time_resolution=None,
                   donor="green", acceptor="red", prompt="prompt", delay="delayed",
                   colors=("blue", "green", "red"), factors=None, subtract_background=False,
                   alex_period=None, alex_windows=None, search_channels=None,
                   histograms=True, trace=None, decays=None):  # fmt: skip
        """As ``tttrlib.StreamingBurstAnalyzer.from_setup`` (its docstring is the reference)."""
        if preset not in cls.PRESETS:
            raise ValueError(f"unknown preset {preset!r}; one of {cls.PRESETS}")
        reading = setup.get("tttr_reading") or {}
        if macro_time_resolution is None:
            macro_time_resolution = float(reading.get("macro_time_resolution", 0.0)) * 1e-9
        if micro_time_resolution is None:
            # ps, as the setup editor writes it (tttrlib's from_setup reads it the same way;
            # an explicit "micro_time_resolution_unit": "ns" reads ns)
            unit = str(reading.get("micro_time_resolution_unit", "ps")).lower()
            scale = {"ps": 1e-12, "ns": 1e-9, "s": 1.0}.get(unit)
            if scale is None:
                raise ValueError(f"micro_time_resolution_unit {unit!r}: one of ps, ns, s")
            micro_time_resolution = float(reading.get("micro_time_resolution", 0.0)) * scale
        a = cls(float(macro_time_resolution), float(micro_time_resolution))
        detectors = dict(setup.get("detectors") or {})
        for name, d in detectors.items():
            ranges = [int(x) for r in (d.get("micro_time_ranges") or []) for x in r]
            a.add_detector(str(name), [int(c) for c in d.get("chs", [])], ranges)
        windows = dict(setup.get("windows") or {})
        if preset == "alex":
            if not alex_period:
                raise ValueError("preset 'alex' needs alex_period (seconds)")

            def ticks(s):
                return int(round(s / macro_time_resolution))

            period = ticks(alex_period)
            aw = alex_windows or {
                prompt: (0.0, alex_period / 2),
                delay: (alex_period / 2, alex_period),
            }
            for name, (lo, hi) in aw.items():
                a.add_phase_window(str(name), period, ticks(lo), ticks(hi))
        else:
            for name, (lo, hi) in windows.items():
                a.add_window(str(name), int(lo), int(hi))
        a.set_search(int(min_photons), int(window_photons), float(window_time))
        if search_channels is not None:
            a.set_search_channels([int(c) for c in search_channels])
        bg = bool(subtract_background)
        hists = []

        if preset == "single_color":
            hists += [("Number of Photons", 50, 0, 500), ("Duration (ms)", 50, 0.0, 10.0)]
        elif preset == "two_color":
            a.add_ratio("Proximity Ratio", [acceptor], [donor, acceptor], bg)
            hists += [("Proximity Ratio", 50, -0.1, 1.1)]
        elif preset in ("pie", "alex"):
            dd, da, aa = f"{prompt} {donor}", f"{prompt} {acceptor}", f"{delay} {acceptor}"
            a.add_ratio("Proximity Ratio", [da], [dd, da], bg)
            a.add_ratio("Stoichiometry", [dd, da], [dd, da, aa], bg)
            hists += [("Proximity Ratio", 50, -0.1, 1.1, "Stoichiometry", 50, -0.1, 1.1)]
            if factors is not None:
                f = {"gamma": 1.0, "beta": 1.0, "alpha": 0.0, "delta": 0.0}
                f.update(factors)
                a.add_corrected_fret("FRET Efficiency", "Stoichiometry (corrected)", dd, da, aa,
                                     f["gamma"], f["beta"], f["alpha"], f["delta"], bg)  # fmt: skip
                hists += [
                    ("FRET Efficiency", 50, -0.1, 1.1, "Stoichiometry (corrected)", 50, -0.1, 1.1)
                ]
        elif preset == "mfd":
            pre = (prompt + " ") if prompt in windows else ""
            colours = [
                n[:-4] for n in detectors if n.endswith("_par") and n[:-4] + "_perp" in detectors
            ]
            if not colours:
                raise ValueError("preset 'mfd' needs <colour>_par / <colour>_perp detectors")

            def pol(c, key, default):
                d = detectors.get(c + "_par") or {}
                return float(d.get(key, setup.get(key, default)))

            for c in colours:
                par, perp = pre + c + "_par", pre + c + "_perp"
                g, l1, l2 = pol(c, "g_factor", 1.0), pol(c, "l1", 0.0), pol(c, "l2", 0.0)
                a.add_anisotropy(f"r Experimental ({c})", par, perp, g, l1, l2, False)
                if bg:
                    a.add_anisotropy(f"r Scatter ({c})", par, perp, g, l1, l2, True)
                if pre:
                    a.add_mean_microtime(f"Mean Microtime ({pre.strip()} {c}_par) (ns)", par)
                hists += [(f"r Experimental ({c})", 50, -0.2, 0.6)]
            if donor in colours and acceptor in colours:
                don = [pre + donor + "_par", pre + donor + "_perp"]
                acc = [pre + acceptor + "_par", pre + acceptor + "_perp"]
                a.add_ratio("Proximity Ratio", acc, don + acc, bg)
                hists += [
                    ("Proximity Ratio", 50, -0.1, 1.1, f"r Experimental ({donor})", 40, -0.2, 0.6)
                ]
        elif preset == "three_color_pie":
            b, g, r = colors

            def s(w, d):
                return f"{w} {d}"

            a.add_ratio("Proximity Ratio (BG)", [s(b, g)], [s(b, b), s(b, g)], bg)
            a.add_ratio("Proximity Ratio (BR)", [s(b, r)], [s(b, b), s(b, r)], bg)
            a.add_ratio("Proximity Ratio (GR)", [s(g, r)], [s(g, g), s(g, r)], bg)
            a.add_ratio("Stoichiometry (BG)", [s(b, b), s(b, g), s(b, r)],
                        [s(b, b), s(b, g), s(b, r), s(g, g), s(g, r)], bg)  # fmt: skip
            a.add_ratio("Stoichiometry (GR)", [s(g, g), s(g, r)], [s(g, g), s(g, r), s(r, r)], bg)
            hists += [("Proximity Ratio (GR)", 50, -0.1, 1.1, "Stoichiometry (GR)", 50, -0.1, 1.1),
                      ("Proximity Ratio (BG)", 50, -0.1, 1.1, "Proximity Ratio (BR)", 50, -0.1, 1.1)]  # fmt: skip
        if histograms:
            for h in hists:
                if len(h) == 4:
                    a.add_histogram(h[0], int(h[1]), float(h[2]), float(h[3]), "", 0, 0.0, 0.0)
                else:
                    a.add_histogram(h[0], int(h[1]), float(h[2]), float(h[3]),
                                    h[4], int(h[5]), float(h[6]), float(h[7]))  # fmt: skip
        if trace is not None:
            a.set_trace(float(trace[0]), int(trace[1]))
        if decays is not None:
            a.set_decays(
                int(decays[0]), int(decays[1]), bool(decays[2]) if len(decays) > 2 else False
            )
        return a

    def histograms(self):
        """{name: {"counts", "x", "x_edges"[, "y", "y_edges"]}}; the name is ``x`` or ``"x vs y"``."""
        out = {}
        for h in self._histograms:
            d = {"x": h["x"], "x_edges": h["x_edges"].copy(), "counts": h["counts"].copy()}
            if h["y"]:
                d["y"] = h["y"]
                d["y_edges"] = h["y_edges"].copy()
            out[f"{h['x']} vs {h['y']}" if h["y"] else h["x"]] = d
        return out

    def snapshot(self):
        """Counters, per-stream background (cps), histograms, and traces/decays when set."""
        streams = self.stream_names()
        snap = {
            "revision": int(self.revision()),
            "bursts": int(self.burst_count()),
            "photons": int(self.photon_count()),
            "elapsed_s": float(self.elapsed_seconds()),
            "burst_rate_hz": float(self.burst_rate_hz()),
            "background_cps": {s: float(self.background_rate(s)) for s in streams},
            "histograms": self.histograms(),
        }
        if self._trace_width > 0:
            trace = (
                np.array(self._trace)
                if self._started and self._trace
                else np.zeros((0, len(streams)))
            )
            snap["trace"] = {
                "bin_width_s": float(self._trace_width),
                "first_bin": int(self._trace_first if self._started else 0),
                "counts": {s: trace[:, k].astype(float) for k, s in enumerate(streams)},
            }
        if self._decay_bins > 0:
            ok = self._started
            snap["decays"] = {
                s: (self._decay_all[k].copy() if ok else np.zeros(0)) for k, s in enumerate(streams)
            }
            snap["burst_decays"] = {
                s: (self._decay_burst[k].copy() if ok else np.zeros(0))
                for k, s in enumerate(streams)
            }
        return snap

    _INT_COLUMNS = ("First Photon", "Last Photon", "Number of Photons")

    def table(self):
        """The burst table as {column: numpy array}, in the batch table's names and order."""
        out = {}
        for name in self.table_names():
            col = np.asarray(self.table_column(name), dtype=float)
            if name.startswith(self._INT_COLUMNS) or "(photons)" in name:
                col = col.astype(np.int64)
            out[name] = col
        return out


def analyze_offline(tttr, setup: dict, preset: str, *, min_photons=20, window_photons=10, window_time=5e-4,
                    donor="green", acceptor="red", prompt="prompt", delay="delayed") -> dict:  # fmt: skip
    """The batch reference: burst selection's search over a whole file, counted per stream.

    Written independently of both analyzers -- the photons of the detector channels selected,
    ``TTTR.burst_search`` on them, counts per stream by membership, the preset's ratios without
    background. The guard holds every live analyzer's table to this for the columns it gives.
    """
    detectors = setup.get("detectors") or {}
    windows = setup.get("windows") or {}
    chs = sorted({int(c) for d in detectors.values() for c in d.get("chs", [])})
    channel = np.asarray(tttr.routing_channels)
    sel = np.flatnonzero(np.isin(channel, chs))
    sub = tttr[sel] if len(sel) != len(tttr) else tttr
    macro = np.asarray(sub.macro_times, dtype=np.int64)
    micro = np.asarray(sub.micro_times, dtype=np.int64)
    ch = np.asarray(sub.routing_channels, dtype=np.int64)
    idx = np.asarray(
        sub.burst_search(int(min_photons), int(window_photons), float(window_time))
    ).reshape(-1, 2)

    def member(det, win=None):
        d = detectors[det]
        m = np.isin(ch, d.get("chs", []))
        if win is not None:
            lo, hi = windows[win]
            m &= (micro >= lo) & (micro < hi)
        return m

    cum = {}

    def count(det, win=None):
        key = (det, win)
        if key not in cum:
            cum[key] = np.concatenate([[0], np.cumsum(member(det, win))])
        c = cum[key]
        return (c[idx[:, 1] + 1] - c[idx[:, 0]]).astype(float)

    clock = float(tttr.header.macro_time_resolution)
    out = {
        "First Photon": idx[:, 0].astype(np.int64),
        "Last Photon": idx[:, 1].astype(np.int64),
        "Number of Photons": (idx[:, 1] - idx[:, 0] + 1).astype(np.int64),
        "Duration (ms)": (macro[idx[:, 1]] - macro[idx[:, 0]]) * clock * 1e3,
    }
    for det in detectors:
        out[f"Number of Photons ({det})"] = count(det).astype(np.int64)

    def ratio(num, den):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den != 0, num / np.where(den != 0, den, 1), 0.0)

    if preset == "two_color":
        out["Proximity Ratio"] = ratio(count(acceptor), count(donor) + count(acceptor))
    elif preset == "pie":
        dd, da, aa = count(donor, prompt), count(acceptor, prompt), count(acceptor, delay)
        out["Proximity Ratio"] = ratio(da, dd + da)
        out["Stoichiometry"] = ratio(dd + da, dd + da + aa)
    return out
