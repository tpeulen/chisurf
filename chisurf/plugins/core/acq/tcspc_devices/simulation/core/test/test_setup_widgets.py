"""GUI tests for the acquisition simulator setup dialog (decay + channels)."""

from __future__ import annotations

import pytest


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
    """The per-species grid is the general ``state_table`` section now.

    Same contract as the bespoke table it replaced: values are per species and
    not replicated, the grid follows the Species count, and enabling a colour
    adds its parallel/perpendicular brightness columns — the last one now
    crossing a seam, since the switches and the grid are separate widgets that
    agree only through ``species_columns()``.
    """
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.state_table_section import StateTableWidget
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        _ChannelSwitches,
    )

    m = _model(N_species=2, green_enabled=True, red_enabled=True,
               species_M=[10.0, 20.0], species_D=[1.0, 2.0],
               species_q=[100, 90, 80, 70, 0, 0, 50, 40, 30, 20, 0, 0])
    form = AutoForm(m)
    qtbot.addWidget(form)
    table = form.findChild(StateTableWidget)
    switches = form.findChild(_ChannelSwitches)
    assert table is not None and switches is not None
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
    # Enabling a colour adds its parallel/perpendicular brightness columns.
    switches._checks["yellow"].setChecked(True)
    assert table.table.columnCount() == 9  # M, D, 3 colours x 2, and Decay
    # The background row edits scalars, not the per-species store.
    m.bg_green_p = 0.005
    table.refresh()
    assert table._cells[(3, 2)].value() == pytest.approx(0.005)
    # The decay is a spectrum, so its column is a per-row button rather than a
    # cell -- that is what removed the dialog's "which species" selector.
    decay = table.table.cellWidget(0, 8)
    assert isinstance(decay, QtWidgets.QToolButton)
    assert "species" in decay.toolTip().lower()


def test_a_new_species_does_not_inherit_another_species_decay(qapp, qtbot):
    """Species added after the stored decays start from the default, not a copy.

    The editor used to index ``decay_lifetimes[i % len(...)]``, so a third
    species silently showed the *first* species' spectrum -- a copy nothing on
    screen distinguished from a value someone had entered. Padding with the
    default makes an unset species look unset.
    """
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        DecaySettingsDialog,
    )

    m = _model(N_species=3, decay_lifetimes=[[[1.0, 4.5]], [[1.0, 0.8]]])
    dialog = DecaySettingsDialog(m)
    qtbot.addWidget(dialog)
    assert dialog._lifetimes[0] == [[1.0, 4.5]]
    assert dialog._lifetimes[1] == [[1.0, 0.8]]
    assert dialog._lifetimes[2] == [[1.0, 3.2]]          # the default, not a copy


def test_the_decay_editor_opens_on_the_species_it_was_asked_for(qapp, qtbot):
    """The per-row button passes its row, so the editor opens on that species."""
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        DecaySettingsDialog,
    )

    m = _model(N_species=3, decay_lifetimes=[[[1.0, 4.5]], [[1.0, 0.8]], [[1.0, 2.1]]])
    dialog = DecaySettingsDialog(m, start_species=2)
    qtbot.addWidget(dialog)
    assert dialog._cur == 2
    assert dialog.combo.currentIndex() == 2
    assert dialog.editor_model.name == "Species 3"
    # Out-of-range is clamped rather than raising: the row count can change
    # between the table being built and the button being pressed.
    assert DecaySettingsDialog(m, start_species=99)._cur == 2
