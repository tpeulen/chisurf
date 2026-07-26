"""PRD-23 Task 3 / PRD-36: construction smoke test for the FPS JSON Editor tool.

Builds the real window offscreen to catch import / side-effect-on-init regressions
and asserts it reuses the shared ``ChisurfDockTool`` base (PRD-23 Task 1), including
the window-level path drag-drop the base provides.
"""

from __future__ import annotations

import json
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
    from chisurf.plugins.modelling.fps_json_editor.gui.tool import FpsJsonEditorTool

    _ensure_app()
    tool = FpsJsonEditorTool()
    try:
        assert isinstance(tool, ChisurfDockTool)
        assert tool.tool_settings_name == "FpsJsonEditorTool"
        # the base wires window-level path drag-drop for every dock tool
        assert tool.acceptDrops()
        # read-only construction: no MMFDB connection is opened on init
        assert tool.acquire_mmfdb_connection() is None
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_dropped_json_is_loaded_into_the_editor(tmp_path) -> None:
    """A dropped ``.fps.json`` path is loaded; non-JSON paths are ignored."""
    from chisurf.plugins.modelling.fps_json_editor.gui.tool import FpsJsonEditorTool

    _ensure_app()
    payload = {
        "Positions": {"A1": {"chain_identifier": "A", "residue_seq_number": 1}},
        "Distances": {},
    }
    json_path = tmp_path / "labels.fps.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    other_path = tmp_path / "structure.pdb"
    other_path.write_text("ATOM\n", encoding="utf-8")

    tool = FpsJsonEditorTool()
    try:
        tool.on_paths_dropped([other_path])
        assert tool.editor.fps_json_payload.get("Positions", {}) == {}

        tool.on_paths_dropped([other_path, json_path])
        assert "A1" in tool.editor.fps_json_payload["Positions"]
    finally:
        tool.close()
