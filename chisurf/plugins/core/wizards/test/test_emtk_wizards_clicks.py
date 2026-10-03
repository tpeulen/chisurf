"""The native Wizards hub operated with simulated pointer, wheel, key and drop events (every control, both sizes)."""

from __future__ import annotations

import pytest
from emtk import keys

from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401
from chisurf.plugins.emtk_test_input import Driver, assert_tour_card_clear

from ..gui.app import WizardHubApp

BIG, SMALL = (1200, 800), (800, 600)


@pytest.fixture
def drv():
    app = WizardHubApp()
    d = Driver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def test_a_click_on_an_entry_selects_it_and_builds_its_wizard(drv):
    assert drv.app.selected == "anisotropy"
    drv.click_name("entry:batch_analysis")
    assert drv.app.selected == "batch_analysis" and "batch_analysis" in drv.app.children
    assert any("Template fit" in s or "Loaded data" in s for s in drv.draw(3).strings)


def test_the_arrow_keys_step_the_selection_unless_the_wizard_takes_them(drv):
    drv.app.pointer_move(40.0, 40.0)
    drv.app.key(keys.KEY_DOWN, "")
    drv.draw(2)
    assert drv.app.selected == "batch_analysis"
    drv.app.key(keys.KEY_UP, "")
    drv.draw(2)
    assert drv.app.selected == "anisotropy"


def test_pointer_and_wheel_reach_the_embedded_wizard_in_its_own_coordinates(drv, tmp_path):
    drv.click_name("entry:batch_analysis")
    batch = drv.app.children["batch_analysis"]
    drv.draw(3)
    bx, by, _w, _h = drv.app.child_box
    sx, sy, sw, sh = batch.item_rects["step_files"]  # the child's rectangle, in its own coordinates
    drv.click((bx + sx, by + sy, sw, sh))
    assert batch.model.step_id == "files"
    # the wheel over the child's file table scrolls it (the child's own scrolling, reached through the hub)
    for i in range(40):
        (tmp_path / f"f{i:02d}.sm").write_text("x")
    batch.model.add_paths([str(tmp_path)])
    drv.draw(3)
    tx, ty, tw, th = batch.form.rects["file_rows"]
    first = lambda: sorted((t for t in drv.draw(2).texts if bx + tx <= t[0] <= bx + tx + tw and by + ty + 20 <= t[1] <= by + ty + th),
                           key=lambda t: t[1])[0][5]  # noqa: E731
    before = first()
    drv.wheel(bx + tx + tw / 2, by + ty + th / 2, steps=-4)
    assert first() != before


def test_a_file_dropped_on_the_window_goes_to_the_open_wizard(drv, tmp_path):
    drv.click_name("entry:batch_analysis")
    batch = drv.app.children["batch_analysis"]
    f = tmp_path / "a.sm"
    f.write_text("x")
    assert drv.drop(str(f)) is True
    assert batch.model.files == [str(f)]


def test_the_wizard_keeps_working_through_the_hub_a_whole_batch(drv, tmp_path):
    from chisurf.plugins.core.batch_analysis.test.fakes import FakeSession

    drv.click_name("entry:batch_analysis")
    batch = drv.app.children["batch_analysis"]
    batch.model.session = FakeSession()
    batch.model.reload_datasets()
    batch.model.reload_fits()
    batch.model.selected_dataset_indices = [0]
    batch.model.save_path = str(tmp_path / "r.csv")
    batch.model.go_to(3)
    drv.draw(3)
    x, y, w, h = drv.app.child_box
    cx, cy, cw, ch = batch.form.rects["run"]
    drv.click((x + cx, y + cy, cw, ch))
    batch.model.wait(30)
    assert (tmp_path / "r.csv").exists() and batch.model.has_results


def test_help_button_opens_the_help_window_and_its_buttons_work(drv):
    drv.click_name("help")
    assert drv.app.help_window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not drv.app.help_window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.click_name("help")
    drv.escape()
    assert not drv.app.help_window.open


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_the_tour_is_walked_with_the_user_operating_the_awaited_list(size):
    app = WizardHubApp()
    d = Driver(app, size)
    d.draw(3)
    tour = app.tour
    d.click_name("guide")
    seen = []
    for _ in range(12):
        if not tour.active:
            break
        d.draw(3)
        assert_tour_card_clear(tour, size)
        if tour.awaiting:
            seen.append(tour.steps[tour.step_idx]["title"])
            d.click_name("entry:batch_analysis")
            assert not tour.awaiting
        tour.next()
    assert not tour.active and seen == ["Pick one"] and app.selected == "batch_analysis"
    app.close()


def test_the_tour_card_can_be_dragged(drv):
    from chisurf.plugins.emtk_test_input import tour_card_box

    drv.click_name("guide")
    drv.draw(3)
    x, y, w, h = tour_card_box(drv.app.tour, BIG)
    drv.drag((x + 30, y + 10), (x + 5, y + 50))
    assert drv.app.tour.card_offset != (0.0, 0.0)
    assert_tour_card_clear(drv.app.tour, BIG)
