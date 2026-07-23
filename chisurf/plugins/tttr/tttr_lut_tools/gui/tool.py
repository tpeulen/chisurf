"""Dockable TTTR LUT Tools plugin window."""

from __future__ import annotations

import json
import pathlib

from qtpy import QtCore, QtWidgets

import chisurf as cs
from chisurf.gui.widgets.dock_area import DockArea

from .settings_panel import TTTRSettingsPanel
from .tac_lut_panel import TACLinearizationPanel

_README = pathlib.Path(__file__).parents[1] / "README.md"

#: One-line explanation shown in the header so the two stages are never a mystery.
_FLOW_TEXT = (
    "①  Compute a LUT from a uniform-illumination measurement   →   "
    "②  Assign it to channels & export   →   "
    "Configure LUTs… in the Detector setup applies it at read time"
)


class _HelpDialog(QtWidgets.QDialog):
    """Modal help window rendering the plugin README (Markdown)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TTTR LUT Tools — help")
        self.resize(640, 560)
        layout = QtWidgets.QVBoxLayout(self)
        browser = QtWidgets.QTextBrowser()
        browser.setOpenExternalLinks(True)
        try:
            text = _README.read_text(encoding="utf-8")
        except Exception:
            text = "Help unavailable."
        if hasattr(browser, "setMarkdown"):
            browser.setMarkdown(text)
        else:  # pragma: no cover - very old Qt
            browser.setPlainText(text)
        layout.addWidget(browser, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TTRLutToolsWidget(QtWidgets.QMainWindow):
    """Combined TTTR microtime LUT computation and settings workspace."""

    def __init__(self) -> None:
        """Create the combined LUT tools window."""
        super().__init__()

        self.setWindowTitle("TTTR LUT Tools")
        self.resize(1100, 700)

        # Header: a one-line flow explanation + the ①→② bridge + a ? help modal,
        # so users understand what the two tabs are and how a LUT reaches a setup.
        header = QtWidgets.QToolBar("LUT flow", self)
        header.setMovable(False)
        flow = QtWidgets.QLabel(_FLOW_TEXT)
        flow.setStyleSheet("color: #9ba3af; font-size: 11px; padding: 2px 6px;")
        header.addWidget(flow)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        header.addWidget(spacer)
        self.bridge_btn = QtWidgets.QToolButton()
        self.bridge_btn.setText("→ Use in ② Assign")
        self.bridge_btn.setToolTip(
            "Hand the LUT just computed in ① straight to ② Assign & Export — no "
            "need to Save then Load a file."
        )
        self.bridge_btn.clicked.connect(self._bridge_compute_to_assign)
        header.addWidget(self.bridge_btn)
        help_btn = QtWidgets.QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip("What is the difference between the two tabs? (help)")
        help_btn.clicked.connect(self._show_help)
        header.addWidget(help_btn)
        self.addToolBar(QtCore.Qt.TopToolBarArea, header)

        self.dock_area = DockArea(self)
        self.dock_area.setNewTabButtonVisible(False)
        self.dock_area.setTabsClosable(False)
        self.dock_area.setContextMenuEnabled(True)
        self.setCentralWidget(self.dock_area)

        self.tac_panel = TACLinearizationPanel()
        self.settings_panel = TTTRSettingsPanel()
        self.tac_panel.setToolTip(
            "Stage ①: MAKE a LUT from a flat / uniform-illumination measurement."
        )
        self.settings_panel.setToolTip(
            "Stage ②: ASSIGN computed LUTs to routing channels and export settings.tttr.json."
        )
        self.dock_area.addTab(self.tac_panel, "① Compute LUT")
        self.dock_area.addTab(self.settings_panel, "② Assign / Export")

        self.statusBar().showMessage(
            "① Compute a LUT from flat light, then ‘→ Use in ② Assign’ to assign it to channels."
        )
        self.dock_area.layoutChanged.connect(self.save_dock_layout_state)
        self.restore_dock_layout_state()

    def _show_help(self) -> None:
        """Open the modal help window (the README)."""
        _HelpDialog(self).exec_()

    def _bridge_compute_to_assign(self) -> None:
        """Hand the LUT computed in ① to ② Assign (the in-memory bridge)."""
        table = getattr(self.tac_panel, "current_table", None)
        if not table or table.get("NTAC_fract") is None:
            QtWidgets.QMessageBox.information(
                self, "No LUT yet",
                "Compute a LUT in ‘① Compute LUT’ first (load a uniform-illumination "
                "file and pick the linear region).",
            )
            return
        name = f"computed_{table.get('linear_start', 0)}_{table.get('linear_stop', 0)}"
        self.settings_panel.receive_computed_lut(name, table["NTAC_fract"])
        # Switch focus to the Assign tab.
        try:
            self.dock_area.setCurrentWidget(self.settings_panel)
        except Exception:
            pass
        self.statusBar().showMessage(
            f"LUT ‘{name}’ sent to ② Assign — select a channel and click Assign."
        )

    def _lut_tools_settings(self) -> QtCore.QSettings:
        """Return QSettings for the LUT tools dock layout."""
        settings_path = cs.core.settings.get_path("settings") / "tttr_lut_tools_dock_layout.ini"
        return QtCore.QSettings(str(settings_path), QtCore.QSettings.IniFormat)

    def _widget_key(self, widget: QtWidgets.QWidget) -> str:
        """Return a stable key for dock layout persistence."""
        if widget is self.tac_panel:
            return "compute_microtime_lut"
        if widget is self.settings_panel:
            return "create_lut_settings"
        return self.dock_area.tabText(self.dock_area.indexOf(widget))

    def get_dock_layout_state(self) -> dict[str, object]:
        """Return the current dock layout state."""
        return self.dock_area.get_layout_state(key_func=self._widget_key)

    def save_dock_layout_state(self) -> None:
        """Persist the current dock layout."""
        try:
            if self.dock_area.count() <= 0:
                return
            state = self.get_dock_layout_state()
            settings = self._lut_tools_settings()
            settings.setValue("dock_layout", json.dumps(state, sort_keys=True))
            settings.sync()
        except Exception as exc:
            cs.logging.warning(f"Failed to save TTTR LUT tools dock layout: {exc}")

    def restore_dock_layout_state(self) -> None:
        """Restore the saved dock layout."""
        try:
            settings = self._lut_tools_settings()
            value = settings.value("dock_layout")
            if isinstance(value, str):
                state = json.loads(value)
            elif isinstance(value, dict):
                state = value
            else:
                return
            self.dock_area.set_layout_state(
                state,
                key_func=self._widget_key,
                emit_change=False,
            )
        except Exception as exc:
            cs.logging.warning(f"Failed to restore TTTR LUT tools dock layout: {exc}")


class TTTRLUTSettingsPanel(QtWidgets.QWidget):
    """Embeddable TTTR LUT Tools panel for the unified settings dialog."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Create the panel with compute and assign tabs."""
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QtWidgets.QTabWidget(self)
        tabs.addTab(TACLinearizationPanel(), "Compute Microtime LUT")
        tabs.addTab(TTTRSettingsPanel(), "Create LUT Settings")
        layout.addWidget(tabs)


if __name__ == "plugin":
    window = TTRLutToolsWidget()
    window.show()
