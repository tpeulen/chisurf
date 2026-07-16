"""CLSM Generator — simulate a confocal photon image from intensity + lifetime maps.

Load an intensity image and one lifetime map per detector (TIFF or numpy) and
simulate a raster-scanned CLSM photon stream whose per-pixel intensity and
fluorescence lifetime match the inputs — ground-truth test data for the imaging
analysis tools.  The Qt-free computation lives in
:func:`chisurf.core.fluorescence.imaging.simulate.simulate_clsm_from_maps`; the
AutoForm GUI is in :mod:`.gui`.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Imaging:Simulate:CLSM Generator"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text())
    name = _manifest.get("display_name", name)


def __getattr__(attr_name: str):
    """Lazy Qt gate for the GUI entrypoint (keeps the package import Qt-free)."""
    if attr_name == "ClsmGeneratorTool":
        from .gui.tool import ClsmGeneratorTool as _cls

        globals()["ClsmGeneratorTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


__all__ = ["ClsmGeneratorTool"]
