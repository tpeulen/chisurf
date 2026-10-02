"""Native emtk pixel-wise MLE tool (settings form and lifetime map from ``pixel_mle_emtk.view.json``) on the shared imaging shell."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from emtk.docking import Region, Split

from ...imaging_emtk.app_base import ImagingToolApp
from ...imaging_emtk.path_list import PathListView
from .model import PHOTON_FILE_FILTER, REGION_FILE_FILTER, PixelMleModel

HERE = Path(__file__).parent


class PixelMleApp(ImagingToolApp):
    """Pixel-by-pixel Poisson maximum-likelihood lifetimes of confocal photon files."""

    GUI_DIR = HERE
    SPEC = "pixel_mle_emtk.view.json"
    TITLE = "Pixel-wise MLE"
    HELP_TITLE = "Pixel-wise MLE - Help"
    ROLE = "pixel_mle"
    CANCELLABLE = True
    LAYOUT = Split("h", 0.38, Region("settings"), Region("views"))
    DIALOGS = {
        "add_files": ("Add imaging files", "open", PHOTON_FILE_FILTER, "add_files", True),
        "add_irf": ("Choose the IRF file", "open", PHOTON_FILE_FILTER, "add_irf", True),
        "roi": ("Choose a region", "open", REGION_FILE_FILTER, "set_roi_file"),
    }
    OUTCOMES = {"run": "request_run", "files": "sel_files", "irf": "sel_irf_files"}

    def __init__(self, model: PixelMleModel | None = None, coordinator: Any = None) -> None:
        self.coordinator = coordinator
        self._pending: dict = {}
        super().__init__(model or PixelMleModel())
        self.lists = PathListView(self)
        self.form.custom["path_list"] = lambda section, m, st, w: self.lists.draw(section, m)
        self.model.has_host = coordinator is not None

    # -- the imaging hub's contract ------------------------------------------------------- #
    def start(self, method: str = "request_run", *args: Any) -> bool:
        self.model.request_run()
        return self.job.busy

    def _defer(self, key: str, payload: dict) -> bool:
        """A context that arrives while a worker runs is applied after it delivered (the worker's result would overwrite it)."""
        if self.job.busy or self.model.busy:
            self._pending[key] = copy.deepcopy(payload)
            return True
        return False

    def apply_setup_settings(self, payload: dict) -> None:
        if not self._defer("setup", payload):
            self.model.apply_setup_settings(payload)
            self.request_frame()

    def apply_pipeline_context(self, payload: dict) -> None:
        if not self._defer("pipeline", payload):
            self.model.apply_pipeline_context(payload)
            self.request_frame()

    def apply_calibration(self, payload: dict) -> None:
        if not self._defer("calibration", payload):
            self.model.apply_calibration(copy.deepcopy(payload))
            self.request_frame()

    def _draw_main(self, box: tuple) -> None:
        if self._pending and not (self.job.busy or self.model.busy):
            pending, self._pending = dict(self._pending), {}
            for key, method in (("setup", self.model.apply_setup_settings), ("pipeline", self.model.apply_pipeline_context),
                                ("calibration", self.model.apply_calibration)):
                if key in pending:
                    method(pending[key])
        super()._draw_main(box)

    def export_settings(self) -> dict:
        state = self.model.export_settings()
        state["colormap"] = self.model.colormap
        return state

    def restore_settings(self, state: dict) -> None:
        if self.job.busy or not isinstance(state, dict):
            return
        self.model.restore_settings(state)
        if state.get("colormap") in ("magma", "inferno", "viridis", "gray"):
            self.model.colormap = state["colormap"]

    def files_dropped(self, paths: Any) -> bool:
        """Dropped photon files are added to the list (the Qt path list took drops)."""
        paths = [str(p) for p in paths]
        if not paths or self.job.busy or self.model.busy:
            return False
        self.model.add_files(paths)
        return True


def make_app(coordinator=None) -> PixelMleApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return PixelMleApp(coordinator=coordinator)
