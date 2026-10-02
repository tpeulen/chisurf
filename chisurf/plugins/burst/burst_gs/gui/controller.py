"""Native asynchronous kinetics fitting and measurement/export actions.

The same run as the Qt tool's (``gui/tool.py``): the fit off the UI thread with its
progress, the Qt status line after a fit ("logL = …, k(1→2) = … /s, …"), and an
export that needs a fit and suggests ``<first table>.gs.csv``.
"""

import copy
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event


class BurstGsController:
    def __init__(self, model):
        self.model = model
        self.running = False
        self.status = ""
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-gs")
        self._future = None
        self._cancel = Event()
        self.dialog = None
        self.action = "files"
        #: While fitting: what the optimiser reports, and the done fraction.
        self.progress_text = ""
        self.progress_fraction = 0.0
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.datasets = DatasetPicker(on_paths=self.add_files)

    def add_files(self, paths):
        expanded = []
        for path in map(Path, paths):
            if path.is_dir():
                expanded.extend(path.rglob("*.bur"))
            else:
                expanded.append(path)
        self.model.bur_files = sorted(
            set(self.model.bur_files + [str(p) for p in expanded if p.suffix.lower() == ".bur"])
        )
        self.model.notify("files")

    def on_paths_dropped(self, paths):
        """Add dropped .bur tables, and the tables in dropped folders."""
        before = list(self.model.bur_files)
        self.add_files(paths)
        if paths and self.model.bur_files == before:
            self.status = "No .bur burst table among the dropped paths."

    def progress(self, fraction, message):
        """Progress from the fit (the Qt task's set_fraction); raises when Stop was pressed."""
        if self._cancel.is_set():
            raise CancelledError()
        self.progress_fraction = float(fraction)
        if message:
            self.progress_text = str(message)

    def _compute(self, snapshot):
        ok = snapshot.compute(progress=self.progress)
        self.progress(1, "")
        return snapshot, ok

    def run(self):
        if self.running:
            return
        reason = self.model.can_run()
        if reason:
            self.status = reason
            return
        self._cancel.clear()
        snapshot = copy.copy(self.model)
        snapshot.bur_files = list(self.model.bur_files)
        snapshot._observers = []
        snapshot._write_container = lambda: None
        self.running = True
        self.status = ""
        self.progress_text, self.progress_fraction = "Fitting…", 0.0
        self._future = self._executor.submit(self._compute, snapshot)

    def poll(self):
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            snapshot, ok = future.result()
            self.progress(1, "")
            if ok:
                self.model._bursts, self.model._analysis = snapshot._bursts, snapshot._analysis
                self.model._info = snapshot._info
                self.model.results_text = snapshot.results_text
                self.model._write_container()
                self.model.notify("computed")
                self.status = self._fit_line()
            else:
                self.status = "The fit did not produce a result — see the report."
                self.model.results_text = snapshot.results_text
                self.model.notify("computed")
        except CancelledError:
            self.status = "Kinetics fit cancelled."
        except Exception as exc:
            self.status = f"The fit failed: {exc}"
        finally:
            self.running = False
            self.progress_text = ""

    def _fit_line(self):
        """The Qt tool's status line after a fit."""
        fit = self.model.analysis.fit
        matrix = fit.rate_matrix
        return (f"logL = {fit.log_likelihood:,.1f}, "
                f"k(1→2) = {matrix[1, 0]:,.0f} /s, k(2→1) = {matrix[0, 1]:,.0f} /s")

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = "Stopping kinetics fit …"

    def export(self, path):
        """Write the fitted parameters as CSV."""
        self.model.export_csv(str(path))
        self.status = f"Wrote {path}"

    #: Per action: the dialog's title, mode and file filters.
    DIALOGS = {
        "files": ("Open burst tables", "open", [("BUR", ["*.bur"])]),
        "folder": ("Add burst folder", "folder", None),
        "export": ("Export photon-by-photon kinetics", "save", [("CSV", ["*.csv"])]),
    }

    def browse(self, action="files"):
        """Open the file dialog for *action* (files, folder, export)."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        if action == "export" and self.model.analysis is None:
            self.status = "Run a fit first."
            return
        title, mode, filters = self.DIALOGS[action]
        self.action = action
        options = {"filters": filters} if filters else {}
        filename = None
        if action == "export":  # the Qt tool's suggestion: beside the first table
            filename = Path(self.model.bur_files[0]).with_suffix(".gs.csv").name if self.model.bur_files else "kinetics.gs.csv"
            if self.model.bur_files:
                options["directory"] = str(Path(self.model.bur_files[0]).parent)
        self.dialog = FileDialog(title, mode=mode, multiselect=action == "files", filename=filename, **options)
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-gs-file")
        self._dialog_window.show()

    def draw_inputs(self, remember=None, track=None):
        """The data row (open, add, MMFDB, clear) and the files; *remember*/*track* serve the guide."""
        from emtk import im

        from chisurf.plugins.emtk_layout import button_row

        im.begin_disabled(self.running)
        pressed = button_row([
            {"label": "Open BUR files", "key": "bur_files",
             "tip": "Choose burst tables containing photon ranges to fit."},    # the guide's "files" step
            {"label": "Add burst folder", "tip": "Find BUR tables recursively in an analysis folder."},
            {"label": "MMFDB datasets", "tip": "Select a burst analysis dataset from MMFDB."},
            {"label": "Clear burst files", "tip": "Remove the input tables and previous fitted result."},
        ], remember=remember)
        if pressed == "bur_files":
            if track is not None:
                track("bur_files")
            self.browse()
        elif pressed == "Add burst folder":
            self.browse("folder")
        elif pressed == "MMFDB datasets":
            self.datasets.open()
        elif pressed == "Clear burst files":
            self.model.bur_files = []
            self.model._bursts = self.model._analysis = None
            self.model.notify("files")
        for path in list(self.model.bur_files):
            im.text_wrapped(path)
            if im.button(f"Remove##{path}"):
                self.model.bur_files.remove(path)
            im.set_item_tooltip(f"Remove {Path(path).name} from the fit input.")
        im.end_disabled()

    def draw_progress(self):
        """The progress of a running fit and the last status line."""
        from emtk import im

        if self.running:
            im.progress_bar(self.progress_fraction, overlay=self.progress_text)
            im.set_item_tooltip("Progress of the running fit; Stop fit cancels it.")
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
                    if self.action == "export":
                        self.export(result[0])
                    else:
                        self.add_files(result)
                except Exception as exc:
                    self.status = f"Error: {exc}"
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        self.datasets.render(frame)

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
