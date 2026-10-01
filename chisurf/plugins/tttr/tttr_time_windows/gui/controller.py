"""Pure EMTK time-window controller using the existing scientific backend."""

import logging
from pathlib import Path

from emtk import im
from emtk.file_dialog import FileDialog
from emtk.dialog_window import DialogWindow
from emtk.docking import LayoutStore

from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from ..api.models import TimeWindowResult
from .app import TimeWindowApp
from .client import TimeWindowClient


def _is_supported_path(path):
    return (
        str(path)
        .lower()
        .endswith(
            tuple(
                ext + suffix
                for ext in (".ptu", ".phu", ".ht2", ".ht3", ".pt3", ".t3r")
                for suffix in ("", ".gz", ".bz2")
            )
        )
    )


class TimeWindowController:
    def __init__(self, client=None, database_picker=None):
        self._client = client or TimeWindowClient()
        self.database_picker = database_picker
        self.dataset_picker = None
        self._file_paths = []
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
            on_add_files=self._add_files_dialog,
        )

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

    def choose(self, title, callback, mode="open", multiple=False):
        self.dialog = FileDialog(
            title,
            mode=mode,
            multiselect=multiple,
            filters="TTTR (*.ptu *.phu *.ht2 *.ht3 *.pt3 *.t3r *.ptu.gz *.ptu.bz2);;All files (*)",
        )
        self.dialog_callback = callback

    def _add_files_dialog(self):
        self.choose("Add TTTR files", self.add_paths, multiple=True)

    def _add_folder_dialog(self):
        self.choose(
            "Add TTTR folder",
            lambda paths: self.add_paths(
                sorted(p for p in Path(paths[0]).rglob("*") if p.is_file())
            ),
            mode="folder",
        )

    def _choose_dir(self):
        self.choose(
            "Output folder",
            lambda paths: setattr(self, "output_dir_text", str(paths[0])),
            mode="folder",
        )

    def _add_from_database(self):
        if self.database_picker is not None:
            self.add_paths(self.database_picker() or [])
            return
        from chisurf.emtk.dataset_picker import DatasetPicker

        if self.dataset_picker is None:
            self.dataset_picker = DatasetPicker(on_paths=self.add_paths)
        self.dataset_picker.open()

    def add_paths(self, paths) -> None:
        """Queue files, keeping only supported TTTR extensions, in order."""
        known = {str(p) for p in self._file_paths}
        for path in paths:
            p = Path(path)
            if not _is_supported_path(str(p)) or str(p) in known:
                continue
            self._file_paths.append(p)
            known.add(str(p))
        if self._file_paths and self.app.time_window_gui.preview_index < 0:
            self.app.time_window_gui.select_preview(0)
        self.request_frame()

    def drop_paths(self, paths) -> bool:
        """Queue the TTTR files among *paths*; a dropped folder is searched recursively.

        Returns whether the queue grew. Nothing supported in the drop says so on the status line.
        """
        found = []
        for path in paths or []:
            p = Path(path)
            found.extend(sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else [p])
        before = len(self._file_paths)
        self.add_paths(found)
        grew = len(self._file_paths) > before
        if not grew and not any(_is_supported_path(str(p)) for p in found):
            self.notify("Nothing to queue: drop TTTR files (.ptu, .ht3, .phu, ...) or a folder of them.")
        return grew

    def _remove_preview_file(self) -> None:
        if self.job.running:
            self.notify("Stop the current operation before removing files.")
            return
        gui = self.app.time_window_gui
        index = gui.preview_index
        if not 0 <= index < len(self._file_paths):
            return
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
            self.notify("Processing complete")

        self.job.start(
            lambda: self._client.analyze_files(files, time_window_ms=duration, output_dir=output),
            publish,
            lambda exc: self._fail("Processing failed", f"Processing failed: {exc}"),
        )

    def _clear_all(self) -> None:
        self.job.stop()
        """Clear the file list and results."""
        self._file_paths = []
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
    return LayoutStore("tttr_time_windows", path=chisurf_settings_path / "tttr_time_windows_layout.json")


class _StandaloneApp(TimeWindowApp):
    def close(self):
        self.tool.job.close()
        if self.tool.dataset_picker is not None:
            self.tool.dataset_picker.close()
        docks = self.time_window_gui.docks
        # Written only when the user rearranged the docks: opening and closing the
        # tool (or a test doing so) leaves the settings folder alone.
        if docks.store is not None and docks.state() != self._layout_at_open:
            docks.save()

    def files_dropped(self, paths):
        """Host hook (native, web and Qt hosts): queue the dropped files and folders."""
        return self.tool.drop_paths([str(p) for p in paths or []])

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.continuous = True
        self._job_window = DialogWindow("TTTR operation", size=(320.0, 110.0), key="tw-job",
                                        fit_height=True)
        self._file_window = DialogWindow("Choose files or folder", size=(640.0, 460.0),
                                         key="tw-file")
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
        if self.tool.dataset_picker is not None:
            vp = im.get_main_viewport()
            self.tool.dataset_picker.render((0.0, 0.0, *vp.size))
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        # Sized windows over the app: `im.begin(name)` without a box covered the
        # whole viewport, so every status message hid the tool.
        if self.tool.job.running:
            self._job_window.begin(frame)
            im.text("Working…")
            if im.button("Stop"):
                self.tool.job.stop()
                self.tool.notify(
                    "Stopped publication. The current file operation may finish writing output."
                )
            im.set_item_tooltip(
                "Discard the pending result. A file write already running may finish."
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


def create_app(client=None, database_picker=None):
    return TimeWindowController(client=client, database_picker=database_picker).app
