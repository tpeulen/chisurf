"""Qt-free binning of a TTTR file into intensity traces.

This reproduces ``IntensityTrace.process_ptu`` / ``_process_routing_channels`` of the legacy
Qt tool (``chisurf.plugins.tttr.intensity_trace``) with vectorised numpy and with the detector
mapping (or channel list) passed as an argument instead of read from the global saved-setups
store. Imports are numpy, tttrlib (guarded) and the standard library only.

Binning rule (tttrlib ``compute_intensity_trace``, which the legacy engine calls on a sub-TTTR
of the selected photons): ``clocks_per_bin = max(1, floor(window / macro_time_resolution))``,
photon *t* falls into bin ``t // clocks_per_bin``, and a trace has
``last_macro_time // clocks_per_bin + 1`` bins, so each trace is as long as *its own* last
photon. The traces are then zero-padded to the longest one.
"""

from __future__ import annotations

import logging
import math
import pathlib
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

try:  # pragma: no cover - exercised implicitly
    import tttrlib
except Exception:  # pragma: no cover - tttrlib is an optional dependency here
    tttrlib = None

logger = logging.getLogger(__name__)

#: ``(time_axis, counts, labels)``: *counts* is ``(bins, series)`` float64.
Trace = tuple[np.ndarray, np.ndarray, list[str]]


def _empty() -> Trace:
    return np.array([]), np.zeros((0, 0)), []


def _open(tttr: Any) -> Any:
    """Return a TTTR object for a path (or pass an object through)."""
    if isinstance(tttr, (str, pathlib.Path)):
        if tttrlib is None:
            raise ImportError("tttrlib is required to read TTTR files")
        return tttrlib.TTTR(str(tttr))
    return tttr


def _bin_macro_times(macro: np.ndarray, clocks_per_bin: int) -> np.ndarray:
    """Counts per bin of the (non-decreasing) macro times of one trace, as tttrlib does."""
    if macro.size == 0:
        return np.array([], dtype=float)
    n_bins = int(macro[-1]) // clocks_per_bin + 1
    bins = np.minimum(macro.astype(np.uint64) // np.uint64(clocks_per_bin), np.uint64(n_bins - 1))
    return np.bincount(bins.astype(np.int64), minlength=n_bins).astype(float)


def _pad(traces: list[np.ndarray], window_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Zero-pad *traces* to a common length; return ``(time_axis, counts)``."""
    num_bins = max((len(t) for t in traces), default=0)
    padded = np.zeros((num_bins, len(traces))) if num_bins > 0 else np.zeros((0, 0))
    for i, t in enumerate(traces):
        if len(t) > 0:
            padded[: len(t), i] = t
    time_axis = np.arange(num_bins) * window_s if num_bins > 0 else np.array([])
    return time_axis, padded


def _clocks_per_bin(tttr: Any, window_s: float) -> int | None:
    resolution = float(tttr.header.macro_time_resolution)
    if window_s <= 0.0 or resolution <= 0.0:
        return None
    return max(1, int(math.floor(window_s / resolution)))


def bin_trace(
    tttr: Any,
    time_window_s: float,
    detectors: Mapping[str, Mapping[str, Any]] | None = None,
    channels: Iterable[int] | None = None,
    selected: Sequence[str] | None = None,
) -> Trace:
    """Bin a TTTR file or object into per-detector or per-routing-channel counts.

    Parameters
    ----------
    tttr
        Path of a TTTR file, or a ``tttrlib.TTTR`` object.
    time_window_s
        Bin width in seconds.
    detectors
        Detector mapping ``{name: {"chs": [...], "micro_time_ranges": [[lo, hi], ...]}}``.
        A detector counts the photons whose routing channel is in ``chs`` and, when
        ``micro_time_ranges`` is not empty, whose micro time lies in one of the (inclusive)
        ranges. A detector without ``chs`` is skipped; a detector without any photon after
        gating gives an all-zero column. Series are in mapping order.
    channels
        Used only when *detectors* is empty or ``None``: routing channels, one series each,
        labelled ``"Ch<n>"`` (the legacy engine's label). A channel without photons gives an
        all-zero column. With neither *detectors* nor *channels*, every routing channel used
        in the file is binned (ascending).
    selected
        Optional detector names restricting (and ordering) *detectors*; unknown names are
        ignored. ``None`` or empty means all detectors.

    Returns
    -------
    tuple
        ``(time_axis, counts, labels)``: *time_axis* is ``arange(bins) * time_window_s``,
        *counts* is ``(bins, series)`` float64, *labels* a list of ``str``. When nothing can
        be binned: ``(array([]), zeros((0, 0)), [])``.

    Notes
    -----
    Differences from the legacy engine, all in cases where it fails: the legacy fallback
    (no detector mapping) raised ``KeyError``/returned an empty trace when called with a
    channel list, because it indexed a dict with ``0``; here an empty or absent mapping uses
    *channels*, and with neither, all used routing channels. Series values and shapes for a
    detector mapping and for single channels are identical to the legacy engine.
    """
    window_s = float(time_window_s)
    obj = _open(tttr)
    rc = np.asarray(obj.routing_channels)
    macro = np.asarray(obj.macro_times)
    cpb = _clocks_per_bin(obj, window_s)
    if cpb is None or macro.size == 0:
        return _empty()

    labels: list[str] = []
    traces: list[np.ndarray] = []

    if detectors:
        names = list(detectors.keys())
        if selected:
            names = [n for n in selected if n in detectors]
            if not names:
                return _empty()
        micro = None
        for name in names:
            info = detectors[name] or {}
            det_chs = info.get("chs", []) or []
            if not det_chs:
                logger.warning("binning: detector %r has no routing channels", name)
                continue
            mask = np.isin(rc, np.array(det_chs, dtype=rc.dtype))
            ranges = info.get("micro_time_ranges", []) or []
            if ranges:
                if micro is None:
                    micro = np.asarray(obj.micro_times)
                gate = np.zeros(mask.shape, dtype=bool)
                for rng in ranges:
                    if rng is not None and len(rng) == 2:
                        try:
                            lo, hi = int(rng[0]), int(rng[1])
                        except Exception:
                            continue
                        gate |= (micro >= lo) & (micro <= hi)
                mask &= gate
            traces.append(_bin_macro_times(macro[mask], cpb))
            labels.append(str(name))
    else:
        if channels is None:
            wanted = sorted(int(c) for c in obj.get_used_routing_channels())
        else:
            wanted = [int(c) for c in channels]
        for ch in wanted:
            traces.append(_bin_macro_times(macro[rc == ch], cpb))
            labels.append(f"Ch{ch}")

    time_axis, padded = _pad(traces, window_s)
    return time_axis, padded, labels
