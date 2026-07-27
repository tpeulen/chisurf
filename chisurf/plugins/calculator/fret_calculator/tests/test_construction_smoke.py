"""PRD-23 Task 3 / PRD-36: construction smoke test for the FRET Calculator.

Builds the real window offscreen to catch import / side-effect-on-init regressions
and asserts it reuses the shared ``ChisurfDockTool`` base (PRD-23 Task 1). Also
pins the headless import boundary: the plugin package resolves its Qt tool lazily,
so ``api`` / ``core`` / ``backend`` import without a Qt binding.
"""

from __future__ import annotations

import os
import subprocess
import sys

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
    from chisurf.plugins.calculator.fret_calculator.gui.tool import FretCalculatorTool

    _ensure_app()
    tool = FretCalculatorTool()
    try:
        assert isinstance(tool, ChisurfDockTool)
        assert tool.tool_settings_name == "FretCalculatorTool"
        # the base wires window-level path drag-drop for every dock tool
        assert tool.acceptDrops()
        # read-only construction: no MMFDB connection is opened on init
        assert tool.acquire_mmfdb_connection() is None
        # both calculator tabs are present
        assert tool.tabs.count() == 2
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_dropped_path_is_reported_not_swallowed(tmp_path) -> None:
    """A dropped path raises a standing message instead of doing nothing."""
    from chisurf.plugins.calculator.fret_calculator.gui.tool import FretCalculatorTool

    _ensure_app()
    dropped = tmp_path / "run.ptu"
    dropped.write_bytes(b"")

    tool = FretCalculatorTool()
    try:
        assert not tool.Information.no_file_input.is_shown
        tool.on_paths_dropped([dropped])
        assert tool.Information.no_file_input.is_shown
        # a drop carrying no usable path says nothing
        tool.Information.no_file_input.clear()
        tool.on_paths_dropped([])
        assert not tool.Information.no_file_input.is_shown
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_package_root_still_exposes_the_tool() -> None:
    """The lazy ``__getattr__`` keeps the historical package-root import working."""
    import chisurf.plugins.calculator.fret_calculator as plugin
    from chisurf.plugins.calculator.fret_calculator.gui.tool import FretCalculatorTool

    assert plugin.FretCalculatorTool is FretCalculatorTool
    with pytest.raises(AttributeError):
        plugin.NoSuchTool


def test_package_root_imports_without_qt() -> None:
    """Importing the plugin root must not pull in the Qt tool.

    Run in a clean subprocess: the GUI tests above legitimately import
    ``gui.tool`` into this session, which would mask the boundary.
    """
    code = (
        "import sys\n"
        "import chisurf.plugins.calculator.fret_calculator as p\n"
        "assert p.name\n"
        "mods = [m for m in sys.modules if m.endswith('fret_calculator.gui.tool')]\n"
        "assert not mods, mods\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
