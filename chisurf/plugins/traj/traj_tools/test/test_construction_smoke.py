"""PRD-23 Task 3 / PRD-36: construction smoke test for the Traj Tools workspace.

Builds the real window offscreen to catch import / side-effect-on-init regressions
and asserts it reuses the shared ``ChisurfDockTool`` base (PRD-23 Task 1), including
the window-level path drag-drop the base provides.
"""

from __future__ import annotations

import os

import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

from chisurf.gui.widgets.tools import ChisurfDockTool

_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")
_needs_offscreen = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM", "") != "offscreen",
    reason="Set QT_QPA_PLATFORM=offscreen for headless test",
)

#: Keeps the QApplication alive; a locally-created one is garbage-collected
#: before the first widget is built, which aborts the interpreter.
_APP: list = []


def _ensure_app() -> None:
    """Create the offscreen QApplication once and keep a strong reference."""
    _APP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]


@_needs_qt
@_needs_offscreen
def test_tool_constructs_and_reuses_base() -> None:
    """The tool constructs offscreen and is a ``ChisurfDockTool``."""
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    _ensure_app()
    tool = TrajectoryToolsTool()
    try:
        assert isinstance(tool, ChisurfDockTool)
        assert tool.tool_settings_name == "TrajectoryToolsTool"
        # the base wires window-level path drag-drop for every dock tool
        assert tool.acceptDrops()
        # read-only construction: no MMFDB connection is opened on init
        assert tool.acquire_mmfdb_connection() is None
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_panels_are_unique_and_selectable() -> None:
    """Every panel appears once, and switching tabs tracks the active tool."""
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    _ensure_app()
    tool = TrajectoryToolsTool()
    try:
        labels = list(tool._tools)
        assert len(labels) == len(set(labels))
        # one panel per tool class: no tool is added twice under two labels
        classes = [type(widget) for widget in tool._tools.values()]
        assert len(classes) == len(set(classes))
        assert tool._active_tool == labels[0]

        tool._select_tool("Save Topol")
        assert tool._active_tool == "Save Topol"
        assert tool.dock_area.currentWidget() is tool._tools["Save Topol"]
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_dropped_path_reaches_the_active_panel(tmp_path) -> None:
    """A dropped path sets the active panel's trajectory; other panels report it."""
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    _ensure_app()
    trajectory = tmp_path / "traj.h5"
    trajectory.write_bytes(b"")

    tool = TrajectoryToolsTool()
    try:
        tool._select_tool("Align")
        tool.on_paths_dropped([trajectory])
        assert tool._tools["Align"].trajectory_filename == str(trajectory)

        # a panel without the shared property is told, not silently ignored
        tool._select_tool("Convert")
        tool.on_paths_dropped([trajectory])
        assert "takes no dropped file" in tool.status_bar.currentMessage()
    finally:
        tool.close()
