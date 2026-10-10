"""CLSM Generator — simulate a confocal photon image from intensity + lifetime maps.

Load an intensity image and one lifetime map per detector (TIFF or numpy) and
simulate a raster-scanned CLSM photon stream whose per-pixel intensity and
fluorescence lifetime match the inputs — ground-truth test data for the imaging
analysis tools.  The Qt-free computation lives in
:func:`chisurf.core.fluorescence.imaging.simulate.simulate_clsm_from_maps`; the
native emtk app is in :mod:`.gui.app`.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Imaging:Simulate:CLSM Generator"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text(encoding="utf-8"))
    name = _manifest.get("display_name", name)
