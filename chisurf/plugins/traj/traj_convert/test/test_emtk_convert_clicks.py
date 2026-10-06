"""Click coverage of the native trajectory converter: every control is operated with pointer, keys and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see
``traj_save_topology/test/real_input.py``); the assertions read what is drawn, the model's fields and the files written.
The control -> test list is in ``okf/plugins/emtk-ports/traj_convert/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest
from chisurf.plugins.traj.traj_convert.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import (
    Ui,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_number_field,
    check_row_is_read_only,
    check_text_field,
    clear_field,
    dead_tour_buttons,
    read_xyz,
    wheel_steps_a_number_field,
)
from emtk import keys

SIZE = (800, 700)  # both panels fit: the Output panel's controls must be reachable


def _ui(**kw):
    return Ui(make_app(), SIZE)


def test_guide_and_help_buttons_are_pressed():
    check_guide_and_help_buttons(make_app, size=SIZE, prev_step=5, close_step=5)


def test_no_tour_card_button_is_dead_on_any_step():
    assert dead_tour_buttons(make_app, SIZE) == []


def test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works(
    small_trajectory, monkeypatch
):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(
        make_app,
        "trajectory",
        small_trajectory / "small.dcd",
        small_trajectory / "topol.pdb",
        small_trajectory,
        "Open trajectory",
        size=SIZE,
    )


def test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works(
    small_trajectory, monkeypatch
):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(
        make_app,
        "topology",
        small_trajectory / "topol.pdb",
        small_trajectory / "small.dcd",
        small_trajectory,
        "Open PDB-File",
        model_attr="topology_path",
        size=SIZE,
    )


@pytest.mark.parametrize("row", ["topology", "trajectory", "target"])
def test_the_path_rows_do_not_take_typing(row, small_trajectory):
    check_row_is_read_only(make_app, row, small_trajectory, size=SIZE)


def test_the_target_folder_dialog_lists_folders_only_and_chooses_the_selected_or_the_shown_one(
    small_trajectory, monkeypatch
):
    monkeypatch.chdir(small_trajectory)
    ui = _ui()
    try:
        ui.click("target_browse")
        assert ui.dialog_open and ui.shown("Choose Target-Folder") and ui.shown("[sub]")
        assert not ui.shown("small.dcd") and not ui.shown("topol.pdb")  # folder mode lists no files
        ui.press_text("Choose")  # nothing selected: the shown folder
        assert not ui.dialog_open and ui.app.model.target_directory == str(small_trajectory)
        ui.click("target_browse")
        ui.press_text("[sub]")
        assert ui.app.dialog.selection == ["sub"]
        ui.press_text("Choose")
        assert ui.app.model.target_directory == str(small_trajectory / "sub")
        ui.click("target_browse")  # starts in the chosen folder
        assert ui.app.dialog.directory == str(small_trajectory / "sub")
        ui.press_text("[..]")
        assert ui.app.dialog.directory == str(small_trajectory)
        ui.press_text("Cancel")
        assert ui.app.model.target_directory == str(small_trajectory / "sub")
        ui.click("target_browse")
        ui.press_text("×")
        assert not ui.dialog_open
    finally:
        ui.app.close()


def test_the_folder_checkbox_turns_the_trajectory_row_into_a_folder_chooser(
    small_trajectory, monkeypatch
):
    monkeypatch.chdir(small_trajectory)
    ui = _ui()
    try:
        ui.click("use_folder")
        assert ui.app.model.use_folder is True
        ui.click("trajectory_browse")
        assert ui.app.dialog.mode == "folder" and ui.shown("[sub]") and not ui.shown("small.dcd")
        ui.press_text("[sub]")
        ui.press_text("Choose")
        assert ui.app.model.trajectory == str(small_trajectory / "sub")
        ui.click("use_folder")
        assert ui.app.model.use_folder is False
        ui.click("trajectory_browse")
        assert ui.app.dialog.mode == "open" and ui.shown("small.dcd")
    finally:
        ui.app.close()


def test_dropped_files_and_folders_fill_the_rows_by_type_and_a_foreign_file_is_answered(
    small_trajectory,
):
    ui = _ui()
    try:
        assert ui.drop(small_trajectory / "notes.txt") is True
        assert ui.shown("No topology or trajectory or target folder file among the dropped paths.")
        ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")
        assert ui.app.model.trajectory == str(small_trajectory / "small.dcd")
        assert ui.app.model.topology_path == str(small_trajectory / "topol.pdb")
        ui.drop(small_trajectory / "sub")  # a folder: the target folder row
        assert ui.app.model.target_directory == str(small_trajectory / "sub")
        ui.click("use_folder")
        ui.drop(small_trajectory)  # in folder mode the folder row first
        assert ui.app.model.trajectory == str(small_trajectory)
    finally:
        ui.app.close()


@pytest.mark.parametrize(
    "key, start, typed, minimum, maximum",
    [
        ("first_frame", 0, 3, 0, 99999999),
        ("last_frame", -1, 5, -1, 9999999),
        ("stride", 1, 4, 1, 99999),
    ],
)
def test_each_frame_range_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows(
    key, start, typed, minimum, maximum
):
    check_number_field(
        make_app,
        key,
        start=start,
        typed=typed,
        minimum=minimum,
        maximum=maximum,
        step=1,
        as_type=int,
        size=SIZE,
    )


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel does not reach a field inside a DockManager window "
    "(repro in the report); the Qt spin box steps on the wheel",
)
@pytest.mark.parametrize("key", ["first_frame", "last_frame", "stride"])
def test_the_wheel_steps_a_number_field(key):
    before, after = wheel_steps_a_number_field(make_app, key, size=SIZE)
    assert after != before


def test_the_filename_field_is_typed_and_a_click_away_commits():
    check_text_field(make_app, "filename", start="out", typed="frames", size=SIZE)


def test_the_format_combo_lists_both_formats_and_each_is_clicked():
    ui = _ui()
    try:
        assert ui.app.model.ending == ".dcd" and ui.shown(".dcd")
        ui.click("ending")
        assert ui.shown(".dcd") and ui.shown(".pdb")
        ui.press_text(".pdb")
        assert ui.app.model.ending == ".pdb"
        ui.click("ending")
        ui.press_text(".dcd")
        assert ui.app.model.ending == ".dcd"
        ui.click("ending")  # Escape closes the list, no choice
        ui.key(keys.KEY_ESCAPE, "")
        assert ui.app.model.ending == ".dcd"
    finally:
        ui.app.close()


def test_the_split_checkbox_is_clicked_on_and_off():
    ui = _ui()
    try:
        assert ui.app.model.split is False
        ui.click("split")
        assert ui.app.model.split is True
        ui.click("split")
        assert ui.app.model.split is False
    finally:
        ui.app.close()


def test_the_panel_headers_fold_and_unfold_their_controls():
    ui = _ui()
    try:
        assert ui.shown("First frame") and ui.shown("Filename")
        ui.click("Input.fold")
        assert not ui.shown("First frame") and ui.shown("Filename")
        ui.click("Output.fold")
        assert not ui.shown("Filename")
        ui.click("Input.fold")
        ui.click("Output.fold")
        assert ui.shown("First frame") and ui.shown("Filename")
    finally:
        ui.app.close()


def test_convert_says_what_is_missing_before_it_runs(small_trajectory):
    ui = _ui()
    try:
        ui.click("convert")
        assert ui.shown("Choose a trajectory first.") and not ui.app.running
        ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")
        ui.click("convert")
        assert ui.shown("Choose a target folder first.") and not ui.app.running
    finally:
        ui.app.close()


def _prepare(ui, small_trajectory, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb", out)
    return out


def test_converting_a_range_through_the_ui_writes_those_frames_and_says_done(
    small_trajectory, tmp_path
):
    top = small_trajectory / "topol.pdb"
    source = read_xyz(small_trajectory / "small.dcd", top)
    ui = _ui()
    try:
        out = _prepare(ui, small_trajectory, tmp_path)
        ui.type_into("first_frame", "1")
        ui.type_into("last_frame", "6")
        ui.type_into("stride", "2")
        ui.type_into("filename", "frames")
        ui.click("convert")
        ui.settle()
        assert ui.shown("Conversion done!") and ui.shown("Wrote 3 frames of 5235 atoms")
        np.testing.assert_allclose(
            read_xyz(out / "frames.dcd", top), source[[1, 3, 5]], atol=1e-3
        )  # 6 not reached
        assert ui.app.status == ""
    finally:
        ui.app.close()


def test_last_frame_minus_one_reaches_the_end_and_the_format_combo_writes_a_multi_model_pdb(
    small_trajectory, tmp_path
):
    top = small_trajectory / "topol.pdb"
    source = read_xyz(small_trajectory / "small.dcd", top)
    ui = _ui()
    try:
        out = _prepare(ui, small_trajectory, tmp_path)
        ui.type_into("first_frame", "6")
        ui.click("ending")
        ui.press_text(".pdb")
        ui.type_into("filename", "tail")
        ui.click("convert")
        ui.settle()
        text = (out / "tail.pdb").read_text()
        models = [b for b in text.split("ENDMDL") if "ATOM" in b or "HETATM" in b]
        assert len(models) == 2  # frames 6 and 7
        xyz = np.array(
            [
                [
                    [float(line[30:38]), float(line[38:46]), float(line[46:54])]
                    for line in block.splitlines()
                    if line.startswith(("ATOM", "HETATM"))
                ]
                for block in models
            ]
        )
        np.testing.assert_allclose(xyz, source[[6, 7]], atol=1e-3)
    finally:
        ui.app.close()


def test_split_writes_one_file_per_selected_frame_named_by_its_source_frame(
    small_trajectory, tmp_path
):
    ui = _ui()
    try:
        out = _prepare(ui, small_trajectory, tmp_path)
        ui.click("split")
        ui.click("ending")
        ui.press_text(".pdb")
        ui.type_into("stride", "3")
        ui.type_into("filename", "f")
        ui.click("convert")
        ui.settle()
        assert sorted(p.name for p in out.glob("f_*.pdb")) == [f"f_{i:08d}.pdb" for i in (0, 3, 6)]
        assert ui.shown("Conversion done!")
    finally:
        ui.app.close()


def test_a_range_that_selects_nothing_is_reported_in_the_window_and_writes_nothing(
    small_trajectory, tmp_path
):
    ui = _ui()
    try:
        out = _prepare(ui, small_trajectory, tmp_path)
        ui.type_into("first_frame", "5")
        ui.type_into("last_frame", "2")
        ui.click("convert")
        ui.settle()
        assert (
            ui.app.status == "Conversion failed: The frame range selects no frames."
            and ui.shown(ui.app.status)
        )
        assert not list(out.iterdir())
        ui.type_into("last_frame", "-1")  # fixing the field and running again works
        ui.click("convert")
        ui.settle()
        assert ui.shown("Conversion done!") and ui.app.status == "" and (out / "out.dcd").exists()
    finally:
        ui.app.close()


def test_a_folder_of_pdbs_is_converted_as_consecutive_frames(small_trajectory, tmp_path):
    from chisurf.core.structure import trajectory_data as md

    top = small_trajectory / "topol.pdb"
    source = read_xyz(small_trajectory / "small.dcd", top)
    folder = tmp_path / "pdbs"
    folder.mkdir()
    trajectory = md.load(str(small_trajectory / "small.dcd"), top=str(top))
    for name, index in (("a.pdb", 1), ("b.pdb", 4), ("c.pdb", 7)):
        trajectory[index].save_pdb(str(folder / name))
    out = tmp_path / "out"
    out.mkdir()
    ui = _ui()
    try:
        ui.click("use_folder")
        ui.drop(folder, out)
        assert ui.app.model.trajectory == str(folder) and ui.app.model.target_directory == str(out)
        ui.type_into("filename", "joined")
        ui.click("convert")
        ui.settle()
        assert ui.shown("Read 3 files as 3 frames")
        np.testing.assert_allclose(read_xyz(out / "joined.dcd", top), source[[1, 4, 7]], atol=1e-3)
    finally:
        ui.app.close()


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app, size=SIZE)
    assert scrolled_down < at_start  # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down  # a turn the other way brings them back


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: a text field keeps the keyboard after a click on a checkbox or a "
    "button elsewhere (repro in the report); a Qt line edit loses its focus",
)
def test_a_text_field_gives_up_the_keyboard_when_a_checkbox_elsewhere_is_clicked():
    ui = _ui()
    try:
        ui.click("filename", fx=0.3)
        assert ui.app.io.want_capture_keyboard
        ui.click("split")
        assert ui.app.model.split is True
        assert not ui.app.io.want_capture_keyboard
    finally:
        ui.app.close()
