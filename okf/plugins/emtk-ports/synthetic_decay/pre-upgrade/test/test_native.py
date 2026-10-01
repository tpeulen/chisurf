"""Native generator workflows, exports and pure fit registration."""
from pathlib import Path
import json
import subprocess
import sys

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app import SyntheticDecayApp


def test_native_export_and_spectrum_load(tmp_path):
    app = SyntheticDecayApp()
    spectrum = tmp_path / "spectrum.txt"
    np.savetxt(spectrum, [[.3, 1.2], [.7, 4.]], delimiter=",")
    app.model.load_spectrum(spectrum)
    assert [row["amp"] for row in app.model.spectrum_rows] == [.3, .7]
    app.model.generate()
    for extension in ("csv", "json", "npy"):
        path = tmp_path / f"decay.{extension}"
        app.model.save(path)
        assert path.exists()
        if extension == "json":
            assert json.loads(path.read_text())["y"] == app.model._y
        elif extension == "npy":
            assert np.allclose(np.load(path), app.model._y)
        else:
            assert np.loadtxt(path).shape == (app.model.n_bins, 2)


def test_native_vvvh_save_preserves_calibration_and_identity(tmp_path):
    from chisurf.core.fio.vv_vh import read_vv_vh

    app = SyntheticDecayApp()
    m = app.model
    m.set_polarization("vv/vh")
    m.g_factor, m.l1, m.l2 = 1.5, .03, .07
    m.generate()
    path = tmp_path / "pair.dat"
    m.save(path)
    channels, metadata = read_vv_vh(path, split=True, return_metadata=True)
    assert np.allclose(channels["VV"], m._vv)
    assert np.allclose(channels["VH"], m._vh)
    assert metadata["dt"] == pytest.approx(m.bin_width)
    assert metadata["g_factor"] == pytest.approx(1.5)
    group = m.build_dataset_group()
    assert group.unique_identifier
    assert all(curve.unique_identifier for curve in group)


def test_native_fit_registration_preserves_science(monkeypatch):
    import chisurf

    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    app = SyntheticDecayApp()
    m = app.model
    m.set_polarization("vv/vh")
    m.g_factor, m.l1, m.l2 = 1.5, .03, .07
    m.generate()
    m.send_to_fit()
    assert "Added" in m.status
    assert len(chisurf.fits) == len(chisurf.imported_datasets) == 1
    group = chisurf.fits[0]
    assert [f.model.get_scalar("polarization") for f in group.grouped_fits] == [1, 2]
    model = group.grouped_fits[0].model
    values = {p.canonical_id: p.value for p in model.parameters_all}
    assert values["anisotropy.g"] == pytest.approx(1.5)
    assert values["anisotropy.l1"] == pytest.approx(.03)
    assert values["anisotropy.l2"] == pytest.approx(.07)
    assert model.get_scalar("dt") == pytest.approx(m.bin_width)
    assert any(p.link is not None for p in group.grouped_fits[1].model.parameters_all)
    assert group.flr_metadata["source"] == "synthetic_decay"


def test_native_surface_and_actions_do_not_import_qt(tmp_path):
    script = f'''
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app import make_app
app=make_app()
app.model.generate()
app.draw(RecordingPainter(),0,0,1200,900)
app.model.save({str(tmp_path / 'decay.json')!r})
app.browse_irf()
app.draw(RecordingPainter(),0,0,1200,900)
app.dialog=None
app.model.set_polarization('vv/vh')
app.model.generate()
app.model.send_to_fit()
assert 'Added' in app.model.status, app.model.status
assert 'chisurf.gui' not in sys.modules
'''
    result = subprocess.run([sys.executable,"-c",script],cwd=Path(__file__).resolve().parents[5],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_data_keeps_original_calibration_after_input_edits(tmp_path):
    from chisurf.core.fio.vv_vh import read_vv_vh

    app = SyntheticDecayApp()
    m = app.model
    m.set_polarization("vv/vh")
    m.g_factor, m.bin_width = 1.5, .032
    m.generate()
    m.g_factor, m.bin_width = 3., .064
    m.set_polarization("vm")
    path = tmp_path / "original-pair.dat"
    m.save(path)
    channels, meta = read_vv_vh(path, split=True, return_metadata=True)
    assert len(channels["VV"]) == m.n_bins
    assert meta["g_factor"] == pytest.approx(1.5)
    assert meta["dt"] == pytest.approx(.032)
    group = m.build_dataset_group()
    assert len(group) == 2
    assert group.data_reader.dt == pytest.approx(.032)
    assert group.data_reader.g_factor == pytest.approx(1.5)


def test_native_panels_fold_and_detection_mode_reveals_corrections():
    from emtk.testing import RecordingPainter

    app = SyntheticDecayApp()
    app.draw(RecordingPainter(),0,0,1200,900)
    assert "Histogram.fold" in app.form.rects
    assert "g_factor" not in app.form.rects
    app.model.set_polarization("vv/vh")
    app.form.rects.clear()
    app.draw(RecordingPainter(),0,0,1200,900)
    assert "g_factor" in app.form.rects
    app.form.folds["Histogram"] = False
    app.form.rects.clear()
    app.draw(RecordingPainter(),0,0,1200,900)
    assert "n_bins" not in app.form.rects


def test_native_file_chooser_blocks_background_generate():
    from emtk.testing import RecordingPainter

    app = SyntheticDecayApp()
    app.draw(RecordingPainter(),0,0,1200,900)
    x,y,w,h = app.item_rects["generate"]
    app.browse_irf()
    app.press(x+w/2,y+h/2)
    app.draw(RecordingPainter(),0,0,1200,900)
    app.release()
    app.draw(RecordingPainter(),0,0,1200,900)
    assert not app.model._y
    assert app.dialog is not None
