"""Every control of the native Imaging Tools hub operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the
text a list entry or a button drew) and host file drops reach the window; the assertions read the visible outcome (the
selection, the header, the embedded tool's event log, the status line). The embedded tools are recording fakes (the real
native children are drawn in the parity tests). The control -> test list is in
``okf/plugins/emtk-ports/imaging_tools/REPORT.md``.
"""

from __future__ import annotations

import pytest
from emtk import keys

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

from .test_emtk_imaging_tools_parity import BIG, ROLES, SMALL, Child, Client, fake_hub, hermetic  # noqa: F401  (hermetic is autouse)

from chisurf.plugins.microscopy.imaging_tools.gui.app import PANELS, ImagingToolsApp

LABELS = {row[0]: row[2] for row in PANELS}


class HubDriver(Driver):
    """The imaging driver reading rectangles from the hub's one registry (``item_rects``)."""

    def rect(self, name):
        self.draw(1)
        found = self.app.item_rects.get(name)
        assert found, f"{name!r} was not drawn: {sorted(self.app.item_rects)}"
        return tuple(found)


@pytest.fixture
def drv():
    app = fake_hub()
    d = HubDriver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def click_entry(drv, role):
    drv.click(drv.rect("entry:" + role))
    drv.draw(2)


def test_the_list_shows_every_tool_the_browser_is_selected_and_the_separator_is_drawn(drv):
    shown = drv.draw(2).strings
    for role in ROLES:
        assert LABELS[role] in shown, role
    assert drv.app.selected == "browser" and drv.app.child is not None


def test_a_click_on_a_list_entry_selects_it_builds_its_tool_and_the_header_follows(drv):
    app = drv.app
    click_entry(drv, "pixel_nb")
    assert app.selected == "pixel_nb" and "pixel_nb" in app.children
    assert any(s.startswith("Per-pixel Number (N)") for s in drv.draw(2).strings)
    click_entry(drv, "setup")
    assert app.selected == "setup" and "Define detector channels" in " ".join(drv.draw(2).strings)
    count = len(app.children)
    click_entry(drv, "pixel_nb")
    assert len(app.children) == count and app.child is app.children["pixel_nb"]  # kept, not rebuilt


def test_the_search_field_keeps_the_tools_matching_name_or_description_and_a_miss_says_so(drv):
    click_entry(drv, "pixel_nb")
    drv.type_into("search", "phasor", enter=False)
    shown = drv.draw(2).strings
    assert "5. Phasor-FLIM" in shown and "4. IRF & BG" in shown  # the second names the phasor in its description
    assert "Browser" not in shown and "Setup" not in shown
    drv.select_all()
    drv.type_text("fractional")  # in a description only
    assert "No tool matches the search." in drv.draw(2).strings
    drv.select_all()
    drv.type_text("detector")
    shown = drv.draw(2).strings
    assert "Setup" in shown and "Browser" not in shown
    drv.select_all()
    drv.key(keys.KEY_BACKSPACE)
    assert "Browser" in drv.draw(2).strings and drv.app.search == ""


def test_back_and_next_buttons_walk_the_list_and_are_greyed_at_its_ends(drv):
    app = drv.app
    roles = [r for r in ROLES]
    assert app.selected == "browser"
    drv.click("next")
    assert app.selected == "drift"
    drv.click("next")
    drv.click("next")
    assert app.selected == "flow"  # the list order, the Qt shell's (the pipeline order skips Flow)
    drv.click("previous")
    assert app.selected == "frc"
    click_entry(drv, "setup")
    drv.click("previous")
    assert app.selected == "setup"  # greyed at the top
    click_entry(drv, "clsm_generator")
    drv.click("next")
    assert app.selected == "clsm_generator"  # greyed at the bottom
    click_entry(drv, "pixel_mle")
    drv.click("next")
    assert app.selected == "clsm_draw" and roles.index("clsm_draw") == roles.index("pixel_mle") + 1


def test_fast_forward_walks_the_numbered_steps_each_after_the_previous_has_finished_and_stops_at_the_rule(drv):
    app = drv.app
    visited = []
    real = app.goto_role
    app.goto_role = lambda role: visited.append(role) or real(role)
    click_entry(drv, "pixel_intensity")
    visited.clear()
    drv.click("fast_forward")
    for _ in range(14):
        drv.draw(2)
    assert visited == ["pixel_nb", "pixel_micro_time", "calibration", "pixel_phasor", "pixel_mle"]
    assert app.selected == "pixel_mle" and app._ff_queue == [] and "Fast-forward finished" in drv.draw(2).strings


def test_fast_forward_waits_for_a_running_step_and_a_second_press_stops_it(drv):
    app = drv.app
    click_entry(drv, "pixel_intensity")
    app.child.job = type("J", (), {"busy": True})()  # the open step is computing
    drv.click("fast_forward")
    for _ in range(4):
        drv.draw(2)
    assert app.selected == "pixel_intensity" and app._ff_queue  # waiting
    assert "Stop" in drv.draw(2).strings
    drv.click("fast_forward")
    assert app._ff_queue == [] and "Fast-forward stopped" in " ".join(drv.draw(2).strings)
    app.child.job.busy = False
    for _ in range(3):
        drv.draw(2)
    assert app.selected == "pixel_intensity"


def test_fast_forward_is_greyed_outside_the_numbered_pipeline_and_on_its_last_step(drv):
    app = drv.app
    for role in ("clsm_draw", "spot_finder", "psf", "pixel_mle"):
        click_entry(drv, role)
        drv.click("fast_forward")
        assert app._ff_queue == [], role
    app.goto_role("setup")
    app.toggle_fast_forward()
    assert app._ff_queue[-1] == "pixel_mle" and "clsm_draw" not in app._ff_queue  # from the top: every step to the rule
    app.toggle_fast_forward()
    assert app._ff_queue == []


def test_a_tool_marked_pending_says_so_in_the_list_and_when_clicked():
    app = ImagingToolsApp(client=Client(), factories={"browser": Child})
    d = HubDriver(app, BIG)
    d.draw(3)
    assert "5. Phasor-FLIM - pending" in d.draw(2).strings
    d.click(d.rect("entry:pixel_phasor"))
    d.draw(2)
    assert "Native migration pending for this tool." in " ".join(d.draw(2).strings) and app.selected == "pixel_phasor"
    app.close()


def test_the_embedded_tool_gets_pointer_events_in_its_own_coordinates_inside_its_box(drv):
    app = drv.app
    bx, by, bw, bh = app.child_box
    child = app.child
    drv.click_at(bx + 120, by + 90)
    assert ("press", 120, 90, 1) in child.events and ("release", 120, 90, 1) in child.events
    before = len(child.events)
    drv.click_at(bx - 60, by + 90)  # on the list: the tool must not see the press
    assert not [e for e in child.events[before:] if e[0] == "press"]


def test_the_wheel_over_the_tool_reaches_it_and_over_the_list_does_not(drv):
    app = drv.app
    bx, by, bw, bh = app.child_box
    drv.wheel(bx + 200, by + 200, 3)
    assert ("wheel", 200, 200, 3) in app.child.events
    n = len(app.child.events)
    drv.wheel(bx - 100, 400, 3)
    assert not [e for e in app.child.events[n:] if e[0] == "wheel"]


def test_keys_go_to_the_open_tool_and_a_file_dropped_on_the_window_goes_to_it(drv, tmp_path):
    drv.key(0x41, "a")
    assert ("key", 0x41, "a") in drv.app.child.events
    path = tmp_path / "x.ptu"
    path.write_bytes(b"x")
    assert drv.drop(str(path)) is True
    assert drv.app.child.dropped == [[str(path)]]


def test_a_tool_without_a_drop_handler_ignores_a_dropped_file(tmp_path):
    class Plain(Child):
        on_files_dropped = None

    app = ImagingToolsApp(client=Client(), factories={"browser": Plain})
    d = HubDriver(app, BIG)
    d.draw(3)
    d.drop(str(tmp_path / "y.ptu"))
    assert app.files_dropped([str(tmp_path / "y.ptu")]) is False and app.child.dropped == []
    app.close()


def test_the_source_and_hdf5_lines_follow_the_shared_context(drv):
    app = drv.app
    assert "Source: -" in " ".join(drv.draw(2).strings)
    app.set_pipeline(source="/data/run1.ptu", hdf5="/data/run1.imaging.h5")
    shown = " ".join(drv.draw(3).strings)
    assert "Source: run1.ptu" in shown and "HDF5: run1.imaging.h5" in shown
    drv.hover(*drv.rect("source")[:2], frames=2)


def test_help_button_opens_the_help_window_whose_buttons_work(drv):
    window = drv.app.help
    drv.click_text("Help")
    assert window.open and {"Start Guided Tour", "Close", "Close Help"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.draw(2)
    for closer in ("Close Help", "Close"):
        drv.click_text("Help")
        drv.click_text(closer, last=closer == "Close Help")
        assert not window.open, closer
    drv.click_text("Help")
    drv.escape()
    assert not window.open


def test_the_tour_is_walked_with_the_user_operating_each_awaited_control(drv):
    tour = drv.app.tour
    drv.click_text("Guide")
    seen = []
    for _ in range(30):
        if not tour.active:
            break
        drv.draw(2)
        step = tour.steps[tour.step_idx]
        target = step.get("target") or {}
        if tour.awaiting:
            seen.append(step["title"])
            key = target.get("name")
            if key.startswith("entry:"):
                click_entry(drv, key.split(":")[1])
            elif key == "next":
                drv.click("next")
            assert not tour.awaiting, f"{step['title']}: operating {key} did not release the step"
        tour.next()
    assert not tour.active and len(seen) == 3


def test_every_guide_target_is_a_drawn_control_and_the_card_does_not_cover_it(drv):
    from chisurf.emtk.help_guide import place_tour_card

    for step in drv.app.tour.steps:
        key = (step.get("target") or {}).get("name")
        if not key:
            continue
        rect = drv.app.item_rects.get(key)
        assert rect and rect[2] > 0, f"{step['title']}: {key} is not drawn"
        card_w, card_h = min(480.0, BIG[0] - 40.0), 150.0
        x, y = place_tour_card(rect, float(BIG[0]), float(BIG[1]), card_w, card_h)
        clear = x + card_w <= rect[0] or x >= rect[0] + rect[2] or y + card_h <= rect[1] or y >= rect[1] + rect[3]
        free = (rect[0] + rect[2] + card_w + 16 <= BIG[0] or rect[0] - card_w - 16 >= 0
                or rect[1] + rect[3] + card_h + 16 <= BIG[1] or rect[1] - card_h - 16 >= 0)
        assert clear or not free, step["title"]


def test_the_arrow_keys_step_the_list_selection_like_the_qt_list_unless_the_tool_takes_them(drv):
    app = drv.app
    drv.key(keys.KEY_DOWN)
    assert app.selected == "drift"
    drv.key(keys.KEY_UP)
    assert app.selected == "browser"
    drv.key(keys.KEY_UP)
    assert app.selected == "setup"
    drv.key(keys.KEY_UP)
    assert app.selected == "setup"  # the top of the list
    click_entry(drv, "clsm_generator")
    drv.key(keys.KEY_DOWN)
    assert app.selected == "clsm_generator"  # the bottom of the list

    class Takes(Child):
        def key(self, key, text="", modifiers=0):
            return True

    other = ImagingToolsApp(client=Client(), factories={r: Takes for r in ROLES})
    d = HubDriver(other, BIG)
    d.draw(3)
    d.key(keys.KEY_DOWN)
    assert other.selected == "browser"  # a focused field in the tool keeps its arrow keys
    other.close()


def test_the_whole_flow_works_in_the_small_window_too():
    app = fake_hub()
    d = HubDriver(app, SMALL)
    d.draw(3)
    d.click(d.rect("entry:pixel_intensity"))
    d.click("next")
    assert app.selected == "pixel_nb"
    d.type_into("search", "mle", enter=False)
    assert "6. Pixel-wise MLE" in d.draw(2).strings and "Browser" not in d.draw(2).strings
    d.click_text("Guide")
    assert app.tour.active
    app.close()
