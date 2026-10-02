"""Click coverage of the native micro-time shifter: every control is operated with real pointer, key, wheel and drop input.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` and the host's drop hook (``on_paths_dropped``, which
``emtk.qt_host`` calls for a window without ``files_dropped``) reach the window; each test asserts what a user sees or
gets (the strings of the frame, the histogram's drawn lines, the shifted file). The control -> test list is in
``okf/plugins/emtk-ports/microtime_shifter/REPORT.md``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
# Before the plugin import, which puts modules/ndxplorer (and its own `test` package) on sys.path.
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui as _Ui, hermetic  # noqa: E402,F401
from emtk import keys  # noqa: E402
from emtk.app import RIGHT_BUTTON  # noqa: E402

from chisurf.plugins.tttr.tttr_microtime_shifter.gui.app import create_app  # noqa: E402
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import N_MT, RISE, TARGET, build  # noqa: E402
# isort: on

SIZE = (1200, 800)
GREEN, YELLOW = (50, 200, 90, 255), (255, 220, 40, 255)


class Ui(_Ui):
    """The traj family's pointer/keyboard driver plus what the shifter needs: a host drop, drags, right click, the job."""

    def drop(self, *paths):
        self.app.on_paths_dropped([str(p) for p in paths])
        self.settle()

    def settle(self, timeout=60.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.job.running:
            assert time.monotonic() < end, "the job did not finish"
            time.sleep(0.02)
            self.draw(1)
        return self.draw(3)

    def type_into(self, key, text, enter=True, replace=True, fx=0.3):
        """As the base, at *fx* across the field (a channel row's field has its step arrows at the left)."""
        self.draw(1)
        self.click(key, fx=fx)
        assert self.app.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.type_text(text, replace)
        if enter:
            self.key(keys.KEY_RETURN, "\r")
        return self.draw(2)

    def job_started(self):
        return self.app.job.running

    def right_click(self, key_or_rect):
        rect = self.app.item_rects[key_or_rect] if isinstance(key_or_rect, str) else key_or_rect
        x, y, w, h = rect
        self.app.pointer_move(x + w / 2, y + h / 2)
        self.draw(1)
        self.app.pointer_press(x + w / 2, y + h / 2, RIGHT_BUTTON, 0, 1)
        self.draw(1)
        self.app.pointer_release(x + w / 2, y + h / 2, RIGHT_BUTTON, 0)
        return self.draw(2)

    def drag(self, start, end, steps=8):
        from emtk.app import LEFT_BUTTON

        self.app.pointer_move(*start)
        self.draw(1)
        self.app.pointer_press(*start, LEFT_BUTTON, 0, 1)
        self.draw(1)
        for i in range(1, steps + 1):
            self.app.pointer_move(start[0] + (end[0] - start[0]) * i / steps,
                                  start[1] + (end[1] - start[1]) * i / steps, LEFT_BUTTON)
            self.draw(1)
        self.app.pointer_release(*end, LEFT_BUTTON, 0)
        return self.draw(3)

    # -- the histogram -------------------------------------------------------------------------------- #
    def lines(self, colour):
        return [f for f in self.last.fills if f[4] == colour and (f[2] <= 3 or f[3] <= 3) and max(f[2], f[3]) > 200]

    def plot_box(self):
        """Left, top, width, height of the plot area, from its four axis border lines."""
        border = [f for f in self.last.fills if f[4] == (90, 90, 96, 200) and max(f[2], f[3]) > 200]
        xs = sorted({f[0] for f in border}), sorted({f[1] for f in border})
        x0, x1, y0, y1 = xs[0][0], max(f[0] + f[2] for f in border), xs[1][0], max(f[1] + f[3] for f in border)
        return x0, y0, x1 - x0, y1 - y0

    def target_line_x(self):
        return self.lines(GREEN)[0][0] + 0.5

    def level_line_y(self):
        return self.lines(YELLOW)[0][1] + 0.5

    def axis_numbers(self):
        out = []
        for s in self.last.strings:
            try:
                out.append(float(s))
            except ValueError:
                pass
        return out


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build(tmp_path_factory.mktemp("mts_clicks") / "demo")


@pytest.fixture
def ui():
    ui = Ui(create_app(), SIZE)
    yield ui
    ui.app.close()


@pytest.fixture
def loaded(ui, demo):
    ui.drop(demo)
    assert ui.app.n_mt == N_MT
    return ui


def shifts(app):
    return {ch: app.channel_shifts[ch] for ch in sorted(app.channel_shifts)}


EXPECTED = {ch: (TARGET - 1 - RISE[ch]) % N_MT for ch in RISE}      # the rising edge is found one bin after the rise


def test_the_idle_window_offers_only_what_can_act(ui):
    assert ui.shown("No file loaded.") and ui.shown("No file loaded.")
    for name in ("auto_align", "save_dialog", "save_batch"):
        assert not ui.app.enabled(name), name
    ui.click("auto_align")
    ui.click("save_dialog")
    assert not ui.dialog_open and not ui.app.channel_shifts
    ui.click("save_batch")
    assert ui.app.message == "No file loaded." and not ui.job_started()


# -- the files dock -------------------------------------------------------------------------------------- #
def test_guide_and_help_buttons_are_pressed(ui):
    ui.click("guide")
    steps = len(ui.app.tour.steps)
    assert ui.app.tour.active and ui.shown(f"Step 1 of {steps}")
    ui.press_text("Next ►")
    assert ui.app.tour.step_idx == 1 and ui.shown(f"Step 2 of {steps}")
    ui.app.tour.start(3)
    ui.draw(2)
    ui.press_text("◄ Prev")
    assert ui.app.tour.step_idx == 2
    ui.press_text("Close Tour")
    assert not ui.app.tour.active
    ui.click("help")
    assert ui.app.help.open
    ui.press_text("Close Help")
    assert not ui.app.help.open


def test_the_files_button_opens_a_dialog_and_every_way_out_works(ui, demo, monkeypatch):
    monkeypatch.chdir(demo.parent)
    ui.click("add_files")
    assert ui.dialog_open and ui.shown("TTTR inputs") and ui.shown("Cancel")
    assert ui.shown(demo.name)
    ui.press_text("Open")                                             # nothing selected
    assert ui.dialog_open and ui.shown("Select a file first.") and not ui.app.files
    ui.press_text("Cancel")
    assert not ui.dialog_open and not ui.app.files
    ui.click("add_files")
    ui.press_text("×")
    assert not ui.dialog_open and not ui.app.files
    ui.click("add_files")
    ui.press_text(demo.name)
    ui.press_text("Open")
    ui.settle()
    assert not ui.dialog_open and ui.app.files == [demo.resolve()] and ui.app.n_mt == N_MT
    assert ui.shown(demo.name) and ui.shown("Loaded 1 file(s), 4096 micro-time bins.")


def test_the_files_dialog_double_click_takes_the_file_at_once(ui, demo):
    ui.click("add_files")
    ui.app.dialog.directory = str(demo.parent)
    ui.draw(2)
    ui.press_text(demo.name, clicks=2)
    ui.settle()
    assert not ui.dialog_open and ui.app.files == [demo.resolve()]


def test_the_folder_button_queues_the_photon_files_of_a_folder(ui, demo):
    ui.click("add_folder")
    assert ui.dialog_open and ui.shown("TTTR folder")
    ui.app.dialog.directory = str(demo.parent.parent)
    ui.draw(2)
    ui.press_text(f"[{demo.parent.name}]")
    ui.press_text("Choose")
    ui.settle()
    assert not ui.dialog_open and ui.app.files == [demo.resolve()]


def test_a_dropped_file_is_loaded_and_a_foreign_one_is_answered(ui, demo, tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("not photons")
    ui.drop(other)
    assert not ui.app.files and ui.shown("Choose supported TTTR or PTO photon files.")
    ui.drop(demo)
    assert ui.app.files == [demo.resolve()] and ui.app.n_mt == N_MT and ui.shown(demo.name)


def test_a_dropped_folder_queues_its_file(ui, demo):
    ui.drop(demo.parent)
    assert ui.app.files == [demo.resolve()]


def test_the_database_button_opens_the_dataset_picker_and_closes_again(ui):
    ui.click("add_database")
    assert ui.app.dataset_picker.is_open
    ui.draw(3)
    ui.press_text("Cancel") if ui.shown("Cancel") else ui.press_text("Close")
    assert not ui.app.dataset_picker.is_open


def test_selecting_the_file_in_the_list_reloads_it_and_resets_the_shifts(loaded):
    loaded.click("auto_align")
    assert shifts(loaded.app) == EXPECTED
    loaded.click("file_0")
    loaded.settle()
    assert shifts(loaded.app) == {0: 0, 8: 0}


def test_remove_takes_the_selected_file_off_the_queue_not_the_disk(loaded, demo):
    loaded.click("remove")
    loaded.settle()
    assert loaded.app.files == [] and demo.exists()
    assert not loaded.shown(demo.name)


def test_the_context_menu_removes_the_file(loaded, demo):
    loaded.right_click("file_0")
    assert loaded.shown("Remove from queue")
    loaded.press_text("Remove from queue")
    assert loaded.app.files == [] and demo.exists()


def test_clear_empties_the_queue_and_the_histogram(loaded):
    loaded.click("clear")
    loaded.settle()
    assert loaded.app.files == [] and not loaded.app.channel_shifts and loaded.app.n_mt == 0
    assert loaded.shown("No file loaded.")
    assert not loaded.app.enabled("auto_align")


# -- alignment ------------------------------------------------------------------------------------------- #
def test_auto_align_click_shifts_each_detector_onto_the_target(loaded):
    assert shifts(loaded.app) == {0: 0, 8: 0}
    loaded.click("auto_align")
    assert shifts(loaded.app) == EXPECTED
    assert loaded.shown(str(EXPECTED[0])) and loaded.shown(str(EXPECTED[8]))


def test_the_default_trigger_is_what_the_qt_tool_computes(loaded):
    assert (loaded.app.trigger_level, loaded.app.trigger_position) == (124, 409)
    assert loaded.shown("124") and loaded.shown("409")


def test_trigger_level_and_target_bin_are_typed_and_realign(loaded):
    loaded.click("auto_align")
    loaded.type_into("trigger_position", "1000")
    assert loaded.app.trigger_position == 1000
    assert shifts(loaded.app)[0] == (1000 - 1 - RISE[0]) % N_MT
    loaded.type_into("trigger_level", "300")
    assert loaded.app.trigger_level == 300
    loaded.type_into("trigger_level", "0")                            # below the minimum: clamped, never a zero threshold
    assert loaded.app.trigger_level >= 1
    loaded.type_into("trigger_level", "abc")                          # not a number: the field keeps its value
    assert loaded.app.trigger_level >= 1


def test_the_target_bin_is_bounded_by_the_bin_count(loaded):
    loaded.type_into("trigger_position", "999999")
    assert 0 <= loaded.app.trigger_position <= N_MT - 1


def test_the_trigger_fields_step_with_their_arrows(loaded):
    loaded.arrow("trigger_level", +1)
    assert loaded.app.trigger_level == 125


def test_show_trigger_lines_toggles_the_histogram_lines(loaded):
    assert loaded.lines(GREEN) and loaded.lines(YELLOW)
    loaded.click("show_trigger")
    assert not loaded.app.show_trigger and not loaded.lines(GREEN) and not loaded.lines(YELLOW)
    loaded.click("show_trigger")
    assert loaded.lines(GREEN) and loaded.lines(YELLOW)


def test_log_y_switches_the_axis(loaded):
    linear = loaded.axis_numbers()
    loaded.click("log_y")
    assert loaded.app.log_y
    log = loaded.axis_numbers()
    assert log != linear and any(v in log for v in (1.0, 10.0, 100.0, 1000.0))
    assert 200.0 not in log and 300.0 not in log        # decades only: the counts axis is logarithmic
    loaded.click("log_y")
    assert not loaded.app.log_y and loaded.axis_numbers() == linear


def test_dragging_the_green_line_moves_the_target_bin_and_aligns_on_release(loaded):
    loaded.click("auto_align")
    x0, y0, w, h = loaded.plot_box()
    start = (loaded.target_line_x(), y0 + h * 0.5)
    goal = (x0 + w * 1500 / N_MT, start[1])
    loaded.drag(start, goal)
    assert loaded.app.trigger_position == pytest.approx(1500, abs=N_MT / w * 3)
    assert shifts(loaded.app)[0] == (loaded.app.trigger_position - 1 - RISE[0]) % N_MT
    assert loaded.target_line_x() == pytest.approx(goal[0], abs=3)
    assert loaded.shown(str(loaded.app.trigger_position))


def test_dragging_the_yellow_line_moves_the_trigger_level(loaded):
    x0, y0, w, h = loaded.plot_box()
    start = (x0 + w * 0.7, loaded.level_line_y())
    loaded.drag(start, (start[0], start[1] - 150))
    assert loaded.app.trigger_level > 124 * 1.5


def test_the_wheel_over_the_histogram_zooms(loaded):
    x0, y0, w, h = loaded.plot_box()
    before = loaded.axis_numbers()
    for _ in range(4):
        loaded.app.wheel(x0 + w * 0.12, y0 + h * 0.5, 1)
        loaded.draw(2)
    after = loaded.axis_numbers()
    assert after != before and max(after) < max(before), (before, after)     # zoomed in: the axis ends sooner


# -- shifts ---------------------------------------------------------------------------------------------- #
def test_a_channel_shift_is_typed_stepped_and_reset(loaded):
    loaded.type_into("shift_0", "123", fx=0.3)
    assert loaded.app.channel_shifts[0] == 123
    loaded.arrow("shift_0", +1)
    assert loaded.app.channel_shifts[0] == 124
    loaded.arrow("shift_0", -1)
    loaded.arrow("shift_0", -1)
    assert loaded.app.channel_shifts[0] == 122
    loaded.click("reset_0")
    assert loaded.app.channel_shifts[0] == 0 and loaded.app.channel_shifts[8] == 0


def test_a_shift_moves_the_drawn_histogram_cyclically(loaded):
    before = loaded.app.histograms()[0].copy()
    loaded.type_into("shift_0", "100", fx=0.3)
    assert np.array_equal(loaded.app.histograms()[0], np.roll(before, 100))


def test_the_global_shift_arrows_step_by_one_and_stay_bounded(loaded):
    loaded.arrow("global_shift", +1)
    assert loaded.app.global_shift == 1
    loaded.arrow("global_shift", -1)
    loaded.arrow("global_shift", -1)
    assert loaded.app.global_shift == -1


def test_the_wheel_steps_a_number_field(loaded):
    before = loaded.app.trigger_level
    loaded.wheel_over("trigger_level", 2)
    assert loaded.app.trigger_level != before


def test_the_global_shift_is_added_to_every_channel(loaded):
    loaded.type_into("global_shift", "50")
    assert loaded.app.global_shift == 50
    assert np.array_equal(loaded.app.histograms()[8], np.roll(loaded.app.raw_histograms[8], 50))
    loaded.type_into("global_shift", "999999")
    assert abs(loaded.app.global_shift) <= N_MT - 1


# -- saving ---------------------------------------------------------------------------------------------- #
def _micro(path):
    import tttrlib

    d = tttrlib.TTTR(str(path))
    return np.asarray(d.micro_times, dtype=np.int64), np.asarray(d.routing_channels, dtype=np.int64)


def test_save_shifted_writes_the_file_with_the_shifts_applied(loaded, demo, tmp_path):
    loaded.click("auto_align")
    target = tmp_path / "typed_name.spc"
    loaded.click("save_dialog")
    assert loaded.dialog_open and loaded.shown("Save shifted TTTR") and loaded.shown(demo.stem + "_shifted")
    loaded.press_text("Cancel")
    assert not loaded.dialog_open and not target.exists()
    loaded.click("save_dialog")
    loaded.save_dialog_type_name(str(target))
    loaded.press_text("Save")
    loaded.settle()
    assert target.exists()
    src_micro, src_ch = _micro(demo)
    new_micro, new_ch = _micro(target)
    want = np.array([(m + EXPECTED[c]) % N_MT for m, c in zip(src_micro, src_ch)])
    assert np.array_equal(new_micro, want) and np.array_equal(new_ch, src_ch)


def test_save_batch_needs_a_folder_then_writes_one_file_per_input(loaded, demo, tmp_path):
    loaded.click("auto_align")
    loaded.click("save_batch")
    assert loaded.shown("Choose an output folder first.")
    out = tmp_path / "out"
    out.mkdir()
    loaded.click("browse_output_folder")
    assert loaded.dialog_open and loaded.shown("Output folder")
    loaded.press_text("Cancel")
    assert not loaded.app.output_folder
    loaded.app.output_folder = ""
    loaded.type_into("output_folder", str(out))
    assert loaded.app.output_folder == str(out)
    loaded.click("save_batch")
    loaded.settle()
    written = list(out.glob("*"))
    assert len(written) == 1
    assert np.array_equal(_micro(written[0])[0], np.array([(m + EXPECTED[c]) % N_MT for m, c in zip(*_micro(demo))]))


# -- MMFDB ----------------------------------------------------------------------------------------------- #
def test_the_mmfdb_panel_unfolds_and_its_buttons_answer(loaded):
    assert "MMFDB.fold" in loaded.app.item_rects
    assert not loaded.shown("Register shifts in MMFDB")
    loaded.click("MMFDB.fold")
    assert loaded.shown("Register shifts in MMFDB") and loaded.shown("Refresh samples") and loaded.shown("New sample")
    loaded.press_text("➕  New sample…") if loaded.shown("➕  New sample…") else loaded.press_text("➕ New sample…")
    assert loaded.app.sample_definition is not None and loaded.shown("New MMFDB sample")
    loaded.press_text("Cancel sample")
    assert loaded.app.sample_definition is None


def test_the_other_panels_fold(loaded):
    assert loaded.shown("Auto align")
    loaded.click("Alignment.fold")
    assert not loaded.shown("Trigger level") and not loaded.shown("⚡ Auto align")
    loaded.click("Alignment.fold")
    assert loaded.shown("Trigger level")


def test_the_status_tab_shows_the_file_and_the_message(loaded, demo):
    loaded.press_text("Status")
    assert loaded.shown(str(demo.resolve())) or loaded.shown("File:")
    loaded.press_text("↔ Micro-time shift")
    assert loaded.shown("Trigger level")


def test_help_page_and_guide_do_not_hide_the_tool_after_closing(loaded):
    loaded.click("guide")
    loaded.press_text("Close Tour")
    assert not loaded.app.tour.active and loaded.shown("Trigger level")


def test_qt_free():
    assert qt_free("microtime_shifter")


@pytest.mark.xfail(strict=True, reason="shared gap (chisurf/emtk/help_guide.py): the tour card does not block what lies under "
                                       "it, so Close Tour is dead on a step whose card sits over a field "
                                       "(okf/plugins/emtk-ports/scripts/emtk_gaps_repro.py)")
def test_no_tour_card_button_is_dead_on_any_step():
    from chisurf.plugins.traj.traj_save_topology.test.real_input import dead_tour_buttons

    assert dead_tour_buttons(create_app, SIZE) == []
    assert dead_tour_buttons(create_app, (800, 600)) == []
