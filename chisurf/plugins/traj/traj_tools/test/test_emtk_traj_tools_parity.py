"""The native Traj Tools workspace against the Qt dock workspace: same tools in the same order, drops, state, layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts,
    draw_clip,
    layout_problems,
)
from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401

from ..app import TrajectoryToolsHubApp
from ..registry import TOOL_PANELS

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
DCD = REPO / "test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd"
BIG, SMALL = (1200, 800), (800, 600)
_KEEP: list = []


@pytest.fixture(scope="module")
def qt_tool(qapp, tmp_path_factory):
    """The Qt workspace, built once under a temporary HOME / settings folder (it writes its geometry on close)."""
    root = tmp_path_factory.mktemp("qt_home")
    patch = pytest.MonkeyPatch()
    for name, value in (
        ("HOME", root / "home"),
        ("CHISURF_SETTINGS_DIR", root / "s"),
        ("MMFDB_SETTINGS_DIR", root / "m"),
        ("MMFDB_DATABASE_PATH", root / "m.sqlite"),
    ):
        patch.setenv(name, str(value))
    (root / "home").mkdir()
    from ..gui.tool import TrajectoryToolsTool

    tool = TrajectoryToolsTool()
    _KEEP.append(
        tool
    )  # destroying the dock workspace while the process is alive bus-errors (Qt/pyqtgraph teardown)
    yield tool
    patch.undo()


def test_the_list_is_the_qt_tabs_in_the_same_order(qt_tool):
    assert list(qt_tool._tools) == [p["name"] for p in TOOL_PANELS]
    app = TrajectoryToolsHubApp()
    assert [e.id for e in app.entries] == list(
        qt_tool._tools
    ) and app.selected == qt_tool._active_tool == "Align"
    assert all(p["description"] and p["emtk"] for p in TOOL_PANELS)


def test_the_status_line_says_what_the_qt_status_bar_said(qt_tool):
    app = TrajectoryToolsHubApp()
    assert qt_tool.status_bar.currentMessage() == "Active tool: Align"
    for name in ("Convert", "FRET"):
        qt_tool._select_tool(name)
        app.select(name)
        assert qt_tool.status_bar.currentMessage() == app.status == f"Active tool: {name}"
    app.close()


def test_a_dropped_trajectory_fills_the_same_field_as_the_qt_drop(qt_tool):
    from pathlib import Path as P

    qt_tool._select_tool("Align")
    qt_tool.on_paths_dropped([P(DCD)])
    qt_path = qt_tool._tools["Align"].trajectory_filename
    app = TrajectoryToolsHubApp()
    app.select("Align")
    assert app.files_dropped([str(DCD)]) is True
    assert app.children["Align"].model.trajectory_filename == qt_path == str(DCD)
    assert app.status == f"Align: {DCD.name}"
    app.close()


def test_a_drop_nothing_takes_is_answered_on_the_status_line(tmp_path):
    app = TrajectoryToolsHubApp()
    app.select("Save Topol")
    junk = tmp_path / "notes.txt"
    junk.write_text("x")
    app.files_dropped([str(junk)])
    assert "takes no dropped file" in app.status and app.status.startswith("Save Topol")
    app.close()


def test_tools_are_built_lazily_keep_their_state_and_unknown_raises():
    app = TrajectoryToolsHubApp()
    assert app.children == {}
    app.select("Convert")
    convert = app.children["Convert"]
    convert.model.trajectory = "kept.dcd"
    app.select("Save Topol")
    assert app.select("Convert") is convert and convert.model.trajectory == "kept.dcd"
    with pytest.raises(ValueError):
        app.select("No Such Tool")
    app.close()
    assert app.children == {}


def test_a_failing_tool_is_reported_and_the_rest_works(monkeypatch):
    app = TrajectoryToolsHubApp()
    app.entries_by_name["Join"].emtk = "no.such.module:make_app"
    assert app.select("Join") is None and app.error.startswith("Tool unavailable")
    assert app.select("Align") is not None and not app.error
    app.close()


def test_state_round_trips_with_a_tool_not_yet_opened_and_ignores_bad_values():
    app = TrajectoryToolsHubApp()
    app.select("FRET")
    app.children["FRET"].model.forster_radius = 51.0
    state = json.loads(json.dumps(app.export_settings()))
    assert state["active_tool"] == "FRET"
    fresh = TrajectoryToolsHubApp()
    fresh.restore_settings(state)
    assert fresh.selected == "FRET" and fresh.children["FRET"].model.forster_radius == 51.0
    fresh.restore_settings({"active_tool": "ghost", "open_tools": {"ghost": {"a": 1}, "Align": 5}})
    fresh.restore_settings(None)
    assert fresh.selected == "FRET"
    app.close()
    fresh.close()


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_every_tool_draws_without_layout_problems(size):
    app = TrajectoryToolsHubApp()
    problems = {}
    for entry in app.entries:
        app.select(entry.id)
        painter = draw_clip(app, size)
        hub_only = [p for p in layout_problems(painter, size)]
        cut = clipped_texts(painter)
        if hub_only or cut:
            problems[entry.id] = (hub_only[:2], cut[:2])
    app.close()
    assert problems == {}, problems


def test_every_hub_control_has_a_tooltip_and_the_app_is_qt_free():
    from test.gui.emtk_port_parity import emtk_inventory, qt_free

    app = TrajectoryToolsHubApp()
    assert emtk_inventory(app, BIG)["controls_without_tooltip"] == []
    app.close()
    assert qt_free("traj_tools")
