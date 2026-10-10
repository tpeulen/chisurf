"""Imaging Tools — the unified imaging toolbox.

One window listing the imaging tools in pipeline order (setup, browser, drift,
FRC, flow, tracking, colocalization, the per-pixel maps, MLE, CLSM, PSF). The
window is the native emtk app in :mod:`.gui.app`; importing this package needs
no Qt binding.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest_path = Path(__file__).parent / "manifest.json"
_manifest = (
    json.loads(_manifest_path.read_text(encoding="utf-8")) if _manifest_path.exists() else {}
)
name = _manifest.get("display_name", "Imaging:Image Tools")
