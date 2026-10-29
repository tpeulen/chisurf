"""Video file round trip and explicit source lifecycle."""

import time

import numpy as np
import pytest

pytest.importorskip("cv2")

from chisurf.plugins.core.acq.live.video import OpenCVRecorder, OpenCVSource, VideoFrame


def test_video_file_record_and_playback(tmp_path):
    path = tmp_path / "capture.avi"
    recorder = OpenCVRecorder(path, fps=10)
    frame = np.zeros((32, 40, 3), dtype=np.uint8)
    frame[:, :, 0] = 240
    recorder.write(VideoFrame(frame, 1.0))
    recorder.write(VideoFrame(frame, 1.1))
    recorder.close()

    source = OpenCVSource(str(path))
    source.open()
    try:
        first = source.read()
        second = source.read()
        assert source.read() is None
        assert first.image.shape == frame.shape
        assert first.image[:, :, 0].mean() > 200
        assert first.image[:, :, 2].mean() < 20
        assert second.timestamp_s >= first.timestamp_s
    finally:
        source.close()


def test_recorder_never_overwrites_and_rejects_size_change(tmp_path):
    path = tmp_path / "capture.avi"
    frame = VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 1.0)
    recorder = OpenCVRecorder(path, fps=10)
    recorder.write(frame)
    with pytest.raises(ValueError, match="dimensions changed"):
        recorder.write(VideoFrame(np.zeros((20, 40, 3), dtype=np.uint8), 2.0))
    recorder.close()
    old = path.read_bytes()
    with pytest.raises(FileExistsError):
        OpenCVRecorder(path, fps=10).write(frame)
    assert path.read_bytes() == old


def test_read_requires_open():
    with pytest.raises(RuntimeError, match="not open"):
        OpenCVSource(0).read()


def test_preview_and_recording_worker_writes_timestamps(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui import video_panel

    class Source:
        def __init__(self, address):
            self.closed = False

        def open(self):
            pass

        def read(self):
            time.sleep(0.01)
            return VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), time.monotonic())

        def close(self):
            self.closed = True

    monkeypatch.setattr(video_panel, "source_for", lambda address: Source(address))
    panel = video_panel.VideoPanel()
    panel.photon_context = lambda: "/tmp/photons.ptu"
    panel.output = str(tmp_path / "live.avi")
    panel.connect()
    try:
        deadline = time.monotonic() + 3
        while not panel._connected and time.monotonic() < deadline:
            time.sleep(0.01)
        panel.record()
        deadline = time.monotonic() + 3
        while panel._count < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        panel.stop_recording()
        deadline = time.monotonic() + 3
        while panel._recorder is not None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert panel._recorder is None
        assert panel._count >= 3
        assert panel.frame is not None
        assert (tmp_path / "live.avi").exists()
        rows = (tmp_path / "live.avi.timestamps.csv").read_text().splitlines()
        assert rows[0] == "frame,monotonic_seconds"
        assert rows[3] == "associated_photon_ptu,/tmp/photons.ptu"
        assert len(rows) == panel._count + 4
    finally:
        panel.close()
        panel._thread.join(3)
    assert panel._source.closed
    assert panel.frame is None


def test_slow_open_does_not_block_and_stop_creates_no_sidecar(tmp_path, monkeypatch):
    import threading

    from chisurf.plugins.core.acq.gui import video_panel

    gate = threading.Event()

    class SlowSource:
        def __init__(self, address):
            pass

        def open(self):
            gate.wait(2)

        def close(self):
            pass

    monkeypatch.setattr(video_panel, "source_for", lambda address: SlowSource(address))
    panel = video_panel.VideoPanel()
    panel.output = str(tmp_path / "capture.avi")
    start = time.monotonic()
    panel.connect()
    panel.close()
    assert time.monotonic() - start < 0.5
    gate.set()
    panel._thread.join(3)
    assert not list(tmp_path.iterdir())


def test_file_playback_is_paced(tmp_path):
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel

    path = tmp_path / "source.avi"
    recorder = OpenCVRecorder(path, fps=5)
    for index in range(3):
        recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), index / 5))
    recorder.close()
    panel = VideoPanel()
    panel.address = str(path)
    started = time.monotonic()
    panel.connect()
    panel._thread.join(3)
    assert not panel._thread.is_alive()
    assert time.monotonic() - started >= 0.35


def test_failed_writer_does_not_leave_timestamp_sidecar(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui import video_panel

    class Source:
        def __init__(self, address):
            pass

        def open(self):
            pass

        def read(self):
            time.sleep(0.01)
            return VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), time.monotonic())

        def close(self):
            pass

    class FailingRecorder:
        def __init__(self, path, fps):
            self.path = path

        def write(self, frame):
            raise RuntimeError("encoder unavailable")

        def close(self):
            pass

    monkeypatch.setattr(video_panel, "source_for", lambda address: Source(address))
    monkeypatch.setattr(video_panel, "OpenCVRecorder", FailingRecorder)
    panel = video_panel.VideoPanel()
    panel.output = str(tmp_path / "capture.avi")
    panel.connect()
    deadline = time.monotonic() + 3
    while not panel._connected and time.monotonic() < deadline:
        time.sleep(0.01)
    panel.record()
    panel._thread.join(3)
    assert "encoder unavailable" in panel.status
    assert not list(tmp_path.iterdir())


def test_device_discovery_does_not_open_sources(monkeypatch):
    from chisurf.plugins.core.acq.gui import video_panel

    class Result:
        stdout = "USB Capture Device\n"

    monkeypatch.setattr(video_panel.sys, "platform", "win32")
    monkeypatch.setattr(video_panel.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(video_panel, "source_for", lambda *a: pytest.fail("device opened"))
    panel = video_panel.VideoPanel()
    panel.discover()
    deadline = time.monotonic() + 2
    while panel.discovered == "Looking for video devices…" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert panel.discovered == "USB Capture Device"


def test_recording_resamples_variable_capture_rate(tmp_path):
    path = tmp_path / "resampled.avi"
    recorder = OpenCVRecorder(path, fps=10)
    image = np.zeros((32, 40, 3), dtype=np.uint8)
    timestamps = []
    for t in (1.0, 1.02, 1.31):
        timestamps.extend(recorder.write(VideoFrame(image, t)))
    recorder.close()
    assert timestamps == [1.0, 1.02, 1.02, 1.31]
    source = OpenCVSource(str(path))
    source.open()
    try:
        assert sum(source.read() is not None for _ in range(5)) == 4
    finally:
        source.close()


def test_recording_refuses_unbounded_gap(tmp_path):
    path = tmp_path / "gap.avi"
    recorder = OpenCVRecorder(path, fps=30)
    image = np.zeros((32, 40, 3), dtype=np.uint8)
    recorder.write(VideoFrame(image, 0.0))
    try:
        with pytest.raises(ValueError, match="gap exceeds 30 seconds"):
            recorder.write(VideoFrame(image, 60.0))
    finally:
        recorder.close()


def test_app_close_waits_for_recording_finalizer():
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel

    class Recorder:
        closed = False

        def close(self):
            time.sleep(0.05)
            self.closed = True

    panel = VideoPanel()
    recorder = Recorder()
    panel._recorder = recorder
    panel.close()
    assert recorder.closed
    assert not panel._finalizer.is_alive()


def test_recording_finalizes_while_read_is_blocked_and_tracks_later_run(tmp_path, monkeypatch):
    import threading

    from chisurf.plugins.core.acq.gui import video_panel

    block = threading.Event()
    entered = threading.Event()
    release = threading.Event()
    run = [""]

    class Source:
        def __init__(self, address):
            pass

        def open(self):
            pass

        def read(self):
            if block.is_set():
                entered.set()
                release.wait(3)
                return None
            time.sleep(0.01)
            return VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), time.monotonic())

        def close(self):
            pass

    monkeypatch.setattr(video_panel, "source_for", lambda address: Source(address))
    panel = video_panel.VideoPanel()
    panel.output = str(tmp_path / "capture.avi")
    panel.photon_context = lambda: run[0]
    panel.connect()
    deadline = time.monotonic() + 3
    while not panel._connected and time.monotonic() < deadline:
        time.sleep(0.01)
    panel.record()
    while panel._count < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    run[0] = "/tmp/later.ptu"
    while panel._photon_path != run[0] and time.monotonic() < deadline:
        time.sleep(0.01)
    block.set()
    assert entered.wait(3)
    panel.stop_recording()
    deadline = time.monotonic() + 3
    while panel._recorder is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert panel._recorder is None
        text = (tmp_path / "capture.avi.timestamps.csv").read_text()
        assert "photon_run_at_frame_" in text and "/tmp/later.ptu" in text
    finally:
        release.set()
        panel.close()
        panel._thread.join(3)
