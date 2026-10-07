"""Existing Qt window entry point hosting the one native FCS workflow."""

from __future__ import annotations

from emtk.qt_host import ControlHost

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app
from chisurf.plugins.fcs.fcs_correlator.workflow import FcsWorkflowContext

__all__ = ["FcsCorrelatorTool", "FcsWorkflowContext"]


class FcsCorrelatorTool(ChisurfDockTool):
    """Retain a Qt host while all workflow controls live in the native app."""

    def __init__(self, parent=None, *, app=None, title="FCS Correlator"):
        """Host the native workflow in the existing Qt tool window.

        Parameters
        ----------
        parent : QWidget, optional
            Existing owner window.
        app : FcsHubApp, optional
            App already composed by the full FCS hub.
        title : str, optional
            Host window title.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1180, 760)
        self.app = app if app is not None else make_app()
        self.host = ControlHost(self.app, parent=self)
        self.setCentralWidget(self.host)

    @property
    def workflow(self):
        """Expose the actual scientific workflow owned by the native surface."""
        return self.app.workflow

    @property
    def workflow_context(self):
        """Expose the same shared file/detector/filter context to existing callers."""
        return self.app.workflow.context

    def show_panel_by_role(self, role):
        """Navigate the real native rail, including the Filter Calculator callback."""
        if not any(panel["role"] == role for panel in self.app.tools):
            return False
        self.app.select(role)
        self.app.request_frame()
        self.host.update()
        return self.app.selected == role

    def closeEvent(self, event):
        """Close native children/workers before the existing Qt host is released."""
        self.host.close()
        super().closeEvent(event)
