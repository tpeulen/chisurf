"""GUI entrypoint for the pixel-wise FLIM MLE tool (AutoForm + view.json).

``ImgPixelMleTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~...gui.view_model.PixelMleViewModel`.  The heavy analysis
(``view_model.run``) runs on a background thread so the UI never blocks, and the
fitted lifetime map refreshes when it finishes.

``apply_setup_settings(payload)`` forwards a shared detector definition (from the
Imaging Tools aggregator) to the view-model; ``embedded`` is accepted for API
uniformity.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm

from .view_model import PixelMleViewModel

logger = logging.getLogger(__name__)


class _RunSignals(QtCore.QObject):
    """Signal emitted when a background analysis run finishes."""

    done = QtCore.Signal()


class _RunTask(QtCore.QRunnable):
    """Run the (slow) pixel-wise analysis off the UI thread."""

    def __init__(self, model: PixelMleViewModel, signals: _RunSignals):
        super().__init__()
        self._model = model
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        try:
            self._model.run()
        except Exception:
            logger.debug("pixel-MLE run failed", exc_info=True)
        self._signals.done.emit()


class ImgPixelMleTool(QtWidgets.QWidget):
    """Pixel-wise MLE tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or PixelMleViewModel()
        self.setWindowTitle("Pixel-wise MLE")
        self.setMinimumSize(680, 460)
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
        """Forward the pipeline source TTTR to the view-model."""
        self.model.apply_pipeline_context(payload)
        self._refresh()

    def apply_calibration(self, calibration: dict) -> None:
        """Forward per-detector IRF/BG calibration to the view-model."""
        self.model.apply_calibration(calibration)
        self._refresh()

    def _on_model_event(self, event: str) -> None:
        # ``start_run`` fires on the UI thread (button click) — launch the worker.
        # ``progress``/``done`` may fire on the worker thread; touching Qt there is
        # unsafe, so ignore them (the queued ``_RunSignals.done`` refreshes the UI).
        if event == "start_run":
            self._start_run()
            return
        if QtCore.QThread.currentThread() is not self.thread():
            return
        self._refresh()

    def _refresh(self) -> None:
        for fn in (self.auto_form.sync_fields, self.auto_form.refresh_plots):
            try:
                fn()
            except Exception:
                logger.debug("pixel-MLE refresh failed", exc_info=True)

    def _start_run(self) -> None:
        if self._running:
            return
        self._running = True
        signals = _RunSignals()
        signals.done.connect(self._on_run_done)
        self._run_signals = signals  # keep a ref
        QtCore.QThreadPool.globalInstance().start(_RunTask(self.model, signals))

    def _on_run_done(self) -> None:
        self._running = False
        self._refresh()


__all__ = ["ImgPixelMleTool"]
