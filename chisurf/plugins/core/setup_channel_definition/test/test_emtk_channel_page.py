"""The one-page channel editor driven with REAL INPUT: pointer press and release at drawn rectangles, typed text, Enter,
the wheel, drags and file drops. Every control of the page has a test here (the control -> test list is in
``okf/plugins/emtk-ports/channel_editor/REPORT.md``).

Hermetic: setups files and MMFDB are temporary, the working directory of the file chooser is a temporary folder holding a
copy of ``test/data/tttr/BH/132/BH_SPC132.spc``. The numeric parity of the page against the Qt page (the same setup, the
same typed texts) is in the second half.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.setup_channel_definition.test import driver
from chisurf.plugins.core.setup_channel_definition.test.driver import DATA, norm
from chisurf.plugins.tttr.tttr_count_rate_analysis.tests.pointer import KEY_BACKSPACE, Pointer

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SAMPLE = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
SIZES = [(1200, 800), (800, 600), (720, 600)]


# --------------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "unused.sqlite"))
    yield
    from chisurf.core.fio.lut_context import clear_active_setup_lut

    clear_active_setup_lut()


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """The file chooser's folder: the sample measurement and a LUT table, nothing else."""
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(SAMPLE, work / "BH_SPC132.spc")
    np.save(work / "channel.npy", np.linspace(0.0, 4095.0, 4096))
    monkeypatch.chdir(work)
    return work


@pytest.fixture
def make(tmp_path):
    """Build the tool on a temporary setups file; closes every tool it built."""
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    built = []

    def build(size=(1200, 800), settings=DATA, **kwargs):
        app = make_app(settings=settings, file_path=str(tmp_path / "setups.json"), **kwargs)
        built.append(app)
        return app, Pointer(app, (float(size[0]), float(size[1])))

    yield build
    for app in built:
        app.close()


@pytest.fixture
def ui(make):
    return make()[1]


def app_of(ui):
    return ui.app


def det(ui, name="green"):
    return ui.app.model.data["detectors"][name]


def cell_point(ui, table, row_id, key):
    """Where the cell (*row_id*, *key*) of a table is drawn (from the table's own geometry of the last frame)."""
    binding = {"detectors": ui.app.page._detector_table, "windows": ui.app.page._window_table, "luts": ui.app.page._lut_table}[table]
    control = binding.control
    index = next(i for i, record in enumerate(control.records) if record["id"] == row_id)
    position = control.order().index(index)
    bx, by, bw, bh = control._body_box
    y = by + (position - control.bar.top + 0.5) * control._row_h
    x = control._header_box[0]
    for column, width in zip(control._shown, control._widths):
        if column.key == key:
            return (x + width / 2.0, y)
        x += width
    raise AssertionError(f"column {key} is not drawn")


def clear(ui, count=24):
    """Empty the focused text field: the caret to the end, then Backspace."""
    from emtk.keys import KEY_END

    ui.key(KEY_END)
    for _ in range(count):
        ui.key(KEY_BACKSPACE)


def edit(ui, table, row_id, key, new, finish="enter"):
    """Double-click a table cell, replace its text with *new*, and finish with Enter or a click elsewhere."""
    ui.double_click(cell_point(ui, table, row_id, key))
    clear(ui)
    ui.type(new)
    if finish == "enter":
        ui.enter()
    else:
        ui.click("TTTR Reading Routine:")  # a click elsewhere commits what was typed


def press_button(ui, table, row_id, key):
    """Click the button drawn in a table cell."""
    return ui.click(cell_point(ui, table, row_id, key))


def read_sample(ui):
    """Read the sample through the chooser by pointer clicks, and wait for the read."""
    ui.click("Read")
    ui.click("BH_SPC132.spc")
    ui.click("Open")
    driver.finish_read(ui.app)
    ui.frame(2)


# ============================================================================================ 1. the Setup row
def test_setup_combo_lists_the_saved_setups_and_choosing_one_loads_it(make):
    app, ui = make()
    app.toolbar.save("Lab A")
    app.toolbar.select("")
    app.model.data["detectors"].pop("red")
    ui.frame(2)
    ui.click("Unsaved")  # the list has the blank entry and the saved setup
    assert ui.drawn("Lab A")
    ui.click("Lab A", nth=-1)
    assert app.toolbar.selected == "Lab A" and set(app.model.data["detectors"]) == {"green", "red"}
    assert json.loads(Path(app.model.file_path).read_text())["last_used"] == "Lab A"


def test_save_button_opens_the_prompt_and_a_typed_name_stores_the_setup(make):
    app, ui = make()
    ui.click("Save")
    assert app.toolbar.dialog == "save" and ui.drawn("Enter a name for this setup:")
    ui.click("Save", nth=-1)  # empty name: nothing is stored
    assert not (Path(app.model.file_path)).exists()
    ui.click("Save")
    ui.press(ui.painter.texts[[t[5] for t in ui.painter.texts].index("Enter a name for this setup:")][:2])  # focus stays in the window
    page = app.page
    field = page.item_rects["name_prompt"]
    ui.click((field[0] + 20, field[1] + field[3] / 2))
    clear(ui)
    ui.type("Typed")
    ui.click("Save", nth=-1)
    assert app.toolbar.selected == "Typed"
    stored = json.loads(Path(app.model.file_path).read_text())
    assert list(stored["setups"]) == ["Typed"] and stored["last_used"] == "Typed"
    assert app.toolbar.dialog == ""


def test_rename_and_delete_buttons_ask_first_and_keep_setup_declines(make):
    app, ui = make()
    app.toolbar.save("One")
    ui.click("Rename")
    assert app.toolbar.dialog == "rename"
    ui.click("Cancel")
    assert app.toolbar.selected == "One" and app.toolbar.dialog == ""
    ui.click("Delete")
    assert app.toolbar.dialog == "delete" and ui.drawn("Are you sure you want to delete the setup 'One'?")
    ui.click("Keep setup")
    assert app.toolbar.selected == "One"
    ui.click("Delete")
    ui.click("Delete", nth=-1)  # the prompt's own button
    assert app.toolbar.selected == "" and json.loads(Path(app.model.file_path).read_text())["setups"] == {}


def test_rename_button_renames_through_the_typed_prompt(make):
    app, ui = make()
    app.toolbar.save("One")
    ui.click("Rename")
    field = app.page.item_rects["name_prompt"]
    ui.click((field[0] + 20, field[1] + field[3] / 2))
    clear(ui)
    ui.type("Two")
    ui.click("Rename", nth=-1)
    assert app.toolbar.selected == "Two" and list(json.loads(Path(app.model.file_path).read_text())["setups"]) == ["Two"]


def test_public_checkbox_is_inert_until_a_setup_is_saved_and_then_toggles(make):
    app, ui = make()
    ui.click("Public")
    assert app.page.public is False  # nothing saved: the check box is disabled
    app.toolbar.save("Mine")
    ui.frame(2)
    ui.click("Public")
    assert app.page.public is True
    ui.click("Public")
    assert app.page.public is False


def test_calibration_combo_lists_latest_and_the_snapshots(make):
    app, ui = make()
    app.page.calibrations = ["2026-09-01T10:00:00"]
    ui.frame(2)
    ui.click("Latest")
    assert ui.drawn("2026-09-01T10:00:00")
    ui.click("2026-09-01T10:00:00", nth=-1)
    assert app.page.calibration == "2026-09-01T10:00:00"


def test_question_mark_opens_the_help_and_the_close_button_closes_it(ui):
    ui.click("?")
    assert ui.app.page.help_window.open and ui.drawn("Help - Detector Setup")
    assert any("micro-time units" in s or "IMPORTANT" in s for s in ui.strings)
    x, y, w, h = ui.app.page.help_window.box
    ui.click((x + w - 14, y + 13))  # the window's close button
    assert not ui.app.page.help_window.open


def test_guide_and_help_buttons_of_the_host_strip(ui):
    ui.click("Help")
    assert ui.app.help_window.open
    ui.app.help_window.hide()
    ui.click("Guide")
    assert ui.app.tour.active


# ===================================================================================== 2. TTTR reading routine
def test_section_headers_fold_and_unfold_and_the_state_is_remembered(make):
    app, ui = make()
    assert ui.drawn("▼ TTTR Reading routine") and ui.drawn("File Type:") and not ui.drawn("Window Name")
    ui.click("▼ TTTR Reading routine")
    assert not ui.drawn("File Type:") and ui.drawn("▶ TTTR Reading routine")
    ui.click("▶ PIE Windows")  # PIE Windows is folded at first
    assert ui.drawn("Window Name") and ui.drawn("prompt")
    state = json.loads(json.dumps(app.export_settings()))
    assert state["page"]["sections"] == {"reading": False, "windows": True, "detectors": True, "lut": True}
    other, other_ui = make()
    other.restore_settings(state)
    other_ui.frame(3)
    assert not other_ui.drawn("File Type:") and other_ui.drawn("Window Name")
    ui.click("▼ LUT handling (TAC linearization)")
    assert not ui.drawn("Assign LUT...")


def test_file_type_combo_lists_every_format_of_the_qt_page_and_a_pick_sets_it(make):
    import tttrlib

    app, ui = make()
    ui.click("SPC-130")
    listed = set(ui.strings)
    assert {"Auto", *tttrlib.TTTR.get_supported_container_names()} <= listed
    assert {"CZ-RAW", "SM", "PHOTONS", "PHOTON-HDF5", "SPC-QC", "SPC-600_4096", "BRIGHTEYES-TTR", "FLIMLABS-STT1", "FLIMLABS-ITT1"} <= listed
    ui.click("CZ-RAW")
    assert app.model.data["tttr_reading"]["file_type"] == "CZ-RAW" and ui.drawn("CZ-RAW")
    ui.click("CZ-RAW")
    ui.click("Auto")
    assert app.model.data["tttr_reading"]["file_type"] == "Auto"


def test_read_button_chooses_a_file_by_clicks_and_takes_the_timing_from_it(make, folder):
    app, ui = make()
    ui.click("Read")
    assert app.page.dialog is not None and ui.drawn("BH_SPC132.spc") and ui.drawn("Open")
    ui.click("Cancel")  # declining reads nothing
    assert app.page.dialog is None and app.model.data["tttr_reading"]["macro_time_resolution"] == 13.5 and not app.model.preview
    read_sample(ui)
    assert app.model.data["tttr_reading"]["micro_time_resolution"] == pytest.approx(3.2958984375)
    assert sorted(app.model.preview) == [0, 1, 8, 9]
    assert ui.drawn("3.2958984375")  # the field shows the new timing


def test_a_bad_file_read_raises_like_qt_and_keeps_the_timing(make, folder):
    (folder / "bad.ptu").write_text("this is not photon data")
    app, ui = make()
    before = dict(app.model.data["tttr_reading"])
    ui.click("Read")
    ui.click("bad.ptu")
    ui.click("Open")
    driver.finish_read(app)
    ui.frame(2)
    assert app.page.status.startswith("Error:") and app.model.data["tttr_reading"] == before
    assert any(s.startswith("Error:") for s in ui.strings)


@pytest.mark.parametrize("key,label,typed,expect", [
    ("macro_time_resolution", "13.5", "20", 20.0),
    ("micro_time_resolution", "3.25", "4.5", 4.5),
])
def test_timing_fields_take_typed_numbers_and_a_typo_leaves_the_value(make, key, label, typed, expect):
    app, ui = make()
    reading = app.model.data["tttr_reading"]
    rect = lambda: app.page.item_rects[key]  # noqa: E731
    x, y, w, h = rect()
    ui.click((x + 10, y + h / 2))
    clear(ui)
    last_valid = reading[key]  # every valid prefix applied live, as Qt's textChanged does
    ui.type("x")  # not a number: the model keeps the last valid value and the field shows what was typed
    assert reading[key] == last_valid and ui.drawn("x")
    clear(ui)
    ui.type(typed)
    ui.enter()
    assert reading[key] == expect and ui.drawn(typed)


def test_binning_combo_and_the_effective_microtime(make):
    app, ui = make()
    assert ui.drawn("6.500000")  # 3.25 ps * 2
    ui.click("2")
    ui.click("8", nth=-1)
    assert app.model.data["tttr_reading"]["micro_time_binning"] == 8 and ui.drawn("26.000000")


def test_the_effective_microtime_field_is_read_only(make):
    app, ui = make()
    x, y, w, h = app.page.item_rects["effective"]
    ui.click((x + 10, y + h / 2))
    ui.type("99")
    assert ui.drawn("6.500000") and app.model.data["tttr_reading"]["micro_time_resolution"] == 3.25


def test_plot_button_opens_the_decay_preview_and_dragging_a_gate_moves_the_range(make, folder):
    app, ui = make()
    read_sample(ui)
    ui.click("Plot")
    window = app.page.preview_window
    assert window.open and ui.drawn("Micro-time Decay Preview") and ui.drawn("Routing 9")
    assert det(ui, "red")["micro_time_ranges"] == [[0, 2048]]
    # drag the PIE window "delayed" start line (x = 2048, a vertical line through the plot)
    bx, by, bw, bh = window.box
    inside = [t for t in ui.painter.texts if bx <= t[0] <= bx + bw and by <= t[1] <= by + bh]
    left = [t for t in inside if t[5] == "0"][-1]  # the window is drawn last: its tick labels are the last ones
    right = [t for t in inside if t[5] == "4000"][-1]
    x0, x4000 = left[0] + left[2] / 2, right[0] + right[2] / 2
    x_of = lambda v: x0 + (x4000 - x0) * v / 4000.0  # noqa: E731
    ax_y = left[1] - 120  # inside the plot, above the tick labels
    ui.drag((x_of(2048), ax_y), (x_of(1500), ax_y))
    low, high = det(ui, "red")["micro_time_ranges"][0]  # the line grabbed at 2048 is the end of the red gate (and the PIE windows' edge)
    assert low == 0 and 1400 < high < 1600, (low, high)
    ui.frame(2)
    ui.click("▶ PIE Windows") if not app.page.open_sections["windows"] else None
    assert any(s == f"0:{high}" for s in ui.strings)  # the table shows the dragged gate
    ui.click("Plot")
    assert not window.open


# ========================================================================================== 3. PIE windows table
def test_pie_windows_start_folded_and_add_edit_and_delete_by_pointer(make):
    app, ui = make()
    ui.click("▶ PIE Windows")
    ui.click("Add", nth=0)  # the PIE Windows one: it is the first section with a table drawn
    assert "New Window" in app.model.data["windows"] and app.model.data["windows"]["New Window"] == [0, 2048]
    ui.click("Add", nth=0)
    assert "New Window 1" in app.model.data["windows"]
    edit(ui, "windows", "New Window", "name", "late")  # rename with Enter
    assert "late" in app.model.data["windows"] and list(app.model.data["windows"])[2] == "late"  # keeps its place
    edit(ui, "windows", "late", "start", "3000", finish="away")  # click-away commits
    assert app.model.data["windows"]["late"][0] == 3000
    edit(ui, "windows", "prompt", "start", "abc")  # not a whole number: refused, value stays
    assert app.model.data["windows"]["prompt"][0] == 0 and app.page.status.startswith("Error:")
    press_button(ui, "windows", "prompt", "delete")
    assert "prompt" not in app.model.data["windows"]


# ======================================================================================== 4. detectors table
def test_polarization_resolved_checkbox_toggles_the_flag(make):
    app, ui = make()
    assert app.model.data["polarization_resolved"] is True
    ui.click("Polarization resolved")
    assert app.model.data["polarization_resolved"] is False
    ui.click("Polarization resolved")
    assert app.model.data["polarization_resolved"] is True


def test_add_button_appends_a_detector_with_the_qt_defaults_and_names_stay_unique(make):
    app, ui = make()
    ui.click("Add", nth=0)
    assert app.model.data["detectors"]["New Detector"] == {"chs": [0, 1], "micro_time_ranges": [[0, 2048]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
    ui.click("Add", nth=0)
    assert "New Detector 1" in app.model.data["detectors"]
    assert "prompt_New Detector" in app.model.get_settings()["channels"]


@pytest.mark.parametrize("typed,expected", [
    ("20:10", [[10, 20]]), ("5:5", [[5, 5]]), ("0:10;20:30", [[0, 10], [20, 30]]), ("10-20", [[10, 20]]), ("7", [[7, 7]]),
    ("a:b, 3:4", [[3, 4]]), ("", []),
])
def test_micro_time_range_cell_is_typed_and_read_with_the_qt_rules(make, typed, expected):
    app, ui = make()
    edit(ui, "detectors", "green", "ranges", typed)
    assert det(ui)["micro_time_ranges"] == expected


def test_every_detector_cell_is_edited_by_typing_with_enter_or_click_away(make):
    app, ui = make()
    edit(ui, "detectors", "green", "name", "donor")
    assert list(app.model.data["detectors"]) == ["donor", "red"]
    edit(ui, "detectors", "donor", "chs", "4; 5", finish="away")
    assert det(ui, "donor")["chs"] == [4, 5]
    edit(ui, "detectors", "donor", "g", "2.5")
    assert det(ui, "donor")["g_factor"] == 2.5 and ui.drawn("2.500")
    edit(ui, "detectors", "donor", "l1", "0.07")
    assert det(ui, "donor")["l1"] == 0.07
    edit(ui, "detectors", "donor", "l2", "-0.03")
    assert det(ui, "donor")["l2"] == -0.03
    edit(ui, "detectors", "donor", "gch", "300:400")  # start-end; ':' is accepted too
    assert det(ui, "donor")["g_factor_channels"] == [300, 400] and ui.drawn("300:400")  # the cell keeps what was typed, as Qt
    edit(ui, "detectors", "donor", "gch", "none")
    assert "g_factor_channels" not in det(ui, "donor")


def test_an_empty_g_factor_is_one_and_a_typo_reverts_like_qt(make):
    app, ui = make()
    edit(ui, "detectors", "red", "g", "")
    assert det(ui, "red")["g_factor"] == 1.0 and ui.drawn("1.000")
    edit(ui, "detectors", "red", "g", "oops")
    assert det(ui, "red")["g_factor"] == 1.0 and app.page.status.startswith("Error:")
    edit(ui, "detectors", "red", "l1", "x")
    assert det(ui, "red")["l1"] == 0.01 and app.page.status.startswith("Error:")


def test_a_detector_name_that_exists_is_refused(make):
    app, ui = make()
    edit(ui, "detectors", "green", "name", "red")
    assert list(app.model.data["detectors"]) == ["green", "red"] and app.page.status.startswith("Error:")


def test_calc_g_and_delete_buttons_act_on_their_own_row(make, folder):
    app, ui = make()
    press_button(ui, "detectors", "green", "calc")  # nothing read yet
    assert app.page.status.startswith("Error:")
    read_sample(ui)
    app.model.data["detectors"]["green"]["g_factor_channels"] = [1000, 3000]
    app.page._refresh_rows()
    ui.frame(2)
    press_button(ui, "detectors", "green", "calc")
    assert app.page.status == "Settings updated." and det(ui)["g_factor"] != 1.0 and det(ui, "red")["g_factor"] == 1.25
    press_button(ui, "detectors", "red", "delete")
    assert list(app.model.data["detectors"]) == ["green"]
    press_button(ui, "detectors", "green", "delete")
    assert app.model.data["detectors"] == {} and "prompt_green" not in app.model.get_settings()["channels"]


def test_the_wheel_scrolls_a_long_detector_table(make):
    app, ui = make()
    for i in range(12):
        app.model.data["detectors"][f"d{i}"] = {"chs": [i], "micro_time_ranges": [[0, 10]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
    app.page._refresh_rows()
    ui.frame(3)
    assert ui.drawn("green") and not ui.drawn("d11")
    ui.wheel("green", -6)
    assert not ui.drawn("green") or ui.drawn("d5")
    ui.wheel("d5", 20)
    assert ui.drawn("green")


# ============================================================================================ 5. LUT handling
def test_apply_checkbox_offers_the_lut_calculator_for_channels_without_a_lut(make):
    app, ui = make()
    ui.click("Apply TAC linearization (LUT) when reading")
    assert app.model.data["apply_lut"] is True and ui.drawn("Missing LUTs")
    assert any("Open the LUT calculator to compute one now?" in s for s in ui.strings)
    ui.click("No")
    assert not app.page.question_window.open and not app.page.lut_window.open
    ui.click("Apply TAC linearization (LUT) when reading")
    assert app.model.data["apply_lut"] is False
    ui.click("Apply TAC linearization (LUT) when reading")
    ui.click("Yes")
    assert app.page.lut_window.open and ui.drawn("TTTR LUT Tools")


def test_shift_cell_is_typed_and_a_row_is_selected_by_a_click(make):
    app, ui = make()
    edit(ui, "luts", "9", "shift", "5")
    assert app.model.data["channel_shifts"] == {"9": 5}
    from chisurf.core.fio.lut_context import get_active_setup_lut

    assert {int(k): int(v) for k, v in get_active_setup_lut()[1].items()} == {9: 5}
    ui.click("— none —", nth=1)
    assert app.page.selected_channel == 1


def test_assign_lut_button_needs_a_row_then_assigns_the_chosen_file_and_switches_the_gate_on(make, folder):
    app, ui = make()
    ui.click("Assign LUT...")
    assert "select a channel row first" in app.page.status and app.page.dialog is None
    ui.click("— none —", nth=2)  # channel 2
    ui.click("Assign LUT...")
    assert app.page.dialog is not None
    ui.click("channel.npy")
    ui.click("Open")
    assert "2" in app.model.data["channel_luts"] and len(app.model.data["channel_luts"]["2"]) == 4096
    assert app.model.data["apply_lut"] is True and app.model.data["channel_lut_sources"]["2"] == "channel.npy"
    assert ui.drawn("channel.npy")  # the LUT column names the file


def test_configure_luts_window_computes_exports_and_removes_a_lut(make, folder):
    app, ui = make()
    ui.click("Configure LUTs...")
    assert app.page.lut_window.open and ui.drawn("Routing channel:") and ui.drawn("Linear region start")
    ui.click("Compute TAC LUT")
    assert app.page.status.startswith("Error:")  # no measurement yet
    read_sample(ui)
    x, y, w, h = app.page.lut_window.content_box
    ui.click((x + 150, y + 12))  # the channel combo; channel 8 has a plateau the automatic region finds
    ui.click("8", nth=-1)
    assert app.page.selected_channel == 8
    ui.click("Auto-detect TAC LUT")
    ui.frame(2)
    driver.finish_read(app)
    channel = str(app.page.selected_channel)
    assert channel in app.model.data["channel_luts"] and app.model.data["apply_lut"] is True
    ui.click("Export channel LUT")
    ui.click("Cancel")
    ui.click("Compute TAC LUT")
    driver.finish_read(app)
    assert channel in app.model.data["channel_luts"]
    ui.click("Remove channel LUT")
    driver.finish_read(app)
    assert channel not in app.model.data["channel_luts"]
    ui.click("Assign LUT file")
    assert app.page.dialog is not None
    ui.click("Cancel")


def test_configure_luts_channel_combo_and_region_fields(make):
    app, ui = make()
    ui.click("Configure LUTs...")
    assert app.page.selected_channel == 0
    window = app.page.lut_window
    x, y, w, h = window.content_box
    ui.click((x + 150, y + 12))  # the channel combo
    ui.click("8", nth=-1)
    assert app.page.selected_channel == 8
    start = [t for t in ui.painter.texts if t[5] == "Linear region start"][0]
    ui.click((start[0] - 60, start[1] + start[3] / 2))  # the field is left of its caption
    clear(ui)
    ui.type("123")
    ui.enter()
    assert app.page.lut_start == 123


def test_adjust_shifts_needs_a_calibration_then_shifts_channels_and_ok_or_cancel(make, folder):
    app, ui = make()
    ui.click("Adjust shifts...")
    assert "read a calibration" in app.page.status and not app.page.shift_window.open
    read_sample(ui)
    ui.click("Adjust shifts...")
    assert app.page.shift_window.open and ui.drawn("ch 8") and ui.drawn("Adjust micro-time shifts")
    ch8 = [t for t in ui.painter.texts if t[5] == "ch 8"][0]
    ui.click((ch8[0] + 80, ch8[1] + ch8[3] / 2))  # the shift field of channel 8
    clear(ui)
    ui.type("12")
    ui.enter()
    assert app.page._shift_draft.get(8) == 12 and app.model.data["channel_shifts"] == {}  # nothing applied before OK
    ui.click("Cancel", nth=-1)
    assert not app.page.shift_window.open and app.model.data["channel_shifts"] == {}
    ui.click("Adjust shifts...")
    ch8 = [t for t in ui.painter.texts if t[5] == "ch 8"][0]
    ui.click((ch8[0] + 80, ch8[1] + ch8[3] / 2))
    clear(ui)
    ui.type("7")
    ui.enter()
    ui.click("OK")
    driver.finish_read(app)
    assert app.model.data["channel_shifts"] == {"8": 7} and not app.page.shift_window.open


# ===================================================================================== 6. optical setup, drops
def test_optical_setup_button_opens_the_light_path_editor_and_the_close_button_closes_it(make):
    app, ui = make()
    ui.click("Optical Setup...")
    assert app.page.optical_window.open and ui.drawn("Open advanced graph editor")
    x, y, w, h = app.page.optical_window.box
    ui.click((x + w - 14, y + 13))
    assert not app.page.optical_window.open


def test_dropping_a_measurement_reads_it_and_a_json_file_becomes_the_setups_library(make, folder, tmp_path):
    from emtk.app import ControlSurface

    app, ui = make()
    surface = ControlSurface(app)
    assert surface.on_files_dropped([str(folder / "BH_SPC132.spc")]) is True
    driver.finish_read(app)
    ui.frame(2)
    assert sorted(app.model.preview) == [0, 1, 8, 9]
    library = tmp_path / "library.json"
    library.write_text(json.dumps({"setups": {"From file": {"windows": {"w": [0, 10]}, "detectors": {"d": {"chs": [0], "micro_time_ranges": [[0, 10]]}}}}, "last_used": "From file"}))
    assert surface.on_files_dropped([str(library)]) is True
    ui.frame(2)
    assert str(app.model.file_path) == str(library) and app.toolbar.names == ["From file"]
    app.page.status = ""
    surface.on_files_dropped([])  # nothing dropped: nothing happens
    assert app.page.status == ""


def test_dropping_a_lut_table_assigns_it_to_the_selected_row(make, folder):
    from emtk.app import ControlSurface

    app, ui = make()
    surface = ControlSurface(app)
    surface.on_files_dropped([str(folder / "channel.npy")])
    assert "select a channel row first" in app.page.status
    ui.click("— none —", nth=3)
    surface.on_files_dropped([str(folder / "channel.npy")])
    assert "3" in app.model.data["channel_luts"] and app.model.data["apply_lut"] is True


def test_the_wheel_scrolls_the_page_when_the_window_is_too_short(make):
    app, ui = make(size=(800, 400))
    top = ui.where("Setup:")[1]
    bottom = ui.where("Optical Setup...")[1]
    assert bottom > 400  # the Optical Setup button is below the window's lower edge
    ui.wheel("Setup:", -5)  # the wheel over a label scrolls the page down by 40 px a notch
    assert ui.where("Setup:")[1] == pytest.approx(top - 200.0)
    ui.wheel("Polarization resolved", -5)  # over what is visible now: down to the end of the page
    assert ui.where("Optical Setup...")[1] < 400 and ui.drawn("0 setups available.")
    ui.wheel("0 setups available.", 20)  # and back up to the top, over the status line at the end
    assert ui.where("Setup:")[1] == top


# ============================================================================================ 7. tooltips, layout
def _rects(app):
    return {k: v for k, v in app.page.item_rects.items() if v and v[2] > 0 and v[3] > 0}


@pytest.mark.parametrize("size", SIZES)
def test_every_control_of_the_page_has_a_tooltip(make, folder, size):
    from test.gui.emtk_port_parity import emtk_inventory

    app, ui = make(size)
    app.page.open_sections["windows"] = True
    driver.populate(app, folder / "BH_SPC132.spc")
    ui.frame(3)
    inventory = emtk_inventory(app, size)
    assert inventory["interactive"]
    assert inventory["controls_without_tooltip"] == []
    for table in (app.page._detector_table, app.page._window_table, app.page._lut_table):
        for column in table.control.columns:
            assert column.tooltip, column.key


@pytest.mark.parametrize("size", SIZES + [(520, 500)])
def test_no_control_overlaps_another_or_leaves_the_window_and_the_label_column_is_aligned(make, folder, size):
    app, ui = make(size)
    app.page.open_sections["windows"] = True
    driver.populate(app, folder / "BH_SPC132.spc")
    ui.frame(4)
    rects = _rects(app)
    names = sorted(rects)
    for name in names:
        x, y, w, h = rects[name]
        assert x >= -1 and x + w <= size[0] + 1, (name, rects[name], size)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ra, rb = rects[a], rects[b]
            overlap = min(ra[0] + ra[2], rb[0] + rb[2]) - max(ra[0], rb[0]), min(ra[1] + ra[3], rb[1] + rb[3]) - max(ra[1], rb[1])
            assert not (overlap[0] > 1 and overlap[1] > 1), (a, b, ra, rb)
    # the labels of the reading grid share one x, so do their fields
    texts = {t[5]: t for t in ui.painter.texts}
    if size[0] >= 720:
        left = [texts[label][0] for label in ("File Type:", "Macrotime res. (ns):", "Microtime binning:")]
        assert max(left) - min(left) < 1.0, left
        fields = [rects[k][0] for k in ("file_type", "macro_time_resolution", "binning")]
        assert max(fields) - min(fields) < 1.0, fields
        right = [texts[label][0] for label in ("Microtime res. (ps):", "Eff. microtime (ps):")]
        assert abs(right[0] - right[1]) < 1.0
        assert abs(rects["micro_time_resolution"][0] - rects["effective"][0]) < 1.0


@pytest.mark.parametrize("size", SIZES)
def test_fields_are_capped_not_stretched_across_the_window(make, size):
    app, ui = make(size)
    rects = _rects(app)
    for key in ("macro_time_resolution", "micro_time_resolution", "binning", "effective"):
        assert rects[key][2] <= 130.0, (key, rects[key])
    assert rects["file_type"][2] <= 220.0
    assert rects["setup_choice"][2] <= 260.0 and rects["calibration"][2] <= 250.0


@pytest.mark.parametrize("size", SIZES)
def test_the_page_fits_the_width_and_the_setup_row_wraps_instead_of_clipping(make, size):
    app, ui = make(size)
    for t in ui.painter.texts:
        assert t[0] + t[2] <= size[0] + 1, (t[5], t[:4])
    labels = ("Setup:", "Save", "Rename", "Delete", "Public", "Calibration:", "?")
    texts = {}
    for t in reversed(ui.painter.texts):  # the first drawn of a caption (the table has Delete buttons too)
        texts[t[5]] = t
    for label in labels:
        assert label in texts
    if size[0] >= 1200:
        assert len({round(texts[label][1]) for label in ("Save", "Rename", "Delete", "?")}) == 1  # one row


# ============================================================================== 8. numeric parity against the Qt page
@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def qt_page(qapp, tmp_path, monkeypatch):
    from chisurf.gui import dialogs
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod
    from chisurf.plugins.core.setup_channel_definition.gui.tool import SetupChannelDefinitionWidget

    file = tmp_path / "qt_setups.json"
    file.write_text('{"setups": {}}')
    monkeypatch.setattr(mod, "DETECTOR_SETUPS_FILE", file)
    for kind in ("information", "warning", "error"):
        monkeypatch.setattr(dialogs, kind, lambda *a, **k: None)
    widget = SetupChannelDefinitionWidget()
    widget.page._load_data(DATA)
    yield widget.page
    widget.close()


def _qt_cell(page, name, column):
    rows = {page.detectors_form.item(r, 0).text(): r for r in range(page.detectors_form.rowCount())}
    return page.detectors_form.cellWidget(rows[name], column)


def test_every_cell_text_gives_the_same_detector_as_the_qt_table(make, qt_page):
    """The same texts typed into the Qt cells and into the emtk table end in the same stored detector."""
    app, ui = make()
    page = qt_page
    page._allow_g_update = True
    typed = [
        ("green", 1, "9;1;2", "chs"), ("green", 2, "20:10", "ranges"), ("red", 2, "5:5", "ranges"), ("red", 2, "0:10;20:30", "ranges"),
        ("green", 3, "2.5", "g"), ("red", 4, "0.125", "l1"), ("red", 5, "-0.25", "l2"), ("green", 6, "100-200", "gch"),
        ("green", 1, "", "chs"), ("green", 1, "a,b", "chs"), ("red", 2, "7, 9:3, x, 12-14", "ranges"),
    ]
    for name, column, text, key in typed:
        cell = _qt_cell(page, name, column)
        cell.setText(text)
        cell.editingFinished.emit()
        record = next(r for r in app.page.detector_rows() if r["id"] == name)
        app.page.edit_detector(record, key, text)
        qt_settings = page.get_settings()["detectors"][name]
        mine = app.model.data["detectors"][name]
        assert mine["chs"] == qt_settings["chs"], (name, key, text)
        assert mine["micro_time_ranges"] == [list(r) for r in qt_settings["micro_time_ranges"]], (name, key, text)
        assert mine["g_factor"] == pytest.approx(qt_settings["g_factor"])
        assert mine["l1"] == pytest.approx(qt_settings["l1"]) and mine["l2"] == pytest.approx(qt_settings["l2"])
        assert mine.get("g_factor_channels") == qt_settings.get("g_factor_channels")


def test_window_start_and_end_texts_give_the_same_windows_as_the_qt_table(make, qt_page):
    app, ui = make()
    page = qt_page
    rows = {page.windows_form.item(r, 0).text(): r for r in range(page.windows_form.rowCount())}
    for name, column, text, key in (("prompt", 1, "10", "start"), ("prompt", 2, "300", "end"), ("delayed", 1, "2100", "start")):
        page.windows_form.cellWidget(rows[name], column).setText(text)
        record = next(r for r in app.page.window_rows() if r["id"] == name)
        app.page.edit_window(record, key, text)
    assert {k: list(v) for k, v in page.get_settings()["windows"].items()} == app.model.data["windows"]


def test_qt_and_emtk_offer_the_same_file_types_and_binnings(make, qt_page):
    from chisurf.emtk.channel_definition import BINNINGS, FILE_TYPES

    assert [qt_page.file_type_combo.itemText(i) for i in range(qt_page.file_type_combo.count())] == list(FILE_TYPES)
    assert [qt_page.micro_binning_combo.itemText(i) for i in range(qt_page.micro_binning_combo.count())] == list(BINNINGS)


def test_every_label_button_header_and_check_box_of_the_qt_page_is_on_the_emtk_page(make, qt_page):
    """Data-driven inventory: each text the Qt page shows is drawn by the emtk page (section open, a measurement read)."""
    from qtpy import QtWidgets

    app, ui = make()
    app.page.open_sections["windows"] = True
    ui.frame(3)
    drawn = " | ".join(ui.strings).replace("...", "…")
    drawn_cells = set(ui.strings)
    qt_texts = set()
    for cls in (QtWidgets.QPushButton, QtWidgets.QToolButton, QtWidgets.QCheckBox, QtWidgets.QLabel):
        for widget in qt_page.findChildren(cls):
            text = widget.text().strip()
            if text and widget.isVisibleTo(qt_page) or text and cls is not QtWidgets.QLabel:
                qt_texts.add(text)
    for table in (qt_page.detectors_form, qt_page.windows_form, qt_page._lut_table):
        for i in range(table.columnCount()):
            item = table.horizontalHeaderItem(i)
            if item and item.text().strip():
                qt_texts.add(item.text().strip())
    # glyph prefixes (pictograms) and the colon of a label are not part of the name; the three that are deliberate
    deliberate = {"Edit JSON": "hidden in Qt itself", "Save": "the Setup row's Save", "…": "empty", "": "empty"}
    missing = []
    for text in sorted(qt_texts):
        import re

        name = re.sub(r"^[^\w]+", "", text.replace("...", "…")).strip().rstrip(":").strip()
        if not name or name in ("Edit JSON", "Calculate G-Factor", "Load setups file", "Setups file"):
            continue
        if name in drawn or name.lower() in drawn.lower() or any(name.rstrip("s") in cell for cell in drawn_cells):
            continue
        missing.append(text)
    assert missing == [], missing


# ================================================================ 9. last used setup, remembered state, bad file
def test_the_last_used_setup_is_written_on_choice_and_opened_at_start_like_qt(make, qt_page, tmp_path, monkeypatch):
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    # Qt: save two setups, choose one: the file names it as last used
    qt_file = Path(mod.DETECTOR_SETUPS_FILE)
    qt_page.current_setups_file = str(qt_file)
    mod.QInputDialog.getText = staticmethod(lambda *a, **k: ("A", True))
    qt_page._on_save_setup()
    mod.QInputDialog.getText = staticmethod(lambda *a, **k: ("B", True))
    qt_page._on_save_setup()
    qt_page.setup_combo.setCurrentText("A")
    assert json.loads(qt_file.read_text())["last_used"] == "A"
    # emtk: the same by pointer clicks on the combo
    app, ui = make()
    app.toolbar.save("A")
    app.toolbar.save("B")
    app.toolbar.select("")
    ui.frame(2)
    ui.click("Unsaved")
    ui.click("A", nth=-1)
    stored = json.loads(Path(app.model.file_path).read_text())
    assert stored["last_used"] == "A" and set(stored["setups"]) == {"A", "B"}
    # a tool started without a definition opens it (the Qt page does), and one given a definition does not
    fresh = make_app(file_path=str(app.model.file_path))
    try:
        assert fresh.model.current_name == ""
        Pointer(fresh, (1200.0, 800.0))  # the first frame lists the setups and opens the last used one
        assert fresh.model.current_name == "A" and fresh.toolbar.selected == "A"
    finally:
        fresh.close()
    given = make_app(settings=DATA, file_path=str(app.model.file_path))
    try:
        Pointer(given, (1200.0, 800.0))
        assert given.model.current_name == ""
    finally:
        given.close()


def test_the_last_used_setup_is_remembered_in_the_mmfdb_too(tmp_path):
    from mmfdb.repository import MFDatabase

    from chisurf.core.fio import setup_store
    from chisurf.core.setup_channel_definition import ChannelDefinition

    db = MFDatabase(str(tmp_path / "m.sqlite"))
    db.ensure_user(setup_store.resolve_active_user_id())
    db.conn.commit()
    model = ChannelDefinition(DATA, db=db)
    model.save_setup("One")
    model.save_setup("Two")
    model.remember_last_used("One")
    other = ChannelDefinition(db=db)
    other.refresh_setups()
    assert other.last_used == "One" and other.open_last_used() == "One" and other.current_name == "One"
    assert other.data["detectors"]["red"]["g_factor"] == 1.25


def test_which_sections_are_open_survives_a_restart_of_the_tool(make):
    app, ui = make()
    ui.click("▼ Detectors")
    ui.click("▶ PIE Windows")
    saved = json.loads(json.dumps(app.export_settings()))
    other, other_ui = make()
    other.restore_settings(saved)
    other_ui.frame(3)
    assert other.page.open_sections == {"reading": True, "windows": True, "detectors": False, "lut": True}
    assert other_ui.drawn("▶ Detectors") and other_ui.drawn("▼ PIE Windows")
    other.restore_settings({"page": {"sections": {"reading": "yes", "nonsense": 1}}})
    assert other.page.open_sections["reading"] is True
    other.restore_settings({"page": "garbage"})  # wrong types are ignored


def test_the_embedding_hosts_state_round_trips_with_a_closed_plot(make, folder):
    app, ui = make()
    read_sample(ui)
    ui.click("Plot")
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved["page"]["plot"] is True
    other, other_ui = make()
    other.restore_settings(saved)
    other_ui.frame(2)
    assert other.page.preview_window.open


# ======================================================================================= 10. guide, help, window
def test_guide_steps_point_at_controls_that_exist_and_ask_the_user_to_act(make):
    app, ui = make()
    app.toolbar.request_save()
    ui.frame(2)  # the prompt's buttons exist only while it is open
    steps = json.loads((HERE.parent / "gui" / "guide.json").read_text())["steps"]
    for step in steps:
        target = step.get("target")
        if target:
            assert app.item_rects.get(target["name"]), target
    assert sum(bool(step.get("await")) for step in steps) >= 2 and len(steps) >= 6


def test_the_guide_waits_for_the_save_button_and_a_press_advances_it(make):
    app, ui = make()
    app.tour.start(2)  # the "Save under a name" step awaits the Save button
    ui.frame(3)
    assert app.tour.awaiting
    ui.click("Save", nth=0)
    assert not app.tour.awaiting and app.toolbar.dialog == "save"


def test_help_text_names_the_sections_and_the_controls_of_the_page():
    text = (HERE.parent / "gui" / "help.md").read_text()
    for word in ("TTTR Reading routine", "PIE Windows", "Detectors", "LUT handling", "Optical Setup...", "Calc G", "Assign LUT...", "Configure LUTs...", "Adjust shifts...", "start:end"):
        assert word in text, word
    assert "six tabs" not in text and "tab" not in text.lower().replace("table", "")


def test_the_window_has_the_plugins_name_as_its_title(ui):
    assert "Setup: Channel Definition" in ui.strings
    assert json.loads((HERE.parent / "manifest.json").read_text())["display_name"] == "Setup:Channel Definition"


# ================================================================ 11. narrow hosts: the table's buttons and columns
@pytest.mark.parametrize("width", [344, 400, 470, 520, 720, 1200])
def test_the_detector_table_buttons_never_overlap_or_clip_in_a_narrow_host(make, width):
    app, ui = make((width, 700))
    control = app.page._detector_table.control
    assert control._body_box is not None
    shown = {column.key: w for column, w in zip(control._shown, control._widths)}
    for key, w in shown.items():
        assert w >= 20.0, (key, w)  # the table drops columns before it squeezes them
    compact = app.page._compact
    assert compact == (width < 540)
    if "calc" in shown and "delete" in shown:
        assert (control.value(0, "calc"), control.value(0, "delete")) == (("G", "Del") if compact else ("Calc G", "Delete"))
        for column, cw in zip(control._shown, control._widths):
            if column.key in ("calc", "delete"):
                assert cw >= len(str(control.value(0, column.key))) * 6.0 + 8.0, (width, column.key, cw)
    assert (width >= 700) == ("gch" in shown) and (width >= 600) == ("l1" in shown)
    if width >= 470:  # the delete button of the second row still works at the narrow end
        press_button(ui, "detectors", "red", "delete")
        assert list(app.model.data["detectors"]) == ["green"]
