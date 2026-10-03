"""Actual map simulation/export, native pointer controls and Qt isolation."""

import json
import os
import subprocess
import sys
import threading

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.microscopy.clsm_generator.gui.app import make_app


def populated(tmp_path):
    app = make_app()
    y, x = np.indices((8, 8))
    intensity = 0.2 + np.exp(-0.5 * (((x - 4) / 2) ** 2 + ((y - 4) / 2) ** 2))
    for name, value in [
        ("intensity", intensity),
        ("life0", np.full((8, 8), 2.0)),
        ("life1", np.full((8, 8), 3.0)),
    ]:
        np.save(tmp_path / (name + ".npy"), value)
    assert app.load_maps([tmp_path / "intensity.npy"])
    assert app.load_maps([tmp_path / "life0.npy", tmp_path / "life1.npy"], lifetime=True)
    app.model.n_lifetime_levels = 2
    app.model.n_intensity_levels = 2
    app.model.brightness_scale = 100
    return app


def finish(app):
    app.job.thread.join(timeout=30)
    assert not app.job.thread.is_alive()
    app.job.poll()
    assert not app.job.busy
    assert not app.job.error, app.job.error


def test_qt_blocked_factory_and_populated_map_at_two_sizes():
    code = """
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden: '+fullname)
sys.meta_path.insert(0,BlockQt())
import numpy as np
from emtk.testing import RecordingPainter
from chisurf.plugins.microscopy.clsm_generator.gui.app import make_app
app=make_app()
app.model._intensity_in=np.arange(64).reshape(8,8)
for size in [(800,600),(1200,800)]:
    class Recorder(RecordingPainter):
        def image(self,*args):self.calls.append(('image',args))
    p=Recorder();app.draw(p,0,0,*size)
    assert any(call[0]=='image' for call in p.calls)
    assert 'Generate' in p.strings
assert not set(sys.modules)&{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}
"""
    result = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, env=os.environ.copy()
    )
    assert result.returncode == 0, result.stderr


def test_generate_unchanged_model_and_npz_pto_roundtrip(tmp_path):
    import tttrlib

    from chisurf.core.fio.fluorescence.imaging_container import read_image

    if not hasattr(tttrlib, "SimEngine"):
        pytest.skip("Photon simulator unavailable")
    app = populated(tmp_path)
    assert app.generate()
    app.job.thread.join(timeout=30)
    assert app.model._sim is None, "Worker mutated the displayed model"
    finish(app)
    assert app.model.has_result(), app.model.status_text
    assert app.model.current_view == "recon"
    assert app.model.current_view_image().shape == (8, 8)
    assert app.model.current_view_image().sum() > 0
    original = app.model._sim.tttr
    channels = np.asarray(original.routing_channels)
    assert {0, 1}.issubset(set(channels))
    assert app.save(tmp_path / "photons.npz")
    finish(app)
    with np.load(tmp_path / "photons.npz") as saved:
        np.testing.assert_array_equal(saved["macro_times"], original.macro_times)
        np.testing.assert_array_equal(saved["micro_times"], original.micro_times)
        np.testing.assert_array_equal(saved["routing_channels"], original.routing_channels)
    assert (tmp_path / "photons_intensity.tif").exists()
    assert app.save(tmp_path / "photons.pto")
    finish(app)
    assert "Saved" in app.model.status_text, app.model.status_text
    restored = tttrlib.TTTR(str(tmp_path / "photons.pto"))
    np.testing.assert_array_equal(restored.macro_times, original.macro_times)
    np.testing.assert_array_equal(restored.micro_times, original.micro_times)
    np.testing.assert_array_equal(
        read_image(tmp_path / "photons.pto", name="intensity"), app.model._sim.intensity
    )


def test_validation_paths_detectors_settings_and_output(tmp_path):
    app = populated(tmp_path)
    assert not app.validate()
    state = json.loads(json.dumps(app.state_dict()))
    app.model.pixel_size = 9
    app.model.sel_lifetime_files = []
    app.canvas.colormap = "gray"
    assert app.apply_state(state)
    assert app.model.pixel_size == 0.5
    assert len(app.model._lifetime_in) == 2
    app.model._lifetime_in[0][0, 0] = 0
    app.model._lifetime_in[0][0, 1] = np.nan
    assert not app.validate(), "The existing simulator skips masked lifetime pixels"
    assert app.canvas.colormap == "inferno"
    app.selected_lifetime = 0
    app.remove_lifetime()
    assert app.model.lifetime_paths == state["lifetime_paths"][1:]
    assert not app.load_maps([tmp_path / "missing.npy"], lifetime=True)
    assert "readable" in app.validate()
    app.model.sel_lifetime_files = [str(tmp_path / "life0.npy")]
    app.model._intensity_in[0, 0] = np.nan
    assert "finite" in app.validate()
    assert not app.save(tmp_path / "wrong.csv")
    app.model._sim = object()
    assert not app.save(tmp_path / "wrong.csv")
    assert "Choose .pto" in app.error
    assert not app.save(tmp_path / "missing-directory" / "test.pto")
    assert "directory" in app.error
    bad_state = dict(state, parameters=dict(state["parameters"], n_micro=10.5))
    with pytest.raises(ValueError, match="Non-integer"):
        app.apply_state(bad_state)


def test_mmfdb_lifetime_selection_uses_shared_dataset_paths(tmp_path):
    app = populated(tmp_path)
    app.model.sel_lifetime_files = []
    assert "image_data" in app.picker.kinds
    assert {"tif", "tiff", "npy", "npz"} == set(app.picker.formats)
    app.picker.on_paths([tmp_path / "life1.npy", tmp_path / "life0.npy"])
    assert app.model.lifetime_paths == [str(tmp_path / "life1.npy"), str(tmp_path / "life0.npy")]
    np.testing.assert_array_equal(app.model._lifetime_in[0], np.full((8, 8), 3.0))


def test_cancel_discards_result_and_preserves_previous(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.clsm_generator.gui.view_model import ClsmGeneratorViewModel

    entered, release = threading.Event(), threading.Event()

    def slow_generate(model):
        entered.set()
        release.wait(timeout=10)
        model._sim = "new result"
        model.status_text = "Generated replacement"
        model.notify("done")

    monkeypatch.setattr(ClsmGeneratorViewModel, "generate", slow_generate)
    app = populated(tmp_path)
    app.model._sim = "previous result"
    assert app.generate()
    assert entered.wait(timeout=5)
    app.job.cancel()
    assert not app.generate(), "Must not start a second C++ calculation during cancellation"
    release.set()
    finish(app)
    assert app.model._sim == "previous result"
    assert "canceled" in app.model.status_text


def test_native_hover_and_map_removal_action(tmp_path):
    from emtk.app import LEFT_BUTTON
    from emtk.im_core import Style

    app = populated(tmp_path)
    app.style = Style(tooltip_delay=0)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    x, y, w, h = app.item_rects["Remove selected"]
    cx, cy = x + w / 2, y + h / 2
    app.pointer_move(cx, cy)
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    assert "Remove the selected detector's lifetime map without deleting its file." in " ".join(
        painter.strings
    )
    app.pointer_press(cx, cy, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    app.pointer_release(cx, cy, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert len(app.model.lifetime_paths) == 1


def test_native_settings_save_dialog_real_pointer(tmp_path):
    from emtk.app import LEFT_BUTTON

    app = populated(tmp_path)
    app.choose("save_settings")
    app.dialog.directory = str(tmp_path)
    app.dialog.filename = "generator-state.json"
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 1200, 800)
    button = next(
        call for call in reversed(painter.calls) if call[0] == "text" and call[6] == "Save"
    )
    x, y = button[1] + button[3] / 2, button[2] + button[4] / 2
    app.pointer_press(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    app.pointer_release(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert (
        json.loads((tmp_path / "generator-state.json").read_text())["lifetime_paths"]
        == app.model.lifetime_paths
    )
    assert app.dialog is None


def test_all_six_locales_translate_generator_labels_and_tooltips():
    from emtk.i18n import set_locale, tr

    app = make_app()
    try:
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            set_locale(locale)
            painter = RecordingPainter()
            app.draw(painter, 0, 0, 1200, 800)
            assert tr("Add lifetime maps") in painter.strings
            assert tr("Output format") in painter.strings
            if locale != "en":
                assert tr("Add lifetime maps") != "Add lifetime maps"
                assert (
                    tr("Load the relative pixel brightness from TIFF, NPY or NPZ.")
                    != "Load the relative pixel brightness from TIFF, NPY or NPZ."
                )
    finally:
        set_locale("en")
