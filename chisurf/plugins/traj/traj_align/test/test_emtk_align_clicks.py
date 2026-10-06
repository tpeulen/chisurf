"""Click coverage of the native Align-Trajectory tool: every control is operated with pointer, keys and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see
``traj_save_topology/test/real_input.py``); the assertions read what is drawn, the model's fields and the aligned file.
The control -> test list is in ``okf/plugins/emtk-ports/traj_align/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest
from chisurf.plugins.traj.traj_align.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import (
    Ui,
    check_action_flow,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_number_field,
    check_row_is_read_only,
    check_text_field,
    dead_tour_buttons,
    enter_commits_an_emptied_field,
    read_xyz,
    wheel_steps_a_number_field,
)


def test_guide_and_help_buttons_are_pressed():
    check_guide_and_help_buttons(make_app)


def test_no_tour_card_button_is_dead_on_any_step():
    assert dead_tour_buttons(make_app) == []


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
        "Open topology",
    )


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


def test_the_stride_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows():
    check_number_field(
        make_app, "stride", start=1, typed=5, minimum=1, maximum=999999, step=1, as_type=int
    )


def test_the_atom_selection_field_is_typed_and_may_be_emptied():
    check_text_field(make_app, "atom_selection", start="", typed="0, 1, 2, 3")


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: Enter in a text field that was just emptied is not seen as Enter "
    "(repro in the report); a click away commits the empty value",
)
def test_enter_commits_an_emptied_atom_selection():
    assert enter_commits_an_emptied_field(make_app, "atom_selection", "0, 1") == ""


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel does not reach a field inside a DockManager window "
    "(repro in the report); the Qt spin box steps on the wheel",
)
def test_the_wheel_steps_the_stride_field():
    before, after = wheel_steps_a_number_field(make_app, "stride")
    assert after != before


def test_aligning_through_the_ui_writes_the_superposition_the_core_computes(
    small_trajectory, tmp_path
):
    from chisurf.core.structure import trajectory_data as md

    source, top = small_trajectory / "small.dcd", small_trajectory / "topol.pdb"
    ui = Ui(make_app())
    try:
        ui.drop(source, top)
        ui.type_into("atom_selection", "0, 1, 2, 3")
        ui.arrow("stride", +1)  # 1 -> 2 with the real arrow
        assert ui.app.model.stride == 2
        target = tmp_path / "aligned.dcd"
        ui.click("save")
        assert ui.dialog_open and ui.shown("small_aligned.dcd")
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        ui.settle()
        assert target.exists() and ui.shown("Aligned trajectory saved")
        frame0 = md.load_frame(str(source), 0, top=str(top))
        reference = md.load(str(source), top=str(top), stride=2).superpose(
            frame0, frame=0, atom_indices=np.array([0, 1, 2, 3], np.int32)
        )
        written = read_xyz(target, top)
        assert written.shape == (4, 5235, 3)
        np.testing.assert_allclose(written, np.asarray(reference.xyz), atol=1e-3)
        assert np.abs(read_xyz(source, top)[::2] - written).max() > 0.1  # the frames did move
    finally:
        ui.app.close()


def test_a_selection_that_is_not_atom_ids_is_answered_in_the_log_and_writes_nothing(
    small_trajectory, tmp_path
):
    ui = Ui(make_app())
    try:
        ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")
        ui.type_into("atom_selection", "CA, 1")
        target = tmp_path / "never.dcd"
        ui.click("save")
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        ui.settle()
        assert not target.exists() and ui.shown(
            "Atom selection must be a comma-separated list of atom ids"
        )
    finally:
        ui.app.close()


def test_the_action_flow_dialog_cancel_close_save_and_replace(small_trajectory, tmp_path):
    def verify(path):
        assert read_xyz(path, small_trajectory / "topol.pdb").shape == (8, 5235, 3)

    check_action_flow(
        make_app,
        small_trajectory,
        tmp_path,
        lambda ui: ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb"),
        suggested="small_aligned.dcd",
        title="Save aligned trajectory",
        precondition="Open a trajectory first.",
        cancelled="Save cancelled",
        verify=verify,
    )


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app)
    assert scrolled_down < at_start  # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down  # a turn the other way brings them back
