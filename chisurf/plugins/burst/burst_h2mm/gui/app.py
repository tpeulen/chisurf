"""EMTK immediate-mode UI for H2MM (photon-by-photon HMM) burst segmentation.

Provides dockable, draggable windows with interactive region dropping:
- Controls Window: Action buttons (Run H2MM, Restart, Stop, Bootstrap, LL Scan,
  Dwells in ndX, Guide, Help), Model Selection, and Optimisation settings.
- Transition Rate Matrix Window: Fitted transition rates between states in a clear table/grid.
- Transition Density Plot (TDP) Window: 2D plot of E_initial vs E_final transitions with
  interactive drag-rect gating and region dropping.
- Dwell Times & Trajectories Window: Dwell time distributions per state with interactive
  micro-time gating and region drop target.

Runs toolkit-free under ControlHost in Qt or natively via WebGPU/emtk.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from . import result_view
from .plots import REGION_FILL, ResultPlots

if TYPE_CHECKING:
    from .tool import H2mmTool

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)
REGION_BORDER = (90, 160, 240, 255)


class H2mmGui(TourTarget):
    """EMTK GUI providing dockable windows and region dropping for H2MM analysis."""

    def __init__(
        self,
        tool: H2mmTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_guide = on_guide
        self.on_help = on_help

        # Local parameter mirror
        self.min_states: int = 1
        self.max_states: int = 3
        self.criterion: str = "bic"
        self.engine: str = "em-float32"
        self.restarts: int = 2
        self.max_iter: int = 500
        self.min_photons: int = 5

        self.plots = ResultPlots()
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        from pathlib import Path

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Photon-by-Photon HMM (H2MM) — Help & Reference",
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

        # Build Dock Layout
        layout = Split(
            "h",
            0.35,
            # The controls column is the tall one: settings, model selection and
            # the optimisation engine stack above the rate matrix, and a share
            # that is too small clips the last section at the window border.
            Split("v", 0.72, Region("left_controls"), Region("left_rates")),
            Split("v", 0.50, Region("top_right"), Region("bottom_right")),
        )
        self._dock_manager = DockManager(layout)
        self._dock_manager.add_window(
            "controls",
            "H2MM controls and settings",
            self._draw_controls_dock,
            dock="left_controls",
            closable=False,
        )
        self._dock_manager.add_window(
            "rate_matrix",
            "Transition rate matrix",
            self._draw_rate_matrix_dock,
            dock="left_rates",
            closable=False,
        )
        self._dock_manager.add_window(
            "tdp",
            "Transition density (TDP)",
            self._draw_tdp_dock,
            dock="top_right",
            closable=False,
        )
        self._dock_manager.add_window(
            "dwells",
            "Dwell time distributions",
            self._draw_dwells_dock,
            dock="bottom_right",
            closable=False,
        )

    #: Settings the controls show, as ``attr -> (tool widget, kind)``. The tool's own widgets are the single source of
    #: truth: the controls read them every frame and write them on change, so a value typed here is the value
    #: ``H2mmTool._gather_settings`` fits with (no second copy that can drift, and nothing the tool never sees).
    _BOUND = {
        "min_states": ("sb_min_states", "int"),
        "max_states": ("sb_max_states", "int"),
        "criterion": ("cb_criterion", "text"),
        "engine": ("cb_engine", "data"),
        "restarts": ("sb_restarts", "int"),
        "max_iter": ("sb_max_iter", "int"),
        "min_photons": ("sb_min_photons", "int"),
    }

    def _sync_from_tool(self) -> None:
        """Read the settings from the tool's widgets (when it has them)."""
        for attr, (widget_name, kind) in self._BOUND.items():
            widget = getattr(self.tool, widget_name, None)
            if widget is None:
                continue
            if kind == "int":
                setattr(self, attr, int(widget.value()))
            elif kind == "text":
                setattr(self, attr, str(widget.currentText()))
            else:
                setattr(self, attr, str(widget.currentData() or widget.currentText()))

    def _sync_to_tool(self) -> None:
        """Write the settings to the tool's widgets (when it has them)."""
        for attr, (widget_name, kind) in self._BOUND.items():
            widget = getattr(self.tool, widget_name, None)
            if widget is None:
                continue
            value = getattr(self, attr)
            if kind == "int":
                widget.setValue(int(value))
            elif kind == "text":
                idx = widget.findText(value)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            else:
                idx = widget.findData(value)
                if idx >= 0:
                    widget.setCurrentIndex(idx)

    def _analysis(self):
        """The full in-memory analysis the tool holds (``tool._bundle.analysis``), or ``None`` before a fit.

        ``tool._result`` is the serialisable ``H2mmResult`` summary (n_states, criterion, ...); the arrays the plots
        need (rates, transitions, dwells) are on the bundle's ``H2mmAnalysis``, as in the Qt tool's ``_update_plots``.
        """
        bundle = getattr(self.tool, "_bundle", None)
        return getattr(bundle, "analysis", None)

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        self._sync_from_tool()
        width = float(w or 800.0)
        height = float(h or 600.0)
        self._dock_manager.draw((0.0, 0.0, max(width, 400.0), max(height, 300.0)))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        if self.tour.active:
            self.tour.draw(width, height)

    def _next_row_if_clipped(self, width_needed: float = 100.0) -> None:
        """Same-line the next control, or start a new row when it would clip."""
        if im.get_line_avail() < width_needed:
            im.new_line()
        else:
            im.same_line()

    def _draw_controls_dock(self, box: tuple[float, float, float, float]) -> None:
        # Action Buttons
        is_running = getattr(self.tool, "_fit_task", None) is not None

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("Run H2MM"):
            self.track("toolAction_run")
            self._sync_to_tool()
            if hasattr(self.tool, "btn_run"):
                self.tool.btn_run.click()
        im.set_item_tooltip(
            "Fit the photon-by-photon HMM to the bursts to find states and transition rates."
        )
        self.remember("toolAction_run")
        im.pop_style_color(3)

        im.same_line()
        if im.button("Restart"):
            self.track("toolAction_restart")
            self._sync_to_tool()
            if hasattr(self.tool, "btn_restart"):
                self.tool.btn_restart.click()
        im.set_item_tooltip("Reset the fit state and re-run the optimization from scratch.")
        self.remember("toolAction_restart")

        self._next_row_if_clipped()
        if is_running:
            im.push_style_color(Col.BUTTON, ACCENT_RED)
            if im.button("Stop"):
                if hasattr(self.tool, "stop"):
                    self.tool.stop()
            im.set_item_tooltip("Stop the running H2MM optimization.")
            im.pop_style_color(1)
        else:
            im.begin_disabled()
            im.button("Stop")
            im.set_item_tooltip("Stop the running H2MM optimization (nothing is running).")
            im.end_disabled()

        self._next_row_if_clipped()
        if im.button("Bootstrap"):
            if hasattr(self.tool, "btn_uncert"):
                self.tool.btn_uncert.click()
        im.set_item_tooltip("Estimate parameter uncertainties by bootstrapping the fit.")

        self._next_row_if_clipped()
        if im.button("LL Scan"):
            if hasattr(self.tool, "btn_llscan"):
                self.tool.btn_llscan.click()
        im.set_item_tooltip("Scan the log-likelihood over state numbers to help choose the model.")

        self._next_row_if_clipped()
        if im.button("Guide"):
            self.track("guide")
            self.start_guide()
        self.remember("guide")
        im.set_item_tooltip("Start a step-by-step guided tour of this tool.")

        self._next_row_if_clipped()
        if im.button("Help"):
            self.track("help")
            self.show_help()
        self.remember("help")
        im.set_item_tooltip("Open the help window with reference documentation.")

        im.separator()

        # Model Selection
        if im.collapsing_header("Model Selection", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(120)
            ch_min, new_min = im.slider_int("Min States", self.min_states, 1, 8)
            im.set_item_tooltip("Minimum number of states tried during model selection.")
            if ch_min:
                self.min_states = new_min
                self._sync_to_tool()

            im.set_next_item_width(120)
            ch_max, new_max = im.slider_int("Max States", self.max_states, 1, 8)
            im.set_item_tooltip("Maximum number of states tried during model selection.")
            if ch_max:
                self.max_states = max(self.min_states, new_max)
                self._sync_to_tool()

            im.set_next_item_width(140)
            crit_opts = ["bic", "icl"]
            if im.begin_combo("Criterion", self.criterion):
                for opt in crit_opts:
                    if im.selectable(opt, opt == self.criterion):
                        self.criterion = opt
                        self._sync_to_tool()
                        im.set_item_tooltip("Select this information criterion.")
                im.end_combo()
            im.set_item_tooltip(
                "Information criterion used to pick the best state number (BIC or ICL)."
            )

        im.separator()

        # Optimisation & Engine
        if im.collapsing_header("Optimisation Engine", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(160)
            eng_opts = [
                ("Fast EM (float32)", "em-float32"),
                ("Exact EM (float64)", "em"),
                ("Neural Surrogate", "neural"),
            ]
            curr_label = next((l for l, k in eng_opts if k == self.engine), self.engine)
            if im.begin_combo("Engine", curr_label):
                for label, key in eng_opts:
                    if im.selectable(label, key == self.engine):
                        self.engine = key
                        self._sync_to_tool()
                        im.set_item_tooltip("Run the optimizer with this engine.")
                im.end_combo()
            im.set_item_tooltip(
                "Optimizer used: fast float32 EM, exact float64 EM, or a neural surrogate."
            )

            # A narrow field plus a short label: the dock window is ~200 px of
            # content, and "field + long label" clipped the label mid-word.
            im.set_next_item_width(90)
            ch_res, new_res = im.input_int("Restarts", self.restarts, step=1)
            im.set_item_tooltip(
                "Number of random restarts; the fit with the best log-likelihood wins."
            )
            if ch_res and new_res > 0:
                self.restarts = new_res

            im.set_next_item_width(90)
            ch_it, new_it = im.input_int("Max iters", self.max_iter, step=100)
            im.set_item_tooltip("Maximum number of EM iterations per fit.")
            if ch_it and new_it > 0:
                self.max_iter = new_it

            im.set_next_item_width(90)
            ch_ph, new_ph = im.input_int("Min photons", self.min_photons, step=1)
            im.set_item_tooltip("Bursts shorter than this many photons are excluded from the fit.")
            if ch_ph and new_ph > 0:
                self.min_photons = new_ph

        im.separator()

        # Data & Export
        if im.collapsing_header("Results & Export", im.TreeNodeFlags.DEFAULT_OPEN):
            folder = getattr(self.tool, "data_folder", None)
            im.text(f"Burst Folder: {folder.name if folder else 'None selected'}")
            ana = self._analysis()
            if ana is not None:
                n_best = result_view.n_states(ana)
                im.text_colored(
                    f"Best model: {n_best} states ({ana.n_bursts} bursts, {ana.n_photons} photons)",
                    (0.3, 0.85, 0.4, 1.0),
                )
                if im.button("Open Dwells in ndX"):
                    if hasattr(self.tool, "open_dwells_in_ndx"):
                        self.tool.open_dwells_in_ndx()
                im.set_item_tooltip(
                    "Send the fitted dwell-time segments to ndXplorer for inspection."
                )
            else:
                im.text_wrapped("No H2MM fit yet. Select a burst folder and press Run H2MM.")

    def _draw_rate_matrix_dock(self, box: tuple[float, float, float, float]) -> None:
        rates = result_view.rate_matrix(self._analysis())
        if rates is None:
            im.text_wrapped("No transition rates yet: they appear here once an H2MM fit has finished.")
            return
        n = rates.shape[0]
        im.text_colored(f"Transition rates (1/s), {n} states:", (0.3, 0.85, 0.4, 1.0))
        tbl_h = max(60.0, box[3] - 30.0)
        if im.begin_table(
            "rate_mat_table",
            n + 1,
            im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_Y,
            (0, tbl_h),
        ):
            im.table_setup_column("From \\ To", im.TableColumnFlags.WIDTH_FIXED, 75.0)
            for j in range(n):
                im.table_setup_column(f"S{j}", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()
            for i in range(n):
                im.table_next_row()
                im.table_set_column_index(0)
                im.text(f"State S{i}")
                for j in range(n):
                    im.table_set_column_index(j + 1)
                    if i == j:
                        im.text_colored("-", (0.5, 0.5, 0.5, 1.0))
                    else:
                        im.text(f"{float(rates[i, j]):.1f}")
            im.end_table()

    def _draw_tdp_dock(self, box: tuple[float, float, float, float]) -> None:
        self.plots.draw_tdp(self._analysis())

    def _draw_dwells_dock(self, box: tuple[float, float, float, float]) -> None:
        self.plots.draw_dwells(self._analysis())


class H2mmApp(ImApp):
    """Immediate-mode EMTK application for H2MM photon-by-photon HMM segmentation."""

    def __init__(
        self,
        tool: H2mmTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.h2mm_gui = H2mmGui(
            tool=tool,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.tool = self.h2mm_gui.tool
        self.item_rects = self.h2mm_gui.item_rects
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.h2mm_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.h2mm_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.h2mm_gui.draw(float(w), float(h))
