"""The shared excitation-window pre-flight as the burst-feature engines apply micro-time ranges.

BVA and 2CDE (and the burst workflow that runs them) split each burst's photons into streams by
routing channel *and* micro-time range: ``tttrlib.BVA`` / ``tttrlib.TwoCDE`` keep a photon when
``start <= micro_time <= stop`` -- the ranges are **inclusive**. A setup's detector gates
(``detectors.*.micro_time_ranges``), which the shared check reads, are ``[start, stop)``. So a
stream ``(start, stop)`` is checked as the gate ``[start, stop + 1)``: exactly the channels the
engine keeps.

The streams are checked as detector gates only -- the engines read no PIE windows -- against the
excitation pulses each measurement shows (:mod:`chisurf.core.fluorescence.excitation`): a gate
that leaves out a pulse its detector sees, holds almost none of its photons, or lies beyond the
data's channels. Detectors of the setup the streams came from that share a stream's routing
channels are checked with them, so PIE's split of one acceptor detector into prompt (``red``) and
delayed (``yellow``) is understood. Nothing is changed: the line goes into the warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "from_setup_gates",
    "preflight_detectors",
    "stream_detectors",
    "to_setup_gates",
    "window_checks",
    "window_warnings",
]


def to_setup_gates(ranges: Sequence[Sequence[int]] | None) -> list[list[int]]:
    """Inclusive ``(start, stop)`` stream ranges as setup gates ``[start, stop + 1)``."""
    return [[int(r[0]), int(r[1]) + 1] for r in (ranges or ()) if len(r) >= 2]


def from_setup_gates(gates: Sequence[Sequence[int]] | None) -> list[tuple[int, int]]:
    """Setup gates ``[start, stop)`` as inclusive stream ranges ``(start, stop - 1)``."""
    return [(int(g[0]), max(int(g[0]), int(g[1]) - 1)) for g in (gates or ()) if len(g) >= 2]


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
        str(name): {"chs": [int(c) for c in chs], "micro_time_ranges": to_setup_gates(ranges)}
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


def window_checks(tttrs: Mapping[str, Any], detectors: Mapping[str, Mapping]) -> dict:
    """The shared check of *detectors*' gates against every measurement in *tttrs*.

    Returns ``{name: WindowCheck or None}``; empty when no detector is gated (an ungated stream
    takes every photon: nothing to check).
    """
    if not any((d or {}).get("micro_time_ranges") for d in detectors.values()):
        return {}
    from chisurf.core.fluorescence.excitation import windows_preflight

    out: dict = {}
    for key, tttr in tttrs.items():
        try:
            out[key] = windows_preflight(tttr, {}, detectors=dict(detectors))
        except Exception:  # noqa: BLE001 - a stream that cannot be checked says nothing
            out[key] = None
    return out


def window_warnings(
    tttrs: Mapping[str, Any],
    detectors: Mapping[str, Mapping],
    *,
    checks: Mapping | None = None,
) -> list[str]:
    """One line per measurement whose gates do not hold its excitation pulses.

    Parameters
    ----------
    tttrs : mapping
        ``{name: tttrlib.TTTR}`` -- the measurements the streams are read from.
    detectors : mapping
        From :func:`preflight_detectors` / :func:`stream_detectors`.
    checks : mapping, optional
        Checks already made by :func:`window_checks` (not repeated).

    Returns
    -------
    list of str
        Empty when every measurement fits or nothing is gated. The line names the measurement
        when there is more than one.
    """
    from pathlib import Path

    from chisurf.core.fluorescence.excitation import windows_message

    checks = window_checks(tttrs, detectors) if checks is None else checks
    out: list[str] = []
    for key, check in checks.items():
        message = windows_message(check)
        if message:
            out.append(message if len(checks) == 1 else f"{Path(str(key)).name}: {message}")
    return out
