"""GUI entrypoint for the CLSM Generator (AutoForm + view.json).

``ClsmGeneratorTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to
the Qt-free :class:`~...gui.view_model.ClsmGeneratorViewModel`.  Generation runs
on a background thread so the UI never blocks, and the viewer refreshes when it
finishes; saving prompts for a path on the UI thread.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm

from .view_model import ClsmGeneratorViewModel

logger = logging.getLogger(__name__)


class _JobSignals(QtCore.QObject):
    """Signal emitted when a background job finishes."""

    done = QtCore.Signal()


class _JobTask(QtCore.QRunnable):
    """Run a (slow) view-model job off the UI thread."""

    def __init__(self, job, signals: _JobSignals):
        super().__init__()
        self._job = job
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        try:
            self._job()
        except Exception:
            logger.debug("clsm-generator job failed", exc_info=True)
        self._signals.done.emit()


class ClsmGeneratorTool(QtWidgets.QWidget):
    """CLSM generator tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or ClsmGeneratorViewModel()
        self.setWindowTitle("CLSM Generator")
        self.setMinimumSize(640, 440)
        self._running = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)
        self.model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        if event == "start_generate":
            self._start_job(self.model.generate)
            return
        if event == "start_save":
            self._save()
            return
        if QtCore.QThread.currentThread() is not self.thread():
            return
        self._refresh()

    def _refresh(self) -> None:
        for fn in (self.auto_form.sync_fields, self.auto_form.refresh_plots):
            try:
                fn()
            except Exception:
                logger.debug("clsm-generator refresh failed", exc_info=True)

    def _start_job(self, job) -> None:
        if self._running:
            return
        self._running = True
        signals = _JobSignals()
        signals.done.connect(self._on_job_done)
        self._job_signals = signals  # keep a ref
        QtCore.QThreadPool.globalInstance().start(_JobTask(job, signals))

    def _on_job_done(self) -> None:
        self._running = False
        self._refresh()

    def _save(self) -> None:
        """Prompt for a path and save the generated photon stream (UI thread)."""
        if not self.model.has_result():
            self.model.status_text = "Nothing generated yet."
            self._refresh()
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save photon stream", "clsm_sim.npz",
            "Photon stream (*.pto *.npz *.ptu *.spc *.ht3)",
        )
        if path:
            self.model.save(path)


__all__ = ["ClsmGeneratorTool"]
