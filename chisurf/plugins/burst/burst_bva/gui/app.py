"""The Burst Variance Analysis (BVA) tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstBvaApp`) over
:class:`~.view_model.BvaViewModel`:
- Left pane: folder input, actions (Run, Restart, Stop, Folder), tabbed settings
  (BVA Settings and Channel Definitions), and status.
- Right pane: BVA 2D plot with static line, scatter bursts, and profile mean ± std error.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

from typing import Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.im_core import Col

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
    ) -> None:
        self.model = model if model is not None else BvaViewModel()
        self.on_run = on_run
        self.on_restart = on_restart
        self.on_stop = on_stop
        self.on_browse = on_browse
        self.on_clear = on_clear

        self.selected_settings_tab = "BVA Settings"
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        self.model.add_observer(self._on_model_event)

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

    def draw(self, w: float, h: float) -> None:
        """Draw the BVA GUI into (w, h) display pixels."""
        left_w = min(max(340.0, w * 0.34), 440.0)
        right_w = max(w - left_w - 12.0, 200.0)

        # ── Left pane: Controls & Settings ──────────────────────────────
        if im.begin("BVA Controls", (4.0, 4.0, left_w, h - 8.0)):
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
            self.remember("controls", (4.0, 4.0, left_w, h - 8.0))

        # ── Right pane: Plot ─────────────────────────────────────────────
        plots_x = left_w + 8.0
        if im.begin("BVA Plot Window", (plots_x, 4.0, right_w, h - 8.0)):
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
        im.text("Min window length (s):")
        changed, wl = im.drag_float(
            "##window_length", self.model.window_length, 0.001, 0.0001, 10.0, "%.4f s"
        )
        if changed:
            self.model.window_length = max(0.0001, float(wl))
            self.model.notify("param")

        # Photons per slice
        im.text("Photons per slice:")
        changed, pps = im.drag_float(
            "##photons_per_slice", float(self.model.photons_per_slice), 1.0, 1.0, 500.0, "%.0f"
        )
        if changed:
            self.model.photons_per_slice = max(1, int(round(pps)))
            self.model.notify("param")

        im.spacing()
        im.text_colored((200, 210, 230, 255), "Display Options")

        # Bins
        im.text("Bins X:")
        changed, bx = im.drag_float("##bins_x", float(self.model.bins_x), 1.0, 10.0, 500.0, "%.0f")
        if changed:
            self.model.bins_x = max(10, int(round(bx)))
            self.model.notify("bins")

        im.text("Bins Y:")
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

            implot.end_plot()

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
    ) -> None:
        self.bva_gui = BurstBvaGui(
            model=model,
            on_run=on_run,
            on_restart=on_restart,
            on_stop=on_stop,
            on_browse=on_browse,
            on_clear=on_clear,
        )
        self.model = self.bva_gui.model
        super().__init__(gui=self._render, continuous=False)

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.bva_gui.draw(float(w), float(h))
