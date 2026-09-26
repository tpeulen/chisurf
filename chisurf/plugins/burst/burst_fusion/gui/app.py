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
from emtk.view_form import FormState, draw_sections, find_section
from emtk.widgets.view_spec import load_view_spec

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


class BurstFusionGui:
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

        # Register custom sections
        self.form_state.custom["fusion_actions"] = self._draw_fusion_actions

        self.selected_tab = "All"
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

        help_resource = pathlib.Path(__file__).parent / "help.md"
        guide_resource = pathlib.Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Fusion — Help & Reference",
            resource=help_resource,
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.model,
        )

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def _on_model_event(self, event: str) -> None:
        pass

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        """Store the item's screen rectangle for tour targeting."""
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def _draw_fusion_actions(
        self, section: dict, model: Any, state: FormState, width: float
    ) -> None:
        """Custom handler for fusion_actions in the form."""
        from emtk.im_core import Col

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🚀 Run (Fuse)"):
            self.track("toolAction_run")
            try:
                self.model.fuse()
            except Exception:
                pass
        self.remember("toolAction_run")
        self.remember("fusion_actions")
        im.pop_style_color(3)

        im.same_line()
        if im.button("🔄 Estimate"):
            self.track("toolAction_refresh")
            try:
                self.model.analyze()
            except Exception:
                pass
        self.remember("toolAction_refresh")

        im.same_line()
        if self.on_demo is not None:
            if im.button("🧪 Demo"):
                self.track("load_demo")
                try:
                    self.on_demo()
                except Exception:
                    pass
            self.remember("load_demo")
            im.same_line()

        if im.button("📖 Guide"):
            self.track("guide")
            self.start_guide()
        self.remember("guide")

        im.same_line()
        if im.button("❓ Help"):
            self.track("help")
            self.show_help()
        self.remember("help")

    def draw(self, w: float, h: float) -> None:
        """Draw the fusion GUI into (w, h) display pixels."""
        left_w = min(max(340.0, w * 0.32), 440.0)
        right_w = max(w - left_w - 12.0, 200.0)

        # ── Left pane: Controls ──────────────────────────────────────────
        if im.begin("Fusion Controls", (4.0, 4.0, left_w, h - 8.0)):
            if self.fusion_panel and self.fusion_panel.get("sections"):
                draw_sections(
                    self.fusion_panel.get("sections", []),
                    self.model,
                    self.form_state,
                    n_col=1,
                    titles=True,
                )
            im.end()
            self.remember("Fusion", (4.0, 4.0, left_w, h - 8.0))

        # ── Right pane: Plots ────────────────────────────────────────────
        plots_x = left_w + 8.0
        if im.begin("Fusion Plots", (plots_x, 4.0, right_w, h - 8.0)):
            if im.begin_tab_bar("fusion_plot_tabs"):
                tabs = [
                    ("All", "All Plots"),
                    ("P_same", "Same-molecule P(same)"),
                    ("PR", "Proximity Ratio"),
                    ("Photons", "Photons"),
                    ("Duration", "Duration"),
                    ("Fragments", "Fragments"),
                ]
                for key, label in tabs:
                    if im.begin_tab_item(label):
                        self.selected_tab = key
                        im.end_tab_item()
                im.end_tab_bar()

            avail_w, avail_h = im.get_content_region_avail()
            avail_h = max(avail_h, 300.0)

            if self.selected_tab == "All":
                self._draw_all_plots(avail_w, avail_h)
            elif self.selected_tab == "P_same":
                self._plot_p_same(avail_w, avail_h)
            elif self.selected_tab == "PR":
                self._plot_proximity(avail_w, avail_h)
            elif self.selected_tab == "Photons":
                self._plot_photons(avail_w, avail_h)
            elif self.selected_tab == "Duration":
                self._plot_duration(avail_w, avail_h)
            elif self.selected_tab == "Fragments":
                self._plot_fragments(avail_w, avail_h)

            im.end()
            self.remember("results", (plots_x, 4.0, right_w, h - 8.0))

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
        self.fusion_gui = BurstFusionGui(
            model=model, on_demo=on_demo, on_guide=on_guide, on_help=on_help
        )
        self.model = self.fusion_gui.model
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.fusion_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.fusion_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.fusion_gui.draw(float(w), float(h))
