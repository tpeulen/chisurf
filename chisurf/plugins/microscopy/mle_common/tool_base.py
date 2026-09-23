"""Shared Qt host widget for the AutoForm-hosted MLE-lifetime imaging tools."""

from __future__ import annotations

import logging
import typing

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm

logger = logging.getLogger(__name__)


class _RunSignals(QtCore.QObject):
    """Signal emitted when a background job finishes."""

    done = QtCore.Signal()


class _RunTask(QtCore.QRunnable):
    """Run a (slow) view-model job off the UI thread."""

    def __init__(self, job: typing.Callable[[], None], signals: _RunSignals):
        super().__init__()
        self._job = job
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        try:
            self._job()
        except Exception:
            logger.debug("MLE job failed", exc_info=True)
        self._signals.done.emit()


class AutoFormMleTool(QtWidgets.QWidget):
    """Base host widget: ``AutoForm(view_model)`` + a background run thread.

    Subclasses pass a view-model and a title. The heavy analysis runs off the UI
    thread; ``start_run`` on the model launches ``model.run`` and the display
    refreshes when it finishes. Subclasses that emit extra UI-thread events
    (e.g. ``start_preview``/``start_export``) override :meth:`handle_event`.
    """

    def __init__(
        self,
        view_model,
        title: str,
        parent=None,
        embedded: bool = False,
        *,
        min_size: tuple[int, int] = (640, 420),
    ):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)
        self._running = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        # ?/Guide for help.md + guide.json beside this module; a plain QWidget
        # cannot take the dock-tool mixin, so they go on a slim right-aligned row.
        from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

        help_row = QtWidgets.QHBoxLayout()
        help_row.addStretch(1)
        layout.addLayout(help_row)
        attach_help_and_guide(self, help_row, model=self.model)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)
        self.model.add_observer(self._on_model_event)

    # -- shared setup / context forwarders ------------------------------------
    def apply_setup_settings(self, payload: dict) -> None:
        """Forward a shared detector definition to the view-model."""
        self.model.apply_setup_settings(payload)
        self._refresh()

    def apply_pipeline_context(self, payload: dict) -> None:
        """Forward the pipeline source TTTR to the view-model."""
        self.model.apply_pipeline_context(payload)
        self._refresh()

    def apply_calibration(self, calibration: dict) -> None:
        """Forward per-detector IRF/BG calibration to the view-model."""
        self.model.apply_calibration(calibration)
        self._refresh()

    # -- event handling -------------------------------------------------------
    def handle_event(self, event: str) -> bool:
        """UI-thread hook for tool-specific events; return True when handled."""
        return False

    def _on_model_event(self, event: str) -> None:
        # ``start_run`` fires on the UI thread (button click) — launch the worker.
        # ``progress``/``done`` may fire on the worker thread; touching Qt there is
        # unsafe, so ignore them (the queued ``_RunSignals.done`` refreshes the UI).
        if event == "start_run":
            self._start_job(self.model.run)
            return
        # A structural change (e.g. the fit-model combo swapping the parameter
        # rows) needs a full form rebuild, not just a value sync. Defer it to the
        # next event-loop tick: the widget that fired the change (the combo) is
        # still mid-commit, and rebuild() would delete it out from under itself.
        if event == "rebuild":
            QtCore.QTimer.singleShot(0, self._rebuild)
            return
        if self.handle_event(event):
            return
        if QtCore.QThread.currentThread() is not self.thread():
            return
        self._refresh()

    def _rebuild(self) -> None:
        """Rebuild the whole AutoForm from the (now model-aware) view spec."""
        try:
            self.auto_form.rebuild()
        except Exception:
            logger.debug("MLE tool rebuild failed", exc_info=True)

    def _refresh(self) -> None:
        for fn in (self.auto_form.sync_fields, self.auto_form.refresh_plots):
            try:
                fn()
            except Exception:
                logger.debug("MLE tool refresh failed", exc_info=True)

    def _start_job(self, job: typing.Callable[[], None]) -> None:
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
