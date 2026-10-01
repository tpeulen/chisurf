"""Native fusion runs the real photon writer and hands off its output."""

import json
import shutil
import subprocess
import sys
from concurrent.futures import CancelledError
from pathlib import Path

import pytest

from chisurf.plugins.burst.burst_fusion.gui.app import create_app


def test_rendered_native_factories_without_qt():
    code = """
import sys, logging
class Errors(logging.Handler):
    def emit(self, record):
        if record.levelno>=40: raise AssertionError(record.getMessage())
logging.getLogger().addHandler(Errors())
class Painter:
    def text_width(self,text): return len(str(text))*7
    def line_height(self): return 14
    def __getattr__(self,name): return lambda *a,**kw:None
from chisurf.plugins.burst.burst_fusion.gui.app import create_app as fusion
from chisurf.plugins.burst.burst_browser.gui.app import create_app as browser
for factory in (fusion,browser):
    app=factory()
    app.draw(Painter(),0.,0.,1200.,800.)
    app.draw(Painter(),0.,0.,800.,600.)
    app.close()
qt=[m for m in sys.modules if m.startswith(('qtpy','PyQt','PySide'))]
assert not qt,qt
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_native_fusion_real_photons_handoff_settings_report(tmp_path, caplog):
    data = (
        Path(__file__).resolve().parents[2]
        / "burst_selection"
        / "tests"
        / "data"
        / "bh_spc132_sm_dna"
    )
    if not data.is_dir():
        pytest.skip("sample SPC unavailable")
    raw = tmp_path / "data"
    folder = raw / "bursts"
    (folder / "bi4_bur").mkdir(parents=True)
    shutil.copy(data / "m000.spc", raw / "m000.spc")
    shutil.copy(
        data / "burstwise_All 0.1000#15" / "bi4_bur" / "m000.bur", folder / "bi4_bur" / "m000.bur"
    )
    app = create_app()
    outputs = []
    app.model.folder_written = outputs.append
    app.set_channel_settings(
        {
            "detectors": {
                "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2048]]},
                "red": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
            },
            "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
        }
    )
    app.set_folder(folder)
    try:
        app.controller.estimate()
        app.controller._future.result(timeout=30)
        app.controller.poll()
        statistics = app.model.analysis.statistics
        assert statistics["n_bursts_before"] >= statistics["n_bursts_after"] > 0
        assert outputs == []
        settings = tmp_path / "settings.json"
        app.controller.save_settings(settings)
        app.controller.load_settings(settings)
        app.controller.run()
        app.controller._future.result(timeout=30)
        app.controller.poll()
        assert len(outputs) == 1
        assert Path(outputs[0]).is_dir()
        assert list(Path(outputs[0]).glob("bi4_bur/*.bur"))
        report = tmp_path / "report.json"
        app.controller.export_summary(report)
        assert json.loads(report.read_text())["output_folder"] == outputs[0]

        class Painter:
            def text_width(self, text):
                return len(str(text)) * 7

            def line_height(self):
                return 14

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        app.draw(Painter(), 0.0, 0.0, 1200.0, 800.0)
        assert not [record for record in caplog.records if record.levelno >= 40]
        previous = app.model.analysis
        app.controller.estimate()
        app.controller.stop()
        try:
            app.controller._future.result(timeout=30)
        except CancelledError:
            pass
        app.controller.poll()
        assert app.model.analysis is previous
    finally:
        app.close()
