"""Native phasor scientific parity, snapshot safety and real output persistence."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np


def fake_compute(filename, windows, kind, params=None, progress=None):
    assert kind == "phasor"
    assert params["frequency"] == 80
    if progress:
        progress(0.5, "Phasor reference")
    return {
        name: {
            "g": np.array([[0.3, 0.7], [0.3, 0.7]]),
            "s": np.full((2, 2), 0.45),
            "n_photons": np.ones((2, 2)) * 20,
            "intensity": np.ones((2, 2)) * 20,
            "frames": np.ones((3, 2, 2)),
            "g_frames": np.ones((3, 2, 2)) * 0.3,
            "s_frames": np.ones((3, 2, 2)) * 0.45,
        }
        for name in windows
    }


def populated(monkeypatch):
    from chisurf.core.fluorescence import imaging
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.app import make_app

    monkeypatch.setattr(imaging, "compute_windows", fake_compute)
    app = make_app()
    app.model.frequency = 80
    app.model.filename = "fake.ptu"
    app.model.detectors = {
        "green": {"chs": [0]},
        "red": {"chs": [1], "micro_time_ranges": [[1, 128]], "irf": ["reference.ptu"]},
    }
    app.model.compute_job()
    return app


def test_snapshot_calibration_all_windows_and_cancellation(monkeypatch):
    from chisurf.core.fluorescence import imaging
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.app import make_app

    monkeypatch.setattr(imaging, "compute_windows", fake_compute)
    app = make_app()
    app.model.frequency = 80
    app.model.filename = "fake.ptu"
    app.model.detectors = {"green": {"chs": [0]}, "red": {"chs": [1], "irf": ["irf.ptu"]}}
    assert app.start("compute_job")
    app.job.thread.join(10)
    assert not app.model._columns
    app.job.poll()
    assert not app.job.error
    assert set(app.model._by_window) == {"green", "red"}
    assert "g (red)" in app.model._columns
    assert app.model.detectors["red"]["irf"] == ["irf.ptu"]
    assert not app.model.needs_recompute()
    old = app.model.g_map().copy()
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, progress=None, **kwargs):
        entered.set()
        assert release.wait(5)
        progress(0.5, "Cancel checkpoint")
        return {}

    monkeypatch.setattr(imaging, "compute_windows", blocked)
    app.model.n_ph_min += 1
    app.start("compute_job")
    assert entered.wait(5)
    app.key("Escape")
    release.set()
    app.job.thread.join(5)
    app.job.poll()
    assert "cancelled" in app.job.error
    np.testing.assert_array_equal(app.model.g_map(), old)


def test_all_views_help_import_export_keyboard_tooltip_and_locale(monkeypatch, tmp_path):
    from emtk import i18n, im
    from emtk.testing import RecordingPainter

    from chisurf.core.roi import EllipseROI
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.app import MAPS

    app = populated(monkeypatch)
    app.model.cursors.add(EllipseROI(0.3, 0.45, 0.1, 0.1, name="Population"))
    assert app.model.cursor_mask().sum() == 2
    tips = []
    original = im.set_item_tooltip
    monkeypatch.setattr(
        im,
        "set_item_tooltip",
        lambda text, *a, **k: (tips.append(text), original(text, *a, **k))[-1],
    )
    for key in MAPS:
        app.docks.focus(key)
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert any("modulation" in t.lower() for t in tips)
    assert any("density" in t.lower() for t in tips)
    app.help.show()
    app.tour.start()
    app.draw(RecordingPainter(), 0, 0, 800, 600)
    app.help.hide()
    app.tour.stop()
    for locale in ("en", "de", "fr", "es", "pt", "ru"):
        i18n.set_locale(locale)
        app.draw(RecordingPainter(), 0, 0, 800, 600)
    i18n.set_locale("en")
    path = tmp_path / "cursors.json"
    app.model.cursors.save(str(path))
    from chisurf.core.roi import RegionCollection

    restored = RegionCollection.load(str(path))
    assert restored.to_dict() == app.model.cursors.to_dict()
    app.choose("setup")
    app.dialog.draw = lambda: [str(tmp_path / "setup.json")]
    (tmp_path / "setup.json").write_text(json.dumps({"detectors": {"green": {"chs": [2]}}}))
    app.draw(RecordingPainter(), 0, 0, 800, 600)
    assert app.model.detectors["green"]["chs"] == [2]
    jobs = []
    monkeypatch.setattr(app, "start", lambda method, *args: jobs.append(method) or True)
    from emtk.events import CONTROL_MODIFIER

    assert app.key("Enter", modifiers=CONTROL_MODIFIER)
    assert jobs == ["compute_job"]
    app.choose("gates_save")
    app.draw(RecordingPainter(), 0, 0, 800, 600)


def test_state_restores_before_snapshot_and_pipeline_ndx(monkeypatch):
    from chisurf.core.datastore import row_count
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.app import make_app

    app = populated(monkeypatch)
    app.model.n_ph_min = 12
    app.canvases["g"].gamma = 1.7
    state = app.export_settings()
    restored = make_app()
    starts = []
    monkeypatch.setattr(
        restored,
        "start",
        lambda method, *args: (
            starts.append((restored.model.frequency, restored.model.n_ph_min)) or True
        ),
    )
    restored.restore_settings(state)
    assert starts == [(80, 12)]
    assert restored.canvases["g"].gamma == 1.7
    seen = []
    app.ndx_callback = seen.append
    app.open_ndx()
    assert row_count(seen[0]) == 4

    class Coordinator:
        def set_pipeline(self, **kwargs):
            seen.append(kwargs)

        def advance_from(self, role):
            seen.append(role)

    app.coordinator = Coordinator()
    app.next_step()
    assert seen[-1] == "pixel_phasor"


def test_real_leica_phasor_parity_hdf5_pto(tmp_path):
    from chisurf.core.datastore import numeric_column, row_count
    from chisurf.core.fio.pto import Measurement
    from chisurf.core.fluorescence.imaging import read_imaging_table
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.native_model import NativePhasorModel
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.view_model import PhasorImgViewModel

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    qt_model = PhasorImgViewModel()
    qt_model.filename = str(target)
    qt_model.run()
    native = NativePhasorModel()
    native.load_file(str(target))
    native.compute_job()
    for field in ("g", "s", "n_photons"):
        np.testing.assert_array_equal(native._disp(field), qt_model._disp(field))
    assert native.g_map().shape == native.s_map().shape
    out = tmp_path / "phasor.imaging.h5"
    native.save_hdf5(out)
    table = read_imaging_table(str(out))
    assert row_count(table) == native.g_map().size
    np.testing.assert_array_equal(numeric_column(table, "g (ch0)"), native.g_map().ravel())
    native.save_container()
    with Measurement.open(target.with_suffix(".pto")) as container:
        persisted = container.get_store("phasor")
        np.testing.assert_array_equal(numeric_column(persisted, "s (ch0)"), native.s_map().ravel())


def test_factory_with_qt_forbidden():
    import os
    import subprocess
    import sys

    code = r"""
import sys
class BlockQt:
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden '+name)
sys.meta_path.insert(0,BlockQt())
from chisurf.plugins.microscopy.img_pixel_phasor.gui.app import make_app,MAPS
from emtk.testing import RecordingPainter
import numpy as np
app=make_app();app.model._by_window={'green':{k:np.ones((16,20)) for k in ('g','s','n_photons','intensity')}}
app.model._by_window['green'].update({k:np.ones((3,16,20)) for k in ('frames','g_frames','s_frames')});app.model.display_window='green'
app.model.filename='fake.ptu';app.model._columns={'g (green)':np.ones((16,20))}
for size in [(1200,800),(800,600)]:
 for key in MAPS:
  app.docks.focus(key);app.draw(RecordingPainter(),0,0,*size)
app.open_ndx();assert app.view_ndx,app.error
app.draw(RecordingPainter(),0,0,1200,800)
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_density_uv_and_movie_scatter_use_scientific_coordinates(monkeypatch):
    from emtk import implot
    from emtk.testing import RecordingPainter

    app = populated(monkeypatch)
    app.docks.focus("plane")
    images = []
    original = implot.plot_image

    def record_image(label, texture, bmin, bmax, **kwargs):
        images.append((bmin, bmax, kwargs))
        return original(label, texture, bmin, bmax, **kwargs)

    monkeypatch.setattr(implot, "plot_image", record_image)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert images[-1][2] == {"uv0": (0, 1), "uv1": (1, 0)}
    app.scatter = True
    app.docks.focus("plane_movie")
    app.canvases["plane_movie"].z = 1
    app.model._by_window["green"]["g_frames"][1] = 0.9
    app.model._by_window["green"]["s_frames"][1] = 0.15
    points = []
    original_scatter = implot.plot_scatter

    def record_scatter(label, x, y, *args, **kwargs):
        points.append((x.copy(), y.copy()))
        return original_scatter(label, x, y, *args, **kwargs)

    monkeypatch.setattr(implot, "plot_scatter", record_scatter)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    np.testing.assert_array_equal(points[-1][0], np.full(4, 0.9))
    np.testing.assert_array_equal(points[-1][1], np.full(4, 0.15))
