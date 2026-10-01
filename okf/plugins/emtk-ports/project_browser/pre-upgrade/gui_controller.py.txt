"""Run database and archive I/O away from the native render thread."""

from concurrent.futures import ThreadPoolExecutor


class ProjectJobs:
    def __init__(self, model):
        self.model = model
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="project-browser")
        self.future = None
        self.callback = None
        self.closed = False

    def start(self, label, action, callback=None):
        if self.closed:
            return False
        if self.future is not None:
            raise RuntimeError("Wait for the current project operation to finish.")
        self.model.status = label + "…"
        self.callback = callback
        self.future = self.executor.submit(action)
        try:
            from emtk import im

            context = im.get_current_context()
        except RuntimeError:
            context = None
        if context is not None:
            self.future.add_done_callback(lambda future: context.request_frame())
        return True

    def poll(self):
        if self.future is None or not self.future.done():
            return False
        future, callback = self.future, self.callback
        self.future = self.callback = None
        if self.closed:
            return False
        try:
            result = future.result()
            if callback is not None:
                callback(result)
        except Exception as exc:
            self.model.status = "Error: " + str(exc)
        return True

    def close(self):
        self.closed = True
        if self.future is not None:
            self.future.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
