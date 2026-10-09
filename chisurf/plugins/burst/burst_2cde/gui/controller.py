"""Toolkit-free asynchronous 2CDE workflow for native and browser hosts.

The same run as the Qt tool's (``gui/tool.py``): result cache and stamp, Stop that
abandons the run so it does not start by itself again, an explicit Run or Restart
that forgets the abandonment, and a run when the tool is first shown.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk.dialog_window import DialogWindow

from chisurf.core.datastore import row_count
from chisurf.core.runtime import analysis_cache

from ..core import computation as core

logger = logging.getLogger(__name__)


class TwoCdeController:
    """Run, stop and browse for :class:`~.view_model.TwoCdeViewModel` without a toolkit."""

    def __init__(self, model):
        self.model = model
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="2cde")
        self._future = None
        self._fingerprint = None
        self._cancel = Event()
        self._cache = analysis_cache.ResultCache()
        self._progress_max = 0
        self.dialog = None
        self._dialog_window = DialogWindow(
            "Select burstwise folder", size=(640.0, 460.0), key="2cde-folder"
        )

    # -- runs ---------------------------------------------------------------- #
    def run(self, force=False, explicit=True):
        """Compute 2CDE for the folder; *explicit* (a press) forgets an earlier Stop."""
        if self.model.is_running:
            return
        if explicit:
            self._cache.allow()
        folder = Path(self.model.folder).expanduser()
        if not self.model.folder or not folder.is_dir():
            self.model.status_text = "Select a valid burstwise analysis folder."
            return
        fingerprint = self.model.analysis_fingerprint()
        stamp = folder / "2c4" / "2cde.stamp.json"
        if (
            not force
            and self.model.df is not None
            and self._cache.matches(fingerprint)
            and analysis_cache.is_current(stamp, fingerprint)
        ):
            self.model.status_text = (
                "Unchanged — kept the previous 2CDE result (Restart recomputes it)"
            )
            self.model.restart_attention = True
            return
        self.model.restart_attention = False
        self._cancel.clear()
        self.model.is_running = self.model.is_locked = True
        self.model.status_text = ""
        self._set_progress("Reading burst data …", None)
        self._fingerprint = fingerprint
        self._future = self._executor.submit(
            self._compute,
            folder,
            dict(self.model.settings()),
            fingerprint,
            self.model.input_files(),
            self.model.fingerprint_params(),
        )

    def restart(self):
        """Recompute even when nothing changed."""
        self.run(force=True)

    def auto_run(self):
        """What the Qt tool does when it is shown: run, unless this exact run was stopped."""
        folder = self.model.folder.strip()
        if not folder or not Path(folder).expanduser().is_dir() or self.model.is_running:
            return
        if self._cache.was_abandoned(self.model.analysis_fingerprint()):
            self.model.status_text = "Stopped earlier — press Run to compute 2CDE"
            return
        self.run(explicit=False)

    @property
    def running(self):
        """True while a computation is queued or running."""
        return self._future is not None

    # -- the worker (progress_window protocol of compute_2cde) --------------- #
    def _set_progress(self, text, fraction):
        self.model.progress_text = text
        self.model.progress = fraction

    def set_value(self, value):
        """Progress from the computation; raises when Stop was pressed."""
        if self._cancel.is_set():
            raise InterruptedError("2CDE cancelled")
        if self._progress_max:
            self.model.progress = min(1.0, float(value) / self._progress_max)

    def _compute(self, folder, settings, fingerprint, inputs, params):
        df, tttrs = core.read_burst_analysis(folder, settings["file_type"], pattern="bi4_bur")
        self._progress_max = row_count(df)
        self._set_progress("Computing 2CDE …", 0.0)
        self.set_value(0)
        df = core.compute_2cde(
            df,
            tttrs,
            donor_channels=settings["donor_channels"],
            acceptor_channels=settings["acceptor_channels"],
            donor_micro_time_ranges=[],
            acceptor_micro_time_ranges=[],
            tau=settings["tau_us"] * 1e-6,
            kernel=settings["kernel"],
            variant=settings["variant"],
            progress_window=self,
        )
        self.set_value(0)
        self._progress_max = 0
        self._set_progress("Writing the 2c4 companion …", None)
        note = ""
        try:
            core.write_2cde_analysis(df, str(folder), variant=settings["variant"])
            analysis_cache.write_stamp(
                folder / "2c4" / "2cde.stamp.json",
                fingerprint,
                params=params,
                inputs=inputs,
                outputs=sorted((folder / "2c4").glob("*.2c4")),
                tool="2cde",
            )
        except (
            Exception
        ) as exc:  # the result stands, as in the Qt tool; say why nothing was written
            logger.warning("Could not write 2c4 companion: %s", exc)
            note = f" (could not write the 2c4 companion: {exc})"
        return df, settings["variant"], note

    def stop(self):
        """Cancel the running computation; it will not start by itself again."""
        if self._future is not None:
            self._cancel.set()
            self._cache.abandon(self._fingerprint)
            self.model.status_text = "Stopping the 2CDE computation …"

    def poll(self):
        """Deliver a finished computation to the model (call once a frame)."""
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            result, variant, note = future.result()
            if self._cancel.is_set():
                raise InterruptedError("2CDE cancelled")
            self.model.set_result(result, variant)
            self.model.status_text += note
            self._cache.remember(self._fingerprint)
        except InterruptedError:
            self.model.status_text = "2CDE cancelled."
        except Exception as exc:
            self.model.df = None
            self._cache.invalidate()
            self.model.status_text = f"Error: {exc}"
        finally:
            self.model.is_running = self.model.is_locked = False
            self._set_progress("", None)
            self.model.notify("finished")

    # -- folder -------------------------------------------------------------- #
    def browse(self):
        """Open the folder picker."""
        from emtk.file_dialog import FileDialog

        self.dialog = FileDialog(
            "Select burstwise folder", mode="folder", directory=self.model.folder or None
        )
        self._dialog_window.show()

    def draw_dialog(self, frame):
        """Draw the folder picker in a sized window over *frame*; a pick runs."""
        if self.dialog is None:
            return
        pressed = self._dialog_window.begin(frame)
        result = self.dialog.draw()
        self._dialog_window.end()
        if result:
            self.dialog = None
            self.adopt_folder(result[0])
        elif result is False or pressed == "close":
            self.dialog = None

    def adopt_folder(self, folder):
        """Take *folder* as the analysis folder and compute its 2CDE."""
        self.model.set_folder(folder)
        self.run()

    def on_paths_dropped(self, paths):
        """Adopt the first dropped directory; report anything else."""
        for path in map(Path, paths):
            if path.is_dir():
                self.adopt_folder(path)
                return
        if paths:
            self.model.status_text = (
                f"2CDE reads a burst-analysis folder; {Path(paths[0]).name} is not one."
            )

    def close(self):
        """Stop and release the worker."""
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
