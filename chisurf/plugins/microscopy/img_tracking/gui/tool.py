"""GUI entry point for the particle-tracking tool (toolbar + drops + AutoForm)."""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import ImgTrackingViewModel

logger = logging.getLogger(__name__)


class _ComputeSignals(QtCore.QObject):
    """Cross-thread signals for the background tracking run."""

    progress = QtCore.Signal(float, str)
    finished = QtCore.Signal(bool)


class _ComputeTask(QtCore.QRunnable):
    """Run the Qt-free pipeline off the UI thread (a long movie takes a while)."""

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
            logger.debug("background tracking run failed", exc_info=True)
        self.signals.finished.emit(ok)


class ImgTrackingTool(ChisurfDockTool):
    """Particle-tracking tool: action toolbar + ``AutoForm(view_model)``."""

    tool_settings_name = "ImgTrackingTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or ImgTrackingViewModel()
        self.setWindowTitle("Particle tracking")
        self.setMinimumSize(1040, 680)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("▶ Track")
        a_run.setToolTip(
            "Detect particles in every frame, link them into trajectories, and "
            "fit the diffusion coefficient."
        )
        a_run.triggered.connect(self.run_with_progress)
        a_open = toolbar.addAction("📂 Open")
        a_open.setToolTip("Choose an image stack or photon-stream file to track.")
        a_open.triggered.connect(self._open)
        a_csv = toolbar.addAction("💾 Export CSV")
        a_csv.setToolTip("Write every linked detection (track, frame, y, x) to a CSV file.")
        a_csv.triggered.connect(self._export_csv)
        # Long help behind a ? at the far right of the toolbar — never inline text.
        self.add_toolbar_help(toolbar, resource="help.md", title="Particle tracking — help")
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
        """Track in a worker thread so the UI stays responsive."""
        reason = self.model.can_run()
        if reason:
            self.statusBar().showMessage(reason, 8000)
            return
        self.statusBar().showMessage("Tracking…")
        task = _ComputeTask(self.model)
        task.signals.progress.connect(
            lambda f, t: self.statusBar().showMessage(f"{t} ({int(f * 100)} %)")
        )
        task.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(task)

    def _on_finished(self, ok: bool) -> None:
        """Refresh the form once the background run finished."""
        result = self.model.result
        if ok and result is not None:
            if result.fit is not None:
                message = (
                    f"{len(result.tracks)} tracks, "
                    f"D = {result.fit.diffusion_coefficient:.4g} ± "
                    f"{result.fit.diffusion_coefficient_error:.2g}"
                )
            else:
                message = f"{len(result.tracks)} tracks — no transport fit; see the report."
        else:
            message = "Tracking did not produce a result — see the report."
        self.statusBar().showMessage(message, 12000)
        self._refresh()

    def _open(self) -> None:
        """Ask for an image stack and load it."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open image stack",
            "",
            "Images and photon streams (*.pto *.tif *.tiff *.ptu *.ht3 *.spc *.hdf *.h5);;All files (*)",
        )
        if path:
            self.model.set_filename(path)

    def _export_csv(self) -> None:
        """Ask for a path and write the linked detections to it."""
        if self.model.result is None:
            self.statusBar().showMessage("Run the tracker first.", 6000)
            return
        default = ""
        if self.model.filename:
            default = str(pathlib.Path(self.model.filename).with_suffix(".tracks.csv"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export tracks", default, "CSV (*.csv)"
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
        """Load the first dropped image stack."""
        if paths:
            self.model.set_filename(str(paths[0]))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the window geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)


__all__ = ["ImgTrackingTool"]
