"""Per-file time regions: which stretches of each measurement enter the correlator, Qt-free.

The user draws regions on a file's count-rate trace (Files & Steps); a photon is used when its macro time falls in one
of its file's regions. A file without regions is used whole, so drawing nothing changes nothing. Times are seconds
from macro time 0, the origin of ``tttrlib.TTTR.get_intensity_trace`` and of the trace drawn here.
"""

from __future__ import annotations

import pathlib

import numpy as np

#: Most bins a drawn count-rate trace has; longer measurements get wider bins.
MAX_TRACE_BINS = 4000


def file_key(path) -> str:
    """The key a file's regions are stored under (its resolved path)."""
    return str(pathlib.Path(str(path)).resolve())


def merge_intervals(intervals) -> list[tuple[float, float]]:
    """Sorted, non-overlapping ``(start, stop)`` intervals; touching or overlapping ones are joined, empty ones dropped."""
    spans = sorted((min(a, b), max(a, b)) for a, b in intervals if float(a) != float(b))
    out: list[tuple[float, float]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((float(a), float(b)))
    return out


def times_s(tttr) -> np.ndarray:
    """Photon macro times in seconds."""
    return np.asarray(tttr.macro_times, dtype=np.float64) * float(
        tttr.header.macro_time_resolution
    )


def interval_mask(t: np.ndarray, intervals) -> np.ndarray:
    """``True`` where *t* lies in one of the sorted, disjoint *intervals* (start inclusive, stop exclusive)."""
    if not intervals:
        return np.ones(len(t), dtype=bool)
    edges = np.asarray(intervals, dtype=np.float64).ravel()
    # An odd insertion index lies between a start and its stop.
    return (np.searchsorted(edges, t, side="right") % 2).astype(bool)


def count_rate_trace(tttr, max_bins: int = MAX_TRACE_BINS) -> tuple[np.ndarray, np.ndarray, float]:
    """``(bin_start_s, rate_kHz, duration_s)`` of *tttr*, at most *max_bins* bins (1 ms or wider)."""
    t = times_s(tttr)
    if t.size == 0:
        return np.zeros(0), np.zeros(0), 0.0
    duration = float(t[-1])
    width = max(1e-3, duration / max(1, int(max_bins)))
    counts = np.bincount((t / width).astype(np.int64))
    x = np.arange(counts.size) * width
    return x, counts / (width * 1000.0), duration


class TimeRegions:
    """The regions of every file, keyed by :func:`file_key`."""

    def __init__(self) -> None:
        self.by_file: dict[str, list[tuple[float, float]]] = {}

    def get(self, path) -> list[tuple[float, float]]:
        return list(self.by_file.get(file_key(path), []))

    def set(self, path, intervals) -> None:
        merged = merge_intervals(intervals)
        key = file_key(path)
        if merged:
            self.by_file[key] = merged
        else:
            self.by_file.pop(key, None)

    def add(self, path, start: float, stop: float) -> None:
        self.set(path, [*self.get(path), (start, stop)])

    def remove_at(self, path, t: float) -> bool:
        """Remove the region of *path* that contains time *t*; whether one did."""
        regions = self.get(path)
        kept = [(a, b) for a, b in regions if not a <= t <= b]
        if len(kept) == len(regions):
            return False
        self.set(path, kept)
        return True

    def clear(self, path=None) -> None:
        if path is None:
            self.by_file.clear()
        else:
            self.by_file.pop(file_key(path), None)

    def copy_to(self, source, targets) -> None:
        """Give every file in *targets* the regions of *source*."""
        regions = self.get(source)
        for target in targets:
            self.set(target, regions)

    def total(self, path) -> float:
        return float(sum(b - a for a, b in self.get(path)))

    def mask(self, path, tttr) -> np.ndarray:
        """The photons of *tttr* (read from *path*) inside its regions; all ``True`` without regions."""
        regions = self.get(path)
        if not regions:
            return np.ones(len(tttr), dtype=bool)
        return interval_mask(times_s(tttr), regions)

    def export_settings(self) -> dict:
        return {k: [list(r) for r in v] for k, v in self.by_file.items()}

    def restore_settings(self, state: dict) -> None:
        self.by_file = {}
        for key, intervals in (state or {}).items():
            try:
                self.set(key, [(float(a), float(b)) for a, b in intervals])
            except (TypeError, ValueError):
                continue


__all__ = [
    "MAX_TRACE_BINS",
    "TimeRegions",
    "count_rate_trace",
    "file_key",
    "interval_mask",
    "merge_intervals",
    "times_s",
]
