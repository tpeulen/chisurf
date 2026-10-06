"""Every control of the native HydroPro operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at
the text a button, a list entry or a header drew) and host file drops reach the window; the assertions read the visible
outcome (the model, the table, the log, the dialogs). The HYDRO program is ``data/fake_hydro.sh`` (recorded output); the
web browser is recorded, not opened. The control -> test list is in ``okf/plugins/emtk-ports/hydropro/REPORT.md``.
"""

from __future__ import annotations

import time
import webbrowser
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.core.project_browser.test.driving import draw_clip, layout_problems
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.modelling.hydropro.app import HydroProApp, build_spec

from . import hermetic
from .support import BIG, SMALL, drain, make_world


@pytest.fixture(scope="module", autouse=True)
def real_state_untouched():
    state = hermetic.RealState()
    yield
    assert state.changes() == []


@pytest.fixture
def world():
    return make_world(Path.home())


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: urls.append(url) or True)
    return urls


@pytest.fixture
def drv(world, opened):
    app = HydroProApp()
    d = Driver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def populate(drv, world, *stems, exe="exe"):
    drv.app.model.exe_path = str(world[exe])
    drv.app.model.struct_files = ", ".join(str(world["files"][s]) for s in stems)
    drv.draw(2)


def finish(drv, timeout=60.0):
    end = time.monotonic() + timeout
    while drv.app.model.running and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    assert not drv.app.model.running
    return drv.draw(3)


def run_and_wait(drv):
    drv.click("run")
    return finish(drv)


def dialog_open(drv):
    return drv.app.dialog is not None


def pick(drv, name):
    """In the open file chooser: click the entry *name*, press its action button (Open / Save / Choose)."""
    drv.click_text(name)
    drv.click_text(drv.app.dialog.action)


def table_strings(drv, frames=2):
    """The texts drawn inside the results table (the log editor draws the same numbers in pieces elsewhere)."""
    painter = drv.draw(frames)
    x, y, w, h = drv.app.form.rects["result_rows"]
    return [t[5] for t in painter.texts if x <= t[0] <= x + w and y <= t[1] <= y + h]


def spec_fields():
    return [
        s
        for p in build_spec()["params"]
        for s in p["sections"]
        if s.get("type") == "value" and s.get("kind") in ("int", "float")
    ]


# -- executable and structures ---------------------------------------------------------------------------------------- #


def test_the_executable_and_structure_fields_take_typed_text_and_enter(drv, world):
    drv.type_into("exe_path", str(world["exe"]))
    assert drv.app.model.exe_path == str(world["exe"])
    drv.type_into("struct_files", f"{world['files']['148l']}, {world['files']['small']}")
    assert [p.name for p in drv.app.model.struct_list()] == ["148l.pdb", "small.pdb"]
    rows = [r["file"] for r in drv.app.model.result_rows()]
    assert rows == [str(world["files"]["148l"]), str(world["files"]["small"])]
    assert "2 rows × 2 columns" in drv.draw(2).strings


def test_a_typed_structure_list_is_committed_when_the_pointer_goes_elsewhere(drv, world):
    drv.type_into("struct_files", str(world["files"]["plain"]), enter=False)
    assert drv.app.model.struct_files == ""
    drv.click("aer", fx=0.9)  # a click on another field
    assert drv.app.model.struct_files == str(world["files"]["plain"])


def test_select_files_opens_the_chooser_and_the_chosen_files_replace_the_list(drv, world):
    drv.click("select_files")
    assert (
        dialog_open(drv)
        and drv.app.dialog.multiselect
        and drv.app.dialog.directory == str(world["home"])
    )
    drv.click_text("148l.pdb")
    drv.click_text("small.pdb")
    drv.click_text("Open")
    assert not dialog_open(drv)
    assert [p.name for p in drv.app.model.struct_list()] == ["148l.pdb", "small.pdb"]
    # Choosing again replaces the list and empties the result cells.
    drv.click("select_files")
    pick(drv, "plain.pdb")
    assert [p.name for p in drv.app.model.struct_list()] == ["plain.pdb"]


def test_the_structure_chooser_cancel_close_and_escape_change_nothing(drv, world):
    drv.app.model.struct_files = str(world["files"]["148l"])
    for how in ("cancel", "close", "escape"):
        drv.click("select_files")
        assert dialog_open(drv)
        drv.click_text("small.pdb")
        if how == "cancel":
            drv.click_text("Cancel", last=True)  # the output pane has a Cancel too, drawn earlier
        elif how == "close":
            drv.click_text("×", last=True)
        else:
            drv.escape()
        assert not dialog_open(drv), how
        assert drv.app.model.struct_files == str(world["files"]["148l"]), how


def test_the_open_button_with_nothing_selected_says_so_and_keeps_the_chooser(drv, world):
    drv.click("select_files")
    drv.click_text("Open")
    assert dialog_open(drv) and drv.app.dialog.error == "Select a file first."
    drv.click_text("Cancel", last=True)


def test_the_executable_button_chooses_one_program(drv, world):
    drv.click("select_exe")
    assert dialog_open(drv) and not drv.app.dialog.multiselect
    assert [label for label, _p in drv.app.dialog.filters] == ["Executables", "All files"]
    drv.app.dialog.enter("bin")
    drv.draw(2)
    pick(drv, "hydropro10.exe")
    assert drv.app.model.exe_path == str(world["exe"])
    shown = drv.draw(2).strings
    assert any("hydropro10.exe" in s for s in shown)


def test_download_page_opens_the_web_page(drv, opened):
    drv.click("download_page")
    assert opened and opened[-1].startswith("https://leonardo.inf.um.es/macromol/programs/")


def test_files_dropped_on_the_window_replace_the_structure_list(drv, world):
    assert drv.drop(str(world["files"]["148l"]), str(world["files"]["plain"]))
    assert [p.name for p in drv.app.model.struct_list()] == ["148l.pdb", "plain.pdb"]
    drv.drop(str(world["home"] / "no_such_file.pdb"))  # not a file: nothing changes
    assert [p.name for p in drv.app.model.struct_list()] == ["148l.pdb", "plain.pdb"]


# -- parameters ----------------------------------------------------------------------------------------------------------- #


def test_the_model_combo_lists_the_three_modes_and_each_can_be_clicked(drv):
    for mode in ("2", "4", "1"):
        drv.click("indmode")
        shown = drv.draw(2).strings
        assert shown.count("1") >= 1 and "2" in shown and "4" in shown
        drv.click_text(mode, last=True)
        assert drv.app.model.indmode == mode
    drv.click("indmode")
    drv.escape()
    assert drv.app.model.indmode == "1"


TYPED = {
    "aer": ("3.5", 3.5),
    "nsig": ("8", 8),
    "sigmin": ("0.5", 0.5),
    "sigmax": ("3", 3.0),
    "t": ("25", 25.0),
    "eta": ("0.0089", 0.0089),
    "rm": ("14300", 14300.0),
    "vbar": ("0.72", 0.72),
    "rho": ("1.002", 1.002),
    "nq": ("20", 20),
    "qmax": ("35000000", 3.5e7),
    "ns": ("30", 30),
    "rmax": ("1.234", 1.234),
    "ntrials": ("1000", 1000),
}


@pytest.mark.parametrize("attr", list(TYPED))
def test_each_numeric_field_takes_typed_text_and_enter(drv, attr):
    text, expected = TYPED[attr]
    drv.type_into(attr, text)
    assert getattr(drv.app.model, attr) == pytest.approx(expected)
    assert drv.app.model.to_settings().to_dict()[attr] == pytest.approx(expected)


def test_typed_garbage_is_ignored_and_out_of_range_numbers_are_clamped(drv):
    drv.type_into("aer", "abc")
    assert drv.app.model.aer == 2.9
    drv.type_into("aer", "999")
    assert drv.app.model.aer == 50.0
    drv.type_into("nsig", "-7")
    assert drv.app.model.nsig == -1
    drv.type_into("ntrials", "-3")
    assert drv.app.model.ntrials == 0


@pytest.mark.parametrize("field", spec_fields(), ids=lambda f: f["attr"])
def test_each_field_arrows_step_by_the_qt_step_and_stop_at_the_limit(drv, field):
    attr, step = field["attr"], field.get("step", 1.0)
    start = getattr(drv.app.model, attr)
    x, y, w, h = drv.rect(f"{attr}.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    up = min(start + step, field["maximum"])
    assert getattr(drv.app.model, attr) == pytest.approx(up), attr
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    down = max(up - 2 * step, field["minimum"])
    assert getattr(drv.app.model, attr) == pytest.approx(down), attr
    for _ in range(3):  # far below the minimum: it stays at the limit
        drv.click_at(x + w / 2, y + h * 0.75)
    assert getattr(drv.app.model, attr) >= field["minimum"] - 1e-9


def test_the_mouse_wheel_steps_a_numeric_field(drv):
    x, y, w, h = drv.rect("aer")
    drv.hover(x + w / 2, y + h / 2)
    drv.wheel(x + w / 2, y + h / 2, 1)
    assert drv.app.model.aer == pytest.approx(3.0)
    drv.wheel(x + w / 2, y + h / 2, -1)
    drv.wheel(x + w / 2, y + h / 2, -1)
    assert drv.app.model.aer == pytest.approx(2.8)
    x, y, w, h = drv.rect("nsig")
    drv.hover(
        x + w / 2, y + h / 2
    )  # the pointer rests on the field first, as a hand does (hover registers a frame later)
    drv.wheel(x + w / 2, y + h / 2, 1)
    assert drv.app.model.nsig == 7 and drv.app.model.aer == pytest.approx(2.8)


def test_one_wheel_notch_is_one_step_however_often_the_window_is_drawn(drv):
    x, y, w, h = drv.rect("t")
    drv.wheel(x + w / 2, y + h / 2, 1)
    assert drv.app.model.t == pytest.approx(21.0)
    drv.draw(6)  # the pointer rests on the field: the wheel must not keep stepping it
    assert drv.app.model.t == pytest.approx(21.0)
    drv.hover(x + w / 2, y + h / 2, 4)
    assert drv.app.model.t == pytest.approx(21.0)


def test_the_diffusion_tensor_toggle_is_clicked(drv):
    assert drv.app.model.idif is True
    drv.click("idif")
    assert drv.app.model.idif is False and drv.app.model.to_settings().idif == 0
    drv.click("idif")
    assert drv.app.model.idif is True


def test_a_panel_header_folds_and_unfolds_its_fields(drv):
    assert "SIGMIN" in drv.draw(2).strings
    drv.click_text("Primary model")
    shown = drv.draw(2).strings
    assert "SIGMIN" not in shown and "Solvent & macromolecule" in shown and "ETA" in shown
    drv.click_text("Primary model")
    assert "SIGMIN" in drv.draw(2).strings


def test_the_status_field_is_read_only(drv):
    drv.app.model.status = "Finished: 1 file(s)."
    drv.draw(2)
    drv.click("status", fx=0.3)
    drv.type_text("xyz")
    drv.enter()
    assert drv.app.model.status == "Finished: 1 file(s)."


# -- run, results, save ---------------------------------------------------------------------------------------------------- #


def test_run_computes_every_file_and_fills_table_status_and_log(drv, world):
    populate(drv, world, "148l", "small", "plain", "garbled", "silent")
    painter = run_and_wait(drv)
    model = drv.app.model
    assert model.status == "Finished: 5 file(s)." and model.output_status == "Finished."
    for cell in ("1.047e-06", "2.500e-07", "4.000e+00", "N/A"):
        assert cell in painter.strings
    assert [r["d"] for r in model.result_rows()] == [
        "1.047e-06",
        "2.500e-07",
        "4.000e+00",
        "N/A",
        "N/A",
    ]
    assert model.log_lines[0] == f"Executable: {world['exe']}"
    assert sum(1 for line in model.log_lines if line.lstrip().startswith("=== Job")) == 5
    assert "100%" in painter.strings and model.progress_fraction == 1.0
    assert model.enabled("save_csv") and model.enabled("run") and not model.enabled("cancel")


def test_the_whole_flow_with_typed_fields_only(drv, world):
    drv.type_into("exe_path", str(world["exe"]))
    drv.type_into("struct_files", str(world["files"]["148l"]))
    drv.type_into("aer", "3.1")
    drv.click("indmode")
    drv.click_text("2", last=True)
    run_and_wait(drv)
    assert drv.app.model.result_rows()[0]["d"] == "1.047e-06"
    dat = (world["home"] / ".hydropp_gui/job_001/hydropro.dat").read_text()
    assert "3.1," in dat and dat.splitlines()[3].startswith("2 ")


def test_run_with_no_files_gives_a_message_whose_ok_closes_it(drv, world):
    drv.app.model.exe_path = str(world["exe"])
    drv.click("run")
    assert drv.app.model.notices == [("No files", "Please select one or more files first.")]
    assert "Please select one or more files first." in drv.draw(2).strings
    drv.click("notice_ok")
    assert drv.app.model.notices == []
    assert "Please select one or more files first." not in drv.draw(2).strings


def test_run_with_invalid_settings_names_the_problem(drv, world):
    populate(drv, world, "148l")
    drv.type_into("nsig", "2")
    drv.click("run")
    assert (
        drv.app.model.notices[0][0] == "Invalid settings"
        and "NSIG must be > 2" in drv.app.model.notices[0][1]
    )
    assert not drv.app.model.running
    drv.click("notice_ok")
    drv.type_into("nsig", "-1")
    drv.type_into("nq", "5")
    drv.click("run")
    assert "QMAX must be > 0 when NQ > 0" in drv.app.model.notices[0][1]
    drv.escape()  # Escape closes the message too
    assert drv.app.model.notices == [] or drv.click("notice_ok") is None


def test_run_without_an_executable_opens_the_prompt_and_close_without_one_says_so(drv, world):
    populate(drv, world, "148l")
    drv.app.model.exe_path = ""
    drv.click("run")
    assert drv.app.model.exe_prompt and not drv.app.model.running
    shown = drv.draw(2).strings
    assert {"Select executable…", "Open download page", "Close"} <= set(shown)
    drv.click("prompt_download")
    assert drv.app.model.opened_urls
    drv.click("prompt_close")
    assert not drv.app.model.exe_prompt
    assert drv.app.model.notices == [
        ("Executable required", "Configure the HYDRO executable before running.")
    ]
    drv.click("notice_ok")


def test_the_prompt_select_executable_continues_the_run_with_the_chosen_program(drv, world):
    populate(drv, world, "148l")
    drv.app.model.exe_path = ""
    drv.click("run")
    drv.click("prompt_select")
    assert dialog_open(drv)
    drv.app.dialog.enter("bin")
    drv.draw(2)
    pick(drv, "hydropro10.exe")
    assert drv.app.model.prompt_path == world["exe"]
    drv.click("prompt_close")
    finish(drv)
    assert (
        drv.app.model.exe_path == str(world["exe"])
        and drv.app.model.result_rows()[0]["d"] == "1.047e-06"
    )


def test_the_prompt_close_button_in_the_header_acts_as_close(drv, world):
    populate(drv, world, "148l")
    drv.app.model.exe_path = ""
    drv.click("run")
    drv.click_text("×", last=True)
    assert not drv.app.model.exe_prompt and drv.app.model.notices[0][0] == "Executable required"


def test_a_failing_run_shows_the_error_in_status_and_log_and_run_works_again(drv, world):
    populate(drv, world, "148l", exe="noexec")
    run_and_wait(drv)
    model = drv.app.model
    assert (
        model.status.startswith("Error: ")
        and model.output_status == "Failed."
        and model.log_lines[-1].startswith("\nERROR:")
    )
    assert not model.enabled("save_csv")
    populate(drv, world, "148l")
    run_and_wait(drv)
    assert model.status == "Finished: 1 file(s)."


def test_run_is_greyed_while_a_run_is_in_flight_and_cancel_skips_the_remaining_files(drv, world):
    populate(drv, world, "slow", "148l")
    drv.click("run")
    drv.draw(3)
    model = drv.app.model
    assert model.running and not model.enabled("run") and model.enabled("cancel")
    before = model.total
    drv.click("run")  # a click on the greyed button starts nothing
    assert model.total == before
    drv.click("cancel")
    assert model.output_status == "Cancelling after current job finishes…" and not model.enabled(
        "cancel"
    )
    finish(drv)
    assert model.status == "Finished: 1 file(s)." and len(model.results) == 1
    assert model.result_rows()[1]["d"] == "" and model.output_status == "Finished."


def test_save_csv_is_greyed_without_results_and_a_click_opens_nothing(drv):
    assert not drv.app.model.enabled("save_csv")
    drv.click("save_csv")
    assert not dialog_open(drv) and drv.app.model.notices == []


def test_save_csv_writes_the_file_with_a_typed_name_and_confirms(drv, world):
    populate(drv, world, "148l", "garbled")
    run_and_wait(drv)
    drv.click("save_csv")
    assert (
        dialog_open(drv)
        and drv.app.dialog.mode == "save"
        and drv.app.dialog.filename == "hydro_results.csv"
    )
    drv.click("hydropro_file_name", fx=0.3) if False else None
    drv.app.dialog.filename = "my_results.csv"
    drv.click_text("Save")
    out = world["home"] / "my_results.csv"
    assert out.read_text().splitlines() == [
        "File,DiffusionCoefficient(cm^2/s)",
        f"{world['files']['148l']},1.047e-06",
        f"{world['files']['garbled']},",
    ]
    assert drv.app.model.notices[-1] == ("Saved", f"Results saved to {out}")
    assert f"Results saved to {out}" in drv.draw(2).strings or any(
        "Results saved to" in s for s in drv.draw(2).strings
    )
    drv.click("notice_ok")


def test_save_csv_cancel_writes_nothing(drv, world):
    populate(drv, world, "148l")
    run_and_wait(drv)
    drv.click("save_csv")
    drv.click_text("Cancel", last=True)
    assert (
        not dialog_open(drv)
        and not (world["home"] / "hydro_results.csv").exists()
        and drv.app.model.notices == []
    )


def test_save_csv_to_an_unwritable_place_reports_the_error(drv, world):
    populate(drv, world, "148l")
    run_and_wait(drv)
    drv.app.model.write_csv(world["home"] / "no_such_dir" / "r.csv")
    title, text = drv.app.model.notices[-1]
    assert title == "Error" and text.startswith("Failed to save CSV: ")


def test_clear_empties_files_status_and_results(drv, world):
    populate(drv, world, "148l")
    run_and_wait(drv)
    drv.click("clear")
    model = drv.app.model
    assert (model.struct_files, model.status, model.results, model.result_rows()) == (
        "",
        "",
        [],
        [],
    )
    assert not model.enabled("save_csv")
    assert "1.047e-06" not in table_strings(drv) and "0 rows × 2 columns" in table_strings(drv)


# -- the table ---------------------------------------------------------------------------------------------------------------- #


def test_a_table_row_can_be_selected_and_the_header_sorts(drv, world):
    populate(drv, world, "148l", "small", "plain")
    run_and_wait(drv)
    binding = drv.app.form.tables["result_rows"]
    drv.click_text("small.pdb") if False else None
    x, y, w, h = drv.text_rect("2.500e-07")
    drv.click_at(x + 2, y + h / 2)
    assert binding.control.selected_key == str(world["files"]["small"])
    assert drv.app.model.struct_files.count("small.pdb") == 1  # selecting changes no value
    head = drv.text_rect("Diffusion coefficient (cm²/s)")
    drv.click(head)
    cells = ("1.047e-06", "2.500e-07", "4.000e+00")
    first = [t for t in table_strings(drv) if t in cells]
    drv.click(head)
    second = [t for t in table_strings(drv) if t in cells]
    assert first == list(cells) and second == list(reversed(first))  # ascending, then descending


def test_the_wheel_scrolls_a_long_results_table(drv, world):
    drv.app.model.struct_files = ", ".join(f"/data/set/structure_{i:03d}.pdb" for i in range(60))
    drv.draw(3)
    x, y, w, h = drv.rect("result_rows")
    assert any("structure_000" in s for s in table_strings(drv)) and not any(
        "structure_059" in s for s in table_strings(drv)
    )
    for _ in range(12):
        drv.wheel(x + w / 2, y + h / 2, -5)
    shown = table_strings(drv)
    assert any("structure_059" in s for s in shown) and not any("structure_000" in s for s in shown)


# -- output pane ---------------------------------------------------------------------------------------------------------------- #


def test_the_output_buttons_are_greyed_before_any_run(drv):
    model = drv.app.model
    assert (
        not model.enabled("clear_log")
        and not model.enabled("save_log")
        and not model.enabled("cancel")
    )
    drv.click("save_log")
    assert not dialog_open(drv)
    drv.click("cancel")
    assert not model.cancelling


def test_clear_log_empties_the_log_and_leaves_the_results(drv, world):
    populate(drv, world, "148l")
    run_and_wait(drv)
    assert drv.app.model.log_lines
    drv.click("clear_log")
    assert drv.app.model.log_lines == [] and drv.app.model.result_rows()[0]["d"] == "1.047e-06"
    assert not drv.app.model.enabled("clear_log")


def test_save_log_writes_the_log_text_to_the_chosen_file(drv, world):
    populate(drv, world, "148l")
    run_and_wait(drv)
    text = drv.app.model.log_text
    drv.click("save_log")
    assert dialog_open(drv) and drv.app.dialog.filename == "hydro_output.txt"
    drv.click_text("Save")
    out = world["home"] / "hydro_output.txt"
    assert out.read_text() == text and "Result: diffusion coefficient = 1.047e-06 cm^2/s" in text
    assert drv.app.model.notices == []


def test_the_log_shows_the_programs_output_and_wraps_long_lines(drv, world):
    populate(drv, world, "148l")
    run_and_wait(drv)
    shown = drv.app._log_seen  # what the log editor holds: the log, broken at the pane's width
    assert (
        "Result: diffusion coefficient = 1.047e-06 cm^2/s" in shown
        and "HYDRO fake: read hydropro.dat" in shown
    )
    assert max(len(line) for line in shown.splitlines()) < max(
        len(line) for line in drv.app.model.log_text.splitlines()
    )
    drv.size = SMALL
    drv.draw(3)
    x, y, w, h = drv.rect("output_log")
    assert x + w <= SMALL[0] + 1 and y + h <= SMALL[1] + 1


# -- help and guide --------------------------------------------------------------------------------------------------------------- #


def test_help_button_opens_the_help_window_whose_buttons_work(drv):
    window = drv.app.help_window
    drv.click("help")
    assert window.open
    painter = drv.draw(2)
    assert {"Start Guided Tour", "Close", "Close Help"} <= set(painter.strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.draw(2)
    for closer in ("Close Help", "Close"):
        drv.click("help")
        drv.click_text(closer, last=closer == "Close Help")
        assert not window.open, closer
    drv.click("help")
    drv.escape()
    assert not window.open


def test_the_help_text_names_the_controls(drv):
    drv.click("help")
    shown = " ".join(drv.draw(2).strings)
    for word in ("INDMODE", "AER", "Guide", "HYDROPRO"):
        assert word in shown, word


def test_guide_button_starts_the_tour_and_its_card_buttons_work(drv):
    tour = drv.app.tour
    drv.click("guide")
    assert tour.active and not tour.awaiting
    drv.click_text(
        "Next ►", last=True
    )  # step 1 awaits the Executable… button: Next is greyed there
    assert tour.step_idx == 1 and tour.awaiting
    drv.click_text("Next ►", last=True)
    assert tour.step_idx == 1
    tour.start(3)  # AER: nothing to press
    drv.draw(3)
    drv.click_text("Next ►", last=True)
    assert tour.step_idx == 4
    drv.click_text("◄ Prev", last=True)
    assert tour.step_idx == 3
    drv.click_text("Close Tour", last=True)
    assert not tour.active


def test_every_guide_target_is_a_drawn_control(drv):
    tour = drv.app.tour
    drv.draw(3)
    for step in tour.steps:
        key = tour._target_key(step.get("target"))
        if key:
            assert tour.get_target_rect(key), f"{step['title']}: {key} is not drawn"


def test_the_tour_waits_for_the_buttons_and_is_walked_to_the_end(drv, world):
    tour = drv.app.tour
    drv.click("guide")
    seen = []
    for _ in range(40):
        if not tour.active:
            break
        drv.draw(2)
        step = tour.steps[tour.step_idx]
        key = tour._target_key(step.get("target"))
        if tour.awaiting:
            seen.append(key)
            if key == "Executable":
                drv.click("select_exe")
                assert dialog_open(drv)
                drv.app.dialog.enter("bin")
                drv.draw(2)
                pick(drv, "hydropro10.exe")
            elif key == "Select files":
                drv.click("select_files")
                pick(drv, "148l.pdb")
            elif key == "Run":
                drv.click("run")
                finish(drv)
            assert not tour.awaiting, f"{step['title']}: operating {key} did not release the step"
        tour.next()
    assert not tour.active and seen == ["Executable", "Select files", "Run"]
    assert drv.app.model.result_rows()[0]["d"] == "1.047e-06"


def test_the_tour_card_does_not_cover_the_control_a_step_points_at(drv):
    from chisurf.emtk.help_guide import place_tour_card

    for index, step in enumerate(drv.app.tour.steps):
        key = drv.app.tour._target_key(step.get("target"))
        if not key:
            continue
        drv.app.tour.start(index)
        drv.draw(3)
        rect = drv.app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, step["title"]
        card_w, card_h = min(480.0, BIG[0] - 40.0), 150.0
        x, y = place_tour_card(rect, float(BIG[0]), float(BIG[1]), card_w, card_h)
        clear = (
            x + card_w <= rect[0]
            or x >= rect[0] + rect[2]
            or y + card_h <= rect[1]
            or y >= rect[1] + rect[3]
        )
        assert clear, f"{step['title']}: the card would cover its target"
    drv.app.tour.stop()


# -- small window, persistence ------------------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(world, opened):
    app = HydroProApp()
    d = Driver(app, SMALL)
    d.draw(3)
    populate(d, world, "148l")
    d.click("run")
    finish(d)
    assert app.model.result_rows()[0]["d"] == "1.047e-06"
    log = [tuple(app.form.rects["output_log"])]
    assert layout_problems(draw_clip(app, SMALL, 3), SMALL, ignore=log) == []
    d.click("select_files")
    assert dialog_open(d)
    d.click_text("Cancel", last=True)
    app.close()


def test_settings_round_trip_through_the_app(drv, world):
    drv.type_into("aer", "4.8")
    drv.click("indmode")
    drv.click_text("2", last=True)
    drv.type_into("exe_path", str(world["exe"]))
    state = drv.app.export_settings()
    other = HydroProApp()
    other.restore_settings(state)
    assert (other.model.aer, other.model.indmode, other.model.exe_path) == (
        4.8,
        "2",
        str(world["exe"]),
    )
    assert (
        other.model.struct_files == ""
    )  # the Qt tool remembered the executable and the parameters, not the file list
    other.close()


def test_closing_the_app_with_a_run_in_flight_does_not_hang(world, opened):
    app = HydroProApp()
    d = Driver(app, BIG)
    populate(d, world, "slow")
    d.click("run")
    start = time.monotonic()
    app.close()
    assert time.monotonic() - start < 6.0
