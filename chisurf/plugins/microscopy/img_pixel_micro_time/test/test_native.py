"""Real mean-time science, persistence, worker delivery and pure native UI."""
import os
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from chisurf.core.datastore import column_names, numeric_column, row_count

SOURCE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"


def test_real_microtime_threshold_movie_units_and_persistence(tmp_path):
    import tttrlib

    from chisurf.core.fio.pto import Measurement
    from chisurf.core.fluorescence.imaging import read_imaging_table
    from chisurf.plugins.microscopy.img_pixel_micro_time.gui.native_model import (
        NativeMicroTimeModel,
    )

    source = tmp_path / SOURCE.name
    source.write_bytes(SOURCE.read_bytes())
    model = NativeMicroTimeModel()
    model.load_file(str(source))
    model.compute_job()
    tttr = tttrlib.TTTR(str(source))
    clsm = tttrlib.CLSMImage(tttr, channels=[0], fill=True)
    ns = tttr.header.micro_time_resolution * 1e9
    expected = np.maximum(np.nan_to_num(clsm.get_mean_micro_time(tttr, ns, 2, True))[0], 0)
    np.testing.assert_allclose(model.mean_micro_time_map(), expected)
    frames = np.maximum(np.nan_to_num(clsm.get_mean_micro_time(tttr, ns, 2, False)), 0)
    np.testing.assert_allclose(model.mean_micro_time_frames(), frames)
    np.testing.assert_array_equal(model.intensity_map(), clsm.get_intensity_u32().sum(axis=0))
    assert model._column_units(model._columns)["mean_micro_time (ch0)"] == "nanoseconds"
    out = tmp_path / "mean.imaging.h5"
    model.save_hdf5(out)
    table = read_imaging_table(str(out))
    assert row_count(table) == expected.size
    assert "mean_micro_time (ch0)" in column_names(table)
    np.testing.assert_allclose(numeric_column(table, "mean_micro_time (ch0)"), expected.ravel())
    model.save_container()
    with Measurement.open(source.with_suffix(".pto")) as measurement:
        persisted = measurement.get_store("mean_micro_time")
        np.testing.assert_allclose(numeric_column(persisted, "mean_micro_time (ch0)"), expected.ravel())
    model.n_ph_min = 100000000
    assert model.needs_recompute()
    model.compute_job()
    assert not np.any(model.mean_micro_time_map())


def test_controls_setup_state_cancel_and_pipeline():
    from emtk.testing import RecordingPainter

    from chisurf.plugins.microscopy.img_pixel_micro_time.gui.app import make_app
    from chisurf.plugins.microscopy.img_pixel_micro_time.gui.native_model import (
        NativeMicroTimeModel,
    )

    app = make_app()
    assert app.canvases["mean"].image_label == "Mean micro-time"
    assert app.canvases["frames"].image_unit == "ns"
    assert app.canvases["intensity"].image_unit == "photons"
    assert app.configure_window("green", "0,1", 3, 100)
    assert app.model.detectors["green"]["micro_time_ranges"] == [(3, 100)]
    assert not app.configure_window("bad", "x", 3, 100)
    assert not app.configure_window("bad", "0", 100, 3)
    app.model.n_ph_min = 15
    app.canvases["mean"].gamma = 1.7
    restored = make_app()
    restored.restore_settings(app.export_settings())
    assert restored.model.n_ph_min == 15
    assert restored.model.detectors == app.model.detectors
    assert restored.canvases["mean"].gamma == 1.7
    entered, release = threading.Event(), threading.Event()

    class Waiting(NativeMicroTimeModel):
        def compute_job(self):
            entered.set()
            assert release.wait(5)
            self._columns = {"mean_micro_time (ch0)": np.ones((2, 2))}
            self.notify("run")

    app = make_app(model=Waiting())
    assert app.start("compute_job")
    assert entered.wait(5)
    app.cancel()
    release.set()
    app.job.thread.join(5)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert not app.model._columns and not app.job.busy
    assert "cancelled" in app.error
    seen = []

    class Coordinator:
        def set_pipeline(self, **kwargs):
            seen.append(kwargs)

        def advance_from(self, role):
            seen.append(role)

    app.coordinator = Coordinator()
    app.next_step()
    assert seen[-1] == "pixel_micro_time"


def test_hard_blocked_qt_populated_factory():
    script = r'''
import sys
class BlockQt:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'}: raise ImportError('Qt forbidden '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.microscopy.img_pixel_micro_time.gui.app import make_app
from chisurf.emtk.i18n import SUPPORTED_LOCALES,set_locale
app=make_app();app.model.load_file(sys.argv[1]);app.model.compute_job()
assert app.model.mean_micro_time_map().sum()>0
for locale in SUPPORTED_LOCALES:
 set_locale(locale)
 for size in ((1200,800),(800,600)):
  app.draw(RecordingPainter(),0,0,*size)
app.docks.focus('mean');app.draw(RecordingPainter(),0,0,1200,800)
app.docks.focus('frames');app.playing=True;app.draw(RecordingPainter(),0,0,1200,800)
app.help.show();app.tour.start();app.draw(RecordingPainter(),0,0,1200,800)
app.help.hide();app.tour.stop();app.choose('hdf5');app.draw(RecordingPainter(),0,0,1200,800)
app.dialog=None
app.ndx_callback=lambda table: None;app.open_ndx();assert not app.error
assert not any(x.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'} for x in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", script, str(SOURCE)], env=os.environ.copy(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_sp8_routing_gate_threshold_and_dropped_source(tmp_path):
    import tttrlib

    from chisurf.plugins.microscopy.img_pixel_micro_time.gui.app import make_app

    source = tmp_path / "Leica_SP8.ptu"
    source.write_bytes(SOURCE.with_name("Leica_SP8.ptu").read_bytes())
    app = make_app()
    assert app.configure_window("signal", "1", 0, 4096)
    assert app.on_files_dropped([str(source)])
    app.job.thread.join(15)
    app.job.poll()
    assert not app.job.busy and not app.job.error
    tttr = tttrlib.TTTR(str(source))
    expected = tttrlib.CLSMImage(tttr, channels=[1], fill=True).get_mean_micro_time(
        tttr, tttr.header.micro_time_resolution * 1e9, 2, True
    )[0]
    np.testing.assert_allclose(app.model.mean_micro_time_map(), np.maximum(np.nan_to_num(expected), 0))
    assert np.any(app.model.mean_micro_time_map() > 0)
    assert app.model.mean_micro_time_frames().shape[-2:] == (512, 512)
