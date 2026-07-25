"""GUI entry point for the colocalization tool (toolbar + file drops + AutoForm)."""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import ColocViewModel

logger = logging.getLogger(__name__)


class _ComputeSignals(QtCore.QObject):
    """Cross-thread signals for the background colocalization run."""

    progress = QtCore.Signal(float, str)
    finished = QtCore.Signal(bool)


class _ComputeTask(QtCore.QRunnable):
    """Run the Qt-free ``compute`` off the UI thread (image reads are slow)."""

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
            logger.debug("background colocalization failed", exc_info=True)
        self.signals.finished.emit(ok)


class ImgColocTool(ChisurfDockTool):
    """Two-channel colocalization tool: action toolbar + ``AutoForm(view_model)``."""

    tool_settings_name = "ImgColocTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or ColocViewModel()
        self.setWindowTitle("Colocalization")
        self.setMinimumSize(900, 600)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("▶ Run")
        a_run.setToolTip("Compute the colocalization coefficients for the selected channel pair.")
        a_run.triggered.connect(self.run_with_progress)
        a_bg = toolbar.addAction("📉 Estimate background")
        a_bg.setToolTip(
            "Set both channel backgrounds from the low intensity quantile and recompute."
        )
        a_bg.triggered.connect(self._estimate_background)
        a_csv = toolbar.addAction("💾 Export CSV")
        a_csv.setToolTip("Write the coefficient table to a CSV file.")
        a_csv.triggered.connect(self._export_csv)
        # Long help behind a ? at the far right of the toolbar — never inline text.
        self.add_toolbar_help(toolbar, resource="help.md", title="Colocalization — help")
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        self.auto_form = AutoForm(self.model)
        self.setCentralWidget(self.auto_form)
        # The view-model also notifies from the compute worker; the signal hop
        # guarantees the handler (which touches widgets) runs on the GUI thread.
        self.modelEvent.connect(self._handle_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()

    # ── actions ──
    def run_with_progress(self) -> None:
        """Compute in a worker thread so the UI stays responsive."""
        if not getattr(self.model, "filename", ""):
            return
        self.statusBar().showMessage("Computing colocalization…")
        task = _ComputeTask(self.model)
        task.signals.progress.connect(
            lambda f, t: self.statusBar().showMessage(f"{t} ({int(f * 100)} %)")
        )
        task.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(task)

    def _on_finished(self, ok: bool) -> None:
        """Refresh the form once the background run finished."""
        self.statusBar().showMessage(
            self.model.results_text if ok else "Colocalization failed", 8000
        )
        self._refresh()

    def _estimate_background(self) -> None:
        """Estimate both backgrounds from the loaded images and recompute."""
        self.model.estimate_background()
        self._refresh()

    def _export_csv(self) -> None:
        """Ask for a path and write the coefficient table to it."""
        if not self.model.metric_rows():
            return
        default = ""
        if self.model.filename:
            default = str(pathlib.Path(self.model.filename).with_suffix(".coloc.csv"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export colocalization results", default, "CSV (*.csv)"
        )
        if path:
            self.model.export_csv(path)
            self.statusBar().showMessage(f"Wrote {path}", 8000)

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
        """React to view-model events on the GUI thread.

        A new file (or a new detector setup) triggers a run; a finished run or a
        changed display refreshes the form.
        """
        if event in ("file", "setup"):
            self.run_with_progress()
        else:
            self._refresh()

    def on_paths_dropped(self, paths) -> None:
        """Load the first dropped image/photon-stream file."""
        if paths:
            self.model.set_filename(str(paths[0]))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the window geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)


__all__ = ["ImgColocTool"]
