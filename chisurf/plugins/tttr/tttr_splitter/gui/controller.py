"""Pure EMTK split/convert controller with the original scientific model.

The inputs are the Datasets workspace: the stream to split and the batch queue are picked in two
Input sections (the manifest's ``accepts`` ``split`` and ``batch``), or handed over by *Open in…* /
a drag; the files a split writes come back into the workspace as children of their input.
"""

from copy import copy
from pathlib import Path

from emtk import im
from emtk.file_dialog import FileDialog

from chisurf.core.support.i18n import tr
from chisurf.plugins.tttr.workspace_io import NamedWorkspaceInput, register_outputs

from .app import SplitterApp
from .jobs import BackgroundJob
from .view_model import SplitterViewModel, read_tttr


class SplitterController:
    def __init__(self):
        self._model = SplitterViewModel()
        #: The workspace dataset of the input, and of each queued batch file.
        self.source_uid = ""
        self.batch_sources: dict[str, str] = {}
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
            on_browse_output=self._browse_output,
            on_run=self._run,
            on_clear_batch=self._clear_batch,
            on_run_batch=self._start_batch,
        )
        #: The Input sections: the stream to split, and the batch queue's streams.
        self.split_input = NamedWorkspaceInput("tttr_splitter", "split", self.app, height=72)
        self.batch_input = NamedWorkspaceInput("tttr_splitter", "batch", self.app, height=72)
        tour = self.app.splitter_gui.tour
        # a pick tells the tour under the key its step names (the section's rect is remembered so)
        self.split_input.workspace_input_on_used = lambda _key: tour.notify_used("input")
        self.batch_input.workspace_input_on_used = lambda _key: tour.notify_used("batch_files")

    def request_frame(self):
        try:
            ctx = im.get_current_context()
        except RuntimeError:
            return
        ctx.request_frame()

    def _browse_output(self):
        """Where the split files go (an output: the input comes from the workspace)."""
        # not-input: the output folder the split files are written to
        self.dialog = FileDialog("Output folder", mode="folder")
        self.dialog_callback = lambda paths: setattr(self._model, "output_folder", str(paths[0]))

    def load_example(self):
        """Generate the demonstration stream, add it to the workspace and load it, as a picked row
        would be; the output goes beside the cache."""
        from chisurf.plugins.tttr.workspace_io import example_into_workspace

        from ..demo import demo_folder, make_demo

        if self.job.running:
            return False
        try:
            path = make_demo(demo_folder())
        except OSError as exc:
            self.message = str(exc)
            return False
        self._model.output_folder = str(demo_folder())
        example_into_workspace(path, receive_split, self.app, key="file")
        return True

    def load_input(self, path, source=""):
        """Read the photon stream *path* (a file or a container's stream) as the input to split;
        *source* is the workspace dataset it came from."""
        from chisurf.core.fio.address import container_of

        if self.job.running:
            return
        if not container_of(str(path)).is_file():
            self.message = f"Could not load {path}: file does not exist"
            return
        kind = self._model.tttr_type
        self.source_uid = str(source or "")

        def work():
            return read_tttr(str(path), kind)

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
            register_outputs(snapshot.last_written, result_of=self.source_uid)

        def error(exc):
            self.message = f"Split failed: {exc}"
            self.run_running = False

        self.job.start(lambda: snapshot.do_split(progress_cb=progress), publish, error)

    def _queue_batch_paths(self, paths, sources=None):
        """Queue PTU streams (files or container members) for the batch run; *sources* maps an
        address to the workspace dataset it came from."""
        known = set(self._model.batch_files)
        for path in paths:
            text = str(path)
            if Path(text).suffix.lower() == ".ptu" and text not in known:
                self._model.batch_files.append(text)
                known.add(text)
                if sources and sources.get(text):
                    self.batch_sources[text] = str(sources[text])

    def _clear_batch(self):
        self._model.batch_files = []
        self.batch_sources = {}
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
            for source, written in snapshot.batch_written.items():
                register_outputs(written, result_of=self.batch_sources.get(source, ""))

        def error(exc):
            self.message = f"Batch failed: {exc}"
            self.batch_running = False

        self.job.start(lambda: snapshot.run_batch(file_progress_cb=progress), publish, error)


#: Model fields that are the user's choices; saved with the window and restored on reopen.
SPLITTER_FIELDS = (
    "input_format",
    "output_format",
    "photons_per_file_k",
    "microtime_binning",
    "split_files",
    "reset_macro_times",
    "keep_original",
    "batch_use_parent",
    "input_file",
    "output_folder",
    "batch_files",
)


class _StandaloneApp(SplitterApp):
    def export_settings(self):
        """Return the split/convert options as JSON-able preferences."""
        return {name: getattr(self.tool._model, name) for name in SPLITTER_FIELDS}

    def restore_settings(self, state):
        """Apply preferences saved by :meth:`export_settings`; a vanished input file is skipped."""
        for name in SPLITTER_FIELDS:
            if name in state:
                setattr(self.tool._model, name, state[name])
        if state.get("input_file") and Path(state["input_file"]).is_file():
            self.tool.load_input(state["input_file"])

    def close(self):
        self.tool.job.close()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.continuous = True
        self.splitter_gui.docks.window("io").draw = self._draw_io

    def _draw_io(self, box):
        """Keep operation status and cancellation inside the existing input/output dock."""
        self.splitter_gui._draw_io(box)
        if self.tool.job.running:
            im.text(tr("Working…"))
            if im.button(tr("Stop"), role="danger"):
                self.tool.job.stop()
                self.tool.message = (
                    "Stopping after the current chunk or file. Completed output remains."
                )
            im.set_item_tooltip(tr("Stop between chunks or files; retain output already written."))
        if self.tool.message:
            im.text_wrapped(self.tool.message)

    def _render(self):
        self.tool.job.poll()
        if not self.tool.job.running:
            self.tool.run_running = False
            self.tool.batch_running = False
        super()._render()
        if self.tool.dialog is not None:
            if im.begin("Output folder"):
                result = self.tool.dialog.draw()
                if result:
                    callback = self.tool.dialog_callback
                    self.tool.dialog = None
                    callback(result)
                elif result is False:
                    self.tool.dialog = None
            im.end()


def create_app():
    return SplitterController().app


def _addresses(given) -> list[str]:
    from chisurf.core.plugin.workspace_input import read_address

    return [read_address(str(a)) for a in ([given] if isinstance(given, str) else list(given))]


def receive_split(app, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``split``): load ``payload["file"]`` -- a TTTR file
    or a container's photon stream, as the workspace hands it -- as the input to split."""
    from chisurf.core.fio.address import container_of

    (address,) = _addresses(payload["file"])
    if not container_of(address).is_file():
        raise FileNotFoundError(f"{address} does not exist")
    if app.tool.job.running:
        raise RuntimeError(tr("the tool is busy; try again when it has finished"))
    app.tool.load_input(address, source=str((payload.get("datasets") or [""])[0]))


def receive_batch(app, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``batch``): queue the PTU streams ``payload["files"]``
    for the batch run (other formats are left out, as the batch only writes from PTU)."""
    addresses = _addresses(payload["files"])
    uids = [str(u) for u in payload.get("datasets") or []]
    app.tool._queue_batch_paths(addresses, sources=dict(zip(addresses, uids)))
