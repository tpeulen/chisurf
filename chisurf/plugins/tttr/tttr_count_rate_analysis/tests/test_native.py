"""Native detector/window gates, background snapshots and table export."""

import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.app import setup_to_channels
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app


class PhotonStream:
    def __init__(self, micro=None, routing=None, macro=None):
        self.micro_times = np.asarray(micro if micro is not None else [0, 1, 2, 3, 4, 5])
        self.routing_channels = np.asarray(routing if routing is not None else [0, 0, 0, 0, 1, 1])
        self.macro_times = np.asarray(macro if macro is not None else [0, 100, 200, 300, 400, 1000])
        self.header = SimpleNamespace(macro_time_resolution=0.001)

    def get_tttr_by_channel(self, channels):
        return self.get_tttr_by_selection(np.flatnonzero(np.isin(self.routing_channels, channels)))

    def get_tttr_by_selection(self, indices):
        return PhotonStream(
            self.micro_times[indices], self.routing_channels[indices], self.macro_times[indices]
        )


SETUP = {
    "detectors": {"green": {"chs": [0], "micro_time_ranges": [[1, 4]]}},
    "windows": {"early": [0, 2], "late": [3, 5]},
}


def test_native_windows_and_detector_gates_are_preserved(tmp_path):
    assert set(setup_to_channels(SETUP)) == {"early_green", "late_green"}
    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    app = create_app(reader=lambda _: PhotonStream(), setups={"instrument": SETUP})
    app.tool.add_paths([path])
    assert app.tool.calculate()
    app.tool.job.future.result(timeout=5)
    app.tool.job.poll()
    rows = app.tool._model.results_rows()
    assert [(r["channel"], r["photons"], r["mean_khz"]) for r in rows] == [
        ("early_green", 2, 0.002),
        ("late_green", 1, 0.001),
    ]
    output = tmp_path / "rates.tsv"
    assert app.tool.save(output)
    app.tool.job.future.result(timeout=5)
    app.tool.job.poll()
    assert "early_green\t0.00" in output.read_text()
    state = app.export_state()
    app.restore_state(json.loads(json.dumps(state)))
    assert app.tool._model.results_rows() == rows
    app.close()


def test_native_factories_and_draw_forbid_qt():
    script = """
import sys
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from emtk.pil_painter import PilPainter
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app
from chisurf.plugins.tttr.tttr_microtime_shifter.gui.app import create_app as shifter
for app in (create_app(),shifter()):
 app.draw(PilPainter(1100,750),0,0,1100,750)
 app.close()
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_library_file_and_snapshot_reading_options(tmp_path, monkeypatch):
    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui import controller

    library = tmp_path / "library.json"
    setup = {
        **SETUP,
        "apply_lut": True,
        "channel_luts": {"0": [0, 1, 2]},
        "tttr_reading": {"file_type": "PTU"},
    }
    library.write_text(json.dumps({"setups": {"instrument": setup}}))
    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    seen = {}

    def read(path, **kwargs):
        seen.update(kwargs)
        return PhotonStream()

    monkeypatch.setattr(controller, "open_tttr", read)
    app = create_app()
    app.tool.load_setups_file([library])
    app.tool.job.future.result(timeout=5)
    app.tool.job.poll()
    app.tool.add_paths([path])
    assert app.tool.calculate()
    app.tool.job.future.result(timeout=5)
    app.tool.job.poll()
    assert seen["routine"] == "PTU"
    assert seen["apply_lut"] is True
    assert seen["channel_luts"] == {0: [0, 1, 2]}
    app.close()


def test_native_success_status_does_not_cover_scientific_docks(tmp_path):
    from emtk.pil_painter import PilPainter

    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    app = create_app(reader=lambda _: PhotonStream(), setups={"instrument": SETUP})
    app.tool.add_paths([path])
    app.tool.calculate()
    app.tool.job.future.result(timeout=5)
    app.tool.job.poll()
    painter = PilPainter(1100, 750)
    app.draw(painter, 0, 0, 1100, 750)
    pixels = np.asarray(painter.frame)
    # Plot/result docks are grey, unlike the dark overlay which formerly hid
    # them after every completed calculation.
    assert np.mean(pixels[40:700, 500:1000]) > 20
    app.close()


def test_native_rebuilds_cached_channels_after_definition_edits():
    setup = {**SETUP, "channels": {"stale": []}}
    assert set(setup_to_channels(setup)) == {"early_green", "late_green"}
    assert setup_to_channels({"channels": {"explicit": [{"detector_chs": [0]}]}}) == {
        "explicit": [{"detector_chs": [0]}]
    }


def test_native_settings_exclude_results_and_restore_control_definitions():
    app = create_app(setups={"instrument": SETUP})
    app.tool._model._per_file = {"secret": {"green": 1}}
    state = app.export_settings()
    assert "per_file" not in state and "measurement_times" not in state
    restored = create_app()
    restored.restore_settings(json.loads(json.dumps(state)))
    assert restored.tool.channels() == app.tool.channels()
    assert restored.tool._model._per_file == {}
    app.close()
    restored.close()


def test_native_full_channel_editor_changes_calculation_and_draws_all_sections(monkeypatch):
    from emtk import im
    from emtk.pil_painter import PilPainter

    app = create_app(setups={"instrument": SETUP})
    editor = app.tool.channel_editor
    editor.model.data["windows"] = {"new_window": [1, 3]}
    editor.model.changed()
    assert set(app.tool.channels()) == {"new_window_green"}
    tooltips = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda text: tooltips.append(text))
    for section in range(6):
        editor.section = section
        with im.frame(PilPainter(640, 850), (0, 0, 640, 850)):
            im.begin("channel settings")
            editor.draw()
            im.end()
    assert len(tooltips) > 40 and all(tooltips)
    app.close()


def test_native_count_plot_pads_markers_and_handles_empty_input_queue(tmp_path, monkeypatch):
    from emtk import implot
    from emtk.pil_painter import PilPainter

    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    app = create_app(reader=lambda _: PhotonStream(), setups={"instrument": SETUP})
    app.tool.add_paths([path])
    app.tool.calculate()
    app.tool.job.future.result(timeout=5)
    app.tool.job.poll()
    calls = []
    real = implot.setup_axes_limits

    def limits(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(implot, "setup_axes_limits", limits)
    app.draw(PilPainter(1100, 750), 0, 0, 1100, 750)
    assert calls[0][3] > 0.002
    app.tool._model.files = []
    app.draw(PilPainter(1100, 750), 0, 0, 1100, 750)
    app.close()
