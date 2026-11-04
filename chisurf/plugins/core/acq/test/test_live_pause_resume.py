"""Pause live analysis while preserving the full raw recording and TCSPC clock."""
import queue
import time
import numpy as np
import tttrlib
from chisurf.plugins.core.acq.live.sources import PhotonBatch, PhotonSource, SourceInfo
from chisurf.plugins.core.acq.live.session import RecordSession


class ControlledSource:
    info = SourceInfo('controlled test source', 1e-6, 1e-9, 1000)
    def __init__(self):
        self.q = queue.Queue()
        self.finished = False
    def start(self):
        pass
    def stop(self):
        self.finished = True
    def status(self):
        return {}
    def read(self, timeout=.2):
        try:
            return self.q.get(timeout=.01)
        except queue.Empty:
            return None
    def put(self, ticks):
        self.q.put(PhotonBatch(np.asarray(ticks, np.uint64), np.zeros(len(ticks), np.uint16),
                               np.zeros(len(ticks), np.int8)))


def until(pred):
    deadline = time.monotonic() + 5
    while not pred():
        assert time.monotonic() < deadline
        time.sleep(.01)


def test_pause_resume_preserves_raw_photons_and_marks_incomplete_analysis(tmp_path):
    source = ControlledSource()
    path = tmp_path / 'interrupted.ptu'
    s = RecordSession(source, ptu_path=path)
    s.start()
    try:
        source.put([100, 200])
        until(lambda: s.snapshot()['photons'] == 2)
        assert s.pause()
        until(lambda: s.paused)
        source.put([300, 310])
        until(lambda: s.paused_photons == 2)
        assert s.snapshot()["qc"]["level"] == "grey"
        assert s.snapshot()["received_photons"] == 4
        assert s.snapshot()["photons"] == 2  # analyzed only
        assert s.resume()
        until(lambda: not s.paused)
        source.put([400, 500])
        until(lambda: s.snapshot()['received_photons'] == 6)
        assert s.snapshot()['photons'] == 2  # analysis never bridges the gap
        s.stop()
        assert s.wait(5) is not None
    finally:
        s.stop()
        s.wait(5)
    events = tttrlib.TTTR(str(path), 'PTU')
    mask = events.event_types == 0
    assert list(events.macro_times[mask]) == [100, 200, 300, 310, 400, 500]
    assert list(events.routing_channels[~mask]) == [13, 14]
    assert np.all(np.diff(events.macro_times.astype(np.int64)) >= 0)
    assert len(list(tmp_path.glob('*.ptu'))) == 1
    assert s.result.photons == 2  # only pre-pause photons were analyzed
    assert not s.result.analysis_complete
    assert s.result.qc["level"] == "grey"
    assert s.snapshot()["analysis_gap"]
    assert s.snapshot()["received_photons"] == 6


def test_start_pause_resume_stop_controls_keep_the_same_ptu(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    m = RecordModel(output_dir=tmp_path, realtime=True)
    app = RecordApp(m)
    ui = Driver(app, (1500, 950))
    try:
        m.load_example()
        ui.draw(3)
        ui.click('start_pause')
        until(lambda: m.running and m.snapshot is not None if (m.poll(force=True) is None) else False)
        path = m.saved_path
        ui.click('start_pause')
        until(lambda: m.session.paused)
        ui.draw(3)
        assert any('End pause' in text for text in ui.strings())
        assert not any('Resume analysis' in text for text in ui.strings())
        ui.click('start_pause')
        until(lambda: not m.session.paused)
        assert 'new run' in m.status_detail.lower()
        assert 'cannot resume' in m.session.snapshot()['analysis_warning']
        assert m.saved_path == path
        ui.click('stop')
        until(lambda: not m.running)
        m.poll(force=True)
        assert m.session.result is not None
        assert m.saved_path == path
    finally:
        app.close()


def test_pause_refuses_hardware_with_external_markers_enabled(tmp_path):
    from types import SimpleNamespace
    source = ControlledSource()
    source.device = SimpleNamespace(get_parameter=lambda *a: 15)
    s = RecordSession(source, ptu_path=tmp_path / 'markers.ptu')
    s.start()
    try:
        assert not s.pause()
        assert 'marker' in s.pause_error.lower()
    finally:
        s.stop()
        s.wait(5)


def test_empty_analysis_pause_is_still_an_explicit_gap(tmp_path):
    source = ControlledSource()
    s = RecordSession(source, ptu_path=tmp_path / "empty-pause.ptu")
    s.start()
    try:
        source.put([100, 200])
        until(lambda: s.snapshot()["photons"] == 2)
        assert s.pause()
        until(lambda: s.paused)
        assert s.paused_photons == 0
        assert s.snapshot()["analysis_gap"]
        assert s.snapshot()["qc"]["level"] == "grey"
        assert s.resume()
        until(lambda: not s.paused)
        s.stop()
        assert not s.wait(5).analysis_complete
    finally:
        s.stop()
        s.wait(5)


def test_received_snapshot_remains_consistent_during_batch_update(tmp_path):
    import threading

    source = ControlledSource()
    session = RecordSession(source)
    session._write_batch(PhotonBatch(np.array([100, 200], np.uint64),
                                     np.zeros(2, np.uint16), np.zeros(2, np.int8)))
    entered, release = threading.Event(), threading.Event()

    class BlockingBatch(PhotonBatch):
        def photons(self):
            entered.set()
            assert release.wait(5)
            return self

    batch = BlockingBatch(np.array([300, 400], np.uint64),
                          np.zeros(2, np.uint16), np.zeros(2, np.int8))
    thread = threading.Thread(target=session._write_batch, args=(batch,))
    thread.start()
    try:
        assert entered.wait(5)
        snap = session.snapshot()
        assert snap["received_photons"] == 2
        assert np.isclose(snap["received_elapsed_s"], 100e-6)
    finally:
        release.set()
        thread.join(5)
    snap = session.snapshot()
    assert snap["received_photons"] == 4
    assert np.isclose(snap["received_elapsed_s"], 300e-6)


def test_paused_point_still_applies_bleach_stop(tmp_path):
    from chisurf.plugins.core.acq.live.points import PointRecordSession
    class Bleach:
        bleached_at_s = None
        level_kcps = None
        threshold_kcps = None
        def push(self, macro, clock):
            self.bleached_at_s = 0.1
            return True
    source = ControlledSource()
    session = PointRecordSession(source, point=(0., 0.), index=0, bleach=Bleach(),
                                 ptu_path=tmp_path / 'bleach.ptu')
    session.start()
    try:
        assert session.pause()
        until(lambda: session.paused)
        source.put([100, 200])
        result = session.wait(5)
        assert result is not None and result.stop_reason == 'bleached'
        assert tttrlib.TTTR(str(result.ptu), 'PTU').macro_times.tolist()[-2:] == [100, 200]
    finally:
        session.stop()
        session.wait(5)
