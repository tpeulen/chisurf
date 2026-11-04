"""The photon streams the burst engines apply, as a detector setup -- and their window pre-flight.

BVA, 2CDE, H2MM, the MFD preparation and the burst workflow split each burst's photons into
streams by routing channel *and* micro-time range. The engines (``tttrlib.BVA`` /
``tttrlib.TwoCDE`` / ``BurstFeature``, :class:`~chisurf.core.fluorescence.burst.photons.StreamDef`)
keep a photon when ``start <= micro_time <= stop`` -- their ranges are **inclusive**. A setup's
detector gates (``detectors.*.micro_time_ranges``) are ``[start, stop)``. The two meet here, once:
a setup is read into engine ranges with :func:`~chisurf.core.fluorescence.tttrlib.ranges_to_inclusive`
(:func:`fret_pair_from_workflow`), and engine streams are checked as setup gates with
:func:`~chisurf.core.fluorescence.tttrlib.ranges_from_inclusive` (:func:`stream_detectors`) --
exactly the channels the engine keeps.

The streams are checked as detector gates against the excitation pulses each measurement shows
(:mod:`chisurf.core.fluorescence.excitation`): a gate that leaves out a pulse its detector sees,
holds almost none of its photons, or lies beyond the data's channels. Detectors of the setup the
streams came from that share a stream's routing channels are checked with them
(:func:`preflight_detectors`), so PIE's split of one acceptor detector into prompt (``red``) and
delayed (``yellow``) is understood. Nothing is changed: the line goes into the warnings.

Ranges are channel numbers of a width: the streams travel with the width of the setup they came
from (``micro_time_resolution_ps`` of :func:`fret_pair_from_workflow`, the windows record of
:func:`gates_record`), so the check names a binning instead of proposing new windows, and an
engine applies them in the measurement's channels (:func:`ranges_in_data`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tttrlib import (
    micro_time_windows,
    micro_time_windows_at,
    ranges_from_inclusive,
    ranges_to_inclusive,
    setup_gates,
    setup_micro_time_resolution,
)

from chisurf.core.fluorescence.excitation import windows_message, windows_preflight

__all__ = [
    "FULL_MICRO_TIME",
    "fret_pair_from_workflow",
    "gates_record",
    "preflight_detectors",
    "ranges_in_data",
    "stream_detectors",
    "window_checks",
    "window_warnings",
]

#: The inclusive range an ungated BVA / 2CDE stream reads (every micro time of a 15-bit TAC).
FULL_MICRO_TIME = (0, 32768)


def fret_pair_from_workflow(workflow_context: Mapping | None) -> dict[str, Any]:
    """The donor/acceptor streams a FRET burst engine reads from a workflow's setup.

    The setup's first two detectors are the pair (``donor``, ``acceptor``); their gates are
    converted to the engines' inclusive ranges (an ungated detector reads
    :data:`FULL_MICRO_TIME`).

    Returns
    -------
    dict
        ``{"names": (donor, acceptor), "detectors": {...}, "settings": {...},
        "micro_time_resolution_ps": float | None}`` -- the detector names in the setup
        (``"donor"`` / ``"acceptor"`` where it has fewer), the setup's detectors (half-open gates,
        for :func:`preflight_detectors`), the settings keywords (``donor_channels``,
        ``donor_micro_time_ranges``, ``acceptor_*``, ``file_type``) for the engine's settings
        dataclass, and the channel width the gates are in (``None``: the setup does not say).
    """
    channel_settings = dict((workflow_context or {}).get("channel_settings") or {})
    detectors = {str(k): dict(v) for k, v in (channel_settings.get("detectors") or {}).items()
                 if isinstance(v, Mapping)}
    reading = channel_settings.get("tttr_reading") or {}
    names = list(detectors)[:2]
    settings: dict[str, Any] = {}
    for role, name, default in (("donor", names[0] if names else None, [0, 8]),
                                ("acceptor", names[1] if len(names) > 1 else None, [1, 9])):
        if name is None:
            continue
        det = detectors[name]
        settings[f"{role}_channels"] = [int(c) for c in det.get("chs", default)]
        settings[f"{role}_micro_time_ranges"] = (
            ranges_to_inclusive(det.get("micro_time_ranges")) or [FULL_MICRO_TIME]
        )
    if reading.get("file_type"):
        settings["file_type"] = str(reading["file_type"])
    width = setup_micro_time_resolution(channel_settings)
    return {
        "names": tuple((names + ["donor", "acceptor"][len(names):])[:2]),
        "detectors": detectors,
        "settings": settings,
        "micro_time_resolution_ps": width * 1e12 if width else None,
    }


def ranges_in_data(
    ranges: Sequence[Sequence[int]] | None,
    micro_time_resolution_ps: float | None,
    tttr: Any,
) -> list[tuple[int, int]]:
    """Inclusive engine ranges given in channels of *micro_time_resolution_ps* in the channels
    of *tttr* (what the engine applies). Unknown width: unchanged (raw). The ungated stream
    (:data:`FULL_MICRO_TIME`) stays ungated."""
    out = [(int(r[0]), int(r[1])) for r in (ranges or [])]
    if not micro_time_resolution_ps or not out or out == [FULL_MICRO_TIME]:
        return out
    try:
        res = float(tttr.header.micro_time_resolution)
    except Exception:  # noqa: BLE001 - no header: nothing to convert to
        return out
    rec = micro_time_windows_at(
        micro_time_windows(gates={"s": ranges_from_inclusive(out)},
                           micro_time_resolution_ps=micro_time_resolution_ps), res)
    return ranges_to_inclusive(rec["gates"].get("s"))


def gates_record(
    detectors: Mapping[str, Mapping],
    micro_time_resolution_ps: float | None,
    windows: Mapping | None = None,
) -> dict:
    """The windows record (``tttrlib.micro_time_windows``) of *detectors*' gates and *windows*
    (``{name: [start, stop)}``), in channels of *micro_time_resolution_ps* (``None``: the width
    is not known -- raw channels, which the pre-flight says)."""
    return micro_time_windows(windows, setup_gates({"detectors": dict(detectors or {})}),
                              micro_time_resolution_ps)


def stream_detectors(
    streams: Mapping[str, tuple[Sequence[int], Sequence[Sequence[int]] | None]],
) -> dict[str, dict[str, Any]]:
    """The streams an engine applies, as setup detectors.

    Parameters
    ----------
    streams : mapping
        ``{name: (routing channels, inclusive micro-time ranges)}``.

    Returns
    -------
    dict
        ``{name: {"chs": [...], "micro_time_ranges": [[start, stop), ...]}}``.
    """
    return {
        str(name): {"chs": [int(c) for c in chs], "micro_time_ranges": ranges_from_inclusive(ranges)}
        for name, (chs, ranges) in streams.items()
    }


def preflight_detectors(
    streams: Mapping[str, tuple[Sequence[int], Sequence[Sequence[int]] | None]],
    setup_detectors: Mapping[str, Mapping] | None = None,
) -> dict[str, dict[str, Any]]:
    """The detectors to check: the applied streams, and the setup's detectors that share a
    stream's routing channels (their gates say which pulse the setup takes elsewhere).

    Parameters
    ----------
    streams : mapping
        ``{name: (routing channels, inclusive ranges)}`` -- what the engine applies. A stream
        named like a setup detector replaces it.
    setup_detectors : mapping, optional
        The setup the streams came from (``{name: {"chs", "micro_time_ranges"}}``, gates
        ``[start, stop)``).
    """
    out = stream_detectors(streams)
    used = {c for d in out.values() for c in d["chs"]}
    for name, det in (setup_detectors or {}).items():
        if str(name) in out or not isinstance(det, Mapping):
            continue
        chs = [int(c) for c in det.get("chs") or ()]
        if used & set(chs):
            out[str(name)] = {
                "chs": chs,
                "micro_time_ranges": [[int(r[0]), int(r[1])]
                                      for r in det.get("micro_time_ranges") or ()],
            }
    return out


def window_checks(tttrs: Mapping[str, Any], windows: Mapping,
                  detectors: Mapping[str, Mapping]) -> dict:
    """The shared check of a windows record's gates (and windows) against every measurement in
    *tttrs*.

    Parameters
    ----------
    tttrs : mapping
        ``{name: tttrlib.TTTR}``.
    windows : mapping
        The windows record (:func:`gates_record`): the gates of *detectors*, any PIE windows and
        the channel width they are in.
    detectors : mapping
        ``{name: {"chs": [...]}}`` -- the streams' routing channels.

    Returns ``{name: WindowCheck or None}``; empty when nothing is gated and there are no windows
    (an ungated stream takes every photon: nothing to check).
    """
    if not windows.get("gates") and not windows.get("windows"):
        return {}
    out: dict = {}
    for key, tttr in tttrs.items():
        try:
            out[key] = windows_preflight(tttr, windows, detectors=dict(detectors))
        except Exception:  # noqa: BLE001 - a stream that cannot be checked says nothing
            out[key] = None
    return out


def window_warnings(
    tttrs: Mapping[str, Any],
    windows: Mapping | None,
    detectors: Mapping[str, Mapping],
    *,
    checks: Mapping | None = None,
) -> list[str]:
    """One line per measurement whose gates do not hold its excitation pulses.

    Parameters
    ----------
    tttrs : mapping
        ``{name: tttrlib.TTTR}`` -- the measurements the streams are read from.
    windows : mapping
        The windows record (:func:`gates_record`); may be ``None`` when *checks* are given.
    detectors : mapping
        From :func:`preflight_detectors` / :func:`stream_detectors`, or a setup's detectors.
    checks : mapping, optional
        Checks already made by :func:`window_checks` (not repeated).

    Returns
    -------
    list of str
        Empty when every measurement fits or nothing is gated. The line names the measurement
        when there is more than one.
    """
    checks = window_checks(tttrs, windows or {}, detectors) if checks is None else checks
    out: list[str] = []
    for key, check in checks.items():
        message = windows_message(check)
        if message:
            out.append(message if len(checks) == 1 else f"{Path(str(key)).name}: {message}")
    return out
