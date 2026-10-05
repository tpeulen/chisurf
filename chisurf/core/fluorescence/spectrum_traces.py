"""MMFDB ``fluorophores.get`` spectra as plot traces (Qt-free).

A probe record from the fluorophore curation service carries its spectra as
``{"spectrum_type", "wavelengths", "intensity"}`` entries. A viewer draws them
normalised to their maximum: one probe in a colour per spectrum type, several
probes overlaid in a colour per probe with a line style per spectrum type.
Shared by the Qt :class:`~chisurf.gui.widgets.spectrum_view.SpectrumView` and the
native emtk MMFDB Admin.

A trace is ``{"name", "x", "y", "color", "style", "width"}`` with ``style`` one of
``solid`` / ``dash`` / ``dot`` / ``dashdot``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Colour per probe when several are overlaid.
PROBE_COLORS = [
    (230, 25, 75),
    (60, 180, 75),
    (0, 130, 200),
    (245, 130, 48),
    (145, 30, 180),
    (70, 240, 240),
    (240, 50, 230),
    (210, 245, 60),
    (250, 190, 190),
    (0, 128, 128),
]

#: Colour per spectrum type for a single probe.
SPECTRUM_COLORS = {
    "absorption": (0, 100, 200),
    "emission": (200, 0, 0),
    "transmission": (0, 150, 0),
    "excitation": (0, 100, 200),
    "quantum_efficiency": (150, 0, 150),
    "responsivity": (0, 150, 150),
    "reflectance": (150, 150, 0),
}

#: Legend label per spectrum type.
SPECTRUM_LABELS = {
    "absorption": "Absorption",
    "emission": "Emission",
    "transmission": "Transmission",
    "excitation": "Excitation",
    "quantum_efficiency": "Quantum Efficiency",
    "responsivity": "Responsivity",
    "reflectance": "Reflectance",
}

#: Line style per spectrum, in order, when probes are overlaid.
OVERLAY_STYLES = ("solid", "dash", "dot", "dashdot")


def _normalised(spec: dict[str, Any]) -> tuple[np.ndarray, np.ndarray] | None:
    wl = np.array(spec.get("wavelengths", []), dtype=float)
    iv = np.array(spec.get("intensity", spec.get("intensity_values", [])), dtype=float)
    if len(wl) == 0 or len(iv) == 0:
        return None
    if np.nanmax(iv) > 0:
        iv = iv / np.nanmax(iv)
    return wl, iv


def probe_traces(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Traces of one probe (a ``fluorophores.get`` response): one per spectrum type."""
    traces: list[dict[str, Any]] = []
    for spec in data.get("spectra", []) or []:
        xy = _normalised(spec)
        if xy is None:
            continue
        stype = spec.get("spectrum_type", "")
        traces.append(
            {
                "name": SPECTRUM_LABELS.get(stype, stype.capitalize()),
                "x": xy[0],
                "y": xy[1],
                "color": SPECTRUM_COLORS.get(stype, (100, 100, 100)),
                "style": "solid",
                "width": 2,
            }
        )
    return traces


def overlay_traces(probes_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Traces of several probes overlaid: a colour per probe, a line style per spectrum."""
    traces: list[dict[str, Any]] = []
    for p_idx, data in enumerate(probes_data):
        probe = data.get("probe", {}) or {}
        name = probe.get("chromophore_name", probe.get("name", f"Probe {p_idx + 1}"))
        color = PROBE_COLORS[p_idx % len(PROBE_COLORS)]
        for s_idx, spec in enumerate(data.get("spectra", []) or []):
            xy = _normalised(spec)
            if xy is None:
                continue
            stype = spec.get("spectrum_type", "")
            label = SPECTRUM_LABELS.get(stype, stype.capitalize())
            traces.append(
                {
                    "name": f"{name} [{label}]",
                    "x": xy[0],
                    "y": xy[1],
                    "color": color,
                    "style": OVERLAY_STYLES[s_idx % len(OVERLAY_STYLES)],
                    "width": 2,
                }
            )
    return traces
