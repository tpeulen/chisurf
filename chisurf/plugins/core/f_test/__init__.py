"""F-test / χ²-max calculator plugin.

Compare two nested model fits (confidence ↔ χ² threshold) and compute the
χ²-max upper limit of a single fit at a confidence level. The GUI is a
declarative AutoForm (:mod:`chisurf.plugins.core.f_test.gui.tool`).
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

from .gui.tool import FTestTool, FTestWidget  # noqa: F401

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Main:Tools:F-Test"

__all__ = ["FTestTool", "FTestWidget"]

if __name__ == "plugin":
    window = FTestTool()
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
