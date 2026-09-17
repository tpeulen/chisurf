"""PSF calculator: AutoForm controls beside a live 3-D volume view."""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

import chisurf.gui.chiplot as cp
from chisurf.gui.autoform.auto_form import AutoForm
from chisurf.gui.autoform.sections import register_section
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from ..core import PSFModel

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
        except Exception as exc:  # pragma: no cover - GUI path
            logger.warning("PSF computation failed", exc_info=True)
            self.signals.failed.emit(str(exc))


class PSFCalculator(ChisurfDockTool):
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

        # The house rule: long help behind a ? modal, and a guided tour beside
        # it. add_toolbar_help picks the Guide button up on its own once
        # gui/guide.json exists.
        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self._add_export_button(toolbar)
        self.add_toolbar_help(
            toolbar, resource="help.md", title="PSF calculator — Help", model=self
        )
        self.addToolBar(toolbar)

        # The spec is a dock_area, so the parameter panels and the 3-D view are
        # docks the user can re-arrange, float or tab -- the inputs and the plot
        # are separable rather than welded into one layout.
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.auto_form)
        self.setCentralWidget(central)

        self.view = self.auto_form.section_widget(key="psf_volume_view")
        if self.view is None:  # spec not applied
            self.view = cp.VolumeView()
            layout.addWidget(self.view)

        #: set while writing model values back into the widgets, so the
        #: valueChanged that provokes does not schedule another recompute
        self._syncing = False
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
        if self._syncing:
            return
        self._timer.start()

    def _wire_controls(self) -> None:
        """Recompute whenever a control commits a value.

        AutoForm writes straight through to the model and has no per-field
        signal, so the tool listens to the built widgets. This has to be redone
        after ``rebuilt``, which replaces them.
        """
        from chisurf.gui.autoform.sections.builtin import ChoiceWidget, ToggleWidget, ValueWidget

        for vw in self.auto_form.findChildren(ValueWidget):
            editor = getattr(vw, "editor", None)
            if editor is None:
                continue
            # Both, not whichever exists first: editingFinished fires only on
            # focus-out or Enter, so a spin-box arrow click would otherwise do
            # nothing until the user clicked somewhere else.
            for name in ("valueChanged", "editingFinished", "textChanged"):
                signal = getattr(editor, name, None)
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
        """Recompute in the background, or just redraw if only the look changed.

        The colormap, threshold and gamma do not enter the physics and so are
        not part of the cache key -- but returning early on them meant editing
        any of the three did nothing at all.
        """
        if not self.model.is_stale and self.model.volume is not None:
            self._show(self.model.volume)
            return
        worker = _Worker(self.model)
        worker.signals.done.connect(self._show)
        worker.signals.failed.connect(self._report)
        self._pool.start(worker)

    def _show(self, volume) -> None:
        self.view.set_scale(1.0, 1.0, self.model.z_step_nm / self.model.pixel_size_nm)
        self.view.set_volume(
            volume,
            colormap=self.model.colormap,
            threshold=self.model.threshold,
            gamma=self.model.gamma,
        )
        segments = self.model.polarization_segments() if self.model.show_polarization else None
        self.view.set_vectors(segments, color=(0.4, 1.0, 0.9, 0.9), width=2.0)

        # The summary is an info section, and only a field sync repaints it.
        # Guarding the sync is the fix; dropping it -- which is what stopped the
        # redraw feeding itself -- left the panel reading "Not computed yet."
        # under a fully rendered volume.
        self._syncing = True
        try:
            self.auto_form.sync_fields()
        finally:
            self._syncing = False

    # -- export ---------------------------------------------------------------
    def _add_export_button(self, toolbar) -> None:
        """A one-button menu offering the two formats the volume is useful in."""
        button = QtWidgets.QToolButton()
        button.setText("💾 Export")
        button.setObjectName("psf_export_button")
        button.setToolTip("Save the computed volume as a NumPy array or an ImageJ TIFF stack.")
        button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        menu = QtWidgets.QMenu(button)
        menu.setToolTipsVisible(True)
        for label, suffix, filt, tip in (
            (
                "NumPy array (.npy)",
                ".npy",
                "NumPy array (*.npy)",
                "Full float precision, no metadata.",
            ),
            (
                "ImageJ TIFF stack (.tif)",
                ".tif",
                "TIFF stack (*.tif *.tiff)",
                "32-bit stack carrying the voxel size, so ImageJ scales it correctly.",
            ),
        ):
            act = menu.addAction(label)
            act.setToolTip(tip)
            act.triggered.connect(lambda checked=False, s=suffix, f=filt: self.export_volume(s, f))
        button.setMenu(menu)
        # Name the action a widget-action would otherwise leave blank: the
        # guided tour finds a toolbar button by its action's text, so a step
        # pointing at "Export" resolves to nothing without this.
        toolbar.addWidget(button).setText("Export")
        self._export_button = button

    def export_volume(self, suffix: str = ".npy", file_filter: str = "") -> None:
        """Ask for a destination and write the current volume to it."""
        from chisurf.gui import dialogs
        from chisurf.gui.widgets.general import save_file

        if self.model.volume is None:
            dialogs.warning(
                "Nothing to export",
                "The PSF has not been computed yet -- wait for the view to fill in.",
            )
            return
        filename = save_file(
            description=f"Export PSF as {suffix}",
            file_type=file_filter or f"(*{suffix})",
        )
        if not filename:
            return
        path = pathlib.Path(filename)
        if not path.suffix:
            # A dialog filter is a hint, not a guarantee: a user who types a bare
            # name would otherwise get an extension-less file that neither
            # NumPy nor ImageJ opens by double-click.
            path = path.with_suffix(suffix)
        try:
            written = self.model.save(path)
        except Exception as exc:
            logger.warning("PSF export failed", exc_info=True)
            dialogs.error("Export failed", str(exc))
            return
        logger.info("PSF exported to %s", written)

    def _report(self, message: str) -> None:
        logger.warning("PSF calculator: %s", message)


__all__ = ["PSFCalculator"]
