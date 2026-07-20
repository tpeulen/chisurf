"""GUI tests for the acquisition simulator setup dialog (decay + channels)."""

from __future__ import annotations


def _model(**params):
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        SimulationSettingsModel,
    )

    return SimulationSettingsModel.from_parameters(params)


def test_decay_dialog_roundtrip_widget(qapp, qtbot):
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        DecaySettingsDialog,
    )

    m = _model(N_species=2)
    dlg = DecaySettingsDialog(m)
    qtbot.addWidget(dlg)
    # Edit species 0 to a bi-exponential (amp, τ) through the shared editor + IRF.
    dlg.editor_model.spectrum_rows = [
        {"amplitude": 0.7, "lifetime": 1.2},
        {"amplitude": 0.3, "lifetime": 4.0},
    ]
    dlg.editor_model.irf_fwhm_ns = 0.3
    dlg._accept()

    assert m.decay_lifetimes[0] == [[0.7, 1.2], [0.3, 4.0]]
    assert m.irf_fwhm_ns == 0.3
    params = m.to_parameters()
    assert params["decay_lifetimes"][0] == [[0.7, 1.2], [0.3, 4.0]]
    assert len(params["decay_lifetimes"]) == 2  # sized to species count
    assert params["irf_fwhm_ns"] == 0.3


def test_decay_dialog_species_switch_preserves_edits(qapp, qtbot):
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        DecaySettingsDialog,
    )

    m = _model(N_species=2)
    dlg = DecaySettingsDialog(m)
    qtbot.addWidget(dlg)
    dlg.editor_model.spectrum_rows = [{"amplitude": 1.0, "lifetime": 1.1}]
    dlg.combo.setCurrentIndex(1)  # switch species → species 0 is saved
    dlg.editor_model.spectrum_rows = [{"amplitude": 1.0, "lifetime": 5.5}]
    dlg._accept()
    assert m.decay_lifetimes[0] == [[1.0, 1.1]]
    assert m.decay_lifetimes[1] == [[1.0, 5.5]]


def test_decay_dialog_load_pattern_widget(qapp, qtbot, tmp_path):
    import numpy as np

    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        DecaySettingsDialog,
    )

    pat = tmp_path / "decay.txt"
    np.savetxt(pat, np.exp(-np.arange(256) / 40.0))
    m = _model(N_species=1)
    dlg = DecaySettingsDialog(m)
    qtbot.addWidget(dlg)
    dlg.editor_model.pattern_path = str(pat)  # as the Pattern… button would set it
    dlg._accept()
    assert m.to_parameters()["decay_pattern_files"][0] == str(pat)


def test_kinetics_matrix_tracks_species_widget(qapp, qtbot):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    m = _model(N_species=2)
    form = AutoForm(m)
    qtbot.addWidget(form)
    m._sync_fields = form.sync_fields
    m._refresh_widgets = form.refresh_plots
    mats = form.findChildren(RateMatrixWidget)
    assert len(mats) == 2 and all(w.table.rowCount() == 2 for w in mats)
    # Changing the species count resizes both N×N matrices.
    m.n_species = 3
    m.species_changed()
    assert all(w.table.rowCount() == 3 for w in mats)
    # Edited rates flow into the emitted parameters (row-major i→j).
    knrad = next(w for w in mats if w._attr == "k_nrad")
    knrad._spins[(0, 1)].setValue(0.5)
    params = m.to_parameters()
    assert len(params["k_nrad"]) == 9 and params["k_nrad"][1] == 0.5
    # Diagonal (self-transition) stays fixed at 0.
    assert not knrad._spins[(1, 1)].isEnabled()


def test_species_table_per_species_and_resizes_widget(qapp, qtbot):
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        _SpeciesTable,
    )

    m = _model(N_species=2, green_enabled=True, red_enabled=True,
               species_M=[10.0, 20.0], species_D=[1.0, 2.0],
               species_q=[100, 90, 80, 70, 0, 0, 50, 40, 30, 20, 0, 0])
    form = AutoForm(m)
    qtbot.addWidget(form)
    table = form.findChild(_SpeciesTable)
    assert table is not None
    assert table.table.rowCount() == 3  # 2 species + Background row
    # Brightness/M/D are per-species (not replicated).
    out = m.to_parameters()
    assert out["M"] == [10.0, 20.0] and out["D"] == [1.0, 2.0]
    assert out["q"][:4] != out["q"][4:8]
    # Driving the Species spinbox resizes the table (via the framework refresh).
    n_field = next(w for w in form.findChildren(QtWidgets.QWidget)
                   if getattr(getattr(w, "_section", None), "attr", "") == "n_species")
    n_field.findChild(QtWidgets.QSpinBox).setValue(3)
    assert table.table.rowCount() == 4  # 3 species + Background
    assert len(m.to_parameters()["M"]) == 3
    # Enabling a colour adds its ∥/⊥ brightness columns.
    table._checks["yellow"].setChecked(True)
    assert table.table.columnCount() == 8  # M, D, G∥, G⊥, R∥, R⊥, Y∥, Y⊥
