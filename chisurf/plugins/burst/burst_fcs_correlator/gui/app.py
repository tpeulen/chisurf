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

        from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

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

        from emtk.docking import DockManager, Region, Split

        self.docks = DockManager(
            Split("h", 0.4, Region("controls"), Split("v", 0.5, Region("results"), Region("plot"))),
            name="burst_fcs_correlator",
        )
        self.docks.add_window(
            "controls", "FCS controls", self._render_controls_window, dock="controls"
        )
        self.docks.add_window(
            "results", "Correlation G(τ)", self._render_corr_window, dock="results"
        )
        self.docks.add_window(
            "plot", "Diffusion distribution", self._render_dist_window, dock="plot"
        )

    @staticmethod
    def _section(label, flags=0):
        expanded = im.collapsing_header(label, flags)
        im.set_item_tooltip(f"Expand or collapse {label.lower()} controls.")
        return expanded

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

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        # Full viewport dockspace
        self.docks.draw((0.0, 0.0, float(w), float(h)))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))

        if self.tour.active:
            self.tour.draw(float(w), float(h))

    def _render_controls_window(self, box=None) -> None:

        if hasattr(self.tool, "draw_controls"):
            self.tool.draw_controls()

        # Action Buttons
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("▶ Run FCS"):
            self.track("toolAction_run")
            self._sync_to_tool()
            if hasattr(self.tool, "_on_run"):
                self.tool._on_run()
        im.set_item_tooltip("Correlate the bursts and compute the FCS curves G(τ).")
        self.remember("run")
        im.pop_style_color(3)

        im.same_line()
        if im.button("📖 Guide"):
            self.track("guide")
            self.start_guide()
        self.remember("guide")
        im.set_item_tooltip("Start a step-by-step guided tour of this tool.")

        im.same_line()
        if im.button("❓ Help"):
            self.track("help")
            self.show_help()
        self.remember("help")
        im.set_item_tooltip("Open the help window with reference documentation.")

        im.separator()

        # FCS Settings
        if self._section("Correlator Settings", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(120)
            ch_b, new_b = im.input_int("Bins per cascade", self.n_bins, step=1)
            im.set_item_tooltip("Number of bins per cascade level of the multi-tau correlator.")
            if ch_b and new_b > 0:
                self.n_bins = new_b
                self._sync_to_tool()

            im.set_next_item_width(120)
            ch_c, new_c = im.input_int("Cascade levels", self.n_casc, step=1)
            im.set_item_tooltip("Number of cascade levels; determines the lag-time range of G(τ).")
            if ch_c and new_c > 0:
                self.n_casc = new_c
                self._sync_to_tool()

            im.set_next_item_width(120)
            ch_p, new_p = im.input_float("Padding (ms)", self.padding_ms, step=10.0)
            im.set_item_tooltip(
                "Padding added around each burst in milliseconds before correlating."
            )
            if ch_p and new_p >= 0:
                self.padding_ms = new_p
                self._sync_to_tool()

            im.set_next_item_width(140)
            im.text("Fit mode:")
            im.same_line()
            fit_modes = ["none", "simple", "maxent"]
            if im.begin_combo("##fit_mode", self.fit_mode):
                for fm in fit_modes:
                    if im.selectable(fm, fm == self.fit_mode):
                        self.fit_mode = fm
                        self._sync_to_tool()
                    im.set_item_tooltip("Fit G(τ) with this model.")
                im.end_combo()
            im.set_item_tooltip(
                "Fit model applied to G(τ): simple exponential or maximum-entropy (maxent)."
            )

            ch_f, new_f = im.checkbox("Fine correlation grid", self.make_fine)
            im.set_item_tooltip(
                "Use a finer lag-time grid for the correlation curve (slower but smoother)."
            )
            if ch_f:
                self.make_fine = new_f
                self._sync_to_tool()

        im.separator()

        # Channel Pairs
        if self._section("Channel Pairs & Files", im.TreeNodeFlags.DEFAULT_OPEN):
            pairs = getattr(self.tool, "_pair_presets", [])
            im.text(f"Configured Pairs: {len(pairs)}")
            for p in pairs[:4]:
                name = p.get("pair_name", p.get("name", "Pair"))
                im.text_colored((180, 200, 230, 255), f"• {name}")

            curves = getattr(self.tool, "_curves", [])
            im.text(f"Calculated Curves: {len(curves)}")

    def _render_corr_window(self, box=None) -> None:

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
                self.tool._model.tmin_fit = self.gate_tau_min
                self.tool._model.tmax_fit = self.gate_tau_max

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

    def _render_dist_window(self, box=None) -> None:

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

            implot.end_plot()


class BurstFcsApp(ImApp):
    """Immediate-mode EMTK application for Burst-wise FCS Correlator."""

    def __init__(
        self,
        tool: BurstFcsTool | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.controller = None
        if tool is None:
            from .controller import BurstFcsController

            tool = self.controller = BurstFcsController()
        self.fcs_gui = BurstFcsGui(
            tool=tool,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.tool = self.fcs_gui.tool
        self.item_rects = self.fcs_gui.item_rects
        self.fcs_gui.remember = self.remember
        super().__init__(gui=self._render, continuous=self.controller is not None)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.fcs_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.fcs_gui.show_help()

    def _render(self) -> None:
        if self.controller is not None:
            self.controller.poll()
            self.fcs_gui._sync_from_tool()
        w, h = im.get_main_viewport().size
        self.fcs_gui.draw(float(w), float(h))
        if self.controller is not None:
            self.controller.draw_dialogs((0, 0, w, h))

    def close(self):
        if self.controller is not None:
            self.controller.close()

    def on_paths_dropped(self, paths):
        if self.controller is not None:
            self.controller.on_paths_dropped(paths)


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return BurstFcsApp(**kwargs)
