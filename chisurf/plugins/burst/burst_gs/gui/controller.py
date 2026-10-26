"""Native asynchronous kinetics fitting and measurement/export actions.

The same run as the Qt tool's (``gui/tool.py``): the fit off the UI thread with its
progress, the Qt status line after a fit ("logL = …, k(1→2) = … /s, …"), and an
export that needs a fit and suggests ``<first table>.gs.csv``.
"""

import copy
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk.i18n import tr


class BurstGsController:
    def __init__(self, model):
        self.model = model
        self.running = False
        self.status = ""
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-gs")
        self._future = None
        self._cancel = Event()
        self.dialog = None
        self.action = "export"
        #: While fitting: what the optimiser reports, and the done fraction.
        self.progress_text = ""
        self.progress_fraction = 0.0

    def set_run(self, address):
        """Take the burst run *address* (a run of a measurement container, from the workspace)."""
        from chisurf.plugins.burst.workspace_io import is_burst_source

        if not is_burst_source(address):
            return False
        self.model.bur_files = [str(address)]
        self.model._bursts = self.model._analysis = None
        self.model.notify("files")
        return True

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
        return (
            f"logL = {fit.log_likelihood:,.1f}, "
            f"k(1→2) = {matrix[1, 0]:,.0f} /s, k(2→1) = {matrix[0, 1]:,.0f} /s"
        )

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = "Stopping kinetics fit …"

    def export(self, path):
        """Write the fitted parameters as CSV."""
        self.model.export_csv(str(path))
        self.status = f"Wrote {path}"

    #: Per action: the dialog's title, mode and file filters (the input comes from the workspace).
    DIALOGS = {
        "export": ("Export photon-by-photon kinetics", "save", [("CSV", ["*.csv"])]),
    }

    def browse(self, action="export"):
        """Open the save dialog for the export (the only file this tool asks for: an output)."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        if action == "export" and self.model.analysis is None:
            self.status = "Run a fit first."
            return
        title, _mode, filters = self.DIALOGS[action]
        self.action = action
        options = {"filters": filters} if filters else {}
        filename = None
        if self.model.bur_files:  # the Qt tool's suggestion: beside the measurement
            from chisurf.core.fio.address import container_of

            source = container_of(self.model.bur_files[0])
            filename = f"{source.stem}.gs.csv"
            options["directory"] = str(source.parent)
        else:
            filename = "kinetics.gs.csv"
        self.dialog = FileDialog(title, mode="save", filename=filename, **options)
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-gs-file")
        self._dialog_window.show()

    def draw_progress(self):
        """The progress of a running fit and the last status line."""
        from emtk import im

        if self.running:
            im.progress_bar(self.progress_fraction, overlay=self.progress_text)
            im.set_item_tooltip(tr("Progress of the running fit; Stop fit cancels it."))
        if self.status:
            im.text_wrapped(self.status)

    def draw_dialogs(self, frame):
        """The export's save dialog in a sized window over *frame*."""
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                try:
                    self.export(result[0])
                except Exception as exc:
                    self.status = f"Error: {exc}"
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
