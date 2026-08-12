"""Dockable TTTR LUT Tools plugin window."""

from __future__ import annotations

import json
import pathlib

from qtpy import QtCore, QtWidgets

import chisurf as cs
from chisurf.gui.widgets.dock_area import DockArea

from .settings_panel import TTTRSettingsPanel
from .tac_lut_panel import TACLinearizationPanel
from chisurf.gui import dialogs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

_README = pathlib.Path(__file__).parents[1] / "README.md"

#: One-line explanation shown in the header so the flow is never a mystery.
_FLOW_TEXT = (
    "①  Load a flat-light file → ➡ Add all channels to setup (one LUT per routing "
    "channel).   ②  is optional: it only saves / loads a settings.tttr.json file."
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
        # The shared renderer, so this README reads like every other help page.
        from chisurf.gui.widgets.tools.help_render import show_in_browser

        show_in_browser(browser, text, _README)
        layout.addWidget(browser, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TTRLutToolsWidget(ChisurfDockTool):
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
        self.bridge_btn.setText("➡ Add all channels to setup")
        self.bridge_btn.setToolTip(
            "Compute a LUT for EVERY routing channel in the loaded file (one per "
            "channel — TAC non-linearity is per channel) and assign them all to your "
            "Detector setup. This is the normal way to use LUTs — applied when you "
            "close this window. Saving a .npy LUT / settings.tttr.json is optional."
        )
        self.bridge_btn.setStyleSheet("font-weight: bold;")
        self.bridge_btn.clicked.connect(self._bridge_compute_to_assign)
        header.addWidget(self.bridge_btn)
        help_btn = QtWidgets.QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip("What do the two tabs do? (help)")
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
            "MAKE a per-routing-channel LUT from a flat / uniform-illumination "
            "measurement, then ‘➡ Add to Detector setup’. This is the main tool."
        )
        self.settings_panel.setToolTip(
            "OPTIONAL: save/load a portable settings.tttr.json file, or assign LUT "
            "files to channels by hand. Not needed for the normal workflow."
        )
        self.dock_area.addTab(self.tac_panel, "① Compute LUT")
        self.dock_area.addTab(self.settings_panel, "② settings.tttr.json (optional)")

        self.statusBar().showMessage(
            "① Compute a LUT per routing channel, then ‘➡ Add to Detector setup’. "
            "Saving a file is optional."
        )
        self.dock_area.layoutChanged.connect(self.save_dock_layout_state)
        self.restore_dock_layout_state()

    def _show_help(self) -> None:
        """Open the modal help window (the README)."""
        _HelpDialog(self).exec_()

    def _bridge_compute_to_assign(self) -> None:
        """Compute a LUT for **every** routing channel and add all to the setup.

        Assigns each per-channel LUT to its routing channel in the (optional)
        settings panel, which the channel-definition editor pulls into the setup
        when this window closes. Saving a file is a separate, optional action.
        """
        model = self.tac_panel.model
        luts = model.compute_all_channels() if hasattr(model, "compute_all_channels") else {}
        if not luts:
            dialogs.information(
                self, "No LUTs yet",
                "Load a uniform-illumination file in ‘① Compute LUT’ first — a LUT is "
                "then computed for every routing channel it contains.",
            )
            return
        for ch, ntac in luts.items():
            self.settings_panel.receive_computed_lut(f"ch{ch}_lut", ntac, channel=int(ch))
        chans = ", ".join(str(c) for c in sorted(luts))
        self.statusBar().showMessage(
            f"Added LUTs for channel(s) {chans} to the Detector setup — "
            "close this window to apply."
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
