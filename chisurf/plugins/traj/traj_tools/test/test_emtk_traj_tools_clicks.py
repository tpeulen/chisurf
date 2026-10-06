"""The native Traj Tools workspace operated with simulated pointer, wheel, key and drop events (both sizes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401
from chisurf.plugins.emtk_test_input import Driver, assert_tour_card_clear, tour_card_box

from ..app import TrajectoryToolsHubApp

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
HG = REPO / "test/data/atomic_coordinates/trajectory/hgbp1"
BIG, SMALL = (1200, 800), (800, 600)


@pytest.fixture
def drv():
    app = TrajectoryToolsHubApp()
    d = Driver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def test_a_click_on_each_entry_opens_that_tool_and_updates_the_status_line(drv):
    for entry in drv.app.entries:
        drv.click_name("entry:" + entry.id)
        assert drv.app.selected == entry.id and drv.app.child is not None and not drv.app.error
        shown = drv.draw(3).strings
        assert f"Active tool: {entry.id}" in shown and entry.description in shown


def test_a_tool_keeps_its_settings_while_another_is_used(drv):
    drv.click_name("entry:Convert")
    convert = drv.app.children["Convert"]
    convert.model.trajectory = "kept.dcd"
    drv.click_name("entry:Join")
    drv.click_name("entry:Convert")
    assert drv.app.children["Convert"] is convert and convert.model.trajectory == "kept.dcd"


def test_the_arrow_keys_step_through_the_list(drv):
    drv.app.pointer_move(40.0, 40.0)
    drv.app.key(keys.KEY_DOWN, "")
    drv.draw(2)
    assert drv.app.selected == "Convert"
    drv.app.key(keys.KEY_UP, "")
    drv.draw(2)
    assert drv.app.selected == "Align"


def test_pointer_and_typing_reach_the_open_tool_in_its_own_coordinates(drv):
    child = drv.app.child
    drv.draw(3)
    x, y, w, h = drv.app.child_box
    sx, sy, sw, sh = child.item_rects["stride"]  # the child's rectangle in its own coordinates
    drv.click((x + sx, y + sy, sw, sh), 0.3)
    assert child.io.want_capture_keyboard
    drv.app.key(0x41, "a", 0x04000000)
    drv.type("7")
    drv.enter()
    assert child.model.stride == 7


def test_a_trajectory_dropped_on_the_window_fills_the_open_tools_field(drv):
    assert drv.drop(str(HG / "hgbp1_transition.dcd")) is True
    assert drv.app.children["Align"].model.trajectory_filename == str(HG / "hgbp1_transition.dcd")
    assert "Align: hgbp1_transition.dcd" in drv.draw(2).strings


def test_a_drop_nothing_takes_says_so_on_the_status_line(drv, tmp_path):
    drv.click_name("entry:Save Topol")
    note = tmp_path / "n.txt"
    note.write_text("x")
    drv.drop(str(note))
    assert any("takes no dropped file" in s for s in drv.draw(2).strings)
    assert drv.drop() is False


def test_the_wheel_scrolls_the_list_in_a_short_window(drv):
    app = TrajectoryToolsHubApp()
    d = Driver(app, (600, 240))
    d.draw(3)
    x, y, w, h = d.rect("entry:Align")
    first = lambda: min(t[1] for t in d.draw(2).texts if t[5] == "Align" and t[0] < 200)  # noqa: E731
    before = first()
    d.wheel(x + w / 2, y + h / 2, steps=-3)
    assert first() <= before
    app.close()


def test_help_button_opens_the_help_window_whose_buttons_work(drv):
    drv.click_name("help")
    assert drv.app.help_window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not drv.app.help_window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.click_name("help")
    drv.escape()
    assert not drv.app.help_window.open


def test_the_help_text_names_the_tools_and_its_links_exist():
    text = (Path(__file__).parent.parent / "gui/help.md").read_text()
    for word in (
        "Align",
        "Convert",
        "Energy Calc",
        "FRET",
        "Join",
        "Remove Clashed",
        "Rot Translate",
        "Save Topol",
    ):
        assert word in text
    import re

    for link in re.findall(r"\]\((docs/[^)]+)\)", text):
        assert (REPO / link).exists(), link


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_the_tour_is_walked_with_the_user_operating_the_awaited_entry(size):
    app = TrajectoryToolsHubApp()
    d = Driver(app, size)
    d.draw(3)
    tour = app.tour
    d.click_name("guide")
    seen = []
    for _ in range(14):
        if not tour.active:
            break
        d.draw(3)
        assert_tour_card_clear(tour, size)
        if tour.awaiting:
            seen.append(tour.steps[tour.step_idx]["title"])
            d.click_name("entry:Align")
            assert not tour.awaiting
        tour.next()
    assert not tour.active and seen == ["Step 1 - superpose on frame 0"]
    app.close()


def test_the_tour_card_can_be_dragged_and_stays_off_its_target(drv):
    drv.click_name("guide")
    drv.draw(3)
    x, y, w, h = tour_card_box(drv.app.tour, BIG)
    drv.drag((x + 30, y + 10), (x + 60, y + 40))
    assert drv.app.tour.card_offset != (0.0, 0.0)
    assert_tour_card_clear(drv.app.tour, BIG)


def test_every_guide_target_is_a_drawn_control(drv):
    for step in drv.app.tour.steps:
        name = (step.get("target") or {}).get("name")
        if name:
            assert drv.app.item_rects.get(name), f"{step['title']}: {name}"


def test_the_whole_flow_works_in_the_small_window_too():
    app = TrajectoryToolsHubApp()
    d = Driver(app, SMALL)
    d.draw(3)
    for name in ("Convert", "FRET", "Align"):
        d.click_name("entry:" + name)
        assert app.selected == name
    assert d.drop(str(HG / "hgbp1_transition.dcd")) is True
    assert app.children["Align"].model.trajectory_filename.endswith("hgbp1_transition.dcd")
    app.close()
