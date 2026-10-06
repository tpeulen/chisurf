"""Qt-free model of the emtk phasor window (the analysis is :class:`~.view_model.PhasorImgViewModel`, shared with the Qt tool)."""

from __future__ import annotations

from ...imaging_emtk.pixel_model import PixelModelMixin
from .view_model import PhasorImgViewModel


class PhasorModel(PixelModelMixin, PhasorImgViewModel):
    """Per-pixel phasor (g, s) plus the state of the emtk window."""

    TOOL_NAME = "Phasor"
    SETTINGS = ("n_ph_min", "frequency")
    REGIONS_ATTR = "cursors"
    COPIED = ("cursors",)

    def __init__(self) -> None:
        PhasorImgViewModel.__init__(self)
        self.status_line = ""
        self.irf_window = ""

    def artifact_name(self) -> str:
        return "phasor"

    # -- the IRF reference of a detector window (the Qt tool takes it from the IRF & BG step) ---------------- #
    def irf_window_choices(self) -> list[str]:
        return self.window_names()

    @property
    def irf_path(self) -> str:
        window = (
            self.irf_window if self.irf_window in self._windows() else next(iter(self._windows()))
        )
        files = self._windows()[window].get("irf") or []
        return str(files[0]) if files else ""

    @irf_path.setter
    def irf_path(self, value: str) -> None:
        pass  # committed by ``commit_irf`` (a typed path is validated before it is adopted)

    def commit_irf(self, value: str) -> None:
        """Use the file *value* as the reference of the chosen window (empty: none); the next Run applies it."""
        value = str(value or "").strip()
        window = (
            self.irf_window if self.irf_window in self._windows() else next(iter(self._windows()))
        )
        if not self.detectors:
            self.detectors = {window: {"chs": [0], "micro_time_ranges": []}}
        self.detectors[window]["irf"] = [value] if value else []
        self.status_line = f"IRF of {window}: {value or 'none'}. Press Run to apply."
        self.notify("setup")

    def clear_irf(self) -> None:
        self.commit_irf("")

    def open_irf(self) -> None:
        self.request_dialog("irf")

    def open_irf_path(self, path: str) -> None:
        self.remember_folder(path)
        self.commit_irf(str(path))

    def calibration_rows(self) -> list[dict]:
        return self.window_rows()

    def notify_regions(self) -> None:
        self.notify_cursors()

    def regions_changed(self) -> None:
        self.notify_cursors()
