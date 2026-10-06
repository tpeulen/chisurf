"""Native browser loading, cancellation and gated/selected table export."""

import copy
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np

from chisurf.core.fio.fluorescence import burst_tree


class BurstBrowserController:
    def __init__(self, model):
        self.model = model
        self.running = False
        self.status = ""
        self._cancel = Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-browser")
        self._future = None
        self.dialog = None
        self.action = "file"
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.datasets = DatasetPicker(
            kinds=["analysis_result", "raw_data", "burst_data"], on_paths=self.on_paths_dropped
        )

    def check_cancel(self):
        if self._cancel.is_set():
            raise CancelledError()

    def load(self, path):
        if self.running:
            return
        path = Path(path)
        # A burst run inside a .pto container is not a file on disk, but the model opens it.
        if not path.exists() and not burst_tree.is_container_path(path):
            self.status = f"Input does not exist: {path}"
            return
        self._cancel.clear()
        snapshot = copy.copy(self.model)
        snapshot._observers = []
        snapshot.table, snapshot.mask, snapshot.selected_indices = None, None, []
        self.running = True
        self.status = f"Loading bursts: {path.name} …"
        self._future = self._executor.submit(self._load, snapshot, path)

    def _load(self, snapshot, path):
        self.check_cancel()
        if path.suffix.lower() == ".bur":
            snapshot.load_bur(path)
        else:
            snapshot.load_folder(path, cancel_check=self.check_cancel)
        self.check_cancel()
        if snapshot.table is None:
            raise ValueError(f"No readable bursts found in {path}")
        return snapshot

    def poll(self):
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            snapshot = future.result()
            self.check_cancel()
            observers = self.model._observers
            self.model.__dict__.update(snapshot.__dict__)
            self.model._observers = observers
            self.model.notify("data")
            # The gates pane shows the live count; a copy here went stale at the first gate change.
            self.status = ""
        except CancelledError:
            self.status = "Loading cancelled; previous data retained."
        except Exception as exc:
            self.status = f"Error: {exc}"
        finally:
            self.running = False

    def on_paths_dropped(self, paths):
        if paths:
            self.load(paths[0])

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = "Stopping burst read …"

    def clear(self):
        self.stop()
        observers = self.model._observers
        self.model.__dict__.update(type(self.model)().__dict__)
        self.model._observers = observers
        self.model.notify("data")
        self.status = "Data cleared."

    def export(self, path, selected=False):
        from chisurf.core.datastore import take_rows
        from chisurf.core.fio.fluorescence.burst import write_csv_table

        if self.model.table is None:
            raise ValueError("Load bursts before exporting.")
        rows = (
            np.asarray(self.model.selected_indices, dtype=int)
            if selected
            else self.model.masked_row_indices()
        )
        rows = np.intersect1d(rows, self.model.masked_row_indices())
        write_csv_table(Path(path), take_rows(self.model.table, rows))
        self.status = f"Exported {len(rows)} bursts: {path}"

    #: Per action: the dialog's title, mode and file filters (open ones as the Qt widget's).
    DIALOGS = {
        "folder": ("Select folder with .bur files", "folder", None),
        "file": ("Select burst file", "open", [("Burst Files", ["*.bur", "*.pto"]), ("All Files", ["*"])]),
        "export_gate": ("Export gated bursts", "save", [("CSV", ["*.csv"])]),
        "export_selected": ("Export selected bursts", "save", [("CSV", ["*.csv"])]),
    }

    def browse(self, action="file"):
        """Open the file dialog for *action* (folder, file, export_gate, export_selected)."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode, filters = self.DIALOGS[action]
        self.action = action
        options = {"filters": filters} if filters else {}
        self.dialog = FileDialog(title, mode=mode, filename="bursts.csv" if mode == "save" else None, **options)
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-browser-file")
        self._dialog_window.show()

    #: The tour/remember key of each control button (the guide points at them).
    CONTROL_KEYS = {"Export gated bursts": "export_gated", "Export selected bursts": "export_selected",
                    "MMFDB datasets": "mmfdb", "Clear data": "clear", "Stop loading": "stop"}

    def draw_controls(self, remember=None, track=None):
        """The controller's buttons and status; *remember*/*track* record rects and use for the tour."""
        from emtk import im

        for label, callback, tip in (
            (
                "MMFDB datasets",
                self.datasets.open,
                "Load a burst analysis dataset from the database.",
            ),
            (
                "Export gated bursts",
                lambda: self.browse("export_gate"),
                "Save every burst passing the current gates as CSV.",
            ),
            (
                "Export selected bursts",
                lambda: self.browse("export_selected"),
                "Save selected table rows that also pass the current gates.",
            ),
            ("Clear data", self.clear, "Remove the current table, histogram and row selection."),
            (
                "Stop loading",
                self.stop,
                "Cancel between input files and retain the previous table.",
            ),
        ):
            key = self.CONTROL_KEYS.get(label, label)
            if im.button(label):
                if track is not None:
                    track(key)
                callback()
            im.set_item_tooltip(tip)
            if remember is not None:
                remember(key)
        if self.status:
            im.text_wrapped(self.status)

    def draw_dialogs(self, frame):
        """The file dialog in a sized window over *frame*, and the MMFDB picker."""
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                try:
                    if self.action.startswith("export"):
                        self.export(result[0], selected=self.action == "export_selected")
                    else:
                        self.load(result[0])
                except Exception as exc:
                    self.status = f"Error: {exc}"
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        self.datasets.render(frame)

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
