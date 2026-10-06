"""Native emtk 2D-FLCS tool (form from ``flc_2d_emtk.view.json``).

The spec is drawn by :func:`emtk.view_form.draw_form`; the two lifetime maps, the
three line plots and the L-curve are the spec's ``custom`` sections, drawn by
callbacks registered in :attr:`emtk.view_form.FormState.custom`. All state and work
is in :class:`~.model.FlcModel` (the same model the Qt tool uses); opening a stream,
simulating one and the analysis run on a :class:`chisurf.emtk.jobs.SnapshotJob`.

The top-level sections of the spec become docked windows: *Settings* (status line,
Open / IRF / Sim / Run and the parameters) on the left, and the result windows as
tabs on the right, as the Qt tool showed them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob

from .model import PHOTON_FILE_FILTER, FlcModel

HERE = Path(__file__).parent

#: Dialog requests the model can make -> (title, mode, filters).
DIALOGS = {
    "open_tttr": ("Open TTTR file", "open", PHOTON_FILE_FILTER),
    "open_irf": ("Open IRF (TTTR) file", "open", PHOTON_FILE_FILTER),
}

#: Series colours of the model's plot sources (pyqtgraph letters -> RGBA).
COLOURS = {
    "y": (255, 215, 0, 255),
    "c": (0, 200, 220, 255),
    "m": (220, 60, 220, 255),
    "g": (40, 190, 60, 255),
    "r": (235, 50, 50, 255),
}

#: Window keys, in the order of the spec's top-level sections.
WINDOW_KEYS = (
    "toolbar",
    "settings",
    "spectrum_image",
    "residual_image",
    "lifetime_series",
    "correlation_series",
    "lcurve_data",
    "irf_series",
)


def _spec_keys(section: dict) -> set[str]:
    """Every ``attr`` and ``action`` named below *section* (what a guide step can point at)."""
    keys: set[str] = set()
    if section.get("attr"):
        keys.add(section["attr"])
    for button in section.get("buttons") or []:
        keys.add(button["action"])
    for child in section.get("sections") or []:
        keys |= _spec_keys(child)
    return keys


class FlcApp(ImApp):
    """2D-FLCS: build the 2D-FDC, invert it to a lifetime map and read the exchange."""

    def __init__(self, model: FlcModel | None = None) -> None:
        self.model = model or FlcModel()
        self.job = SnapshotJob(self.model)
        self.model.add_observer(self._on_event)
        self.spec = json.loads((HERE / "flc_2d_emtk.view.json").read_text(encoding="utf-8"))
        self.windows = self.spec["sections"][0]["sections"]
        self.form = FormState()
        self.form.custom.update(
            image=self._draw_image,
            series_plot=self._draw_series_plot,
            lcurve=self._draw_lcurve,
        )
        self._settings_keys = _spec_keys(self.windows[1])
        self.canvases: dict[str, ImageCanvas] = {}
        self._image_ids: dict[str, int] = {}
        self.dialog: FileDialog | None = None
        self.dialog_kind = ""
        self.item_rects: dict[str, tuple] = {}
        self.error = ""
        self._reported_error = ""
        self._job_method = ""
        self.help_window = EmTkHelpWindow(
            title="2D-FLCS — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.docks = DockManager(Split("v", 0.12, Region("bar"), Region("main")))
        for key, section in zip(WINDOW_KEYS, self.windows):
            # Settings and the results are tabs of one region, as in the Qt tool's dock
            # area; the toolbar (status line and buttons) stays above them.
            self.docks.add_window(
                key,
                section["title"],
                self._result_drawer(section),
                dock="bar" if key == "toolbar" else "main",
                closable=False,
            )
        super().__init__(self.render, continuous=False)

    # ── jobs ───────────────────────────────────────────────────────────
    def start_job(self, method: str, *args: Any) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self.model.error_text = ""
        self._reported_error = ""
        started = self.job.start(method, *args)
        if started:
            self._job_method = method
            self.model.busy = True
        return started

    def _on_event(self, event: str) -> None:
        """Turn the buttons' ``start_*`` announcements into work (draw thread only)."""
        if event == "show_help":
            self.help_window.show()
        elif event == "start_tour":
            self.tour.start()
        elif event == "start_run":
            self.start_job("run")
        elif event == "start_simulate":
            self.start_job("simulate")

    def animating(self) -> bool:
        """Keep drawing while a worker runs, so its result appears."""
        return self.job.busy or super().animating()

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.busy:
            self.model.status_text = self.job.progress or self.model.status_text
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.error_text = self.job.error
        if self._job_method and not self.job.busy:
            self._job_finished(self._job_method)
            self._job_method = ""
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self._open_requested_dialog()
        self._follow_tour()
        self.docks.draw(box)
        self._draw_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _job_finished(self, method: str) -> None:
        """Release the tour's outcome steps: the stream is there, the analysis has run."""
        if self.model.error_text:
            return
        if method == "simulate":
            self.tour.notify_used("Sim")
        elif method == "run":
            self.tour.notify_used("Run")

    def _follow_tour(self) -> None:
        """Bring the window or panel the tour points at into view."""
        if not (self.tour.active and self.tour.steps):
            return
        key = self.tour._target_key(self.tour.steps[self.tour.step_idx].get("target"))
        for window_key, section in zip(WINDOW_KEYS, self.windows):
            if key == section.get("title") and window_key != "toolbar":
                self.docks.focus(window_key)
        if key in self._settings_keys:
            self.docks.focus("settings")
        if key.startswith("sim_"):
            self.form.folds["Simulator"] = True

    # ── windows ────────────────────────────────────────────────────────
    def _collect_rects(self) -> None:
        """Name the controls by the labels the guide points at."""
        rects = self.form.rects
        for key, name in (
            ("Open", "request_open"),
            ("IRF", "request_open_irf"),
            ("Sim", "request_simulate"),
            ("Run", "request_run"),
            ("help", "request_help"),
            ("guide", "request_guide"),
        ):
            if name in rects:
                self.item_rects[key] = rects[name]

    def _draw_window(self, section: dict) -> None:
        """Draw one window's section; the toolbar also names the buttons the guide points at."""
        # A panel's title is its tab's; a custom section draws its own caption.
        if section.get("type") == "panel":
            draw_sections(section.get("sections") or [], self.model, self.form, 1, True)
        else:
            draw_sections([section], self.model, self.form)
        self._collect_rects()
        if self.error and section.get("title") == "Toolbar":
            im.text_wrapped(self.error)

    def _result_drawer(self, section: dict):
        """Return the draw function of one result window."""

        def draw(box: Any) -> None:
            self._draw_window(section)

        return draw

    def _caption(self, section: dict, state: FormState) -> None:
        """The window's title line; its tooltip is the section's description."""
        title = section.get("title", "")
        im.text_unformatted(title)
        im.set_item_tooltip(section.get("description", ""))
        self.item_rects[title] = state.rects[title] = im.get_item_rect()

    # ── custom section: a lifetime map ─────────────────────────────────
    def _draw_image(self, section: dict, model: FlcModel, state: FormState, width: float) -> None:
        """The 2D-FLCS map or its residual, with the shared colormap."""
        self._caption(section, state)
        target = section["target"]
        canvas = self.canvases.get(target)
        if canvas is None:
            canvas = self.canvases[target] = ImageCanvas(target)
            canvas.colormap = "viridis"
        image = getattr(model, target)()
        if canvas.colormap != model.colormap and model.colormap in (
            "magma",
            "inferno",
            "viridis",
            "gray",
        ):
            canvas.colormap = model.colormap
        if image is not None and self._image_ids.get(target) != id(image):
            self._image_ids[target] = id(image)
            canvas.reset()
        if image is None:
            im.text_disabled("Run the analysis to see this map.")
            return
        canvas.draw(image, pick_enabled=False)
        if canvas.colormap != model.colormap:
            model.colormap = canvas.colormap

    # ── custom section: line series ────────────────────────────────────
    def _draw_series_plot(
        self, section: dict, model: FlcModel, state: FormState, width: float
    ) -> None:
        """A plot of the model's ``source`` series (``x``, ``y``, ``color``, ``name``)."""
        self._caption(section, state)
        series = getattr(model, section["source"])()
        log_x = bool(section.get("log_x"))
        height = max(120.0, im.get_content_region_avail()[1] - 6.0)
        if implot.begin_plot("##" + section["source"], (-1.0, height)):
            implot.setup_axes(section.get("x_label", ""), section.get("y_label", ""))
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            if log_x:
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                if not series:
                    implot.setup_axis_limits(implot.AXIS_X1, 0.1, 10.0, implot.COND_ONCE)
            for item in series:
                x = np.asarray(item["x"], dtype=float)
                y = np.asarray(item["y"], dtype=float)
                keep = np.isfinite(x) & np.isfinite(y) & ((x > 0) if log_x else True)
                if not keep.any():
                    continue
                implot.set_next_line_style(
                    COLOURS.get(item.get("color", "y"), COLOURS["y"]),
                    float(item.get("width", 1)) + 0.5,
                )
                implot.plot_line(str(item.get("name", "")), x[keep], y[keep])
            implot.end_plot()

    # ── custom section: the L-curve ────────────────────────────────────
    def _draw_lcurve(self, section: dict, model: FlcModel, state: FormState, width: float) -> None:
        """Residual against solution norm (log-log); the corner is marked."""
        self._caption(section, state)
        data = getattr(model, section["target"])()
        height = max(120.0, im.get_content_region_avail()[1] - 6.0)
        if implot.begin_plot("##lcurve", (-1.0, height)):
            implot.setup_axes("residual norm", "solution norm")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if data is None:
                implot.setup_axes_limits(0.1, 10.0, 0.1, 10.0, implot.COND_ONCE)
            else:
                x = np.asarray(data.residual_norm, dtype=float)
                y = np.asarray(data.solution_norm, dtype=float)
                keep = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
                implot.set_next_line_style(COLOURS["c"], 2.0)
                implot.plot_line("L-curve", x[keep], y[keep])
                corner = int(data.corner_index)
                if 0 <= corner < len(x) and x[corner] > 0 and y[corner] > 0:
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 8.0, COLOURS["r"])
                    implot.plot_scatter("chosen", np.array([x[corner]]), np.array([y[corner]]))
            implot.end_plot()

    # ── file dialogs ───────────────────────────────────────────────────
    def _open_requested_dialog(self) -> None:
        """Turn the model's ``dialog`` request into a :class:`FileDialog`."""
        kind, self.model.dialog = self.model.dialog, ""
        if not kind or self.dialog is not None or kind not in DIALOGS:
            return
        title, mode, filters = DIALOGS[kind]
        self.dialog = FileDialog(
            title, mode=mode, filters=filters, directory=self.model.folder or None
        )
        self.dialog_kind = kind

    def _draw_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                kind, self.dialog = self.dialog_kind, None
                self._dialog_done(kind, [str(p) for p in result])
            elif result is False:
                self.dialog = None
        im.end()

    def _dialog_done(self, kind: str, paths: list[str]) -> None:
        """Act on what a dialog returned; a failure is shown, never raised."""
        self.error = ""
        self.model.folder = str(Path(paths[0]).parent)
        self.start_job("open_irf" if kind == "open_irf" else "open_tttr", paths[0])

    # ── files dropped on the window ────────────────────────────────────
    def on_paths_dropped(self, paths: Any) -> None:
        """Open a dropped photon file as the stream (ignored while a worker runs)."""
        if paths and not self.job.busy:
            self._dialog_done("open_tttr", [str(paths[0])])

    def files_dropped(self, paths: Any) -> bool:
        self.on_paths_dropped(paths)
        return bool(paths)

    on_files_dropped = files_dropped

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """Settings to keep between sessions."""
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        """Adopt settings from :meth:`export_settings`."""
        self.model.restore_settings(state)

    def close(self) -> None:
        """Nothing to release: workers are daemon threads and no file stays open."""


def make_app() -> FlcApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    return FlcApp()
