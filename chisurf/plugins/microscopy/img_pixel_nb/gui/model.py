"""Qt-free model of the emtk N&B window (the analysis is :class:`~.view_model.NBViewModel`, shared with the Qt tool)."""

from __future__ import annotations

from ...imaging_emtk.pixel_model import PixelModelMixin
from .view_model import CROSS_OFF, NBViewModel


class NBModel(PixelModelMixin, NBViewModel):
    """Number & Brightness maps plus the state of the emtk window."""

    TOOL_NAME = "N&B"
    SETTINGS = (
        "subtract",
        "add",
        "box_pixels",
        "box_frames",
        "background",
        "detrend_segments",
        "dead_time_ns",
        "pixel_dwell_us",
        "gain",
        "offset",
        "read_variance",
        "smoothing",
        "radius",
        "median",
        "gamma",
        "plane_x",
        "plane_y",
        "plane_bins",
        "log_histogram",
        "cross_window",
    )
    REGIONS_ATTR = "gates"
    COPIED = ("gates",)

    def __init__(self) -> None:
        NBViewModel.__init__(self)
        self.status_line = ""

    def artifact_name(self) -> str:
        return "nb"

    # the lists of the Qt choices: a saved value outside them is ignored on restore
    def subtract_choices(self) -> list[str]:
        return ["none", "frame_mean", "pixel_mean", "moving_average"]

    def add_choices(self) -> list[str]:
        return ["none", "total_mean", "frame_mean", "pixel_mean", "moving_average"]

    def smoothing_choices(self) -> list[str]:
        return ["none", "average", "disk", "gaussian"]

    def plane_x_choices(self) -> list[str]:
        return self.plane_axis_names()

    def plane_y_choices(self) -> list[str]:
        return self.plane_axis_names()

    def enabled(self, name: str) -> bool:
        if name == "calibrate_analog":
            return not self.busy and bool(self._by_window)
        return super().enabled(name)

    def after_compute(self) -> None:
        self._cross()

    # -- display changes that need the cross maps ----------------------------------------------- #
    def refresh_display(self, value=None) -> None:
        """A window or axis choice changed: redraw; the cross maps of a new window pair are built on the worker."""
        self.notify("run")
        if self._by_window and self.cross_window not in ("", CROSS_OFF) and self._cross_missing():
            self.run_job("compute_cross_job")

    def _cross_missing(self) -> bool:
        return self.cross_window != self.display_window and not self._movie_cache.get("cross_nb")

    def compute_cross_job(self) -> None:
        if self.cancel_event.is_set():
            raise RuntimeError("N&B calculation cancelled.")
        self._cross()
        self.notify("run")

    # -- the demo and the analog calibration (the Qt toolbar's) ----------------------------------- #
    def demo(self) -> None:
        """Write (or reuse) the monomer / dimer demo stream, load it and compute (the Qt Load demo)."""
        self.status_line = "Simulating the demo scan..."
        self.cancel_event.clear()
        self.run_job("demo_job")

    def demo_job(self) -> None:
        try:
            self.load_demo()
        except Exception as exc:  # the simulator is missing from this tttrlib build, or the settings folder is not writable
            self.results_text = f"Demo failed: {exc}"
            self.status_line = self.results_text
            return
        self.status_line = ""
        self.notify("demo")
        self.notify("run")

    def notify_regions(self) -> None:
        self.notify_gates()

    def regions_changed(self) -> None:
        self.notify_gates()
