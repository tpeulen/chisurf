"""Burst Variance Analysis (BVA) tool, powered by emtk.

A tool to compute and plot the BVA burst-dynamics feature over a burstwise
analysis folder and plot it against the per-burst Mean Proximity Ratio.
Hosts the immediate-mode :class:`~.app.BurstBvaApp` via :class:`emtk.qt_host.ControlHost`,
embeddable in the ``burst_analysis`` workflow shell.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets
from qtpy.QtCore import QSettings

from chisurf.core.datastore import row_count
from chisurf.core.fio.fluorescence.burst_manifest import source_inputs
from chisurf.core.runtime import analysis_cache
from chisurf.gui.misc_helpers import get_plugin_settings_path, persist_plugin_state
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tool_buttons import (
    TOOLBAR_STYLE,
    action_button,
    flag_attention,
)
from chisurf.gui.widgets.tools import ChisurfDockTool
from chisurf.plugins.burst.burst_bva.core import computation as core

from .app import WINDOW_BG, BurstBvaApp
from .view_model import ALGORITHM_VERSION, BvaViewModel

logger = logging.getLogger(__name__)


def _folder_field(placeholder: str) -> QtWidgets.QLineEdit:
    """Read-only line edit showing the selected burst-analysis folder."""
    field = QtWidgets.QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setReadOnly(True)
    field.setAcceptDrops(False)
    field.setStyleSheet("color: #aaa; padding: 0 4px; background: transparent; border: none;")
    return field


class _DetectorPageShim:
    """Compatibility shim for workflow detector definitions."""

    def __init__(self, model: BvaViewModel) -> None:
        self._model = model
        self._settings: dict[str, Any] = {}

    def load_data_into_tables(self, settings: dict) -> None:
        self._settings = dict(settings or {})
        detectors = self._settings.get("detectors", {})
        for name, d in detectors.items():
            chs = d.get("chs", [])
            ranges = d.get("micro_time_ranges", [(0, 32768)])
            if "green" in name.lower() or "donor" in name.lower():
                self._model.donor_channels_text = ",".join(str(c) for c in chs)
                self._model.donor_micro_time_ranges = ranges
            elif "red" in name.lower() or "acceptor" in name.lower():
                self._model.acceptor_channels_text = ",".join(str(c) for c in chs)
                self._model.acceptor_micro_time_ranges = ranges
        tttr_reading = self._settings.get("tttr_reading", {})
        if "file_type" in tttr_reading:
            self._model.file_type = tttr_reading["file_type"]
        self._model.notify("detector_settings")

    def get_settings(self) -> dict[str, Any]:
        return self._settings or {
            "detectors": {
                "Donor": {
                    "chs": self._model.donor_channels,
                    "micro_time_ranges": self._model.donor_micro_time_ranges,
                },
                "Acceptor": {
                    "chs": self._model.acceptor_channels,
                    "micro_time_ranges": self._model.acceptor_micro_time_ranges,
                },
            },
            "tttr_reading": {"file_type": self._model.file_type},
        }


@persist_plugin_state("burst_bva")
class BVATool(ChisurfDockTool):
    """BVA analysis widget powered by emtk."""

    tool_settings_name = "BVATool"

    class Error(ChisurfDockTool.Error):
        """Conditions that stop a BVA run, or that a run ended in."""

        no_folder = Msg("Select a data folder first.")
        bad_settings = Msg("BVA settings: {}")
        failed = Msg("BVA failed: {}")

    class Information(ChisurfDockTool.Information):
        """Context worth stating about a drop that changed nothing."""

        not_a_folder = Msg("BVA reads a burst-analysis folder; {} is not one.")

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("smFRET BVA Analysis")

        self.model = BvaViewModel()
        self.app = BurstBvaApp(
            model=self.model,
            on_run=self._run_analysis,
            on_restart=self._restart_analysis,
            on_stop=self.stop,
            on_browse=self._select_folder,
            on_clear=self._clear_plot,
            on_guide=self._start_guide,
            on_help=self._show_help,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)

        # Caching & background task
        self._result_cache = analysis_cache.ResultCache()
        self._running_fingerprint: str | None = None
        self._task = None

        # Recompute coalescing
        self._recompute_pending = False
        self._suspend_recompute = 0
        self._recompute_timer = QtCore.QTimer(self)
        self._recompute_timer.setSingleShot(True)
        self._recompute_timer.setInterval(0)
        self._recompute_timer.timeout.connect(self._flush_recompute)

        # Auto-update checkbox
        self._auto_update_cb = QtWidgets.QCheckBox("Auto update", self)
        self._auto_update_cb.setChecked(self.model.auto_update)
        self._auto_update_cb.toggled.connect(lambda v: setattr(self.model, "auto_update", bool(v)))
        self._auto_update_cb.hide()

        # Toolbar
        self._setup_toolbar()
        if hasattr(self, "toolbar"):
            self.removeToolBar(self.toolbar)
            self.toolbar.setVisible(False)
            self.toolbar.hide()

        # Detector page shim for workflow context
        self.detector_page = _DetectorPageShim(self.model)

        self.model.add_observer(self._on_model_event)

    @property
    def data_folder(self) -> pathlib.Path | None:
        return self.model.data_folder

    @data_folder.setter
    def data_folder(self, val: pathlib.Path | None) -> None:
        self.model.data_folder = val

    @property
    def analysis_folder(self) -> pathlib.Path | None:
        return self.model.analysis_folder

    @analysis_folder.setter
    def analysis_folder(self, val: pathlib.Path | None) -> None:
        self.model.analysis_folder = val

    @property
    def file_type(self) -> str:
        return self.model.file_type

    @file_type.setter
    def file_type(self, val: str) -> None:
        self.model.file_type = val

    @property
    def bva_settings(self) -> dict[str, Any]:
        return self.model.bva_settings()

    @bva_settings.setter
    def bva_settings(self, val: dict[str, Any]) -> None:
        if not isinstance(val, dict):
            return
        if "donor_channels" in val:
            self.model.donor_channels_text = ",".join(str(x) for x in val["donor_channels"])
        if "acceptor_channels" in val:
            self.model.acceptor_channels_text = ",".join(str(x) for x in val["acceptor_channels"])
        if "donor_micro_time_ranges" in val:
            self.model.donor_micro_time_ranges = val["donor_micro_time_ranges"]
        if "acceptor_micro_time_ranges" in val:
            self.model.acceptor_micro_time_ranges = val["acceptor_micro_time_ranges"]
        if "minimum_window_length" in val:
            self.model.window_length = float(val["minimum_window_length"])
        if "number_of_photons_per_slice" in val:
            self.model.photons_per_slice = int(val["number_of_photons_per_slice"])
        if "file_type" in val:
            self.model.file_type = str(val["file_type"])

    @property
    def _df(self):
        return self.model.df

    @_df.setter
    def _df(self, val):
        self.model.df = val

    @property
    def _burst_df(self):
        return self.model.burst_df

    @_burst_df.setter
    def _burst_df(self, val):
        self.model.burst_df = val

    @property
    def _tttrs(self):
        return self.model.tttrs

    @_tttrs.setter
    def _tttrs(self, val):
        self.model.tttrs = val

    def _setup_toolbar(self) -> None:
        self.toolbar = QtWidgets.QToolBar("Main")
        self.toolbar.setObjectName("bvaMainToolbar")
        self.toolbar.setStyleSheet(TOOLBAR_STYLE)

        self.btn_folder = action_button("folder", tooltip="Select the burst analysis folder")
        self.btn_folder.clicked.connect(self._select_folder)
        self._folder_field = _folder_field("No folder selected")
        self._folder_field.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )

        self.btn_run = action_button("run", tooltip="Run BVA on all loaded data")
        self.btn_run.clicked.connect(self._run_analysis)

        self.btn_restart = action_button(
            "restart", tooltip="Recompute BVA from scratch, even if nothing changed"
        )
        self.btn_restart.clicked.connect(self._restart_analysis)

        self.btn_stop = action_button("stop", tooltip="Stop the running BVA analysis")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)

        self.btn_clear = action_button("clear", tooltip="Clear loaded data")
        self.btn_clear.clicked.connect(self._clear_plot)

        self.btn_save = action_button("save", tooltip="Save BVA results")
        self.btn_save.clicked.connect(self._save_plot)

        self.btn_save_settings = action_button(
            "settings", tooltip="Save current settings as default"
        )
        self.btn_save_settings.clicked.connect(self._save_settings)

        self.toolbar.addWidget(self.btn_folder)
        self.toolbar.addWidget(self.btn_run)
        self.toolbar.addWidget(self.btn_restart)
        self.toolbar.addWidget(self.btn_stop)
        self.toolbar.addWidget(self.btn_clear)
        self.toolbar.addWidget(self.btn_save)
        self.toolbar.addWidget(self._folder_field)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.btn_save_settings)
        self.add_toolbar_help(self.toolbar, resource="help.md", title="BVA — help")
        self.addToolBar(self.toolbar)

    def _on_model_event(self, event: str) -> None:
        if event in ("param", "channel", "folder"):
            self._on_param_changed()
        self.host.update()

    def _start_guide(self) -> None:
        if hasattr(self, "app") and hasattr(self.app, "start_guide"):
            self.app.start_guide()
            return
        if getattr(self, "_guide_button", None) is not None:
            self._guide_button.click()
        else:
            from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour
            from chisurf.gui.widgets.tools.help_guide import GUIDE_RESOURCE, resolve_tool_resource

            path = resolve_tool_resource(GUIDE_RESOURCE, self.model, self)
            if path is not None:
                steps = load_tour(path)
                tour = getattr(self.host, "_guided_tour", None)
                if tour is not None:
                    tour.stop()
                tour = GuidedTour(self.host, steps, model=self.model)
                self.host._guided_tour = tour
                tour.start()

    def _show_help(self) -> None:
        if hasattr(self, "app") and hasattr(self.app, "show_help"):
            self.app.show_help()
            return
        if getattr(self, "_help_button", None) is not None:
            self._help_button.show_help()

    def tour_target(self, target: dict[str, Any]) -> tuple[QtWidgets.QWidget, tuple | None] | None:
        """Tell GuidedTour where a step target is on this emtk surface."""
        name = target.get("name") or target.get("tab") or target.get("key") or target.get("attr")
        if name:
            rect = self.app.bva_gui.item_rects.get(str(name))
            if rect is not None:
                return self.host, rect
        return None

    def suspend_recompute(self):
        """Context manager suppressing auto-recompute while applying settings."""
        tool = self

        class _Suspend:
            def __enter__(self_inner):
                tool._suspend_recompute += 1

            def __exit__(self_inner, *exc):
                tool._suspend_recompute -= 1
                if tool._suspend_recompute == 0 and tool._recompute_pending:
                    tool._recompute_timer.start()
                return False

        return _Suspend()

    def _flush_recompute(self) -> None:
        if not self._recompute_pending:
            return
        self._recompute_pending = False
        self._start_analysis(write_output=False)

    def _refresh_detector_combos(self) -> None:
        self.host.update()

    def _select_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Data Folder")
        if folder:
            self._set_folder(folder)

    def _set_folder(self, path: str) -> None:
        from chisurf.core.fio.fluorescence import burst_tree

        p = pathlib.Path(path)
        if p.is_dir() or burst_tree.is_container_path(p):
            self.model.set_folder(p)
            self._folder_field.setText(str(p))
            self._status(f"Data folder: {p}")
            self._on_param_changed()
            self.host.update()

    def on_paths_dropped(self, paths: list[pathlib.Path]) -> None:
        from chisurf.core.fio.fluorescence import burst_tree

        for path in paths:
            if path.is_dir() or burst_tree.is_container_path(path):
                self.Information.not_a_folder.clear()
                self._set_folder(str(path))
                return
        if paths:
            self.Information.not_a_folder(paths[0].name)

    def _run_analysis(self) -> None:
        self._result_cache.allow()
        self._start_analysis(write_output=True)

    def _restart_analysis(self) -> None:
        self._result_cache.allow()
        self._start_analysis(write_output=True, force=True)

    def input_files(self) -> list[pathlib.Path]:
        return self.model.input_files()

    def _stamp_path(self) -> pathlib.Path | None:
        if self.model.analysis_folder is None:
            return None
        return pathlib.Path(self.model.analysis_folder) / "bv4" / "bva.stamp.json"

    def fingerprint_params(self, settings: dict) -> dict:
        return self.model.fingerprint_params(settings)

    def analysis_fingerprint(self, settings: dict) -> str:
        return self.model.analysis_fingerprint(settings)

    def _start_analysis(self, *, write_output: bool, force: bool = False) -> None:
        if not self.model.data_folder:
            self.Error.no_folder()
            return
        self.Error.no_folder.clear()

        settings = self.model.bva_settings()
        fingerprint = self.analysis_fingerprint(settings)
        stamp = self._stamp_path()
        outputs_current = bool(stamp) and analysis_cache.is_current(stamp, fingerprint)

        if (
            not force
            and self.model.df is not None
            and self._result_cache.matches(fingerprint)
            and (not write_output or outputs_current)
        ):
            self._status("Unchanged — kept the previous BVA result (🔁 Restart recomputes it)")
            flag_attention(self.btn_restart, True)
            return

        flag_attention(self.btn_restart, False)
        self._running_fingerprint = fingerprint
        self.btn_stop.setEnabled(True)
        self.model.is_running = True
        self.host.update()

        self._task = ChiSurfProgress.run(
            self,
            "Reading burst data...",
            self._analysis_worker,
            args=(
                dict(settings),
                bool(write_output),
                fingerprint,
                self.input_files(),
                self.fingerprint_params(settings),
            ),
            maximum=0,
            title="BVA Analysis",
            owner=self,
            on_result=self._analysis_done,
            on_error=self._analysis_failed,
            on_done=self._analysis_over,
        )

    def _analysis_over(self) -> None:
        self._task = None
        self.btn_stop.setEnabled(False)
        self.model.is_running = False
        self.host.update()

    def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        self._result_cache.abandon(self._running_fingerprint)
        self._status("Stopping the BVA analysis …")
        self.host.update()

    def _analysis_failed(self, exc) -> None:
        self._result_cache.invalidate()
        self.Error.failed(exc)
        self.host.update()

    def _analysis_worker(self, settings, write_output, fingerprint, inputs, params, task):
        burst_df, tttrs = self.model.burst_df, self.model.tttrs
        if burst_df is None or tttrs is None:
            task.set_range(0, 0)
            task.set_text("Reading burst data...")
            burst_df, tttrs = core.read_burst_analysis(
                self.model.analysis_folder,
                self.model.file_type,
                pattern="bi4_bur",
            )

        task.set_range(0, row_count(burst_df))
        task.set_text("Computing BVA...")
        df_v = core.compute_bva(
            burst_df,
            tttrs,
            progress_window=task.progress_window("Computing BVA..."),
            **settings,
        )

        if write_output and self.model.analysis_folder is not None:
            import numpy as np

            task.set_range(0, len(set(np.asarray(df_v["First File"]).tolist())))
            task.set_text("Writing BV4 files...")
            try:
                core.write_bv4_analysis(
                    df_v,
                    str(self.model.analysis_folder),
                    progress_window=task.progress_window("Writing BV4 files..."),
                )
            except Exception as e:
                logging.error(f"BV4 write failed: {e}")
            bv4_folder = self.model.analysis_folder / "bv4"
            bv4_folder.mkdir(parents=True, exist_ok=True)
            with open(bv4_folder / "bva_settings.json", "w") as f:
                json.dump(settings, f, indent=4)
            analysis_cache.write_stamp(
                bv4_folder / "bva.stamp.json",
                fingerprint,
                params=params,
                inputs=inputs,
                outputs=sorted(bv4_folder.glob("*.bv4")),
                tool="bva",
            )
        return burst_df, tttrs, df_v

    def _analysis_done(self, payload) -> None:
        burst_df, tttrs, df_v = payload
        self.model.set_result(burst_df, tttrs, df_v)
        if self._running_fingerprint is not None:
            self._result_cache.remember(self._running_fingerprint)
        self._status(self.model.status_text)
        self.host.update()

    def _on_param_changed(self) -> None:
        if hasattr(self, "_auto_update_cb") and not self._auto_update_cb.isChecked():
            return
        if not self.model.auto_update:
            return
        self._recompute_pending = True
        if self._suspend_recompute == 0:
            self._recompute_timer.start()

    def _save_settings(self) -> None:
        ini = QtCore.QSettings(
            str(get_plugin_settings_path("burst_bva")), QtCore.QSettings.IniFormat
        )
        ini.setValue("window_length", str(self.model.window_length))
        ini.setValue("photons_per_slice", str(self.model.photons_per_slice))
        ini.setValue("bins_x", self.model.bins_x)
        ini.setValue("bins_y", self.model.bins_y)
        if self.model.data_folder is not None:
            ini.setValue("last_folder", str(self.model.data_folder))
        self._status("Settings saved")

    def _clear_plot(self) -> None:
        self.model.df = None
        self._result_cache.invalidate()
        self._status("Plot cleared")
        self.host.update()

    def _save_plot(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Plot",
            "bva_plot.png",
            "PNG (*.png)",
        )
        if path:
            pm = self.host.grab()
            pm.save(path)

    def _restore_dock_layout(self):
        try:
            settings = QSettings("chisurf", "BVATool")
            value = settings.value("dock_layout_v2")
            if isinstance(value, str):
                layout_state = json.loads(value)
            elif isinstance(value, dict):
                layout_state = value
            else:
                return
            if not getattr(self, "_embedded", False):
                geometry = settings.value("window_geometry")
                if geometry is not None and hasattr(self, "restoreGeometry"):
                    self.restoreGeometry(geometry)
                state = settings.value("window_state")
                if state is not None and hasattr(self, "restoreState"):
                    self.restoreState(state)
            if hasattr(self, "dock_area") and self.dock_area is not None:
                self.dock_area.set_layout_state(layout_state, emit_change=False)
        except Exception:
            pass

    def _status(self, msg: str) -> None:
        self.model.status_text = msg
        logging.getLogger(__name__).info(msg)
        self.host.update()


__all__ = ["BVATool"]
