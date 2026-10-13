"""The acquisition simulator setup dialog (species grid, kinetics, decay editor) on emtk.

These behaviours were asserted against the Qt ``EnhancedSimulationSetupDialog`` /
``DecaySettingsDialog`` before those were retired; they now drive the emtk dialog of the
acquisition app (``chisurf.plugins.core.acq.gui.sim_setup``) -- through the pointer and
keyboard where a control is involved, through its edit model where the Qt test set a value
programmatically too.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.core.acq.test.test_emtk_sim_setup import edit_cell
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

W, H = 900, 1000


def _driver(**params):
    """The acquisition app with its simulation setup dialog open on *params*."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel
    from chisurf.plugins.core.acq.gui.sim_setup import SimulationSetupDialog

    app = AcquisitionApp(AcquisitionNativeModel())
    ui = Driver(app, (W, H))
    ui.draw(3)
    base = app.model._editor_params()
    base.update(params)
    app.setup_kind = "SIMULATION"
    app.sim_setup = SimulationSetupDialog(base, on_apply=app.model.apply_simulation_setup)
    app.sim_setup.show()
    ui.draw(3)
    return ui


@pytest.fixture
def make():
    """Factory of open dialogs; every app it made is closed afterwards."""
    made = []

    def factory(**params):
        ui = _driver(**params)
        made.append(ui)
        return ui

    yield factory
    for ui in made:
        ui.app.close()


def test_decay_dialog_roundtrip_widget(make):
    drv = make(N_species=2)
    dialog = drv.app.sim_setup
    dialog.open_decay(0)
    drv.draw(3)
    edit = dialog.decay
    # Edit species 0 to a bi-exponential (amp, tau) through the table + IRF.
    edit.add_component()
    drv.draw(2)
    edit_cell(drv, "spectrum_rows", 0, "amplitude", "0.7")
    edit_cell(drv, "spectrum_rows", 0, "lifetime", "1.2")
    edit_cell(drv, "spectrum_rows", 1, "amplitude", "0.3")
    edit_cell(drv, "spectrum_rows", 1, "lifetime", "4.0")
    edit.irf_fwhm_ns = 0.3
    drv.click("decay_ok")
    drv.draw(2)

    m = dialog.model
    assert m.decay_lifetimes[0] == [[0.7, 1.2], [0.3, 4.0]]
    assert m.irf_fwhm_ns == 0.3
    params = m.to_parameters()
    assert params["decay_lifetimes"][0] == [[0.7, 1.2], [0.3, 4.0]]
    assert len(params["decay_lifetimes"]) == 2  # sized to species count
    assert params["irf_fwhm_ns"] == 0.3


def test_decay_dialog_species_switch_preserves_edits(make):
    drv = make(N_species=2)
    dialog = drv.app.sim_setup
    dialog.open_decay(0)
    drv.draw(3)
    edit_cell(drv, "spectrum_rows", 0, "lifetime", "1.1")
    # switch species with the editor's Species spin -> species 0 is kept
    drv.click("species")
    drv.select_all()
    drv.type_text("2")
    drv.enter()
    drv.draw(3)
    assert dialog.decay.cur == 1
    edit_cell(drv, "spectrum_rows", 0, "lifetime", "5.5")
    drv.click("decay_ok")
    drv.draw(2)
    m = dialog.model
    assert m.decay_lifetimes[0] == [[1.0, 1.1]]
    assert m.decay_lifetimes[1] == [[1.0, 5.5]]


def test_decay_dialog_load_pattern_widget(make, tmp_path):
    import numpy as np

    pat = tmp_path / "decay.txt"
    np.savetxt(pat, np.exp(-np.arange(256) / 40.0))
    drv = make(N_species=1)
    dialog = drv.app.sim_setup
    dialog.open_decay(0)
    drv.draw(3)
    dialog.decay.pattern_path = str(pat)  # as the Pattern... chooser sets it
    drv.click("decay_ok")
    drv.draw(2)
    assert dialog.model.to_parameters()["decay_pattern_files"][0] == str(pat)


def test_kinetics_matrix_tracks_species_widget(make):
    drv = make(N_species=2)
    dialog = drv.app.sim_setup
    m = dialog.model
    drv.click("Kinetics.fold")
    drv.draw(2)
    assert len(m.k_rad_table.rows()) == 2 and len(m.k_nrad_table.rows()) == 2
    # Changing the species count resizes both N x N matrices.
    drv.click("n_species")
    drv.select_all()
    drv.type_text("3")
    drv.enter()
    drv.draw(3)
    assert m.n_species == 3
    assert len(m.k_rad_table.rows()) == 3 and len(m.k_nrad_table.rows()) == 3
    assert len(m.k_nrad_table.columns()) == 4  # row label + 3 targets
    # Edited rates flow into the emitted parameters (row-major i -> j).
    edit_cell(drv, "k_nrad_table.rows", 0, "to1", "0.5")
    params = m.to_parameters()
    assert len(params["k_nrad"]) == 9 and params["k_nrad"][1] == 0.5
    # Diagonal (self-transition) stays fixed at 0.
    row1 = m.k_nrad_table.rows()[1]
    assert not m.k_nrad_table.cell_editable(row1, "to1")
    edit_cell(drv, "k_nrad_table.rows", 1, "to1", "9")
    assert m.k_nrad[4] == 0.0


def test_species_table_per_species_and_resizes_widget(make):
    """The per-species grid: values per species, follows the Species count, colours add columns."""
    drv = make(
        N_species=2,
        green_enabled=True,
        red_enabled=True,
        species_M=[10.0, 20.0],
        species_D=[1.0, 2.0],
        species_q=[100, 90, 80, 70, 0, 0, 50, 40, 30, 20, 0, 0],
    )
    m = drv.app.sim_setup.model
    assert "species_rows" in drv.app.item_rects
    assert len(m.species_rows()) == 3  # 2 species + Background row
    # Brightness/M/D are per-species (not replicated).
    out = m.to_parameters()
    assert out["M"] == [10.0, 20.0] and out["D"] == [1.0, 2.0]
    assert out["q"][:4] != out["q"][4:8]
    # Driving the Species field resizes the table.
    drv.click("n_species")
    drv.select_all()
    drv.type_text("3")
    drv.enter()
    drv.draw(3)
    assert len(m.species_rows()) == 4  # 3 species + Background
    assert len(m.to_parameters()["M"]) == 3
    # Enabling a colour adds its parallel/perpendicular brightness columns.
    before = [c["key"] for c in m.species_columns()]
    drv.click("yellow_enabled")
    drv.draw(3)
    assert m.yellow_enabled
    keys = [c["key"] for c in m.species_columns()]
    assert len(keys) == len(before) + 2
    # #, M, D, 3 colours x 2, and Decay
    assert keys[:3] == ["species", "M", "D"] and keys[-1] == "decay" and len(keys) == 10
    # The background row edits scalars, not the per-species store.
    m.bg_green_p = 0.005
    m.touched()
    bg = m.species_rows()[-1]
    assert bg["species"] == "BG" and bg["q0"] == pytest.approx(0.005)
    assert bg["M"] is None and not m.species_cell_editable(bg, "M")
    # The decay is a spectrum, so its column opens the editor on that row's species --
    # that is what removed a "which species" selector.
    decay = next(c for c in m.species_columns() if c["key"] == "decay")
    assert "species" in decay["description"].lower()
    m.species_cell_activated(m.species_rows()[1], "decay")
    drv.draw(2)
    assert drv.app.sim_setup.decay_window.open and drv.app.sim_setup.decay.cur == 1


def test_a_new_species_does_not_inherit_another_species_decay(make):
    """Species added after the stored decays start from the default, not a copy."""
    drv = make(N_species=3, decay_lifetimes=[[[1.0, 4.5]], [[1.0, 0.8]]])
    dialog = drv.app.sim_setup
    dialog.open_decay(0)
    lifetimes = dialog.decay.lifetimes
    assert lifetimes[0] == [[1.0, 4.5]]
    assert lifetimes[1] == [[1.0, 0.8]]
    assert lifetimes[2] == [[1.0, 3.2]]  # the default, not a copy


def test_the_decay_editor_opens_on_the_species_it_was_asked_for(make):
    """The per-row cell passes its row, so the editor opens on that species."""
    drv = make(N_species=3, decay_lifetimes=[[[1.0, 4.5]], [[1.0, 0.8]], [[1.0, 2.1]]])
    dialog = drv.app.sim_setup
    dialog.open_decay(2)
    drv.draw(3)
    assert dialog.decay.cur == 2
    assert dialog.decay.species == 3
    assert dialog.decay.spectrum_rows()[0]["lifetime"] == 2.1
    # Out-of-range is clamped rather than raising: the row count can change
    # between the table being built and the cell being activated.
    dialog.open_decay(99)
    assert dialog.decay.cur == 2


def test_picoquant_status_lists_each_device():
    """The PicoQuant card lists every detected device and its status, as the Qt dialog did."""
    from chisurf.plugins.core.acq.gui.setup_models import PicoQuantSetupModel

    class Api:
        def detect_devices(self):
            return [
                {"device_id": "MultiHarp150-1", "status": "ready"},
                {"device_id": "MultiHarp150-2", "status": "busy"},
            ]

    class Device:
        api = Api()

    setup = PicoQuantSetupModel(Device(), 100_000)
    setup.detect_status()
    lines = setup.status.splitlines()
    assert lines[0] == "PicoQuant API reports 2 device(s):"
    assert lines[1] == "Device: MultiHarp150-1  Status: ready"
    assert lines[2] == "Device: MultiHarp150-2  Status: busy"
