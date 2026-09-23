"""Dockable combined trajectory tools workspace."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qtpy import QtGui, QtWidgets

from chisurf.gui.widgets.dock_area import DockArea
from chisurf.gui.widgets.tools import ChisurfDockTool
from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer
from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget
from chisurf.plugins.traj.traj_align.widget import AlignTrajectoryWidget
from chisurf.plugins.traj.traj_convert.widget import MDConverter
from chisurf.plugins.traj.traj_join.widget import JoinTrajectoriesWidget
from chisurf.plugins.traj.traj_remove_clashes.widget import RemoveClashedFrames
from chisurf.plugins.traj.traj_rotate_translate.widget import RotateTranslateTrajectoryWidget
from chisurf.plugins.traj.traj_save_topology.widget import SaveTopology

ToolFactory = Callable[[], QtWidgets.QWidget]


class TrajectoryToolsTool(ChisurfDockTool):
    """Combined dockable workspace for trajectory tools."""

    tool_settings_name = "TrajectoryToolsTool"

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        """Create the combined trajectory tools window."""
        super().__init__(parent)
        self.setWindowTitle("Traj Tools")
        self.setMinimumSize(800, 480)
        self.resize(850, 520)
        self._tools: dict[str, QtWidgets.QWidget] = {}
        self._active_tool = ""
        self._init_ui()
        self._add_tools()
        self._select_tool(next(iter(self._tools), ""))
        self.restore_window_geometry()

    def _init_ui(self) -> None:
        """Build the main window layout."""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        self.ensure_help_toolbar(title="Trajectory tools — help")
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.dock_area = DockArea(central)
        self.dock_area.setNewTabButtonVisible(False)
        self.dock_area.setTabsClosable(True)
        self.dock_area.currentChanged.connect(self._on_current_tab_changed)
        layout.addWidget(self.dock_area, 1)

        self.status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _add_tools(self) -> None:
        """Create and add all trajectory tool panels."""
        for label, factory in self._tool_factories():
            widget = factory()
            widget.setObjectName(f"trajectory_tool_{label.lower().replace(' ', '_')}")
            widget.show()
            self._tools[label] = widget
            self.dock_area.addTab(widget, label)

    def _tool_factories(self) -> list[tuple[str, ToolFactory]]:
        """Return the trajectory tools in display order."""
        return [
            ("Align", AlignTrajectoryWidget),
            ("Convert", MDConverter),
            ("Energy Calc", PotentialEnergyWidget),
            ("FRET", Structure2Transfer),
            ("Join", JoinTrajectoriesWidget),
            ("Remove Clashed", RemoveClashedFrames),
            ("Rot Translate", RotateTranslateTrajectoryWidget),
            ("Save Topol", SaveTopology),
        ]

    def _select_tool(self, tool_name: str) -> None:
        """Activate one trajectory tool panel."""
        widget = self._tools.get(tool_name)
        if widget is None:
            return
        self._active_tool = tool_name
        self.dock_area.setCurrentWidget(widget)
        self.status_bar.showMessage(f"Active tool: {tool_name}")

    def _on_current_tab_changed(self, index: int) -> None:
        """Track the tab the user switched to so drops reach the visible panel."""
        widget = self.dock_area.currentWidget()
        for label, tool in self._tools.items():
            if tool is widget:
                self._active_tool = label
                self.status_bar.showMessage(f"Active tool: {label}")
                return

    # -- drag & drop -----------------------------------------------------------

    def on_paths_dropped(self, paths: list[Path]) -> None:
        """Load the first dropped path into the active panel.

        The trajectory panels share a ``trajectory_filename`` property; a path
        dropped anywhere on the window is routed to the panel currently in front.
        Panels without that property (converter, FRET, join) keep their own
        per-field drop targets, so the drop is reported rather than swallowed.
        """
        widget = self._tools.get(self._active_tool)
        if widget is None or not paths:
            return
        if not hasattr(type(widget), "trajectory_filename"):
            self.status_bar.showMessage(
                f"{self._active_tool} takes no dropped file — drop onto one of its fields"
            )
            return
        widget.trajectory_filename = str(paths[0])
        self.status_bar.showMessage(f"{self._active_tool}: {paths[0].name}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Persist the window geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)
