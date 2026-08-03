"""PSF calculator: AutoForm controls beside a live 3-D volume view."""
from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

import chisurf.gui.chiplot as cp
from chisurf.gui.autoform.auto_form import AutoForm

from .core import PSFModel

logger = logging.getLogger(__name__)

class _Worker(QtCore.QRunnable):
    """Compute a volume off the GUI thread.

    The vectorial integral takes seconds at full quality; running it inline
    would freeze the window on every keystroke.
    """

    class _Signals(QtCore.QObject):
        done = QtCore.Signal(object)
        failed = QtCore.Signal(str)

    def __init__(self, model: PSFModel):
        super().__init__()
        self._model = model
        self.signals = self._Signals()

    def run(self):
        try:
            self.signals.done.emit(self._model.compute())
        except Exception as exc:                       # pragma: no cover - GUI path
            logger.warning("PSF computation failed", exc_info=True)
            self.signals.failed.emit(str(exc))


class PSFCalculator(QtWidgets.QWidget):
    """Compute a point-spread function and view it as a volume.

    Controls on the left, the 3-D view on the right. Editing a parameter
    schedules a recomputation rather than running one: the vectorial model is
    expensive, and a fresh calculation per keystroke would make the tool
    unusable at exactly the numerical aperture it exists for.
    """

    #: quiet period after the last edit before recomputing, milliseconds
    DEBOUNCE_MS = 250

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSF Calculator")

        self.model = PSFModel()
        self.auto_form = AutoForm(self.model)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        controls = QtWidgets.QScrollArea()
        controls.setWidgetResizable(True)
        controls.setWidget(self.auto_form)
        # AutoForm lays value fields two to a row, so a narrow pane clips the
        # right-hand column entirely -- the immersion index and the polarization
        # simply vanish.
        controls.setMinimumWidth(560)
        controls.setMaximumWidth(680)
        layout.addWidget(controls, 0)

        # The viewer is a sibling of the form, not a section inside it: put it
        # in the spec and AutoForm renders it at the bottom of the scrolling
        # column, which is not what "beside the controls" means.
        self.view = cp.VolumeView()
        self.view.setMinimumWidth(380)
        layout.addWidget(self.view, 1)

        self._pool = QtCore.QThreadPool.globalInstance()
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self.recompute)

        try:
            self.model.add_observer(self._on_model_event)
        except AttributeError:
            pass                                        # plain model: no signals

        self.recompute()

    # -- recomputation -------------------------------------------------------
    def schedule(self) -> None:
        """Ask for a recomputation once the user stops editing."""
        self._timer.start()

    def _on_model_event(self, event: str) -> None:
        try:
            self.auto_form.sync_fields()
        except Exception:
            logger.warning("PSF calculator: field sync failed", exc_info=True)
        self.schedule()

    def recompute(self) -> None:
        """Recompute in the background, unless the parameters are unchanged."""
        if not self.model.is_stale and self.model.volume is not None:
            return
        worker = _Worker(self.model)
        worker.signals.done.connect(self._show)
        worker.signals.failed.connect(self._report)
        self._pool.start(worker)

    def _show(self, volume) -> None:
        self.view.set_scale(1.0, 1.0, self.model.z_step_nm / self.model.pixel_size_nm)
        self.view.set_volume(volume, colormap=self.model.colormap,
                             threshold=self.model.threshold, gamma=self.model.gamma)
        try:
            self.auto_form.sync_fields()
        except Exception:
            pass

    def _report(self, message: str) -> None:
        logger.warning("PSF calculator: %s", message)


__all__ = ["PSFCalculator"]
