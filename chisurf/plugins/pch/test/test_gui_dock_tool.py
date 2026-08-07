"""PRD-23 Task 3 / PRD-36: the PCH tool is on the shared dockable-tool base.

Builds the real window offscreen to catch import / side-effect-on-init
regressions, asserts it reuses ``ChisurfDockTool``, and pins the two things the
base buys this tool: a window-level drop that goes through the *same* load path
as the toolbar action, and a read-only construction that opens no MMFDB
connection. Also pins the headless import boundary — the plugin package resolves
its Qt tool lazily, so ``api`` / ``backend`` / ``cli`` import without Qt.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from chisurf.gui.widgets.tools import ChisurfDockTool


def test_gui_tool_is_a_dock_tool(qapp):
    """The tool constructs offscreen and is a ``ChisurfDockTool``."""
    from chisurf.plugins.pch.gui.tool import PCHApp

    widget = PCHApp()
    try:
        assert isinstance(widget, ChisurfDockTool)
        assert widget.tool_settings_name == "PCHApp"
        # the base wires window-level path drag-drop for every dock tool
        assert widget.acceptDrops()
        # read-only construction: no MMFDB connection is opened on init
        assert widget.acquire_mmfdb_connection() is None
    finally:
        widget.close()


def test_gui_dropped_tttr_file_is_loaded(qapp, tmp_path):
    """A dropped photon-stream file takes the toolbar action's load path.

    What gets loaded is what the drop *guard* returns, not what was dropped:
    this drop zone opts into ``tttr_to_pto``, so a vendor file becomes the
    measurement's container on the way in. An empty file cannot be converted,
    so the guard leaves it alone and the two coincide here -- asserted against
    the guard's answer rather than the dropped path, because pinning the
    dropped path would make this test fail the moment the conversion works.
    """
    from chisurf.gui.widgets.dropguard import apply_drop_guards
    from chisurf.plugins.pch.gui.tool import PCHApp

    dropped = tmp_path / "run.ptu"
    dropped.write_bytes(b"")
    expected = apply_drop_guards(None, [str(dropped)], ["tttr_to_pto"])

    widget = PCHApp()
    try:
        loaded: list[str] = []
        widget._client.load_tttr = lambda path: loaded.append(path) or {"n_photons": 7}
        widget.on_paths_dropped([dropped])
        assert loaded == expected
        assert widget._filename == expected[0]
        assert widget.action_compute.isEnabled()
        assert not widget.Information.unsupported_drop.is_shown
    finally:
        widget.close()


def test_gui_dropped_other_file_is_reported_not_swallowed(qapp, tmp_path):
    """A drop this tool cannot use says so instead of doing nothing."""
    from chisurf.plugins.pch.gui.tool import PCHApp

    dropped = tmp_path / "notes.txt"
    dropped.write_bytes(b"")

    widget = PCHApp()
    try:
        called: list[str] = []
        widget._client.load_tttr = lambda path: called.append(path)
        widget.on_paths_dropped([dropped])
        assert called == []
        assert widget._filename == ""
        assert widget.Information.unsupported_drop.is_shown
        # a drop carrying no path at all says nothing
        widget.Information.unsupported_drop.clear()
        widget.on_paths_dropped([])
        assert not widget.Information.unsupported_drop.is_shown
    finally:
        widget.close()


def test_gui_dropped_file_that_fails_to_load_keeps_the_tool_disarmed(qapp, tmp_path):
    """A failed drop reports the failure and leaves nothing half-loaded."""
    from chisurf.plugins.pch.gui.tool import PCHApp

    dropped = tmp_path / "broken.ht3"
    dropped.write_bytes(b"")

    def boom(path):
        raise OSError("not a TTTR file")

    widget = PCHApp()
    try:
        widget._client.load_tttr = boom
        widget.on_paths_dropped([dropped])
        assert widget.Error.load_failed.is_shown
        assert widget._filename == ""
        assert not widget.action_compute.isEnabled()
    finally:
        widget.close()


def test_gui_package_root_still_exposes_the_tool(qapp):
    """The lazy ``__getattr__`` keeps the historical package-root import working."""
    import chisurf.plugins.pch as plugin
    from chisurf.plugins.pch.gui.tool import PCHApp

    assert plugin.PCHApp is PCHApp
    with pytest.raises(AttributeError):
        plugin.NoSuchTool


def test_gui_package_root_imports_without_qt():
    """Importing the plugin root must not pull in the Qt tool.

    Run in a clean subprocess: the tests above legitimately import ``gui.tool``
    into this session, which would mask the boundary.
    """
    code = (
        "import sys\n"
        "import chisurf.plugins.pch as p\n"
        "assert p.name\n"
        "mods = [m for m in sys.modules if m.endswith('pch.gui.tool')]\n"
        "assert not mods, mods\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(pathlib.Path(__file__).resolve().parents[4]),
    )
    assert result.returncode == 0, result.stderr
