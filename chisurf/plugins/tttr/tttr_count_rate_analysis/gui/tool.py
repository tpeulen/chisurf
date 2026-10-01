"""New-style GUI entrypoint for the Count Rate Analysis tool.

:class:`CountRateAnalyzer` is a thin :class:`~qtpy.QtWidgets.QWidget` hosting
the EMTK app in :mod:`.app` (:class:`CountRateApp`) over the Qt-free
:class:`~..view_model.CountRateViewModel`. The channel definition comes from a
saved detector setup in the canonical store, injected into the model as its
``channels_provider`` — the same contract the old DetectorWizardPage page
fulfilled.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from . import sections  # noqa: F401  (side effect: register the custom sections)
from .view_model import CountRateViewModel

logger = logging.getLogger(__name__)


class CountRateAnalyzer(QtWidgets.QWidget):
    """Count rates per detector channel across many TTTR files (mean/std + plot)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Count Rate Analysis")
        self.setMinimumSize(700, 500)

        self._model = CountRateViewModel()
        self.selected_setup: str = ""

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, CountRateApp

        self.app = CountRateApp(
            self,
            on_calculate=self._calculate,
            on_save=self._save,
            on_add_files=self._add_files,
            on_clear=self._clear,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

        # The channel definition the model computes with: the selected saved
        # detector setup, converted — the contract the DetectorWizardPage had.
        self._model.channels_provider = self.channels

    # ── the channel source ───────────────────────────────────────────

    def available_setups(self) -> dict:
        """The saved detector setups, from the canonical store."""
        try:
            from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
                load_detector_setups,
            )

            info = load_detector_setups()
            return dict(info.get("setups", {})) if isinstance(info, dict) else {}
        except Exception:
            logger.debug("count-rate: could not read the setup store", exc_info=True)
            return {}

    def channels(self) -> dict:
        """The channel definition of the selected setup, for the model."""
        from .app import setup_to_channels

        setups = self.available_setups()
        setup = setups.get(self.selected_setup)
        return setup_to_channels(setup) if setup else {}

    # ── actions ──────────────────────────────────────────────────────

    def _calculate(self) -> None:
        from chisurf.gui import dialogs

        reason = self._model.can_compute()
        if reason is not None:
            dialogs.warning(self, "Cannot calculate", reason)
            return
        try:
            self._model.compute()
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Error", str(exc))
        self.host.update()

    def _save(self) -> None:
        from chisurf.gui import dialogs

        reason = self._model.can_save()
        if reason is not None:
            dialogs.warning(self, "No data", reason)
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Table as Text File", "", "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            self._model.save_table(path)
            dialogs.information(self, "Success", f"Table saved to {path}")
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Error", f"Failed to save file: {exc}")

    def _add_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select TTTR files")
        if paths:
            self._model.add_files(list(paths))
        self.host.update()

    def _clear(self) -> None:
        self._model.clear()
        self.host.update()

    # ── the AutoForm-era surface ─────────────────────────────────────

    @property
    def auto_form(self):
        """A shim whose refresh repaints the canvas."""
        return self

    def refresh_plots(self) -> None:
        if hasattr(self, "host"):
            self.host.update()

    def sync_fields(self) -> None:
        if hasattr(self, "host"):
            self.host.update()

    @property
    def model(self):
        return self._model


__all__ = ["CountRateAnalyzer"]
