"""Live preview startup and mean-based trace autoscaling."""
import numpy as np
import pytest

from chisurf.plugins.core.acq.live.trace import LiveTrace, TraceStream


def test_trace_retains_whole_run_mean_even_after_buffer_rolls():
    stream = TraceStream('green', (0,), 1, (0.0, 1.0, 0.0, 1.0))
    trace = LiveTrace([stream], macro_clock_s=0.001, window_s=0.01, bin_s=0.001)
    trace.push(np.array([0, 1, 2, 30]), np.zeros(4), np.zeros(4))
    snapshot = trace.snapshot()
    assert snapshot['streams'][0]['run_mean_per_bin'] == pytest.approx(4 / 31)
    assert np.sum(snapshot['streams'][0]['counts']) == 1


def test_trace_limits_follow_run_means_not_an_extreme_peak():
    from chisurf.plugins.core.acq.gui.record_app import _trace_y_limits
    streams = [{'sign': 1, 'run_mean_per_bin': 4, 'counts': [1, 10000]},
               {'sign': -1, 'run_mean_per_bin': 2, 'counts': [-1, -4000]}]
    lo, hi = _trace_y_limits({'streams': streams})
    assert 4 < hi < 10000 and -4000 < lo < -2
    streams[0]['counts'] = [1, 1000000]
    assert _trace_y_limits({'streams': streams}) == (lo, hi)


def test_record_app_connects_preview_on_startup(monkeypatch, tmp_path):
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.gui import record_app
    monkeypatch.setattr(record_app.sys, 'platform', 'win32')
    calls = []
    monkeypatch.setattr(VideoPanel, 'connect', lambda self: calls.append(self.address))
    app = RecordApp(RecordModel(output_dir=tmp_path))
    try:
        assert calls == ['0']
    finally:
        app.close()
