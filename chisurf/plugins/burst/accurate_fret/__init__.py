"""Accurate FRET — automatic Hellenkamp calibration of a burst measurement.

Determines the correction factors (alpha leakage, delta direct excitation, gamma
detection/quantum-yield ratio, beta excitation-flux ratio) from the measurement
itself: the burst populations are found by a Gaussian mixture over the
stoichiometry, the light path supplies the priors, and the static FRET line adds
the lifetime route that identifies gamma even for a single-population sample.
The widget is built via AutoForm (PRD-40) from ``accurate_fret.view.json``.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🎯"

from pathlib import Path  # noqa: E402

from chisurf.core.plugin import load_manifest  # noqa: E402
from chisurf.core.plugin.registry import apply_manifest_statefulness  # noqa: E402

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "FRET:Accurate FRET"

if __name__ == "plugin":
    from .gui.tool import AccurateFretTool

    window = AccurateFretTool()
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
    try:
        window.raise_()
        window.activateWindow()
    except Exception:
        pass
