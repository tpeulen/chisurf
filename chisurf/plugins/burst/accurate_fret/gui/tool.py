"""GUI entry point for the accurate-FRET tool (toolbar + file drops + AutoForm)."""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import AccurateFretViewModel

logger = logging.getLogger(__name__)


class AccurateFretTool(ChisurfDockTool):
    """Accurate-FRET calibration tool: action toolbar + ``AutoForm(view_model)``."""

    tool_settings_name = "AccurateFretTool"

    class Error(ChisurfDockTool.Error):
        """Conditions that stop the calibration from running or finishing."""

        not_ready = Msg("{}")
        failed = Msg("Calibration failed: {}")
        no_result = Msg("The calibration produced no result — see the report.")

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or AccurateFretViewModel()
        self.setWindowTitle("Accurate FRET")
        self.setMinimumSize(1000, 640)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_run = toolbar.addAction("🎯 Calibrate")
        a_run.setToolTip(
            "Find the burst populations and determine alpha, beta, gamma and delta "
            "from them (combined with the optics prior)."
        )
        a_run.triggered.connect(self.run_with_progress)
        a_ndx = toolbar.addAction("📥 From ndX")
        a_ndx.setToolTip("Take the burst columns from an open ndX window.")
        a_ndx.triggered.connect(self._load_from_ndx)
        a_push = toolbar.addAction("📤 To ndX")
        a_push.setToolTip("Push the calibrated factors into ndX's MFD constants.")
        a_push.triggered.connect(self._push_to_ndx)
        a_register = toolbar.addAction("🔗 Share in session")
        a_register.setToolTip(
            "Publish the calibration so any fit can link its correction parameters to it."
        )
        a_register.triggered.connect(self._register)
        a_setup = toolbar.addAction("🔬 Store on setup")
        a_setup.setToolTip(
            "Save the factors on the selected detector setup. They belong to the "
            "instrument, not to this file, so every tool that picks the same setup "
            "starts from the measured calibration instead of defaults."
        )
        a_setup.triggered.connect(self._store_on_setup)
        a_csv = toolbar.addAction("💾 Export CSV")
        a_csv.setToolTip("Write the per-burst accurate E, S, lifetime and distance to a CSV file.")
        a_csv.triggered.connect(self._export_csv)
        # Long help behind a ? at the far right of the toolbar — never inline text.
        self.add_toolbar_help(toolbar, resource="help.md", title="Accurate FRET — help")
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
        """Calibrate off the GUI thread so the window stays usable.

        Bootstrapping is slow; the progress, the Cancel and the delivery of the
        result all come from the shared task layer rather than from a per-tool
        ``QRunnable``.
        """
        reason = self.model.can_run()
        if reason:
            self.Error.not_ready(reason)
            return
        self.Error.clear()
        ChiSurfProgress.run(
            self, "Calibrating…", self._calibrate, maximum=100,
            on_result=self._calibrated,
            on_error=self.Error.failed,
            on_done=self._refresh,
            title="Accurate FRET",
        )

    def _calibrate(self, task) -> bool:
        """Worker: run the Qt-free calibration through *task*. No GUI here."""
        def report(fraction: float, message: str) -> None:
            task.raise_if_cancelled()
            task.set_fraction(float(fraction), str(message))

        return bool(self.model.compute(progress=report))

    def _calibrated(self, ok: bool) -> None:
        """Back on the GUI thread with the correction factors (or with nothing)."""
        if ok and self.model.result is not None:
            factors = self.model.result.factors
            self.Error.no_result.clear()
            self.statusBar().showMessage(
                f"gamma = {factors['gamma']:.3f}, beta = {factors['beta']:.3f}, "
                f"alpha = {factors['alpha']:.3f}, delta = {factors['delta']:.3f}",
                12000,
            )
        else:
            self.Error.no_result()

    def _load_from_ndx(self) -> None:
        """Pull the burst columns from an open ndX window."""
        self.statusBar().showMessage(self.model.load_from_ndxplorer(), 8000)
        self._refresh()

    def _push_to_ndx(self) -> None:
        """Push the calibrated factors into ndX."""
        self.statusBar().showMessage(self.model.push_to_ndxplorer(), 8000)

    def _register(self) -> None:
        """Publish the calibration as a session-wide link target."""
        self.statusBar().showMessage(self.model.register_in_session(), 8000)

    def _store_on_setup(self) -> None:
        """Attach the calibration to the selected detector setup."""
        self.statusBar().showMessage(self.model.save_calibration_to_setup(), 8000)

    def _export_csv(self) -> None:
        """Ask for a path and write the per-burst accurate values to it."""
        if self.model.result is None:
            self.statusBar().showMessage("Run a calibration first.", 6000)
            return
        default = ""
        if self.model.filename and not self.model.filename.startswith("<"):
            default = str(pathlib.Path(self.model.filename).with_suffix(".accurate.csv"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export accurate FRET", default, "CSV (*.csv)"
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
        """Load the first dropped burst table."""
        if paths:
            self.model.set_filename(str(paths[0]))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the window geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)


__all__ = ["AccurateFretTool"]
