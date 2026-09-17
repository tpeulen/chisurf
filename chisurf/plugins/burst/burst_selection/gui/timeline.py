"""Map between the concatenated measurement timeline and photon indices.

The diagnostic plots draw a *photon-index* range, and every file in the
selection is concatenated into one continuous index. That is the right unit for
the code and the wrong one for the person looking at the plot: a burst search
over six 300-second files draws eleven million photons into a trace one
thousand pixels wide, where nothing is visible except the envelope, and asking
"show me photons 4 000 000 to 4 500 000" is not a question anyone has.

The question people do have is "show me ten seconds, and let me walk through
the measurement". This module is the translation — Qt-free, so the arithmetic
can be tested without a window.

The timeline is *continuous across files*: file two starts where file one
ended, matching the offsets the trace plot already draws with. So a position on
it names both a time and a file, which is what makes a scroll position
meaningful when a selection holds more than one measurement.
"""

from __future__ import annotations

import dataclasses
import pathlib

import numpy as np

__all__ = ["Segment", "build_timeline", "span", "photon_range", "locate"]


@dataclasses.dataclass(frozen=True)
class Segment:
    """One file's place on the concatenated timeline.

    Attributes
    ----------
    index : int
        Position of the file in the selection.
    name : str
        File name, for the label that says what is on screen.
    start_s, stop_s : float
        Its span on the shared timeline, in seconds.
    first_photon : int
        Global index of its first photon.
    n_photons : int
        How many photons it contributes.
    macro_times : np.ndarray
        Its raw macro times, for the index lookup.
    resolution_s : float
        Macro-time resolution, in seconds.
    """

    index: int
    name: str
    start_s: float
    stop_s: float
    first_photon: int
    n_photons: int
    macro_times: np.ndarray
    resolution_s: float


def build_timeline(diagnostics, offsets_ms) -> list[Segment]:
    """Describe where every file sits on the shared timeline.

    Parameters
    ----------
    diagnostics : sequence of dict
        The tool's per-file diagnostics (``tttr``, ``selected``, ``path``).
    offsets_ms : sequence of float
        Each file's start on the shared timeline, in milliseconds — the same
        offsets the trace plot draws with, so the slider and the picture agree.

    Returns
    -------
    list of Segment
        Empty when nothing carries photons.
    """
    segments: list[Segment] = []
    first_photon = 0
    for index, diag in enumerate(diagnostics):
        tttr = diag.get("tttr")
        selected = diag.get("selected")
        n_photons = int(len(selected)) if selected is not None else 0
        macro_times = np.asarray(getattr(tttr, "macro_times", []) if tttr is not None else [])
        if macro_times.size == 0 or n_photons == 0:
            first_photon += n_photons
            continue
        try:
            resolution_s = float(tttr.header.macro_time_resolution)
        except Exception:
            resolution_s = 0.0
        start_s = float(offsets_ms[index]) / 1000.0 if index < len(offsets_ms) else 0.0
        duration_s = float(macro_times[-1] - macro_times[0]) * resolution_s
        path = diag.get("path")
        segments.append(
            Segment(
                index=index,
                name=pathlib.Path(str(path)).name if path else f"file {index + 1}",
                start_s=start_s,
                stop_s=start_s + duration_s,
                first_photon=first_photon,
                n_photons=n_photons,
                macro_times=macro_times,
                resolution_s=resolution_s,
            )
        )
        first_photon += n_photons
    return segments


def span(segments) -> float:
    """Total length of the timeline in seconds (``0.0`` when it is empty)."""
    return float(segments[-1].stop_s) if segments else 0.0


def photon_range(segments, start_s: float, stop_s: float) -> tuple[int, int]:
    """Global photon indices covering ``[start_s, stop_s]``.

    Returns ``(first, last)`` **inclusive**, which is the convention the tool's
    two range spin boxes use.
    """
    if not segments:
        return 0, 0
    total = segments[-1].first_photon + segments[-1].n_photons
    first, last = None, None
    for segment in segments:
        if segment.stop_s < start_s or segment.start_s > stop_s:
            continue
        local_lo = _local_index(segment, start_s)
        local_hi = _local_index(segment, stop_s)
        if first is None:
            first = segment.first_photon + local_lo
        last = segment.first_photon + local_hi
    if first is None:
        # The window fell in a gap between files — clamp to the nearer edge
        # rather than showing everything, which is what an empty range would do.
        edge = min(segments, key=lambda s: abs(s.start_s - start_s))
        return edge.first_photon, min(total - 1, edge.first_photon + edge.n_photons - 1)
    return int(first), int(min(total - 1, max(first, last)))


def locate(segments, start_s: float) -> Segment | None:
    """The file visible at ``start_s``, or the nearest one."""
    if not segments:
        return None
    for segment in segments:
        if segment.start_s <= start_s <= segment.stop_s:
            return segment
    return min(segments, key=lambda s: min(abs(s.start_s - start_s), abs(s.stop_s - start_s)))


def _local_index(segment: Segment, time_s: float) -> int:
    """Index within one file of the first photon at or after ``time_s``."""
    if segment.resolution_s <= 0.0:
        return 0
    offset = (time_s - segment.start_s) / segment.resolution_s + float(segment.macro_times[0])
    index = int(np.searchsorted(segment.macro_times, offset))
    return int(np.clip(index, 0, segment.n_photons - 1))
