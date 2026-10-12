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
    model.lifetime.new_amplitude = 0.25
    model.lifetime.new_value = 3.5
    model.lifetime.add()
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


def test_example_global_fit_recovers_the_simulated_lifetime_and_rotation(tmp_path, monkeypatch):
    """Load example, load, create the linked fits and fit: tau, rho and r0 come back."""
    import chisurf
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.demo import DEMO

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    model = NativeAnisotropyModel()
    model.example_folder = tmp_path
    model.load_example()
    assert model.files_ready()
    assert model.load_data()
    result = model.create_fits()
    assert result is not None, model.status
    vv, vh, global_fit = result
    for fit in (vv, vh):
        fit.fit_range = (20, DEMO["n_tac"] - 20)
    global_fit.run()
    values = {p.canonical_id: p.value for p in vv.model.parameters_all}
    assert values["lifetime.tau.0"] == pytest.approx(DEMO["tau_ns"], rel=0.03)
    assert values["rotation.time.0"] == pytest.approx(DEMO["rho_ns"], rel=0.05)
    assert values["anisotropy.r0"] == pytest.approx(DEMO["r0"], rel=0.05)
    # The fit must also *describe* the data: before the IRF window the model sat ~25 counts
    # above data that are zero and this range gave chi2r 27.6 with the parameters still "right".
    assert global_fit.chi2r < 1.3, global_fit.chi2r


def test_example_fit_with_the_readers_range_is_a_good_fit_and_recovers_the_truth(
    tmp_path, monkeypatch
):
    """Load example → Create fits → Fit, untouched: chi2r ~1 and the simulated tau, rho, r0 (found 2026-10-11).

    The model clips the background-subtracted IRF at zero; over the whole range that keeps the
    positive half of the tail noise, a flat pedestal the convolution turned into a constant
    offset under the decay (chi2r 4.2, r0 0.347 against 0.38). The wizard now restricts each IRF
    to the channels it occupies (the model's IRF start/stop).
    """
    import chisurf
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.demo import DEMO

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    model = NativeAnisotropyModel()
    model.example_folder = tmp_path
    model.load_example()
    assert model.load_data()
    vv, vh, global_fit = model.create_fits()
    start, stop = vv.model.get_scalar("response_start"), vv.model.get_scalar("response_stop")
    assert 0 < start < DEMO["irf_mean_ns"] < stop < DEMO["irf_mean_ns"] + 1.0
    global_fit.run()
    assert global_fit.chi2r < 1.2, global_fit.chi2r
    values = {p.canonical_id: p.value for p in vv.model.parameters_all}
    assert values["lifetime.tau.0"] == pytest.approx(DEMO["tau_ns"], rel=0.02)
    assert values["rotation.time.0"] == pytest.approx(DEMO["rho_ns"], rel=0.03)
    assert values["anisotropy.r0"] == pytest.approx(DEMO["r0"], rel=0.03)
    # where the data are ~0 (before the pulse) the model is too, not a constant ~25 counts
    model_y, data_y = np.asarray(vv.model.y), np.asarray(vv.data.y)
    assert abs(model_y[25] - data_y[25]) < 5


def test_load_example_is_cached_and_releases_the_tour_step(tmp_path):
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.demo import make_demo
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import AnisotropyApp

    first = make_demo(tmp_path)
    stamp = first.stat().st_mtime_ns
    assert make_demo(tmp_path) == first and first.stat().st_mtime_ns == stamp
    app = AnisotropyApp(NativeAnisotropyModel())
    app.model.example_folder = tmp_path
    app.tour.start(1)
    assert app.tour.awaiting
    app.load_example()
    assert not app.tour.awaiting and app.model.files_ready()


def test_created_fits_can_be_run_as_created(tmp_path, monkeypatch):
    """*Create fits* then *Fit*, with nothing set by hand (found 2026-10-11).

    The created fits had the range (0, 0), so the user's Fit failed with
    "9 parameters against 0 residuals"; the test above set the range itself.
    """
    import chisurf

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    model = NativeAnisotropyModel()
    model.example_folder = tmp_path
    model.load_example()
    assert model.load_data()
    vv, vh, global_fit = model.create_fits()
    for fit in (vv, vh, global_fit):
        xmin, xmax = fit.fit_range
        assert xmax - xmin > 100, (fit.name, fit.fit_range)
    chi2_start = global_fit.chi2r
    global_fit.run()
    assert global_fit.chi2r < chi2_start / 100
