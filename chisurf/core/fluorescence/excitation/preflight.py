"""The one pre-flight every PIE analysis runs before it uses micro-time windows.

Burst selection, the burst analyses that read prompt/delayed streams and any other consumer of
a setup's windows call :func:`windows_preflight` on the measurement they are about to analyse.
It runs the shared detection and check (:func:`~.measure.check_setup`) on the micro time only
(the windows are micro-time ranges; a µs-ALEX file is the Alternation step's business) and turns
the verdict into one line for the analysis's warnings -- the same words everywhere. A donor-only
measurement gives a short note, never a warning: one pulse cannot say where the windows belong.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .measure import check_setup, detect_windows, histograms_from_tttr, setup_detectors
from .result import WindowCheck

__all__ = ["windows_message", "windows_preflight"]

#: Photons the pre-flight reads: the shape of the decays, not the whole file.
PREFLIGHT_PHOTONS = 1_000_000


def windows_preflight(
    tttr: Any,
    windows: Mapping | None,
    *,
    detectors: Mapping | None = None,
    tttr_reading: Mapping | None = None,
    setup: Mapping | None = None,
) -> WindowCheck | None:
    """Check *windows* against the micro time of *tttr*; ``None`` when there is nothing to check
    (no windows and no micro time).

    Parameters
    ----------
    tttr : tttrlib.TTTR or path
        The measurement about to be analysed.
    windows : mapping
        ``{name: [start, stop]}`` in micro-time channels.
    detectors, tttr_reading : mapping, optional
        The setup's detectors (name the histograms) and reading routine (the channel width the
        windows are in).
    setup : mapping, optional
        A whole setup instead of the three parts.
    """
    s = dict(setup or {})
    if windows is not None:
        s["windows"] = {k: [int(v[0]), int(v[1])] for k, v in dict(windows).items()}
    if detectors is not None:
        s["detectors"] = dict(detectors)
    if tttr_reading is not None:
        s["tttr_reading"] = dict(tttr_reading)
    try:
        det = detect_windows(tttr, setup=s, kind="pie", max_photons=PREFLIGHT_PHOTONS)
    except Exception:  # noqa: BLE001 - a stream that cannot be histogrammed: nothing to say
        return None
    if det.n_channels <= 8 and not s.get("windows"):
        return None
    hists, _, _ = histograms_from_tttr(tttr, setup_detectors(s) or None,
                                       max_photons=PREFLIGHT_PHOTONS)
    total = sum(hists.values()) if hists else None
    return check_setup(s, detection=det, histogram=total)


def windows_message(check: WindowCheck | None) -> str | None:
    """One line for an analysis's warnings, or ``None`` when the windows hold the pulses."""
    if check is None:
        return None
    det = check.detection
    if not det.alternating:
        if det.kind == "single" and check.windows:
            return ("One excitation pulse in the micro time (donor-only or not PIE): the PIE "
                    "windows were not checked against the data.")
        return None
    if not check.mismatch:
        return None
    proposal = ", ".join(f"{k} {v[0]}–{v[1]}" for k, v in check.proposal.items())
    return (f"PIE windows do not match the data: {check.summary} Detected windows: {proposal} "
            "(Excitation Windows / setup editor: Auto-detect).")
