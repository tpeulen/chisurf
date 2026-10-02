"""Native MEM numerical, file, isolated-worker and full render regressions."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.maxent_decay.gui.model import MEMModel, execute_job
from chisurf.plugins.fluorescence_decay.maxent_decay.test.test_solver_contract import _problem


def model():
    m = MEMModel()
    y, lamp, dt, t = _problem(n=128)
    m.set_data(t, y)
    m.select_irf(SimpleNamespace(x=t, y=lamp, name="IRF"))
    m.settings.tau_bins = 8
    m.settings.max_iter = 20
    m.settings.r_bins = 8
    return m


def test_native_solver_rebuild_export_and_generation_snapshot(tmp_path):
    m = model()
    result = m.run()
    arrays = m.arrays()
    expected = np.asarray(result["Fi"]) @ result["p"] * result["sigma"] + result["fit_additive"]
    assert np.allclose(arrays["fit"], expected)
    assert np.isfinite(arrays["wres"]).all()
    old = result["nu_input"]
    m.settings.nu = 0.2
    m.export_result(tmp_path)
    import json

    assert json.loads((tmp_path / "meta.json").read_text())["settings"]["nu"] == old
    assert {path.name for path in tmp_path.iterdir()} == {
        "distribution.txt",
        "decay_fit.txt",
        "irf.txt",
        "wres.txt",
        "meta.json",
    }


def test_native_fret_requires_donor_and_uses_loaded_spectrum(tmp_path):
    m = model()
    m.settings.mode = "fret"
    with pytest.raises(ValueError, match="donor"):
        m.run()
    donor = tmp_path / "donor.csv"
    np.savetxt(donor, [[1.0, 4.1]], delimiter=",")
    m.load_donor(donor)
    result = m.run()
    assert "R" in result and len(result["p"]) == 8
    assert np.isfinite(result["p"]).all()


def test_fixed_nuisance_values_are_honored_by_actual_solver():
    m = model()
    m.settings.optimize_nuisance = True
    m.settings.timeshift = 0.37
    m.settings.background = 7.5
    m.settings.irf_background = 0.1
    m.fix_timeshift = m.fix_background = m.fix_irf_background = True
    result = m.run()
    assert result["timeshift"] == pytest.approx(0.37)
    assert result["background"] == pytest.approx(7.5)
    assert result["irf_background"] == pytest.approx(0.1)


def test_real_lcurve_and_sampling(tmp_path):
    m = model()
    m.settings.tau_bins = 4
    m.run()
    curve = execute_job({"kind": "lcurve", "snapshot": m.snapshot()})
    assert len(curve["log10_nu"]) == 16
    assert np.isfinite(curve["chi2r"]).all()
    m.sample_steps = 10
    m.sample_thin = 1
    m.sample_walkers = 10
    m.sample_substeps = 5
    m.sample_nprocs = 1
    m.sample_vectorized = True
    stats = execute_job(
        {"kind": "sample", "snapshot": m.snapshot(), "result": m.result, "folder": str(tmp_path)}
    )
    assert stats["n_samples"] > 0
    assert len(stats["p_mean"]) == 4
    assert (tmp_path / "sampling.npz").is_file()
    assert (tmp_path / "sampling_project.json").is_file()


def test_actual_isolated_worker_completes():
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.controller import MEMJobs

    m = model()
    jobs = MEMJobs(m)
    try:
        jobs.start("run")
        jobs.process.wait(timeout=30)
        assert jobs.poll()
        assert m.result is not None, m.status + "\n" + "\n".join(jobs.output)
    finally:
        jobs.close()


def test_legacy_and_native_preferences_preserve_user_choices():
    m = MEMModel()
    m.restore_preferences(
        {
            "tau_grid": {"min": 0.2, "max": 8.0, "bins": 32},
            "fret": {"R0": 54.0, "period_ns": 12.0, "use_periodic": True},
            "sampling_defaults": {"steps_total": 77, "vectorized": None},
            "lcurve_span_decades": {"left": 3.0},
        }
    )
    assert (m.settings.tau_min, m.settings.tau_max, m.settings.tau_bins) == (0.2, 8.0, 32)
    assert m.settings.R0 == 54.0 and m.settings.period == 12.0 and m.use_periodic
    assert m.sample_steps == 77 and m.lcurve_left == 3.0
    restored = MEMModel()
    restored.restore_preferences(m.parameters())
    assert restored.parameters() == m.parameters()


def test_cancel_terminates_owned_process_without_clearing_result(monkeypatch):
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.controller import MEMJobs

    m = model()
    m.run()
    saved = m.result
    jobs = MEMJobs(m)
    original_popen = subprocess.Popen
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda args, **kwargs: original_popen(
            [sys.executable, "-c", "import time;time.sleep(30)"], **kwargs
        ),
    )
    jobs.start("run")
    process = jobs.process
    try:
        jobs.cancel()
        assert process.poll() is not None
        assert m.result is saved
    finally:
        if process.poll() is None:
            process.kill()


def test_native_full_surface_and_science_without_qt(tmp_path):
    script = f"""
import importlib.abc,sys,numpy as np
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:raise RuntimeError('Qt '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
from types import SimpleNamespace
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import make_app
from chisurf.plugins.fluorescence_decay.maxent_decay.test.test_solver_contract import _problem
app=make_app();y,lamp,dt,t=_problem(n=128)
app.model.set_data(t,y);app.model.select_irf(SimpleNamespace(x=t,y=lamp,name='IRF'))
app.model.settings.tau_bins=8;app.model.settings.r_bins=8;app.model.settings.max_iter=20
app.model.run();app.draw(RecordingPainter(),0,0,1200,900)
assert all(key in app.item_rects for key in ('maxentBtnRefresh','maxentBtnRun','maxentBtnLcurve'))
app.model.export_result({str(tmp_path)!r})
app.model.settings.mode='fret';app.model.donor=np.array([1.,4.1]);app.model.run()
app.draw(RecordingPainter(),0,0,1200,900)
app.open_settings();app.draw(RecordingPainter(),0,0,1200,900)
assert 'chisurf.gui' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
