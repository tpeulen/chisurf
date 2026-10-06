"""Click coverage of the native Save-Topology tool: every control is operated with pointer, keys and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see ``real_input``);
the assertions read what is drawn, the model's fields and the file written. The control -> test list is in
``okf/plugins/emtk-ports/traj_save_topology/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest
from chisurf.plugins.traj.traj_save_topology.app import SaveTopologyApp, make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import (
    DATA,
    Ui,
    check_action_flow,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_row_is_read_only,
    dead_tour_buttons,
    read_xyz,
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
        assert (
            ui.drop(small_trajectory / "notes.txt") is True
        )  # the host repaints: the answer is on screen
        assert ui.shown("No trajectory or topology file among the dropped paths.")
        assert ui.app.model.trajectory_filename == ""
        ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")
        assert ui.app.model.trajectory_filename == str(small_trajectory / "small.dcd")
        assert ui.app.model.topology_filename == str(small_trajectory / "topol.pdb")
        assert not ui.shown("No trajectory or topology")
        ui.drop(small_trajectory / "other.dcd")  # both rows full: the first matching row again
        assert ui.app.model.trajectory_filename == str(small_trajectory / "other.dcd")
        assert ui.drop(small_trajectory / "sub") is True  # a folder is no file for either row
        assert ui.shown("No trajectory or topology file among the dropped paths.")
    finally:
        ui.app.close()


def test_save_writes_frame_zero_as_the_typed_pdb_and_asks_before_replacing_it(
    small_trajectory, tmp_path
):
    def load(ui):
        ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")

    def verify(path):
        from chisurf.core.structure import trajectory_data as md

        written = md.load(str(path))
        first = read_xyz(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")[0]
        assert written.xyz.shape[1] == first.shape[0]
        np.testing.assert_allclose(
            np.asarray(written.xyz)[0], first, atol=2e-3
        )  # PDB keeps 3 decimals

    check_action_flow(
        make_app,
        small_trajectory,
        tmp_path,
        load,
        suggested="small_frame0.pdb",
        title="Save PDB-file",
        precondition="Open a trajectory first.",
        cancelled="Save cancelled",
        verify=verify,
    )


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app)
    assert scrolled_down < at_start  # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down  # a turn the other way brings them back
