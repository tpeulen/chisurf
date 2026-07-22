"""PRD-23 Task 3: construction smoke test for the TTTR Time-Window tool.

Builds the real widget offscreen to catch import / side-effect-on-init regressions
and asserts it reuses the shared ``ChisurfDockTool`` base (PRD-23 Task 1).
"""

from __future__ import annotations

import os

import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

from chisurf.gui.widgets.tools import ChisurfDockTool, PathDropListWidget


_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")
_needs_offscreen = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM", "") != "offscreen",
    reason="Set QT_QPA_PLATFORM=offscreen for headless test",
)


@_needs_qt
@_needs_offscreen
def test_tool_constructs_and_reuses_base() -> None:
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = TTTRTimeWindowTool()
    try:
        assert isinstance(tool, ChisurfDockTool)
        assert tool.acceptDrops() is True
        # the file list is the shared, extension-filtering drop widget
        assert isinstance(tool.file_list, PathDropListWidget)
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_drop_hook_routes_to_add_paths(monkeypatch) -> None:
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = TTTRTimeWindowTool()
    try:
        captured = []
        monkeypatch.setattr(tool, "_add_paths", lambda paths: captured.append(paths))
        tool.on_paths_dropped(["x.ptu"])
        assert captured == [["x.ptu"]]
    finally:
        tool.close()


@_needs_qt
def test_supported_path_filter_accepts_tttr_and_rejects_others() -> None:
    """The extension predicate now passed to PathDropListWidget."""
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import _is_supported_path

    assert _is_supported_path("/data/run.ptu") is True
    assert _is_supported_path("/data/run.ptu.gz") is True
    assert _is_supported_path("/data/run.txt") is False


@_needs_qt
@_needs_offscreen
def test_add_from_mmfdb_routes_picked_paths_to_add_paths(monkeypatch, tmp_path) -> None:
    """The 🗄 Database button commits picked paths through the same _add_paths."""
    from pathlib import Path

    from chisurf.gui.widgets.mmfdb import picker
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sample = tmp_path / "from_db.ptu"
    monkeypatch.setattr(picker, "inprocess_client", lambda: object())
    monkeypatch.setattr(picker, "pick_local_paths", lambda *a, **k: [sample])

    tool = TTTRTimeWindowTool()
    try:
        captured = []
        monkeypatch.setattr(tool, "_add_paths", lambda paths: captured.append(paths))
        tool._add_from_mmfdb()
        assert captured == [[Path(sample)]]
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_add_from_mmfdb_without_database_is_quiet(monkeypatch) -> None:
    """No database available -> nothing added, no crash, no blocking modal."""
    from chisurf.gui.widgets.mmfdb import picker
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(picker, "inprocess_client", lambda: None)
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "information", staticmethod(lambda *a, **k: None)
    )

    tool = TTTRTimeWindowTool()
    try:
        called = []
        monkeypatch.setattr(tool, "_add_paths", lambda paths: called.append(paths))
        tool._add_from_mmfdb()
        assert called == []
    finally:
        tool.close()
