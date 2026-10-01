"""Toolkit-free BVA execution; rendering owns polling on the UI thread.

The same run as the Qt tool's (``gui/tool.py``): an explicit Run or Restart forgets
an earlier Stop and writes the ``bv4`` companions; an auto-update after a parameter
change recomputes without writing; the burst table read once is reused until the
folder or file type changes; an unchanged run is kept and points at Restart.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk.dialog_window import DialogWindow

from chisurf.core.runtime import analysis_cache

from ..core import computation as core

logger = logging.getLogger(__name__)


class BvaController:
    """Run, stop, browse and save for :class:`~.view_model.BvaViewModel` without a toolkit."""

    def __init__(self, model, settings_path=None):
        self.model = model
        if settings_path is None:
            from chisurf.core.settings import get_path

            settings_path = Path(get_path("settings")) / "plugin_burst_bva_settings.ini"
        self.settings_path = Path(settings_path)
        self._restore_settings()
        self._dialog_kind = "folder"
        self._dialog_window = DialogWindow("Select Data Folder", size=(640.0, 460.0), key="bva-file")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bva")
        self._future = None
        self._fingerprint = None
        self._cache = analysis_cache.ResultCache()
        self._cancel = Event()
        self.dialog = None
        #: A PNG path the app writes on its next frame (a picture of the window).
        self.pending_export = None
        self._pending = False
        model.add_observer(self._changed)

    def _changed(self, event):
        """The Qt tool's auto update: recompute on a parameter change, without writing."""
        if event in ("param", "channel", "folder", "file_type") and self.model.auto_update:
            if self.model.is_running:
                self._pending = True
            else:
                self.run(write_output=False, explicit=False)

    @property
    def running(self):
        """True while a computation is queued or running."""
        return self._future is not None

    # -- runs ---------------------------------------------------------------- #
    def run(self, force=False, write_output=True, explicit=True):
        """Compute BVA; *write_output* writes the bv4 companions, *explicit* forgets a Stop."""
        if self.model.is_running:
            return
        if explicit:
            self._cache.allow()
        folder = self.model.analysis_folder
        if folder is None or not Path(folder).exists():
            self.model.status_text = "Select a data folder first."
            return
        folder = Path(folder)
        settings = self.model.bva_settings()
        self._fingerprint = self.model.analysis_fingerprint(settings)
        outputs_current = analysis_cache.is_current(folder / "bv4" / "bva.stamp.json", self._fingerprint)
        if (
            not force
            and self.model.df is not None
            and self._cache.matches(self._fingerprint)
            and (not write_output or outputs_current)
        ):
            self.model.status_text = "Unchanged — kept the previous BVA result (Restart recomputes it)"
            self.model.restart_attention = True
            return
        self.model.restart_attention = False
        self._cancel.clear()
        self.model.is_running = True
        self.model.status_text = "Reading burst data …" if self.model.burst_df is None else "Computing BVA …"
        self._future = self._executor.submit(
            self._compute,
            folder,
            settings,
            bool(write_output),
            self._fingerprint,
            self.model.input_files(),
            self.model.fingerprint_params(settings),
            self.model.burst_df,
            self.model.tttrs,
        )

    def restart(self):
        """Recompute and write even when nothing changed."""
        self.run(force=True)

    def set_value(self, value):
        """Progress from the computation; raises when Stop was pressed."""
        if self._cancel.is_set():
            raise InterruptedError("BVA cancelled")

    def _compute(self, folder, settings, write_output, fingerprint, inputs, params, burst_df, tttrs):
        saved_settings = dict(settings)
        file_type = settings.pop("file_type")
        if burst_df is None or tttrs is None:  # read once; reused until the folder or file type changes
            burst_df, tttrs = core.read_burst_analysis(folder, file_type, pattern="bi4_bur")
        self.set_value(0)
        result = core.compute_bva(burst_df, tttrs, **settings, progress_window=self)
        self.set_value(0)
        note = ""
        if write_output:
            output = folder / "bv4"
            try:
                core.write_bv4_analysis(result, str(folder), progress_window=self)
            except InterruptedError:
                raise
            except Exception as exc:  # the result stands, as in the Qt tool
                logger.error("BV4 write failed: %s", exc)
                note = f" (could not write the bv4 companions: {exc})"
            output.mkdir(parents=True, exist_ok=True)
            (output / "bva_settings.json").write_text(json.dumps(saved_settings, indent=4))
            analysis_cache.write_stamp(
                output / "bva.stamp.json",
                fingerprint,
                params=params,
                inputs=inputs,
                outputs=sorted(output.glob("*.bv4")),
                tool="bva",
            )
        return burst_df, tttrs, result, note

    def stop(self):
        """Cancel the running computation; it will not start by itself again."""
        if self._future is not None:
            self._cancel.set()
            self._cache.abandon(self._fingerprint)
            self.model.status_text = "Stopping the BVA analysis …"

    def poll(self):
        """Deliver a finished computation to the model (call once a frame)."""
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            burst_df, tttrs, result, note = future.result()
            self.set_value(0)
            self.model.set_result(burst_df, tttrs, result)
            self.model.status_text += note
            self._cache.remember(self._fingerprint)
        except InterruptedError:
            self.model.status_text = "BVA cancelled."
        except Exception as exc:
            self._cache.invalidate()
            self.model.status_text = f"BVA failed: {exc}"
        finally:
            self.model.is_running = False
            self.model.notify("finished")
            if self._pending:
                self._pending = False
                self.run(write_output=False, explicit=False)

    def clear(self):
        """Clear the plot (the Qt tool's Clear)."""
        self.stop()
        self._pending = False
        self._cache.invalidate()
        self.model.df = None
        self.model.status_text = "Plot cleared"

    # -- settings ------------------------------------------------------------ #
    def _restore_settings(self):
        import configparser

        config = configparser.ConfigParser()
        config.read(self.settings_path)
        values = config["General"] if config.has_section("General") else {}
        for name in ("window_length", "photons_per_slice", "bins_x", "bins_y"):
            if name in values:
                try:
                    value = type(getattr(self.model, name))(values[name])
                    if value > 0:
                        setattr(self.model, name, value)
                except ValueError:
                    pass
        if values.get("last_folder"):
            self.model.data_folder = self.model.analysis_folder = Path(values["last_folder"])

    def save_settings(self):
        """Save the current settings as the defaults (the Qt tool's INI, same keys)."""
        import configparser

        config = configparser.ConfigParser()
        config["General"] = {
            name: str(getattr(self.model, name))
            for name in ("window_length", "photons_per_slice", "bins_x", "bins_y")
        }
        if self.model.analysis_folder:
            config["General"]["last_folder"] = str(self.model.analysis_folder)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w") as stream:
            config.write(stream)
        self.model.status_text = "Settings saved"

    # -- save plot ----------------------------------------------------------- #
    def write_window_png(self, app, path, size):
        """Write a picture of the window to *path* (the Qt tool saved a grab of its host)."""
        from emtk.export import save_png

        try:
            save_png(app, path, size=size)
            self.model.status_text = f"Plot saved: {path}"
        except Exception as exc:
            self.model.status_text = f"Could not save the plot: {exc}"

    def save_plot(self):
        """Ask where to save the picture of the window."""
        self._open("save")

    # -- folder -------------------------------------------------------------- #
    def browse(self):
        """Open the folder picker."""
        self._open("folder")

    def _open(self, kind):
        from emtk.file_dialog import FileDialog

        self._dialog_kind = kind
        if kind == "save":
            self.dialog = FileDialog("Save Plot", mode="save", filename="bva_plot.png", filters=[("PNG", ["*.png"])])
            title = "Save Plot"
        else:
            self.dialog = FileDialog("Select Data Folder", mode="folder",
                                     directory=str(self.model.analysis_folder or "") or None)
            title = "Select Data Folder"
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="bva-file")
        self._dialog_window.show()

    def draw_dialog(self, frame):
        """The file dialog in a sized window over *frame*."""
        if self.dialog is None:
            return
        pressed = self._dialog_window.begin(frame)
        result = self.dialog.draw()
        self._dialog_window.end()
        if result:
            self.dialog = None
            if self._dialog_kind == "save":
                self.pending_export = result[0]
            else:
                self.set_folder(result[0])
        elif result is False or pressed == "close":
            self.dialog = None

    def set_folder(self, path):
        """Take a burst folder or container as the input (auto update recomputes, as in Qt)."""
        from chisurf.core.fio.fluorescence import burst_tree

        p = Path(path)
        if p.is_dir() or burst_tree.is_container_path(p):
            self.model.set_folder(p)
            self.model.status_text = f"Data folder: {p}"
            return True
        return False

    def on_paths_dropped(self, paths):
        """Adopt the first dropped burst folder or container; report anything else."""
        for path in paths:
            if self.set_folder(path):
                return
        if paths:
            self.model.status_text = f"BVA reads a burst-analysis folder; {Path(paths[0]).name} is not one."

    def close(self):
        """Stop and release the worker."""
        self.stop()
        self.model.remove_observer(self._changed)
        self._executor.shutdown(wait=False, cancel_futures=True)
