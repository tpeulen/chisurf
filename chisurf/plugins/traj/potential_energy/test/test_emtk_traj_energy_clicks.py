"""Click coverage of the native Potential-Energy calculator: every control is operated with pointer, keys and drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see
``traj_save_topology/test/real_input.py``); the assertions read what is drawn, the editor's and the model's fields,
the table and the energies written, which are compared with what the Qt widget's model wrote. The control -> test
list is in ``okf/plugins/emtk-ports/traj_energy/REPORT.md``.
"""

from __future__ import annotations

import shutil

import numpy as np
import pytest
from chisurf.plugins.traj.potential_energy.app import make_app
from chisurf.plugins.traj.potential_energy.potential_specs import get_spec, potential_names
from chisurf.plugins.traj.traj_save_topology.test.real_input import (
    Ui,
    check_action_flow,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_number_field,
    check_row_is_read_only,
    dead_tour_buttons,
    wheel_steps_a_number_field,
)
from emtk import keys

from .test_emtk_traj_energy_parity import POTENTIALS
from .test_view_model import _peptide_trajectory

SIZE = (800, 700)


@pytest.fixture
def folder(tmp_path):
    """A folder holding a small peptide trajectory (pep.dcd, pep.pdb), a text file and a sub folder."""
    pytest.importorskip("IMP.cgmol")
    _peptide_trajectory(str(tmp_path / "pep.dcd"))
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    return tmp_path


def _ui():
    return Ui(make_app(), SIZE)


def _pick_type(ui, name):
    ui.click("potential_type")
    ui.press_text(name)
    assert ui.app.editor.potential_type == name


def test_guide_and_help_buttons_are_pressed():
    check_guide_and_help_buttons(make_app, size=SIZE, prev_step=5, close_step=5)


def test_no_tour_card_button_is_dead_on_any_step():
    assert dead_tour_buttons(make_app, SIZE) == []


def test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works(
    folder, monkeypatch
):
    monkeypatch.chdir(folder)
    check_browse_row(
        make_app,
        "trajectory",
        folder / "pep.dcd",
        folder / "pep.pdb",
        folder,
        "Open trajectory",
        model_attr="trajectory_file",
        size=SIZE,
    )


def test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works(
    folder, monkeypatch
):
    monkeypatch.chdir(folder)
    check_browse_row(
        make_app,
        "topology",
        folder / "pep.pdb",
        folder / "pep.dcd",
        folder,
        "Open topology",
        size=SIZE,
    )


@pytest.mark.parametrize("row", ["trajectory", "topology"])
def test_the_path_rows_do_not_take_typing(row, folder):
    check_row_is_read_only(make_app, row, folder, size=SIZE)


def test_dropped_files_fill_the_rows_by_type_and_a_foreign_file_is_answered(folder):
    ui = _ui()
    try:
        assert ui.drop(folder / "notes.txt") is True
        assert ui.shown("No trajectory or topology file among the dropped paths.")
        ui.drop(folder / "pep.dcd", folder / "pep.pdb")
        assert ui.app.model.trajectory_file == str(folder / "pep.dcd")
        assert ui.app.model.topology_filename == str(folder / "pep.pdb")
        assert not ui.shown("No trajectory or topology")
    finally:
        ui.app.close()


def test_the_type_combo_lists_every_potential_and_each_choice_shows_its_own_parameters():
    ui = _ui()
    try:
        ui.click("potential_type")
        assert set(potential_names()) <= set(ui.strings)
        for name in potential_names():
            _pick_type(ui, name)
            spec = get_spec(name)
            for param in spec.params:
                assert ui.shown(param.label), (name, param.label)
            if name == "H-Bond":
                assert all(ui.shown(label) for label in ("OH", "ON", "CN", "CH"))
            ui.click("potential_type")
            assert ui.shown(name)  # the list is open again, on the same names
            ui.key(keys.KEY_ESCAPE, "")
        _pick_type(ui, "Radius of Gyration")
        assert not ui.shown("Cutoff CA")  # a type without parameters shows none
    finally:
        ui.app.close()


def test_escape_closes_the_open_type_list_without_choosing():
    ui = _ui()
    try:
        ui.click("potential_type")
        assert ui.shown("Go-Potential")
        ui.key(keys.KEY_ESCAPE, "")
        ui.draw(2)
        assert ui.app.editor.potential_type == "H-Bond"
    finally:
        ui.app.close()


@pytest.mark.parametrize(
    "potential, key, start, typed, minimum, maximum, step, as_type",
    [
        ("H-Bond", "cutoff_ca", 8.0, 9.0, 0.0, 100.0, 0.5, float),
        ("H-Bond", "cutoff_hbond", 3.0, 4.0, 0.0, 20.0, 0.25, float),
        ("AV-Potential", "av_samples", 10000, 500, 1, 999999, 1000, int),
        ("AV-Potential", "min_av", 150, 20, 0, 999999, 50, int),
        ("Iso-UNRES", "ca_cutoff", 25.0, 12.0, 10.0, 27.0, 0.5, float),
        ("Miyazawa-Jernigan", "ca_cutcoff", 6.5, 7.0, 0.0, 100.0, 0.5, float),
        ("Go-Potential", "epsilon", 1.0, 2.0, 0.0, 1000.0, 0.1, float),
        ("Go-Potential", "cutoff", 6.5, 7.5, 0.0, 100.0, 0.5, float),
        ("Go-Potential", "nnEFactor", 0.7, 0.3, 0.0, 10.0, 0.05, float),
        ("ASA-Calpha", "n_sphere_point", 590, 100, 1, 100000, 10, int),
        ("ASA-Calpha", "probe", 1.0, 1.5, 0.0, 20.0, 0.1, float),
        ("ASA-Calpha", "radius", 2.5, 3.0, 0.0, 20.0, 0.1, float),
        ("Clash potential", "clash_tolerance", 2.0, 1.5, 0.01, 100.0, 0.25, float),
        ("Clash potential", "covalent_radius", 1.5, 2.0, 0.25, 10.0, 0.25, float),
    ],
)
def test_each_parameter_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows(
    potential, key, start, typed, minimum, maximum, step, as_type
):
    check_number_field(
        make_app,
        key,
        start=start,
        typed=typed,
        minimum=minimum,
        maximum=maximum,
        step=step,
        as_type=as_type,
        size=SIZE,
        model_of=lambda app: app.editor,
        prepare=lambda ui: _pick_type(ui, potential),
    )


@pytest.mark.parametrize(
    "potential, attrs",
    [
        ("H-Bond", ["oh", "on", "cn", "ch"]),
        ("Go-Potential", ["native_cutoff_on", "non_native_contact_on"]),
    ],
)
def test_each_checkbox_is_clicked_off_and_on(potential, attrs):
    ui = _ui()
    try:
        _pick_type(ui, potential)
        for attr in attrs:
            assert getattr(ui.app.editor, attr) is True
            ui.click(attr)
            assert getattr(ui.app.editor, attr) is False
            assert all(getattr(ui.app.editor, other) is True for other in attrs if other != attr)
            ui.click(attr)
            assert getattr(ui.app.editor, attr) is True
    finally:
        ui.app.close()


def test_the_parameters_of_a_type_survive_choosing_another_and_return_to_their_defaults_after_add():
    pytest.importorskip("IMP.cgmol")
    ui = _ui()
    try:
        ui.type_into("cutoff_ca", "9.5")
        _pick_type(ui, "Go-Potential")
        _pick_type(ui, "H-Bond")
        assert ui.app.editor.cutoff_ca == 9.5 and ui.shown("9.50")
        ui.click("add")
        assert [r["name"] for r in ui.app.model.added_potentials()] == ["H-Bond"]
        assert ui.app.editor.cutoff_ca == 8.0 and ui.shown("8.00")  # a fresh editor, as in Qt
    finally:
        ui.app.close()


def test_a_potential_file_field_is_typed_and_its_browse_button_picks_a_file(folder, monkeypatch):
    np.save(folder / "table.npy", np.zeros(3))
    monkeypatch.chdir(folder)
    ui = _ui()
    try:
        default = ui.app.editor.potential
        assert default.endswith("hb.npy")
        ui.type_into("potential", str(folder / "typed.npy"))
        assert ui.app.editor.potential == str(folder / "typed.npy")
        ui.click("potential_browse")
        assert (
            ui.dialog_open
            and ui.shown("Open Potential")
            and ui.shown("table.npy")
            and not ui.shown("notes.txt")
        )
        ui.press_text("table.npy")
        ui.press_text("Open")
        assert not ui.dialog_open and ui.app.editor.potential == str(folder / "table.npy")
        ui.click("potential_browse")
        ui.press_text("Cancel")
        assert ui.app.editor.potential == str(folder / "table.npy")
        ui.click("potential_browse")
        ui.press_text("×")
        assert not ui.dialog_open
    finally:
        ui.app.close()


def test_the_weight_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows():
    check_number_field(
        make_app,
        "potential_weight",
        start=1.0,
        typed=2.5,
        minimum=-1e6,
        maximum=1e6,
        step=1.0,
        size=SIZE,
    )


def test_the_stride_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows():
    check_number_field(
        make_app,
        "stride",
        start=1,
        typed=3,
        minimum=1,
        maximum=9999,
        step=1,
        as_type=int,
        size=SIZE,
    )


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel does not reach a field inside a DockManager window "
    "(repro in the report); the Qt spin box steps on the wheel",
)
@pytest.mark.parametrize("key", ["stride", "potential_weight", "cutoff_ca"])
def test_the_wheel_steps_a_number_field(key):
    before, after = wheel_steps_a_number_field(make_app, key, size=SIZE)
    assert after != before


def test_add_puts_the_potential_in_the_table_with_the_typed_weight_and_a_failure_is_shown_in_the_window():
    pytest.importorskip("IMP.cgmol")
    ui = _ui()
    try:
        assert not ui.shown("Radius of Gyration")
        _pick_type(ui, "Radius of Gyration")
        ui.type_into("potential_weight", "0.5")
        ui.click("add")
        assert ui.app.model.added_potentials() == [
            {"name": "Radius of Gyration", "weight": 0.5, "idx": 0}
        ]
        assert ui.shown("Radius of Gyration") and ui.shown("0.5") and ui.app.status == ""
        assert ui.app.model.log_text()[-1].endswith(
            "Added potential 'Radius of Gyration' (weight=0.5)"
        )
    finally:
        ui.app.close()


def test_a_potential_that_cannot_be_built_is_reported_under_the_form_and_not_added(monkeypatch):
    from chisurf.plugins.traj.potential_energy import app as app_module

    def refuse(name, values=None, structure=None):
        raise ValueError(f"cannot build {name}")

    monkeypatch.setattr(app_module, "make_potential", refuse)
    ui = _ui()
    try:
        ui.click("add")
        assert ui.app.model.added_potentials() == []
        assert ui.app.status == "ValueError: cannot build H-Bond" and ui.shown(ui.app.status)
    finally:
        ui.app.close()


def test_a_double_click_removes_the_row_and_so_does_delete_on_the_selected_row():
    pytest.importorskip("IMP.cgmol")
    ui = _ui()
    try:
        _pick_type(ui, "Radius of Gyration")
        for _ in range(3):
            ui.click("add")
        assert len(ui.app.model.added_potentials()) == 3
        x, y, w, h = ui.app.item_rects["added_potentials"]
        ui.click_at(x + 30, y + 30)  # one click only selects
        assert len(ui.app.model.added_potentials()) == 3
        ui.click_at(x + 30, y + 30, clicks=2)
        assert len(ui.app.model.added_potentials()) == 2
        ui.click_at(x + 30, y + 30)
        ui.key(keys.KEY_DELETE, "")
        assert len(ui.app.model.added_potentials()) == 1
        assert ui.app.model.log_text()[-1].endswith("Removed potential 'Radius of Gyration'")
    finally:
        ui.app.close()


def test_process_says_what_is_missing_before_it_asks_for_a_file(folder):
    pytest.importorskip("IMP.cgmol")
    ui = _ui()
    try:
        ui.click("process")
        assert not ui.dialog_open and ui.shown("Open a trajectory first.")
        ui.drop(folder / "pep.dcd", folder / "pep.pdb")
        ui.click("process")
        assert not ui.dialog_open and ui.shown("Add at least one potential.")
        _pick_type(ui, "Radius of Gyration")
        ui.click("add")
        ui.click("process")
        assert (
            ui.dialog_open
            and ui.shown("Save energies")
            and ui.shown("(*.txt)")
            or ui.shown("CSV-name file")
        )
    finally:
        ui.app.close()


def test_processing_through_the_ui_writes_the_energies_the_qt_widgets_model_wrote(
    qt, trajectory, tmp_path
):  # noqa: F811
    dcd, pdb, _tmp = trajectory
    ui = _ui()
    try:
        ui.drop(dcd, pdb)
        for name, weight in POTENTIALS:
            _pick_type(ui, name)
            ui.type_into("potential_weight", str(weight))
            ui.click("add")
        assert [(r["name"], r["weight"]) for r in ui.app.model.added_potentials()] == POTENTIALS
        target = tmp_path / "energies.txt"
        ui.click("process")
        assert ui.dialog_open
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        assert not ui.dialog_open and ui.app.running
        ui.settle()
        assert ui.shown("Processed 4 frame(s).")
        assert target.read_text() == qt["energies"]
    finally:
        ui.app.close()


def test_the_process_dialog_cancel_close_and_replace_buttons(folder, tmp_path):
    pytest.importorskip("IMP.cgmol")

    def load(ui):
        ui.drop(folder / "pep.dcd", folder / "pep.pdb")
        _pick_type(ui, "Radius of Gyration")
        ui.click("add")

    def verify(path):
        assert len(path.read_text().strip().splitlines()) == 5  # header and the four frames

    check_action_flow(
        make_app,
        folder,
        tmp_path,
        load,
        suggested="",
        title="Save energies",
        precondition="Open a trajectory first.",
        cancelled="Process cancelled",
        verify=verify,
        log_names_target=False,
        size=SIZE,
    )


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app, size=SIZE)
    assert scrolled_down < at_start  # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down  # a turn the other way brings them back
