"""Qt-free model of the emtk pixel-wise MLE window (the analysis is :class:`~.view_model.PixelMleViewModel`, shared with the Qt tool)."""

from __future__ import annotations

import copy
import pathlib
import threading
from typing import Any

from ...imaging_emtk.model_base import EmtkModelMixin
from .view_model import PixelMleViewModel

PHOTON_FILE_FILTER = "Photon data (*.pto *.ptu *.ht3 *.spc *.pt3);;All files (*)"
REGION_FILE_FILTER = "Regions (*.json *.npy *.tif *.tiff *.png);;All files (*)"

#: scalar settings kept between sessions (attributes of the view model)
PERSISTED = ("channels_parallel_text", "channels_perpendicular_text", "micro_time_start", "micro_time_stop", "micro_time_binning", "min_photons",
             "irf_threshold", "shift_sp", "shift_ss", "twoi_star", "bifl_scatter", "use_bg", "bg_p", "bg_s", "engine", "n_workers", "roi_path")


class PixelMleModel(EmtkModelMixin, PixelMleViewModel):
    """Pixel-wise MLE plus the state of the emtk window."""

    colormap = "inferno"

    def __init__(self) -> None:
        PixelMleViewModel.__init__(self)
        self.cancel_event = threading.Event()
        self._busy_text = ""
        self.has_host = False

    # the Qt status bar is the view model's ``status_text``
    @property
    def status_line(self) -> str:  # type: ignore[override]
        return self.status_text

    @status_line.setter
    def status_line(self, value: str) -> None:
        self.status_text = value

    def __copy__(self):
        snapshot = PixelMleViewModel.__copy__(self)
        snapshot.settings = copy.deepcopy(self.settings)
        return snapshot

    # -- choices -------------------------------------------------------------------------- #
    def engine_choices(self) -> list[str]:
        return ["auto", "fast", "loop"]

    def fit_model_choices(self) -> list[str]:
        return ["fit23", "fit24", "fit25"]

    def enabled(self, name: str) -> bool:
        if self.busy:
            return False
        if name == "request_run":
            return self.can_run()[0]
        if name == "export_results":
            return bool(self.results)
        return True

    # -- files ---------------------------------------------------------------------------- #
    def add_files(self, paths: list[str]) -> None:
        added = [p for p in dict.fromkeys(str(p) for p in paths) if p not in self.files]
        if added:
            self.remember_folder(added[0])
            self.files = [*self.files, *added]
            self.status_text = ""
            self.notify("files")
            self.notify("settings")

    def add_irf(self, paths: list[str]) -> None:
        """The IRF is one file (a new one replaces the old)."""
        if paths:
            self.remember_folder(str(paths[0]))
            self.irf_files = [str(paths[0])]
            self.status_text = ""
            self.notify("irf")
            self.notify("settings")

    def open_path(self, path: str) -> None:
        """A dataset picked in the database: a photon file to analyse."""
        self.add_files([path])

    def open_second_path(self, path: str) -> None:
        """A dataset picked in the database for the IRF."""
        self.add_irf([path])

    def open_database_second(self) -> None:
        self.request_dialog("database_second")

    def open_roi(self) -> None:
        self.request_dialog("roi")

    def set_roi_file(self, path: str) -> None:
        self.remember_folder(path)
        self.roi_path = str(path)

    def commit_roi(self, value: str) -> None:
        self.roi_path = str(value or "")

    # -- running -------------------------------------------------------------------------- #
    def request_run(self) -> None:
        """Fit every selected file in the background (the Qt Run)."""
        ok, reason = self.can_run()
        if not ok:
            self.status_text = reason
            return
        self.cancel_event.clear()
        self.status_text = "Fitting..."
        self.run_job("fit_job")

    def fit_job(self) -> None:
        """The worker body: the blocking ``run`` of the Qt tool."""
        self.run()
        self.notify("run")

    def cancel(self) -> None:
        self.cancel_event.set()
        self.status_text = "Cancelling..."

    def export_results(self) -> None:  # the CSV is written per file by run(); nothing more to write
        pass

    # -- hub adapters (the Imaging Tools hub talks to the model; the app forwards) --------- #
    def apply_pipeline_context(self, payload: dict) -> None:
        super().apply_pipeline_context(payload)

    # -- settings ------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        state = {name: getattr(self, name) for name in PERSISTED}
        state.update(files=list(self.files), irf_files=list(self.irf_files), fit_model=self.fit_model, folder=self.folder,
                     model_params={k: [list(v[0]), list(v[1])] for k, v in self._model_params.items()})
        return state

    def restore_settings(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        for name in PERSISTED:
            if name not in state:
                continue
            current, value = getattr(self, name), state[name]
            try:
                if isinstance(current, bool) and not isinstance(value, bool):
                    continue
                if isinstance(current, (int, float)) and not isinstance(current, bool) and (isinstance(value, (bool, str)) or value != value):
                    continue
                if isinstance(current, str) and not isinstance(value, str):
                    continue
                if name == "engine" and value not in self.engine_choices():
                    continue
                setattr(self, name, value)
            except (TypeError, ValueError):
                continue
        if isinstance(state.get("files"), list):
            self.files = [str(p) for p in state["files"]]
        if isinstance(state.get("irf_files"), list):
            self.irf_files = [str(p) for p in state["irf_files"]][:1]
        if state.get("fit_model") in self.fit_model_choices():
            self.fit_model = state["fit_model"]
        if isinstance(state.get("folder"), str):
            self.folder = state["folder"]
        for name, pair in (state.get("model_params") or {}).items():
            if name in self.fit_model_choices() and isinstance(pair, list) and len(pair) == 2:
                try:
                    self._model_params[name] = ([float(x) for x in pair[0]], [int(x) for x in pair[1]])
                except (TypeError, ValueError):
                    continue

    @property
    def summary_text(self) -> str:
        from .app_text import plain

        return plain(self.info_html())
