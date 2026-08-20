"""Plugin manager: what is installed, how it is wired, and what to switch off.

The panel is built from ``plugins.view.json`` by AutoForm; everything it shows
and every edit it makes lives in :class:`~.view_model.PluginManagerViewModel`,
and the file operations live in the Qt-free ``api`` package. What is left here
is a toolbar and the handful of things that genuinely need a widget: file
dialogs, confirmations, and the icon panel.

This replaced a 1856-line widget in which roughly 60 % of the code was an AI
icon-generation client. That is now :mod:`..api.icons`, called through the
shared background-task helper rather than blocking the GUI thread for up to five
minutes.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

#: Legacy AST-discovery name. Kept because the menu path is asserted by
#: ``test/plugins/test_plugin_menu_metadata.py`` against the manifest.
name = "Setup:Plugins"


class PluginManagerWidget(ChisurfDockTool):
    """Browse, configure, install and remove plugins."""

    tool_settings_name = "PluginManagerWidget"
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None, view_model=None, **kwargs: Any):
        super().__init__(parent)
        self.setWindowTitle("Plugin Manager")
        self.model = view_model or PluginManagerViewModel()

        toolbar = QtWidgets.QToolBar()
        toolbar.setObjectName("plugin_manager_toolbar")
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self._add_actions(toolbar)
        self.add_toolbar_guide(toolbar, resource="guide.json")
        self.add_toolbar_help(toolbar, resource="help.md", title="Plugins — help")
        self.addToolBar(toolbar)

        self.auto_form = AutoForm(self.model)
        self.setCentralWidget(self.auto_form)

        # Model events arrive on whatever thread changed the model; the signal
        # hop puts the refresh back on the GUI thread.
        self.modelEvent.connect(self._on_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()

    # -- toolbar ---------------------------------------------------------

    def _add_actions(self, toolbar: QtWidgets.QToolBar) -> None:
        """Build the toolbar.

        Every action carries a tooltip, which is also what the guided tour
        matches its steps against.
        """
        def add(label: str, tooltip: str, slot) -> None:
            action = toolbar.addAction(label)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)

        add(f"{Glyphs.SAVE} Save",
            "Write the plugin settings. Menu changes take effect after a restart.",
            self._save)
        add(f"{Glyphs.RESET} Revert",
            "Discard every change made since the last save.",
            self._revert)
        toolbar.addSeparator()
        add(f"{Glyphs.REFRESH} Rescan",
            "Walk the plugin folders again and rebuild the list.",
            self._rescan)
        toolbar.addSeparator()
        add(f"{Glyphs.IMPORT} Install…",
            "Install a plugin from a folder or a .zip archive into your personal "
            "plugin directory.",
            self._install)
        add(f"{Glyphs.DELETE} Uninstall",
            "Delete the selected plugin. Only plugins you installed yourself can "
            "be removed; built-in ones are switched off instead.",
            self._uninstall)
        toolbar.addSeparator()
        add(f"{Glyphs.UP} Move up",
            "Move the selected plugin earlier in the menus.",
            lambda: self.model.move_selected(-1))
        add(f"{Glyphs.DOWN} Move down",
            "Move the selected plugin later in the menus.",
            lambda: self.model.move_selected(+1))
        toolbar.addSeparator()
        add(f"{Glyphs.EDIT} Rename…",
            "Change the name this plugin shows in the menus. Edits the plugin's "
            "manifest, which is the field the menus actually read.",
            self._rename)
        add(f"{Glyphs.PALETTE} Icon…",
            "Choose, generate or clear the icon shown beside this plugin.",
            self._edit_icon)
        add(f"{Glyphs.FOLDER} Open folder",
            "Open the selected plugin's directory in the file browser.",
            self._open_folder)

    # -- model events ----------------------------------------------------

    def _on_model_event(self, event: str) -> None:
        """Re-read the model into the form."""
        if event == "reloaded":
            self.auto_form.refresh_plots()
            self.auto_form.sync_fields()
        else:
            self.auto_form.refresh_plots()
            self.auto_form.sync_fields()

    # -- actions ---------------------------------------------------------

    def _save(self) -> None:
        self.model.save()

    def _revert(self) -> None:
        if not self.model.dirty:
            self.model.set_status("Nothing to revert.")
            return
        if dialogs.confirm(
            self, "Discard changes",
            "Discard every plugin setting changed since the last save?",
        ):
            self.model.revert()

    def _rescan(self) -> None:
        self.model.reload(rescan=True)
        self.model.set_status("Plugin folders rescanned.")

    def _selected_or_warn(self):
        """The selected row, or ``None`` after telling the user to pick one."""
        row = self.model.selected
        if row is None:
            dialogs.information(self, "No plugin selected", "Select a plugin first.")
        return row

    def _install(self) -> None:
        """Install from a folder or a zip, validating before anything is copied."""
        from chisurf.plugins.core.plugin_manager.api import install as installer

        source, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose a plugin archive", "", "Plugin archive (*.zip);;All files (*)"
        )
        if not source:
            source = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Choose a plugin folder"
            )
        if not source:
            return

        plan = installer.inspect_source(source)
        if not plan.ok:
            dialogs.error(self, "Cannot install", "\n".join(plan.problems))
            return

        message = f"Install {plan.plugin_name!r} into {plan.destination.parent}?"
        if plan.overwrites:
            message += "\n\nThis replaces the plugin already installed there."
        if plan.warnings:
            message += "\n\n" + "\n".join(plan.warnings)
        if not dialogs.confirm(self, "Install plugin", message):
            return

        try:
            destination = installer.install(plan)
        except Exception as exc:
            dialogs.error(self, "Install failed", str(exc))
            return
        self.model.reload(rescan=True)
        self.model.set_status(f"Installed {plan.plugin_name!r} into {destination}.")

    def _uninstall(self) -> None:
        """Delete a user-installed plugin, refusing to orphan its dependants."""
        from chisurf.plugins.core.plugin_manager.api import install as installer

        row = self._selected_or_warn()
        if row is None:
            return

        dependants = row.blocking_dependants(self.model.settings.disabled)
        message = f"Permanently delete {row.name!r} from\n{row.package_dir}?"
        if dependants:
            message += (
                "\n\nThese plugins require it and will stop working:\n  "
                + "\n  ".join(dependants)
            )
        if not dialogs.confirm(self, "Uninstall plugin", message):
            return

        try:
            installer.uninstall(row.package_dir)
        except ValueError as exc:
            dialogs.warning(self, "Cannot uninstall", str(exc))
            return
        except Exception as exc:
            dialogs.error(self, "Uninstall failed", str(exc))
            return
        self.model.reload(rescan=True)
        self.model.set_status(f"Removed {row.name!r}.")

    def _rename(self) -> None:
        """Rename the selected plugin's menu entry."""
        row = self._selected_or_warn()
        if row is None:
            return
        new_name, accepted = QtWidgets.QInputDialog.getText(
            self, "Rename plugin", "Menu name:", QtWidgets.QLineEdit.Normal, row.name
        )
        if not accepted:
            return
        problem = self.model.rename_selected(new_name)
        if problem:
            dialogs.warning(self, "Cannot rename", problem)

    def _open_folder(self) -> None:
        row = self._selected_or_warn()
        if row is None:
            return
        from qtpy.QtCore import QUrl
        from qtpy.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(row.package_dir)))

    def _edit_icon(self) -> None:
        """Open the icon panel for the selected plugin."""
        row = self._selected_or_warn()
        if row is None:
            return
        from chisurf.plugins.core.plugin_manager.gui.icon_dialog import IconDialog

        dialog = IconDialog(row, parent=self)
        if dialog.exec_():
            self.model.reload(rescan=True)
            self.model.set_status(f"Icon updated for {row.name!r}.")

    # -- window ----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        """Warn before dropping unsaved settings.

        The old manager discarded every checkbox change silently on close.
        """
        if self.model.dirty and not dialogs.confirm(
            self, "Unsaved changes",
            "The plugin settings have changed but have not been saved.\n\nClose anyway?",
        ):
            event.ignore()
            return
        self.save_window_geometry()
        super().closeEvent(event)


#: Backwards-compatible alias -- the manifest entrypoint and three embedders
#: (`setup`, `boarding`, the ribbon) name this class.
PluginManagerTool = PluginManagerWidget
