"""GUI entry point for the drift-correction tool (toolbar + file drops + AutoForm)."""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import DriftViewModel

logger = logging.getLogger(__name__)


class _ComputeSignals(QtCore.QObject):
    """Cross-thread signals for the background drift measurement."""

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
            logger.debug("background drift measurement failed", exc_info=True)
        self.signals.finished.emit(ok)


class ImgDriftTool(ChisurfDockTool):
    """Drift-correction tool: action toolbar + ``AutoForm(view_model)``."""

    tool_settings_name = "ImgDriftTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or DriftViewModel()
        self.setWindowTitle("Drift correction")
        self.setMinimumSize(900, 600)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("▶ Measure")
        a_run.setToolTip("Measure the inter-frame drift of the selected channel.")
        a_run.triggered.connect(self.run_with_progress)
        a_stack = toolbar.addAction("💾 Export stack")
        a_stack.setToolTip("Write the drift-corrected stack as a multi-page TIFF.")
        a_stack.triggered.connect(self._export_stack)
        a_csv = toolbar.addAction("💾 Export shifts")
        a_csv.setToolTip("Write the per-frame displacements to a CSV file.")
        a_csv.triggered.connect(self._export_shifts)
        # Long help behind a ? at the far right of the toolbar — never inline text.
        self.add_toolbar_help(toolbar, resource="help.md", title="Drift correction — help")
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
        if not getattr(self.model, "filename", ""):
            return
        self.statusBar().showMessage("Measuring drift…")
        task = _ComputeTask(self.model)
        task.signals.progress.connect(
            lambda f, t: self.statusBar().showMessage(f"{t} ({int(f * 100)} %)")
        )
        task.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(task)

    def _on_finished(self, ok: bool) -> None:
        """Refresh the form once the background run finished."""
        self.statusBar().showMessage(self.model.status if ok else "Drift measurement failed", 8000)
        self._refresh()

    def _default_path(self, suffix: str) -> str:
        """Return a sensible default export path next to the source file."""
        if not self.model.filename:
            return ""
        return str(pathlib.Path(self.model.filename).with_suffix(suffix))

    def _export_stack(self) -> None:
        """Ask for a path and write the corrected stack to it."""
        if self.model.result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export corrected stack",
            self._default_path(".corrected.tif"),
            "TIFF (*.tif *.tiff)",
        )
        if path:
            self.statusBar().showMessage("Writing corrected stack…")
            written = self.model.export(stack_path=path)
            self.statusBar().showMessage(f"Wrote {written.get('stack', path)}", 8000)

    def _export_shifts(self) -> None:
        """Ask for a path and write the shift table to it."""
        if self.model.result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export drift shifts", self._default_path(".drift.csv"), "CSV (*.csv)"
        )
        if path:
            written = self.model.export(shifts_path=path)
            self.statusBar().showMessage(f"Wrote {written.get('shifts', path)}", 8000)

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
        if event == "file":
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


__all__ = ["ImgDriftTool"]
