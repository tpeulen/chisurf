"""Native IRF IO, numerical workflow, transfer and full surface contract."""
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.irf_estimator.gui.view_model import IRFViewModel


def decay(n=300, dt=.1):
    time = np.arange(n) * dt
    irf = np.exp(-.5 * ((time-3.)/.4)**2)
    irf /= irf.sum()
    convolved = np.convolve(np.exp(-time/2.), irf)[:n]
    return np.random.default_rng(5).poisson(4.e4 * convolved / convolved.max() + 8.), time


def test_native_estimate_background_applied_once(tmp_path):
    from chisurf.plugins.fluorescence_decay.irf_estimator.core.estimation import estimate_irf

    values, time = decay()
    m = IRFViewModel()
    m.load_data(values, time_axis=time)
    m.manual_background = 8.
    m.rl_iterations = 50
    result = m.estimate()
    reference = estimate_irf(values.astype(float), m.dt, m.settings(), time)
    assert np.allclose(result.irf, reference.irf)
    assert result.decay_rate_ns == pytest.approx(1./result.lifetime_ns)
    assert len(m.plot_series()) == 4
    path = m.save(tmp_path / "irf")
    reloaded = IRFViewModel()
    reloaded.load_file(path)
    assert len(reloaded.decay_data_original) == len(values)
    assert np.allclose(reloaded.decay_data_original, result.irf, rtol=1e-5, atol=1e-6)
    assert reloaded.dt == pytest.approx(.1)
    datasets = []
    group = m.transfer(datasets.append)
    assert datasets == [group]
    assert len(group) == 2
    assert group.unique_identifier
    assert all(curve.unique_identifier for curve in group)
    assert group.data_reader.dt == pytest.approx(.1)
    assert group.data_reader.rep_rate == pytest.approx(10.)


def test_native_load_preserves_even_single_channel_files(tmp_path):
    from chisurf.core.fio.vv_vh import write_vv_vh

    path = tmp_path / "single.dat"
    write_vv_vh(path, vm=np.arange(32.)+1, metadata={"dt": .2})
    m = IRFViewModel()
    m.load_file(path)
    assert len(m.decay_data_original) == 32
    assert m.dt == pytest.approx(.2)


def test_native_async_estimation_and_plot_mouse():
    from emtk.testing import RecordingPainter
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp

    values, time = decay()
    app = IRFEstimatorApp()
    app.model.load_data(values, time_axis=time)
    app.model.rl_iterations = 50
    app.start_estimate()
    app.future.result(timeout=20)
    app.poll()
    assert app.model.result is not None
    app.model.use_range_selection = True
    app.draw(RecordingPainter(),0,0,1200,900)
    app.io.mouse_pos = (900.,300.)
    app.draw(RecordingPainter(),0,0,1200,900)
    assert "Intensity:" in app.pointer_text      # the Qt tooltip: "Time: x ns, Intensity: y"


def test_native_surface_workflow_without_qt(tmp_path):
    script = f'''
import importlib.abc, sys, numpy as np
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app
from chisurf.core.data import DataCurve
app=make_app()
t=np.arange(300)*.1
irf=np.exp(-.5*((t-3.)/.4)**2);irf/=irf.sum()
y=np.random.default_rng(5).poisson(4e4*np.convolve(np.exp(-t/2.),irf)[:300]+8.)
app.model.load_dataset(DataCurve(x=t,y=y,load_filename_on_init=False))
app.model.rl_iterations=50
app.model.estimate()
app.model.use_range_selection=True
app.draw(RecordingPainter(),0,0,1200,900)
app.model.save({str(tmp_path/'irf.dat')!r})
app.model.transfer()
app.choose_file()
app.draw(RecordingPainter(),0,0,1200,900)
assert 'chisurf.gui' not in sys.modules
'''
    result = subprocess.run([sys.executable,"-c",script],cwd=Path(__file__).resolve().parents[5],capture_output=True,text=True)
    assert result.returncode == 0,result.stdout+result.stderr


def test_reference_qt_estimation_passes_uncorrected_counts_once(qapp, qtbot, monkeypatch):
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import tool as legacy
    from chisurf.plugins.fluorescence_decay.irf_estimator.api.models import IRFEstimationResult

    widget = legacy.IRFEstimatorTool()
    qtbot.addWidget(widget)
    original = np.arange(20.) + 10.
    widget.decay_data_original = original
    widget.decay_data = original - 3.
    widget.manual_background = 3.
    seen = []
    def estimate(intensity, **kwargs):
        seen.append(np.asarray(intensity).copy())
        return IRFEstimationResult(irf=np.ones(20).tolist(),params={"k":.1,"k_per_ns":.1,"C":3.},time_axis=np.arange(20.).tolist(),dt=1.,lifetime_ns=10.,decay_rate_ns=.1,amplitude=1.,offset=3.)
    monkeypatch.setattr(legacy, "_estimate_irf", estimate)
    widget.estimate_irf()
    assert np.array_equal(seen[0], original)


def test_bin_width_recalibration_keeps_rate_lifetime_and_export_consistent(tmp_path):
    values, time = decay()
    m = IRFViewModel()
    m.load_data(values, time_axis=time)
    m.rl_iterations = 50
    result = m.estimate()
    original_irf = np.asarray(result.irf).copy()
    lifetime, rate = result.lifetime_ns, result.decay_rate_ns
    m.set_bin_width(.2)
    assert result.lifetime_ns == pytest.approx(2. * lifetime)
    assert result.decay_rate_ns == pytest.approx(rate / 2.)
    assert result.params["k_per_ns"] == pytest.approx(result.decay_rate_ns)
    assert np.array_equal(result.irf, original_irf)
    assert np.diff(m.channel_axis).mean() == pytest.approx(.2)
    path = m.save(tmp_path / "recalibrated.dat")
    reloaded = IRFViewModel()
    reloaded.load_file(path)
    assert reloaded.dt == pytest.approx(.2)


def test_plot_range_drag_translates_nanoseconds_to_channel_indices(monkeypatch):
    from types import SimpleNamespace
    from emtk import implot
    from emtk.testing import RecordingPainter
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp

    values, time = decay()
    app = IRFEstimatorApp()
    app.model.load_data(values, time_axis=time)
    app.model.use_range_selection = True
    monkeypatch.setattr(implot, "drag_rect", lambda *args, **kwargs: SimpleNamespace(modified=True,x_min=2.,x_max=10.))
    app.draw(RecordingPainter(),0,0,1200,900)
    assert app.model.range_bounds == [20.,100.]


def test_async_result_respects_bin_width_edited_while_estimation_runs():
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp

    values, time = decay()
    app = IRFEstimatorApp()
    app.model.load_data(values,time_axis=time)
    app.model.rl_iterations = 50
    app.start_estimate()
    app.model.set_bin_width(.2)
    app.future.result(timeout=20)
    app.poll()
    result = app.model.result
    assert result.dt == pytest.approx(.2)
    assert result.decay_rate_ns == pytest.approx(result.params["k"]/.2)
    assert result.lifetime_ns == pytest.approx(1./result.decay_rate_ns)
