"""PRD-23 Task 3 / PRD-36: construction smoke test for the BVA tool.

Builds the real window offscreen to catch import / side-effect-on-init regressions
and asserts it reuses the shared ``ChisurfDockTool`` base (PRD-23 Task 1). Also
pins the drop contract — BVA reads a *folder*, so a dropped file is reported
rather than written into the folder box — and the headless import boundary: the
plugin package resolves its Qt tool lazily, so ``api`` / ``core`` / ``backend`` /
``cli`` import without a Qt binding.
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
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    _ensure_app()
    tool = BVATool(embedded=True)
    try:
        assert isinstance(tool, ChisurfDockTool)
        assert tool.tool_settings_name == "BVATool"
        # the base wires window-level path drag-drop for every dock tool
        assert tool.acceptDrops()
        # the folder box only displays; the window owns the drop now
        assert not tool._folder_field.acceptDrops()
        # read-only construction: no MMFDB connection is opened on init
        assert tool.acquire_mmfdb_connection() is None
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_dropped_folder_is_loaded_and_a_dropped_file_is_reported(tmp_path) -> None:
    """A dropped directory selects it; a dropped file says so instead."""
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    _ensure_app()
    folder = tmp_path / "bursts"
    folder.mkdir()
    stray = tmp_path / "run.ptu"
    stray.write_bytes(b"")

    tool = BVATool(embedded=True)
    try:
        tool.on_paths_dropped([folder])
        assert tool.data_folder == folder
        assert tool.analysis_folder == folder
        assert tool._folder_field.text() == str(folder)
        assert not tool.Information.not_a_folder.is_shown

        # a dropped file is reported, and must not overwrite the folder box
        tool.on_paths_dropped([stray])
        assert tool.Information.not_a_folder.is_shown
        assert tool._folder_field.text() == str(folder)

        # a drop carrying no usable path says nothing new
        tool.Information.not_a_folder.clear()
        tool.on_paths_dropped([])
        assert not tool.Information.not_a_folder.is_shown
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_package_root_still_exposes_the_tool() -> None:
    """The lazy ``__getattr__`` keeps the historical package-root import working."""
    import chisurf.plugins.burst.burst_bva as plugin
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    assert plugin.BVATool is BVATool
    with pytest.raises(AttributeError):
        plugin.NoSuchTool


def test_package_root_imports_without_qt() -> None:
    """Importing the plugin root must not pull in the Qt tool.

    Run in a clean subprocess: the GUI tests above legitimately import
    ``gui.tool`` into this session, which would mask the boundary.
    """
    code = (
        "import sys\n"
        "import chisurf.plugins.burst.burst_bva as p\n"
        "assert p.name\n"
        "mods = [m for m in sys.modules if m.endswith('burst_bva.gui.tool')]\n"
        "assert not mods, mods\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
