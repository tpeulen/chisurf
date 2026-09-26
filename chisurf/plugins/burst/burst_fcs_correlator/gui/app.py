"""EMTK immediate-mode UI for Burst-wise FCS Correlator.

Provides dockable, draggable windows with interactive region dropping:
- Controls Window: Action buttons (Run FCS, Settings, Guide, Help),
  FCS parameters (cascades, bins, padding, fit mode), and channel pairs.
- Correlation G(τ) Window: Correlation curve with log-time axis, interactive
  fit-window drag-rect, and region dropping.
- Diffusion Distribution P(τ_D) Window: Maximum-entropy / diffusion time
  distribution curve with interactive range gating and drop target.

Runs toolkit-free under ControlHost in Qt or natively via WebGPU/emtk.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.im_core import Col

if TYPE_CHECKING:
    from .tool import BurstFcsTool

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


class BurstFcsGui:
    """EMTK GUI providing dockable windows and region dropping for Burst FCS."""

    def __init__(
        self,
        tool: BurstFcsTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_guide = on_guide
        self.on_help = on_help

        # Local parameter mirrors
        self.n_bins: int = 3
        self.n_casc: int = 20
        self.padding_ms: float = 100.0
        self.fit_mode: str = "simple"
        self.make_fine: bool = False

        # Interactive gating
        self.gate_tau_min: float = 0.001
        self.gate_tau_max: float = 100.0
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        from pathlib import Path

        from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst-wise FCS Correlator — Help & Reference",
            resource=help_resource,
            owner=self.tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.tool,
        )

        self._sync_from_tool()

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def _sync_from_tool(self) -> None:
        """Read parameters from tool model."""
        m = getattr(self.tool, "_model", None)
        if m is not None:
            self.n_bins = int(m.n_bins)
            self.n_casc = int(m.n_casc)
            self.padding_ms = float(m.padding_ms)
            self.fit_mode = str(m.fit_mode)
            self.make_fine = bool(m.make_fine)

    def _sync_to_tool(self) -> None:
        """Write parameters back to tool model."""
        m = getattr(self.tool, "_model", None)
        if m is not None:
            m.n_bins = int(self.n_bins)
            m.n_casc = int(self.n_casc)
            m.padding_ms = float(self.padding_ms)
            m.fit_mode = str(self.fit_mode)
            m.make_fine = bool(self.make_fine)

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
        # Full viewport dockspace
        im.dock_space_over_viewport(1)

        self._render_controls_window()
        self._render_corr_window()
        self._render_dist_window()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))

        if self.tour.active:
            self.tour.draw(float(w), float(h))

    def _render_controls_window(self) -> None:
        im.set_next_window_size((380, 520), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((10, 10), im.Cond.FIRST_USE_EVER)

        if not im.begin("Burst FCS Controls & Settings"):
            return

        # Action Buttons
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("▶ Run FCS"):
            self.track("toolAction_run")
            self._sync_to_tool()
            if hasattr(self.tool, "_on_run"):
                self.tool._on_run()
        self.remember("run")
        im.pop_style_color(3)

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

        im.separator()

        # FCS Settings
        if im.collapsing_header("Correlator Settings", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(120)
            ch_b, new_b = im.input_int("Bins per cascade", self.n_bins, step=1)
            if ch_b and new_b > 0:
                self.n_bins = new_b
                self._sync_to_tool()

            im.set_next_item_width(120)
            ch_c, new_c = im.input_int("Cascade levels", self.n_casc, step=1)
            if ch_c and new_c > 0:
                self.n_casc = new_c
                self._sync_to_tool()

            im.set_next_item_width(120)
            ch_p, new_p = im.input_float("Padding (ms)", self.padding_ms, step=10.0)
            if ch_p and new_p >= 0:
                self.padding_ms = new_p
                self._sync_to_tool()

            im.set_next_item_width(140)
            fit_modes = ["simple", "maxent"]
            if im.begin_combo("Fit mode", self.fit_mode):
                for fm in fit_modes:
                    if im.selectable(fm, fm == self.fit_mode):
                        self.fit_mode = fm
                        self._sync_to_tool()
                im.end_combo()

            ch_f, new_f = im.checkbox("Fine correlation grid", self.make_fine)
            if ch_f:
                self.make_fine = new_f
                self._sync_to_tool()

        im.separator()

        # Channel Pairs
        if im.collapsing_header("Channel Pairs & Files", im.TreeNodeFlags.DEFAULT_OPEN):
            pairs = getattr(self.tool, "_pair_presets", [])
            im.text(f"Configured Pairs: {len(pairs)}")
            for p in pairs[:4]:
                name = p.get("name", "Pair")
                im.text_colored(f"• {name}", (0.7, 0.8, 0.9, 1.0))

            curves = getattr(self.tool, "_curves", [])
            im.text(f"Calculated Curves: {len(curves)}")

        im.end()

    def _render_corr_window(self) -> None:
        im.set_next_window_size((500, 260), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((400, 10), im.Cond.FIRST_USE_EVER)

        if not im.begin("Correlation G(τ) Curve"):
            return

        if implot.begin_plot("Autocorrelation & Fit G(tau)", (-1, -1)):
            implot.setup_axes("Lag Time tau (ms)", "G(tau)")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)

            # Fit window drag rect
            res_rect = implot.drag_rect(
                601,
                self.gate_tau_min,
                0.0,
                self.gate_tau_max,
                2.0,
                REGION_FILL,
            )
            if res_rect.modified:
                self.gate_tau_min = max(1e-4, res_rect.x_min)
                self.gate_tau_max = max(self.gate_tau_min * 2.0, res_rect.x_max)

            implot.tag_x(
                self.gate_tau_min, (0.3, 0.8, 0.4, 1.0), fmt=f"tau_min: {self.gate_tau_min:.4f} ms"
            )
            implot.tag_x(
                self.gate_tau_max, (0.3, 0.8, 0.4, 1.0), fmt=f"tau_max: {self.gate_tau_max:.2f} ms"
            )

            # Try to get active series from model
            m = getattr(self.tool, "_model", None)
            series = m.corr_plot_series() if m is not None else []
            if series:
                for s in series:
                    xs = np.asarray(s.get("x", []), dtype=np.float64)
                    ys = np.asarray(s.get("y", []), dtype=np.float64)
                    if len(xs) > 0 and len(xs) == len(ys):
                        implot.plot_line(s.get("name", "G(tau)"), xs, ys)
            else:
                # Simulated FCS curve preview
                taus = np.logspace(-3, 2, 100, dtype=np.float64)
                g_demo = 1.0 + 0.8 / ((1.0 + taus / 0.5) * np.sqrt(1.0 + taus / (0.5 * 25.0)))
                implot.plot_line("G(tau) preview", taus, g_demo)

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                    x_rng = data.get("x_range", [0.001, 100.0])
                    if len(x_rng) == 2:
                        self.gate_tau_min = float(x_rng[0])
                        self.gate_tau_max = float(x_rng[1])
                except Exception:
                    pass
            im.end_drag_drop_target()

        im.end()

    def _render_dist_window(self) -> None:
        im.set_next_window_size((500, 270), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((400, 280), im.Cond.FIRST_USE_EVER)

        if not im.begin("Diffusion Time Distribution P(τ_D)"):
            return

        if implot.begin_plot("Diffusion Distribution", (-1, -1)):
            implot.setup_axes("Diffusion Time tau_D (ms)", "Probability P")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)

            m = getattr(self.tool, "_model", None)
            dist_series = m.dist_plot_series() if m is not None else []
            if dist_series:
                for s in dist_series:
                    xs = np.asarray(s.get("x", []), dtype=np.float64)
                    ys = np.asarray(s.get("y", []), dtype=np.float64)
                    if len(xs) > 0 and len(xs) == len(ys):
                        implot.plot_line(s.get("name", "P(tau_D)"), xs, ys)
            else:
                # Simulated diffusion distribution peak
                tds = np.logspace(-2, 2, 80, dtype=np.float64)
                p_demo = np.exp(-((np.log10(tds) - np.log10(0.5)) ** 2) / (2.0 * 0.25**2))
                implot.plot_line("P(tau_D) preview", tds, p_demo)

            implot.end_plot()

        im.end()


class BurstFcsApp(ImApp):
    """Immediate-mode EMTK application for Burst-wise FCS Correlator."""

    def __init__(
        self,
        tool: BurstFcsTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.fcs_gui = BurstFcsGui(
            tool=tool,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.tool = self.fcs_gui.tool
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.fcs_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.fcs_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.fcs_gui.draw(float(w), float(h))
