"""Native anisotropy files, normalization, components and real linked fits."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel


def configured_model(tmp_path):
    model = NativeAnisotropyModel()
    model.bin_width = 0.1
    model.first_column_is_time = True
    x = np.arange(128) * 0.1
    values = {
        "irf_vv": np.exp(-0.5 * ((x - 2) / 0.3) ** 2) * 100 + 2,
        "irf_vh": np.exp(-0.5 * ((x - 2) / 0.3) ** 2) * 60 + 3,
        "data_vv": np.exp(-x / 4) * 1000 + 5,
        "data_vh": np.exp(-x / 4) * 500 + 5,
    }
    for key, y in values.items():
        path = tmp_path / f"{key}.txt"
        np.savetxt(path, np.column_stack((x, y)), header="time_ns counts")
        setattr(model, key + "_path", str(path))
    return model


def test_native_load_normalize_export_and_component_order(tmp_path):
    from chisurf.core.fio.vv_vh import read_vv_vh

    model = configured_model(tmp_path)
    assert model.load_data()
    model.apply_region(100, 50)
    assert (model.region_lb, model.region_ub) == (50, 100)
    vv, vh = model.data["irf_vv_bg_norm"], model.data["irf_vh_bg_norm"]
    assert vv.y.sum() == pytest.approx(vh.y.sum())
    assert vv.unique_identifier != model.data["irf_vv"].unique_identifier
    path = tmp_path / "normalized.dat"
    model.export_irfs(path)
    saved, metadata = read_vv_vh(path, split=True, return_metadata=True)
    assert np.allclose(saved["VV"], vv.y)
    assert metadata["dt"] == pytest.approx(0.1)
    model.new_lifetime_amplitude = 0.25
    model.new_lifetime_value = 3.5
    model.add_lifetime()
    assert model.lifetime_spectrum[-1] == [0.25, 3.5]
    spectra = tmp_path / "components.spk.json"
    model.save_spectra(spectra)
    model.lifetime_spectrum = []
    model.load_spectra(str(spectra))
    assert model.lifetime_spectrum[-1] == [0.25, 3.5]


def test_native_real_fit_parameters_links_and_global_references(tmp_path, monkeypatch):
    import chisurf
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.core.native_fits import LocalLinkClient

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    model = configured_model(tmp_path)
    model.load_data()
    model.g_factor, model.l1, model.l2 = 1.5, 0.03, 0.07
    result = model.create_fits()
    assert result is not None, model.status
    vv, vh, global_fit = result
    assert len(chisurf.fits) == 3
    assert len(chisurf.imported_datasets) == 4
    assert global_fit.model.fits == [vv, vh]
    assert vv.model.anisotropy.polarization_type == "vv"
    assert vh.model.anisotropy.polarization_type == "vh"
    parameters = {p.canonical_id: p for p in vv.model.parameters_all}
    assert parameters["lifetime.amplitude.0"].value == pytest.approx(0.3)
    assert parameters["lifetime.tau.1"].value == pytest.approx(4.1)
    assert parameters["rotation.amplitude.0"].value == pytest.approx(0.28)
    assert parameters["rotation.time.1"].value == pytest.approx(10.0)
    assert parameters["anisotropy.g"].value == pytest.approx(1.5)
    client = LocalLinkClient([vv, vh])
    for name in ("n0", "xL1", "tL2", "rho(1)", "b(2)", "g", "l1", "l2"):
        assert client.parameter(1, name).link is client.parameter(0, name)
    assert client.parameter(0, "g").fixed
    assert client.parameter(1, "lb").fixed
    assert not client.parameter(0, "n0").fixed
    assert np.isfinite(vv.model.y).all()
    assert vv.model.convolve.irf is model.data["irf_vv_bg_norm"]


def test_native_preferences_roundtrip_and_stale_inputs_require_reload(tmp_path, monkeypatch):
    import chisurf

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    model = configured_model(tmp_path)
    model.g_factor = 1.4
    state = model.export_preferences()
    restored = NativeAnisotropyModel()
    restored.restore_preferences(state)
    assert restored.g_factor == pytest.approx(1.4)
    assert restored.data_vv_path == model.data_vv_path
    model.load_data()
    model.bin_width = 0.2
    assert model.create_fits() is None
    assert "reload" in model.status
    assert not chisurf.fits and not chisurf.imported_datasets


def test_native_every_step_dialog_and_workflow_without_qt(tmp_path):
    model = configured_model(tmp_path)
    state = model.export_preferences()
    script = f"""
import importlib.abc,sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:
            raise RuntimeError('Qt imported: '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app
app=make_app()
app.model.restore_preferences({state!r})
app.model.load_data()
for index in range(6):
    app.select_step(index)
    app.draw(RecordingPainter(),0,0,1200,900)
app.choose('load_spectra')
app.draw(RecordingPainter(),0,0,1200,900)
app.dialog=None
assert app.model.create_fits() is not None,app.model.status
assert 'chisurf.gui' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_stacked_files_select_both_channels_and_preserve_header_dt(tmp_path):
    from chisurf.core.fio.vv_vh import write_vv_vh

    n = 64
    irf_vv = np.arange(n, dtype=float) + 2
    irf_vh = np.arange(n, dtype=float) * 2 + 3
    data_vv = np.arange(n, dtype=float) * 3 + 5
    data_vh = np.arange(n, dtype=float) * 4 + 7
    irf = tmp_path / "irf.dat"
    data = tmp_path / "data.dat"
    write_vv_vh(irf, vv=irf_vv, vh=irf_vh, metadata={"dt": 0.1})
    write_vv_vh(data, vv=data_vv, vh=data_vh, metadata={"dt": 0.1})
    model = NativeAnisotropyModel()
    model.stacked_files = True
    model.bin_width = 0.2
    model.irf_vv_path = str(irf)
    model.data_vv_path = str(data)
    assert model.files_ready()
    model.load_data()
    assert np.allclose(model.data["data_vv"].y, data_vv)
    assert np.allclose(model.data["data_vh"].y, data_vh)
    assert np.diff(model.data["data_vh"].x).mean() == pytest.approx(0.1)
