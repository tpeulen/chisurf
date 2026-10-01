"""EMTK immediate-mode UI for Gopich-Szabo photon-by-photon kinetics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np

if TYPE_CHECKING:
    from .view_model import BurstGsViewModel

from emtk.app import ImApp
from emtk.im_core import get_current_context

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

WINDOW_BG = (30, 32, 38, 255)


def _hex_to_rgba(colour: str) -> tuple[int, int, int, int]:
    """``#rrggbb`` -> an RGBA tuple (the model's series carry hex colours)."""
    colour = colour.lstrip("#")
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16), 255


class BurstGsGui:
    """EMTK GUI for photon-by-photon kinetics with dockable, draggable windows."""

    def __init__(
        self,
        model: BurstGsViewModel,
        on_fit: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model
        self.on_fit = on_fit
        self.on_export = on_export
        self.on_guide = on_guide
        self.on_help = on_help
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None
        from pathlib import Path

        from emtk.docking import DockManager, Region, Split

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Photon-by-Photon Kinetics — Help & Reference",
            resource=help_resource,
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource, get_target_rect=lambda k: self.item_rects.get(k), owner=self.model,
            wait_for_controls=True,
        )
        self.on_used = self.tour.notify_used  # the Simulate and Fit steps wait for their control
        self.docks = DockManager(
            Split("h", 0.4, Region("controls"), Split("v", 0.5, Region("results"), Region("plot"))),
            name="burst_gs",
        )
        self.docks.add_window(
            "controls", "Kinetics controls", self._render_controls_window, dock="controls"
        )
        self.docks.add_window(
            "results", "Rate matrix & report", self._render_results_window, dock="results"
        )
        self.docks.add_window("plot", "Kinetics dynamics", self._render_plot_window, dock="plot")
        self.docks.add_window(
            "efficiency", "FRET states", self._render_efficiency_window, dock="plot"
        )

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

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

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float, h: float) -> None:
        self.docks.draw((0.0, 0.0, float(w), float(h)))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, w, h))

        if self.tour.active:
            self.tour.draw(w, h)

    def _render_controls_window(self, box=None) -> None:

        if getattr(self, "controller", None) is not None:
            self.controller.draw_inputs(remember=self.remember, track=self.track)

        # Action Buttons
        can_run_msg = self.model.can_run()
        if can_run_msg:
            im.begin_disabled()
            im.button("▶ Fit Kinetics")
            im.set_item_tooltip(
                "Fit the photon-by-photon kinetic model (Gopich–Szabo). Load .bur files and set the channels below first."
            )
            self.remember("Fit")
            im.end_disabled()
            # On its own wrapped line: a hint long enough to matter does not
            # fit beside the button and was clipped mid-word at the edge.
            im.text_wrapped(can_run_msg)
        else:
            if im.button("▶ Fit Kinetics"):
                self.track("Fit")
                if self.on_fit:
                    self.on_fit()
                else:
                    self.model.compute()
            im.set_item_tooltip(
                "Fit the photon-by-photon kinetic model (Gopich–Szabo) to the loaded bursts and report rates and states."
            )
            self.remember("Fit")

        im.new_line()
        if self.model.analysis is not None:
            if im.button("💾 Export CSV"):
                if self.on_export:
                    self.on_export()
            im.set_item_tooltip("Export fitted transition rates, states and provenance as CSV.")
        else:
            im.begin_disabled()
            im.button("💾 Export CSV")
            im.set_item_tooltip("Run a fit first; the results are then exported as CSV.")
            im.end_disabled()

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

        im.begin_disabled(bool(getattr(self, "controller", None) and self.controller.running))

        # Simulation Mode Toggle
        toggled, self.model.use_simulation = im.checkbox("Use Simulation Mode", self.model.use_simulation)
        im.set_item_tooltip(
            "Generate simulated burst trains instead of reading .bur files, to test the fitting."
        )
        self.remember("use_simulation")
        if toggled:
            self.track("use_simulation")
        if self.model.use_simulation:
            if self._section("Simulation Parameters", im.TreeNodeFlags.DEFAULT_OPEN):
                im.set_next_item_width(120)
                _, self.model.sim_k_forward = im.input_float(
                    "k_forward (s⁻¹)", self.model.sim_k_forward, step=100.0
                )
                im.set_item_tooltip(
                    "Forward transition rate of the simulated two-state model in s⁻¹."
                )
                self.remember("sim_k_forward")
                im.set_next_item_width(120)
                _, self.model.sim_k_backward = im.input_float(
                    "k_backward (s⁻¹)", self.model.sim_k_backward, step=100.0
                )
                im.set_item_tooltip(
                    "Backward transition rate of the simulated two-state model in s⁻¹."
                )
                im.set_next_item_width(120)
                _, self.model.sim_e1 = im.slider_float("E₁ (State 1)", self.model.sim_e1, 0.0, 1.0)
                im.set_item_tooltip("FRET efficiency of simulated state 1.")
                im.set_next_item_width(120)
                _, self.model.sim_e2 = im.slider_float("E₂ (State 2)", self.model.sim_e2, 0.0, 1.0)
                im.set_item_tooltip("FRET efficiency of simulated state 2.")
                im.set_next_item_width(120)
                _, self.model.sim_n_bursts = im.input_int(
                    "N Bursts", self.model.sim_n_bursts, step=50
                )
                im.set_item_tooltip("Number of simulated bursts to generate.")
                im.set_next_item_width(120)
                _, self.model.sim_seed = im.input_int("Seed", self.model.sim_seed, step=1)
                im.set_item_tooltip(
                    "Random seed for the simulation; identical seeds reproduce identical bursts."
                )
        else:
            if self._section("Data Input & Channels", im.TreeNodeFlags.DEFAULT_OPEN):
                im.text(f"Loaded .bur files: {len(self.model.bur_files)}")
                im.set_next_item_width(180)
                _, self.model.donor_channels = im.input_text(
                    "Donor Channels", self.model.donor_channels
                )
                im.set_item_tooltip(
                    "Comma-separated routing channels assigned to the donor (e.g. 0, 8)."
                )
                im.set_next_item_width(180)
                _, self.model.acceptor_channels = im.input_text(
                    "Acceptor Channels", self.model.acceptor_channels
                )
                im.set_item_tooltip(
                    "Comma-separated routing channels assigned to the acceptor (e.g. 1, 9)."
                )
                im.set_next_item_width(120)
                _, self.model.min_photons = im.input_int(
                    "Min Photons/Burst", self.model.min_photons, step=5
                )
                im.set_item_tooltip(
                    "Bursts with fewer photons than this are excluded from the fit."
                )

        im.separator()

        # Model Parameters
        if self._section("Kinetic Model Settings", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(120)
            _, self.model.n_states = im.slider_int("Number of States", self.model.n_states, 2, 4)
            im.set_item_tooltip("Number of FRET states in the kinetic model (2–4).")
            self.remember("n_states")
            im.set_next_item_width(120)
            _, self.model.initial_rate = im.input_float(
                "Initial Rate (s⁻¹)", self.model.initial_rate, step=100.0
            )
            im.set_item_tooltip("Starting guess for all transition rates in s⁻¹.")
            im.set_next_item_width(120)
            _, self.model.max_iterations = im.input_int(
                "Max Iterations", self.model.max_iterations, step=200
            )
            im.set_item_tooltip("Maximum number of optimizer iterations before the fit gives up.")
            _, self.model.fix_efficiencies = im.checkbox(
                "Fix Efficiencies", self.model.fix_efficiencies
            )
            im.set_item_tooltip("Keep the state FRET efficiencies fixed while fitting the rates.")
            _, self.model.scan_transition_time = im.checkbox(
                "Scan Transition Time", self.model.scan_transition_time
            )
            im.set_item_tooltip(
                "Scan a range of transition times and report the likelihood profile."
            )
            _, self.model.decode_states = im.checkbox(
                "Decode State Trajectories", self.model.decode_states
            )
            im.set_item_tooltip(
                "Decode the most likely state sequence per photon and show the transition profile."
            )

        self._draw_remaining_parameters()
        im.end_disabled()

    def _draw_remaining_parameters(self):
        im.separator()
        for attr, label, tooltip in (
            (
                "data_dir",
                "TTTR folder",
                "Resolve raw measurement filenames from the BUR table against this folder.",
            ),
            (
                "file_type",
                "TTTR file type",
                "Use auto to detect the container, or specify SPC-130, PTU, HT3 or HDF.",
            ),
            ("method", "Optimizer", "Choose nelder-mead or l-bfgs-b."),
        ):
            im.text(label + ":")
            changed, value = im.input_text("##" + attr, getattr(self.model, attr))
            im.set_item_tooltip(tooltip)
            if changed:
                setattr(self.model, attr, value)
        for attr, label, minimum, tooltip in (
            (
                "macro_time_resolution_ns",
                "Macro-time tick (ns)",
                0.0,
                "Zero reads the header resolution; an explicit tick rescales all fitted rates.",
            ),
            (
                "sim_photon_rate_khz",
                "Simulated photon rate (kHz)",
                0.1,
                "Detected photons per millisecond within each simulated burst.",
            ),
        ):
            changed, value = im.input_float(label, getattr(self.model, attr))
            im.set_item_tooltip(tooltip)
            self.remember(attr)  # the guide points at these by attribute
            if changed:
                setattr(self.model, attr, max(minimum, value))
        for attr, label, minimum, tooltip in (
            (
                "max_bursts",
                "Maximum bursts",
                0,
                "Limit the input for a quick fit; zero uses all bursts.",
            ),
            (
                "sim_photons_per_burst",
                "Simulated photons / burst",
                5,
                "Number of photons in every simulated burst.",
            ),
            (
                "transit_points",
                "Transition scan points",
                2,
                "Number of finite-transition-time hypotheses in the likelihood scan.",
            ),
        ):
            changed, value = im.input_int(label, getattr(self.model, attr))
            im.set_item_tooltip(tooltip)
            self.remember(attr)
            if changed:
                setattr(self.model, attr, max(minimum, value))
        changed, value = im.checkbox("Cross-check H2MM", self.model.cross_check_h2mm)
        im.set_item_tooltip("Compare the photon-by-photon fit with the discrete-time H2MM method.")
        if changed:
            self.model.cross_check_h2mm = value

    def _render_results_window(self, box=None) -> None:

        ana = self.model.analysis
        if ana is not None:
            im.text_colored("Fitted Kinetic Rates (s⁻¹):", (0.3, 0.85, 0.4, 1.0))
            self.remember("Rates")  # the guide's "Rates" table
            rates = ana.fit.rate_matrix
            if rates is not None:
                rates_arr = np.asarray(rates)
                n = rates_arr.shape[0] if rates_arr.ndim == 2 else self.model.n_states
                if im.begin_table(
                    "rates_table", n + 1, im.TableFlags.BORDERS | im.TableFlags.ROW_BG
                ):
                    im.table_setup_column("From \\ To", im.TableColumnFlags.WIDTH_FIXED, 70.0)
                    for j in range(n):
                        im.table_setup_column(f"State {j + 1}", im.TableColumnFlags.WIDTH_STRETCH)
                    im.table_headers_row()

                    for i in range(n):
                        im.table_next_row()
                        im.table_set_column_index(0)
                        im.text(f"State {i + 1}")
                        for j in range(n):
                            im.table_set_column_index(j + 1)
                            if i == j:
                                im.text_colored("—", (0.5, 0.5, 0.5, 1.0))
                            else:
                                val = rates_arr[j, i] if rates_arr.ndim == 2 else 0.0
                                im.text(f"{val:.1f}")
                    im.end_table()

            im.spacing()
            effs = ana.fit.efficiencies
            if effs is not None:
                im.text_colored("State Efficiencies:", (0.3, 0.8, 1.0, 1.0))
                eff_strs = [f"E_{i + 1} = {e:.3f}" for i, e in enumerate(effs)]
                im.text(" | ".join(eff_strs))
                if im.begin_table(
                    "state_populations", 3, im.TableFlags.BORDERS | im.TableFlags.ROW_BG
                ):
                    for title in ("State", "Efficiency", "Equilibrium population"):
                        im.table_setup_column(title)
                    im.table_headers_row()
                    for row in self.model.state_rows():
                        im.table_next_row()
                        for index, key in enumerate(("state", "efficiency", "population")):
                            im.table_set_column_index(index)
                            im.text(row[key])
                    im.end_table()

            im.separator()

        im.text_colored("Fit Summary & Console:", (0.8, 0.8, 0.8, 1.0))
        im.text_wrapped(self.model.results_text)

    def rate_bars(self) -> tuple[list[str], np.ndarray, np.ndarray | None]:
        """Fitted rate per transition, its label "k(i→j)", and the simulated rate where known.

        ``rate_matrix`` is ``K[target, source]``: k(i→j) is ``K[j, i]`` (as in the Qt tool's
        status line). The simulated truth exists only for the two-state simulation.
        """
        ana = self.model.analysis
        if ana is None or getattr(ana.fit, "rate_matrix", None) is None:
            return [], np.empty(0), None
        matrix = np.asarray(ana.fit.rate_matrix, dtype=float)
        pairs = [(i, j) for i in range(matrix.shape[0]) for j in range(matrix.shape[0]) if i != j]
        labels = [f"k({i + 1}\u2192{j + 1})" for i, j in pairs]
        rates = np.asarray([matrix[j, i] for i, j in pairs], dtype=float)
        truth = None
        if self.model.use_simulation and matrix.shape[0] == 2:
            truth = np.asarray([self.model.sim_k_forward, self.model.sim_k_backward], dtype=float)
        return labels, rates, truth

    def _render_plot_window(self, box=None) -> None:
        transit = self.model.transit_series()
        if transit:  # the transition-time scan, when it ran
            if implot.begin_plot("Transition-time scan##gs_rates", (-1, -1)):
                implot.setup_axes("transition time (\u00b5s)", "\u0394 log-likelihood vs instantaneous")
                for series in transit:
                    implot.set_next_line_style(_hex_to_rgba(series.get("color", "#4c9be8")),
                                               float(series.get("width", 2)))
                    implot.plot_line(series["name"], np.asarray(series["x"], float), np.asarray(series["y"], float))
                implot.end_plot()
            return
        labels, rates, truth = self.rate_bars()
        if implot.begin_plot("Fitted rates##gs_rates", (-1, -1)):
            implot.setup_axes("transition", "rate (1/s)")
            if labels:
                xs = np.arange(len(labels), dtype=float) + 1.0
                implot.setup_axis_ticks(implot.AXIS_X1, xs, labels=labels)
                implot.setup_legend(implot.LOCATION_NORTH_EAST)
                # Room above the taller of fitted and simulated, so neither sits on the edge;
                # applied when the rates change (a first ONCE request on a drawn plot is ignored).
                top = float(max(np.max(rates), np.max(truth) if truth is not None else 0.0)) * 1.15
                request = (0.0, top if top > 0 else 1.0)
                changed = request != getattr(self, "_rates_request", None)
                self._rates_request = request
                implot.setup_axis_limits(implot.AXIS_Y1, *request, implot.COND_ALWAYS if changed else implot.COND_ONCE)
                implot.plot_bars("fitted", xs, rates, bar_size=0.5)
                if truth is not None:
                    implot.set_next_marker_style(implot.MARKER_DIAMOND, 7.0, fill=(240, 140, 30, 255))
                    implot.plot_scatter("simulated", xs, truth)
            implot.end_plot()

    def _render_efficiency_window(self, box=None):
        if implot.begin_plot("FRET efficiency & fitted states", (-1, -1)):
            implot.setup_axes("FRET efficiency", "Population / photon density")
            for series in self.model.efficiency_series():
                x, y = series.get("x", []), series.get("y", [])
                if len(x) and len(x) == len(y):
                    implot.plot_line(series.get("name", "States"), x, y)
            implot.end_plot()


class BurstGsApp(ImApp):
    """Immediate-mode EMTK application for Gopich-Szabo kinetics."""

    def __init__(
        self,
        model: BurstGsViewModel | None = None,
        on_fit: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        if model is None:
            from .view_model import BurstGsViewModel

            model = BurstGsViewModel()
        self.controller = None
        if on_fit is None:
            from .controller import BurstGsController

            self.controller = BurstGsController(model)
            on_fit = self.controller.run
            on_export = on_export or (lambda: self.controller.browse("export"))
        self.gs_gui = BurstGsGui(
            model=model,
            on_fit=on_fit,
            on_export=on_export,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.gs_gui.model
        self.item_rects = self.gs_gui.item_rects
        self.gs_gui.remember = self.remember
        self.gs_gui.controller = self.controller
        super().__init__(gui=self._render)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.gs_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.gs_gui.show_help()

    def _render(self) -> None:
        if self.controller is not None:
            self.controller.poll()
            if self.controller.running:  # look again in 0.1 s while the fit runs
                ctx = get_current_context()
                ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.gs_gui.draw(float(w), float(h))
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
    return BurstGsApp(**kwargs)
