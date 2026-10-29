"""The running smFRET trace: the last few seconds of photons, binned, donor up and acceptor down.

The classic single-molecule trace: the donor signal under donor excitation is drawn positive, the
acceptor signals negative -- the acceptor under donor excitation (FRET, DA) and, with alternating or
pulsed interleaved excitation, the directly excited acceptor (AA). Bursts show as mirrored spikes, a
FRET burst as a donor spike over an acceptor spike.

:class:`LiveTrace` keeps a ring buffer of bin counts covering the last ``window_s`` seconds: a batch
adds its photons to their bins, bins older than the window are dropped, so a redraw costs the
window's bins, never the run's photons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from chisurf.core.fluorescence.excitation import micro_mask

__all__ = ["LiveTrace", "TraceStream", "trace_streams"]

#: The trace's default span and bin width.
DEFAULT_WINDOW_S = 1.0
DEFAULT_BIN_S = 1e-3
#: Most bins a trace keeps (span / bin width), whatever the user enters.
MAX_BINS = 200_000


@dataclass(frozen=True)
class TraceStream:
    """One curve of the trace: which photons, drawn up (+1) or down (-1), in which colour."""

    name: str
    channels: tuple
    sign: int
    colour: tuple
    window: tuple | None = None  # micro-time [lo, hi)
    phase: int | None = None  # ALEX: 0 under the donor laser, 1 under the acceptor laser


GREEN = (0.20, 0.75, 0.30, 1.0)
RED = (0.90, 0.25, 0.25, 1.0)
MAGENTA = (0.75, 0.25, 0.75, 1.0)
BLUE = (0.30, 0.55, 0.95, 1.0)


def _chs(setup: dict, name: str) -> tuple:
    det = (setup.get("detectors") or {}).get(name) or {}
    return tuple(int(c) for c in det.get("chs", ()))


def trace_streams(
    setup: dict, preset: str, *, donor="green", acceptor="red", prompt="prompt", delay="delayed"
) -> list[TraceStream]:
    """The curves a preset's trace draws.

    * PIE: DD up (donor detector, prompt window), DA down (acceptor detector, prompt), AA down
      (acceptor detector, delay window).
    * µs-ALEX: the same three, split by the alternation phase instead of micro-time windows.
    * two colour (and MFD): donor up, acceptor down.
    * single colour: the one detector up.
    * three-colour PIE: each detector of the setup in turn, the first up and the rest down.
    """
    windows = setup.get("windows") or {}
    d, a = _chs(setup, donor), _chs(setup, acceptor)
    if preset == "pie" and prompt in windows and delay in windows:
        p, q = tuple(windows[prompt]), tuple(windows[delay])
        return [
            TraceStream("DD (donor, donor exc.)", d, +1, GREEN, window=p),
            TraceStream("DA (FRET, donor exc.)", a, -1, RED, window=p),
            TraceStream("AA (acceptor exc.)", a, -1, MAGENTA, window=q),
        ]
    if preset == "alex":
        return [
            TraceStream("DD (donor, donor exc.)", d, +1, GREEN, phase=0),
            TraceStream("DA (FRET, donor exc.)", a, -1, RED, phase=0),
            TraceStream("AA (acceptor exc.)", a, -1, MAGENTA, phase=1),
        ]
    if preset == "single_color":
        names = list((setup.get("detectors") or {}).keys())
        chs = _chs(setup, names[0]) if names else (0,)
        return [TraceStream(names[0] if names else "signal", chs, +1, GREEN)]
    if preset == "mfd":
        green = (
            tuple(
                c
                for k in (setup.get("detectors") or {})
                if k.startswith(donor)
                for c in _chs(setup, k)
            )
            or d
        )
        red = (
            tuple(
                c
                for k in (setup.get("detectors") or {})
                if k.startswith(acceptor)
                for c in _chs(setup, k)
            )
            or a
        )
        return [TraceStream("donor", green, +1, GREEN), TraceStream("acceptor", red, -1, RED)]
    if preset == "three_color_pie":
        colours = (BLUE, GREEN, RED, MAGENTA)
        out = []
        for k, name in enumerate((setup.get("detectors") or {}).keys()):
            out.append(
                TraceStream(
                    name, _chs(setup, name), +1 if k == 0 else -1, colours[k % len(colours)]
                )
            )
        return out
    return [TraceStream("donor", d, +1, GREEN), TraceStream("acceptor", a, -1, RED)]


class LiveTrace:
    """A ring buffer of bin counts per stream over the last ``window_s`` seconds.

    Parameters
    ----------
    streams : list of TraceStream
    macro_clock_s : float
    window_s, bin_s : float
        The span shown and the bin width.
    alex_period_s : float, optional
        µs-ALEX: the alternation period (the first half excites the donor).
    """

    def __init__(
        self,
        streams: list[TraceStream],
        *,
        macro_clock_s: float,
        window_s: float = DEFAULT_WINDOW_S,
        bin_s: float = DEFAULT_BIN_S,
        alex_period_s: float | None = None,
    ):
        self.streams = list(streams)
        self.clock = float(macro_clock_s)
        self.alex_period_s = alex_period_s
        self.configure(window_s, bin_s)

    def configure(self, window_s: float, bin_s: float) -> None:
        """Set the span and bin width (the buffer starts empty again)."""
        bin_s = max(float(bin_s), 1e-7)
        window_s = max(float(window_s), bin_s)
        self.bin_s = bin_s
        self.n_bins = int(min(MAX_BINS, max(1, round(window_s / bin_s))))
        self.window_s = self.n_bins * self.bin_s
        self.counts = np.zeros((len(self.streams), self.n_bins), np.int64)
        self.head = -1  # absolute index of the newest bin (-1: nothing yet)
        self._first: int | None = None
        self.revision = 0

    def _advance(self, new_head: int) -> None:
        """Move the newest bin to *new_head*, clearing the bins that come into the window."""
        if self.head < 0:
            self.head = new_head
            return
        steps = new_head - self.head
        if steps <= 0:
            return
        if steps >= self.n_bins:
            self.counts[:] = 0
        else:
            idx = (np.arange(self.head + 1, new_head + 1)) % self.n_bins
            self.counts[:, idx] = 0
        self.head = new_head

    def push(self, macro, micro, channel) -> None:
        """Add photons (time order) to their bins; older than the window they are dropped."""
        if len(macro) == 0:
            return
        macro = np.asarray(macro, np.int64)
        if self._first is None:
            self._first = int(macro[0])
        t = (macro - self._first) * self.clock
        b = np.floor(t / self.bin_s).astype(np.int64)
        self._advance(int(b[-1]))
        keep = b > self.head - self.n_bins
        if not np.any(keep):
            return
        b, t = b[keep], t[keep]
        micro = np.asarray(micro, np.int64)[keep]
        channel = np.asarray(channel, np.int64)[keep]
        slots = b % self.n_bins
        phase = None
        if self.alex_period_s:
            phase = ((t % self.alex_period_s) >= self.alex_period_s / 2).astype(np.int64)
        for k, s in enumerate(self.streams):
            sel = np.isin(channel, s.channels)
            if s.window is not None:
                sel &= micro_mask(micro, [s.window])
            if s.phase is not None and phase is not None:
                sel &= phase == s.phase
            if np.any(sel):
                np.add.at(self.counts[k], slots[sel], 1)
        self.revision += 1

    def snapshot(self) -> dict[str, Any]:
        """The window's bins, oldest first: times (s, relative to the newest bin's end) and signed
        counts per stream."""
        if self.head < 0:
            order = np.arange(self.n_bins)
        else:
            order = (np.arange(self.head + 1, self.head + 1 + self.n_bins)) % self.n_bins
        t = (np.arange(self.n_bins) - self.n_bins + 1) * self.bin_s
        return {
            "window_s": self.window_s,
            "bin_s": self.bin_s,
            "t": t,
            "end_s": (self.head + 1) * self.bin_s if self.head >= 0 else 0.0,
            "streams": [
                {
                    "name": s.name,
                    "sign": s.sign,
                    "colour": s.colour,
                    "counts": s.sign * self.counts[k, order],
                }
                for k, s in enumerate(self.streams)
            ],
            "revision": self.revision,
        }
