"""A detector setup's windows and gates: read, converted, applied, checked -- in one place.

Every tool that takes a ChiSurf detector setup (``windows``, ``detectors`` with ``chs`` and
``micro_time_ranges``, ``tttr_reading``) reads it through these functions, so the windows mean the
same channels everywhere.

**Range dialects.** A setup's windows and gates are half-open ``[start, stop)`` (the setup editor:
"End: exclusive upper TAC channel"). Some engines take inclusive ``(start, stop)`` ranges
(tttrlib's BVA / TwoCDE / BurstFeature, ``CLSMImage.fill``, StreamDef); :func:`gates_to_inclusive`
and :func:`gates_from_inclusive` convert at that boundary, :func:`micro_mask` applies either.

* :func:`channel_map` -- the window × detector stream map (``"<window>_<detector>"`` entries of
  ``{window_range, detector_chs, micro_time_range}``);
* :func:`polarization_channels` -- a detector's (parallel, perpendicular) routing channels;
* :func:`merge_gates` -- detected gates written into a detectors mapping;
* :func:`format_ranges` -- ``"prompt 50–1613, delayed 1613–3125"``;
* :func:`gate_check`, :func:`remembered_gate_check`, :data:`GATE_CODES` -- the pre-flight of a
  tool that applies only detector gates (an image, a trace), its findings restricted to gates.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

__all__ = [
    "GATE_CODES",
    "channel_map",
    "format_ranges",
    "gate_check",
    "gate_setup",
    "gates_from_inclusive",
    "gates_to_inclusive",
    "merge_gates",
    "micro_mask",
    "polarization_channels",
    "remembered_gate_check",
]

#: Findings about the detectors' gates (what a gate-only tool reports).
GATE_CODES = frozenset({"gate_outside_range", "gate_misses_pulse", "gate_empty"})


def _detectors(setup: Mapping | None) -> dict[str, dict]:
    s = dict((setup or {}).get("data", setup or {})) if isinstance(setup, Mapping) else {}
    return {str(k): dict(v) for k, v in (s.get("detectors") or {}).items() if isinstance(v, Mapping)}


# -- range dialects ----------------------------------------------------------------------------------


def gates_to_inclusive(gates: Sequence[Sequence[int]] | None) -> list[tuple[int, int]]:
    """Setup gates ``[start, stop)`` as inclusive engine ranges ``(start, stop - 1)``."""
    return [(int(g[0]), max(int(g[0]), int(g[1]) - 1)) for g in (gates or ()) if len(g) >= 2]


def gates_from_inclusive(ranges: Sequence[Sequence[int]] | None) -> list[list[int]]:
    """Inclusive engine ranges ``(start, stop)`` as setup gates ``[start, stop + 1)``."""
    return [[int(r[0]), int(r[1]) + 1] for r in (ranges or ()) if len(r) >= 2]


def micro_mask(micro: np.ndarray, ranges: Sequence[Sequence[int]] | None, *,
               inclusive: bool = False) -> np.ndarray:
    """Photons whose micro time is in any of *ranges* (no ranges: every photon).

    *ranges* are half-open ``[start, stop)``, or inclusive ``(start, stop)`` with *inclusive*.
    """
    micro = np.asarray(micro)
    if not ranges:
        return np.ones(micro.shape, dtype=bool)
    keep = np.zeros(micro.shape, dtype=bool)
    for r in ranges:
        lo, hi = int(r[0]), int(r[1])
        keep |= (micro >= lo) & ((micro <= hi) if inclusive else (micro < hi))
    return keep


# -- reading a setup ---------------------------------------------------------------------------------


def channel_map(setup: Mapping | None, *, ungated_means_all: bool = False,
                per_detector_without_windows: bool = False) -> dict[str, list[dict]]:
    """The window × detector stream map of a setup.

    ``{"<window>_<detector>": [{"window_range": [a, b), "detector_chs": [...],
    "micro_time_range": [c, d)}, ...]}`` -- one entry per gate of the detector.

    Parameters
    ----------
    setup : mapping
        The detector setup.
    ungated_means_all : bool
        A detector without gates gets one entry with ``micro_time_range`` ``None`` (all photons)
        instead of none.
    per_detector_without_windows : bool
        A setup without windows gives one stream per detector (``"<detector>"``, window ``None``)
        instead of none.
    """
    s = dict((setup or {}).get("data", setup or {})) if isinstance(setup, Mapping) else {}
    windows = dict(s.get("windows") or {})
    if not windows and per_detector_without_windows:
        windows = {"": None}
    out: dict[str, list[dict]] = {}
    for wname, wrange in windows.items():
        for dname, info in _detectors(s).items():
            gates = list(info.get("micro_time_ranges") or [])
            if not gates and ungated_means_all:
                gates = [None]
            key = f"{wname}_{dname}" if wname else dname
            out[key] = [
                {"window_range": wrange, "detector_chs": list(info.get("chs") or []),
                 "micro_time_range": g}
                for g in gates
            ]
    return out


def polarization_channels(detector: Mapping) -> tuple[list[int], list[int]]:
    """A detector's ``(parallel, perpendicular)`` routing channels: explicit ``ch_p`` / ``ch_s``,
    else ``chs`` split even (parallel) / odd (perpendicular); one channel is both."""
    ch_p = [int(x) for x in (detector.get("ch_p") or [])]
    ch_s = [int(x) for x in (detector.get("ch_s") or [])]
    if ch_p or ch_s:
        return ch_p, ch_s
    chs = [int(x) for x in (detector.get("chs") or [])]
    if not chs:
        return [], []
    return chs[::2], (chs[1::2] if len(chs) > 1 else chs)


def merge_gates(detectors: Mapping[str, Mapping], gates: Mapping[str, Sequence]) -> dict:
    """*detectors* with the gates of *gates* (``{detector: [[start, stop), ...]}``) written in."""
    out = {str(k): dict(v) for k, v in (detectors or {}).items()}
    for name, ranges in (gates or {}).items():
        if name in out:
            out[name]["micro_time_ranges"] = [[int(r[0]), int(r[1])] for r in ranges]
    return out


def format_ranges(ranges: Mapping[str, Sequence]) -> str:
    """``{"prompt": [50, 1613]}`` (or a gate list per name) as ``"prompt 50–1613"``."""
    parts = []
    for name, r in (ranges or {}).items():
        rs = r if r and isinstance(r[0], (list, tuple)) else [r]
        parts.append(f"{name} " + ", ".join(f"{int(a)}–{int(b)}" for a, b in rs))
    return ", ".join(parts)


# -- the gate-only pre-flight ------------------------------------------------------------------------


def gate_setup(setup: Mapping | None) -> dict:
    """What a gate-only check reads of *setup*: the detectors, the reading routine without a
    channel width (the tool applies the gates as the data's channels), no windows."""
    s = dict((setup or {}).get("data", setup or {})) if isinstance(setup, Mapping) else {}
    reading = {k: v for k, v in dict(s.get("tttr_reading") or {}).items()
               if k != "micro_time_resolution"}
    return {"windows": {}, "detectors": _detectors(s), "tttr_reading": reading}


def gate_check(tttr: Any, setup: Mapping | None):
    """The pre-flight of *setup*'s detector gates against *tttr*, its findings restricted to the
    gates (``None`` when no detector is gated or nothing can be checked)."""
    from .preflight import windows_preflight
    from .result import SEVERITIES

    s = gate_setup(setup)
    if not any(d.get("micro_time_ranges") for d in s["detectors"].values()):
        return None
    try:
        check = windows_preflight(tttr, None, setup=s)
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        return None
    if check is None:
        return None
    kept = [i for i in check.issues if i.code in GATE_CODES]
    status = SEVERITIES[max((SEVERITIES.index(i.severity) for i in kept), default=0)]
    return dataclasses.replace(check, issues=kept, status=status)


_MEMO: OrderedDict[tuple, Any] = OrderedDict()
_MEMO_SIZE = 64


def remembered_gate_check(path: str | pathlib.Path, setup: Mapping | None, tttr: Any = None,
                          reading_routine: str | None = None):
    """:func:`gate_check` of the file at *path*, read only when it was not checked with these
    gates before (keyed on path, size, mtime, gates and channels); *tttr* is used when the caller
    has the file open."""
    s = gate_setup(setup)
    if not any(d.get("micro_time_ranges") for d in s["detectors"].values()):
        return None
    path = pathlib.Path(path)
    try:
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime_ns, json.dumps(
            {k: [v.get("micro_time_ranges"), v.get("chs")] for k, v in s["detectors"].items()},
            default=str, sort_keys=True))
    except OSError:
        key = None
    if key is not None and key in _MEMO:
        _MEMO.move_to_end(key)
        return _MEMO[key]
    if tttr is None:
        from chisurf.core.fio.staging import open_tttr

        try:
            tttr = open_tttr(path, reading_routine)
        except Exception:  # noqa: BLE001 - an unreadable file has no gates to check
            return None
    check = gate_check(tttr, setup)
    if key is not None:
        _MEMO[key] = check
        while len(_MEMO) > _MEMO_SIZE:
            _MEMO.popitem(last=False)
    return check
