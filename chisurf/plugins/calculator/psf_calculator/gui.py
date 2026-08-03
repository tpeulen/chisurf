"""PSF calculator: AutoForm controls beside a live 3-D volume view."""
from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

import chisurf.gui.chiplot as cp
from chisurf.gui.autoform.auto_form import AutoForm
from chisurf.gui.autoform.sections import register_section

from .core import PSFModel

logger = logging.getLogger(__name__)

@register_section("psf_volume_view")
def _psf_volume_view(model=None, target=None, **options):
    """The 3-D view, as a dock of its own beside the parameters.

    ``_autoform_expanding`` is AutoForm's hook for a widget that should take
    the space in its dock rather than sit at its size hint with a stretch
    pushed underneath it -- which for a viewport means a strip at the top of an
    otherwise empty panel.
    """
    view = cp.VolumeView()
    view._autoform_expanding = True
    return view


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

        # The spec is a dock_area, so the parameter panels and the 3-D view are
        # docks the user can re-arrange, float or tab -- the inputs and the plot
        # are separable rather than welded into one layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.auto_form)

        self.view = self.auto_form.section_widget(key="psf_volume_view")
        if self.view is None:                      # spec not applied
            self.view = cp.VolumeView()
            layout.addWidget(self.view)

        self._pool = QtCore.QThreadPool.globalInstance()
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self.recompute)

        self._wire_controls()
        self.auto_form.rebuilt.connect(self._wire_controls)

        self.recompute()

    # -- recomputation -------------------------------------------------------
    def schedule(self, *_args) -> None:
        """Ask for a recomputation once the user stops editing."""
        self._timer.start()

    def _wire_controls(self) -> None:
        """Recompute whenever a control commits a value.

        AutoForm writes straight through to the model and has no per-field
        signal, so the tool listens to the built widgets. This has to be redone
        after ``rebuilt``, which replaces them.
        """
        from chisurf.gui.autoform.sections.builtin import (
            ChoiceWidget, ToggleWidget, ValueWidget)

        for vw in self.auto_form.findChildren(ValueWidget):
            editor = getattr(vw, "editor", None)
            if editor is None:
                continue
            signal = (getattr(editor, "editingFinished", None)
                      or getattr(editor, "valueChanged", None))
            if signal is not None:
                signal.connect(self.schedule)

        for cw in self.auto_form.findChildren(ChoiceWidget):
            if cw.combo is not None:
                cw.combo.currentIndexChanged.connect(self.schedule)
            for rb in getattr(cw, "_radios", []):
                rb.toggled.connect(self.schedule)

        for tw in self.auto_form.findChildren(ToggleWidget):
            checkbox = getattr(tw, "checkbox", None)
            if checkbox is not None:
                checkbox.toggled.connect(self.schedule)

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
        self.auto_form.sync_fields()

    def _report(self, message: str) -> None:
        logger.warning("PSF calculator: %s", message)


__all__ = ["PSFCalculator"]
