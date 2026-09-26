"""The Burst Variance Analysis (BVA) tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstBvaApp`) over
:class:`~.view_model.BvaViewModel`:
- Left pane: folder input, actions (Run, Restart, Stop, Folder), tabbed settings
  (BVA Settings and Channel Definitions), and status.
- Right pane: BVA 2D plot with static line, scatter bursts, and profile mean ± std error.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

import json
from pathlib import Path
from typing import Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.im_core import Col

from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

from .view_model import BvaViewModel

__all__ = ["BurstBvaApp", "BurstBvaGui", "WINDOW_BG"]

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)


class BurstBvaGui:
    """The immediate-mode GUI logic and rendering for BVA."""

    def __init__(
        self,
        model: BvaViewModel | None = None,
        on_run: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else BvaViewModel()
        self.on_run = on_run
        self.on_restart = on_restart
        self.on_stop = on_stop
        self.on_browse = on_browse
        self.on_clear = on_clear
        self.on_guide = on_guide
        self.on_help = on_help

        self.region_rect: list[float] = [0.2, 0.05, 0.8, 0.35]
        self.selected_settings_tab = "BVA Settings"
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        self.model.add_observer(self._on_model_event)

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Variance Analysis (BVA) — Help & Reference",
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

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        """Draw the BVA GUI into (w, h) display pixels."""
        im.dock_space_over_viewport(1)

        vp = im.get_main_viewport()
        vw, vh = vp.size
        width = float(w or vw or 800.0)
        height = float(h or vh or 600.0)

        left_w = min(max(340.0, width * 0.34), 440.0)
        right_w = max(width - left_w - 12.0, 200.0)

        # ── Left pane: Controls & Settings (Dockable) ───────────────────
        im.set_next_window_pos((4.0, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((left_w, height - 8.0), im.Cond.ALWAYS)
        if im.begin("BVA Controls"):
            self._draw_action_buttons()
            im.spacing()
            self._draw_folder_input(left_w - 16.0)
            im.spacing()

            # Tab bar for settings
            if im.begin_tab_bar("bva_settings_tabs"):
                if im.begin_tab_item("BVA Settings"):
                    self.selected_settings_tab = "BVA Settings"
                    self.remember("BVA Settings")
                    self._draw_bva_parameters()
                    im.end_tab_item()
                else:
                    self.remember("BVA Settings")

                if im.begin_tab_item("Channel Definitions"):
                    self.selected_settings_tab = "Channel Definitions"
                    self.remember("Channel Definitions")
                    self._draw_channel_definitions()
                    im.end_tab_item()
                else:
                    self.remember("Channel Definitions")
                im.end_tab_bar()

            im.spacing()
            self._draw_status()
            im.end()
            self.remember("controls", (4.0, 4.0, left_w, height - 8.0))

        # ── Right pane: Plot (Dockable) ──────────────────────────────────
        plots_x = left_w + 8.0
        im.set_next_window_pos((plots_x, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((right_w, height - 8.0), im.Cond.ALWAYS)
        if im.begin("BVA Plot Window"):
            if im.begin_tab_bar("bva_plot_tabs"):
                if im.begin_tab_item("Plot"):
                    self.remember("Plot")
                    avail_w, avail_h = im.get_content_region_avail()
                    avail_h = max(avail_h, 250.0)
                    self._draw_plot(avail_w, avail_h)
                    im.end_tab_item()
                else:
                    self.remember("Plot")
                im.end_tab_bar()
            im.end()
            self.remember("PlotWindow", (plots_x, 4.0, right_w, h - 8.0))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        if self.tour.active:
            self.tour.draw(width, height)

    def _draw_action_buttons(self) -> None:
        """Draw Run, Restart, Stop, and Browse actions."""
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🚀 Run"):
            self.track("toolAction_run")
            if not self.model.is_running and callable(self.on_run):
                self.on_run()
        self.remember("run")
        self.remember("toolAction_run")
        im.pop_style_color(3)

        im.same_line()
        if im.button("🔄 Restart"):
            self.track("toolAction_restart")
            if not self.model.is_running and callable(self.on_restart):
                self.on_restart()
        self.remember("restart")
        self.remember("toolAction_restart")

        im.same_line()
        if self.model.is_running:
            im.push_style_color(Col.BUTTON, ACCENT_RED)
            im.push_style_color(Col.BUTTON_HOVERED, (234, 59, 60, 255))
            im.push_style_color(Col.BUTTON_ACTIVE, (180, 20, 20, 255))
        if im.button("⏹ Stop"):
            self.track("toolAction_stop")
            if self.model.is_running and callable(self.on_stop):
                self.on_stop()
        self.remember("stop")
        self.remember("toolAction_stop")
        if self.model.is_running:
            im.pop_style_color(3)

        im.same_line()
        if im.button("📁 Folder"):
            self.track("folder")
            if callable(self.on_browse):
                self.on_browse()
        self.remember("folder")

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

    def _draw_folder_input(self, width: float) -> None:
        """Folder path input."""
        im.text("Burst folder:")
        folder_str = str(self.model.analysis_folder or "")
        changed, text = im.input_text("##folder_path", folder_str, hint="Burst analysis folder …")
        if changed:
            self.model.set_folder(text)

    def _draw_bva_parameters(self) -> None:
        """Draw BVA parameter controls."""
        im.spacing()
        im.text_colored((200, 210, 230, 255), "Analysis Parameters")

        # Window length
        col_x = 175.0
        im.align_text_to_frame_padding()
        im.text("Min window length (s):")
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, wl = im.drag_float(
            "##window_length", self.model.window_length, 0.001, 0.0001, 10.0, "%.4f s"
        )
        if changed:
            self.model.window_length = max(0.0001, float(wl))
            self.model.notify("param")

        # Photons per slice
        im.align_text_to_frame_padding()
        im.text("Photons per slice:")
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, pps = im.drag_float(
            "##photons_per_slice", float(self.model.photons_per_slice), 1.0, 1.0, 500.0, "%.0f"
        )
        if changed:
            self.model.photons_per_slice = max(1, int(round(pps)))
            self.model.notify("param")

        im.spacing()
        im.text_colored((200, 210, 230, 255), "Display Options")

        # Bins
        im.align_text_to_frame_padding()
        im.text("Bins X:")
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, bx = im.drag_float("##bins_x", float(self.model.bins_x), 1.0, 10.0, 500.0, "%.0f")
        if changed:
            self.model.bins_x = max(10, int(round(bx)))
            self.model.notify("bins")

        im.align_text_to_frame_padding()
        im.text("Bins Y:")
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, by = im.drag_float("##bins_y", float(self.model.bins_y), 1.0, 10.0, 500.0, "%.0f")
        if changed:
            self.model.bins_y = max(10, int(round(by)))
            self.model.notify("bins")

        # Toggles
        if im.checkbox("Show static line", self.model.show_static_line)[0]:
            self.model.show_static_line = not self.model.show_static_line
            self.model.notify("display")

        if im.checkbox("Auto update", self.model.auto_update)[0]:
            self.model.auto_update = not self.model.auto_update
            self.model.notify("display")

    def _draw_channel_definitions(self) -> None:
        """Draw detector channel controls."""
        im.spacing()
        im.text_colored((200, 210, 230, 255), "Detector Routing")

        im.text("Donor routing channels:")
        changed, donor = im.input_text("##donor_ch", self.model.donor_channels_text, hint="0,8")
        if changed:
            self.model.donor_channels_text = donor
            self.model.notify("channel")

        im.text("Acceptor routing channels:")
        changed, acc = im.input_text("##acceptor_ch", self.model.acceptor_channels_text, hint="1,9")
        if changed:
            self.model.acceptor_channels_text = acc
            self.model.notify("channel")

        im.text("File type:")
        changed, ft = im.input_text("##file_type", self.model.file_type, hint="SPC-130")
        if changed:
            self.model.file_type = ft
            self.model.notify("file_type")

    def _draw_status(self) -> None:
        """Status readout."""
        if self.model.status_text:
            im.separator()
            im.text_wrapped(self.model.status_text)

    def _draw_plot(self, w: float, h: float) -> None:
        """Plot the computed BVA results."""
        origin = im.get_cursor_screen_pos()
        plot_data = self.model.get_plot_data() or {}

        if implot.begin_plot("Burst Variance Analysis##bva_plot", (w, h)):
            implot.setup_axes("Mean Proximity Ratio", "Std Proximity Ratio")
            implot.setup_axis_limits(implot.AXIS_X1, -0.05, 1.05)
            implot.setup_axis_limits(implot.AXIS_Y1, -0.01, 0.44)

            # Static line
            if self.model.show_static_line and "static_x" in plot_data:
                implot.set_next_line_style((255, 107, 107, 255), 2.5)
                implot.plot_line("Static line", plot_data["static_x"], plot_data["static_y"])

            # Data
            if plot_data.get("has_data"):
                # Scatter of bursts
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 3.0, fill=(31, 119, 180, 110))
                implot.plot_scatter("Bursts", plot_data["scatter_x"], plot_data["scatter_y"])

                # Profile mean
                prof_x = plot_data.get("profile_x")
                prof_y = plot_data.get("profile_mean")
                prof_sd = plot_data.get("profile_sd")
                if prof_x is not None and len(prof_x) > 0:
                    implot.set_next_line_style((0, 255, 255, 255), 2.0)
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, fill=(0, 255, 255, 220))
                    implot.plot_line("Profile mean", prof_x, prof_y)

                    if prof_sd is not None and len(prof_sd) > 0:
                        implot.set_next_error_bar_style((0, 255, 255, 160))
                        implot.plot_error_bars("##profile_err", prof_x, prof_y, prof_sd)

            # Interactive draggable region
            r_res = implot.drag_rect(
                0,
                float(self.region_rect[0]),
                float(self.region_rect[1]),
                float(self.region_rect[2]),
                float(self.region_rect[3]),
                col=(46, 117, 182, 60),
            )
            if r_res.modified:
                self.region_rect = [
                    min(r_res.x_min, r_res.x_max),
                    min(r_res.y_min, r_res.y_max),
                    max(r_res.x_min, r_res.x_max),
                    max(r_res.y_min, r_res.y_max),
                ]
            implot.tag_x(self.region_rect[0], (90, 160, 240, 255), f"E: {self.region_rect[0]:.2f}")
            implot.tag_x(self.region_rect[2], (90, 160, 240, 255), f"E: {self.region_rect[2]:.2f}")
            implot.tag_y(
                self.region_rect[3], (90, 160, 240, 255), f"Std: {self.region_rect[3]:.2f}"
            )

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                    if "min" in data and "max" in data:
                        self.region_rect[0] = float(data["min"])
                        self.region_rect[2] = float(data["max"])
                except Exception:
                    pass
            im.end_drag_drop_target()

        self.remember("bva_plot", (origin[0], origin[1], w, h))


class BurstBvaApp(ImApp):
    """The EMTK App for Burst Variance Analysis (BVA)."""

    def __init__(
        self,
        model: BvaViewModel | None = None,
        on_run: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.bva_gui = BurstBvaGui(
            model=model,
            on_run=on_run,
            on_restart=on_restart,
            on_stop=on_stop,
            on_browse=on_browse,
            on_clear=on_clear,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.bva_gui.model
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.bva_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.bva_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.bva_gui.draw(float(w), float(h))
