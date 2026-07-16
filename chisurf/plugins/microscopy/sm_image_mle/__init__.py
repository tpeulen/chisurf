"""Molecule-wise MLE lifetime analysis for TTTR imaging data.

Segments single molecules from a confocal (CLSM) image and fits each by
single-lifetime Poisson maximum likelihood (Fit23).  The Qt-free computation core
lives in :mod:`.core.molecule_mle`; the AutoForm GUI is in :mod:`.gui`.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Imaging:Lifetime:Molecule-wise MLE"
cli_entrypoint = "sm-image-mle=chisurf.plugins.microscopy.sm_image_mle.cli:cli"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text())
    name = _manifest.get("display_name", name)


def __getattr__(attr_name: str):
    """Lazy Qt gate for the GUI entrypoint (keeps the package import Qt-free)."""
    if attr_name == "SmImageMleTool":
        from .gui.tool import SmImageMleTool as _cls

        globals()["SmImageMleTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


__all__ = ["SmImageMleTool"]
