"""FRET-2CDE / ALEX-2CDE GUI tool, powered by emtk.

A compact panel to compute the 2CDE burst-dynamics feature over a burstwise
analysis folder and plot it against the per-burst FRET efficiency. The heavy
lifting is in :mod:`chisurf.plugins.burst.burst_2cde.core.computation`; this is
an immediate-mode EMTK interface hosted in Qt via :class:`emtk.qt_host.ControlHost`,
embeddable in the ``burst_analysis`` workflow shell.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets

from chisurf.core.runtime import analysis_cache
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tool_buttons import TOOLBAR_STYLE, action_button, flag_attention
from chisurf.gui.widgets.tools import ChisurfDockTool
from chisurf.plugins.burst.burst_2cde.core import computation as core

from .app import WINDOW_BG, BurstTwoCdeApp
from .view_model import ALGORITHM_VERSION, TwoCdeViewModel

logger = logging.getLogger(__name__)


class _TextShim:
    """Compatibility shim for text fields."""

    def __init__(self, getter, setter) -> None:
        self._getter = getter
        self._setter = setter

    def text(self) -> str:
        return str(self._getter())

    def setText(self, val: str) -> None:
        self._setter(str(val))


class _ComboShim:
    """Compatibility shim for combo boxes."""

    def __init__(self, getter, setter) -> None:
        self._getter = getter
        self._setter = setter

    def currentText(self) -> str:
        return str(self._getter())

    def setCurrentText(self, val: str) -> None:
        self._setter(str(val))


class _SpinShim:
    """Compatibility shim for spin boxes."""

    def __init__(self, getter, setter) -> None:
        self._getter = getter
        self._setter = setter

    def value(self) -> float:
        return float(self._getter())

    def setValue(self, val: float) -> None:
        self._setter(float(val))


class _BoxShim:
    """Compatibility shim for setting box enabled state."""

    def __init__(self, getter, setter) -> None:
        self._getter = getter
        self._setter = setter

    def isEnabled(self) -> bool:
        return bool(self._getter())

    def setEnabled(self, val: bool) -> None:
        self._setter(bool(val))


class _PlotShim:
    """Compatibility shim for chiplot.Plot."""

    def clear(self) -> None:
        pass

    def scatter(self, *args, **kwargs) -> None:
        pass

    def line(self, *args, **kwargs) -> None:
        pass

    def set_labels(self, *args, **kwargs) -> None:
        pass


class BurstTwoCdeTool(ChisurfDockTool):
    """Compute and plot FRET-2CDE / ALEX-2CDE for a burstwise analysis folder."""

    name = "Spectroscopy:Single-Molecule:2CDE"
    tool_settings_name = "BurstTwoCdeTool"

    class Information(ChisurfDockTool.Information):
        """Context worth stating about a drop that changed nothing."""

        not_a_folder = Msg("2CDE reads a burst-analysis folder; {} is not one.")

    def __init__(self, parent=None, embedded: bool = False, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("FRET-2CDE / ALEX-2CDE")
        self._embedded = embedded

        self.model = TwoCdeViewModel()
        self.app = BurstTwoCdeApp(
            model=self.model,
            on_run=self._on_run_clicked,
            on_restart=self._on_restart_clicked,
            on_stop=self.stop,
            on_browse=self._browse,
            on_guide=self._start_guide,
            on_help=self._show_help,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)

        # Result caching and task management
        self._result_cache = analysis_cache.ResultCache()
        self._running_fingerprint: str | None = None
        self._task = None

        # Action toolbar
        toolbar = QtWidgets.QToolBar(self)
        toolbar.setStyleSheet(TOOLBAR_STYLE)
        self._run = action_button("run", tooltip="Compute 2CDE over all loaded data")
        self._run.clicked.connect(self._on_run_clicked)
        self._restart = action_button(
            "restart", tooltip="Recompute 2CDE from scratch, even if nothing changed"
        )
        self._restart.clicked.connect(self._on_restart_clicked)
        self._stop = action_button("stop", tooltip="Stop the running 2CDE computation")
        self._stop.setEnabled(False)
        self._stop.clicked.connect(self.stop)
        browse = action_button("folder", tooltip="Choose the burst analysis folder")
        browse.clicked.connect(self._browse)

        toolbar.addWidget(self._run)
        toolbar.addWidget(self._restart)
        toolbar.addWidget(self._stop)
        guide_btn = self.add_toolbar_guide(toolbar, resource="guide.json", model=self.model)
        if guide_btn is not None:
            try:
                guide_btn.clicked.disconnect()
            except Exception:
                pass
            guide_btn.clicked.connect(self._start_guide)

        help_btn = self.add_toolbar_help(toolbar, resource="help.md", title="2CDE — help")
        if help_btn is not None and getattr(help_btn, "button", None) is not None:
            try:
                help_btn.button.clicked.disconnect()
            except Exception:
                pass
        self.toolbar = toolbar
        self.toolbar.setVisible(False)
        self.toolbar.hide()

        # Compatibility shims for tests and legacy callers
        self._folder_edit = _TextShim(lambda: self.model.folder, self._set_folder_from_edit)
        self._variant = _ComboShim(
            lambda: self.model.variant, lambda v: setattr(self.model, "variant", str(v))
        )
        self._kernel = _ComboShim(
            lambda: self.model.kernel, lambda k: setattr(self.model, "kernel", str(k))
        )
        self._tau = _SpinShim(
            lambda: self.model.tau_us, lambda t: setattr(self.model, "tau_us", float(t))
        )
        self._donor = _TextShim(
            lambda: self.model.donor_channels_text,
            lambda d: setattr(self.model, "donor_channels_text", str(d)),
        )
        self._acceptor = _TextShim(
            lambda: self.model.acceptor_channels_text,
            lambda a: setattr(self.model, "acceptor_channels_text", str(a)),
        )
        self._file_type = _TextShim(
            lambda: self.model.file_type,
            lambda f: setattr(self.model, "file_type", str(f)),
        )
        self._settings_box = _BoxShim(
            lambda: not self.model.is_locked,
            lambda enabled: setattr(self.model, "is_locked", not bool(enabled)),
        )
        self._status = _TextShim(
            lambda: self.model.status_text,
            lambda s: self._set_status(str(s)),
        )
        self._plot = _PlotShim()

        self.model.add_observer(self._on_model_event)

    @property
    def _df(self):
        return self.model.df

    @_df.setter
    def _df(self, val):
        self.model.df = val

    def _set_folder_from_edit(self, text: str) -> None:
        self.model.set_folder(text)
        self.host.update()

    def _on_model_event(self, event: str) -> None:
        self.host.update()

    def _start_guide(self) -> None:
        if hasattr(self, "app") and hasattr(self.app, "start_guide"):
            self.app.start_guide()
            return
        if getattr(self, "_guide_button", None) is not None:
            self._guide_button.click()

    def _show_help(self) -> None:
        if hasattr(self, "app") and hasattr(self.app, "show_help"):
            self.app.show_help()
            return
        if getattr(self, "_help_button", None) is not None:
            self._help_button.show_help()

    def tour_target(self, target: dict[str, Any]) -> tuple[QtWidgets.QWidget, tuple | None] | None:
        """Tell GuidedTour where a step target is on this emtk surface."""
        name = target.get("name") or target.get("key") or target.get("attr")
        if name:
            rect = self.app.two_cde_gui.item_rects.get(str(name))
            if rect is not None:
                return self.host, rect
        return None

    def _set_status(self, msg: str) -> None:
        """Update status and report via normal logging."""
        self.model.status_text = msg
        logging.getLogger(__name__).info(msg)
        self.host.update()

    def _browse(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select burstwise folder")
        if d:
            self._adopt_folder(pathlib.Path(d))

    def _adopt_folder(self, folder: pathlib.Path) -> None:
        """Take folder as the analysis folder and compute its 2CDE."""
        self.model.set_folder(folder)
        self.Information.not_a_folder.clear()
        self.host.update()
        self._on_run_clicked()

    def on_paths_dropped(self, paths: list[pathlib.Path]) -> None:
        """Adopt the first dropped directory; report anything else."""
        for path in paths:
            if path.is_dir():
                self._adopt_folder(path)
                return
        if paths:
            self.Information.not_a_folder(paths[0].name)

    def set_folder(self, folder) -> None:
        """Set the analysis folder (used by the workflow context)."""
        self.model.set_folder(folder)
        self.host.update()

    def input_files(self) -> list[pathlib.Path]:
        return self.model.input_files()

    def settings(self) -> dict:
        return self.model.settings()

    def fingerprint_params(self) -> dict:
        return self.model.fingerprint_params()

    def analysis_fingerprint(self) -> str:
        return self.model.analysis_fingerprint()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._auto_run)

    def _auto_run(self) -> None:
        folder = self.model.folder.strip()
        if not folder or not pathlib.Path(folder).is_dir() or self._is_running():
            return
        if self._result_cache.was_abandoned(self.analysis_fingerprint()):
            self._set_status("Stopped earlier — press Run to compute 2CDE")
            return
        self.run()

    def _on_run_clicked(self) -> None:
        self._result_cache.allow()
        self.run()

    def _on_restart_clicked(self) -> None:
        self._result_cache.allow()
        self.run(force=True)

    def run(self, *, force: bool = False) -> None:
        folder = self.model.folder.strip()
        if not folder or not pathlib.Path(folder).is_dir():
            self._set_status("Select a valid burstwise analysis folder.")
            return
        fingerprint = self.analysis_fingerprint()
        stamp = pathlib.Path(folder) / "2c4" / "2cde.stamp.json"
        if (
            not force
            and self.model.df is not None
            and self._result_cache.matches(fingerprint)
            and analysis_cache.is_current(stamp, fingerprint)
        ):
            self._set_status("Unchanged — kept the previous 2CDE result (🔁 Restart recomputes it)")
            flag_attention(self._restart, True)
            return
        flag_attention(self._restart, False)
        self._running_fingerprint = fingerprint
        self._run.setEnabled(False)
        self._stop.setEnabled(True)
        self.model.is_running = True
        self.model.is_locked = True
        self.host.update()

        self._task = ChiSurfProgress.run(
            self,
            "Reading burst data …",
            self._analysis_worker,
            args=(
                folder,
                self.settings(),
                fingerprint,
                self.input_files(),
                self.fingerprint_params(),
            ),
            maximum=0,
            title="2CDE",
            owner=self._run,
            on_result=self._analysis_done,
            on_error=self._analysis_failed,
            on_done=self._analysis_over,
        )

    def _analysis_over(self) -> None:
        self._task = None
        self._run.setEnabled(True)
        self._stop.setEnabled(False)
        self.model.is_running = False
        self.model.is_locked = False
        self.host.update()

    def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        self._result_cache.abandon(self._running_fingerprint)
        self._set_status("Stopping the 2CDE computation …")

    def _is_running(self) -> bool:
        return self._task is not None and self._task.is_running

    def _analysis_worker(self, folder, settings, fingerprint, inputs, params, task):
        task.set_range(0, 0)
        task.set_text("Reading burst data …")
        df, tttrs = core.read_burst_analysis(
            pathlib.Path(folder), settings["file_type"], pattern="bi4_bur"
        )
        from chisurf.core.datastore import row_count

        task.set_range(0, row_count(df))
        task.set_text("Computing 2CDE …")
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
            progress_window=task.progress_window("Computing 2CDE …"),
        )
        try:
            core.write_2cde_analysis(df, folder, variant=settings["variant"])
            out = pathlib.Path(folder) / "2c4"
            analysis_cache.write_stamp(
                pathlib.Path(folder) / "2c4" / "2cde.stamp.json",
                fingerprint,
                params=params,
                inputs=inputs,
                outputs=sorted(out.glob("*.2c4")),
                tool="2cde",
            )
        except Exception as exc:  # pragma: no cover
            logging.getLogger(__name__).warning("Could not write 2c4 companion: %s", exc)
        return df, settings["variant"]

    def _analysis_done(self, result) -> None:
        df, variant = result
        self.model.set_result(df, variant)
        if self._running_fingerprint is not None:
            self._result_cache.remember(self._running_fingerprint)
        self._set_status(self.model.status_text)
        self.host.update()

    def _analysis_failed(self, exc) -> None:
        self.model.df = None
        self._result_cache.invalidate()
        self._set_status(f"Error: {exc}")
        self.host.update()

    def _draw(self, df, column: str) -> None:
        variant = "alex" if column == core.COLUMN_ALEX_2CDE else "fret"
        self.model.set_result(df, variant)
        self._set_status(self.model.status_text)
        self.host.update()


__all__ = ["BurstTwoCdeTool"]
