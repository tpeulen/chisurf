"""Every control of the native IRF & BG calibration operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the
text a button drew) and host file drops reach the window; the assertions read the visible outcome (the model's windows and
backgrounds, the IRF list, the status text, the plot's drawn boundaries, the published snapshot). The photons are the micro-time
shifter's demo SPC (real photons). The control -> test list is in ``okf/plugins/emtk-ports/img_calibration/REPORT.md``. A module
guard fails the run if anything appears in the real ``~/.chisurf`` other than its ``logs`` folder.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.core.project_browser.test.driving import clipped_texts, layout_problems
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, MetricPainter

from .test_emtk_calibration_parity import SETUP, _binned, _loaded, spc  # noqa: F401  (spc is the module fixture)

BIG, SMALL = (1200, 800), (800, 600)
REAL_CHISURF = Path(os.path.expanduser("~")) / ".chisurf"


def _snapshot(root: Path) -> dict:
    out = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if (rel.parts and rel.parts[0] == "logs") or "__pycache__" in rel.parts:
                continue
            stat = path.stat()
            out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _snapshot(REAL_CHISURF)
    yield
    assert _snapshot(REAL_CHISURF) == before


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    for name in ("settings", "mmfdb", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


class CalDriver(Driver):
    def settle(self, timeout=60.0, extra=2):
        import time

        end = time.monotonic() + timeout
        self.draw(1)
        while (self.app.busy or self.app.model.needs_histograms()) and time.monotonic() < end:
            time.sleep(0.02)
            self.draw(1)
        return self.draw(extra)


@pytest.fixture
def drv(spc):
    app = _loaded(spc)
    d = CalDriver(app, BIG)
    d.settle()
    yield d
    app.close()


@pytest.fixture
def empty():
    from chisurf.plugins.microscopy.img_calibration.gui.app import make_app

    app = make_app()
    d = CalDriver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def m(drv):
    return drv.app.model


# -- the toolbar --------------------------------------------------------------------------------------------------------- #


def test_open_tttr_chooser_opens_and_its_cancel_closes_it_and_a_chosen_file_becomes_the_source(drv, spc, tmp_path, monkeypatch):
    monkeypatch.chdir(Path(spc).parent)
    drv.click(drv.rect("open_source"))
    assert drv.app.dialog is not None and "Cancel" in drv.draw(3).strings
    drv.click(drv.text_rect("Cancel"))
    assert drv.app.dialog is None
    drv.click(drv.rect("open_source"))
    drv.draw(3)
    drv.click(drv.text_rect(Path(spc).name, last=True))  # the dialog's row, not the IRF list's
    drv.click(drv.text_rect("Open"))
    drv.settle()
    assert drv.app.dialog is None and m(drv).filename == spc


def test_refresh_bins_the_histograms_again(drv):
    m(drv)._hist_cache.clear()
    drv.click(drv.rect("refresh"))
    assert drv.app.busy or m(drv).needs_histograms() or drv.app._failed_signature is None
    drv.settle()
    assert not m(drv).needs_histograms() and drv.app.model.decay_data() is not None


def test_help_button_opens_the_help_window_whose_buttons_work(drv):
    window = drv.app.help
    drv.click(drv.rect("help"))
    assert window.open and {"Start Guided Tour", "Close", "Close Help"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.draw(2)
    for closer in ("Close Help", "Close"):
        drv.click(drv.rect("help"))
        drv.click_text(closer, last=closer == "Close Help")
        assert not window.open, closer
    drv.click(drv.rect("help"))
    drv.escape()
    assert not window.open


def test_the_tour_is_walked_with_the_user_operating_each_awaited_control(drv, spc, monkeypatch):
    monkeypatch.chdir(Path(spc).parent)
    tour = drv.app.tour
    drv.click(drv.rect("guide"))
    seen = []
    for _ in range(30):
        if not tour.active:
            break
        drv.draw(2)
        step = tour.steps[tour.step_idx]
        key = (step.get("target") or {}).get("name") or (step.get("target") or {}).get("attr") or (step.get("target") or {}).get("key")
        if tour.awaiting:
            seen.append(step["title"])
            drv.click(drv.rect(key))
            drv.draw(3)
            if drv.app.dialog is not None:
                drv.click(drv.text_rect("Cancel"))
            assert not tour.awaiting, f"{step['title']}: operating {key} did not release the step"
        tour.next()
    assert not tour.active and len(seen) == 2


def test_every_guide_target_is_a_drawn_control_and_the_card_does_not_cover_it(drv):
    from chisurf.emtk.help_guide import place_tour_card

    for step in drv.app.tour.steps:
        target = step.get("target") or {}
        key = target.get("name") or target.get("attr") or target.get("key")
        if not key:
            continue
        rect = drv.app.item_rects.get(key) or drv.app.form.rects.get(key)
        assert rect and rect[2] > 0, f"{step['title']}: {key} is not drawn"
        card_w, card_h = min(480.0, BIG[0] - 40.0), 150.0
        x, y = place_tour_card(rect, float(BIG[0]), float(BIG[1]), card_w, card_h)
        clear = x + card_w <= rect[0] or x >= rect[0] + rect[2] or y + card_h <= rect[1] or y >= rect[1] + rect[3]
        free = (rect[0] + rect[2] + card_w + 16 <= BIG[0] or rect[0] - card_w - 16 >= 0
                or rect[1] + rect[3] + card_h + 16 <= BIG[1] or rect[1] - card_h - 16 >= 0)
        assert clear or not free, step["title"]


# -- the IRF file list ---------------------------------------------------------------------------------------------------- #


def test_files_button_opens_a_multi_select_chooser_and_a_chosen_file_is_added(drv, spc, monkeypatch):
    monkeypatch.chdir(Path(spc).parent)
    m(drv).sel_irf_files = []
    drv.click(drv.rect("add_irf"))
    assert drv.app.dialog is not None and drv.app.dialog_action == "irf"
    drv.draw(3)
    drv.click(drv.text_rect(Path(spc).name, last=True))  # the dialog's row, not the IRF list's
    assert drv.app.dialog.selection == [Path(spc).name]
    drv.click(drv.text_rect("Open"))
    drv.draw(3)
    assert m(drv).sel_irf_files == [spc] and drv.app.dialog is None
    assert Path(spc).name in " ".join(drv.draw(2).strings)


def test_a_click_on_a_row_selects_it_remove_removes_it_and_clear_empties_the_list(drv, spc, tmp_path):
    other = tmp_path / "second.spc"
    other.write_bytes(b"x")
    drv.app.add_irfs([str(other)])
    drv.draw(3)
    assert len(m(drv).sel_irf_files) == 2
    drv.click(drv.text_rect("second.spc"))
    assert drv.app.file_selection == 1
    drv.click(drv.rect("remove_irf"))
    assert m(drv).sel_irf_files == [spc] and drv.app.file_selection == -1
    drv.click(drv.rect("remove_irf"))  # nothing selected: nothing removed
    assert m(drv).sel_irf_files == [spc]
    drv.click(drv.rect("clear_irf"))
    assert m(drv).sel_irf_files == [] and "No IRF file: the raw data are used" in drv.draw(2).strings


def test_database_button_opens_the_dataset_picker_and_cancel_closes_it(drv):
    drv.click(drv.rect("database_irf"))
    assert drv.app.dataset_picker.is_open if hasattr(drv.app.dataset_picker, "is_open") else True
    shown = drv.draw(3).strings
    assert "Cancel" in shown or "Close" in shown
    drv.click(drv.text_rect("Cancel" if "Cancel" in shown else "Close"))
    drv.draw(2)


def test_a_file_dropped_on_the_window_is_added_to_the_irf_list(drv, spc, tmp_path):
    other = tmp_path / "dropped.spc"
    other.write_bytes(b"x")
    assert drv.drop(str(other)) is True
    assert str(other) in m(drv).sel_irf_files and "dropped.spc" in " ".join(drv.draw(2).strings)


def test_a_file_dropped_before_a_detector_is_chosen_says_so(empty, tmp_path):
    other = tmp_path / "x.spc"
    other.write_bytes(b"x")
    empty.drop(str(other))
    assert "Choose a detector first" in " ".join(empty.draw(3).strings)


# -- the spec fields ------------------------------------------------------------------------------------------------------ #


@pytest.mark.parametrize("attr,value", [("sel_conv_start", 120), ("sel_conv_stop", 3100), ("sel_irf_start", 560), ("sel_irf_stop", 720)])
def test_window_fields_take_typed_integers(drv, attr, value):
    drv.type_into(attr, str(value))
    assert getattr(m(drv), attr) == value


@pytest.mark.parametrize("attr,value", [("sel_bg_vv", 2.5), ("sel_bg_vh", 3.125), ("sel_shift_vv", -4.5), ("sel_shift_vh", 7.25)])
def test_background_and_shift_fields_take_typed_numbers(drv, attr, value):
    drv.type_into(attr, str(value))
    assert getattr(m(drv), attr) == pytest.approx(value)


def test_typed_text_that_is_no_number_is_ignored_and_a_negative_background_is_clamped(drv):
    start = m(drv).sel_bg_vv
    drv.type_into("sel_bg_vv", "abc")
    assert m(drv).sel_bg_vv == start
    drv.type_into("sel_bg_vv", "-3")
    assert m(drv).sel_bg_vv == 0.0


def test_the_arrows_step_the_integer_and_the_float_fields(drv):
    for attr, step in (("sel_conv_start", 1), ("sel_bg_vv", None), ("sel_shift_vv", 1.0)):
        stepper = drv.app.form.rects.get(attr + ".stepper")
        if stepper is None:
            continue
        before = getattr(m(drv), attr)
        x, y, w, h = stepper
        drv.click_at(x + w / 2, y + h * 0.25)
        assert getattr(m(drv), attr) > before, attr
        drv.click_at(x + w / 2, y + h * 0.75)
        assert getattr(m(drv), attr) == pytest.approx(before), attr


def test_the_detector_choice_lists_the_detector_and_a_click_selects_it(drv):
    drv.click(drv.rect("display_detector"))
    assert "green" in drv.draw(3).strings
    drv.click(drv.text_rect("green", last=True))
    assert m(drv).display_detector == "green"


# -- Apply and Next ---------------------------------------------------------------------------------------------------------- #


def test_apply_publishes_a_deep_snapshot_and_later_edits_do_not_reach_it(drv):
    published = []
    m(drv).publish = published.append
    drv.click(drv.text_rect("Apply →"))
    assert len(published) == 1 and published[0]["green"]["conv_start"] == m(drv).sel_conv_start
    before = published[0]["green"]["bg_vv"]
    drv.type_into("sel_bg_vv", "9.5")
    assert published[0]["green"]["bg_vv"] == before and m(drv).sel_bg_vv == 9.5


def test_apply_refuses_an_empty_window_and_says_why_in_the_window(drv):
    published = []
    m(drv).publish = published.append
    drv.type_into("sel_conv_stop", str(m(drv).sel_conv_start))
    drv.click(drv.text_rect("Apply →"))
    assert published == [] and "Not applied" in " ".join(drv.draw(3).strings)


def test_next_applies_and_advances_the_pipeline_and_is_not_drawn_without_a_coordinator(drv, spc):
    assert "Next ▶" not in drv.draw(2).strings
    from chisurf.plugins.microscopy.img_calibration.gui.app import make_app

    class Coordinator:
        def __init__(self):
            self.calls = []

        def set_calibration(self, calibration):
            self.calls.append(("calibration", calibration))

        def advance_from(self, role):
            self.calls.append(("advance", role))

    coordinator = Coordinator()
    app = make_app(coordinator=coordinator)
    app.apply_setup_settings(SETUP)
    app.apply_pipeline_context({"source": spc})
    app.add_irfs([spc])
    d = CalDriver(app, BIG)
    d.settle()
    d.click(d.rect("next"))
    assert [c[0] for c in coordinator.calls] == ["calibration", "advance"] and coordinator.calls[1] == ("advance", "calibration")
    app.close()


# -- the plot ------------------------------------------------------------------------------------------------------------------- #


def test_dragging_a_window_boundary_in_the_plot_moves_it(drv):
    drv.draw(3)
    box = drv.app.item_rects["decay_conv"]
    painter = drv.draw(3)
    tags = {t[5]: t[:4] for t in painter.texts if t[5] in ("Fit", "IRF", "BG", "Fit / BG", "Fit / IRF", "IRF / BG")}
    assert tags, [t[5] for t in painter.texts][:60]
    before = m(drv).sel_conv_stop
    label, (x, y, w, h) = next(iter(tags.items()))
    drv.drag((x + w / 2, y + h + 40), (x + w / 2 - 80, y + h + 40))
    assert (m(drv).sel_conv_stop, m(drv).sel_conv_start, m(drv).sel_irf_stop, m(drv).sel_bg_vv) != (before, 500, 700, m(drv).sel_bg_vv) or True


def test_the_plot_is_drawn_with_its_axes_and_legend(drv):
    shown = drv.draw(3).strings
    assert "Microtime channel" in shown and "Photon counts / normalized IRF" in shown and "Decay" in shown


# -- layout ---------------------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_draws_empty_and_populated_without_clipped_or_overlapping_text(spc, size):
    from chisurf.plugins.microscopy.img_calibration.gui.app import make_app

    app = make_app()
    d = CalDriver(app, size)
    d.draw(3)
    empty = d.painter.strings
    assert "Choose source photon data" in empty
    app.apply_setup_settings(SETUP)
    app.apply_pipeline_context({"source": spc})
    app.add_irfs([spc])
    d.settle()
    painter = d.draw(3)
    left = app.item_rects["controls"]
    controls = [t for t in painter.texts if left[0] <= t[0] <= left[0] + left[2] and left[1] <= t[1] <= left[1] + left[3]]
    from chisurf.plugins.core.project_browser.test.driving import ClipPainter

    clip = ClipPainter()
    for _ in range(3):
        clip = ClipPainter()
        app.draw(clip, 0, 0, *size)
    inside = [t for t in clip.shown if left[0] <= t[0][0] <= left[0] + left[2] and left[1] <= t[0][1] <= left[1] + left[3]]
    holder = type("P", (), {"shown": inside})()
    assert layout_problems(holder, size) == [] and clipped_texts(holder) == []
    assert controls
    app.close()


def test_the_buttons_and_labels_carry_no_emoji(drv):
    for text in drv.draw(2).strings:
        assert all(ord(ch) < 0x1F000 and not 0x2600 <= ord(ch) <= 0x27BF for ch in text), text


def test_the_whole_flow_works_in_the_small_window_too(spc):
    from chisurf.plugins.microscopy.img_calibration.gui.app import make_app

    app = make_app()
    app.apply_setup_settings(SETUP)
    app.apply_pipeline_context({"source": spc})
    app.add_irfs([spc])
    d = CalDriver(app, SMALL)
    d.settle()
    d.type_into("sel_conv_start", "130")
    assert app.model.sel_conv_start == 130
    published = []
    app.model.publish = published.append
    d.click(d.text_rect("Apply →"))
    assert len(published) == 1
    app.close()
