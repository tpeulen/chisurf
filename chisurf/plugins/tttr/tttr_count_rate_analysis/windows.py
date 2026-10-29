"""The shared excitation-window pre-flight as the count rates use a detector setup.

A count rate per ``window_detector`` channel counts the photons of the detector's routing channels
inside its micro-time gate *and* the PIE window (:func:`~.cli.get_channels_from_setup`), so both
are held against the excitation pulses the measurement shows before the photons are counted --
the check every PIE analysis runs (:mod:`chisurf.core.fluorescence.excitation`). A setup without
windows counts per detector: then only its gates are checked, and "no windows" is not a finding.
The line it gives goes into the warnings (CLI output, the tool's status line); nothing is changed.

The counts apply the windows and gates as channels of the data (:meth:`~.gui.view_model.
CountRateViewModel._apply_range`, :func:`~.cli.calculate_count_rates`): a setup's
``tttr_reading.micro_time_resolution`` does not convert them. So they are checked as they are
applied -- in the data's channels -- and the check says what the counts contain, not what a
converted setup would have meant. *Use detected windows* writes the data's channel width with them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

__all__ = ["preflight_setup", "window_check", "window_warning"]

#: Findings about the detectors' gates: what a setup without windows can be checked for.
GATE_CODES = {"gate_outside_range", "gate_misses_pulse", "gate_empty"}


def preflight_setup(setup: Mapping | None) -> dict:
    """The parts of *setup* the pre-flight reads: the windows that are ranges (an ``all: None``
    window counts every photon and has nothing to check), the detectors, the reading routine
    without a channel width (the counts apply the ranges as the data's channels)."""
    s = dict(setup or {})
    windows = {
        str(k): [int(v[0]), int(v[1])]
        for k, v in (s.get("windows") or {}).items()
        if isinstance(v, (list, tuple)) and len(v) == 2 and None not in v
    }
    detectors = {
        str(k): dict(v) for k, v in (s.get("detectors") or {}).items() if isinstance(v, Mapping)
    }
    reading = {k: v for k, v in dict(s.get("tttr_reading") or {}).items()
               if k != "micro_time_resolution"}  # the ranges are applied as data channels
    return {"windows": windows, "detectors": detectors, "tttr_reading": reading}


def window_check(tttr: Any, setup: Mapping | None):
    """The shared check of *setup*'s windows and gates against *tttr* (``None``: nothing to say).

    Parameters
    ----------
    tttr : tttrlib.TTTR or path
        The measurement the count rates are taken from.
    setup : mapping
        The detector setup (``windows``, ``detectors``, ``tttr_reading``).

    Returns
    -------
    WindowCheck or None
    """
    from chisurf.core.fluorescence.excitation import windows_preflight
    from chisurf.core.fluorescence.excitation.result import SEVERITIES

    s = preflight_setup(setup)
    if not s["detectors"] and not s["windows"]:
        return None
    try:
        check = windows_preflight(tttr, None, setup=s)
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        return None
    if check is None or s["windows"]:
        return check
    kept = [i for i in check.issues if i.code in GATE_CODES]
    status = SEVERITIES[max((SEVERITIES.index(i.severity) for i in kept), default=0)]
    return dataclasses.replace(check, issues=kept, status=status)


def window_warning(tttr: Any, setup: Mapping | None) -> str | None:
    """The pre-flight's one line for *tttr* (``None`` when the windows and gates hold the pulses)."""
    from chisurf.core.fluorescence.excitation import windows_message

    return windows_message(window_check(tttr, setup))
