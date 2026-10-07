"""Existing FCS Qt entry point hosting the complete native workflow and tools."""

from __future__ import annotations

from chisurf.plugins.fcs.fcs_correlator.tool import FcsCorrelatorTool
from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app

__all__ = ["FcsTool", "FcsToolboxTool"]


class FcsTool(FcsCorrelatorTool):
    """The native five-step correlator and all five optional tools in one host."""

    def __init__(self, parent=None):
        super().__init__(parent=parent, app=make_app(), title="FCS")


FcsToolboxTool = FcsTool
