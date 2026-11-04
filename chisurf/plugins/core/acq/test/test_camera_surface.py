"""Camera startup and controls use simulated sources only."""
import time
import numpy as np

from chisurf.plugins.core.acq.gui import video_panel
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.core.acq.live.video import VideoFrame
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_restored_camera_connects_once_after_settings_are_loaded(tmp_path, monkeypatch):
    opened = []
    class Source:
        def open(self): opened.append('opened')
        def read(self):
            time.sleep(.01)
            return VideoFrame(np.zeros((8, 8, 3), dtype=np.uint8), time.monotonic())
        def close(self): pass
    monkeypatch.setattr(video_panel, 'source_for', lambda address: (opened.append(address), Source())[1])
    app = RecordApp(RecordModel(output_dir=tmp_path))
    try:
        assert opened == []
        app.restore_settings({'video': {'address': 'fake:configured'}})
        assert opened == []
        ui = Driver(app, (1500, 950)); ui.draw(3)
        deadline = time.monotonic() + 2
        while not app.video._connected and time.monotonic() < deadline: time.sleep(.01)
        assert opened == ['fake:configured', 'opened']
        ui.draw(3)
        assert opened == ['fake:configured', 'opened']
    finally:
        app.close()
        if app.video._thread: app.video._thread.join(2)


def test_camera_empty_surface_and_context_menu(tmp_path, monkeypatch):
    monkeypatch.setattr(video_panel, 'source_for', lambda address: (_ for _ in ()).throw(AssertionError('unexpected camera probe')))
    app = RecordApp(RecordModel(output_dir=tmp_path))
    try:
        ui = Driver(app, (1500, 950)); app.focus_dock('video'); ui.draw(3)
        assert app.video.status.startswith('Camera unavailable')
        assert 'camera_frame' in app.video_form.rects
        assert not {'address', 'record', 'stop_recording'} & set(app.video_form.rects)
        x, y, w, h = app.video_form.rects['camera_frame']
        app.pointer_move(x + w / 2, y + min(h / 2, 60)); ui.draw(1)
        app.pointer_press(x + w / 2, y + min(h / 2, 60), 2, 0); ui.draw(1)
        app.pointer_release(x + w / 2, y + min(h / 2, 60), 2); ui.draw(2)
        assert {'address', 'connect', 'output', 'record', 'stop_recording'} <= set(app.video_form.rects)
    finally: app.close()


def test_failed_configured_camera_reports_unavailable(tmp_path, monkeypatch):
    class Broken:
        def open(self): raise RuntimeError('not present')
        def close(self): pass
    monkeypatch.setattr(video_panel, 'source_for', lambda address: Broken())
    app = RecordApp(RecordModel(output_dir=tmp_path))
    try:
        app.restore_settings({'video': {'address': 'fake:missing'}})
        Driver(app, (1500, 950)).draw(1)
        app.video._thread.join(2)
        assert 'Camera unavailable' in app.video.status and 'not present' in app.video.status
        assert app.video.frame is None
    finally: app.close()


def test_hidden_preview_pauses_reads_but_recording_keeps_them(monkeypatch):
    reads = []
    class Source:
        def open(self): pass
        def read(self):
            time.sleep(.005); reads.append(1)
            return VideoFrame(np.zeros((8, 8, 3), dtype=np.uint8), time.monotonic())
        def close(self): pass
    monkeypatch.setattr(video_panel, 'source_for', lambda address: Source())
    panel = video_panel.VideoPanel(); panel.preview_visible = False; panel.connect()
    try:
        deadline = time.monotonic() + 2
        while not panel._connected and time.monotonic() < deadline: time.sleep(.01)
        time.sleep(.15)
        assert not reads
        panel.preview_visible = True
        deadline = time.monotonic() + 2
        while not reads and time.monotonic() < deadline: time.sleep(.01)
        assert reads
        panel.preview_visible = False
        time.sleep(.15); previous = len(reads)
        time.sleep(.15); assert len(reads) == previous
        # A live recording must continue receiving frames even when the dock is hidden.
        class Recorder:
            def write(self, frame): return []
            def close(self): pass
        panel._recorder = Recorder()
        deadline = time.monotonic() + 2
        while len(reads) == previous and time.monotonic() < deadline: time.sleep(.01)
        assert len(reads) > previous
    finally:
        panel.close(); panel._thread.join(2)


def test_lost_capture_clears_last_frame(monkeypatch):
    for fail in (False, True):
        class Source:
            calls = 0
            def open(self): pass
            def read(self):
                self.calls += 1
                if self.calls == 1:
                    return VideoFrame(np.zeros((8, 8, 3), dtype=np.uint8), time.monotonic())
                if fail: raise RuntimeError('camera unplugged')
                return None
            def close(self): pass
        monkeypatch.setattr(video_panel, 'source_for', lambda address: Source())
        panel = video_panel.VideoPanel(); panel.connect(); panel._thread.join(2)
        assert not panel._thread.is_alive()
        assert panel.frame is None and not panel._connected
        assert 'unavailable' in panel.status.lower()
        panel.close()


def test_recorder_close_error_does_not_leave_frame_or_source_open(monkeypatch):
    closed = []
    class Source:
        calls = 0
        def open(self): pass
        def read(self):
            self.calls += 1
            if self.calls == 1:
                return VideoFrame(np.zeros((8, 8, 3), dtype=np.uint8), time.monotonic())
            time.sleep(.01)
            return None
        def close(self): closed.append(True)
    class Recorder:
        def write(self, frame): return []
        def close(self): raise RuntimeError('finalization failed')
    monkeypatch.setattr(video_panel, 'source_for', lambda address: Source())
    panel = video_panel.VideoPanel(); panel._recorder = Recorder(); panel.connect(); panel._thread.join(2)
    assert not panel._thread.is_alive() and closed
    assert panel.frame is None and panel._recorder is None
    assert 'finalization failed' in panel.status


def test_stop_recording_reports_finalization_failure():
    class Recorder:
        def close(self): raise RuntimeError('disk failed')
    panel = video_panel.VideoPanel(); panel._recorder = Recorder()
    panel.stop_recording(); panel._finalizer.join(2)
    assert not panel._finalizer.is_alive()
    assert panel._recorder is None
    assert 'finalization failed' in panel.status and 'disk failed' in panel.status


def test_finalization_error_survives_disconnect_status_in_both_orders(monkeypatch):
    import threading
    for finish_first in (False, True):
        entered = threading.Event(); release = threading.Event()
        class Source:
            def open(self): pass
            def read(self):
                entered.set(); release.wait(2)
                return None
            def close(self): pass
        class Recorder:
            def close(self): raise RuntimeError('durable error')
        monkeypatch.setattr(video_panel, 'source_for', lambda address: Source())
        panel = video_panel.VideoPanel(); panel.connect(); assert entered.wait(2)
        panel._recorder = Recorder()
        if finish_first:
            panel.stop_recording(); panel._finalizer.join(2)
            panel.disconnect(); release.set(); panel._thread.join(2)
        else:
            panel._stop.set(); release.set(); panel._thread.join(2)
            panel.disconnect()
        assert not panel._thread.is_alive()
        assert 'durable error' in panel.status
