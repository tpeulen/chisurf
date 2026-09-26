"""The Burst Background Estimation tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstBackgroundApp`) over
:class:`~.view_model.BackgroundViewModel`:
- Docking & Draggable Windows: All panels (Parameters, Inter-photon Time,
  Background Rate, Results Table) are dockable, draggable, resizable and floatable.
- Interactive Region Dropping & Dragging:
  - On the Inter-photon Time distribution plot, an interactive shaded fit-window region
    (:func:`implot.drag_rect`) and axis tags (:func:`implot.tag_x`) allow dragging
    `fit_from_ms` and `fit_to_ms` directly on the plot.
  - Drop targets allow dropping region presets directly onto the plot.
- Rate Bars & Results: Per-detector background rate bar chart with custom colors and
  results summary table.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp

from ..view_model import BackgroundViewModel

__all__ = ["BurstBackgroundApp", "BurstBackgroundGui", "WINDOW_BG"]

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)
REGION_FILL = (255, 255, 255, 30)
REGION_BORDER = (200, 210, 230, 255)


def _hex_to_rgba(col: Any, alpha: int = 255) -> tuple[int, int, int, int]:
    if isinstance(col, (tuple, list)):
        return int(col[0]), int(col[1]), int(col[2]), int(col[3] if len(col) > 3 else alpha)
    c = str(col).lstrip("#")
    if len(c) == 6:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha
    return (100, 150, 240, alpha)


class BurstBackgroundGui:
    """Immediate-mode GUI logic and rendering for Burst Background Estimation."""

    def __init__(
        self,
        model: BackgroundViewModel | None = None,
        on_estimate: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else BackgroundViewModel()
        self.on_estimate = on_estimate
        self.on_guide = on_guide
        self.on_help = on_help
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None
        self._dragging_window = False

        from pathlib import Path

        from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Background Estimation — Help & Reference",
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

        self.model.add_observer(self._on_model_event)

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

    def draw(self, w: float, h: float) -> None:
        """Draw the dockable Burst Background tool into (w, h) display pixels."""
        im.dock_space_over_viewport(1)

        left_w = min(max(280.0, w * 0.28), 340.0)
        right_w = max(w - left_w - 16.0, 320.0)

        # ── Window 1: Parameters & Actions ──────────────────────────────
        im.set_next_window_pos((4.0, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((left_w, h - 8.0), im.Cond.FIRST_USE_EVER)
        if im.begin("Fit Parameters"):
            self._draw_parameters()
            im.end()

        # ── Window 2: Inter-photon Time Distribution Plot ───────────────
        im.set_next_window_pos((8.0 + left_w, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((right_w, (h - 12.0) * 0.60), im.Cond.FIRST_USE_EVER)
        if im.begin("Inter-photon Time Distribution"):
            self._draw_iht_plot()
            im.end()

        # ── Window 3: Background Rate Bars & Results ─────────────────────
        im.set_next_window_pos((8.0 + left_w, 8.0 + (h - 12.0) * 0.60), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((right_w, (h - 12.0) * 0.40), im.Cond.FIRST_USE_EVER)
        if im.begin("Rates & Results"):
            self._draw_rates_and_results()
            im.end()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))

        if self.tour.active:
            self.tour.draw(float(w), float(h))

    def _draw_parameters(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        im.text_colored(ACCENT_BLUE, "Fit Settings")

        # Fit from / to (ms)
        im.text("Fit from (ms):")
        im.set_next_item_width(avail_w)
        ch_lo, new_lo = im.drag_float(
            "##fit_from", float(self.model.fit_from_ms), 0.01, 0.001, 1000.0, "%.3f"
        )
        if ch_lo and new_lo > 0:
            self.model.fit_from_ms = float(new_lo)
            self.model.update()

        im.text("Fit to (ms):")
        im.set_next_item_width(avail_w)
        ch_hi, new_hi = im.drag_float(
            "##fit_to", float(self.model.fit_to_ms), 0.01, 0.001, 1000.0, "%.3f"
        )
        if ch_hi and new_hi > self.model.fit_from_ms:
            self.model.fit_to_ms = float(new_hi)
            self.model.update()

        im.text("Bin width (ms):")
        im.set_next_item_width(avail_w)
        ch_bin, new_bin = im.drag_float(
            "##bin_w", float(self.model.binsize_ms), 0.01, 0.001, 10.0, "%.3f"
        )
        if ch_bin and new_bin > 0:
            self.model.binsize_ms = float(new_bin)
            self.model.update()

        im.text("Min counts / bin:")
        im.set_next_item_width(avail_w)
        ch_cnt, new_cnt = im.drag_int("##min_cnt", int(self.model.min_counts), 1, 0, 1000)
        if ch_cnt and new_cnt >= 0:
            self.model.min_counts = int(new_cnt)
            self.model.update()

        im.spacing()
        im.separator()
        im.spacing()

        # Action button
        from emtk.im_core import Col

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🌑 Estimate Background", (avail_w, 28.0)):
            self.track("toolAction_run")
            if callable(self.on_estimate):
                self.on_estimate()
            else:
                try:
                    self.model.estimate()
                except Exception:
                    pass
        self.remember("toolAction_run")
        im.pop_style_color(3)

        btn_half_w = max(50.0, (avail_w - 6.0) * 0.5)
        im.spacing()
        if im.button("📖 Guide", (btn_half_w, 24.0)):
            self.track("guide")
            self.start_guide()
        self.remember("guide")

        im.same_line()
        if im.button("❓ Help", (btn_half_w, 24.0)):
            self.track("help")
            self.show_help()
        self.remember("help")

        im.spacing()
        im.text_colored(ACCENT_GRAY, f"Files loaded: {len(self.model.files)}")
        im.spacing()
        im.text_wrapped(self.model.status)

    def _draw_iht_plot(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        origin = im.get_cursor_screen_pos()
        plot_w = max(avail_w, 150.0)
        plot_h = max(avail_h - 10.0, 150.0)

        series = self.model.iht_series()
        if not series:
            im.text_disabled(
                "No inter-photon time distribution data. Load TTTR files and estimate."
            )
            return

        if implot.begin_plot("Inter-photon Time Distribution##iht_plot", (plot_w, plot_h)):
            implot.setup_axes("Inter-photon time (ms)", "Counts")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)

            all_y = []
            for s in series:
                x = np.asarray(s.get("x", []), dtype=float)
                y = np.asarray(s.get("y", []), dtype=float)
                if len(x) == 0 or len(y) == 0:
                    continue
                all_y.append(y)
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                name = s.get("name", "Series")

                if s.get("symbol"):
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 3.0, fill=col)
                    implot.plot_scatter(name, x, y)
                else:
                    implot.set_next_line_style(col, float(s.get("width", 2.0)))
                    implot.plot_line(name, x, y)

            # ── Interactive Draggable Fit Window Region ──────────────────
            low, high = self.model.fit_from_ms, self.model.fit_to_ms
            if low > 0 and high > low:
                max_cnt = float(np.max(np.concatenate(all_y))) if all_y else 1000.0
                r_res = implot.drag_rect(
                    0,
                    float(low),
                    1.0,
                    float(high),
                    max_cnt,
                    col=REGION_FILL,
                )
                if r_res.modified:
                    self.model.fit_from_ms = float(min(r_res.x_min, r_res.x_max))
                    self.model.fit_to_ms = float(max(r_res.x_min, r_res.x_max))
                    self.model.update()

                implot.tag_x(
                    self.model.fit_from_ms,
                    REGION_BORDER,
                    f"Fit from: {self.model.fit_from_ms:.2f} ms",
                )
                implot.tag_x(
                    self.model.fit_to_ms, REGION_BORDER, f"Fit to: {self.model.fit_to_ms:.2f} ms"
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
                        self.model.fit_from_ms = float(data["min"])
                        self.model.fit_to_ms = float(data["max"])
                        self.model.update()
                except Exception:
                    pass
            im.end_drag_drop_target()

        self.remember("bg_iht_plot", (origin[0], origin[1], plot_w, plot_h))

    def _draw_rates_and_results(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        half_w = max(avail_w * 0.48, 120.0)

        # Left subpane: Rate bar chart
        rows = self.model.rate_rows()
        if rows:
            if implot.begin_plot("Background Rate (kHz)##rate_bars", (half_w, avail_h - 10.0)):
                implot.setup_axes("Detector", "Rate (kHz)")
                xs = np.arange(len(rows), dtype=float)
                for i, r in enumerate(rows):
                    col = _hex_to_rgba(r.get("color", ACCENT_BLUE))
                    implot.set_next_fill_style(col)
                    implot.plot_bars(
                        r.get("detector", f"Det {i}"),
                        np.array([xs[i]]),
                        ys=np.array([r.get("rate", 0.0)]),
                        bar_size=0.6,
                    )
                implot.end_plot()
        else:
            im.text_disabled("No rate data available.")

        im.same_line()

        # Right subpane: Results Table
        res_rows = self.model.results_rows()
        tbl_w = max(avail_w - half_w - 8.0, 150.0)
        if im.begin_table(
            "bg_results_tbl",
            3,
            im.TableFlags.ROW_BG | im.TableFlags.BORDERS | im.TableFlags.SCROLL_Y,
            size=(tbl_w, avail_h - 10.0),
        ):
            im.table_setup_scroll_freeze(0, 1)
            im.table_setup_column("File")
            im.table_setup_column("Detector")
            im.table_setup_column("Rate (kHz)")
            im.table_headers_row()

            for r in res_rows:
                im.table_next_row()
                im.table_next_column()
                im.text(str(r.get("file", "")))
                im.table_next_column()
                im.text(str(r.get("detector", "")))
                im.table_next_column()
                rate = r.get("rate_khz", 0.0)
                im.text(f"{rate:.3f}" if isinstance(rate, (float, np.floating)) else str(rate))
            im.end_table()


class BurstBackgroundApp(ImApp):
    """Immediate-mode EMTK application for Burst Background Estimation."""

    def __init__(
        self,
        model: BackgroundViewModel | None = None,
        on_estimate: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.bg_gui = BurstBackgroundGui(
            model=model,
            on_estimate=on_estimate,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.bg_gui.model
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.bg_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.bg_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.bg_gui.draw(w, h)
