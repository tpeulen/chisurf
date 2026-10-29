"""The photon streams the burst engines apply, as a detector setup -- and their window pre-flight.

BVA, 2CDE, H2MM, the MFD preparation and the burst workflow split each burst's photons into
streams by routing channel *and* micro-time range. The engines (``tttrlib.BVA`` /
``tttrlib.TwoCDE`` / ``BurstFeature``, :class:`~chisurf.core.fluorescence.burst.photons.StreamDef`)
keep a photon when ``start <= micro_time <= stop`` -- their ranges are **inclusive**. A setup's
detector gates (``detectors.*.micro_time_ranges``) are ``[start, stop)``. The two meet here, once:
a setup is read into engine ranges with :func:`~chisurf.core.fluorescence.excitation.gates_to_inclusive`
(:func:`fret_pair_from_workflow`), and engine streams are checked as setup gates with
:func:`~chisurf.core.fluorescence.excitation.gates_from_inclusive` (:func:`stream_detectors`) --
exactly the channels the engine keeps.

The streams are checked as detector gates against the excitation pulses each measurement shows
(:mod:`chisurf.core.fluorescence.excitation`): a gate that leaves out a pulse its detector sees,
holds almost none of its photons, or lies beyond the data's channels. Detectors of the setup the
streams came from that share a stream's routing channels are checked with them
(:func:`preflight_detectors`), so PIE's split of one acceptor detector into prompt (``red``) and
delayed (``yellow``) is understood. Nothing is changed: the line goes into the warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from chisurf.core.fluorescence.excitation import (
    gates_from_inclusive,
    gates_to_inclusive,
    windows_message,
    windows_preflight,
)

__all__ = [
    "FULL_MICRO_TIME",
    "fret_pair_from_workflow",
    "preflight_detectors",
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
        ``{"names": (donor, acceptor), "detectors": {...}, "settings": {...}}`` -- the detector
        names in the setup (``"donor"`` / ``"acceptor"`` where it has fewer), the setup's
        detectors (half-open gates, for :func:`preflight_detectors`) and the settings keywords
        (``donor_channels``, ``donor_micro_time_ranges``, ``acceptor_*``, ``file_type``) for the
        engine's settings dataclass.
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
            gates_to_inclusive(det.get("micro_time_ranges")) or [FULL_MICRO_TIME]
        )
    if reading.get("file_type"):
        settings["file_type"] = str(reading["file_type"])
    return {
        "names": tuple((names + ["donor", "acceptor"][len(names):])[:2]),
        "detectors": detectors,
        "settings": settings,
    }


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
        str(name): {"chs": [int(c) for c in chs], "micro_time_ranges": gates_from_inclusive(ranges)}
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


def window_checks(tttrs: Mapping[str, Any], detectors: Mapping[str, Mapping],
                  windows: Mapping | None = None) -> dict:
    """The shared check of *detectors*' gates (and *windows*, when given) against every
    measurement in *tttrs*.

    Returns ``{name: WindowCheck or None}``; empty when no detector is gated (an ungated stream
    takes every photon: nothing to check).
    """
    if not any((d or {}).get("micro_time_ranges") for d in detectors.values()):
        return {}
    out: dict = {}
    for key, tttr in tttrs.items():
        try:
            out[key] = windows_preflight(tttr, dict(windows or {}), detectors=dict(detectors))
        except Exception:  # noqa: BLE001 - a stream that cannot be checked says nothing
            out[key] = None
    return out


def window_warnings(
    tttrs: Mapping[str, Any],
    detectors: Mapping[str, Mapping],
    *,
    checks: Mapping | None = None,
    windows: Mapping | None = None,
) -> list[str]:
    """One line per measurement whose gates do not hold its excitation pulses.

    Parameters
    ----------
    tttrs : mapping
        ``{name: tttrlib.TTTR}`` -- the measurements the streams are read from.
    detectors : mapping
        From :func:`preflight_detectors` / :func:`stream_detectors`, or a setup's detectors.
    checks : mapping, optional
        Checks already made by :func:`window_checks` (not repeated).
    windows : mapping, optional
        PIE windows ``{name: [start, stop)}`` checked with the gates.

    Returns
    -------
    list of str
        Empty when every measurement fits or nothing is gated. The line names the measurement
        when there is more than one.
    """
    checks = window_checks(tttrs, detectors, windows) if checks is None else checks
    out: list[str] = []
    for key, check in checks.items():
        message = windows_message(check)
        if message:
            out.append(message if len(checks) == 1 else f"{Path(str(key)).name}: {message}")
    return out
