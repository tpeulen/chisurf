"""The Burst Fusion tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstFusionApp`) over
:class:`~.view_model.FusionViewModel`:
- Left pane: form controls declared in ``fusion.view.json`` rendered by
  :mod:`emtk.view_form` (source folder, P(same) threshold, max gap, max fragments,
  Run/Estimate action buttons, status text, summary before/after table, and the
  collapsible P_same estimate parameters).
- Right pane: plots drawn with :mod:`emtk.implot` (Same-molecule probability curve
  with threshold and cutoff lines, Proximity ratio histogram, Photons per burst,
  Burst duration, and Fragments per fused burst).

This app is toolkit-free and can run under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import pathlib
from typing import Any, Callable

import emtk
import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.im_core import get_current_context
from emtk.view_form import FormState, draw_sections, find_section
from emtk.widgets.view_spec import load_view_spec

from chisurf.plugins.emtk_layout import (
    LabelColumn, button_row, cap_widths, group_by_width, icon_label, labelled,
)

from .view_model import FusionViewModel

__all__ = ["BurstFusionApp", "BurstFusionGui", "WINDOW_BG"]

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)


def _hex_to_rgba(
    color: Any, default: tuple[int, int, int, int] = (200, 200, 200, 255)
) -> tuple[int, int, int, int]:
    """Convert hex string (e.g. #1f77b4) or rgb tuple to rgba tuple."""
    if isinstance(color, str):
        hex_str = color.lstrip("#")
        if len(hex_str) == 6:
            r = int(hex_str[:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return (r, g, b, 255)
    elif isinstance(color, (tuple, list)):
        if len(color) >= 3:
            return (
                int(color[0]),
                int(color[1]),
                int(color[2]),
                255 if len(color) == 3 else int(color[3]),
            )
    return default


from chisurf.emtk.help_guide import TourTarget


class BurstFusionGui(TourTarget):
    """The immediate-mode GUI logic and rendering for Burst Fusion."""

    def __init__(
        self,
        model: FusionViewModel | None = None,
        on_demo: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else FusionViewModel()
        self.on_demo = on_demo
        self.on_guide = on_guide
        self.on_help = on_help
        self.form_state = FormState()
        spec_path = pathlib.Path(__file__).parent / "fusion.view.json"
        self.spec = load_view_spec(str(spec_path))
        self.dock_spec = self.spec["sections"][0] if self.spec.get("sections") else {}
        self.fusion_panel = find_section(self.dock_spec, "Fusion") or {}

        # Keep the before/after summary compact so advanced parameters remain reachable.
        for section in self.fusion_panel.get("sections", []):
            if section.get("type") == "table":
                section["expand"] = False
                section["height"] = 210       # the nine summary rows, none cut off
        cap_widths(self.fusion_panel.get("sections", []))
        self.labels = LabelColumn()

        # Register custom sections
        self.form_state.custom["fusion_actions"] = self._draw_fusion_actions

        self.selected_tab = "All"
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None
        from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

        help_resource = pathlib.Path(__file__).parent / "help.md"
        guide_resource = pathlib.Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Fusion — Help & Reference",
            resource=help_resource,
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        # Targets are buttons (item_rects) or spec fields (the form's rects); the action
        # steps wait for their control.
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k) or self.form_state.rects.get(k),
            owner=self.model,
            wait_for_controls=True,
        )
        self.on_used = self.tour.notify_used
        self.form_state.on_used = self.tour.notify_used
        from emtk.docking import DockManager, Region, Split

        self.docks = DockManager(
            Split("h", 0.35, Region("controls"), Region("plots")), name="burst_fusion"
        )
        self.docks.add_window("controls", "Fusion controls", self._draw_controls, dock="controls")
        self.docks.add_window("plots", "Fusion plots", self._draw_plots, dock="plots")


    def _draw_controls(self, box):
        controller = getattr(self, "controller", None)
        if controller:
            controller.draw_controls(remember=self.remember)
        running = bool(controller and controller.running)
        target = self.model
        if running:
            # ``begin_disabled`` greys the spec's fields but they still take typing; an edit during a run was then
            # overwritten when the worker's snapshot came back (the run's own settings). The fields draw against a
            # throw-away copy while a run is in flight, so an edit is refused instead of silently lost.
            import copy

            target = copy.copy(self.model)
            target.settings = copy.deepcopy(self.model.settings)
            target._observers = []
        if not self.labels.ready:
            fields = [s for s in labelled(self.fusion_panel.get("sections", []))]
            self.labels.measure([f["label"] for f in fields])
            self.labels.pad(self.fusion_panel.get("sections", []))
        sections = self.fusion_panel.get("sections", [])
        at = next((i for i, s in enumerate(sections) if s.get("key") == "fusion_actions"), len(sections))
        im.begin_disabled(running)
        draw_sections(group_by_width(sections[:at]), target, self.form_state, n_col=1, titles=True)
        im.end_disabled()
        self._draw_fusion_actions(None, self.model, self.form_state, 0.0)     # Stop stays live while a run is in flight
        im.begin_disabled(running)
        draw_sections(sections[at + 1:], target, self.form_state, n_col=1, titles=True)
        im.end_disabled()
        if "summary_rows" in self.form_state.rects:  # the guide names the table by its title
            self.item_rects["Summary"] = self.form_state.rects["summary_rows"]

    def _draw_plots(self, box):
        if im.begin_tab_bar("fusion_plot_tabs"):
            for key, label in [
                ("All", "All plots"),
                ("P_same", "P(same)"),
                ("PR", "Proximity ratio"),
                ("Photons", "Photons"),
                ("Duration", "Duration"),
                ("Fragments", "Fragments"),
            ]:
                if im.begin_tab_item(label):
                    self.selected_tab = key
                    im.end_tab_item()
                im.set_item_tooltip(f"Show the {label.lower()} before/after comparison.")
            im.end_tab_bar()
        width, height = im.get_content_region_avail()
        plot = {
            "All": self._draw_all_plots,
            "P_same": self._plot_p_same,
            "PR": self._plot_proximity,
            "Photons": self._plot_photons,
            "Duration": self._plot_duration,
            "Fragments": self._plot_fragments,
        }[self.selected_tab]
        plot(max(80, width), max(100, height))

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def _on_model_event(self, event: str) -> None:
        pass

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def _draw_fusion_actions(
        self, section: dict | None, model: Any, state: FormState, width: float
    ) -> None:
        """The actions in two wrapped rows: run (Run, Estimate, Demo, Stop), then files and help."""
        controller = getattr(self, "controller", None)
        running = bool(controller and controller.running)
        im.spacing()
        pressed = button_row([
            {"label": icon_label("🚀", "Run (Fuse)"), "key": "toolAction_run", "enabled": not running,
             "keys": ("fusion_actions",), "colours": (ACCENT_GREEN, (56, 180, 77, 255), (36, 140, 57, 255)),
             "tip": "Fuse burst fragments that likely belong to the same molecule using the P(same) threshold."},
            {"label": icon_label("🔄", "Estimate"), "key": "toolAction_refresh", "enabled": not running,
             "tip": "Estimate the P(same) curve and thresholds from the loaded bursts without fusing."},
            *([{"label": icon_label("🧪", "Demo"), "key": "load_demo", "enabled": not running, "keys": ("Load demo",),
                "tip": "Load a demo dataset to try the fusion analysis."}] if self.on_demo is not None else []),
            {"label": "Stop fusion", "key": "Stop", "enabled": running,
             "tip": "Cancel the estimate before writing; an output write already started finishes consistently."
             if running else "Nothing is running; a fusion in progress can be stopped here."},
        ], remember=self.remember)
        if pressed in ("toolAction_run", "toolAction_refresh", "load_demo"):
            self.track(pressed)
            if pressed != "load_demo":
                self.track("fusion_actions")
            else:
                self.track("Load demo")
            try:
                if pressed == "toolAction_run":
                    controller.run() if controller else self.model.fuse()
                elif pressed == "toolAction_refresh":
                    controller.estimate() if controller else self.model.analyze()
                else:
                    self.on_demo()
            except Exception:
                pass
        elif pressed == "Stop" and controller is not None:
            controller.stop()
        im.begin_disabled(running)
        files = button_row([
            {"label": "Load settings", "key": "load", "tip": "Load a saved fusion parameter JSON file."},
            {"label": "Save settings", "key": "save", "tip": "Save current fusion parameters as JSON."},
            {"label": "Export fusion report", "key": "export",
             "tip": "Export before/after statistics and the output folder path."},
        ], remember=self.remember)
        im.end_disabled()
        if files and controller is not None:
            controller.browse(files)
        pressed = button_row([
            {"label": icon_label("📖", "Guide"), "key": "guide", "tip": "Start a step-by-step guided tour of this tool."},
            {"label": icon_label("❓", "Help"), "key": "help", "tip": "Open the help window with reference documentation."},
        ], remember=self.remember)
        if pressed == "guide":
            self.track("guide")
            self.start_guide()
        elif pressed == "help":
            self.track("help")
            self.show_help()
        if controller is not None:
            controller.draw_status()

    def draw(self, w: float, h: float) -> None:
        self.docks.draw((0.0, 0.0, float(w), float(h)))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, w, h))

        if self.tour.active:
            self.tour.draw(w, h)

    def _draw_all_plots(self, w: float, h: float) -> None:
        """Draw 5 plots in a 2-column grid."""
        half_w = max((w - 8.0) / 2.0, 180.0)
        row_h = max((h - 16.0) / 3.0, 160.0)

        # Row 1: P_same spans full width
        self._plot_p_same(w, row_h)

        # Row 2: Proximity ratio and Photons
        self._plot_proximity(half_w, row_h)
        im.same_line()
        self._plot_photons(half_w, row_h)

        # Row 3: Duration and Fragments
        self._plot_duration(half_w, row_h)
        im.same_line()
        self._plot_fragments(half_w, row_h)

    def _plot_p_same(self, w: float, h: float) -> None:
        """Plot same-molecule probability curve."""
        origin = im.get_cursor_screen_pos()
        series_list = self.model.p_same_series()
        if implot.begin_plot("Same-molecule probability##p_same", (w, h)):
            implot.setup_axes("Lag between bursts (ms)", "P(same molecule)")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 1.05)
            for idx, s in enumerate(series_list):
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                width = float(s.get("width", 2.0))
                style = str(s.get("style", "solid"))
                dash = (6.0, 4.0) if style == "dash" else ((2.0, 2.0) if style == "dot" else None)
                implot.set_next_line_style(col, width, dash=dash)
                implot.plot_line(s.get("name", f"Curve {idx}"), s["x"], s["y"])
            implot.end_plot()
        self.remember("Same-molecule probability", (origin[0], origin[1], w, h))

    def _plot_proximity(self, w: float, h: float) -> None:
        """Plot proximity ratio before and after fusion."""
        origin = im.get_cursor_screen_pos()
        series_list = self.model.proximity_series()
        if implot.begin_plot("Proximity ratio##pr", (w, h)):
            implot.setup_axes("Proximity ratio", "probability density")
            implot.setup_axis_limits(implot.AXIS_X1, -0.1, 1.1)
            for idx, s in enumerate(series_list):
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                implot.set_next_line_style(col, float(s.get("width", 2.0)))
                implot.plot_line(s.get("name", f"PR {idx}"), s["x"], s["y"])
            implot.end_plot()
        self.remember("Proximity ratio", (origin[0], origin[1], w, h))

    def _plot_photons(self, w: float, h: float) -> None:
        """Plot photons per burst before and after fusion."""
        origin = im.get_cursor_screen_pos()
        series_list = self.model.photon_series()
        if implot.begin_plot("Photons per burst##photons", (w, h)):
            implot.setup_axes("log10 photons per burst", "probability density")
            for idx, s in enumerate(series_list):
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                implot.set_next_line_style(col, float(s.get("width", 2.0)))
                implot.plot_line(s.get("name", f"Photons {idx}"), s["x"], s["y"])
            implot.end_plot()
        self.remember("Photons per burst", (origin[0], origin[1], w, h))

    def _plot_duration(self, w: float, h: float) -> None:
        """Plot burst duration before and after fusion."""
        origin = im.get_cursor_screen_pos()
        series_list = self.model.duration_series()
        if implot.begin_plot("Burst duration##duration", (w, h)):
            implot.setup_axes("log10 duration (ms)", "probability density")
            for idx, s in enumerate(series_list):
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                implot.set_next_line_style(col, float(s.get("width", 2.0)))
                implot.plot_line(s.get("name", f"Duration {idx}"), s["x"], s["y"])
            implot.end_plot()
        self.remember("Burst duration", (origin[0], origin[1], w, h))

    def _plot_fragments(self, w: float, h: float) -> None:
        """Plot fragments per fused burst."""
        origin = im.get_cursor_screen_pos()
        series_list = self.model.group_size_series()
        if implot.begin_plot("Fragments per fused burst##fragments", (w, h)):
            implot.setup_axes("original bursts in one fused burst", "fused bursts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            # Bars stand on zero, which a log axis cannot show: its auto-fit spanned the bar
            # tops only, so the smallest count sat on the floor and the largest ran off the top.
            tops = [float(np.max(s["y"])) for s in series_list if len(s.get("y", [])) > 0]
            sizes = sorted({int(x) for s in series_list for x in np.asarray(s.get("x", []), float)})
            if tops:
                # Applied whenever the bars change (ALWAYS once), held otherwise so a zoom stays:
                # a first ONCE request after the plot was drawn empty is not applied at all.
                request = (0.8, max(tops) * 1.5)
                changed = request != getattr(self, "_fragments_request", None)
                self._fragments_request = request
                implot.setup_axis_limits(implot.AXIS_Y1, *request,
                                         implot.COND_ALWAYS if changed else implot.COND_ONCE)
            if sizes:  # whole fragment counts, not 1.5 fragments
                implot.setup_axis_ticks(implot.AXIS_X1, np.asarray(sizes, float), labels=[str(n) for n in sizes])
            for idx, s in enumerate(series_list):
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                implot.set_next_fill_style(col)
                xs = s["x"]
                ys = s["y"]
                if len(xs) > 0 and len(ys) > 0:
                    implot.plot_bars(s.get("name", "fragments"), xs, ys=ys, bar_size=0.6)
            implot.end_plot()
        self.remember("Fragments per fused burst", (origin[0], origin[1], w, h))


class BurstFusionApp(ImApp):
    """The EMTK App for Burst Fusion."""

    def __init__(
        self,
        model: FusionViewModel | None = None,
        on_demo: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        from .controller import FusionController

        model = model if model is not None else FusionViewModel()
        self.controller = FusionController(model)
        on_demo = on_demo or self.controller.demo
        self.fusion_gui = BurstFusionGui(
            model=model, on_demo=on_demo, on_guide=on_guide, on_help=on_help
        )
        self.model = self.fusion_gui.model
        self.item_rects = self.fusion_gui.item_rects
        self.fusion_gui.remember = self.remember
        self.fusion_gui.controller = self.controller
        super().__init__(gui=self._render)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.fusion_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.fusion_gui.show_help()

    def _render(self) -> None:
        self.controller.poll()
        if self.controller.running:  # look again in 0.1 s while a worker runs
            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.fusion_gui.draw(float(w), float(h))
        self.controller.draw_dialogs((0, 0, w, h))

    def set_folder(self, folder):
        self.model.set_folder(str(folder))

    def set_channel_settings(self, settings):
        self.model.detectors = dict(settings.get("detectors") or {})
        self.model.windows = dict(settings.get("windows") or {})
        import json

        self.controller.channel_text = json.dumps(
            {"detectors": self.model.detectors, "windows": self.model.windows}, indent=2
        )

    @property
    def output_folder(self):
        return self.model.written_folder

    def process_bursts(self):
        if self.controller.running:
            raise RuntimeError("Fusion is already running.")
        return self.model.fuse()

    def close(self):
        self.controller.close()

    def on_paths_dropped(self, paths):
        self.controller.on_paths_dropped(paths)

    def files_dropped(self, paths) -> bool:
        """A host's file drop (Qt, the desktop window, a page): the same as ``on_paths_dropped``.

        Without this name only the Qt host reached the controller: the desktop and web hosts deliver
        ``files_dropped`` / ``on_files_dropped`` and found nothing to call.
        """
        paths = list(paths)
        self.controller.on_paths_dropped(paths)
        return bool(paths)


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return BurstFusionApp(**kwargs)
