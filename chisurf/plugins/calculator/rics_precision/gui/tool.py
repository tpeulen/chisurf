"""GUI entry point for the RICS-precision calculator (the emtk app in a Qt host).

The UI is :class:`~.app.RicsPrecisionApp` over the Qt-free
:class:`~.view_model.PrecisionViewModel`; this window only hosts it through
:class:`emtk.qt_host.ControlHost`. The sweep runs on the app's own worker, so the Qt side keeps
nothing but the window geometry. The calculator hub embeds this class with its own view model.
"""

from __future__ import annotations

import logging

from qtpy import QtCore

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import PrecisionViewModel

logger = logging.getLogger(__name__)


class _FormShim:
    """Compatibility shim for callers expecting an AutoForm interface."""

    def __init__(self, host) -> None:
        self._host = host

    def sync_fields(self) -> None:
        self._host.update()

    def refresh_plots(self) -> None:
        self._host.update()


class RicsPrecisionTool(ChisurfDockTool):
    """RICS-precision calculator: the emtk app in a Qt window."""

    tool_settings_name = "RicsPrecisionTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or PrecisionViewModel()
        self.setWindowTitle("RICS precision")
        self.setMinimumSize(900, 600)

        from emtk.qt_host import ControlHost

        from .app import RicsPrecisionApp

        self.app = RicsPrecisionApp(self.model)
        self.host = ControlHost(self.app)
        self.setCentralWidget(self.host)
        self.auto_form = _FormShim(self.host)

        self.modelEvent.connect(self._handle_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()

    # ── actions ──
    def run_with_progress(self) -> None:
        """Predict on the app's worker so the UI stays responsive."""
        self.app.predict()
        self._refresh()

    def _export_csv(self) -> None:
        """Open the app's Export CSV dialog (nothing to write before a prediction)."""
        self.app.start_export()
        self._refresh()

    # ── model / window plumbing ──
    def _refresh(self) -> None:
        """Repaint the canvas (values, table and plot come from the model)."""
        if hasattr(self, "host"):
            self.host.update()

    def _handle_model_event(self, event: str) -> None:
        """React to view-model events on the GUI thread."""
        self._refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the window geometry on close."""
        self.save_window_geometry()
        self.app.close()
        super().closeEvent(event)


__all__ = ["RicsPrecisionTool"]
