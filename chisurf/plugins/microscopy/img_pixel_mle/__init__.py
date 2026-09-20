"""Pixel-wise lifetime MLE analysis.

This plugin provides a powerful interface for analyzing fluorescence lifetime data
from imaging experiments using Maximum Likelihood Estimation (MLE).

Features:
- Analysis of image data from Time-Tagged Time-Resolved (TTTR) measurements
- Maximum Likelihood Estimation for accurate fluorescence lifetime determination
- Handling of Instrument Response Function (IRF) and background corrections
- Support for multiple detector channels
- Interactive visualization of lifetime fits and results
- Comprehensive parameter adjustment for optimizing analysis
- Export of results in various formats

MLE is particularly advantageous for fluorescence lifetime analysis
as it provides more accurate parameter estimates than traditional least-squares methods
when dealing with low photon counts.

The methodology implemented in this plugin is based on the approach described in:
Maus, M., Cotlet, M., Hofkens, J., Gensch, T., De Schryver, F. C., Schaffer, J., & Seidel, C. A. (2001).
An Experimental Comparison of the Maximum Likelihood Estimation and Nonlinear Least-Squares
Fluorescence Lifetime Analysis of Single Molecules.
Analytical Chemistry, 73(9), 2078-2086. https://doi.org/10.1021/ac000877g
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Imaging:Lifetime:Pixel-wise lifetime MLE"
cli_entrypoint = "img-pixel-mle=chisurf.plugins.microscopy.img_pixel_mle.cli:cli"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text(encoding="utf-8"))
    name = _manifest.get("display_name", name)


def __getattr__(attr_name: str):
    """Lazy Qt gate for the GUI entrypoint (keeps the package import Qt-free)."""
    if attr_name == "ImgPixelMleTool":
        from .gui.tool import ImgPixelMleTool as _cls

        globals()["ImgPixelMleTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


def run():
    """Run the pixel-wise MLE tool (standalone window)."""
    from .gui.tool import ImgPixelMleTool

    tool = ImgPixelMleTool()
    tool.show()
    return tool


__all__ = ["ImgPixelMleTool", "run"]
