"""Native LLTF subprocess, settings, results and actual render contract."""

import subprocess
import sys
from pathlib import Path

import yaml

from chisurf.plugins.fluorescence_decay.lltf.gui.model import LLTFModel


def test_command_preserves_component_selection_options(tmp_path):
    m = LLTFModel()
    m.decay_file = "decay.dat"
    m.irf_file = "irf.dat"
    m.output_dir = str(tmp_path)
    m.config_file = "config.yml"
    fixed = m.build_command()
    assert fixed[:5] == [
        sys.executable,
        "-m",
        "chisurf.plugins.fluorescence_decay.lltf.core",
        "fit",
        "decay.dat",
    ]
    assert fixed[-3:] == ["-n", "1", "-v"]
    m.find_optimal = True
    m.max_lifetimes = 4
    m.prob_threshold = 0.68
    automatic = m.build_command()
    assert automatic[-6:] == ["-f", "-m", "4", "-pt", "0.68", "-v"]


def test_stop_owned_process_and_preferences_roundtrip():
    m = LLTFModel()
    m.find_optimal = True
    m.max_lifetimes = 5
    m.decay_file = "measured.dat"
    restored = LLTFModel()
    restored.restore_preferences(m.export_preferences())
    assert restored.export_preferences() == m.export_preferences()
    process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    m.process = process
    try:
        m.stop()
        assert process.poll() is not None and m.process is None
    finally:
        if process.poll() is None:
            process.kill()


def test_actual_lltf_analysis_and_result_plots(tmp_path):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.fluorescence_decay.lltf.gui.app import LLTFApp

    root = Path(__file__).parents[1] / "example"
    m = LLTFModel()
    m.decay_file = str(root / "5-44_D0.dat")
    m.irf_file = str(root / "IRF_D0.dat")
    m.output_dir = str(tmp_path)
    m.verbose = False
    settings = yaml.safe_load(m.config_text)
    settings["estimate_irf_shift_parameters"]["enabled"] = False
    settings["estimate_background_parameter"]["enabled"] = False
    m.config_text = yaml.safe_dump(settings)
    try:
        m.start()
        m.process.wait(timeout=60)
        assert m.poll()
        assert m.returncode == 0, m.status + "\n" + "\n".join(m.output)
        assert m.result and m.result["lifetimes"]
        assert Path(m.output_file).is_file()
        arrays = m.plot_arrays()
        assert len(arrays["residuals"]) == len(arrays["fit"])
        app = LLTFApp(m)
        app.arrays = arrays
        app.pending_tab = "Results"
        app.draw(RecordingPainter(), 0, 0, 1200, 900)
    finally:
        m.close()


def test_native_settings_and_all_panels_without_qt(tmp_path):
    script = f"""
import importlib.abc,sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:raise RuntimeError('Qt '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.lltf.gui.app import make_app
app=make_app()
app.draw(RecordingPainter(),0,0,1200,900)
app.config_open=True;app.draw(RecordingPainter(),0,0,1200,900)
app.model.save_config({str(tmp_path / "config.yml")!r})
app.model.load_config({str(tmp_path / "config.yml")!r})
app.config_open=False;app.choose('decay_file');app.draw(RecordingPainter(),0,0,1200,900)
assert 'chisurf.gui' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
