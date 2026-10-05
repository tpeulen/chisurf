"""Click coverage of the native Trajectory-to-FRET tool: every control is operated with pointer, keys and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``key`` / ``on_files_dropped`` reach the window (see
``traj_save_topology/test/real_input.py``); the assertions read what is drawn, the model's fields and the table written.
The control -> test list is in ``okf/plugins/emtk-ports/traj_fret/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.traj.fret_trajectory.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import (  # noqa: F401  (hermetic is autouse)
    Ui,
    check_action_flow,
    check_browse_row,
    check_guide_and_help_buttons,
    check_log_scrolls_with_the_wheel,
    check_number_field,
    check_row_is_read_only,
    dead_tour_buttons,
    hermetic,
    read_xyz,
    small_trajectory,
    wheel_steps_a_number_field,
)

SIZE = (800, 700)               # the Process panel and the log are on screen


def _ui():
    return Ui(make_app(), SIZE)


def _loaded(small_trajectory):
    ui = _ui()
    ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb")
    ui.draw(3)
    return ui


def test_guide_and_help_buttons_are_pressed():
    check_guide_and_help_buttons(make_app, size=SIZE, prev_step=6, close_step=6)


def test_no_tour_card_button_is_dead_on_any_step():
    assert dead_tour_buttons(make_app, SIZE) == []


def test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works(small_trajectory, monkeypatch):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(make_app, "trajectory", small_trajectory / "small.dcd", small_trajectory / "topol.pdb",
                     small_trajectory, "Open trajectory", model_attr="trajectory_file", size=SIZE)


def test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works(small_trajectory, monkeypatch):
    monkeypatch.chdir(small_trajectory)
    check_browse_row(make_app, "topology", small_trajectory / "topol.pdb", small_trajectory / "small.dcd",
                     small_trajectory, "Open topology", size=SIZE)


@pytest.mark.parametrize("row", ["trajectory", "topology"])
def test_the_path_rows_do_not_take_typing(row, small_trajectory):
    check_row_is_read_only(make_app, row, small_trajectory, size=SIZE)


def test_dropped_files_fill_the_rows_by_type_and_either_order_works(small_trajectory):
    ui = _ui()
    try:
        assert ui.drop(small_trajectory / "notes.txt") is True
        assert ui.shown("No trajectory or topology file among the dropped paths.")
        assert ui.shown("Choose the trajectory and its topology to pick the atoms.")
        ui.drop(small_trajectory / "small.dcd")                           # the trajectory before its topology
        assert ui.app.model.pdb is None and ui.shown("Choose the trajectory and its topology to pick the atoms.")
        ui.drop(small_trajectory / "topol.pdb")
        assert ui.app.model.pdb is not None and not ui.shown("Choose the trajectory and its topology")
        assert ui.shown("Donor") and ui.shown("Acceptor") and ui.shown("Chain")
    finally:
        ui.app.close()


def caption(ui, name, column):
    """The drawn caption (``Chain`` / ``Residue`` / ``Atom``) in the donor (0) or acceptor (1) column."""
    hits = [t for t in ui.last.texts if t[5] == name]
    return sorted(hits, key=lambda t: t[0])[column]


def combo_at(ui, role, slot, which):
    """Click the chain (0), residue (1) or atom (2) combo of atom *slot* (0, 1) of ``donor`` / ``acceptor``."""
    ui.draw(2)
    c = caption(ui, ("Chain", "Residue", "Atom")[which], 0 if role == "donor" else 1)
    return ui.click_at(c[0] + 8, c[1] + 19 + 23 * slot + 8)


def entry(ui, label, nth=-1):
    return ui.click(ui.text_rect(label, nth))


def test_each_of_the_twelve_pickers_opens_its_list_and_a_choice_changes_the_atom(small_trajectory):
    ui = _loaded(small_trajectory)
    try:
        index = ui.app.atom_index()
        assert ui.app.model.donor == (0, 1) and ui.app.model.acceptor == (2, 3)
        # atoms: the combo lists the atoms of the residue; picking the third atom moves the selected index
        for role, slot in (("donor", 0), ("donor", 1), ("acceptor", 0), ("acceptor", 1)):
            before = getattr(ui.app.model, role)
            chain, residue = index.where(before[slot])
            atoms = index.atoms(chain, residue)
            combo_at(ui, role, slot, 2)
            target = index.name(atoms[3])
            assert ui.shown(target) and ui.shown(index.name(atoms[0]))     # the list is open
            entry(ui, target)
            after = getattr(ui.app.model, role)
            assert after[slot] == atoms[3] and after[1 - slot] == before[1 - slot], (role, slot)
            assert ui.app.tour.active is False
        # residues: the first atom of the residue picked
        combo_at(ui, "donor", 0, 1)
        entry(ui, "2", nth=-1)
        assert index.where(ui.app.model.donor[0]) == ("A", 2) and ui.app.model.donor[0] == index.atoms("A", 2)[0]
        # chains: the first atom of the first residue of the chain picked
        combo_at(ui, "acceptor", 1, 0)
        entry(ui, "B")
        chain, residue = index.where(ui.app.model.acceptor[1])
        assert chain == "B" and residue == index.residues["B"][0]
        assert ui.app.model.acceptor[1] == index.atoms("B", residue)[0]
        assert ui.shown("B")
    finally:
        ui.app.close()


def test_a_picker_list_closes_with_escape_without_choosing(small_trajectory):
    from emtk import keys

    ui = _loaded(small_trajectory)
    try:
        before = ui.app.model.donor
        combo_at(ui, "donor", 0, 2)
        ui.key(keys.KEY_ESCAPE, "")
        ui.draw(2)
        assert ui.app.model.donor == before
    finally:
        ui.app.close()


@pytest.mark.parametrize("key, start, typed, minimum, maximum, step, as_type", [
    ("stride", 1, 4, 1, 99999, 1, int),
    ("forster_radius", 52.0, 60.0, 0.0, 9999.0, 1.0, float),
    ("tau0", 2.6, 4.0, 0.0, 1000.0, 0.1, float),
    ("t_step", 1.0, 2.5, 0.0, 100000.0, 0.1, float),
])
def test_each_number_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows(key, start, typed, minimum, maximum,
                                                                                    step, as_type):
    check_number_field(make_app, key, start=start, typed=typed, minimum=minimum, maximum=maximum, step=step,
                       as_type=as_type, size=SIZE)


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel does not reach a field inside a DockManager window "
                                       "(repro in the report); the Qt spin box steps on the wheel")
@pytest.mark.parametrize("key", ["stride", "forster_radius", "tau0", "t_step"])
def test_the_wheel_steps_a_number_field(key):
    before, after = wheel_steps_a_number_field(make_app, key, size=SIZE)
    assert after != before


def test_the_dipole_checkbox_is_clicked_on_and_off():
    ui = _ui()
    try:
        assert ui.app.model.dipoles is True
        ui.click("dipoles")
        assert ui.app.model.dipoles is False
        ui.click("dipoles")
        assert ui.app.model.dipoles is True
    finally:
        ui.app.close()


def test_the_panel_headers_fold_and_unfold_their_controls(small_trajectory):
    ui = _loaded(small_trajectory)
    try:
        assert ui.shown("Chain") and ui.shown("R0 [Ang]")
        ui.click("Dipole atoms.fold")
        assert not ui.shown("Chain") and ui.shown("R0 [Ang]")
        ui.click("Parameters.fold")
        assert not ui.shown("R0 [Ang]")
        ui.click("Dipole atoms.fold")
        ui.click("Parameters.fold")
        assert ui.shown("Chain") and ui.shown("R0 [Ang]")
    finally:
        ui.app.close()


def _table(path):
    return np.loadtxt(path, skiprows=1)


def _reference(xyz, donor, acceptor, r0, tau0, dipoles=True):
    """Dipole-centre distance, kappa and the rate from the coordinates (frames, atoms, 3)."""
    d1, d2, a1, a2 = (xyz[:, i] for i in (*donor, *acceptor))
    unit = lambda v: v / np.linalg.norm(v, axis=1)[:, None]  # noqa: E731
    if not dipoles:
        r = np.linalg.norm(a1 - d1, axis=1)
        return r, np.full(len(r), np.nan), 1.5 * (2 / 3) * (r0 / r) ** 6 / tau0
    dd, da, rda = d2 - d1, a2 - a1, (a1 + a2) / 2 - (d1 + d2) / 2
    r = np.linalg.norm(rda, axis=1)
    ud, ua, ur = unit(dd), unit(da), unit(rda)
    kappa = np.sum(ud * ua, 1) - 3 * np.sum(ud * ur, 1) * np.sum(ua * ur, 1)
    return r, kappa, 1.5 * kappa ** 2 * (r0 / r) ** 6 / tau0


def test_processing_through_the_ui_writes_the_physics_of_the_picked_atoms(small_trajectory, tmp_path):
    top = small_trajectory / "topol.pdb"
    xyz = read_xyz(small_trajectory / "small.dcd", top).astype(float)
    ui = _loaded(small_trajectory)
    try:
        index = ui.app.atom_index()
        # choose the donor's second atom and the acceptor's first through their atom combos
        for role, slot, k in (("donor", 1, 2), ("acceptor", 0, 1)):
            chain, residue = index.where(getattr(ui.app.model, role)[slot])
            combo_at(ui, role, slot, 2)
            entry(ui, index.name(index.atoms(chain, residue)[k]))
        ui.type_into("stride", "2")
        ui.type_into("forster_radius", "55")
        ui.type_into("tau0", "3.5")
        ui.type_into("t_step", "2.5")
        donor, acceptor = ui.app.model.donor, ui.app.model.acceptor
        assert donor != (0, 1) or acceptor != (2, 3)
        target = tmp_path / "fret.csv"
        ui.click("process")
        assert ui.dialog_open and ui.shown("Output-file") and ui.shown("small_fret.csv")
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        assert not ui.dialog_open and ui.app.running
        ui.settle()
        table = _table(target)
        r, kappa, rate = _reference(xyz[::2], donor, acceptor, 55.0, 3.5)
        assert table.shape == (4, 6)
        np.testing.assert_allclose(table[:, 0], [0, 2, 4, 6])                    # frame numbers
        np.testing.assert_allclose(table[:, 1], np.array([0, 2, 4, 6]) * 2.5)    # time = frame x t-step
        np.testing.assert_allclose(table[:, 2], r, atol=0.01)
        np.testing.assert_allclose(np.abs(table[:, 3]), np.abs(kappa), rtol=1e-3, atol=1e-3)
        np.testing.assert_allclose(table[:, 5], rate, rtol=2e-3)
        assert ui.shown("Finished") and ui.app.model.log_text()[-1].endswith("(4 frames)")
    finally:
        ui.app.close()


def test_without_the_dipole_box_the_first_atoms_and_two_thirds_are_used(small_trajectory, tmp_path):
    top = small_trajectory / "topol.pdb"
    xyz = read_xyz(small_trajectory / "small.dcd", top).astype(float)
    ui = _loaded(small_trajectory)
    try:
        ui.click("dipoles")
        assert ui.app.model.dipoles is False
        target = tmp_path / "iso.csv"
        ui.click("process")
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        ui.settle()
        table = _table(target)
        r, _kappa, _rate = _reference(xyz, (0, 1), (2, 3), 52.0, 2.6, dipoles=False)
        np.testing.assert_allclose(table[:, 2], r, atol=0.01)
        np.testing.assert_allclose(table[:, 4], 2 / 3, rtol=1e-3)
    finally:
        ui.app.close()


def test_the_action_flow_dialog_cancel_close_save_and_replace(small_trajectory, tmp_path):
    def verify(path):
        assert _table(path).shape == (8, 6)

    check_action_flow(make_app, small_trajectory, tmp_path,
                      lambda ui: ui.drop(small_trajectory / "small.dcd", small_trajectory / "topol.pdb"),
                      suggested="small_fret.csv", title="Output-file", precondition="Open a trajectory first.",
                      cancelled="Process cancelled", verify=verify, log_names_target=False, size=SIZE)


def test_the_log_scrolls_under_the_wheel_and_back():
    at_start, scrolled_down, back_up = check_log_scrolls_with_the_wheel(make_app, size=SIZE)
    assert scrolled_down < at_start                               # a turn down moves the lines up: later ones show
    assert back_up > scrolled_down                                # a turn the other way brings them back
