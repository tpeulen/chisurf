"""Click coverage of the native Join-Trajectories tool: every control is operated with pointer, keys and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see
``traj_save_topology/test/real_input.py``); the assertions read what is drawn, the model's fields and the joined file.
The control -> test list is in ``okf/plugins/emtk-ports/traj_join/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.traj.traj_join.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import (  # noqa: F401  (hermetic is autouse)
    Ui,
    check_action_flow,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_number_field,
    check_row_is_read_only,
    hermetic,
    dead_tour_buttons,
    read_xyz,
    small_trajectory,
    wheel_steps_a_number_field,
)


def test_guide_and_help_buttons_are_pressed():
    check_guide_and_help_buttons(make_app)


def test_no_tour_card_button_is_dead_on_any_step():
    assert dead_tour_buttons(make_app) == []


@pytest.mark.parametrize("row, title", [("trajectory_1", "Open trajectory 1"), ("trajectory_2", "Open trajectory 2")])
def test_each_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works(row, title, small_trajectory,
                                                                                        monkeypatch):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(make_app, row, small_trajectory / "small.dcd", small_trajectory / "topol.pdb", small_trajectory,
                     title)


def test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works(small_trajectory, monkeypatch):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(make_app, "topology", small_trajectory / "topol.pdb", small_trajectory / "small.dcd",
                     small_trajectory, "Open topology")


@pytest.mark.parametrize("row", ["trajectory_1", "trajectory_2", "topology"])
def test_the_path_rows_do_not_take_typing(row, small_trajectory):
    check_row_is_read_only(make_app, row, small_trajectory)


def test_dropped_files_fill_the_empty_row_first_and_a_pdb_the_topology(small_trajectory):
    ui = Ui(make_app())
    try:
        assert ui.drop(small_trajectory / "notes.txt") is True
        assert ui.shown("No trajectory 1 or trajectory 2 or topology file among the dropped paths.")
        ui.drop(small_trajectory / "small.dcd")
        assert ui.app.model.trajectory_filename_1 == str(small_trajectory / "small.dcd")
        assert ui.app.model.trajectory_filename_2 == ""
        ui.drop(small_trajectory / "other.dcd", small_trajectory / "topol.pdb")
        assert ui.app.model.trajectory_filename_2 == str(small_trajectory / "other.dcd")
        assert ui.app.model.topology_filename == str(small_trajectory / "topol.pdb")
        assert not ui.shown("No trajectory 1")
    finally:
        ui.app.close()


def test_the_join_mode_radios_are_clicked_and_the_choice_is_drawn_checked():
    ui = Ui(make_app())
    try:
        assert ui.app.model.join_mode == "time" and {"By time (append frames)", "By atoms (stack)"} <= set(ui.strings)
        ui.click("join_mode.1")
        assert ui.app.model.join_mode == "atoms"
        ui.click("join_mode.0")
        assert ui.app.model.join_mode == "time"
        ui.click("join_mode.0")                                   # the checked one stays checked
        assert ui.app.model.join_mode == "time"
    finally:
        ui.app.close()


@pytest.mark.parametrize("attr", ["reverse_traj_1", "reverse_traj_2"])
def test_each_reverse_checkbox_is_clicked_on_and_off(attr):
    ui = Ui(make_app())
    try:
        assert getattr(ui.app.model, attr) is False
        ui.click(attr)
        assert getattr(ui.app.model, attr) is True
        ui.click(attr)
        assert getattr(ui.app.model, attr) is False
        ui.click(attr, fx=0.05)                                   # the box itself, at the left edge of the row
        assert getattr(ui.app.model, attr) is True
    finally:
        ui.app.close()


def test_the_chunk_size_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows():
    ui = Ui(make_app())
    start = ui.app.model.chunk_size
    ui.app.close()
    check_number_field(make_app, "chunk_size", start=start, typed=50, minimum=1, maximum=9999999, step=1, as_type=int)


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel does not reach a field inside a DockManager window "
                                       "(repro in the report); the Qt spin box steps on the wheel")
def test_the_wheel_steps_the_chunk_size():
    before, after = wheel_steps_a_number_field(make_app, "chunk_size")
    assert after != before


def _join(ui, tmp_path, first, second, top, name):
    ui.drop(first, second, top)
    target = tmp_path / name
    ui.click("save")
    assert ui.dialog_open and ui.shown("small_joined.dcd")
    ui.save_dialog_type_name(str(target))
    ui.press_text("Save")
    ui.settle()
    return target


def test_a_time_join_through_the_ui_appends_the_second_trajectory_reversed_when_its_box_is_ticked(small_trajectory,
                                                                                                    tmp_path):
    top = small_trajectory / "topol.pdb"
    a, b = read_xyz(small_trajectory / "small.dcd", top), read_xyz(small_trajectory / "other.dcd", top)
    ui = Ui(make_app())
    try:
        ui.click("reverse_traj_2")
        ui.type_into("chunk_size", "3")                           # smaller than the trajectory: the chunking is real
        target = _join(ui, tmp_path, small_trajectory / "small.dcd", small_trajectory / "other.dcd", top, "j.dcd")
        assert ui.shown("Joined trajectory saved") and ui.shown("Wrote 16 frames of 5235 atoms")
        written = read_xyz(target, top)
        np.testing.assert_allclose(written, np.concatenate([a, b[::-1]]), atol=1e-3)
    finally:
        ui.app.close()


def test_reversing_trajectory_one_reverses_the_first_half(small_trajectory, tmp_path):
    top = small_trajectory / "topol.pdb"
    a, b = read_xyz(small_trajectory / "small.dcd", top), read_xyz(small_trajectory / "other.dcd", top)
    ui = Ui(make_app())
    try:
        ui.click("reverse_traj_1")
        target = _join(ui, tmp_path, small_trajectory / "small.dcd", small_trajectory / "other.dcd", top, "j.dcd")
        np.testing.assert_allclose(read_xyz(target, top), np.concatenate([a[::-1], b]), atol=1e-3)
    finally:
        ui.app.close()


def test_an_atoms_join_through_the_radio_stacks_the_two_trajectories_frame_by_frame(small_trajectory, tmp_path):
    from chisurf.core.fio.trajectory.dcd import read_dcd

    top = small_trajectory / "topol.pdb"
    a, b = read_xyz(small_trajectory / "small.dcd", top), read_xyz(small_trajectory / "other.dcd", top)
    ui = Ui(make_app())
    try:
        ui.click("join_mode.1")
        target = _join(ui, tmp_path, small_trajectory / "small.dcd", small_trajectory / "other.dcd", top, "s.dcd")
        stacked = np.asarray(read_dcd(str(target))[0])          # no topology names 2 x 5235 atoms
        assert stacked.shape == (8, 2 * 5235, 3)
        np.testing.assert_allclose(stacked, np.concatenate([a, b], axis=1), atol=1e-3)
    finally:
        ui.app.close()


def test_one_trajectory_is_not_enough_and_the_dialog_does_not_open(small_trajectory):
    ui = Ui(make_app())
    try:
        ui.drop(small_trajectory / "small.dcd")
        ui.click("save")
        assert not ui.dialog_open and ui.shown("Open two trajectories first.")
    finally:
        ui.app.close()


def test_the_action_flow_dialog_cancel_close_save_and_replace(small_trajectory, tmp_path):
    top = small_trajectory / "topol.pdb"

    def verify(path):
        assert read_xyz(path, top).shape == (16, 5235, 3)

    check_action_flow(make_app, small_trajectory, tmp_path,
                      lambda ui: ui.drop(small_trajectory / "small.dcd", small_trajectory / "other.dcd", top),
                      suggested="small_joined.dcd", title="Save trajectory",
                      precondition="Open two trajectories first.", cancelled="Join cancelled", verify=verify)


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app)
    assert scrolled_down < at_start                               # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down                                # a turn the other way brings them back
