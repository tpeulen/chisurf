"""GUI entry point for the FRC resolution calculator (toolbar + AutoForm)."""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import FrcViewModel

logger = logging.getLogger(__name__)


class _ComputeSignals(QtCore.QObject):
    """Cross-thread signals for the background measurement."""

    progress = QtCore.Signal(float, str)
    finished = QtCore.Signal(bool)


class _ComputeTask(QtCore.QRunnable):
    """Run the Qt-free measurement off the UI thread (image reads are slow)."""

    def __init__(self, model):
        super().__init__()
        self._model = model
        self.signals = _ComputeSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        ok = False
        try:
            ok = bool(
                self._model.compute(
                    progress=lambda f, t: self.signals.progress.emit(float(f), str(t))
                )
            )
        except Exception:
            logger.debug("background FRC measurement failed", exc_info=True)
        self.signals.finished.emit(ok)


class ImgFrcTool(ChisurfDockTool):
    """FRC resolution calculator: action toolbar + ``AutoForm(view_model)``."""

    tool_settings_name = "ImgFrcTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or FrcViewModel()
        self.setWindowTitle("FRC resolution")
        self.setMinimumSize(900, 600)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("▶ Measure")
        a_run.setToolTip("Correlate the two halves and read the resolution off the crossing.")
        a_run.triggered.connect(self.run_with_progress)
        a_csv = toolbar.addAction("💾 Export CSV")
        a_csv.setToolTip("Write the curve, its threshold and the ring counts to a CSV file.")
        a_csv.triggered.connect(self._export_csv)
        # Long help behind a ? at the far right of the toolbar — never inline text.
        self.add_toolbar_help(toolbar, resource="help.md", title="FRC resolution — help")
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        self.auto_form = AutoForm(self.model)
        self.setCentralWidget(self.auto_form)
        self.modelEvent.connect(self._handle_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()

    # ── actions ──
    def run_with_progress(self) -> None:
        """Measure in a worker thread so the UI stays responsive."""
        self.statusBar().showMessage("Measuring…")
        task = _ComputeTask(self.model)
        task.signals.progress.connect(
            lambda f, t: self.statusBar().showMessage(f"{t} ({int(f * 100)} %)")
        )
        task.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(task)

    def _on_finished(self, ok: bool) -> None:
        """Refresh the form once the background run finished."""
        self.statusBar().showMessage(self.model.status if ok else "Measurement failed", 8000)
        self._refresh()

    def _export_csv(self) -> None:
        """Ask for a path and write the measured curve to it."""
        if self.model.result is None:
            self.statusBar().showMessage("Nothing to export yet", 5000)
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export FRC curve", "frc_resolution.csv", "CSV (*.csv)"
        )
        if not path:
            return
        written = self.model.export_csv(path)
        self.statusBar().showMessage(f"Wrote {written}", 8000)

    # ── imaging-toolbox adapters ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Forward the shared imaging detector setup to the view model."""
        self.model.apply_setup_settings(payload)
        self._refresh()

    def apply_pipeline_context(self, payload: dict) -> None:
        """Forward the shared pipeline context (source + HDF5) to the view model."""
        self.model.apply_pipeline_context(payload)
        self._refresh()

    # ── model / window plumbing ──
    def _refresh(self) -> None:
        """Re-read the model into the form (values, tables and image docks)."""
        try:
            self.auto_form.sync_fields()
        except Exception:
            logger.debug("AutoForm field sync failed", exc_info=True)
        try:
            self.auto_form.refresh_plots()
        except Exception:
            logger.debug("AutoForm plot refresh failed", exc_info=True)

    def _handle_model_event(self, event: str) -> None:
        """React to view-model events on the GUI thread."""
        self._refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the window geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)


__all__ = ["ImgFrcTool"]
