"""Single-job execution with publication on the EMTK frame thread."""

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event

from chisurf.emtk import job_gate


class BackgroundJob:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tttr")
        self.future = None
        self.publish = None
        self.error = None
        self.cancelled = Event()

    @property
    def running(self):
        return self.future is not None

    @property
    def busy(self):
        """Alias of :attr:`running` under the name ``emtk.testing.Driver.settle`` waits on."""
        return self.running

    def start(self, work, publish, error):
        if self.running:
            return False
        self.cancelled.clear()
        self.publish, self.error = publish, error
        ticket = job_gate.admit()

        def guarded():
            with job_gate.hold(ticket, self.cancelled.is_set) as go:
                return work() if go else None

        try:
            self.future = self.executor.submit(guarded)
        except RuntimeError:
            # No thread can be started (Pyodide without cross-origin
            # isolation): run the work inline and hand poll() an already
            # finished future, so publication and error reporting flow the
            # exact same path as on a thread-capable host. An inline run
            # cannot be cancelled -- stop() before start() still clears the
            # gate check, and the frame blocks for the work's duration.
            inline = Future()
            try:
                inline.set_result(guarded())
            except BaseException as exc:  # noqa: BLE001 - reported via poll()
                inline.set_exception(exc)
            self.future = inline
        return True

    def poll(self):
        future = self.future
        if future is None or not future.done():
            return
        self.future = None
        try:
            result = future.result()
        except Exception as exc:
            self.error(exc)
        else:
            if not self.cancelled.is_set():
                self.publish(result)

    def stop(self):
        self.cancelled.set()
        if self.future is not None:
            self.future.cancel()

    def close(self):
        self.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
