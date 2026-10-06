"""Integrated burst analysis GUI package.

``BurstAnalysisTool`` (the legacy Qt shell) is imported on first use, so the native hub (``.native``) imports
without Qt.
"""

__all__ = ["BurstAnalysisTool"]


def __getattr__(name):
    if name == "BurstAnalysisTool":
        from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

        return BurstAnalysisTool
    raise AttributeError(name)
