"""EMTK immediate-mode UI for Burst Maximum Likelihood (MLE) Lifetime Analysis.

Provides dockable, draggable windows. Every number and curve in them is read from the wizard that computed it
(``fit_view``); with no fit the windows say so instead of drawing placeholders:
- Controls Window: Action buttons (Fit Bursts, Refit, Guide, Help), the wizard's start value and fit window,
  the fit-parameter table, and the input status.
- Decay & IRF Fit Window: the fitted decay, model, IRF and background of the current burst file, log scale.
- Lifetime Distribution Window: histogram of the fitted per-burst lifetimes with an interactive gate.
- Results Table Window: pooled lifetimes per state (segment-level analysis).

Runs toolkit-free under ControlHost in Qt or natively via WebGPU/emtk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import cap_widths

from . import fit_view

if TYPE_CHECKING:
    from ..wizard import MLELifetimeAnalysisWizard

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


class BurstMleGui(TourTarget):
    """EMTK GUI providing dockable windows and region dropping for Burst MLE."""

    def __init__(
        self,
        wizard: MLELifetimeAnalysisWizard,
        split_by_state: bool = False,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.wizard = wizard
        self.split_by_state = split_by_state
        self.on_guide = on_guide
        self.on_help = on_help

        # Interactive gate on the lifetime histogram: unset until there are lifetimes, then the data range.
        self.gate_tau_min: float | None = None
        self.gate_tau_max: float | None = None
        self._last_dropped_region: dict[str, Any] | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None
        # Start value and fit window: the spec's fields (typed, clamped, Enter commits) over the wizard itself.
        self.form_state = FormState()
        spec = load_view_spec(str(Path(__file__).parent / "mle.view.json"))
        self._fields = spec["sections"]
        cap_widths(self._fields)

        # Build Dock Layout
        layout = Split(
            "h",
            0.35,
            Split("v", 0.62, Region("left_controls"), Region("left_results")),
            Split("v", 0.50, Region("top_right"), Region("bottom_right")),
        )
        self._dock_manager = DockManager(layout)
        self._dock_manager.add_window(
            "controls",
            "Burst segment MLE controls" if self.split_by_state else "Burst MLE controls",
            self._draw_controls_dock,
            dock="left_controls",
            closable=False,
        )
        self._dock_manager.add_window(
            "results",
            "Fitted lifetimes",
            self._draw_results_dock,
            dock="left_results",
            closable=False,
        )
        self._dock_manager.add_window(
            "decay", "Decay and IRF fit", self._draw_decay_dock, dock="top_right", closable=False
        )
        self._dock_manager.add_window(
            "distribution",
            "Burst lifetime distribution",
            self._draw_distribution_dock,
            dock="bottom_right",
            closable=False,
        )

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Lifetime MLE - Help & Reference",
            resource=help_resource,
            owner=self.wizard,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.wizard,
            wait_for_controls=True,
        )
        self.on_used = self.tour.notify_used  # steps that ask for a press wait for it
        self.form_state.on_used = self.tour.notify_used

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        width = max(w, 400.0)
        height = max(h, 300.0)
        self._dock_manager.draw((0.0, 0.0, width, height))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        if self.tour.active:
            self.tour.draw(width, height)

    def _draw_controls_dock(self, box: tuple[float, float, float, float]) -> None:
        # Action Buttons
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("Fit Bursts"):
            self.track("toolAction_run")
            self.wizard.process_bursts()
        im.set_item_tooltip(
            "Fit the lifetime model to the micro-time decays of all bursts by maximum likelihood."
        )
        self.remember("toolAction_run")
        im.pop_style_color(3)

        im.same_line()
        if im.button("Refit"):
            self.track("toolAction_restart")
            self.wizard.refit()
        im.set_item_tooltip("Fit the current burst file's decay again with the current start values and fit window.")
        self.remember("toolAction_restart")

        im.same_line()
        if im.button("Guide"):
            self.start_guide()
        im.set_item_tooltip("Start a step-by-step guided tour of this tool.")
        self.remember("guide")

        im.same_line()
        if im.button("Help"):
            self.show_help()
        im.set_item_tooltip("Open the help window with reference documentation.")
        self.remember("help")

        im.separator()

        if self.split_by_state:
            im.text_colored(
                "Segment-level analysis: split by H2MM state is active", (0.3, 0.85, 0.4, 1.0)
            )
            im.separator()

        wiz = self.wizard
        # Start value and fit window are the wizard's own settings (one source of truth): shown from it,
        # written to it when changed (the wizard then refits).
        draw_sections(self._fields, wiz, self.form_state)
        for attr, key in (("tau", "tau_start"), ("micro_time_start", "window_start"), ("micro_time_stop", "window_stop")):
            rect = self.form_state.rects.get(attr)
            if rect is not None:
                self.item_rects[key] = tuple(rect)
        first = self.form_state.rects.get("tau")
        if first is not None:
            self.item_rects["start_and_window"] = tuple(first)

        im.separator()

        if im.collapsing_header("Fit parameters", im.TreeNodeFlags.DEFAULT_OPEN):
            self.remember("fit_parameters")
            rows = fit_view.parameter_rows(wiz)
            if not rows:
                im.text_wrapped("The wizard has no fit parameters yet.")
            elif im.begin_table(
                "fit_param_tbl", 4, im.TableFlags.BORDERS | im.TableFlags.ROW_BG, (0, 24.0 + 22.0 * len(rows))
            ):
                im.table_setup_column("Parameter", im.TableColumnFlags.WIDTH_STRETCH)
                im.table_setup_column("Start", im.TableColumnFlags.WIDTH_FIXED, 70.0)
                im.table_setup_column("Fixed", im.TableColumnFlags.WIDTH_FIXED, 50.0)
                im.table_setup_column("Result", im.TableColumnFlags.WIDTH_FIXED, 70.0)
                im.table_headers_row()
                for row in rows:
                    im.table_next_row()
                    im.table_set_column_index(0)
                    im.text(row.name)
                    im.table_set_column_index(1)
                    im.text(f"{row.initial:.4g}")
                    im.table_set_column_index(2)
                    im.text("yes" if row.fixed else "no")
                    im.table_set_column_index(3)
                    im.text(f"{row.result:.4g}" if wiz.fit_curves is not None else "-")
                im.end_table()

        im.separator()

        # Upstream inputs status, read from the wizard
        if im.collapsing_header("Input data and IRF status", im.TreeNodeFlags.DEFAULT_OPEN):
            self.remember("input_status")
            if fit_view.irf_background_ready(wiz):
                im.text_colored(
                    f"IRF and background loaded for {wiz.current_detector}", (0.3, 0.85, 0.4, 1.0)
                )
            else:
                im.text_colored("No IRF and background for the current detector yet", (0.8, 0.8, 0.4, 1.0))
            im.text(f"Burst files: {fit_view.burst_file_count(wiz)}")

    def _draw_decay_dock(self, box: tuple[float, float, float, float]) -> None:
        self.remember("decay", box)
        curves = fit_view.fit_curves(self.wizard)
        if curves is None:
            im.text_wrapped(
                "No fit yet. Load burst files, an IRF and a background in the wizard, then press Fit Bursts "
                "or Refit: the decay, the model, the IRF and the background of the current file appear here."
            )
        elif implot.begin_plot("Decay histogram and fit", (-1, -1)):
            implot.setup_axes("Micro-time window (channels, VV then VH)", "Photons")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.plot_scatter("Data (VV|VH)", curves.x, curves.data, size=2.5)
            implot.plot_line("Model (fit)", curves.x, curves.model)
            if curves.irf is not None:
                implot.plot_line("IRF", curves.x, curves.irf)
            implot.plot_line("Background", curves.x, curves.background)
            implot.end_plot()

        # Region Drop Target: a dropped region sets the fit window (bins)
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                    x_rng = data.get("x_range")
                    if x_rng and len(x_rng) == 2 and int(x_rng[0]) < int(x_rng[1]):
                        self.wizard.micro_time_range = [int(x_rng[0]), int(x_rng[1])]
                except Exception:
                    pass
            im.end_drag_drop_target()

    def _draw_distribution_dock(self, box: tuple[float, float, float, float]) -> None:
        self.remember("distribution", box)
        lifetimes = fit_view.burst_lifetimes(getattr(self.wizard, "burst_results", None))
        histograms = fit_view.lifetime_histograms(lifetimes)
        if not histograms:
            im.text_wrapped(
                "No burst lifetimes yet: press Fit Bursts. The histogram of the fitted lifetimes of all "
                "bursts appears here."
            )
            return
        everything = [v for values in lifetimes.values() for v in values]
        if self.gate_tau_min is None or self.gate_tau_max is None:
            self.gate_tau_min, self.gate_tau_max = float(min(everything)), float(max(everything))
        peak = max(float(counts.max()) for _, _, counts, _ in histograms)
        if implot.begin_plot("Fitted lifetime histogram", (-1, -1)):
            implot.setup_axes("Lifetime tau (ns)", "Bursts")
            for label, centres, counts, width in histograms:
                implot.plot_bars(label, centres, counts, bar_size=width * 0.9)
            res_rect = implot.drag_rect(
                502, self.gate_tau_min, 0.0, self.gate_tau_max, max(peak, 1.0), REGION_FILL
            )
            if res_rect.modified:
                self.gate_tau_min = res_rect.x_min
                self.gate_tau_max = max(self.gate_tau_min, res_rect.x_max)
            implot.end_plot()
        inside = sum(1 for v in everything if self.gate_tau_min <= v <= self.gate_tau_max)
        im.text(f"{inside} of {len(everything)} lifetimes inside the gate")
        im.set_item_tooltip("Fitted lifetimes between the two edges of the dragged box.")

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                    x_rng = data.get("x_range")
                    if x_rng and len(x_rng) == 2:
                        self.gate_tau_min, self.gate_tau_max = float(x_rng[0]), float(x_rng[1])
                except Exception:
                    pass
            im.end_drag_drop_target()

    def _draw_results_dock(self, box: tuple[float, float, float, float]) -> None:
        state_lifetimes = fit_view.state_lifetime_rows(self.wizard)
        if state_lifetimes:
            im.text_colored("Pooled state lifetimes:", (0.3, 0.85, 0.4, 1.0))
            tbl_h = max(60.0, box[3] - 40.0)
            if im.begin_table(
                "state_tau_tbl",
                4,
                im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_Y,
                (0, tbl_h),
            ):
                im.table_setup_column("State", im.TableColumnFlags.WIDTH_FIXED, 60.0)
                im.table_setup_column("Detector", im.TableColumnFlags.WIDTH_FIXED, 80.0)
                im.table_setup_column("Tau (ns)", im.TableColumnFlags.WIDTH_FIXED, 90.0)
                im.table_setup_column("Photons", im.TableColumnFlags.WIDTH_STRETCH)
                im.table_headers_row()

                for row in state_lifetimes:
                    im.table_next_row()
                    im.table_set_column_index(0)
                    im.text(f"S{row['State']}")
                    im.table_set_column_index(1)
                    im.text(str(row["Detector"]))
                    im.table_set_column_index(2)
                    im.text(f"{row['Tau']:.3f}")
                    im.table_set_column_index(3)
                    im.text(f"{int(row['Photons']):,}")
                im.end_table()
        elif self.split_by_state:
            im.text_wrapped("No pooled state lifetimes yet: press Fit Bursts to fit every H2MM state.")
        else:
            im.text_wrapped(
                "Pooled state lifetimes exist only for the segment-level analysis (split by H2MM state)."
            )


class BurstMleApp(ImApp):
    """Immediate-mode EMTK application for Burst Maximum Likelihood (MLE) Lifetime Analysis."""

    def __init__(
        self,
        wizard: MLELifetimeAnalysisWizard,
        split_by_state: bool = False,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.mle_gui = BurstMleGui(
            wizard=wizard,
            split_by_state=split_by_state,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.wizard = self.mle_gui.wizard
        self.item_rects = self.mle_gui.item_rects
        self.form = self.mle_gui.form_state
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.mle_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.mle_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.mle_gui.draw(float(w), float(h))
