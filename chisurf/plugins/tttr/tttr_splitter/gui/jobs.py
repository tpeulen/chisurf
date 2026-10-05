"""Single-job execution with publication on the EMTK frame thread."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event


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

    def start(self, work, publish, error):
        if self.running:
            return False
        self.cancelled.clear()
        self.publish, self.error = publish, error
        self.future = self.executor.submit(work)
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
