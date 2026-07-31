"""GUI entry point for the flow-map tool (toolbar + AutoForm + guided tour)."""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import FlowViewModel

logger = logging.getLogger(__name__)


class _TaskSignals(QtCore.QObject):
    """Cross-thread signals for a background job."""

    progress = QtCore.Signal(float, str)
    finished = QtCore.Signal(bool)


class _Task(QtCore.QRunnable):
    """Run a Qt-free job off the UI thread (image reads and scans are slow)."""

    def __init__(self, fn):
        super().__init__()
        self._fn = fn
        self.signals = _TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        ok = False
        try:
            ok = bool(
                self._fn(
                    progress=lambda f, t: self.signals.progress.emit(float(f), str(t))
                )
            )
        except Exception:
            logger.debug("background flow job failed", exc_info=True)
        self.signals.finished.emit(ok)


class ImgFlowTool(ChisurfDockTool):
    """Flow-map tool: action toolbar + ``AutoForm(view_model)`` + a guided tour."""

    tool_settings_name = "ImgFlowTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or FlowViewModel()
        self.setWindowTitle("Flow map")
        self.setMinimumSize(1000, 640)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("▶ Map flow")
        a_run.setToolTip("Track each tile's correlation peak and read its velocity.")
        a_run.triggered.connect(self.run_with_progress)
        a_demo = toolbar.addAction("🧪 Load demo")
        a_demo.setToolTip(
            "Simulate a scan whose flow profile is known, and load it — so the "
            "arrows can be checked against a number."
        )
        a_demo.triggered.connect(self.load_demo_with_progress)
        a_csv = toolbar.addAction("💾 Export CSV")
        a_csv.setToolTip("Write one row per tile — position, velocity and quality.")
        a_csv.triggered.connect(self._export_csv)
        # The guide walks the user through the tool -- it points at these very
        # buttons and waits for the user to press them, so it needs no code of
        # its own here. The ? beside it holds the long text.
        self.add_toolbar_guide(toolbar, resource="guide.json")
        self.add_toolbar_help(toolbar, resource="help.md", title="Flow maps — help")
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
        self.statusBar().showMessage("Mapping…")
        self._start(self.model.compute)

    def load_demo_with_progress(self) -> None:
        """Simulate (or reuse) the demo photon stream in a worker thread."""
        self.statusBar().showMessage("Simulating the demo scan…")

        def job(progress=None):
            self.model.load_demo(progress=progress)
            return True

        self._start(job)

    def _start(self, fn) -> None:
        task = _Task(fn)
        task.signals.progress.connect(
            lambda f, t: self.statusBar().showMessage(f"{t} ({int(f * 100)} %)")
        )
        task.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(task)

    def _on_finished(self, ok: bool) -> None:
        """Refresh the form once the background run finished."""
        self.statusBar().showMessage(self.model.status, 8000)
        self._refresh()

    def _export_csv(self) -> None:
        """Ask for a path and write the velocity field to it."""
        if self.model.result is None:
            self.statusBar().showMessage("Nothing to export yet", 5000)
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export flow map", "flow_map.csv", "CSV (*.csv)"
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
        """Re-read the model into the form (values, tables, plots and the field)."""
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


__all__ = ["ImgFlowTool"]
