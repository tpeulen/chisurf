"""The FRET-2CDE / ALEX-2CDE tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstTwoCdeApp`) over
:class:`~.view_model.TwoCdeViewModel`:
- Left pane: folder input, actions (Run, Restart, Stop, Browse), and settings
  (Variant, Kernel, tau, donor channels, acceptor channels, file type).
- Right pane: 2CDE scatter plot (FRET efficiency vs 2CDE) or 1D histogram.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.im_core import Col

from .view_model import TwoCdeViewModel

__all__ = ["BurstTwoCdeApp", "BurstTwoCdeGui", "WINDOW_BG"]

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)


class BurstTwoCdeGui:
    """The immediate-mode GUI logic and rendering for 2CDE."""

    def __init__(
        self,
        model: TwoCdeViewModel | None = None,
        on_run: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else TwoCdeViewModel()
        self.on_run = on_run
        self.on_restart = on_restart
        self.on_stop = on_stop
        self.on_browse = on_browse

        self.threshold_y: float = 10.0
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
        """Draw the 2CDE GUI into (w, h) display pixels."""
        im.dock_space_over_viewport(1)

        left_w = min(max(320.0, w * 0.32), 420.0)
        right_w = max(w - left_w - 12.0, 200.0)

        # ── Left pane: Controls (Dockable) ───────────────────────────────
        im.set_next_window_pos((4.0, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((left_w, h - 8.0), im.Cond.FIRST_USE_EVER)
        if im.begin("2CDE Controls"):
            self._draw_action_buttons()
            im.spacing()
            self._draw_folder_input(left_w - 16.0)
            im.spacing()
            self._draw_settings(left_w - 16.0)
            im.spacing()
            self._draw_status()
            im.end()
            self.remember("controls", (4.0, 4.0, left_w, h - 8.0))

        # ── Right pane: Plot (Dockable) ──────────────────────────────────
        plots_x = left_w + 8.0
        im.set_next_window_pos((plots_x, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((right_w, h - 8.0), im.Cond.FIRST_USE_EVER)
        if im.begin("2CDE Plot"):
            avail_w, avail_h = im.get_content_region_avail()
            avail_h = max(avail_h, 250.0)
            self._draw_plot(avail_w, avail_h)
            im.end()
            self.remember("twocde_plot", (plots_x, 4.0, right_w, h - 8.0))

    def _draw_action_buttons(self) -> None:
        """Draw Run, Restart, Stop, and Browse actions."""
        locked = self.model.is_locked or self.model.is_running

        # Run button
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🚀 Run"):
            self.track("toolAction_run")
            if not locked and callable(self.on_run):
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
        im.text("Analysis folder:")
        changed, text = im.input_text("##folder_path", self.model.folder, hint="Burst folder …")
        if changed:
            self.model.set_folder(text)

    def _draw_settings(self, width: float) -> None:
        """2CDE analysis parameters."""
        im.separator()
        im.text_colored((200, 210, 230, 255), "2CDE Parameters")

        # Variant
        im.text("Variant:")
        if im.begin_combo("##twocde_variant", self.model.variant):
            for var in ("fret", "alex"):
                if im.selectable(var, var == self.model.variant):
                    self.model.variant = var
                    self.model.notify("variant")
            im.end_combo()
        self.remember("twocde_variant")

        # Kernel
        im.text("Kernel:")
        if im.begin_combo("##twocde_kernel", self.model.kernel):
            for k in ("laplace", "gaussian"):
                if im.selectable(k, k == self.model.kernel):
                    self.model.kernel = k
                    self.model.notify("kernel")
            im.end_combo()
        self.remember("twocde_kernel")

        # tau
        im.text("τ (window):")
        changed, tau = im.drag_float(
            "##twocde_tau", self.model.tau_us, 1.0, 1.0, 100000.0, "%.1f µs"
        )
        if changed:
            self.model.tau_us = max(1.0, float(tau))
            self.model.notify("tau")
        self.remember("twocde_tau")

        # Donor channels
        im.text("Donor routing channels:")
        changed, donor = im.input_text("##twocde_donor", self.model.donor_channels_text, hint="0,8")
        if changed:
            self.model.donor_channels_text = donor
            self.model.notify("donor")
        self.remember("twocde_donor")

        # Acceptor channels
        im.text("Acceptor routing channels:")
        changed, acc = im.input_text(
            "##twocde_acceptor", self.model.acceptor_channels_text, hint="1,9"
        )
        if changed:
            self.model.acceptor_channels_text = acc
            self.model.notify("acceptor")
        self.remember("twocde_acceptor")

        # File type
        im.text("File type:")
        changed, ft = im.input_text("##twocde_file_type", self.model.file_type, hint="SPC-130")
        if changed:
            self.model.file_type = ft
            self.model.notify("file_type")
        self.remember("twocde_file_type")

    def _draw_status(self) -> None:
        """Status readout."""
        if self.model.status_text:
            im.separator()
            im.text_wrapped(self.model.status_text)

    def _draw_plot(self, w: float, h: float) -> None:
        """Plot the computed 2CDE results."""
        origin = im.get_cursor_screen_pos()
        plot_data = self.model.get_plot_data()

        if plot_data is not None:
            if plot_data["kind"] == "scatter":
                if implot.begin_plot("FRET-2CDE / ALEX-2CDE##twocde_plot", (w, h)):
                    implot.setup_axes(plot_data["xlabel"], plot_data["ylabel"])
                    implot.setup_axis_limits(implot.AXIS_X1, -0.05, 1.05)

                    # Interactive draggable threshold line (default 10.0)
                    r_thresh = implot.drag_line_y(
                        0, float(self.threshold_y), col=(240, 140, 30, 220), thickness=2.0
                    )
                    if r_thresh.modified:
                        self.threshold_y = float(r_thresh.value)
                    implot.tag_y(
                        self.threshold_y,
                        (240, 140, 30, 255),
                        f"Threshold: {self.threshold_y:.1f}",
                    )

                    # Scatter markers
                    implot.set_next_marker_style(
                        implot.MARKER_CIRCLE, 3.5, fill=(31, 119, 180, 140)
                    )
                    implot.plot_scatter("Bursts", plot_data["x"], plot_data["y"])
                    implot.end_plot()
            elif plot_data["kind"] == "hist":
                if implot.begin_plot(f"{plot_data['ylabel']}##twocde_plot", (w, h)):
                    implot.setup_axes(plot_data["xlabel"], plot_data["ylabel"])
                    implot.set_next_line_style((31, 119, 180, 255), 2.0)
                    implot.plot_line("Distribution", plot_data["x"], plot_data["y"])
                    implot.end_plot()
        else:
            if implot.begin_plot("FRET-2CDE / ALEX-2CDE##twocde_plot", (w, h)):
                implot.setup_axes("FRET efficiency (proximity ratio)", "2CDE")
                implot.setup_axis_limits(implot.AXIS_X1, -0.05, 1.05)
                implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 50.0)
                implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                    if "max" in data:
                        self.threshold_y = float(data["max"]) * 20.0
                except Exception:
                    pass
            im.end_drag_drop_target()

        self.remember("twocde_plot", (origin[0], origin[1], w, h))


class BurstTwoCdeApp(ImApp):
    """The EMTK App for 2CDE."""

    def __init__(
        self,
        model: TwoCdeViewModel | None = None,
        on_run: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
    ) -> None:
        self.two_cde_gui = BurstTwoCdeGui(
            model=model,
            on_run=on_run,
            on_restart=on_restart,
            on_stop=on_stop,
            on_browse=on_browse,
        )
        self.model = self.two_cde_gui.model
        super().__init__(gui=self._render, continuous=False)

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.two_cde_gui.draw(float(w), float(h))
