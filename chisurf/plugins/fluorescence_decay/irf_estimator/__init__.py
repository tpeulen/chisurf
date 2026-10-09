"""IRF Estimator Plugin.

Blind IRF estimation from fluorescence decay data using truncated exponential
fitting and Richardson-Lucy deconvolution.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "⚡"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Spectroscopy:Fluorescence decay:IRF Extraction"


__all__ = ["IRFEstimatorTool"]


# When the plugin is loaded as a module with __name__ == "plugin",
# the ChiSurf plugin host directly executes this file in a custom
# namespace.  In that case we instantiate and show the GUI.
def __getattr__(name):
    if name == "IRFEstimatorTool":
        from .gui.tool import IRFEstimatorTool

        return IRFEstimatorTool
    raise AttributeError(name)


if __name__ == "plugin":
    from .gui.tool import IRFEstimatorTool

    gui = IRFEstimatorTool()
    gui.show()
