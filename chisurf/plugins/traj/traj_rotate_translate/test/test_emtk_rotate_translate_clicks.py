"""Click coverage of the native Rotate/Translate-Trajectory tool: every control is operated with pointer, keys and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see
``traj_save_topology/test/real_input.py``); the assertions read what is drawn, the model's fields and the moved file.
The control -> test list is in ``okf/plugins/emtk-ports/traj_rotate_translate/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.traj.traj_rotate_translate.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import (  # noqa: F401  (hermetic is autouse)
    Ui,
    check_action_flow,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_number_field,
    check_row_is_read_only,
    hermetic,
    read_xyz,
    dead_tour_buttons,
    small_trajectory,
    wheel_steps_a_number_field,
)


def test_guide_and_help_buttons_are_pressed():
    check_guide_and_help_buttons(make_app)


def test_no_tour_card_button_is_dead_on_any_step():
    assert dead_tour_buttons(make_app) == []


def test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works(small_trajectory, monkeypatch):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(make_app, "trajectory", small_trajectory / "small.dcd", small_trajectory / "topol.pdb",
                     small_trajectory, "Open trajectory")


def test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works(small_trajectory, monkeypatch):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(make_app, "topology", small_trajectory / "topol.pdb", small_trajectory / "small.dcd",
                     small_trajectory, "Open topology")


@pytest.mark.parametrize("row", ["trajectory", "topology"])
def test_the_path_rows_do_not_take_typing(row, small_trajectory):
    check_row_is_read_only(make_app, row, small_trajectory)


def test_dropped_files_fill_the_rows_by_type_and_a_foreign_file_is_answered(small_trajectory):
    ui = Ui(make_app())
    try:
        assert ui.drop(small_trajectory / "notes.txt") is True
        assert ui.shown("No trajectory or topology file among the dropped paths.")
        ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")
        assert ui.app.model.trajectory_filename == str(small_trajectory / "small.dcd")
        assert ui.app.model.topology_filename == str(small_trajectory / "topol.pdb")
        assert not ui.shown("No trajectory or topology")
    finally:
        ui.app.close()



def cell(ui, block, index):
    """The drawn rectangle of one matrix (``rotation_matrix``, 3x3) or translation (``translation``, 1x3) editor."""
    x, y, w, h = ui.app.item_rects[block]
    rows = 3 if block == "rotation_matrix" else 1
    i, j = divmod(index, 3)
    return (x + j * w / 3, y + i * h / rows, w / 3, h / rows)


def type_cell(ui, block, index, text):
    ui.draw(1)
    ui.click(cell(ui, block, index), fx=0.3)
    assert ui.app.io.want_capture_keyboard
    ui.type_text(text)
    ui.key(keys.KEY_RETURN, "\r")


def test_the_stride_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows():
    check_number_field(make_app, "stride", start=1, typed=5, minimum=1, maximum=999999, step=1, as_type=int)


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel does not reach a field inside a DockManager window "
                                       "(repro in the report); the Qt spin box steps on the wheel")
def test_the_wheel_steps_the_stride_field():
    before, after = wheel_steps_a_number_field(make_app, "stride")
    assert after != before


def test_every_matrix_and_translation_cell_takes_a_typed_number_on_enter():
    ui = Ui(make_app())
    try:
        for block in ("rotation_matrix", "translation"):
            n = 9 if block == "rotation_matrix" else 3
            for index in range(n):
                value = 0.5 + index                              # a number no cell starts with
                type_cell(ui, block, index, str(value))
                got = np.asarray(ui.app.model.rotation_matrix if block == "rotation_matrix"
                                 else ui.app.model.translation_vector).ravel()
                assert got[index] == pytest.approx(value), (block, index)
                assert ui.shown(str(value))
        np.testing.assert_allclose(np.asarray(ui.app.model.rotation_matrix).ravel(), 0.5 + np.arange(9))
        np.testing.assert_allclose(np.asarray(ui.app.model.translation_vector), 0.5 + np.arange(3))
    finally:
        ui.app.close()


def test_a_cell_keeps_its_value_when_the_text_is_no_number_and_commits_when_clicked_away():
    ui = Ui(make_app())
    try:
        type_cell(ui, "rotation_matrix", 1, "abc")
        assert np.asarray(ui.app.model.rotation_matrix)[0, 1] == 0.0
        ui.click(cell(ui, "translation", 2), fx=0.3)
        ui.type_text("12.5")
        assert np.asarray(ui.app.model.translation_vector)[2] == 0.0           # typed, not committed yet
        ui.click("log", fy=0.9)                                                # a click away commits (focus loss)
        assert np.asarray(ui.app.model.translation_vector)[2] == pytest.approx(12.5)
    finally:
        ui.app.close()


def test_the_warning_names_a_matrix_that_is_not_a_rotation_and_goes_when_it_is_one_again():
    ui = Ui(make_app())
    try:
        assert not ui.shown("Not a rotation")
        type_cell(ui, "rotation_matrix", 0, "2")                              # scales x: sheared / scaled
        assert ui.shown("Not a rotation: RᵀR ≠ 1")
        type_cell(ui, "rotation_matrix", 0, "1")
        assert not ui.shown("Not a rotation")
        type_cell(ui, "rotation_matrix", 0, "-1")                             # a mirror: det = -1
        assert ui.shown("Not a rotation: det R = −1")
        type_cell(ui, "rotation_matrix", 0, "1")
        assert not ui.shown("Not a rotation")
    finally:
        ui.app.close()


def test_rotating_and_translating_through_the_ui_writes_R_x_plus_t(small_trajectory, tmp_path):
    from chisurf.core.structure import trajectory_data as md

    source, top = small_trajectory / "small.dcd", small_trajectory / "topol.pdb"
    R, T = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], [10.0, 0.0, 0.0]
    ui = Ui(make_app())
    try:
        ui.drop(source, top)
        for index, value in ((0, "0"), (1, "-1"), (3, "1"), (4, "0")):
            type_cell(ui, "rotation_matrix", index, value)
        type_cell(ui, "translation", 0, "10")
        ui.arrow("stride", +1)
        assert np.asarray(ui.app.model.rotation_matrix).tolist() == R
        assert np.asarray(ui.app.model.translation_vector).tolist() == T and ui.app.model.stride == 2
        target = tmp_path / "moved.dcd"
        ui.click("save")
        assert ui.dialog_open and ui.shown("small_moved.dcd")
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        ui.settle()
        assert ui.shown("Rotated/translated trajectory saved")
        original = np.asarray(md.load(str(source), top=str(top), stride=2).xyz, dtype=float)
        written = read_xyz(target, top)
        assert written.shape == (4, 5235, 3)
        np.testing.assert_allclose(written, original @ np.asarray(R).T + np.asarray(T), atol=1e-3)
        x, y, z = original[0, 0]
        np.testing.assert_allclose(written[0, 0], [10 - y, x, z], atol=1e-3)         # the help page's example
    finally:
        ui.app.close()


def test_the_action_flow_dialog_cancel_close_save_and_replace(small_trajectory, tmp_path):
    def verify(path):
        assert read_xyz(path, small_trajectory / "topol.pdb").shape == (8, 5235, 3)

    check_action_flow(make_app, small_trajectory, tmp_path,
                      lambda ui: ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb"),
                      suggested="small_moved.dcd", title="Save trajectory",
                      precondition="Open a trajectory first.", cancelled="Save cancelled", verify=verify)


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app)
    assert scrolled_down < at_start                               # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down                                # a turn the other way brings them back
