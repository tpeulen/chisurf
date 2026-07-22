"""Parse a shared detector-setup payload into MLE fit inputs.

Every polarisation-resolved MLE consumer (the pixel-wise and molecule-wise
imaging tools, and the burst wizard) receives the *same* detector-definition
payload from the shared setup (`DetectorWizardPage` /
:class:`~...setup_client.DetectorSetupClient`): a mapping of detector name to
``{"chs", "micro_time_ranges"/"mtr", "g_factor", "l1", "l2", ...}``.

Each tool used to re-parse that payload by hand and, crucially, each imaging
tool dropped ``g_factor``/``l1``/``l2`` on the floor — reading only ``chs`` and
the micro-time range — so the polarisation corrections entered in the setup
never reached the fit (it silently ran at ``g=1, l1=l2=0``). This module is the
one parser they share, so the channels, fit window **and** the polarisation
corrections are extracted identically and in one place.
"""

from __future__ import annotations

import dataclasses
import typing


@dataclasses.dataclass
class DetectorSetup:
    """Fit-ready view of a detector-setup payload.

    Attributes
    ----------
    channels : list[int]
        All routing channels, in first-seen order.
    channels_parallel, channels_perpendicular : list[int]
        ``channels`` split by the interleaved convention (even = parallel,
        odd = perpendicular). Tools that keep a single channel list use
        ``channels``; tools that need the VV/VH split use these.
    micro_range : tuple[int, int] | None
        The first detector's micro-time range, or ``None`` if none was given.
    g_factor, l1, l2 : float | None
        Polarisation corrections from the first detector that supplies them,
        or ``None`` when the payload does not carry them (so callers can keep
        their own default rather than forcing one).
    """

    channels: list[int] = dataclasses.field(default_factory=list)
    channels_parallel: list[int] = dataclasses.field(default_factory=list)
    channels_perpendicular: list[int] = dataclasses.field(default_factory=list)
    micro_range: tuple[int, int] | None = None
    g_factor: float | None = None
    l1: float | None = None
    l2: float | None = None


def _first_float(det: typing.Mapping, key: str) -> float | None:
    value = det.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_detector_setup(payload: typing.Mapping | None) -> DetectorSetup:
    """Extract channels, micro-time range and polarisation corrections.

    Parameters
    ----------
    payload : mapping or None
        The shared setup payload, expected to hold ``payload["detectors"]`` as a
        mapping of detector name to its definition dict. A falsy payload yields
        an empty :class:`DetectorSetup`.

    Returns
    -------
    DetectorSetup
    """
    result = DetectorSetup()
    if not payload:
        return result
    detectors = payload.get("detectors") or {}
    for det in detectors.values():
        if not isinstance(det, typing.Mapping):
            continue
        for ch in det.get("chs", []) or []:
            ich = int(ch)
            if ich not in result.channels:
                result.channels.append(ich)
                bucket = (
                    result.channels_parallel
                    if ich % 2 == 0
                    else result.channels_perpendicular
                )
                bucket.append(ich)
        if result.micro_range is None:
            ranges = det.get("mtr") or det.get("microtime_ranges") or det.get("micro_time_ranges")
            if ranges:
                first = ranges[0]
                if first is not None and len(first) == 2:
                    result.micro_range = (int(first[0]), int(first[1]))
        # Polarisation corrections: take them from the first detector that
        # actually carries them, so a later detector left at defaults cannot
        # blank a real calibration.
        if result.g_factor is None:
            result.g_factor = _first_float(det, "g_factor")
        if result.l1 is None:
            result.l1 = _first_float(det, "l1")
        if result.l2 is None:
            result.l2 = _first_float(det, "l2")
    return result
