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

from chisurf.gui.autoform.sections.path_list_section import PathListWidget
from chisurf.gui.widgets.tools import ChisurfDockTool


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
        # the file list is the shared, unified AutoForm file/folder list
        assert isinstance(tool.file_list, PathListWidget)
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_unified_list_updates_paths_and_preview_combo(tmp_path) -> None:
    """Adding via the unified list updates _file_paths and the preview combo."""
    from unittest.mock import MagicMock

    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = TTTRTimeWindowTool()
    tool._load_preview = MagicMock()  # skip real TTTR decode of dummy files
    try:
        f1 = tmp_path / "a.ptu"
        f1.write_bytes(b"x")
        f2 = tmp_path / "b.ht3"
        f2.write_bytes(b"x")
        tool.file_list.add_paths([f1, f2])
        assert len(tool._file_paths) == 2
        assert tool.cmb_file.count() == 2  # preview combo mirrors the list

        tool._clear_all()
        assert len(tool._file_paths) == 0
        assert tool.cmb_file.count() == 0
    finally:
        tool.close()


@_needs_qt
def test_supported_path_filter_accepts_tttr_and_rejects_others() -> None:
    """The extension predicate passed to PathListWidget as its path_filter."""
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import _is_supported_path

    assert _is_supported_path("/data/run.ptu") is True
    assert _is_supported_path("/data/run.ptu.gz") is True
    assert _is_supported_path("/data/run.txt") is False
