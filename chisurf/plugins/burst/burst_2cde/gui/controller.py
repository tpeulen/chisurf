"""Toolkit-free asynchronous 2CDE workflow for native and browser hosts.

The same run as the Qt tool's (``gui/tool.py``): result cache and stamp, Stop that
abandons the run so it does not start by itself again, an explicit Run or Restart
that forgets the abandonment, and a run when the tool is first shown.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from chisurf.core.datastore import row_count
from chisurf.core.runtime import analysis_cache
from chisurf.plugins.burst.workspace_io import is_burst_source

from ..core import computation as core

logger = logging.getLogger(__name__)


class TwoCdeController:
    """Run and stop for :class:`~.view_model.TwoCdeViewModel` without a toolkit."""

    def __init__(self, model):
        self.model = model
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="2cde")
        self._future = None
        self._fingerprint = None
        self._cancel = Event()
        self._cache = analysis_cache.ResultCache()
        self._progress_max = 0

    # -- runs ---------------------------------------------------------------- #
    def run(self, force=False, explicit=True):
        """Compute 2CDE for the folder; *explicit* (a press) forgets an earlier Stop."""
        if self.model.is_running:
            return
        if explicit:
            self._cache.allow()
        folder = Path(self.model.folder).expanduser()
        if not self.model.folder or not is_burst_source(folder):
            self.model.status_text = "Pick a burst run in the Input section first."
            return
        fingerprint = self.model.analysis_fingerprint()
        stamp = analysis_cache.stamp_path(folder, "2cde")
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
        if not folder or not is_burst_source(Path(folder).expanduser()) or self.model.is_running:
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
        self._set_progress("Writing the 2CDE result …", None)
        note = ""
        try:
            written = core.write_2cde_container(
                df,
                settings["variant"],
                parameters=params,
                analysis_folder=folder,
            )
            analysis_cache.write_stamp(
                analysis_cache.stamp_path(folder, "2cde"),
                fingerprint,
                params=params,
                inputs=inputs,
                outputs=[Path(p) for p in written],
                tool="2cde",
            )
        except (
            Exception
        ) as exc:  # the result stands, as in the Qt tool; say why nothing was written
            logger.warning("Could not write the 2CDE result: %s", exc)
            note = f" (could not write the 2CDE result: {exc})"
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

    # -- input ------------------------------------------------------------- #
    def adopt_folder(self, folder):
        """Take the burst run *folder* (an address from the workspace) and compute its 2CDE."""
        if not is_burst_source(folder):
            return False
        self.model.set_folder(folder)
        self.run()
        return True

    def close(self):
        """Stop and release the worker."""
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
