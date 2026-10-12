"""The emtk simulation setup dialog: every edit reaches the simulation the tool runs.

The tests drive the real pointer path (double-click a table cell, type, Enter, press OK) and then
check the simulated words, not just the settings dictionary: an edit that only changes a number
nobody reads would pass a dictionary comparison.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

W, H = 900, 1000


@pytest.fixture
def drv():
    """The acquisition app with its simulation setup dialog open."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    app = AcquisitionApp(AcquisitionNativeModel())
    ui = Driver(app, (W, H))
    ui.draw(3)
    ui.click("open_simulation_setup")
    ui.draw(3)
    assert app.sim_setup is not None and app.sim_setup.open
    yield ui
    app.close()


def cell(drv: Driver, source: str, row: int, key: str) -> tuple[float, float]:
    """Centre of cell (*row*, column *key*) of the dialog's table *source*."""
    dialog = drv.app.sim_setup
    control = (
        (dialog.decay_form if source == "spectrum_rows" else dialog.form).tables[source].control
    )
    bx, by, bw, _bh = control._body_box
    widths = control._column_widths(bw)
    x = bx
    for column, width in zip(control.visible_columns(), widths):
        if column.key == key:
            return x + width / 2.0, by + (row + 0.5) * control._row_h
        x += width
    raise KeyError(key)


def edit_cell(drv: Driver, source: str, row: int, key: str, text: str) -> None:
    """Double-click a cell, replace its text, press Enter."""
    x, y = cell(drv, source, row, key)
    drv.app.pointer_move(x, y)
    drv.draw(2)
    for clicks in (1, 2):
        drv.app.pointer_press(x, y, 1, 0, clicks)
        drv.draw(2)
        drv.app.pointer_release(x, y, 1)
        drv.draw(2)
    drv.select_all()
    drv.type_text(text)
    drv.enter()
    drv.draw(2)


def channel_counts(params: dict) -> dict[int, int]:
    """Photons per routing channel of a run of the production simulator."""
    from chisurf.plugins.core.acq.pipeline import PhotonDecoder
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
    )

    words = generate_spc132_uint32(params)
    _macro, _micro, channels = PhotonDecoder(PhotonDecoderRecord()).decode(words)
    values, counts = np.unique(channels, return_counts=True)
    return {int(v): int(c) for v, c in zip(values, counts)}


def PhotonDecoderRecord() -> int:
    """The record type the tool decodes the simulator's words as."""
    from chisurf.plugins.core.acq.pipeline import PipelineConfig

    return PipelineConfig().record_type


def test_every_control_group_of_the_qt_dialog_is_present(drv):
    """The control inventory of the Qt dialog, reachable in the emtk one."""
    rects = drv.app.item_rects
    for name in (
        # Acquisition
        "excitation_mode",
        "n_ph_max",
        "n_ph_per_file",
        "output_path",
        "seed_diffusion",
        "seed_emission",
        # Sample & brightness, channels, the species grid and its Decay cells
        "n_species",
        "green_enabled",
        "red_enabled",
        "yellow_enabled",
        "species_rows",
        # Geometry / Microtime
        "box_xy",
        "box_z",
        "focus_w0",
        "focus_z0",
        "dt",
        "n_tac_channels",
        "tac_dt",
        "laser_period",
        # Performance
        "per_molecule_skip",
        "fast_grid_bbox",
        "independent_molecules",
        "analytic_excitation",
        "psf_type",
        "psf_zR",
        "psf_file",
        "psf_r_step",
        "psf_z_step",
        "active_margin",
        "max_windows",
        "coast_safety",
        "min_coast_windows",
        "focus_threshold",
        # Tools
        "open_decay_dialog",
        "load_json",
        "save_json",
        "view_json",
        # Dialog buttons
        "sim_ok",
        "sim_cancel",
    ):
        assert name in rects, f"{name} is not drawn"
    # Kinetics sits in a fold that starts closed, as in the Qt dialog; opening it shows both grids.
    drv.click("Kinetics.fold")
    drv.draw(2)
    assert "k_rad_table.rows" in drv.app.item_rects and "k_nrad_table.rows" in drv.app.item_rects


def test_edits_reach_the_simulated_photons(drv):
    """Brightness, species count, rates and decay typed into the tables change the simulation."""
    app = drv.app
    drv.click("n_species")
    drv.select_all()
    drv.type_text("2")
    drv.enter()
    drv.draw(3)
    dialog = app.sim_setup
    assert dialog.model.n_species == 2

    # Species 1: parallel green only; species 2 off. Background off, so counts are the species'.
    edit_cell(drv, "species_rows", 0, "q0", "300")
    edit_cell(drv, "species_rows", 0, "q1", "0")
    edit_cell(drv, "species_rows", 1, "q0", "0")
    edit_cell(drv, "species_rows", 1, "q1", "0")
    edit_cell(drv, "species_rows", 2, "q0", "0")
    edit_cell(drv, "species_rows", 2, "q1", "0")
    edit_cell(drv, "species_rows", 0, "M", "7")
    assert dialog.model.species_q[:2] == [300.0, 0.0]
    assert dialog.model.species_M[0] == 7.0

    drv.click("Kinetics.fold")
    drv.draw(2)
    edit_cell(drv, "k_rad_table.rows", 0, "to1", "2.5")
    assert dialog.model.k_rad[1] == 2.5
    # the diagonal is not a rate: refused
    edit_cell(drv, "k_rad_table.rows", 0, "to0", "9")
    assert dialog.model.k_rad[0] == 0.0

    drv.click("sim_ok")
    drv.draw(3)
    assert not dialog.open

    params = app.model._editor_params()
    assert params["N_species"] == 2
    assert params["M"][0] == 7.0
    assert params["q"][:2] == [300.0, 0.0]
    assert params["k_rad"] == [0.0, 2.5, 0.0, 0.0]
    assert "Simulation setup applied" in app.model.status

    params["N_ph_max"] = 400
    counts = channel_counts(params)
    # Only the edited detector shows photons: the first one (green parallel, decoded as routing 8).
    assert set(counts) == {8}

    # Flip it: perpendicular only. The channel the photons land in follows the edit (the second
    # detector, green perpendicular, decoded as routing 9).
    again = dict(params, q=[0.0, 300.0, 0.0, 0.0], N_ph_max=400)
    assert set(channel_counts(again)) == {9}


def test_start_runs_the_dialogs_values(drv):
    """The tool's Start path simulates the dialog's parameters, not the ones it opened with."""
    from chisurf.plugins.core.acq.gui import app as app_module

    app = drv.app
    edit_cell(drv, "species_rows", 0, "q0", "0")
    edit_cell(drv, "species_rows", 0, "q1", "250")
    drv.click("sim_ok")
    drv.draw(3)
    seen = {}
    real = app_module.generate_spc132_uint32

    def spy(params):
        seen.update(params)
        return real(params)

    app_module.generate_spc132_uint32 = spy
    try:
        app.model.photon_limit = 300
        assert app.model.start()
        for _ in range(400):
            drv.draw(1)
            app.model.poll()
            if not app.model.running:
                break
            import time

            time.sleep(0.02)
    finally:
        app_module.generate_spc132_uint32 = real
    assert seen["q"][:2] == [0.0, 250.0]
    assert app.model.snapshot is not None and app.model.snapshot["total_photons"] > 0


def test_emission_seed_survives_apply(drv):
    """The dialog's emission seed is not overwritten by the tool's seed field."""
    app = drv.app
    drv.click("seed_emission")
    drv.select_all()
    drv.type_text("777")
    drv.enter()
    drv.draw(2)
    drv.click("sim_ok")
    drv.draw(3)
    assert app.model._editor_params()["rmt2seed"] == 777
    assert app.model.apply_tool_fields(app.model._editor_params())["rmt2seed"] == 777


def test_decay_editor_writes_lifetimes_back_on_ok_only(drv):
    """Decay cell -> editor -> OK writes the spectrum; Cancel discards."""
    dialog = drv.app.sim_setup
    drv.click("open_decay_dialog")
    drv.draw(3)
    assert dialog.decay_window.open
    edit = dialog.decay
    edit.add_component()
    drv.draw(2)
    edit_cell(drv, "spectrum_rows", 1, "lifetime", "0.9")
    assert edit.lifetimes[0][1][1] == 0.9
    drv.click("decay_cancel")
    drv.draw(2)
    assert len(dialog.model.decay_lifetimes[0]) == 1  # untouched

    drv.click("open_decay_dialog")
    drv.draw(3)
    dialog.decay.add_component()
    drv.draw(2)
    edit_cell(drv, "spectrum_rows", 1, "lifetime", "0.9")
    drv.click("decay_ok")
    drv.draw(2)
    assert dialog.model.decay_lifetimes[0][1] == [1.0, 0.9]
    params = dialog.model.to_parameters()
    assert params["decay_lifetimes"][0][1] == [1.0, 0.9]


def test_apply_is_refused_when_the_engine_rejects_it(drv, monkeypatch):
    """A parameter set the engine cannot build keeps the dialog open and says so."""
    from chisurf.plugins.core.acq.gui import app as app_module

    def reject(_params):
        raise ValueError("no engine")

    monkeypatch.setattr(app_module, "build_engine", reject)
    drv.click("sim_ok")
    drv.draw(3)
    assert drv.app.sim_setup.open
    assert "rejected" in drv.app.model.status.lower()


def test_view_json_shows_what_the_simulator_receives(drv):
    """View JSON toggles a read-only copy of the parameters under the form."""
    drv.click("view_json")
    drv.draw(3)
    assert "sim_json_view" in drv.app.item_rects
    assert drv.app.sim_setup.model.show_json is True


def test_save_and_load_json_round_trip(drv, tmp_path):
    """Save JSON then Load JSON restores an edited species table."""
    dialog = drv.app.sim_setup
    edit_cell(drv, "species_rows", 0, "M", "33")
    path = tmp_path / "sim.json"
    dialog.file_chosen("save", path)
    edit_cell(drv, "species_rows", 0, "M", "11")
    assert dialog.model.species_M[0] == 11.0
    dialog.file_chosen("load", path)
    drv.draw(3)
    assert dialog.model.species_M[0] == 33.0
    assert dialog.model.to_parameters()["M"][0] == 33.0


@pytest.mark.parametrize(
    ("locale", "title", "decay"),
    [
        ("de", "Simulationseinrichtung", "Zerfall"),
        ("fr", "Configuration de la simulation", "Déclin"),
    ],
)
def test_dialog_is_translated(locale, title, decay):
    """The dialog's title, section text and table headers come out in German and French."""
    from chisurf.emtk import i18n
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    i18n.install(locale)
    app = AcquisitionApp(AcquisitionNativeModel())
    try:
        ui = Driver(app, (W, H))
        ui.draw(3)
        ui.click("open_simulation_setup")
        shown = set(ui.draw(3).strings)
        assert any(title in s for s in shown), sorted(shown)[:40]
        assert decay in shown
    finally:
        app.close()
        i18n.install("en")
