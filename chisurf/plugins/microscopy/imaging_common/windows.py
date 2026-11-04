"""The shared excitation-window pre-flight as the per-pixel imaging tools use a detector setup.

A detector window of an imaging tool fills its image only with the photons of its routing
channels inside its micro-time gates (``micro_time_ranges``; ``build_clsm_windowed``): the gates
are applied in the data's own channels, and the setup's PIE windows do not shape an image. So
only the gates are held against the excitation pulses of the photon stream -- the core gate-only
check with its per-file memory (:func:`chisurf.core.fluorescence.excitation.remembered_gate_check`).
The tools build their pre-flight setup with ``gate_setup``, report with ``windows_message`` and
take detected gates with ``merge_gates`` / ``setup_gates``, all from that package.

Nothing is checked for an image file (TIFF, camera) or for detectors without gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tttrlib import setup_gates

from chisurf.core.fluorescence.excitation import remembered_gate_check

__all__ = ["gate_check"]


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
    detectors = dict(detectors or {})
    widths = {float(d["micro_time_resolution_ps"]) for d in detectors.values()
              if d.get("micro_time_ranges") and d.get("micro_time_resolution_ps")}
    setup = {"detectors": detectors}
    gated = [d for d in detectors.values() if d.get("micro_time_ranges")]
    if len(widths) == 1 and all(d.get("micro_time_resolution_ps") for d in gated):
        setup["tttr_reading"] = {"micro_time_resolution": widths.pop()}
    elif widths:
        # Each detector may have come from a different setup; convert independently.
        from chisurf.core.fio.staging import open_tttr
        from chisurf.core.fluorescence.excitation import setup_in_data

        tttr = open_tttr(filename)
        for name, detector in detectors.items():
            width = detector.get("micro_time_resolution_ps")
            if width:
                converted = setup_in_data({"detectors": {name: detector},
                    "tttr_reading": {"micro_time_resolution": width}}, tttr)
                detectors[name] = converted["detectors"][name]
    if not filename or not setup_gates(setup):
        return None
    from chisurf.core.fluorescence.imaging.image_source import is_photon_stream

    if not is_photon_stream(str(filename)):
        return None
    return remembered_gate_check(str(filename), setup)
