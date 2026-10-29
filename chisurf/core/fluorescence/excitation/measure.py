"""Excitation windows of a measurement: from a TTTR object or file, and against an Experiment setup.

* :func:`detect_windows` -- PIE pulses in the micro time first; when there are none (flat micro
  time) and two detectors alternate in the macro time, µs-ALEX.
* :func:`detect_alex_windows` -- the µs-ALEX branch: the alternation period, the detector roles
  and the laser windows (:mod:`.alex`).
* :func:`check_setup` -- an Experiment setup's windows against a measurement: what every PIE / ALEX
  consumer calls before it runs.

A *setup* is the shared channel definition (``detectors``, ``windows``, ``tttr_reading``).
Its windows are raw micro-time channels of the resolution in ``tttr_reading.micro_time_resolution``
(ps); :func:`setup_window_resolution_s` reads it so a different TAC range or binning is converted,
not silently misapplied.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from typing import Any

import numpy as np

from .check import check_windows
from .pie import detect_pie_windows
from .result import ExcitationWindows, Pulse, WindowCheck

__all__ = [
    "check_setup",
    "detect_alex_windows",
    "detect_windows",
    "histograms_from_tttr",
    "setup_detectors",
    "setup_gates",
    "setup_window_resolution_s",
]

#: A routing channel with less than this share of the photons is a marker or crosstalk line.
_MIN_SHARE = 1e-3
#: The alternation periods µs-ALEX uses (s): a slower "alternation" is intensity drift.
ALEX_PERIOD_RANGE_S = (2e-6, 2e-3)
#: Above this ratio of its donor-excitation rate, the donor detector is not dark under acceptor
#: excitation: the stream does not alternate between two lasers.
ALEX_MAX_CONTRAST = 0.5
#: Photons read for a detection: plenty for the shape of a histogram.
MAX_PHOTONS = 4_000_000


def _unwrap(setup: Mapping | None) -> dict:
    if not isinstance(setup, Mapping):
        return {}
    return dict(setup.get("data", setup))


def setup_detectors(setup: Mapping | None) -> dict[str, list[int]]:
    """``{detector: routing channels}`` of a setup (empty when it names none)."""
    det = _unwrap(setup).get("detectors") or {}
    return {
        str(k): [int(c) for c in (v.get("chs") or [])]
        for k, v in det.items()
        if isinstance(v, Mapping) and v.get("chs")
    }


def setup_window_resolution_s(setup: Mapping | None) -> float | None:
    """The channel width a setup's windows are in (``tttr_reading.micro_time_resolution``, ps),
    in seconds; ``None`` when the setup does not say."""
    reading = _unwrap(setup).get("tttr_reading") or {}
    try:
        ps = float(reading.get("micro_time_resolution") or 0.0)
    except (TypeError, ValueError):
        return None
    return ps * 1e-12 if ps > 0 else None


def _load(data: Any):
    if isinstance(data, (str, pathlib.Path)):
        import tttrlib  # noqa: PLC0415

        tttr = tttrlib.TTTR(str(data))
        if len(tttr) == 0:
            raise ValueError(f"{data}: no photons read (unsupported or empty file)")
        return tttr
    return data


def _arrays(tttr, max_photons: int):
    micro = np.asarray(tttr.micro_times)
    routing = np.asarray(tttr.routing_channels)
    macro = np.asarray(tttr.macro_times)
    if max_photons and micro.size > max_photons:
        micro, routing, macro = micro[:max_photons], routing[:max_photons], macro[:max_photons]
    return micro, routing, macro


def _groups(routing: np.ndarray, detectors: Mapping[str, list[int]] | None) -> dict[str, list[int]]:
    if detectors:
        return {str(k): [int(c) for c in v] for k, v in detectors.items() if v}
    present, counts = np.unique(routing, return_counts=True)
    total = max(int(counts.sum()), 1)
    return {f"ch {int(c)}": [int(c)] for c, k in zip(present, counts) if k > _MIN_SHARE * total}


def histograms_from_tttr(
    tttr, detectors: Mapping[str, list[int]] | None = None, *, max_photons: int = MAX_PHOTONS
) -> tuple[dict[str, np.ndarray], float, int]:
    """Per-detector micro-time histograms of *tttr*: ``(histograms, resolution_s, n_channels)``.

    Detectors are the setup's (``{name: routing channels}``) or, without one, every routing
    channel carrying photons (``"ch 0"``, ...). The channel count is the header's, or the data's
    when the data uses more (some headers undercount it).
    """
    tttr = _load(tttr)
    micro, routing, _ = _arrays(tttr, max_photons)
    res = float(tttr.header.micro_time_resolution)
    n = int(tttr.get_number_of_micro_time_channels() or 0)
    if micro.size:
        n = max(n, int(micro.max()) + 1)
        if int(micro.max()) == int(micro.min()):
            n = 0  # no micro time recorded (an .sm file, a T2 stream): nothing to histogram
    hists = {
        name: np.bincount(micro[np.isin(routing, chs)].astype(np.int64), minlength=n)[:n]
        for name, chs in _groups(routing, detectors).items()
    }
    return hists, res, n


def detect_alex_windows(
    macro_times,
    routing_channels,
    macro_resolution_s: float,
    *,
    detectors: Mapping[str, list[int]] | None = None,
) -> ExcitationWindows:
    """µs-ALEX: the alternation period, which detector is the donor, and the laser windows.

    A thin call into :mod:`.alex` (:func:`~.alex.measure_alex_period`,
    :func:`~.alex.detect_alex_channels`, :func:`~.alex.auto_alex_windows`); windows are phases of
    the period in macro-time ticks, ``prompt`` the donor laser and ``delayed`` the acceptor's.
    """
    from . import alex  # noqa: PLC0415

    macro = np.asarray(macro_times).astype(np.int64)
    rc = np.asarray(routing_channels)
    out = ExcitationWindows(
        kind="unclear", domain="macro", resolution_s=float(macro_resolution_s),
        n_photons=int(macro.size),
    )
    groups = _groups(rc, detectors)
    if len(groups) < 2:
        out.message = "One detector: µs-ALEX alternation needs two detection colours."
        return out
    names = list(groups)
    keep = np.isin(rc, [c for chs in groups.values() for c in chs])
    macro, rc = macro[keep], rc[keep]
    try:
        tick = float(macro_resolution_s) or 1.0
        m = alex.measure_alex_period(
            macro, rc, channel_groups=list(groups.values()),
            min_period=max(16, int(ALEX_PERIOD_RANGE_S[0] / tick)),
            max_period=max(64, int(ALEX_PERIOD_RANGE_S[1] / tick)),
        )
    except ValueError as exc:
        out.message = f"No µs-ALEX alternation in the macro time: {exc}."
        return out
    period = int(m["period"])
    phase = macro % period
    busy = [list(g) for g in m["channels"]]
    two = np.isin(rc, busy[0] + busy[1])
    try:
        roles = alex.detect_alex_channels(
            phase[two], rc[two], alex_period=period, channel_groups=busy
        )
        if float(roles.get("contrast", 0.0)) > ALEX_MAX_CONTRAST:
            raise ValueError(
                f"the donor detector is not dark in either half of the {period}-tick cycle "
                f"(contrast {float(roles['contrast']):.2f})"
            )
        w = alex.auto_alex_windows(
            phase, rc, donor_channels=roles["donor"], acceptor_channels=roles["acceptor"],
            alex_period=period,
        )
    except ValueError as exc:
        out.message = f"µs-ALEX period {period} ticks, but no laser windows: {exc}."
        out.n_channels = period
        return out

    def name_of(chs):
        return next((k for k, v in groups.items() if set(v) == set(chs)), f"ch {list(chs)}")

    donor, acceptor = name_of(roles["donor"]), name_of(roles["acceptor"])
    out.kind, out.n_channels, out.confidence = "alex", period, float(m["confidence"])
    out.donor_detectors, out.acceptor_detectors = [donor], [a for a in names if a != donor]
    for label, key, role, excites in (("prompt", "green", "donor", names),
                                      ("delayed", "red", "acceptor", [acceptor])):
        lo, hi = (int(x) for x in w[key])
        out.windows[label] = [lo, hi]
        out.pulses.append(Pulse(rise=lo, peak=(lo + ((hi - lo) % period) // 2) % period,
                                core_stop=hi, excites=list(excites), role=role, window=label))
    f = period * out.resolution_s
    out.message = (
        f"µs-ALEX: alternation period {period} ticks ({f * 1e6:.2f} µs, contrast "
        f"{out.confidence:.0f}x); donor detector {donor}."
    )
    return out


def detect_windows(
    data: Any,
    *,
    setup: Mapping | None = None,
    detectors: Mapping[str, list[int]] | None = None,
    kind: str = "auto",
    max_photons: int = MAX_PHOTONS,
) -> ExcitationWindows:
    """Detect the excitation scheme of a measurement and propose windows.

    Parameters
    ----------
    data : tttrlib.TTTR or path
        The measurement (a path is opened by tttrlib, container inferred).
    setup : mapping, optional
        An Experiment setup; its detectors name the histograms.
    detectors : mapping, optional
        ``{name: routing channels}``, instead of a setup's.
    kind : str
        ``"auto"`` (PIE, then µs-ALEX), ``"pie"`` or ``"alex"``.
    max_photons : int
        Photons read from the start of the measurement.
    """
    tttr = _load(data)
    det = detectors or setup_detectors(setup) or None
    if kind in ("auto", "pie"):
        hists, res, n = histograms_from_tttr(tttr, det, max_photons=max_photons)
        pie = detect_pie_windows(hists, res, n_channels=n) if n > 8 else ExcitationWindows(
            "unclear", resolution_s=res, n_channels=n,
            message="No micro time in this measurement (no TCSPC: not PIE).",
        )
        if kind == "pie" or pie.kind == "pie" or (pie.kind == "single" and len(hists) < 2):
            return pie
    else:
        pie = None
    micro, routing, macro = _arrays(tttr, max_photons)
    alex = detect_alex_windows(
        macro, routing, float(tttr.header.macro_time_resolution), detectors=det
    )
    if alex.kind == "alex" or pie is None:
        if pie is not None:
            alex.notes.append(pie.message)
        return alex
    if pie.kind == "unclear":  # a single pulse needs no word on µs-ALEX
        pie.notes.append(alex.message)
    return pie


def setup_gates(setup: Mapping | None) -> dict[str, list[list[int]]]:
    """``{detector: [[start, stop], ...]}`` -- the micro-time gates of a setup's detectors (those
    that have any)."""
    det = _unwrap(setup).get("detectors") or {}
    return {
        str(k): [[int(r[0]), int(r[1])] for r in (v.get("micro_time_ranges") or [])]
        for k, v in det.items()
        if isinstance(v, Mapping) and v.get("micro_time_ranges")
    }


def check_setup(
    setup: Mapping,
    data: Any = None,
    *,
    detection: ExcitationWindows | None = None,
    histogram: np.ndarray | None = None,
    histograms: Mapping[str, np.ndarray] | None = None,
    windows_resolution_s: float | None = None,
) -> WindowCheck:
    """Check an Experiment setup's windows and detector gates against a measurement -- the shared
    pre-flight of every PIE / ALEX analysis.

    Parameters
    ----------
    setup : mapping
        The Experiment setup (``windows``, ``detectors`` with their ``micro_time_ranges``,
        ``tttr_reading``).
    data : tttrlib.TTTR or path, optional
        The measurement; not needed when *detection* is given.
    detection : ExcitationWindows, optional
        A detection already made (e.g. from live decays).
    histogram : array, optional
        All photons per channel, for the empty-window check (read from *data* when given).
    histograms : mapping, optional
        Per-detector photons per channel, for the gates (read from *data* when given).
    windows_resolution_s : float, optional
        The channel width of the setup's windows and gates; default
        :func:`setup_window_resolution_s`.
    """
    s = _unwrap(setup)
    if detection is None:
        if data is None:
            raise ValueError("check_setup needs the measurement or a detection")
        tttr = _load(data)
        detection = detect_windows(tttr, setup=s)
        if histograms is None and detection.domain == "micro":
            histograms, _, _ = histograms_from_tttr(tttr, setup_detectors(s) or None)
    if histogram is None and histograms:
        histogram = np.sum([np.asarray(h, float) for h in histograms.values()], axis=0)
    if windows_resolution_s is None and detection.domain == "micro":
        windows_resolution_s = setup_window_resolution_s(s)
    windows = s.get("windows") or {}
    gates = setup_gates(s) if detection.domain == "micro" else {}
    if detection.domain == "macro":
        windows = s.get("alex_windows") or {}
    return check_windows(
        windows, detection, windows_resolution_s=windows_resolution_s, histogram=histogram,
        gates=gates, histograms=dict(histograms) if histograms else None,
        gate_channels=setup_detectors(s),
    )
