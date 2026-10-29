"""The shared excitation-window pre-flight as the per-pixel imaging tools use a detector setup.

A detector window of an imaging tool fills its image only with the photons of its routing
channels inside its micro-time gates (``micro_time_ranges``; ``build_clsm_windowed``): the gates
are applied in the data's own channels, and the setup's PIE windows do not shape an image. So
only the gates are held against the excitation pulses of the photon stream (the check every PIE
analysis runs, :mod:`chisurf.core.fluorescence.excitation`) -- the same gate-only check, with the
same per-file memory, as the image browser's
(:func:`chisurf.core.fluorescence.excitation.remembered_gate_check`).

Nothing is checked for an image file (TIFF, camera) or for detectors without gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["gate_check", "gate_warnings", "gated_detectors", "take_gates"]


def gated_detectors(detectors: Mapping | None) -> dict:
    """The detectors of *detectors* that gate in micro time (``{name: {chs, micro_time_ranges}}``)."""
    out = {}
    for name, det in dict(detectors or {}).items():
        if isinstance(det, Mapping) and det.get("micro_time_ranges"):
            out[str(name)] = {
                "chs": [int(c) for c in det.get("chs") or []],
                "micro_time_ranges": [[int(a), int(b)] for a, b in det["micro_time_ranges"]],
            }
    return out


def gate_check(filename: str, detectors: Mapping | None) -> Any:
    """The gate check of the photon stream *filename* (``None``: nothing to check or say).

    Parameters
    ----------
    filename : str
        The measurement the windows are filled from.
    detectors : mapping
        The detector windows (``{name: {"chs": [...], "micro_time_ranges": [...]}}``).

    Returns
    -------
    WindowCheck or None
        Remembered per file (size, modification time) and gates: a second Run reads nothing.
    """
    gated = gated_detectors(detectors)
    if not gated or not filename:
        return None
    from chisurf.core.fluorescence.imaging.image_source import is_photon_stream

    if not is_photon_stream(str(filename)):
        return None
    from chisurf.core.fluorescence.excitation import remembered_gate_check

    return remembered_gate_check(str(filename), {"detectors": gated})


def gate_warnings(filename: str, detectors: Mapping | None) -> list[str]:
    """The pre-flight's line for the windows of *filename* (empty when the gates hold the pulses)."""
    from chisurf.core.fluorescence.excitation import windows_message

    line = windows_message(gate_check(filename, detectors))
    return [line] if line else []


def take_gates(detectors: Mapping | None, setup: Mapping | None) -> dict:
    """*detectors* with the gates of *setup* (what *Use detected windows* proposes); every other
    key of a detector window (calibration, polarization channels) is kept."""
    out = {str(k): dict(v) for k, v in dict(detectors or {}).items()}
    for name, det in dict((setup or {}).get("detectors") or {}).items():
        if name in out and isinstance(det, Mapping) and "micro_time_ranges" in det:
            out[name]["micro_time_ranges"] = [
                tuple(int(v) for v in r) for r in det["micro_time_ranges"] or []
            ]
    return out
