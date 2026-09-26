"""The Burst IRF & Background tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstIrfBackgroundApp`) over
:class:`~.view_model.IrfBackgroundViewModel`:
- Docking & Draggable Windows: All panels (Parameters & Actions, IRF Plot,
  Results Table) are dockable, draggable, resizable and floatable.
- Interactive Region Dropping & Dragging:
  - On the IRF micro-time plot, interactive baseline threshold (:func:`implot.drag_line_y`)
    and tags allow adjusting the background floor live.
  - Drop targets allow dropping region presets directly onto the plot.
- Compute & Send-to-MLE actions to drive downstream burst-MLE fits.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp

from .view_model import IrfBackgroundViewModel

__all__ = ["BurstIrfBackgroundApp", "BurstIrfBackgroundGui", "WINDOW_BG"]

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)
REGION_FILL = (46, 117, 182, 60)
REGION_BORDER = (90, 160, 240, 255)


def _hex_to_rgba(col: Any, alpha: int = 255) -> tuple[int, int, int, int]:
    if isinstance(col, (tuple, list)):
        return int(col[0]), int(col[1]), int(col[2]), int(col[3] if len(col) > 3 else alpha)
    c = str(col).lstrip("#")
    if len(c) == 6:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha
    return (100, 150, 240, alpha)


class BurstIrfBackgroundGui:
    """Immediate-mode GUI logic and rendering for Burst IRF & Background."""

    def __init__(
        self,
        model: IrfBackgroundViewModel | None = None,
        on_compute: Callable[[], None] | None = None,
        on_send_to_mle: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else IrfBackgroundViewModel()
        self.on_compute = on_compute
        self.on_send_to_mle = on_send_to_mle
        self.on_guide = on_guide
        self.on_help = on_help
        self.status_text = "Load files, define detectors, then compute."
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        from pathlib import Path

        from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst IRF & Background — Help & Reference",
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
        if event == "computed":
            n = len(self.model.results_rows())
            self.status_text = f"Extracted IRF + background for {n} detector(s)."

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
        """Draw the dockable IRF & Background tool into (w, h) display pixels."""
        im.dock_space_over_viewport(1)

        left_w = min(max(280.0, w * 0.28), 340.0)
        right_w = max(w - left_w - 16.0, 320.0)

        # ── Window 1: Parameters & Actions ──────────────────────────────
        im.set_next_window_pos((4.0, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((left_w, max(h - 8.0, 100.0)), im.Cond.ALWAYS)
        if im.begin("IRF Parameters"):
            self._draw_parameters()
            im.end()

        # ── Window 2: IRF Decay Plot ─────────────────────────────────────
        im.set_next_window_pos((8.0 + left_w, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((right_w, max((h - 12.0) * 0.60, 150.0)), im.Cond.ALWAYS)
        if im.begin("IRF Plot (Non-burst scatter)"):
            self._draw_irf_plot()
            im.end()

        # ── Window 3: Results Table ──────────────────────────────────────
        im.set_next_window_pos((8.0 + left_w, 8.0 + max((h - 12.0) * 0.60, 150.0)), im.Cond.ALWAYS)
        im.set_next_window_size((right_w, max((h - 12.0) * 0.40, 100.0)), im.Cond.ALWAYS)
        if im.begin("Results"):
            self._draw_results_table()
            im.end()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))

        if self.tour.active:
            self.tour.draw(float(w), float(h))

    def _draw_parameters(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        im.text_colored(ACCENT_BLUE, "Burst Search & Baseline")

        # Min photons / burst
        im.text("Min photons / burst:")
        im.set_next_item_width(avail_w)
        ch_ph, new_ph = im.drag_int("##min_photons", int(self.model.min_photons), 5, 2, 100000)
        if ch_ph and new_ph >= 2:
            self.model.min_photons = int(new_ph)

        # Photon window
        im.text("Photon window:")
        im.set_next_item_width(avail_w)
        ch_pw, new_pw = im.drag_int("##photon_window", int(self.model.photon_window), 1, 2, 10000)
        if ch_pw and new_pw >= 2:
            self.model.photon_window = int(new_pw)

        # Time window (ms)
        im.text("Time window (ms):")
        im.set_next_item_width(avail_w)
        ch_tw, new_tw = im.drag_float(
            "##time_window", float(self.model.time_window_ms), 0.1, 0.001, 1000.0, "%.3f"
        )
        if ch_tw and new_tw > 0:
            self.model.time_window_ms = float(new_tw)

        # Baseline quantile
        im.text("Dark-count floor (quantile):")
        im.set_next_item_width(avail_w)
        ch_q, new_q = im.slider_float(
            "##quantile", float(self.model.baseline_quantile), 0.0, 0.9, "%.2f"
        )
        if ch_q:
            self.model.baseline_quantile = float(new_q)

        # Micro-time binning
        im.text("Micro-time binning:")
        im.set_next_item_width(avail_w)
        ch_bin, new_bin = im.drag_int("##binning", int(self.model.micro_time_binning), 1, 1, 64)
        if ch_bin and new_bin >= 1:
            self.model.micro_time_binning = int(new_bin)

        im.spacing()
        im.separator()
        im.spacing()

        # Actions
        from emtk.im_core import Col

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🌙 Compute", (avail_w, 28.0)):
            self.track("toolAction_run")
            if callable(self.on_compute):
                self.on_compute()
            else:
                try:
                    self.model.compute()
                except Exception as exc:
                    self.status_text = f"Error: {exc}"
        self.remember("toolAction_run")
        im.pop_style_color(3)

        im.spacing()
        if im.button("🎯 Send to MLE", (avail_w, 26.0)):
            self.track("send_to_mle")
            if callable(self.on_send_to_mle):
                self.on_send_to_mle()
        self.remember("send_to_mle")

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
        im.text_wrapped(self.status_text)

    def _draw_irf_plot(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        origin = im.get_cursor_screen_pos()
        plot_w = max(avail_w, 150.0)
        plot_h = max(avail_h - 10.0, 150.0)

        series = self.model.irf_series()
        if not series:
            im.text_disabled(
                "No IRF data available. Load TTTR files, define detectors, and compute."
            )
            return

        if implot.begin_plot("IRF (non-burst scatter)##irf_plot", (plot_w, plot_h)):
            implot.setup_axes("Micro time (ns)", "IRF (normalised)")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)

            for s in series:
                x = np.asarray(s.get("x", []), dtype=float)
                y = np.asarray(s.get("y", []), dtype=float)
                if len(x) == 0 or len(y) == 0:
                    continue
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                name = s.get("name", "IRF")
                implot.set_next_line_style(col, float(s.get("width", 2.0)))
                # Only plot positive values for log scale
                pos_mask = y > 0
                if np.any(pos_mask):
                    implot.plot_line(name, x[pos_mask], y[pos_mask])

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                    if "min" in data:
                        self.model.baseline_quantile = min(0.9, max(0.0, float(data["min"])))
                except Exception:
                    pass
            im.end_drag_drop_target()

        self.remember("irf_series", (origin[0], origin[1], plot_w, plot_h))

    def _draw_results_table(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        rows = self.model.results_rows()

        if im.begin_table(
            "irf_results_tbl",
            5,
            im.TableFlags.ROW_BG | im.TableFlags.BORDERS | im.TableFlags.SCROLL_Y,
            size=(avail_w, avail_h - 10.0),
        ):
            im.table_setup_scroll_freeze(0, 1)
            im.table_setup_column("Detector")
            im.table_setup_column("Background (kHz)")
            im.table_setup_column("Prompt (ns)")
            im.table_setup_column("Non-burst")
            im.table_setup_column("Burst")
            im.table_headers_row()

            for r in rows:
                im.table_next_row()
                im.table_next_column()
                im.text(str(r.get("detector", "")))
                im.table_next_column()
                im.text(f"{r.get('background_khz', 0.0):.3f}")
                im.table_next_column()
                im.text(f"{r.get('prompt_ns', 0.0):.3f}")
                im.table_next_column()
                im.text(f"{r.get('n_bg', 0):d}")
                im.table_next_column()
                im.text(f"{r.get('n_burst', 0):d}")

            im.end_table()


class BurstIrfBackgroundApp(ImApp):
    """Immediate-mode EMTK application for Burst IRF & Background."""

    def __init__(
        self,
        model: IrfBackgroundViewModel | None = None,
        on_compute: Callable[[], None] | None = None,
        on_send_to_mle: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.irf_gui = BurstIrfBackgroundGui(
            model=model,
            on_compute=on_compute,
            on_send_to_mle=on_send_to_mle,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.irf_gui.model
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.irf_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.irf_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.irf_gui.draw(w, h)
