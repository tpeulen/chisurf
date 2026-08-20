"""Model manager: which fitting models the model drop-down offers.

Built from ``models.view.json`` by AutoForm over
:class:`~.view_model.ModelManagerViewModel`; the registry reading lives in the
Qt-free ``api`` package.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.model_manager.gui.view_model import ModelManagerViewModel

#: Legacy AST-discovery name.
name = "Setup:Models"


class ModelManagerWidget(ChisurfDockTool):
    """Browse the registered fitting models and choose which are offered."""

    tool_settings_name = "ModelManagerWidget"
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None, view_model=None, **kwargs: Any):
        super().__init__(parent)
        self.setWindowTitle("Model Manager")
        self.model = view_model or ModelManagerViewModel()

        toolbar = QtWidgets.QToolBar()
        toolbar.setObjectName("model_manager_toolbar")
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self._add_actions(toolbar)
        self.add_toolbar_guide(toolbar, resource="guide.json")
        self.add_toolbar_help(toolbar, resource="help.md", title="Models — help")
        self.addToolBar(toolbar)

        self.auto_form = AutoForm(self.model)
        self.setCentralWidget(self.auto_form)

        self.modelEvent.connect(self._on_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()

    def _add_actions(self, toolbar: QtWidgets.QToolBar) -> None:
        """Build the toolbar; every action carries a tooltip."""
        def add(label: str, tooltip: str, slot) -> None:
            action = toolbar.addAction(label)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)

        add(f"{Glyphs.SAVE} Save",
            "Write the disabled-model list to your settings file.",
            self._save)
        add(f"{Glyphs.RESET} Revert",
            "Discard every change made since the last save.",
            self._revert)
        toolbar.addSeparator()
        add(f"{Glyphs.REFRESH} Rescan",
            "Read the experiment registry again.",
            self._rescan)
        add(f"{Glyphs.CLEAR} Drop stale",
            "Remove disabled entries that match no registered model.",
            self._drop_stale)

    def _on_model_event(self, _event: str) -> None:
        self.auto_form.refresh_plots()
        self.auto_form.sync_fields()

    def _save(self) -> None:
        self.model.save()

    def _revert(self) -> None:
        if not self.model.dirty:
            self.model.set_status("Nothing to revert.")
            return
        if dialogs.confirm(
            self, "Discard changes",
            "Discard every model setting changed since the last save?",
        ):
            self.model.revert()

    def _rescan(self) -> None:
        self.model.reload()
        self.model.set_status("Model registry re-read.")

    def _drop_stale(self) -> None:
        stale = self.model.stale_entries()
        if not stale:
            self.model.set_status("No stale entries: every disabled name matches a model.")
            return
        if dialogs.confirm(
            self, "Drop stale entries",
            "These disabled entries match no registered model and do nothing:\n  "
            + "\n  ".join(stale) + "\n\nRemove them?",
        ):
            self.model.drop_stale()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        """Warn before dropping unsaved changes."""
        if self.model.dirty and not dialogs.confirm(
            self, "Unsaved changes",
            "The model settings have changed but have not been saved.\n\nClose anyway?",
        ):
            event.ignore()
            return
        self.save_window_geometry()
        super().closeEvent(event)


#: Backwards-compatible alias.
ModelManagerTool = ModelManagerWidget
