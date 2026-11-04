"""Optional analysis cannot backpressure the capture loop or join over gaps."""
import threading
import numpy as np

from chisurf.plugins.core.acq.live.bounded_analysis import BoundedAnalysis
from chisurf.plugins.core.acq.live.sources import PhotonBatch


def batch(t):
    return PhotonBatch(np.array([t], np.uint64), np.zeros(1, np.uint16),
                       np.zeros(1, np.int8))


def test_overload_never_blocks_skips_and_resumes_after_a_boundary():
    """A full queue skips the batch (never blocks the recording), then the analysis resumes --
    after a boundary, so the stretches before and after the gap are never joined."""
    entered, release = threading.Event(), threading.Event()
    seen, flushes = [], []

    def stalled(item):
        entered.set()
        assert release.wait(5)
        seen.extend(item.macro.tolist())

    worker = BoundedAnalysis(stalled, lambda: flushes.append(len(seen)), capacity=1)
    try:
        a = batch(1)
        assert worker.submit(a)
        assert entered.wait(5)
        a.macro[0] = 99  # the queued copy is the analysis', not the source's buffer
        assert worker.submit(batch(2))
        assert not worker.submit(batch(3))  # full: skipped, a gap
        assert not worker.submit(batch(4))  # still full: skipped, the same gap
        assert worker.skipped_batches == 2 and worker.gaps == 1
        assert 'could not keep up' in worker.reason
    finally:
        release.set()
    # room again: the boundary goes in before the next batch, and the analysis carries on
    for _ in range(200):
        if worker.submit(batch(5)):
            break
        threading.Event().wait(0.01)
    assert not worker.finish(5)  # incomplete: the run had a gap
    assert seen == [1, 2, 5]
    assert flushes and flushes[0] == 2  # flushed after 1, 2 -- before 5


def test_consumer_failure_is_isolated_and_signalled():
    entered = threading.Event()
    def fail(_):
        entered.set()
        raise ValueError('broken optional analysis')
    worker = BoundedAnalysis(fail, lambda: None)
    assert worker.submit(batch(1))
    assert entered.wait(5)
    assert not worker.finish(5)
    assert 'broken optional analysis' in worker.reason
