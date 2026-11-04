"""Bounded, best-effort analysis queue; recording never waits for its consumer.

When the consumer falls behind (the queue is full) the batch is skipped and the analysis has a
gap -- but it is not abandoned: once there is room again a continuity boundary (the pause's
flush) goes in first, so nothing is joined across the gap, and the analysis carries on. A
hiccup of a second (a garbage collection, a first import, a busy frame) used to close the
analysis for the rest of the run: the live plots froze while the photons were still recorded,
which looked like an acquisition that had stopped. The run is still reported incomplete
(:attr:`reason`). A consumer that *fails* (raises) stops for good -- that is a bug, not load.
"""
from __future__ import annotations

import queue
import threading

import numpy as np

from .sources import PhotonBatch


class BoundedAnalysis:
    def __init__(self, push, flush, *, capacity=4, max_batch_events=250_000):
        if capacity < 1 or max_batch_events < 1:
            raise ValueError('analysis queue limits must be positive')
        self._push = push
        self._flush = flush
        self._queue = queue.Queue(maxsize=capacity)
        self.max_batch_events = max_batch_events
        self._closed = threading.Event()
        self._finished = threading.Event()
        self.reason = ''
        self.skipped_batches = 0
        #: Gaps the analysis has had (each: skipped batches, then a boundary, then on again).
        self.gaps = 0
        self._gap_pending = False
        # Whether a batch went in since the last boundary: only then can a gap join two stretches.
        self._since_boundary = True
        self._thread = threading.Thread(target=self._run, name='live-analysis', daemon=True)
        self._thread.start()

    def _disable(self, why):
        if not self._closed.is_set():
            self.reason = why
            self._closed.set()

    def disable(self, reason):
        """Permanently stop input when the stream develops a gap."""
        self._disable(reason)

    def submit(self, batch):
        if self._closed.is_set():
            self.skipped_batches += 1
            return False
        if len(batch) > self.max_batch_events:
            self._gap('Live analysis skipped a batch above its event budget; it continues.')
            return False
        if self._gap_pending:
            # Close the gap first: a boundary flushes the continuity, so the next batch starts a
            # new stretch instead of being joined to the one before the gap.
            try:
                self._queue.put_nowait(None)
                self._gap_pending = False
                self._since_boundary = False
            except queue.Full:
                self.skipped_batches += 1
                return False
        # Copy decoded events only, never native raw writer buffers. Source objects may reuse memory.
        try:
            item = PhotonBatch(*(np.array(v, copy=True) for v in
                                 (batch.macro, batch.micro, batch.channel)),
                               event=None if batch.event is None else np.array(batch.event, copy=True))
        except Exception as exc:
            self.skipped_batches += 1
            self._disable(f"Live analysis could not copy a batch: {type(exc).__name__}: {exc}")
            return False
        try:
            self._queue.put_nowait(item)
            self._since_boundary = True
            return True
        except queue.Full:
            self._gap('Live analysis could not keep up and skipped photons; it continues.')
            return False

    def _gap(self, why):
        """Skip the batch at hand and mark a gap; the analysis resumes after a boundary."""
        self.skipped_batches += 1
        if not self._gap_pending and self._since_boundary:
            self.gaps += 1
            self._gap_pending = True
        if not self.reason:
            self.reason = why

    def boundary(self):
        """Flush continuity before an analysis pause; never wait for the consumer."""
        if self._closed.is_set():
            return False
        try:
            self._queue.put_nowait(None)
            self._since_boundary = False
            return True
        except queue.Full:
            self._gap('Live analysis could not keep up and skipped photons; it continues.')
            return False

    def finish(self, timeout=1.0):
        self._finished.set()
        self._thread.join(timeout)
        if self._thread.is_alive():
            self._disable('Live analysis did not finish; raw recording was closed.')
            return False
        return not self._closed.is_set() and not self.gaps

    def _run(self):
        while not (self._finished.is_set() and self._queue.empty()):
            try:
                item = self._queue.get(timeout=.05)
            except queue.Empty:
                continue
            try:
                if item is None:
                    self._flush()
                else:
                    self._push(item)
            except Exception as exc:  # optional analysis never terminates recording
                self._disable(f'Live analysis failed: {type(exc).__name__}: {exc}')
                # The failing consumer must never process later batches as a continuous stream.
                return
            finally:
                self._queue.task_done()
