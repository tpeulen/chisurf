"""Recorded batches reach the writer before optional live analysis."""
import queue
import time

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.core.acq.live.session import RecordSession
from chisurf.plugins.core.acq.live.sources import PhotonBatch, SourceInfo


class Source:
    info = SourceInfo('test', 1e-6, 1e-9, 1000)

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


def test_write_precedes_live_analysis():
    src = Source()
    session = RecordSession(src)
    observed = []
    write, push = session._write_batch, session._push
    session._write_batch = lambda batch: (observed.append('write'), write(batch))[-1]
    session._push = lambda batch: (observed.append('analysis'), push(batch))[-1]
    src.q.put(PhotonBatch(np.array([1, 2], np.uint64), np.zeros(2, np.uint16),
                          np.zeros(2, np.int8)))
    session.start()
    deadline = time.monotonic() + 5
    while len(observed) < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    session.stop()
    assert session.wait(5) is not None
    assert observed == ['write', 'analysis']


def test_batch_is_recorded_when_analysis_raises(tmp_path):
    src = Source()
    path = tmp_path / 'writer-first.ptu'
    session = RecordSession(src, ptu_path=path)

    def fail(_batch):
        raise ValueError('simulated analysis failure')

    session._push = fail
    src.q.put(PhotonBatch(np.array([100, 200], np.uint64), np.zeros(2, np.uint16),
                          np.zeros(2, np.int8)))
    session.start()
    deadline = time.monotonic() + 5
    while not session.snapshot().get("analysis_warning") and time.monotonic() < deadline:
        time.sleep(.01)
    assert session.running  # optional failure must not stop capture
    src.q.put(PhotonBatch(np.array([300, 400], np.uint64), np.zeros(2, np.uint16),
                          np.zeros(2, np.int8)))
    deadline = time.monotonic() + 5
    while session.snapshot()["received_photons"] < 4 and time.monotonic() < deadline:
        time.sleep(.01)
    assert session.snapshot()["received_photons"] == 4
    session.stop()
    assert session.wait(5) is not None
    assert 'simulated analysis failure' in session.snapshot()["analysis_warning"]
    recorded = tttrlib.TTTR(str(path), 'PTU')
    assert recorded.macro_times.tolist() == [100, 200, 300, 400]
    assert not session.result.analysis_complete


@pytest.mark.parametrize('failure', ['flush', 'table'])
def test_finalization_failure_still_closes_and_reports_ptu(tmp_path, failure):
    src = Source()
    path = tmp_path / 'finalization.ptu'
    session = RecordSession(src, ptu_path=path)

    def fail(*_args):
        raise ValueError('simulated finalization failure')

    if failure == 'flush':
        class AnalyzerProxy:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def __getattr__(self, name):
                return fail if name == 'flush' else getattr(self.wrapped, name)

        session.analyzer = AnalyzerProxy(session.analyzer)
    else:
        session.table = fail
    src.q.put(PhotonBatch(np.array([100, 200], np.uint64), np.zeros(2, np.uint16),
                          np.zeros(2, np.int8)))
    session.start()
    deadline = time.monotonic() + 5
    while session.batches < 1 and time.monotonic() < deadline:
        time.sleep(.01)
    session.stop()
    result = session.wait(5)
    assert result is not None
    assert result.stop_reason == 'error'
    assert not result.analysis_complete
    assert result.table == {}
    assert 'simulated finalization failure' in session.error
    assert tttrlib.TTTR(str(path), 'PTU').macro_times.tolist() == [100, 200]


def test_writer_close_refusal_is_reported():
    class FailingWriter:
        def close(self):
            return False

        def error(self):
            return 'simulated disk failure'

    src = Source()
    src.finished = True
    session = RecordSession(src)
    session._writer = FailingWriter()
    session._run()
    assert session.result is not None
    assert session.result.stop_reason == 'error'
    assert not session.result.analysis_complete
    assert 'simulated disk failure' in session.error


def test_marker_collision_records_entire_batch_before_error(tmp_path):
    src = Source()
    path = tmp_path / 'collision.ptu'
    session = RecordSession(src, ptu_path=path)
    session._interrupt_used = True
    src.q.put(PhotonBatch(np.array([100, 200, 300], np.uint64),
                          np.zeros(3, np.uint16), np.array([0, 13, 1], np.int8),
                          event=np.array([0, 1, 0], np.int8)))
    session.start()
    result = session.wait(5)
    assert result is not None and result.stop_reason == 'error'
    assert 'collides' in session.error
    recorded = tttrlib.TTTR(str(path), 'PTU')
    assert recorded.macro_times.tolist() == [100, 200, 300]
    assert recorded.event_types.tolist() == [0, 1, 0]


def test_stalled_live_analysis_does_not_block_capture_or_lose_raw_events(tmp_path):
    import threading
    src = Source()
    path = tmp_path / 'overload.ptu'
    session = RecordSession(src, ptu_path=path)
    entered, release = threading.Event(), threading.Event()
    original = session._push
    def stall(batch):
        entered.set()
        assert release.wait(5)
        original(batch)
    session._push = stall
    session.start()
    try:
        src.q.put(PhotonBatch(np.array([100], np.uint64), np.zeros(1, np.uint16),
                              np.zeros(1, np.int8)))
        assert entered.wait(5)
        for t in range(200, 2200, 100):
            src.q.put(PhotonBatch(np.array([t], np.uint64), np.zeros(1, np.uint16),
                                  np.zeros(1, np.int8)))
        deadline = time.monotonic() + 5
        while session.snapshot()['received_photons'] < 21 and time.monotonic() < deadline:
            time.sleep(.01)
        assert session.snapshot()['received_photons'] == 21
        assert 'could not keep up' in session.snapshot()['analysis_warning']
        session.stop()
        # The raw writer closes even if the optional consumer is still stalled.
        result = session.wait(4)
        assert result is not None and not result.analysis_complete
        recorded = tttrlib.TTTR(str(path), 'PTU')
        assert recorded.macro_times.tolist() == list(range(100, 2200, 100))
        assert not result.run_address
    finally:
        release.set()
        session.stop()
        session.wait(5)


def test_duration_boundary_preserves_entire_delivered_batch(tmp_path):
    src = Source()
    path = tmp_path / 'deadline.ptu'
    src.q.put(PhotonBatch(np.array([100, 200, 300], np.uint64),
                          np.zeros(3, np.uint16), np.zeros(3, np.int8)))
    session = RecordSession(src, ptu_path=path, duration_s=150e-6)
    session.start()
    result = session.wait(5)
    assert result is not None and result.stop_reason == 'duration reached'
    assert tttrlib.TTTR(str(path), 'PTU').macro_times.tolist() == [100, 200, 300]


def test_stop_drains_source_contract_buffer(tmp_path):
    import threading
    class DrainingSource(Source):
        drain_after_stop = True
        def __init__(self):
            super().__init__()
            self.stopped = threading.Event()
            self.buffer_sent = False
        def stop(self):
            self.stopped.set()
        def read(self, timeout=.2):
            try:
                return self.q.get(timeout=.01)
            except queue.Empty:
                if self.stopped.is_set() and not self.buffer_sent:
                    self.buffer_sent = True
                    return PhotonBatch(np.array([300, 400], np.uint64),
                                       np.zeros(2, np.uint16), np.zeros(2, np.int8))
                if self.stopped.is_set():
                    self.finished = True
                return None
    src = DrainingSource()
    path = tmp_path / 'drained.ptu'
    src.q.put(PhotonBatch(np.array([100, 200], np.uint64), np.zeros(2, np.uint16),
                          np.zeros(2, np.int8)))
    session = RecordSession(src, ptu_path=path)
    session.start()
    deadline = time.monotonic() + 5
    while session.snapshot()['received_photons'] < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    session.stop()
    assert session.wait(5) is not None
    assert tttrlib.TTTR(str(path), 'PTU').macro_times.tolist() == [100, 200, 300, 400]


def test_guided_reference_metrics_are_invalidated_on_analysis_gap():
    from chisurf.plugins.core.acq.live.guided_analysis import GuidedRecordSession
    session = GuidedRecordSession(Source(), None, stage='fcs')
    session._last_reference_live = {'stage': 'fcs', 'metrics': {0: {'n_amplitude_estimate': 64}},
                                    'correlations': {0: {'g': [1.0]}}, 'quality': []}
    session._analysis_gap = True
    snap = session.snapshot()
    assert snap['analysis_gap']
    assert snap['reference_live']['metrics'] == {}
    assert snap['reference_live']['correlations'] == {}
    assert snap['reference_live']['quality'][0]['status'] == 'fail'


def test_source_stop_is_called_once_despite_repeated_session_stop():
    class OneStopSource(Source):
        def __init__(self):
            super().__init__()
            self.stop_count = 0
        def stop(self):
            self.stop_count += 1
            if self.stop_count > 1:
                raise RuntimeError('source stop is not idempotent')
            self.finished = True
    source = OneStopSource()
    session = RecordSession(source)
    session.start()
    session.stop()
    session.stop()
    result = session.wait(5)
    session.stop()
    assert result is not None
    assert source.stop_count == 1
    assert not session.error


def test_device_source_stop_is_idempotent_without_probing_hardware():
    import threading
    from types import SimpleNamespace
    from chisurf.plugins.core.acq.live.devices import DeviceSource
    calls = []
    device = SimpleNamespace(stop=lambda: calls.append('stop'))
    source = DeviceSource.__new__(DeviceSource)
    source.device, source._stop, source._stop_lock, source._error = (
        device, threading.Event(), threading.Lock(), '')
    threads = [threading.Thread(target=source.stop) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == ['stop']


def test_marker_collision_drains_buffered_source_before_reporting_error(tmp_path):
    import threading
    class DrainingSource(Source):
        drain_after_stop = True
        def __init__(self):
            super().__init__()
            self.stopped = threading.Event()
            self.sent = False
        def stop(self):
            self.stopped.set()
        def read(self, timeout=.2):
            try:
                return self.q.get(timeout=.01)
            except queue.Empty:
                if self.stopped.is_set() and not self.sent:
                    self.sent = True
                    return PhotonBatch(np.array([400, 500], np.uint64),
                                       np.zeros(2, np.uint16), np.zeros(2, np.int8))
                if self.stopped.is_set():
                    self.finished = True
                return None
    source = DrainingSource()
    source.q.put(PhotonBatch(np.array([100, 200, 300], np.uint64), np.zeros(3, np.uint16),
                             np.array([0, 13, 1], np.int8), event=np.array([0, 1, 0], np.int8)))
    session = RecordSession(source, ptu_path=tmp_path / 'collision-drain.ptu')
    session._interrupt_used = True
    session.start()
    result = session.wait(5)
    assert result is not None and result.stop_reason == 'error'
    assert 'collides' in session.error
    assert tttrlib.TTTR(str(result.ptu), 'PTU').macro_times.tolist() == [100, 200, 300, 400, 500]


@pytest.mark.parametrize('source_status', [
    {'error': 'simulated device read failure', 'dropped': 0},
    {'error': '', 'dropped': 2},
])
def test_source_error_or_overflow_marks_recording_and_quality_failed(source_status):
    class FailedSource(Source):
        def status(self):
            return dict(source_status)
    source = FailedSource()
    source.finished = True
    session = RecordSession(source)
    session.start()
    result = session.wait(5)
    assert result.stop_reason == 'error'
    assert not result.analysis_complete
    assert session.snapshot()['qc']['level'] == 'grey'
    assert ('read failure' in session.error or 'overflow/loss' in session.error)


def test_capture_safety_failure_still_drains_buffered_events(tmp_path):
    import threading
    class DrainingSource(Source):
        drain_after_stop = True
        def __init__(self):
            super().__init__()
            self.stopped = threading.Event()
            self.sent = False
        def stop(self):
            self.stopped.set()
        def read(self, timeout=.2):
            try:
                return self.q.get(timeout=.01)
            except queue.Empty:
                if self.stopped.is_set() and not self.sent:
                    self.sent = True
                    return PhotonBatch(np.array([300, 400], np.uint64),
                                       np.zeros(2, np.uint16), np.zeros(2, np.int8))
                if self.stopped.is_set():
                    self.finished = True
                return None
    source = DrainingSource()
    source.q.put(PhotonBatch(np.array([100, 200], np.uint64), np.zeros(2, np.uint16),
                             np.zeros(2, np.int8)))
    session = RecordSession(source, ptu_path=tmp_path / 'safety-drain.ptu')
    def fail(_):
        raise ValueError('bleach safety failed')
    session._capture_batch = fail
    session.start()
    result = session.wait(5)
    assert result is not None and result.stop_reason == 'error'
    assert 'bleach safety failed' in session.error
    assert tttrlib.TTTR(str(result.ptu), 'PTU').macro_times.tolist() == [100, 200, 300, 400]


def test_set_trace_does_not_wait_for_stalled_analyzer():
    import threading
    src = Source()
    session = RecordSession(src)
    entered, release, changed = threading.Event(), threading.Event(), threading.Event()
    def stall(_):
        entered.set()
        assert release.wait(5)
    session._push = stall
    src.q.put(PhotonBatch(np.array([100], np.uint64), np.zeros(1, np.uint16),
                          np.zeros(1, np.int8)))
    session.start()
    try:
        assert entered.wait(5)
        thread = threading.Thread(target=lambda: (session.set_trace(2.0, .002), changed.set()))
        thread.start()
        assert changed.wait(1), 'UI trace setting must not wait on optional analysis'
        thread.join(1)
    finally:
        release.set()
        session.stop()
        session.wait(5)

@pytest.mark.parametrize('image', [False, True])
@pytest.mark.parametrize('failure', ['close', 'read', 'overflow'])
def test_model_poll_surfaces_recording_failures_and_no_verdict(tmp_path, image, failure):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live.imaging import ImageRecordSession
    from chisurf.plugins.core.acq.live.scanner import ScanSettings

    class FailedSource(Source):
        def status(self):
            if failure == 'read':
                return {'error': 'simulated read failure'}
            if failure == 'overflow':
                return {'dropped': 2}
            return {}

    class FailingWriter:
        def close(self):
            return False
        def error(self):
            return 'simulated close failure'

    source = FailedSource()
    source.finished = True
    path = tmp_path / 'recording.ptu'
    session = (ImageRecordSession(source, ScanSettings(), ptu_path=path) if image
               else RecordSession(source, ptu_path=path))
    if failure == 'close':
        session._writer = FailingWriter()
    session._run()
    assert session.result.qc['level'] == 'grey'
    assert session.snapshot()['qc']['level'] == 'grey'
    model = RecordModel(output_dir=tmp_path)
    model.session = session
    model._run_shutters = lambda *_: None
    model._poll_runs(force=True)
    assert model.status_text == 'Recording error'
    expected = {'close': 'simulated close failure', 'read': 'simulated read failure',
                'overflow': 'overflow/loss'}[failure]
    assert expected in model.status_detail
    model.session = None
    model.close()


def test_running_model_immediately_reports_source_overflow(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel

    class OverflowSource(Source):
        def status(self):
            return {'dropped': 3}

    source = OverflowSource()
    session = RecordSession(source)
    session.qc = {'ready': True, 'level': 'green'}
    session.start()
    model = RecordModel(output_dir=tmp_path)
    model.session = session
    model._poll_runs(force=True)
    assert model.snapshot['qc']['level'] == 'grey'
    assert 'overflow/loss' in model.status_detail
    session.stop()
    session.wait(5)
    model.session = None
    model.close()
