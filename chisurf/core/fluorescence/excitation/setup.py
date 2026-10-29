"""What ChiSurf's tools do with a detector setup's windows and gates beyond reading them.

Reading a setup -- its detectors, gates, windows, reading units, the window x detector stream map,
the half-open/inclusive range dialects, rescaling to another channel width, the photon mask -- is
tttrlib's (``tttrlib.setup_detectors``, ``setup_gates``, ``setup_windows``,
``setup_micro_time_resolution``, ``setup_channel_map``, ``ranges_to_inclusive``,
``rescale_micro_time_ranges``, ``micro_time_mask``, ``polarization_channels``): one reader for
tttrlib's ``from_setup``, ChiSurf and ndXplorer. What is here builds on the window check:

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

__all__ = [
    "GATE_CODES",
    "format_ranges",
    "gate_check",
    "gate_setup",
    "merge_gates",
    "remembered_gate_check",
]

#: Findings about the detectors' gates (what a gate-only tool reports).
GATE_CODES = frozenset({"gate_outside_range", "gate_misses_pulse", "gate_empty"})


def _detectors(setup: Mapping | None) -> dict[str, dict]:
    s = dict((setup or {}).get("data", setup or {})) if isinstance(setup, Mapping) else {}
    return {str(k): dict(v) for k, v in (s.get("detectors") or {}).items() if isinstance(v, Mapping)}


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
