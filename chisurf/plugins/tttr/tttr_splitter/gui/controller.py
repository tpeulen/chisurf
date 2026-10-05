"""Pure EMTK split/convert controller with the original scientific model."""

from copy import copy
from pathlib import Path

import tttrlib
from emtk import im
from emtk.file_dialog import FileDialog

from .app import SplitterApp
from .jobs import BackgroundJob
from .view_model import SplitterViewModel


class SplitterController:
    def __init__(self, database_picker=None):
        self._model = SplitterViewModel()
        self.database_picker = database_picker
        self.dataset_picker = None
        self.run_progress = 0
        self.run_running = False
        self.batch_progress = (0, 0)
        self.batch_running = False
        self.message = ""
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_callback = None
        self.app = _StandaloneApp(
            self,
            on_browse_input=self._browse_input,
            on_browse_output=self._browse_output,
            on_run=self._run,
            on_add_batch_files=self._add_batch_files,
            on_add_batch_folder=self._add_batch_folder,
            on_clear_batch=self._clear_batch,
            on_run_batch=self._start_batch,
        )

    def request_frame(self):
        try:
            ctx = im.get_current_context()
        except RuntimeError:
            return
        ctx.request_frame()

    def choose(self, title, callback, mode="open", multiple=False):
        self.dialog = FileDialog(
            title,
            mode=mode,
            multiselect=multiple,
            filters="TTTR (*.ptu *.ht3 *.spc *.hdf *.raw *.sm);;All files (*)",
        )
        self.dialog_callback = callback

    def _browse_input(self):
        self.choose("Open TTTR", lambda paths: self.load_input(paths[0]))

    def _browse_output(self):
        self.choose(
            "Output folder",
            lambda paths: setattr(self._model, "output_folder", str(paths[0])),
            mode="folder",
        )

    def load_input(self, path):
        if self.job.running:
            return
        if not Path(path).is_file():
            self.message = f"Could not load {path}: file does not exist"
            return
        kind = self._model.tttr_type

        def work():
            return tttrlib.TTTR(str(path)) if kind is None else tttrlib.TTTR(str(path), kind)

        def publish(tttr):
            self._model.set_tttr(tttr, str(path))
            self.message = ""

        self.job.start(
            work, publish, lambda exc: setattr(self, "message", f"Could not load {path}: {exc}")
        )

    def _run(self):
        if self.job.running:
            return
        snapshot = copy(self._model)
        snapshot._observers = []
        reason = snapshot.can_split()
        if reason:
            self.message = reason
            return
        self.run_running = True
        self.run_progress = 0

        def progress(percent):
            if self.job.cancelled.is_set():
                raise RuntimeError("Split stopped between chunks; completed output files remain.")
            self.run_progress = int(percent)

        def publish(output):
            self.message = f"Complete: {output}"
            self.run_running = False
            self.run_progress = 100

        def error(exc):
            self.message = f"Split failed: {exc}"
            self.run_running = False

        self.job.start(lambda: snapshot.do_split(progress_cb=progress), publish, error)

    def _queue_batch_paths(self, paths):
        known = set(self._model.batch_files)
        for path in paths:
            text = str(path)
            if Path(text).suffix.lower() == ".ptu" and text not in known:
                self._model.batch_files.append(text)
                known.add(text)

    def _add_batch_files(self):
        self.choose("Add PTU files", self._queue_batch_paths, multiple=True)

    def _add_batch_folder(self):
        self.choose(
            "Add PTU folder",
            lambda paths: self._queue_batch_paths(
                sorted(p for p in Path(paths[0]).rglob("*") if p.is_file())
            ),
            mode="folder",
        )

    def _add_batch_database(self):
        if self.database_picker is not None:
            self._queue_batch_paths(self.database_picker() or [])
            return
        from chisurf.emtk.dataset_picker import DatasetPicker

        if self.dataset_picker is None:
            self.dataset_picker = DatasetPicker(on_paths=self._queue_batch_paths)
        self.dataset_picker.open()

    def _clear_batch(self):
        self._model.batch_files = []
        self.batch_progress = (0, 0)

    def _start_batch(self):
        if self.job.running:
            return
        snapshot = copy(self._model)
        snapshot._observers = []
        snapshot.batch_files = list(self._model.batch_files)
        if not snapshot.batch_files:
            self.message = "Add PTU files or folders first."
            return
        self.batch_running = True

        def progress(index, total, path):
            if self.job.cancelled.is_set():
                raise RuntimeError("Batch stopped between files; completed output files remain.")
            self.batch_progress = (index, total)

        def publish(count):
            self.message = f"Processed {count} file(s)."
            self.batch_running = False

        def error(exc):
            self.message = f"Batch failed: {exc}"
            self.batch_running = False

        self.job.start(lambda: snapshot.run_batch(file_progress_cb=progress), publish, error)


class _StandaloneApp(SplitterApp):
    def close(self):
        self.tool.job.close()
        if self.tool.dataset_picker is not None:
            self.tool.dataset_picker.close()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.continuous = True

    def _render(self):
        self.tool.job.poll()
        if not self.tool.job.running:
            self.tool.run_running = False
            self.tool.batch_running = False
        super()._render()
        if self.tool.dataset_picker is not None:
            vp = im.get_main_viewport()
            self.tool.dataset_picker.render((0.0, 0.0, *vp.size))
        if self.tool.job.running:
            if im.begin("TTTR operation"):
                im.text("Working…")
                if im.button("Stop"):
                    self.tool.job.stop()
                    self.tool.message = (
                        "Stopping after the current chunk or file. Completed output remains."
                    )
                im.set_item_tooltip("Stop between chunks or files; retain output already written.")
            im.end()
        if self.tool.message:
            if im.begin("Status"):
                im.text_wrapped(self.tool.message)
            im.end()
        if self.tool.dialog is not None:
            if im.begin("Choose files or folder"):
                result = self.tool.dialog.draw()
                if result:
                    callback = self.tool.dialog_callback
                    self.tool.dialog = None
                    callback(result)
                elif result is False:
                    self.tool.dialog = None
            im.end()


def create_app(database_picker=None):
    return SplitterController(database_picker=database_picker).app
