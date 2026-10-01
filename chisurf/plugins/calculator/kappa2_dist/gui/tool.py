"""K² Distribution Calculator widget.

The UI is the EMTK app in :mod:`.app` (:class:`Kappa2App`), backed by
``Kappa2DistClient`` (which dispatches to core via in-process RPC).
Backward-compat attributes are maintained for
``kappa2_helpers.open_experimental_k2_dialog``.
"""

from __future__ import annotations

import pathlib
import typing

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.core.dataspec import load_view_spec
from chisurf.core.fluorescence.anisotropy.kappa2 import s2delta
from chisurf.gui import dialogs

from .client import Kappa2DistClient

_GUI_DIR = pathlib.Path(__file__).parent


try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:

    def persist_plugin_state(n):
        return lambda c: c


from .model import _Kappa2DistModel


class _ModelTypeRadio:
    """Stands in for one of the old Qt radio buttons.

    ``kappa2_helpers.open_experimental_k2_dialog`` probes ``isChecked()`` and
    ``setChecked()`` on the model-choice radios; the EMTK combo carries the
    same state, so these read and write it.
    """

    def __init__(self, widget: Kappa2Dist, option: str) -> None:
        self._widget = widget
        self._option = option

    def isChecked(self) -> bool:
        return self._widget._model.model_type == self._option

    def setChecked(self, on: bool) -> None:
        if on:
            self._widget._model.model_type = self._option
            self._widget.onUpdateHist()


class _ButtonStub:
    """Stands in for one of the old Compute/Save push buttons.

    ``isEnabled()`` / ``setEnabled()`` and ``click()`` — enough for a caller
    that pokes or disables the buttons by handle. ``click()`` runs the slot.
    """

    def __init__(self, slot, enabled_property: bool = True) -> None:
        self._slot = slot
        self._enabled = enabled_property

    def isEnabled(self) -> bool:
        return self._enabled

    def setEnabled(self, on: bool) -> None:
        self._enabled = bool(on)

    def click(self) -> None:
        if self._enabled:
            self._slot()


@persist_plugin_state("kappa2_dist")
class Kappa2Dist(QtWidgets.QWidget):
    """K² orientation-factor distribution calculator.

    The EMTK app (:class:`~.app.Kappa2App`) is the UI, backed by a
    client-server architecture.

    Backward-compat attributes (``radioButton_2``, ``radioButton``,
    ``k2scale``, ``k2hist``, ``k2_mean``, ``onUpdateHist``) are
    maintained for ``kappa2_helpers.open_experimental_k2_dialog``.
    """

    name = "Kappa2Dist"

    def __init__(
        self,
        kappa2: float = 0.667,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.kappa2 = kappa2
        self._client = Kappa2DistClient()
        self._model = _Kappa2DistModel()
        self._model.kappa2_true = kappa2

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, Kappa2App

        self.app = Kappa2App(
            self,
            on_compute=self._do_compute,
            on_edit=self._schedule_compute,
            on_save=self._on_save,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])

        from qtpy import QtWidgets as _QtWidgets

        layout = _QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

        # Backward-compat: the model-choice radios the old AutoForm built.
        self.radioButton_2 = _ModelTypeRadio(self, "cone")
        self.radioButton = _ModelTypeRadio(self, "diffusion")
        self.radioButton_iso = _ModelTypeRadio(self, "isotropic")
        # The old Compute/Save buttons: same handles, the EMTK app's buttons
        # do the work, these forward to the same slots for external pokes.
        self.pushButton = _ButtonStub(self._do_compute)
        self.saveButton = _ButtonStub(self._on_save, enabled_property=False)

        self._compute_timer = QtCore.QTimer(self)
        self._compute_timer.setSingleShot(True)
        self._compute_timer.timeout.connect(self._do_compute)
        self._do_compute()

    # ── the AutoForm-era surface, for callers that still poke it ─────

    def _schedule_compute(self) -> None:
        """Debounce edits, as the old 50 ms timer did."""
        self._compute_timer.start(50)

    @property
    def _form(self):
        """A shim whose sync/refresh repaint the canvas."""
        return self

    @property
    def auto_form(self):
        """The AutoForm object the old widget exposed (a repaint shim now)."""
        return self

    def sync_fields(self) -> None:
        if hasattr(self, "host"):
            self.host.update()

    def refresh_plots(self) -> None:
        if hasattr(self, "host"):
            self.host.update()

    # ── compute ──────────────────────────────────────────────────────

    def _do_compute(self) -> None:
        self._model.compute(self._client)
        if hasattr(self, "host"):
            self.host.update()

    def onUpdateHist(self) -> None:
        """Backward-compat: called by ``open_experimental_k2_dialog``."""
        self._do_compute()

    # ── backward-compat properties ───────────────────────────────────

    @property
    def k2scale(self) -> np.ndarray | None:
        return self._model._k2scale

    @property
    def k2hist(self) -> np.ndarray | None:
        return self._model._k2hist

    @property
    def k2_mean(self) -> float:
        return self._model.k2_mean

    @k2_mean.setter
    def k2_mean(self, v: float) -> None:
        self._model.k2_mean = v

    # ── save ─────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Kappa2 Distribution",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        k2scale = self._model._k2scale
        k2hist = self._model._k2hist
        if k2scale is None or k2hist is None:
            dialogs.warning(self, "Save", "Nothing to save.")
            return

        bins = k2scale[1:]
        header = [
            "# Kappa2 Distribution",
            f"# Model: {self._model.model_type}",
            f"# SD2: {self._model.SD2:.6f}",
            f"# SA2: {self._model.SA2:.6f}",
            f"# Mean kappa2: {self._model.k2_mean:.6f}",
            f"# SD kappa2: {self._model.k2_sd:.6f}",
            f"# Assumed kappa2: {self._model.kappa2_true:.6f}",
            f"# Mean Rapp: {self._model.Rapp_mean:.6f}",
            f"# SD Rapp: {self._model.RappSD:.6f}",
            "#",
            "# kappa2,probability",
        ]
        try:
            with open(file_path, "w") as f:
                f.write("\n".join(header) + "\n")
                for x, y in zip(bins, k2hist):
                    f.write(f"{x:.6f},{y:.6f}\n")
            dialogs.information(self, "Save Successful", f"Saved to:\n{file_path}")
        except Exception as exc:
            dialogs.error(self, "Save Error", f"An error occurred:\n{exc}")


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    win = Kappa2Dist()
    win.show()
    app.exec_()
