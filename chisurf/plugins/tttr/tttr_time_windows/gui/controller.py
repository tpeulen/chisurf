"""Pure EMTK time-window controller using the existing scientific backend.

The input is the Datasets workspace: photon streams picked in the Input section (or handed over
by *Open in…* / a drag) are queued through :func:`receive_files`; the windows written into each
measurement's container come back into the workspace as a burst run, a child of its stream.
"""

import logging
from pathlib import Path

from emtk import im
from emtk.dialog_window import DialogWindow
from emtk.docking import LayoutStore
from emtk.file_dialog import FileDialog
from emtk.i18n import tr

from chisurf.core.plugin.workspace_input import WorkspaceInputMixin
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from ..api.models import TimeWindowResult
from .app import TimeWindowApp
from .client import TimeWindowClient


def _supported_exts():
    """The TTTR file extensions tttrlib reads (the vendor list when tttrlib cannot say)."""
    found = set()
    try:
        import tttrlib

        for ext in getattr(tttrlib, "get_supported_filetypes", lambda: [])():
            text = str(ext).strip().lower()
            if text:
                found.add(text if text.startswith(".") else "." + text)
    except Exception:  # noqa: BLE001 - the fixed list below is the fallback
        pass
    return found or {".ptu", ".phu", ".ht2", ".ht3", ".pt3", ".t3r"}


def _is_supported_path(path):
    """Whether *path* has a supported TTTR extension, optionally ``.gz`` / ``.bz2``."""
    lower = str(path).lower()
    return any(
        lower.endswith(ext + suffix) for ext in _supported_exts() for suffix in ("", ".gz", ".bz2")
    )


class TimeWindowController(WorkspaceInputMixin):
    """The queue, the processing and the Input section's model (the workspace's photon streams)."""

    workspace_input_plugin = "tttr_time_windows"

    def __init__(self, client=None):
        self._client = client or TimeWindowClient()
        self._file_paths = []
        #: The workspace dataset each queued stream came from: its windows become that row's child.
        self._sources: dict[str, str] = {}
        self._last_result = None
        self._log_lines = []
        self.time_window_ms = 10.0
        self.output_dir_text = ""
        self.preview_data = None
        self.message = ""
        self.job = BackgroundJob()
        self._job_kind = ""
        #: Process was pressed while a preview loaded: it runs when the preview is in.
        self.process_pending = False
        self.dialog = None
        self.dialog_callback = None
        self.app = _StandaloneApp(
            self,
            on_process=self._process_all,
            on_clear=self._clear_all,
            on_browse=self._choose_dir,
        )
        self.workspace_input_app = self.app

    def on_time_window(self, _value=None):
        """The duration field changed: the preview's boundaries follow, and the tour hears it."""
        gui = self.app.time_window_gui
        gui.refresh_preview()
        gui._used("time_window")

    def notify(self, message, timeout=0):
        self.message = str(message)

    def request_frame(self):
        try:
            ctx = im.get_current_context()
        except RuntimeError:
            return
        ctx.request_frame()

    def _choose_dir(self):
        """Where a new container goes (an output: the input comes from the workspace)."""
        # not-input: the output folder a new container is written to
        self.dialog = FileDialog("Output folder", mode="folder")
        self.dialog_callback = lambda paths: setattr(self, "output_dir_text", str(paths[0]))

    def add_paths(self, paths, *, sources=None) -> None:
        """Queue photon streams (files or container members), keeping only supported TTTR
        types, in order; *sources* maps an address to the workspace dataset it came from."""
        known = {str(p) for p in self._file_paths}
        for path in paths:
            p = Path(path)
            if not _is_supported_path(str(p)) or str(p) in known:
                continue
            self._file_paths.append(p)
            known.add(str(p))
            if sources and sources.get(str(path)):
                self._sources[str(p)] = str(sources[str(path)])
        if self._file_paths and self.app.time_window_gui.preview_index < 0:
            self.app.time_window_gui.select_preview(0)
        self.request_frame()

    def load_example(self) -> bool:
        """Generate the demonstration stream in the settings cache, add it to the workspace and
        queue it, as a picked row would be."""
        from chisurf.plugins.tttr.workspace_io import example_into_workspace

        from ..demo import demo_folder, make_demo

        try:
            path = make_demo(demo_folder())
        except OSError as exc:
            self.notify(str(exc))
            return False
        example_into_workspace(path, receive_files, self.app, key="files", many=True)
        self.notify(f"Example queued: {Path(path).name}. Press Process.")
        return True

    def _remove_preview_file(self) -> None:
        if self.job.running:
            self.notify("Stop the current operation before removing files.")
            return
        gui = self.app.time_window_gui
        index = gui.preview_index
        if not 0 <= index < len(self._file_paths):
            return
        self._sources.pop(str(self._file_paths[index]), None)
        del self._file_paths[index]
        self.preview_data = None
        gui.preview = None
        gui.preview_index = -1
        if self._file_paths:
            gui.select_preview(min(index, len(self._file_paths) - 1))
        self.request_frame()

    def load_preview_for_index(self, index):
        if self.job.running or not 0 <= index < len(self._file_paths):
            return
        path = self._file_paths[index]
        duration = self.time_window_ms

        self._job_kind = "preview"

        def publish(data):
            self.preview_data = data if data and "counts" in data else None
            if self.preview_data is not None:
                self.preview_data["time_window_ms"] = duration
            self.app.time_window_gui.preview = self.preview_data
            self.notify(f"Preview: {path.name}" if self.preview_data else "Preview unavailable")
            if duration != self.time_window_ms:
                self.load_preview_for_index(index)

        self.job.start(
            lambda: self._client.load_preview(path, duration),
            publish,
            lambda exc: self._fail("Preview failed", f"Preview failed for {path.name}: {exc}"),
        )

    def _process_all(self):
        if self.job.running:
            # The Qt tool processed synchronously, so Process always ran; here a
            # preview load (started by adding a file) may hold the single worker.
            if self._job_kind == "preview":
                self.process_pending = True
                self.notify("Processing starts when the preview has loaded…")
            return
        self.process_pending = False
        files = list(self._file_paths)
        if not files:
            self._log("No TTTR files to process. Add files first.")
            return
        duration = float(self.time_window_ms)
        output = Path(self.output_dir_text.strip()) if self.output_dir_text.strip() else None
        self.notify("Processing files…")
        self._log(f"Processing {len(files)} file(s) with time window = {duration:.3f} ms…")
        self._job_kind = "process"

        def publish(result):
            self._last_result = TimeWindowResult(**result)
            metadata = result.get("metadata", {})
            out_dir = metadata.get("output_dir")
            if out_dir:
                self.output_dir_text = str(out_dir)
            self._log(
                f"Done: {len(files)} file(s), {metadata.get('total_windows', 0)} total windows. Output: {out_dir}"
            )
            for path, count in result.get("n_windows", {}).items():
                self._log(f"  {Path(path).name}: {count} windows")
            self._register_runs(result.get("output_paths", {}), duration)
            self.notify("Processing complete")

        self.job.start(
            lambda: self._client.analyze_files(files, time_window_ms=duration, output_dir=output),
            publish,
            lambda exc: self._fail("Processing failed", f"Processing failed: {exc}"),
        )

    def _register_runs(self, output_paths: dict, duration_ms: float) -> None:
        """Each container's new ``time_window`` run enters the workspace as a child of its stream."""
        from chisurf.core.fio.address import join_address
        from chisurf.core.plugin.workspace_input import register_result

        from ..api.io import run_name

        for path, container in output_paths.items():
            try:
                register_result(
                    join_address(container, run_name(duration_ms / 1000.0)),
                    kind="bursts",
                    result_of=self._sources.get(str(path), ""),
                )
            except Exception:  # noqa: BLE001 - the run is written; the workspace row is a convenience
                logging.getLogger(__name__).exception("registering the windows of %s failed", path)

    def _clear_all(self) -> None:
        """Clear the file list and results."""
        self.job.stop()
        self._file_paths = []
        self._sources = {}
        self._last_result = None
        self._log_lines = []
        self.preview_data = None
        self.app.time_window_gui.preview = None
        self.app.time_window_gui.preview_index = -1
        self.notify(("Cleared"), 4000)
        self.request_frame()

    def _fail(self, status: str, detail: str) -> None:
        """Show a failure on the status line and keep the detail in the log."""
        self.notify(status)
        self._log(detail)

    def _log(self, msg: str) -> None:
        """Append a message to the on-canvas log and the application log."""
        try:
            logging.info(msg)
        except Exception:
            pass
        self._log_lines.append(str(msg))
        self.request_frame()


def _layout_store():
    """The dock arrangement, in the settings folder (the Qt tool kept it in QSettings)."""
    try:
        from chisurf.core.settings import chisurf_settings_path
    except Exception:  # noqa: BLE001 - no settings folder: the layout is not kept
        return None
    return LayoutStore(
        "tttr_time_windows", path=chisurf_settings_path / "tttr_time_windows_layout.json"
    )


class _StandaloneApp(TimeWindowApp):
    def export_settings(self):
        """Return the window length, output folder and queued files as JSON-able preferences."""
        return {
            "selected_files": [str(p) for p in self.tool._file_paths],
            "time_window_ms": self.tool.time_window_ms,
            "output_dir": self.tool.output_dir_text,
        }

    def restore_settings(self, state):
        """Apply preferences saved by :meth:`export_settings`."""
        self.tool.time_window_ms = float(state.get("time_window_ms", 10.0))
        self.tool.output_dir_text = str(state.get("output_dir") or "")
        self.tool.add_paths(state.get("selected_files", []))

    def close(self):
        self.tool.job.close()
        docks = self.time_window_gui.docks
        # Written only when the user rearranged the docks: opening and closing the
        # tool (or a test doing so) leaves the settings folder alone.
        if docks.store is not None and docks.state() != self._layout_at_open:
            docks.save()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.continuous = True
        self._job_window = DialogWindow(
            "TTTR operation", size=(320.0, 110.0), key="tw-job", fit_height=True
        )
        self._file_window = DialogWindow("Output folder", size=(640.0, 460.0), key="tw-file")
        self._job_window.show()
        self._file_window.show()
        docks = self.time_window_gui.docks
        docks.store = _layout_store()
        docks.load()
        self._layout_at_open = docks.state()

    def _render(self):
        self.tool.job.poll()
        if self.tool.process_pending and not self.tool.job.running:
            self.tool._process_all()
        super()._render()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        # Sized windows over the app: `im.begin(name)` without a box covered the
        # whole viewport, so every status message hid the tool.
        if self.tool.job.running:
            self._job_window.begin(frame)
            im.text(tr("Working…"))
            if im.button(tr("Stop"), role="danger"):
                self.tool.job.stop()
                self.tool.notify(
                    "Stopped publication. The current file operation may finish writing output."
                )
            im.set_item_tooltip(
                tr("Discard the pending result. A file write already running may finish.")
            )
            self._job_window.end()
        if self.tool.dialog is not None:
            pressed = self._file_window.begin(frame)
            result = self.tool.dialog.draw()
            self._file_window.end()
            if result:
                callback = self.tool.dialog_callback
                self.tool.dialog = None
                callback(result)
            elif result is False or pressed == "close":
                self.tool.dialog = None


def create_app(client=None):
    return TimeWindowController(client=client).app


def receive_files(app, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``tttr_files``): queue ``payload["files"]`` and preview the first.

    The values are addresses as the workspace hands them -- a TTTR file or a photon stream of a
    container; ``datasets`` names the rows they came from (the windows become their children).
    ``window_ms``, when given, sets the time window. A stream that is missing or not a TTTR stream
    raises (the host says why); the streams already queued stay.
    """
    from chisurf.core.fio.address import container_of
    from chisurf.core.plugin.workspace_input import read_address

    tool = app.tool
    given = payload["files"]
    addresses = [given] if isinstance(given, str) else list(given)
    files = [Path(read_address(str(f))) for f in addresses]
    if not files:
        raise ValueError("no file to open in the Time Window tool")
    for path in files:
        if not container_of(str(path)).is_file():
            raise FileNotFoundError(f"{path} does not exist")
    if payload.get("window_ms") is not None:
        tool.time_window_ms = float(payload["window_ms"])
    uids = [str(u) for u in payload.get("datasets") or []]
    tool.add_paths(files, sources=dict(zip((str(f) for f in files), uids)))
    queued = [str(p) for p in tool._file_paths]
    if str(files[0]) not in queued:
        raise ValueError(f"{files[0].name} is not a TTTR file the Time Window tool reads")
    app.time_window_gui.select_preview(queued.index(str(files[0])))
