"""Burst-selection diagnostics shared by the Qt tool and the emtk app: plain numpy over TTTR objects and burst tables.

Everything here used to live in the Qt ``BurstSelectionTool`` (``gui/tool.py``), so the native app could not reach
it without importing Qt. The Qt tool now imports these functions from here; nothing in this module imports a
toolkit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    numeric_column,
    row_count,
    take_columns,
)

from .adapter import (
    PROXIMITY_RATIO_COLUMN,
    UI_COLUMNS,
    burst_rows_for_display,
    make_ui_dataframe,
    proximity_ratio_from_frame,
)

#: Display defaults of the Qt tool (``gui/tool.py``), kept identical so the two show the same thing.
DEFAULT_HISTOGRAM_BINS = 61
DEFAULT_TRACE_BIN_WIDTH_MS = 0.25
DEFAULT_DECAY_BINS = 8
DEFAULT_BURST_BINS = 51
DEFAULT_PLOT_MAX = 100000
HISTOGRAM_FEATURES = [*UI_COLUMNS, PROXIMITY_RATIO_COLUMN]


def normalize_filetype(filetype: str | None) -> str | None:
    """The detector setup's file type for ``tttrlib`` (``None`` = infer it)."""
    if not filetype or str(filetype).strip().lower() == "auto":
        return None
    return str(filetype).strip()


def setup_summary(setup_name: str | None, filetype: str | None) -> str:
    """A compact detector setup summary for the status text."""
    if not setup_name:
        return "Detector setup: custom/default"
    if filetype:
        return f"Detector setup: {setup_name} (file type: {filetype})"
    return f"Detector setup: {setup_name} (file type: auto)"


def histogram_data_from_frame(frame, feature: str) -> np.ndarray:
    """Numeric histogram data excluding Margarita zero separator rows."""
    if feature == PROXIMITY_RATIO_COLUMN:
        data = proximity_ratio_from_frame(burst_rows_for_display(frame))
        if data is not None:
            return data[np.isfinite(data)]
    data = numeric_column(burst_rows_for_display(frame), feature)
    return data[np.isfinite(data)]


def as_count_rate_hz(counts, bin_width_ms: float):
    """Photons per bin as a **count rate in Hz** (counts are not comparable across bin widths; a rate is).

    Returns the counts unchanged if the bin width is not usable (a zero width would fill the trace with
    infinities).
    """
    values = np.asarray(counts, dtype=float)
    if not np.isfinite(bin_width_ms) or bin_width_ms <= 0.0:
        return values
    return values * 1000.0 / float(bin_width_ms)


def trace_rate_hz(tttr_slice, bin_width_s: float, bin_width_ms: float, offset_s: float):
    """A photon slice as ``(time_s, rate_hz)``, without the empty run in front.

    ``get_intensity_trace`` bins from macro time **zero of the file**, not from the first photon it is given, so a
    ten-second window taken at 65 s came back as a 75-second trace whose first bins are empty. The leading bins are
    dropped and the time axis is shifted by as many, so the trace still sits where it belongs on the file's clock.
    """
    trace = np.asarray(tttr_slice.get_intensity_trace(time_window_length=bin_width_s), dtype=float)
    macro_times = np.asarray(getattr(tttr_slice, "macro_times", []))
    skip = 0
    if macro_times.size and trace.size:
        try:
            resolution_s = float(tttr_slice.header.macro_time_resolution)
        except Exception:
            resolution_s = 0.0
        if resolution_s > 0.0 and bin_width_s > 0.0:
            skip = int(float(macro_times[0]) * resolution_s / bin_width_s)
            skip = max(0, min(skip, trace.size))
            trace = trace[skip:]
    time_s = (np.arange(trace.size) + skip) * bin_width_s + offset_s
    return time_s, as_count_rate_hz(trace, bin_width_ms)


def macro_time_offsets_ms(diagnostics: list[dict[str, Any]]) -> list[float]:
    """Per-file macro-time offsets that continue across file boundaries."""
    offsets: list[float] = []
    previous_end: float | None = None
    for diag in diagnostics:
        tttr = diag["tttr"]
        macro_times = getattr(tttr, "macro_times", None)
        if macro_times is None:
            offsets.append(0.0)
            continue
        macro_times = np.asarray(macro_times)
        if macro_times.size == 0:
            offsets.append(0.0)
            continue
        resolution_ms = float(tttr.header.macro_time_resolution) * 1000.0
        first = float(macro_times[0])
        offset_ticks = 0.0 if previous_end is None else previous_end - first
        offsets.append(offset_ticks * resolution_ms)
        # The end on the *continued* axis, not the file's own.
        previous_end = float(macro_times[-1]) + offset_ticks
    return offsets


def delta_macro_time_ms(tttr: Any, offset_ticks: float = 0.0) -> np.ndarray:
    """Delta macro times in milliseconds."""
    macro_times = tttr.macro_times
    d_t = np.diff(macro_times, prepend=macro_times[0] - offset_ticks)
    return d_t * tttr.header.macro_time_resolution * 1000.0


def burst_durations_ms(diag: dict[str, Any]) -> np.ndarray:
    """Burst durations in milliseconds for one diagnostic entry."""
    tttr = diag.get("tttr")
    start_stop = diag.get("start_stop")
    if tttr is None or start_stop is None:
        return np.array([], dtype=float)
    macro_times = np.asarray(tttr.macro_times)
    if macro_times.size == 0:
        return np.array([], dtype=float)
    resolution_ms = float(tttr.header.macro_time_resolution) * 1000.0
    durations = [
        float(macro_times[stop] - macro_times[start]) * resolution_ms
        for start, stop in np.asarray(start_stop, dtype=int).reshape(-1, 2)
        if 0 <= start < stop < macro_times.size
    ]
    return np.asarray(durations, dtype=float)


def gate_mismatch_warning(tttr, detectors) -> str | None:
    """Warn when the detector gates cannot match the photons at all (an unconverted micro-second ALEX file).

    Such a file carries the laser alternation in the macro time and its micro time is all zero, so a setup that
    gates detectors on a micro-time range selects nothing and every per-detector count is zero, while the search
    still finds bursts.
    """
    if not detectors:
        return None
    gated = [
        name
        for name, info in detectors.items()
        if any(int(hi) > int(lo) for lo, hi in (info or {}).get("micro_time_ranges", []) or [])
    ]
    if not gated:
        return None
    try:
        micro_times = np.asarray(tttr.micro_times)
    except Exception:
        return None
    if micro_times.size == 0 or int(micro_times.max()) > 0:
        return None
    return (
        "This measurement has no micro-time — every photon reads 0 — but "
        f"the detector setup gates {', '.join(sorted(gated))} on a "
        "micro-time range, so those detectors select no photons and every "
        "per-detector count is zero.\n\n"
        "That is what an unconverted µs-ALEX file looks like: the laser "
        "alternation is still in the macro time. Run the Alternation step "
        "(and press its convert button) before searching bursts."
    )


def output_formats_for_inputs(paths) -> list[str]:
    """Where a run's results go, decided by what was loaded: ``"pto"`` into a container, ``"bur"`` beside a file."""
    from chisurf.core.fio.pto import SUFFIX

    paths = list(paths or [])
    if not paths:
        return ["pto"]
    containers = [p for p in paths if Path(p).suffix.lower() == SUFFIX]
    formats = []
    if containers:
        formats.append("pto")
    if len(containers) != len(paths):
        formats.append("bur")
    return formats


def display_frame(frames: list, file_indices: list[int] | None = None):
    """The burst table the GUI shows: the frames stacked, tagged with ``File Idx``, the UI columns first."""
    from chisurf.core.fio.fluorescence.burst_container import as_table

    indexed = []
    for index, frame in enumerate(frames):
        # ``.copy()`` is load-bearing: "File Idx" is added below, and ``as_table`` hands a store straight back.
        tagged = as_table(frame).copy()
        which = file_indices[index] if file_indices is not None and index < len(file_indices) else index
        tagged["File Idx"] = np.full(row_count(tagged), which, dtype=np.int64)
        indexed.append(tagged)
    ui_frame = make_ui_dataframe(concat_stores(indexed))
    present = column_names(ui_frame)
    order = (
        [c for c in ("File Idx",) if c in present]
        + [c for c in UI_COLUMNS if c in present and c != "File Idx"]
        + [c for c in present if c not in UI_COLUMNS and c != "File Idx"]
    )
    return take_columns(ui_frame, order)


__all__ = [
    "DEFAULT_BURST_BINS",
    "DEFAULT_DECAY_BINS",
    "DEFAULT_HISTOGRAM_BINS",
    "DEFAULT_PLOT_MAX",
    "DEFAULT_TRACE_BIN_WIDTH_MS",
    "HISTOGRAM_FEATURES",
    "as_count_rate_hz",
    "burst_durations_ms",
    "delta_macro_time_ms",
    "display_frame",
    "gate_mismatch_warning",
    "histogram_data_from_frame",
    "macro_time_offsets_ms",
    "normalize_filetype",
    "output_formats_for_inputs",
    "setup_summary",
    "trace_rate_hz",
]
