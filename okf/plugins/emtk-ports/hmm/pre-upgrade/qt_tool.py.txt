"""GUI entrypoint for the hidden-Markov-model tool (AutoForm + view.json).

``HmmTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~.view_model.HmmViewModel`. Fitting runs on a background thread
so the window stays responsive on long traces, and the plots refresh when it
finishes.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm

from .view_model import HmmViewModel

logger = logging.getLogger(__name__)

__all__ = ["HmmTool"]


class _Worker(QtCore.QThread):
    """Runs one blocking view-model job off the UI thread."""

    failed = QtCore.Signal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self._job = job

    def run(self) -> None:
        """Execute the job, reporting an exception rather than dying silently."""
        try:
            self._job()
        except Exception as exc:  # pragma: no cover - defensive, job logs its own
            logger.exception("HMM job failed")
            self.failed.emit(str(exc))


class HmmTool(QtWidgets.QWidget):
    """Generic hidden-Markov-model tool for binned traces."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(parent)
        self.model = view_model or HmmViewModel()
        self._embedded = bool(embedded)
        self._worker = None
        self.setWindowTitle("Hidden Markov model")
        self.setMinimumSize(760, 520)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        # A hairline strip for the ``?`` and **Guide** pair. The view spec has an
        # inline ``help`` section, which answers what a control *means* but never
        # which one to touch first — that is the tour, and it needs a button.
        from chisurf.gui.widgets.tools.help_guide import (
            attach_help_and_guide,
            promote_to_toolbar,
        )

        toolbar = QtWidgets.QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("QToolBar { border: none; padding: 0px; spacing: 2px; }")
        layout.addWidget(toolbar)
        self.auto_form = AutoForm(self.model)
        # The two things this tool does, on the strip rather than below the
        # State-scan panel. Add/Remove-style buttons stay in the form: they act
        # on one section and read as nonsense on a window-level bar.
        promote_to_toolbar(self.auto_form, toolbar, ("request_run", "request_scan"))
        attach_help_and_guide(self, toolbar, title="Hidden Markov model — help", model=self.model)
        layout.addWidget(self.auto_form)
        self.model.add_observer(self._on_model_event)

    def set_traces(self, traces, labels=None) -> None:
        """Analyse traces handed over by another tool instead of files."""
        self.model.set_traces(traces, labels)
        self._refresh()

    def _on_model_event(self, event: str) -> None:
        """Start a background job for a run request; ignore plain value changes."""
        if event == "start_run":
            self._start(self.model.run)
        elif event == "start_scan":
            self._start(self.model.run_scan)

    def _start(self, job) -> None:
        """Run ``job`` on a worker thread unless one is already busy."""
        if self._worker is not None and self._worker.isRunning():
            return
        self.setCursor(QtCore.Qt.BusyCursor)
        self._worker = _Worker(job, self)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(lambda message: logger.warning("HMM tool: %s", message))
        self._worker.start()

    def _on_finished(self) -> None:
        """Refresh the view once the worker is done."""
        self.unsetCursor()
        self._refresh()

    def _refresh(self) -> None:
        """Re-read every field and redraw the plots."""
        self.auto_form.sync_fields()
        self.auto_form.refresh_plots()
