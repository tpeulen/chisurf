"""Scientific audification, native transport and Qt-free GUI regressions."""

import json
import signal
import subprocess
import sys
import wave
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from chisurf.plugins.tttr.audifier.core import TTTRData, compute_microtime_waterfall
from chisurf.plugins.tttr.audifier.gui.app import create_app
from chisurf.plugins.tttr.audifier.gui.view_model import AudifierViewModel
from chisurf.plugins.tttr.audifier.native_playback import NativeSoundPlayer


def data():
    return TTTRData(
        np.array([0, 0, 0, 1, 1, 1]),
        np.array([100, 110, 150, 160, 180, 195]),
        np.array([1, 2, 1, 2, 3, 2]),
        0.001,
        1e-9,
    )


def test_factory_draws_all_panels_under_hard_qt_block():
    script = """
import sys
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from emtk.pil_painter import PilPainter
from chisurf.plugins.tttr.audifier.gui.app import create_app
app=create_app()
import numpy as np
from chisurf.plugins.tttr.audifier.core import TTTRData
app.model.data=app.source_data=TTTRData(np.array([0,1,0,1]),np.array([0,1,2,3]),np.array([1,2,3,4]),.01,1e-9)
app.model.set_detectors_from_settings({'detectors':{'a':{'chs':[0,1]}}})
app.compute_waterfall()
app.job.future.result(timeout=5)
app.job.poll()
for panel in ['setup','audio','waterfall_parameters','notes','mixer']:
 app.docks.focus(panel)
 app.draw(PilPainter(1200,800),0,0,1200,800)
app.close()
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_waterfall_shared_detector_time_and_micro_grids_and_brightness():
    stream = data()
    results = [
        compute_microtime_waterfall(stream, channels=[ch], macro_bin_width_s=0.02, n_micro_bins=8)
        for ch in [0, 1]
    ]
    np.testing.assert_array_equal(results[0][1], results[1][1])
    np.testing.assert_array_equal(results[0][2], results[1][2])
    assert results[0][0].shape == results[1][0].shape
    assert results[1][0][:3].sum() == 0
    model = AudifierViewModel()
    model.data = stream
    model.wf_bin_width = 0.02
    model.wf_micro_bins = 8
    model.set_detectors_from_settings({"detectors": {"a": {"chs": [0]}, "b": {"chs": [1]}}})
    payload = model.compute_waterfall()
    assert payload["rgb_data"].shape == (8, 5, 3)
    model.wf_micro_bins = 1
    brightness = model.compute_waterfall()["rgb_data"].max(axis=2).ravel()
    assert len(np.unique(brightness[brightness > 0])) > 1


def test_preview_and_export_share_all_envelope_parameters(tmp_path):
    model = AudifierViewModel()
    model.data = TTTRData(
        np.zeros(80, dtype=int),
        np.sort(np.concatenate([np.zeros(50, dtype=int), np.full(20, 40), np.arange(10) * 10 + 1])),
        np.ones(80, dtype=int),
        0.001,
        1e-9,
    )
    model.sample_rate = 8000
    model.bin_width = 0.01
    model.env_floor = 0.5
    model.env_scale = 3
    model.attack_frames = 4
    model.release_frames = 9
    model.set_detectors_from_settings({"detectors": {"all": {"chs": [0, 1]}}})
    np.random.seed(123)
    preview, duration = model.build_audio()
    np.random.seed(123)
    exported = model.save_wav(str(tmp_path / "audio.wav"))
    np.testing.assert_array_equal(preview, exported)
    assert duration == len(preview) / 8000
    with wave.open(str(tmp_path / "audio.wav")) as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2 and wav.getframerate() == 8000
        assert wav.getnframes() == len(preview)
    assert np.all(np.isfinite(preview))
    assert np.max(np.abs(preview)) > 0
    model.env_floor = 0.9
    np.random.seed(123)
    changed, _ = model.build_audio()
    assert not np.allclose(preview, changed)


class Process:
    def __init__(self):
        self.signals = []
        self.code = None

    def poll(self):
        return self.code

    def send_signal(self, signal):
        self.signals.append(signal)

    def terminate(self):
        self.code = -15

    def wait(self, timeout):
        return self.code


def test_native_true_pause_resume_revert_stop_cleanup():
    now = [0.0]
    processes = []

    def spawn(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process

    player = NativeSoundPlayer(command=["player"], clock=lambda: now[0], spawn=spawn)
    player.load_audio(np.zeros(8000), 8000)
    path = Path(player.path)
    player.play()
    now[0] = 0.25
    player.pause()
    assert player.position == 0.25 and player.state == "paused"
    now[0] = 10
    player.play()
    assert len(processes) == 1 and processes[0].signals == [signal.SIGSTOP, signal.SIGCONT]
    now[0] = 10.1
    assert player.poll()[0] == pytest.approx(0.35)
    player.revert()
    assert len(processes) == 2 and player.position == 0
    player.close()
    assert not path.exists() and player.state == "stopped"


def test_native_colour_controls_convert_between_byte_and_float_rgb(monkeypatch):
    from emtk import im
    from emtk.pil_painter import PilPainter

    app = create_app()
    app.model.set_detectors_from_settings({"detectors": {"red": {"chs": [0]}}})
    seen = []

    def colour(label, values):
        seen.append(values)
        return True, (0, 128, 255)

    monkeypatch.setattr(im, "color_edit3", colour)
    try:
        app.draw(PilPainter(1200, 800), 0, 0, 1200, 800)
        assert seen[0][0] == 255
        np.testing.assert_allclose(app.model.detectors[0]["color"], (0, 128 / 255, 1))
    finally:
        app.close()


def test_async_load_snapshot_range_gate_and_wav_export(tmp_path):
    entered, release = Event(), Event()

    def loader(path):
        entered.set()
        assert release.wait(5)
        return data()

    app = create_app(loader=loader)
    try:
        app.model.sample_rate = 8000
        assert app.load(tmp_path / "stream.ptu")
        assert entered.wait(5)
        assert app.model.data is None and not app.load("other.ptu")
        release.set()
        app.job.future.result(timeout=5)
        app.job.poll()
        assert app.model.sample_rate == 8000 and app.model.channels == [0, 1]
        app.range_start = 0.05
        app.range_end = 0.09
        snapshot = app.snapshot()
        app.apply_range(snapshot)
        np.testing.assert_array_equal(snapshot.data.macro_ticks, [150, 160, 180])
        app.model.channel_configs[0] = __import__("dataclasses").replace(
            app.model.channel_configs[0], micro_min=2
        )
        output = tmp_path / "selected.wav"
        assert app.render_audio(output=output)
        app.job.future.result(timeout=5)
        app.job.poll()
        assert output.exists() and len(app.waveform) > 0
        json.dumps(app.export_settings())
    finally:
        release.set()
        app.close()


def test_lifetime_waterfall_axes_are_seconds_and_shared():
    from chisurf.plugins.tttr.audifier.lifetime_analysis import compute_lifetime_waterfall

    stream = data()
    results = [
        compute_lifetime_waterfall(
            stream,
            ch,
            macro_bin_width_s=0.02,
            micro_gate=None,
            n_tau=20,
            tau_min=0.1e-9,
            tau_max=5e-9,
        )
        for ch in [0, 1]
    ]
    np.testing.assert_array_equal(results[0][1], results[1][1])
    assert results[0][1][-1] < 1
    assert results[0][0].shape == (5, 20)
    assert np.all(np.isfinite(results[0][0]))


def test_stop_before_background_render_finishes_never_starts_audio(monkeypatch):
    entered, release = Event(), Event()

    def build(model):
        entered.set()
        assert release.wait(5)
        return np.zeros(800), 0.1

    monkeypatch.setattr(AudifierViewModel, "build_audio", build)
    app = create_app()
    try:
        app.model.data = app.source_data = data()
        app.model.set_detectors_from_settings({"detectors": {"a": {"chs": [0]}}})
        assert app.render_audio(play=True)
        assert entered.wait(5)
        app.stop_playback()
        release.set()
        app.job.future.result(timeout=5)
        app.job.poll()
        assert app.player.path is None and app.player.state == "stopped"
    finally:
        release.set()
        app.close()


def test_real_tttr_loading_waterfall_and_selected_export(tmp_path):
    from chisurf.plugins.tttr.audifier.core import load_tttr_with_tttrlib

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    if not source.exists():
        pytest.skip("Real TTTR fixture unavailable")
    app = create_app()
    try:
        assert app.load(source)
        app.job.future.result(timeout=30)
        app.job.poll()
        original = load_tttr_with_tttrlib(str(source))
        np.testing.assert_array_equal(app.model.data.micro_bins, original.micro_bins)
        app.range_end = 0.1
        app.model.sample_rate = 8000
        assert app.compute_waterfall()
        app.job.future.result(timeout=10)
        app.job.poll()
        assert app.texture is not None
        output = tmp_path / "real.wav"
        assert app.render_audio(output=output)
        app.job.future.result(timeout=10)
        app.job.poll()
        with wave.open(str(output)) as wav:
            assert wav.getnframes() > 0 and wav.getframerate() == 8000
    finally:
        app.close()


def test_preferences_roundtrip_excludes_live_data_and_preview_arrays():
    app, restored = create_app(), create_app()
    try:
        app.model.data = data()
        app.model.master_gain = 0.25
        app.model.set_detectors_from_settings({"detectors": {"a": {"chs": [0]}}})
        app.model.set_channel(0, chord_type="minor7", gain=2)
        app.editor.model.data["_microtime_per_channel_decay"] = {"channels": {"0": [1, 2, 3]}}
        preferences = app.export_settings()
        restored.restore_settings(json.loads(json.dumps(preferences)))
        assert restored.model.data is None
        assert "_microtime_per_channel_decay" not in preferences["setup"]
        assert restored.model.master_gain == 0.25
        assert restored.model.channel_configs[0].chord_type == "minor7"
        assert restored.model.channel_configs[0].gain == 2
    finally:
        app.close()
        restored.close()


def test_selected_reader_lut_and_timing_units_are_honoured(monkeypatch):
    from types import SimpleNamespace

    from chisurf.core.fio import staging
    from chisurf.plugins.tttr.audifier.core import load_tttr_with_tttrlib

    recorded = []
    stream = SimpleNamespace(
        routing_channels=np.array([0, 1]),
        macro_times=np.array([1, 2]),
        micro_times=np.array([3, 4]),
        header=SimpleNamespace(macro_time_resolution=1e-6, micro_time_resolution=1e-9),
    )

    def reader(path, filetype, **kwargs):
        recorded.append((filetype, kwargs))
        return stream

    monkeypatch.setattr(staging, "open_tttr", reader)
    loaded = load_tttr_with_tttrlib(
        "input.spc",
        setup={
            "channel_shifts": {"0": 2},
            "tttr_reading": {
                "file_type": "SPC-130",
                "override_timing": True,
                "macro_time_resolution": 50,
                "micro_time_resolution": 25,
            },
        },
    )
    assert recorded[0][0] == "SPC-130"
    assert recorded[0][1]["channel_shifts"] == {0: 2}
    assert loaded.macro_time_unit_s == pytest.approx(50e-9)
    assert loaded.micro_time_unit_s == pytest.approx(25e-12)
