"""Calibration math, detector isolation, asynchronous delivery and native rendering."""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from chisurf.plugins.microscopy.img_calibration.gui.app import make_app


def populated():
    app = make_app()
    app.apply_setup_settings(
        {"detectors": {"green": {"chs": [0, 1], "ch_p": [0], "ch_s": [1]}, "red": {"chs": [2, 3]}}}
    )
    app.model.filename = "source.ptu"
    app.add_irfs(["irf.ptu"])
    vv = np.array([2.0, 4.0, 8.0, 10.0, 6.0, 4.0, 2.0, 2.0])
    vh = np.array([1.0, 3.0, 5.0, 7.0, 5.0, 3.0, 1.0, 1.0])
    app.model._hist_cache[app.model._hist_key()] = {
        "n": 8,
        "data": vv + vh,
        "data_vv": vv,
        "data_vh": vh,
        "irf_vv_raw": vv,
        "irf_vh_raw": vh,
    }
    return app


def test_background_normalization_ranges_and_exact_transfer():
    app = populated()
    app.model.set_bg_range(0, 2)
    assert app.model.sel_bg_vv == 3
    assert app.model.sel_bg_vh == 2
    app.model.sel_shift_vv = 1
    app.model.set_conv_range(7, 1)
    app.model.set_irf_range(6, 2)
    decay = app.model.decay_data()
    np.testing.assert_array_equal(decay["data"], [3, 7, 13, 17, 11, 7, 3, 3])
    expected = np.clip(np.roll(np.array([2, 4, 8, 10, 6, 4, 2, 2]), 1) - 3, 0, None)
    np.testing.assert_allclose(decay["irf_vv"], expected / expected.sum())
    assert decay["irf_vh"].sum() == 1
    assert decay["conv"] == (1, 7) and decay["irf_range"] == (2, 6)
    published = []
    app.model.publish = published.append
    assert app.apply()
    assert published[0] == app.model.calibration
    app.model.sel_irf_files = ["changed.ptu"]
    assert published[0]["green"]["irf"] == ["irf.ptu"]
    app.model.display_detector = "red"
    assert app.model.sel_irf_files == [] and app.model.sel_bg_vv == 0
    state = app.export_settings()
    restored = make_app()
    restored.restore_settings(json.loads(json.dumps(state)))
    assert restored.export_settings() == state
    app.model.sel_conv_start = 9
    app.model.sel_conv_stop = 8
    assert not app.apply() and "range start must be smaller than stop" in app.apply_error


def test_async_cache_rejects_changed_detector_and_error_does_not_spin(monkeypatch):
    from chisurf.core.fluorescence import imaging

    started, finish = threading.Event(), threading.Event()
    calls = []

    def histogram(*args):
        calls.append(args)
        started.set()
        assert finish.wait(3)
        return {"n": 1}

    monkeypatch.setattr(imaging, "calibration_histograms", histogram)
    app = populated()
    app.model._hist_cache.clear()
    app.request_histograms()
    assert started.wait(2)
    app.apply_setup_settings({"detectors": {"green": {"chs": [5]}}})
    finish.set()
    for _ in range(100):
        if not app._messages.empty():
            break
        time.sleep(0.01)
    app.poll()
    assert not app.model._hist_cache, "Old channel histogram must not enter new detector cache"
    for _ in range(100):
        if not app._messages.empty():
            break
        time.sleep(0.01)
    app.poll()
    assert len(calls) == 2 and calls[-1][1] == [5]

    def broken(*args):
        raise ValueError("Unreadable source")

    monkeypatch.setattr(imaging, "calibration_histograms", broken)
    app.model._hist_cache.clear()
    app.request_histograms()
    for _ in range(100):
        if not app._messages.empty():
            break
        time.sleep(0.01)
    app.poll()
    assert not app.busy and app.error == "Unreadable source"
    app.poll()
    assert not app.busy


def test_real_leica_histograms_match_photon_arrays():
    import tttrlib

    from chisurf.core.fluorescence.imaging.pixel_maps import _calibration_hist_worker

    path = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    hist = _calibration_hist_worker(str(path), [0, 1], [0], [1], [str(path)])
    tttr = tttrlib.TTTR(str(path))
    channels = np.asarray(tttr.routing_channels)
    microtimes = np.asarray(tttr.micro_times)
    for name, selected in (("data", [0, 1]), ("data_vv", [0]), ("data_vh", [1])):
        chosen = microtimes[np.isin(channels, selected)]
        expected = np.bincount(chosen[chosen < hist["n"]], minlength=hist["n"])
        np.testing.assert_array_equal(hist[name], expected)
    np.testing.assert_array_equal(hist["irf_vv_raw"], hist["data_vv"])
    np.testing.assert_array_equal(hist["irf_vh_raw"], hist["data_vh"])


def test_populated_native_forbids_qt_and_six_locales():
    code = """
import sys,logging
errors=[]
class Errors(logging.Handler):
 def emit(self,record):
  if record.levelno>=logging.ERROR:errors.append(record.getMessage())
logging.getLogger().addHandler(Errors())
from chisurf.emtk.validation import BlockQt
sys.meta_path.insert(0,BlockQt())
from chisurf.plugins.microscopy.img_calibration.test.test_native import populated
from emtk.testing import RecordingPainter
from emtk.i18n import set_locale
app=populated()
for locale in ('en','de','fr','es','pt','ru'):
 set_locale(locale)
 for size in ((1200,800),(800,600)):
  p=RecordingPainter();app.draw(p,0,0,*size)
  assert p.strings
assert not errors,errors
assert not any(n.split('.')[0] in {'qtpy','PyQt5','PySide6','pyqtgraph'} for n in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(
        Path(__file__).resolve().parents[1].joinpath("gui/translations.json").read_text()
    )
    assert all(set(values) == set(data["en"]) for values in data.values())
    assert len(data) == 6


def test_coordinator_next_transfers_exact_calibration():
    class Coordinator:
        def __init__(self):
            self.calibration = None
            self.role = None

        def set_calibration(self, payload):
            self.calibration = payload

        def advance_from(self, role):
            self.role = role

    source = populated()
    source.model.set_conv_range(1, 7)
    source.model.set_irf_range(2, 6)
    source.model.set_bg_range(0, 2)
    coordinator = Coordinator()
    app = make_app(model=source.model, coordinator=coordinator)
    app.next_step()
    assert coordinator.calibration == app.model.calibration
    assert coordinator.role == "calibration"
    app.model.calibration["green"]["irf"].append("later.ptu")
    assert coordinator.calibration["green"]["irf"] == ["irf.ptu"]
