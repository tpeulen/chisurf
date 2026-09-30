"""Dockable 2D-FLCS GUI backed by the plugin RPC API."""

from __future__ import annotations

import json
import logging
import pathlib

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.core.fio.staging import TTTR_FILE_FILTER
from chisurf.gui import dialogs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

from .client import FlcClient
from .model import _FlcModel

_GUI_DIR = pathlib.Path(__file__).parent
logger = logging.getLogger(__name__)


# The tool used to carry a ``FlcHelpDialog`` — an HTML literal plus the CLI
# ``--help`` output. It is gone: the shared ``?`` modal renders ``gui/help.md``,
# so the help is prose in a file rather than a string in a widget, its links are
# live, and it sits beside the ``guide.json`` that answers the other question.
# See :mod:`chisurf.gui.widgets.tools.help_guide`.


class FlcTwoDTool(ChisurfDockTool):
    """Modern 2D-FLCS tool with dockable AutoForm panels."""

    tool_settings_name = "FlcTwoDTool"

    def __init__(self, parent=None) -> None:
        """Initialize the 2D-FLCS GUI."""
        super().__init__(parent)
        self.setWindowTitle("2D-FLCS")
        self.resize(1040, 660)
        # The photon stream, IRF and results live on the Qt-free model (``gui/model.py``);
        # the ``_tttr`` ... ``_client`` attributes below are views of it.
        self._model = _FlcModel()
        self._model.client = FlcClient()
        self._model.on_status = self._show_status
        self.dock_area = None
        self._build_toolbar()
        self._build_central()

    def _build_toolbar(self) -> None:
        """Build the compact top toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("flcTwoDMainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        act_open = QtWidgets.QAction("Open", self)
        act_open.setToolTip("Open TTTR photon stream file.")
        act_open.triggered.connect(self._on_open)
        toolbar.addAction(act_open)

        act_irf = QtWidgets.QAction("IRF", self)
        act_irf.setToolTip("Load an instrument-response TTTR file.")
        act_irf.triggered.connect(self._on_open_irf)
        toolbar.addAction(act_irf)

        act_sim = QtWidgets.QAction("Sim", self)
        act_sim.setToolTip("Generate a synthetic two-state exchange photon stream.")
        act_sim.triggered.connect(self._on_simulate)
        toolbar.addAction(act_sim)

        toolbar.addSeparator()
        self.act_run = QtWidgets.QAction("Run", self)
        self.act_run.setToolTip("Build 2D-FDC and resolve lifetimes.")
        self.act_run.triggered.connect(self._on_run)
        self.act_run.setEnabled(False)
        toolbar.addAction(self.act_run)

        spacer = QtWidgets.QWidget(self)
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(spacer)
        # Adjacent stretches share the slack rather than adding to it, so the
        # helper must not add a second one and strand the pair mid-bar.
        toolbar.setProperty("_chisurf_right_spacer", True)

        # The shared **Guide** / ``?`` pair, replacing this tool's own modal. The
        # tour walks on the simulator below, so it needs no data of the user's.
        attach_help_and_guide(self, toolbar, title="2D-FLCS — help", model=self._model)

    def _build_central(self) -> None:
        """Build the declarative docked AutoForm UI."""
        from chisurf.gui.autoform import AutoForm

        self._form = AutoForm(self._model, parent=self)
        self.setCentralWidget(self._form)
        self._settings_form = self._form
        self._plots_form = self._form
        self._configure_dock_area()
        self._restore_window_geometry()
        self.statusBar().showMessage("Open a TTTR file to begin.")

    def _configure_dock_area(self) -> None:
        """Enable dock visibility context menus and layout persistence."""
        areas = getattr(self._form, "_dock_areas", [])
        self.dock_area = areas[0] if areas else None
        if self.dock_area is None:
            return
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        self.dock_area.setTabsClosable(True)
        self.dock_area.layoutChanged.connect(self._save_dock_layout)
        self._restore_dock_layout()

    def _refresh_results(self) -> None:
        """Refresh all result docks."""
        self._form.refresh_plots()

    def _settings(self) -> QtCore.QSettings:
        """Return persistent settings for the plugin shell."""
        return QtCore.QSettings("chisurf", self.tool_settings_name)

    def _save_window_geometry(self) -> None:
        """Persist the main window geometry."""
        try:
            settings = self._settings()
            settings.setValue("geometry", self.saveGeometry())
            settings.sync()
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Failed to save window geometry: {exc}")

    def _restore_window_geometry(self) -> None:
        """Restore the main window geometry."""
        try:
            geometry = self._settings().value("geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Failed to restore window geometry: {exc}")

    def _save_dock_layout(self) -> None:
        """Persist the dock layout."""
        if self.dock_area is None:
            return
        try:
            settings = self._settings()
            settings.setValue(
                "dock_layout", json.dumps(self.dock_area.get_layout_state(), sort_keys=True)
            )
            settings.sync()
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Failed to save dock layout: {exc}")

    def _restore_dock_layout(self) -> None:
        """Restore the saved dock layout."""
        if self.dock_area is None:
            return
        try:
            value = self._settings().value("dock_layout")
            if isinstance(value, str):
                layout_state = json.loads(value)
            elif isinstance(value, dict):
                layout_state = value
            else:
                return
            self.dock_area.set_layout_state(layout_state, emit_change=False)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Failed to restore dock layout: {exc}")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Save state before closing."""
        self._save_window_geometry()
        self._save_dock_layout()
        super().closeEvent(event)

    # The model owns these; the window reads and writes them through here.
    _client = property(
        lambda self: self._model.get_client(), lambda self, v: setattr(self._model, "client", v)
    )
    _tttr = property(lambda self: self._model.tttr, lambda self, v: setattr(self._model, "tttr", v))
    _tttr_path = property(
        lambda self: self._model.tttr_path, lambda self, v: setattr(self._model, "tttr_path", v)
    )
    _irf = property(lambda self: self._model.irf, lambda self, v: setattr(self._model, "irf", v))
    _irf_time_ns = property(
        lambda self: self._model.irf_time_ns, lambda self, v: setattr(self._model, "irf_time_ns", v)
    )
    _irf_file = property(
        lambda self: self._model.irf_file, lambda self, v: setattr(self._model, "irf_file", v)
    )
    _irf_file_time_ns = property(
        lambda self: self._model.irf_file_time_ns,
        lambda self, v: setattr(self._model, "irf_file_time_ns", v),
    )
    _irf_path = property(
        lambda self: self._model.irf_path, lambda self, v: setattr(self._model, "irf_path", v)
    )
    _spectrum2d = property(
        lambda self: self._model.spectrum2d, lambda self, v: setattr(self._model, "spectrum2d", v)
    )
    _kinetics = property(
        lambda self: self._model.kinetics, lambda self, v: setattr(self._model, "kinetics", v)
    )

    def _show_status(self, text: str) -> None:
        """Show a model status line in the status bar (and let the window repaint)."""
        self.statusBar().showMessage(text)
        QtWidgets.QApplication.processEvents()

    def _on_open(self) -> None:
        """Open a TTTR file through the RPC client."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open TTTR file",
            "",
            TTTR_FILE_FILTER,
        )
        if not path:
            return
        try:
            self._model.open_tttr(path)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Load failed", str(exc))
            return
        self._settings_form.sync_fields()
        self.act_run.setEnabled(True)

    def _on_open_irf(self) -> None:
        """Open an IRF TTTR file through the RPC client."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open IRF (TTTR) file",
            "",
            TTTR_FILE_FILTER,
        )
        if not path:
            return
        try:
            self._model.open_irf(path)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Load failed", str(exc))
            return
        self._settings_form.sync_fields()

    def set_irf(self, irf: np.ndarray, irf_time_ns: np.ndarray) -> None:
        """Set the IRF directly for tests and scripts."""
        self._model.set_irf(irf, irf_time_ns)

    def _on_simulate(self) -> None:
        """Generate a synthetic photon stream and load it as the active dataset."""
        try:
            self._model.simulate()
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Simulation failed", str(exc))
            return
        self._settings_form.sync_fields()
        self.act_run.setEnabled(True)

    def _on_run(self) -> None:
        """Run the current 2D-FLCS analysis."""
        if self._model.tttr is None:
            return
        self._model.run()
        self._refresh_results()
