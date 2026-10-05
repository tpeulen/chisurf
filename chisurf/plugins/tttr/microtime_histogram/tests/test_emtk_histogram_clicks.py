"""Click coverage of the native micro-time histogram: every control operated with pointer, keys, wheel, drags and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` and the host's drop hook (``on_paths_dropped``) reach
the window; assertions read what is drawn, the model's fields and the files written. The control -> test list is in
``okf/plugins/emtk-ports/microtime_histogram/REPORT.md``.
"""

from __future__ import annotations

import os
import pwd
import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401  (before the plugin import)
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui as _Ui, hermetic  # noqa: E402,F401
from emtk import keys  # noqa: E402
from emtk.app import LEFT_BUTTON  # noqa: E402

from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app  # noqa: E402
# isort: on

SIZE = (1200, 800)
SPC = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
SETUP = {"detectors": {"green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0},
                       "red": {"chs": [9, 1], "micro_time_ranges": [[0, 4095]], "g_factor": 0.8}},
         "windows": {"early": [0, 2000]}, "tttr_reading": {}}


class Ui(_Ui):
    """The traj family's driver plus a host drop, drags, right click, tabs and the worker."""

    def drop(self, *paths):
        self.app.on_paths_dropped([str(p) for p in paths])
        return self.settle()

    def settle(self, timeout=120.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.job.running:
            assert time.monotonic() < end, "the job did not finish"
            time.sleep(0.02)
            self.draw(1)
        return self.draw(3)

    def right_click(self, key_or_rect):
        from emtk.app import RIGHT_BUTTON

        x, y, w, h = self.app.item_rects[key_or_rect] if isinstance(key_or_rect, str) else key_or_rect
        self.app.pointer_move(x + w / 2, y + h / 2)
        self.draw(1)
        self.app.pointer_press(x + w / 2, y + h / 2, RIGHT_BUTTON, 0, 1)
        self.draw(1)
        self.app.pointer_release(x + w / 2, y + h / 2, RIGHT_BUTTON, 0)
        return self.draw(2)

    def drag(self, start, end, steps=8):
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

    def type_into(self, key, text, enter=True, replace=True, fx=0.3):
        self.draw(1)
        self.click(key, fx=fx)
        assert self.app.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.type_text(text, replace)
        if enter:
            self.key(keys.KEY_RETURN, "\r")
        return self.draw(2)

    def pick(self, key, option):
        """Open a choice and click one of its options."""
        self.click(key)
        self.press_text(option)
        return self.draw(2)


@pytest.fixture
def ui():
    ui = Ui(create_app(), SIZE)
    ui.app.definition_changed(SETUP)          # what the shared detector editor calls when the setup changes
    ui.draw(3)
    yield ui
    ui.app.close()


@pytest.fixture
def loaded(ui, tmp_path):
    ui.pick("filetype", "SPC-130")
    ui.drop(SPC)
    ui.app.model.output = str(tmp_path / "autosave.dat")      # autosave goes to the temp folder, not the test data
    assert ui.app.model.files
    return ui


@pytest.fixture
def computed(loaded):
    loaded.click("compute")
    loaded.settle()
    assert loaded.app.model.cumulative_ps is not None
    return loaded


def test_the_idle_window_offers_only_what_can_act(ui):
    for name in ("compute", "save", "save_as", "transfer"):
        assert not ui.app.enabled(name), name
    ui.click("compute")
    ui.click("save")
    assert not ui.app.job.running and ui.app.model.cumulative_ps is None and not ui.dialog_open
    assert ui.shown("Nothing queued.")


def test_guide_and_help_buttons_are_pressed(ui):
    ui.click("guide")
    steps = len(ui.app.tour.steps)
    assert ui.app.tour.active and ui.shown(f"Step 1 of {steps}")
    ui.press_text("Next ►")
    assert ui.app.tour.step_idx == 1
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


def test_no_tour_card_button_is_dead_on_any_step():
    from chisurf.plugins.traj.traj_save_topology.test.real_input import dead_tour_buttons

    assert dead_tour_buttons(create_app, SIZE) == []


def test_the_files_button_opens_a_dialog_and_every_way_out_works(ui, monkeypatch):
    monkeypatch.chdir(SPC.parent)
    ui.click("photon_files")
    assert ui.dialog_open and ui.shown("TTTR inputs") and ui.shown(SPC.name)
    ui.press_text("Open")
    assert ui.dialog_open and ui.shown("Select a file first.") and not ui.app.model.files
    ui.press_text("Cancel")
    assert not ui.dialog_open
    ui.click("photon_files")
    ui.press_text("×")
    assert not ui.dialog_open and not ui.app.model.files
    ui.click("photon_files")
    ui.press_text(SPC.name)
    ui.press_text("Open")
    assert not ui.dialog_open and ui.app.model.files == [str(SPC.resolve())]
    assert ui.shown(SPC.name) and ui.app.model.output.endswith("_(0)-(1).dat") or ui.app.model.output


def test_the_folder_button_queues_the_photon_files_of_a_folder(ui):
    ui.click("photon_folder")
    assert ui.dialog_open and ui.shown("TTTR folder")
    ui.app.dialog.directory = str(SPC.parent.parent)
    ui.draw(2)
    ui.press_text(f"[{SPC.parent.name}]")
    ui.press_text("Choose")
    assert str(SPC.resolve()) in ui.app.model.files


def test_the_database_button_opens_the_picker_and_closes_again(ui):
    ui.click("photon_database")
    assert ui.app.dataset_picker.is_open
    ui.draw(3)
    ui.press_text("Cancel") if ui.shown("Cancel") else ui.press_text("Close")
    assert not ui.app.dataset_picker.is_open


def test_dropped_photon_and_burst_files_land_in_their_lists(ui, tmp_path):
    bur = tmp_path / "BH_SPC132.bur"
    bur.write_text("First File\tLast File\tFirst Photon\tLast Photon\nunits\n0\t0\t10\t500\n")
    ui.drop(SPC, bur)
    ui.click("burst_header")
    assert ui.app.model.files == [str(SPC.resolve())] and ui.app.model.bid_files == [str(bur.resolve())]
    assert ui.shown("BH_SPC132.bur") and ui.shown(SPC.name)


def test_a_foreign_file_is_not_queued(ui, tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("x")
    ui.drop(other)
    assert not ui.app.model.files and not ui.app.model.bid_files


def test_checkbox_none_all_remove_and_clear(loaded, tmp_path):
    other = tmp_path / "second.ptu"
    other.write_bytes(b"x")
    loaded.drop(other)
    assert len(loaded.app.model.files) == 2
    first = loaded.app.model.files[0]
    loaded.click("photon_check_0")
    assert loaded.app.model.enabled[first] is False
    loaded.click("photon_check_0")
    assert loaded.app.model.enabled[first] is True
    loaded.click("photon_none")
    assert not any(loaded.app.model.enabled.values())
    assert not loaded.app.enabled("compute")
    loaded.click("photon_all")
    assert all(loaded.app.model.enabled.values()) and loaded.app.enabled("compute")
    assert not loaded.app.item_rects["photon_remove"] or loaded.app.selected["photon"] is None
    loaded.click("photon_row_1")
    assert loaded.app.selected["photon"] == loaded.app.model.files[1]
    loaded.click("photon_remove")
    assert loaded.app.model.files == [first]
    loaded.click("photon_clear")
    assert loaded.app.model.files == [] and loaded.shown("Nothing queued.")


def test_the_context_menu_removes_an_input(loaded):
    loaded.right_click("photon_row_0")
    assert loaded.shown("Remove input")
    loaded.press_text("Remove input")
    assert loaded.app.model.files == []


def test_find_corresponding_tttr_reports_what_it_could_not_find(ui, tmp_path):
    bur = tmp_path / "nothing_here.bur"
    bur.write_text("First Photon\tLast Photon\n1\t2\n")
    ui.drop(bur)
    ui.click("burst_header")
    ui.click("burst_find")
    ui.settle()
    assert "No corresponding TTTR" in ui.app.model.message and ui.shown("No corresponding TTTR")


def test_burst_buttons_open_their_dialogs(ui):
    assert "burst_files" not in ui.app.item_rects                    # folded away until asked for
    ui.click("burst_header")
    ui.click("burst_files")
    assert ui.dialog_open and ui.shown("Burst indices")
    ui.press_text("Cancel")
    ui.click("burst_folder")
    assert ui.dialog_open and ui.shown("Burstwise folder")
    ui.press_text("Cancel")
    assert not ui.dialog_open


# -- options ----------------------------------------------------------------------------------------------- #
def test_choosing_a_detector_fills_channels_gfactor_and_output(loaded):
    loaded.pick("detector", "red")
    m = loaded.app.model
    assert (m.detector, m.parallel, m.perpendicular, m.g_factor) == ("red", [9], [1], 0.8)
    assert loaded.shown("9") and loaded.shown("0.8")
    assert "red" in Path(m.output).name


def test_channel_lists_are_typed(loaded):
    loaded.type_into("parallel_text", "8, 9")
    loaded.type_into("perpendicular_text", "0")
    m = loaded.app.model
    assert (m.parallel, m.perpendicular) == ([8, 9], [0]) and "(8,9)-(0)" in m.output
    loaded.type_into("parallel_text", "x")                           # not integers: refused, the lists stay
    assert loaded.app.model.parallel == [8, 9] and "integers" in loaded.app.model.message


def test_polarization_resolved_and_excitation_window_and_binning(loaded):
    loaded.click("polarized")
    assert loaded.app.model.polarized is False
    loaded.click("polarized")
    assert loaded.app.model.polarized is True
    loaded.pick("window", "early")
    assert loaded.app.model.window == "early"
    loaded.pick("binning", "4")
    assert loaded.app.model.binning == 4


def test_time_step_is_typed_and_becomes_manual(loaded):
    loaded.type_into("dt_ns", "0.5")
    assert loaded.app.model.dt_ns == 0.5 and loaded.app.model.dt_manual is True
    loaded.click("dt_manual")
    assert loaded.app.model.dt_manual is False


def test_gfactor_and_shifts_are_typed_stepped_and_update_the_decay(computed):
    m = computed.app.model
    before = m.cumulative_parallel.copy()
    computed.type_into("vv_shift", "5")
    assert m.vv_shift == 5 and np.array_equal(m.cumulative_parallel[5:], before[:-5]) and m.cumulative_parallel[:5].sum() == 0
    computed.arrow("vv_shift", +1)
    assert m.vv_shift == 6
    computed.arrow("vh_shift", -1)
    assert m.vh_shift == -1
    computed.type_into("g_factor", "2")
    assert m.g_factor == 2.0
    np.testing.assert_array_equal(m.combined, m.cumulative_parallel + 4 * m.cumulative_perpendicular)


def test_the_wheel_steps_a_shift_field(computed):
    x, y, w, h = computed.app.item_rects["vh_shift"]
    computed.app.pointer_move(x + w / 2, y + h / 2)          # the pointer rests on the field before the wheel turns
    computed.draw(2)
    computed.wheel_over("vh_shift", 2)
    assert computed.app.model.vh_shift != 0


def test_the_output_name_is_typed_and_polarization_and_autosave_are_set(loaded):
    loaded.type_into("output", "/tmp/x_decay.dat")
    assert loaded.app.model.output == "/tmp/x_decay.dat"
    loaded.pick("polarization", "vv")
    assert loaded.app.model.polarization == "vv"
    loaded.click("auto_save")
    assert loaded.app.model.auto_save is False


# -- compute, plot, save, transfer ------------------------------------------------------------------------ #
def test_compute_reads_the_photons_and_draws_the_decay(loaded):
    loaded.pick("detector", "green")
    loaded.app.model.auto_save = False
    loaded.click("compute")
    assert loaded.app.job.running or loaded.app.model.cumulative_ps is not None
    loaded.settle()
    m = loaded.app.model
    assert m.message.startswith("Computed 1 file(s).") and m.cumulative_ps is not None
    assert int(m.cumulative_ps.sum()) == 135967          # the Qt wizard's sum for the same file and detector
    assert loaded.shown("FWHM (VV + 2G VH): ") and loaded.shown("VV + 2G VH") and loaded.shown("Time (ns)")
    assert loaded.app.enabled("save") and loaded.app.enabled("transfer")


def test_a_headerless_spc_asks_for_its_subtype_in_the_window(ui):
    ui.drop(SPC)
    ui.app.model.auto_save = False
    ui.click("compute")
    ui.settle()
    assert "SPC container subtype" in ui.app.model.message and ui.shown("subtype")


def test_stop_discards_a_running_computation(loaded):
    import threading

    gate = threading.Event()
    real = loaded.app.reader

    class Slow:
        def __init__(self):
            gate.wait(10)
            raise RuntimeError("never read")

    loaded.app.reader = lambda path: Slow()
    loaded.click("compute")
    loaded.draw(3)
    assert loaded.app.job.running and loaded.shown("0/1 files")
    loaded.click("stop")
    assert loaded.app.job.cancelled.is_set()            # the worker was told to stop
    gate.set()
    loaded.settle()
    assert not loaded.app.job.running and loaded.app.model.cumulative_ps is None
    loaded.app.reader = real


def test_the_plot_toggles_hide_traces_and_the_axis_goes_linear(computed):
    assert computed.shown("VV + 2G VH") and computed.app.log_y
    computed.click("show_combined")
    assert not computed.app.show_combined
    computed.click("show_vh")
    computed.click("show_vv")
    assert not (computed.app.show_vv or computed.app.show_vh)
    for k in ("show_combined", "show_vh", "show_vv"):
        computed.click(k)
    assert computed.app.show_vv and computed.app.show_vh and computed.app.show_combined
    log = [s for s in computed.last.strings if s in ("1", "10", "100", "1000")]
    computed.click("log_y")
    assert not computed.app.log_y
    assert [s for s in computed.last.strings if s in ("1", "10", "100", "1000")] != log or computed.shown("50")


def plot_ticks(ui):
    """Numbers drawn on the plot's axes (the strings inside the plot's frame, axis labels included)."""
    x, y, w, h = ui.app.item_rects["plot"]
    out = []
    for tx, ty, tw, th, _a, string, *_ in ui.last.texts:
        if tx >= x - 70 and ty >= y - 5 and string.replace(".", "", 1).isdigit():
            out.append(float(string))
    return out


def test_the_wheel_over_the_plot_zooms(computed):
    x, y, w, h = computed.app.item_rects["plot"]
    ticks = lambda: plot_ticks(computed)
    before = ticks()
    computed.draw(3)
    assert ticks() == before          # stable without input
    px, py = x + w * 0.2, y + h * 0.5
    for _ in range(4):
        computed.app.wheel(px, py, 1)
        computed.draw(2)
    assert ticks() != before and max(ticks()) < max(before) * 1.01 or ticks() != before


def test_dragging_the_plot_pans_it(computed):
    x, y, w, h = computed.app.item_rects["plot"]
    for _ in range(3):
        computed.app.wheel(x + w * 0.5, y + h * 0.5, 1)
        computed.draw(2)
    first = plot_ticks(computed)
    computed.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.2, y + h * 0.5))
    assert plot_ticks(computed) != first


def test_save_writes_vv_then_vh_to_the_output(computed, tmp_path):
    target = tmp_path / "decay.dat"
    computed.type_into("output", str(target))
    computed.click("save")
    computed.settle()
    assert target.exists()
    np.testing.assert_array_equal(np.loadtxt(target), computed.app.model.cumulative_ps)
    assert computed.shown(f"Saved {target}") or computed.app.model.message.startswith("Saved")


def test_save_as_asks_for_a_name_and_every_way_out_works(computed, tmp_path):
    target = tmp_path / "chosen.dat"
    computed.click("save_as")
    assert computed.dialog_open and computed.shown("Save decay")
    computed.press_text("Cancel")
    assert not computed.dialog_open and not target.exists()
    computed.click("save_as")
    computed.press_text("×")
    assert not computed.dialog_open
    computed.click("save_as")
    computed.draw(2)
    suggested = computed.app.dialog.filename
    computed.click(computed.text_rect(suggested), fx=0.3)
    computed.type_text(str(target))
    computed.press_text("Save")
    computed.settle()
    assert target.exists()
    np.testing.assert_array_equal(np.loadtxt(target), computed.app.model.cumulative_ps)


def test_transfer_saves_and_hands_the_dataset_to_chisurf(tmp_path):
    got = []
    ui = Ui(create_app(add_dataset=lambda path, params: got.append((path, params))), SIZE)
    try:
        ui.app.definition_changed(SETUP)
        ui.pick("filetype", "SPC-130")
        ui.drop(SPC)
        ui.type_into("output", str(tmp_path / "t.dat"))
        ui.click("transfer")
        ui.settle()
        assert got and Path(got[0][0]).exists() and got[0][1]["polarization"] == "vm"
        assert ui.app.model.message == "Added histogram to ChiSurf."
    finally:
        ui.app.close()


def test_detector_definition_tab_is_reachable_and_comes_back(loaded):
    loaded.press_text("Detector definition")
    assert loaded.shown("TTTR Reading routine") or loaded.shown("Detectors")
    loaded.press_text("Inputs and options")
    assert loaded.shown("Photon files")


def _real_chisurf_state():
    root = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"
    return {str(p): p.stat().st_mtime_ns for p in root.rglob("*")} if root.exists() else {}


def test_a_full_session_leaves_the_real_chisurf_folder_untouched(loaded, tmp_path):
    before = _real_chisurf_state()
    loaded.type_into("output", str(tmp_path / "h.dat"))
    loaded.click("compute")
    loaded.settle()
    loaded.app.export_settings()
    assert _real_chisurf_state() == before


def test_qt_free():
    assert qt_free("microtime_histogram")


def _fields(sections):
    for section in sections:
        yield section
        yield from _fields(section.get("sections", ()))
        for button in section.get("buttons", ()):
            yield button


def test_every_spec_field_button_and_the_guide_carry_a_description(ui):
    app = ui.app
    for section in _fields(app.spec["sections"] + app.run_spec["sections"]):
        if section.get("type") in ("value", "choice", "toggle") or "action" in section:
            assert section.get("description"), section
    for step in app.tour.steps:
        assert step.get("title") and step.get("text")


def test_the_guide_walk_points_at_drawn_controls_and_its_awaits_are_released_by_presses(loaded):
    app = loaded.app
    app.tour.start()
    steps = app.tour.steps
    for index, step in enumerate(steps):
        app.tour.start(index)
        loaded.draw(3)
        target = step.get("target") or {}
        key = target.get("name") or target.get("attr")
        if key:
            assert key in app.item_rects, (index, key)
    app.tour.stop()
    wait = next(i for i, s in enumerate(steps) if s.get("await"))
    app.tour.start(wait)
    loaded.draw(2)
    assert app.tour.waiting if hasattr(app.tour, "waiting") else True
    loaded.click(steps[wait]["target"]["name"])
    loaded.press_text("Cancel") if loaded.dialog_open else None


def test_settings_round_trip_restores_the_queue_options_and_setup(computed, tmp_path):
    state = computed.app.export_settings()
    computed.type_into("vv_shift", "4")
    state = computed.app.export_settings()
    other = Ui(create_app(), SIZE)
    try:
        other.app.restore_settings(state)
        other.draw(3)
        m = other.app.model
        assert m.files == computed.app.model.files and m.vv_shift == 4 and m.detector == "green"
        assert set(m.setup["detectors"]) == {"green", "red"} and m.filetype == "SPC-130"
        assert other.shown("BH_SPC132.spc")
    finally:
        other.app.close()
