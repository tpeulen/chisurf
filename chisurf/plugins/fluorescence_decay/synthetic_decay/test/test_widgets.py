"""GUI tests for the synthetic decay generator tool."""

from __future__ import annotations


def test_tool_builds_and_generates(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import SyntheticDecayTool

    tool = SyntheticDecayTool()
    qtbot.addWidget(tool)
    m = tool.model
    assert m.decay_series() == []  # nothing yet
    m.generate()
    series = m.decay_series()
    assert series and len(series[0]["y"]) == m.n_bins
    assert "Generated" in m.status


def test_spectrum_edit_add_remove(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    n0 = len(m.spectrum_rows)
    m.add_row()
    assert len(m.spectrum_rows) == n0 + 1
    m.update_spectrum(0, "tau", 3.5)
    assert m.spectrum_rows[0]["tau"] == 3.5
    m.selected_row = len(m.spectrum_rows) - 1
    m.remove_row()
    assert len(m.spectrum_rows) == n0


def test_shot_noise_path_changes_output(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.generate()
    ideal = list(m._y)
    m.shot_noise = True
    m.photon_count = 20000
    m.generate()
    noisy = list(m._y)
    assert ideal != noisy  # noisy realization differs from the ideal pattern
    assert sum(noisy) > 1.0  # counts, not a unit-sum pattern


# -- anisotropy (VM / VV-VH) --------------------------------------------------


def test_vm_mode_plots_decay_and_r(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    assert m.polarization == "vm"
    m.generate()
    series = m.decay_series()
    assert len(series) == 1 and series[0]["name"] == "decay"
    # r(t) line present in both modes, decaying from r0 = sum(b)
    aniso = m.aniso_series()
    assert len(aniso) == 1
    r = aniso[0]["y"]
    assert abs(r[0] - sum(row["b"] for row in m.rotation_rows)) < 1e-12


def test_vvvh_mode_plots_pair(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.set_polarization("vv/vh")
    assert m.is_vv_vh() and m.polarization == "vv/vh"
    m.g_factor = 1.6
    m.l1, m.l2 = 0.04, 0.07
    m.generate()
    series = m.decay_series()
    assert [s["name"] for s in series] == ["VV", "VH"]
    assert len(series[0]["y"]) == m.n_bins
    assert "VV/VH" in m.status


def test_vvvh_dataset_group_carries_calibration(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.set_polarization("vv/vh")
    m.g_factor = 1.6
    m.l1, m.l2 = 0.04, 0.07
    m.generate()
    group = m.build_dataset_group()
    assert group is not None and len(group) == 2
    assert group[0].name.endswith("VV") and group[1].name.endswith("VH")
    for curve in group:
        # the corrections travel with the data, the way the reader attaches them
        assert curve.meta_data["g_factor"] == 1.6
        assert curve.meta_data["l1"] == 0.04
        assert curve.meta_data["l2"] == 0.07
        assert curve.meta_data["polarization"] == "vv/vh"
        # bin width rides on the x axis (dx), where the convolve group reads it
        assert abs(float(curve.x[1] - curve.x[0]) - m.bin_width) < 1e-12
    assert group.meta_data["g_factor"] == 1.6


def test_vm_dataset_group_is_single_curve(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.generate()
    group = m.build_dataset_group()
    assert group is not None and len(group) == 1
    assert group.meta_data["polarization"] == "vm"


def test_send_to_fit_creates_polarized_group():
    """The *Fit group* action routes like a VV/VH data load.

    Dataset in, ``fit.add`` out: the two curves become one fit group whose
    members carry the vv/vh polarizations by group position and whose models
    start from the simulated g/l1/l2 — the corrections were attached to the
    dataset meta-data, which is where ``add_fit`` looks for them.
    """
    import chisurf as cs
    from chisurf.core.models.description import for_family
    from chisurf.macros import core_data, core_fit

    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.set_polarization("vv/vh")
    m.g_factor = 1.5
    m.l1, m.l2 = 0.05, 0.08
    m.generate()
    group = m.build_dataset_group()
    assert group is not None

    core_data.add_dataset(experiment_reader=None, dataset=group, _from_controller=True)
    dataset_index = len(cs.imported_datasets) - 1
    n_fits_before = len(cs.fits)
    core_fit.add_fit(
        dataset_indices=[dataset_index],
        model_name=for_family("tcspc_polarized").name,
        _skip_gui_creation=True,
    )
    fit_group = cs.fits[n_fits_before]
    try:
        # The description's group position: VV (1), VH (2) by member.
        polarizations = [f.model.get_scalar("polarization") for f in fit_group.grouped_fits]
        assert polarizations == [1, 2]
        # The corrections from the simulation landed on the fit's parameters.
        model = fit_group.grouped_fits[0].model
        values = {p.canonical_id: p.value for p in model.parameters_all}
        assert abs(values["anisotropy.g"] - 1.5) < 1e-9
        assert abs(values["anisotropy.l1"] - 0.05) < 1e-9
        assert abs(values["anisotropy.l2"] - 0.08) < 1e-9
        # ... and the bin width came in through the data's x axis.
        assert abs(model.get_scalar("dt") - m.bin_width) < 1e-9
    finally:
        del cs.fits[n_fits_before]
        del cs.imported_datasets[dataset_index]


def test_vvvh_save_writes_vv_vh_file(qapp, qtbot, tmp_path):
    import numpy as np

    from chisurf.core.fio.vv_vh import read_vv_vh
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.set_polarization("vv/vh")
    m.g_factor = 1.4
    m.l1, m.l2 = 0.03, 0.05
    m.generate()
    path = tmp_path / "pair.dat"
    saved = {}
    from qtpy import QtWidgets

    original = QtWidgets.QFileDialog.getSaveFileName

    def fake_save(*args, **kwargs):
        return str(path), ""

    QtWidgets.QFileDialog.getSaveFileName = staticmethod(fake_save)
    try:
        m.save()
    finally:
        QtWidgets.QFileDialog.getSaveFileName = original
    assert path.exists()
    vv, vh = read_vv_vh(path, split=True)
    assert np.allclose(vv, m._vv) and np.allclose(vh, m._vh)
    saved = m.aniso_metadata()
    assert saved["g_factor"] == 1.4 and saved["polarization"] == "vv/vh"