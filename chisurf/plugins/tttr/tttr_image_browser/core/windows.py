"""The shared excitation-window pre-flight as the image browser uses a detector setup: the gates.

A tile of the mosaic is one detector: the photons of its routing channels inside its micro-time
gates (``micro_time_ranges``), summed over every window -- :func:`~.image.get_combo_stack` never
reads a window's ``window_range``, and :func:`~.image.group_channels_by_detector` folds the
``window_detector`` combinations into one tile per detector. So the setup's PIE windows do not
shape an image and are not checked here; its gates do, and are held against the excitation pulses
of the file (the check every PIE analysis runs, :mod:`chisurf.core.fluorescence.excitation`)
-- "PIE but no windows" is not a finding for an intensity image.

The gates are applied as channels of the data (:func:`~.image.compute_entry_stack_cached` hands
them to the image as they are): a setup's ``tttr_reading.micro_time_resolution`` does not convert
them, so they are checked that way too -- the check says what the tiles contain. *Use detected
windows* writes the data's channel width with the gates.

A file is read once per gate setting: the check is remembered for the file as it is on disk.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

__all__ = ["gate_check", "gate_setup", "gate_warnings", "has_gates", "remembered_check"]

#: Findings about the detectors' gates.
GATE_CODES = {"gate_outside_range", "gate_misses_pulse", "gate_empty"}
#: Checks remembered per (file, size, mtime, gates).
_MEMO: OrderedDict[tuple, Any] = OrderedDict()
_MEMO_SIZE = 64


def gate_setup(setup: Mapping | None) -> dict:
    """The parts of *setup* the gate check reads: the detectors and the reading routine without a
    channel width (no windows: an image does not use them; the gates are data channels)."""
    s = dict(setup or {})
    detectors = {
        str(k): dict(v) for k, v in (s.get("detectors") or {}).items() if isinstance(v, Mapping)
    }
    reading = {k: v for k, v in dict(s.get("tttr_reading") or {}).items()
               if k != "micro_time_resolution"}  # the gates are applied as data channels
    return {"windows": {}, "detectors": detectors, "tttr_reading": reading}


def has_gates(setup: Mapping | None) -> bool:
    """Whether *setup* gates any detector in micro time (else there is nothing to check)."""
    return any(d.get("micro_time_ranges") for d in gate_setup(setup)["detectors"].values())


def gate_check(tttr: Any, setup: Mapping | None):
    """The shared check of *setup*'s detector gates against *tttr* (``None``: nothing to say).

    Parameters
    ----------
    tttr : tttrlib.TTTR
        The photon file the mosaic is made of.
    setup : mapping
        The detector setup (``detectors`` with ``micro_time_ranges``, ``tttr_reading``).

    Returns
    -------
    WindowCheck or None
        The check with its gate findings only.
    """
    from chisurf.core.fluorescence.excitation import windows_preflight
    from chisurf.core.fluorescence.excitation.result import SEVERITIES

    if not has_gates(setup):
        return None
    try:
        check = windows_preflight(tttr, None, setup=gate_setup(setup))
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        return None
    if check is None:
        return None
    kept = [i for i in check.issues if i.code in GATE_CODES]
    status = SEVERITIES[max((SEVERITIES.index(i.severity) for i in kept), default=0)]
    return dataclasses.replace(check, issues=kept, status=status)


def _key(path: pathlib.Path, setup: Mapping | None) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    s = gate_setup(setup)
    gates = {k: v.get("micro_time_ranges") for k, v in s["detectors"].items()}
    chs = {k: v.get("chs") for k, v in s["detectors"].items()}
    return (str(path), st.st_size, st.st_mtime_ns, json.dumps([gates, chs], default=str))


def remembered_check(path: str | pathlib.Path, setup: Mapping | None, tttr: Any = None,
                     reading_routine: str | None = None):
    """:func:`gate_check` of the file at *path*, read (with *reading_routine*) only when it was
    not checked with these gates before; *tttr* is used when the caller has the file open."""
    if not has_gates(setup):
        return None
    path = pathlib.Path(path)
    key = _key(path, setup)
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


def gate_warnings(path: str | pathlib.Path, setup: Mapping | None, tttr: Any = None,
                  reading_routine: str | None = None) -> list[str]:
    """The pre-flight's line for the image of *path* (empty when the gates hold the pulses)."""
    from chisurf.core.fluorescence.excitation import windows_message

    line = windows_message(remembered_check(path, setup, tttr, reading_routine))
    return [line] if line else []
