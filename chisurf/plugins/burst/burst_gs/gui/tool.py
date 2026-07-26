"""GUI entry point for the Gopich-Szabo tool (toolbar + file drops + AutoForm)."""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import BurstGsViewModel

logger = logging.getLogger(__name__)


class _ComputeSignals(QtCore.QObject):
    """Cross-thread signals for the background fit."""

    progress = QtCore.Signal(float, str)
    finished = QtCore.Signal(bool)


class _ComputeTask(QtCore.QRunnable):
    """Run the Qt-free fit off the UI thread (it can take minutes)."""

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
            logger.debug("background Gopich-Szabo fit failed", exc_info=True)
        self.signals.finished.emit(ok)


class BurstGsTool(ChisurfDockTool):
    """Photon-by-photon kinetics tool: action toolbar + ``AutoForm(view_model)``."""

    tool_settings_name = "BurstGsTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or BurstGsViewModel()
        self.setWindowTitle("Photon-by-photon kinetics")
        self.setMinimumSize(1040, 680)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("▶ Fit")
        a_run.setToolTip(
            "Fit kinetic rates and per-state FRET efficiencies to the arrival "
            "time and colour of every photon."
        )
        a_run.triggered.connect(self.run_with_progress)
        a_csv = toolbar.addAction("💾 Export CSV")
        a_csv.setToolTip("Write the fitted rates, efficiencies and any scan to a CSV file.")
        a_csv.triggered.connect(self._export_csv)
        # Long help behind a ? at the far right of the toolbar — never inline text.
        self.add_toolbar_help(toolbar, resource="help.md", title="Photon-by-photon kinetics — help")
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
        """Fit in a worker thread so the UI stays responsive."""
        reason = self.model.can_run()
        if reason:
            self.statusBar().showMessage(reason, 8000)
            return
        self.statusBar().showMessage("Fitting…")
        task = _ComputeTask(self.model)
        task.signals.progress.connect(
            lambda f, t: self.statusBar().showMessage(f"{t} ({int(f * 100)} %)")
        )
        task.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(task)

    def _on_finished(self, ok: bool) -> None:
        """Refresh the form once the background fit finished."""
        analysis = self.model.analysis
        if ok and analysis is not None:
            matrix = analysis.fit.rate_matrix
            message = (
                f"logL = {analysis.fit.log_likelihood:,.1f}, "
                f"k(1→2) = {matrix[1, 0]:,.0f} /s, k(2→1) = {matrix[0, 1]:,.0f} /s"
            )
        else:
            message = "The fit did not produce a result — see the report."
        self.statusBar().showMessage(message, 12000)
        self._refresh()

    def _export_csv(self) -> None:
        """Ask for a path and write the fitted parameters to it."""
        if self.model.analysis is None:
            self.statusBar().showMessage("Run a fit first.", 6000)
            return
        default = ""
        if self.model.bur_files:
            default = str(pathlib.Path(self.model.bur_files[0]).with_suffix(".gs.csv"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export photon-by-photon kinetics", default, "CSV (*.csv)"
        )
        if path:
            self.model.export_csv(path)
            self.statusBar().showMessage(f"Wrote {path}", 8000)

    # ── model / window plumbing ──
    def _refresh(self) -> None:
        """Re-read the model into the form (values, tables and plots)."""
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

    def on_paths_dropped(self, paths) -> None:
        """Add dropped burst tables to the file list."""
        added = [str(p) for p in paths if str(p).lower().endswith(".bur")]
        if added:
            self.model.bur_files = list(self.model.bur_files) + added
            self.model.notify("changed")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the window geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)


__all__ = ["BurstGsTool"]
