"""Scientific and workflow parity of the native N&B workstation."""

import copy
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from chisurf.core.fluorescence.imaging import nb_pipeline
from chisurf.core.roi import RectangleROI


def test_all_windows_snapshot_units_gates_cross_and_state(monkeypatch, tmp_path):
    from chisurf.core.fluorescence import imaging
    from chisurf.plugins.microscopy.img_pixel_nb.gui.app import make_app

    rng = np.random.default_rng(87)
    stack = rng.poisson(rng.poisson(6, (100, 6, 8)) * 0.5).astype(float)

    def compute(filename, windows, kind, params, progress):
        assert kind == "nb"
        out = {}
        for name, detector in windows.items():
            frames = stack * (1 + detector["chs"][0])
            maps = nb_pipeline(frames, params)
            out[name] = {**maps, "frames": frames, "intensity": frames.sum(0)}
            progress(0.5, name)
        return out

    monkeypatch.setattr(imaging, "compute_windows", compute)
    app = make_app()
    app.model.filename = str(tmp_path / "source.ptu")
    app.apply_setup_settings({"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}})
    assert app.start("compute_job")
    app.job.thread.join(10)
    assert not app.model._columns
    app.job.poll()
    assert not app.job.error
    assert set(app.model._by_window) == {"green", "red"}
    mean, variance = stack.mean(0), stack.var(0, ddof=1)
    np.testing.assert_allclose(app.model._by_window["green"]["B"], variance / mean)
    np.testing.assert_allclose(app.model._by_window["green"]["N"], mean**2 / variance)
    assert app.model.COLUMN_UNITS["B"] == "counts"
    assert app.model.COLUMN_UNITS["N"] == "dimensionless"
    app.model.gates.add(RectangleROI(0, 0, 100, 100, name="Population"))
    np.testing.assert_array_equal(app.model.gate_mask(), mean > 0)
    app.model.cross_window = "red"
    assert app.model.cross_brightness_map().shape == mean.shape
    assert app.model.cross_number_map().shape == mean.shape
    app.model.gamma = 0.3536
    saved = app.export_settings()
    restored = make_app()
    restored.restore_settings(saved)
    assert restored.model.gamma == 0.3536
    assert restored.model.detectors == app.model.detectors
    assert len(restored.model.gates) == 1
    snapshot = copy.copy(app.model)
    snapshot.detectors["green"]["chs"].append(7)
    snapshot.gates.clear()
    assert app.model.detectors["green"]["chs"] == [0]
    assert len(app.model.gates) == 1
    ndx = []
    app.ndx_callback = ndx.append
    app.open_ndx()
    assert len(ndx) == 1

    class Pipeline:
        def set_pipeline(self, **kwargs):
            self.source = kwargs["source"]

        def advance_from(self, step):
            self.step = step

    app.coordinator = Pipeline()
    app.next_step()
    assert app.coordinator.step == "pixel_nb"
    from chisurf.plugins.microscopy.imaging_common import mmfdb

    registrations = []

    def register(db, **payload):
        registrations.append(payload)
        return "nb-artifact"

    monkeypatch.setattr(mmfdb, "register_imaging_output", register)
    app.model.mmfdb_db = object()
    app.model.mmfdb_source_artifact_id = "photon-source"
    app.model.mmfdb_session = object()
    app.model.save_hdf5(tmp_path / "maps.h5")
    assert app.model.mmfdb_artifact_id == "nb-artifact"
    assert registrations[0]["source_artifact_id"] == "photon-source"
    assert registrations[0]["metadata"]["analysis_kind"] == "nb"
    assert registrations[0]["metadata"]["shape"] == [6, 8]
    assert "B (red)" in registrations[0]["metadata"]["result_columns"]
    app.model.save_hdf5(tmp_path / "maps.h5")
    assert len(registrations) == 1


def test_cancel_discards_partial_result(monkeypatch):
    import threading

    from chisurf.core.fluorescence import imaging
    from chisurf.plugins.microscopy.img_pixel_nb.gui.app import make_app

    begun, resume = threading.Event(), threading.Event()

    def compute(*args, progress, **kwargs):
        begun.set()
        resume.wait(5)
        progress(0.5, "second window")
        raise AssertionError("Cancellation failed to stop compute")

    # compute() passes progress by keyword to the shared estimator.
    monkeypatch.setattr(imaging, "compute_windows", compute)
    app = make_app()
    app.model.filename = "cancel.ptu"
    app.start("compute_job")
    assert begun.wait(5)
    app.cancel()
    resume.set()
    app.job.thread.join(5)
    app.job.poll()
    assert "cancelled" in app.job.error
    assert not app.model._columns


def test_populated_native_forbids_qt_all_maps_and_controls(tmp_path):
    code = r"""
import sys
from chisurf.emtk.validation import BlockQt
sys.meta_path.insert(0,BlockQt())
import numpy as np
from emtk.testing import RecordingPainter
from chisurf.core.fluorescence.imaging import nb_pipeline
from chisurf.core.roi import RectangleROI, EllipseROI, PolygonROI
from chisurf.plugins.microscopy.img_pixel_nb.gui.app import make_app
from chisurf.emtk.i18n import set_locale, SUPPORTED_LOCALES
app=make_app()
frames=np.random.default_rng(5).poisson(3,(30,16,20)).astype(float)
maps=nb_pipeline(frames)
app.model._by_window={'green':{**maps,'frames':frames,'intensity':frames.sum(0)},'red':{**maps,'frames':frames,'intensity':frames.sum(0)}}
app.model._columns={'B (green)':maps['B']}
app.model.detectors={'green':{'chs':[0]},'red':{'chs':[1]}}
app.model.display_window='green'
app.model.cross_window='red'
app.model.gates.add(RectangleROI(0,0,5,5,name='Population'))
app.model.gates.add(EllipseROI(2,2,1,1,name='Ellipse'))
app.model.gates.add(PolygonROI(np.array([[0.,0.],[3.,0.],[1.,3.]]),name='Polygon'))
for locale in SUPPORTED_LOCALES:
 set_locale(locale)
 for size in [(1200,800),(800,600)]:
  for key in app.canvases:
   app.docks.focus(key)
   app.draw(RecordingPainter(),0,0,*size)
app.help.show();app.tour.start();app.draw(RecordingPainter(),0,0,1200,800)
app.help.hide();app.tour.stop()
app.docks.focus('frames');app.loop_movie=False;app.playing=True;app._last_frame=0;app.canvases['frames'].z=29
app.draw(RecordingPainter(),0,0,1200,800);assert not app.playing
app.loop_movie=True;app.playing=True;app._last_frame=0
app.draw(RecordingPainter(),0,0,1200,800);assert app.canvases['frames'].z==0
app.choose('setup');app.draw(RecordingPainter(),0,0,1200,800)
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[5],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_real_scanner_numeric_parity_hdf5_and_pto(tmp_path):
    import tttrlib

    from chisurf.core.datastore import column_names, numeric_column
    from chisurf.core.fluorescence.imaging import build_clsm, clsm_intensity_counts
    from chisurf.plugins.microscopy.img_pixel_nb.gui.native_model import NativeNBModel

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    model = NativeNBModel()
    model.load_file(str(source))
    model.compute_job()
    expected = nb_pipeline(
        clsm_intensity_counts(build_clsm(tttrlib.TTTR(str(source)), channels=(0,)))
    )
    for key in ("N", "B", "epsilon", "n", "mean", "variance"):
        np.testing.assert_allclose(model._by_window["ch0"][key], expected[key], equal_nan=True)
    table = model.to_table()
    assert "B (ch0)" in column_names(table)
    np.testing.assert_allclose(numeric_column(table, "B (ch0)"), expected["B"].ravel())
    hdf = tmp_path / "nb.imaging.h5"
    model.save_hdf5(hdf)
    assert hdf.is_file()
    from chisurf.core.fluorescence.imaging import read_imaging_table

    persisted = read_imaging_table(str(hdf))
    np.testing.assert_allclose(numeric_column(persisted, "B (ch0)"), expected["B"].ravel())
    # Copy raw data so the container validates actual source bytes in scratch space.
    import shutil

    shutil.copy2(source, tmp_path / "source.ptu")
    model.filename = str(tmp_path / "source.ptu")
    model.save_container()
    assert (tmp_path / "source.pto").is_file()
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(tmp_path / "source.pto") as container:
        persisted = container.get_store("nb")
        np.testing.assert_allclose(numeric_column(persisted, "B (ch0)"), expected["B"].ravel())


def test_native_open_never_computes_on_ui_thread(monkeypatch):
    from chisurf.plugins.microscopy.img_pixel_nb.gui.native_model import NativeNBModel

    model = NativeNBModel()
    monkeypatch.setattr(
        model,
        "compute",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Synchronous compute")),
    )
    model.load_file("first.ptu")
    assert not model._columns
    model.apply_pipeline_context({"source": "next.ptu", "hdf5": "next.h5"})
    assert model.filename == "next.ptu"
    assert model.pipeline_hdf5 == "next.h5"


def test_analog_calibration_and_gate_round_trip(tmp_path):
    from chisurf.plugins.microscopy.img_pixel_nb.gui.app import make_app

    app = make_app()
    mean = np.arange(1, 101, dtype=float).reshape(10, 10)
    app.model._by_window = {"ch0": {"mean": mean, "variance": 2 * mean + 5}}
    app.model.display_window = "ch0"
    app.model.read_variance = 1
    app.model.calibrate_analog()
    assert np.isclose(app.model.gain, 2)
    app.model.gates.add(RectangleROI(0, 0, 10, 10, name="Population"), invert=True)
    path = tmp_path / "gates.json"
    app.model.gates.save(path)
    from chisurf.core.roi import RegionCollection

    restored = RegionCollection.load(path)
    assert restored.get("Population").invert
    assert restored.get("Population").roi.x1 == 10


def test_demo_photon_stream_recovers_monomer_dimer_truth(tmp_path):
    from chisurf.plugins.microscopy.img_pixel_nb.demo import create_demo
    from chisurf.plugins.microscopy.img_pixel_nb.gui.native_model import NativeNBModel

    info = create_demo(tmp_path / "demo.ptu", n_pixel=16, n_frames=300)
    model = NativeNBModel()
    model.load_file(info["path"])
    model.compute_job()
    epsilon = model.epsilon_map()
    number = model.number_map()
    np.testing.assert_allclose(
        [np.median(epsilon[:, :8]), np.median(epsilon[:, 8:])], [0.5, 1], atol=0.12
    )
    np.testing.assert_allclose([np.median(number[:, :8]), np.median(number[:, 8:])], [6, 3], atol=1)
