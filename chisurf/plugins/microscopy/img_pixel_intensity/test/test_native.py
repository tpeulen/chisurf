"""Scientific columns, snapshot delivery and real scanner persistence."""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, numeric_column, row_count


def fake_compute(filename, windows, kind, progress=None):
    assert kind == "intensity"
    if progress:
        progress(0.5, "Window green")
    return {
        "green": {
            "n_par": np.array([[10.0, 20.0], [30.0, 40.0]]),
            "n_perp": np.array([[2.0, 4.0], [6.0, 8.0]]),
            "durations": np.array([0.004, 0.008]),
            "n_pixel": 2,
            "bg": 2.0,
            "frames": np.ones((3, 2, 2)),
        }
    }


def test_polar_counts_rates_background_and_snapshot(monkeypatch):
    from chisurf.core.fluorescence import imaging
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import make_app

    monkeypatch.setattr(imaging, "compute_windows", fake_compute)
    app = make_app()
    app.model.filename = "fake.ptu"
    app.model.detectors = {"green": {"chs": [0, 1], "ch_p": [0], "ch_s": [1]}}
    assert app.start("compute_job")
    app.job.thread.join(timeout=10)
    assert not app.job.thread.is_alive()
    assert not app.model._columns, "Worker modified visible model before delivery"
    app.job.poll()
    assert not app.job.error
    np.testing.assert_array_equal(app.model._columns["Ng-all"], [[12, 24], [36, 48]])
    np.testing.assert_allclose(app.model.count_rate_map(), [[4, 10], [7, 10]])
    np.testing.assert_array_equal(
        app.model._columns["Number of Photons"], app.model.intensity_map()
    )
    assert app.model.frame_stack().shape == (3, 2, 2)
    assert not app.model.needs_recompute()
    app.model.detectors["green"]["bg_vv"] = 1
    assert app.model.needs_recompute()


def test_native_population_forbids_qt(tmp_path):
    code = r"""
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden '+fullname)
sys.meta_path.insert(0,BlockQt())
import numpy as np
from emtk.testing import RecordingPainter
from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import make_app
app=make_app()
app.model._by_window={'green':{'intensity':np.ones((16,20)),'count_rate':np.ones((16,20))*3,'frames':np.ones((3,16,20))}}
app.model._columns={'Number of Photons':np.ones((16,20))}
app.model.display_window='green'
for size in [(900,650),(1200,800)]:
 p=RecordingPainter();app.draw(p,0,0,*size)
 assert 'Run' in p.strings and 'HDF5' in p.strings
app.docks.focus('rate');app.draw(RecordingPainter(),0,0,1200,800)
app.docks.focus('frames');app.playing=True;app._last_frame=0
app.draw(RecordingPainter(),0,0,1200,800);assert app.canvases['frames'].z==1
app.playing=False
app.help.show();app.tour.start();app.draw(RecordingPainter(),0,0,1200,800)
app.help.hide();app.tour.stop()
app.choose('hdf5');app.draw(RecordingPainter(),0,0,1200,800)
app.dialog=None
app.open_ndx();assert app.view_ndx,app.error
app.draw(RecordingPainter(),0,0,1200,800)
app.model.load_file(sys.argv[1]);app.model.compute_job()
assert app.model.intensity_map().sum()>0
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"),
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_real_leica_counts_hdf5_container(tmp_path):
    import tttrlib

    from chisurf.core.fio.pto import Measurement
    from chisurf.core.fluorescence.imaging import read_imaging_source, read_imaging_table
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.native_model import NativeIntensityModel

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    assert source.is_file(), "Required real reference image is unavailable"
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    model = NativeIntensityModel()
    model.load_file(str(target))
    model.compute_job()
    counts = model.intensity_map()
    assert counts.ndim == 2 and counts.sum() > 0
    original = tttrlib.TTTR(str(target))
    clsm = tttrlib.CLSMImage(original, channels=[0], fill=True)
    expected = clsm.get_intensity_u32().sum(axis=0)
    np.testing.assert_array_equal(counts, expected)
    out = tmp_path / "result.imaging.h5"
    model.save_hdf5(out)
    assert read_imaging_source(str(out)) == str(target)
    table = read_imaging_table(str(out))
    assert row_count(table) == counts.size
    assert "Number of Photons" in column_names(table)
    np.testing.assert_array_equal(numeric_column(table, "Number of Photons"), counts.ravel())
    model.save_container()
    with Measurement.open(target.with_suffix(".pto")) as container:
        persisted = container.get_store("intensity")
        assert row_count(persisted) == counts.size
        np.testing.assert_array_equal(
            numeric_column(persisted, "Number of Photons"), counts.ravel()
        )


def test_state_pipeline_and_native_ndx(monkeypatch):
    from chisurf.core.fluorescence import imaging
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import make_app

    monkeypatch.setattr(imaging, "compute_windows", fake_compute)
    app = make_app()
    app.model.filename = "fake.ptu"
    app.model.compute_job()
    app.canvases["frames"].z = 2
    app.canvases["rate"].gamma = 1.5
    state = app.export_settings()
    restored = make_app()
    restore_jobs = []
    monkeypatch.setattr(restored, "start", lambda method, *args: restore_jobs.append(method) or True)
    restored.restore_settings(state)
    assert restore_jobs == ["compute_job"]
    assert restored.canvases["frames"].z == 2 and restored.canvases["rate"].gamma == 1.5
    seen = []
    app.ndx_callback = seen.append
    app.open_ndx()
    assert row_count(seen[0]) == 4
    app.next_step()
    assert "pipeline" in app.error

    class Coordinator:
        def set_pipeline(self, **kwargs):
            seen.append(kwargs)

        def advance_from(self, role):
            seen.append(role)

    app.coordinator = Coordinator()
    app.next_step()
    assert seen[-1] == "pixel_intensity"
    app.job.busy = True
    pipeline_jobs = []
    monkeypatch.setattr(app, "start", lambda method, *args: pipeline_jobs.append(method) or True)
    app.apply_pipeline_context({"source": "later.ptu", "hdf5": "later.h5"})
    assert app.model.filename == "fake.ptu"
    app.job.busy = False
    from emtk.testing import RecordingPainter

    app.render_pending_context()
    assert app.model.filename == "later.ptu" and app.model.pipeline_hdf5 == "later.h5"
    assert pipeline_jobs == ["compute_job"]


def test_native_file_selection_does_not_compute_synchronously():
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.native_model import NativeIntensityModel

    model = NativeIntensityModel()
    calls = []
    model.run = lambda *args, **kwargs: calls.append((args, kwargs))
    model.load_file("selected.ptu")
    assert model.filename == "selected.ptu"
    assert not calls
    assert not model._columns and not model._by_window


def test_pipeline_update_during_compute_is_not_overwritten():
    import threading

    from emtk.testing import RecordingPainter

    from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import make_app
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.native_model import NativeIntensityModel

    entered = threading.Event()
    release = threading.Event()

    class Model(NativeIntensityModel):
        def compute_job(self):
            entered.set()
            assert release.wait(5)
            self._columns = {"Number of Photons": np.ones((2, 2))}
            self._by_window = {"old": {"intensity": np.ones((2, 2))}}
            self.notify("run")

    model = Model()
    model.filename = "old.ptu"
    app = make_app(model=model)
    app.start("compute_job")
    assert entered.wait(5)
    app.apply_pipeline_context({"source": "new.ptu", "hdf5": "new.h5"})
    assert model.filename == "old.ptu"
    release.set()
    app.job.thread.join(timeout=5)
    app.draw(RecordingPainter(), 0, 0, 900, 650)
    assert model.filename == "new.ptu" and model.pipeline_hdf5 == "new.h5"
    assert not model._columns and not model._by_window
