"""Image Tools — the imaging pipeline.

One window listing the imaging steps that share one context (detector setup,
photon source, imaging HDF5, IRF & BG calibration) in pipeline order: setup,
browser, FRC, flow, colocalization, the numbered per-pixel maps, CLSM Draw,
Spot Finder and Region MLE. Tools that read their own input (Drift Correction,
Particle Tracking, PSF Determination, CLSM Generator) are ribbon entries of
their own. The window is the native emtk app in :mod:`.gui.app`; importing
this package needs no Qt binding.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest_path = Path(__file__).parent / "manifest.json"
_manifest = (
    json.loads(_manifest_path.read_text(encoding="utf-8")) if _manifest_path.exists() else {}
)
name = _manifest.get("display_name", "Imaging:Image Tools")
