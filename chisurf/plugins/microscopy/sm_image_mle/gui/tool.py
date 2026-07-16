"""GUI entrypoint for the molecule-wise MLE tool (AutoForm + view.json).

``SmImageMleTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~...gui.view_model.MoleculeMleViewModel`.  The heavy analysis
(``view_model.run``) runs on a background thread so the UI never blocks, and the
segmentation image / molecule table refresh when it finishes.

``apply_setup_settings(payload)`` forwards a shared detector definition (from the
Imaging Tools aggregator) to the view-model; ``embedded`` is accepted for API
uniformity.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm

from .view_model import MoleculeMleViewModel

logger = logging.getLogger(__name__)


class _RunSignals(QtCore.QObject):
    """Signal emitted when a background analysis run finishes."""

    done = QtCore.Signal()


class _RunTask(QtCore.QRunnable):
    """Run a (slow) view-model job off the UI thread."""

    def __init__(self, job, signals: _RunSignals):
        super().__init__()
        self._job = job
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        try:
            self._job()
        except Exception:
            logger.debug("molecule-MLE job failed", exc_info=True)
        self._signals.done.emit()


class SmImageMleTool(QtWidgets.QWidget):
    """Molecule-wise MLE tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or MoleculeMleViewModel()
        self.setWindowTitle("Molecule-wise MLE")
        self.setMinimumSize(640, 420)
        self._running = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)
        self.model.add_observer(self._on_model_event)

    def apply_setup_settings(self, payload: dict) -> None:
        """Forward a shared detector definition to the view-model."""
        self.model.apply_setup_settings(payload)
        self._refresh()

    def apply_pipeline_context(self, payload: dict) -> None:
        """Forward the imaging pipeline's source TTTR to the view-model."""
        self.model.apply_pipeline_context(payload)
        self._refresh()

    def apply_calibration(self, calibration: dict) -> None:
        """Forward the shared IRF/BG calibration to the view-model."""
        self.model.apply_calibration(calibration)
        self._refresh()

    def _on_model_event(self, event: str) -> None:
        # ``start_run`` fires on the UI thread (button click) — launch the worker.
        # ``progress``/``done`` may fire on the worker thread; touching Qt there is
        # unsafe, so ignore them (the queued ``_RunSignals.done`` refreshes the UI).
        if event == "start_run":
            self._start_job(self.model.run)
            return
        if event == "start_preview":
            self._start_job(self.model.preview_segmentation)
            return
        if event == "start_export":
            self._export()
            return
        if QtCore.QThread.currentThread() is not self.thread():
            return
        self._refresh()

    def _export(self) -> None:
        """Prompt for a path and export the molecule table (UI thread)."""
        if not self.model.has_results():
            self.model.status_text = "No molecules to export."
            self._refresh()
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export molecule table", "molecules.tsv", "Tables (*.tsv *.csv)"
        )
        if path:
            self.model.export_results(path)

    def _refresh(self) -> None:
        for fn in (self.auto_form.sync_fields, self.auto_form.refresh_plots):
            try:
                fn()
            except Exception:
                logger.debug("molecule-MLE refresh failed", exc_info=True)

    def _start_job(self, job) -> None:
        if self._running:
            return
        self._running = True
        signals = _RunSignals()
        signals.done.connect(self._on_run_done)
        self._run_signals = signals  # keep a ref
        QtCore.QThreadPool.globalInstance().start(_RunTask(job, signals))

    def _on_run_done(self) -> None:
        self._running = False
        self._refresh()


__all__ = ["SmImageMleTool"]
