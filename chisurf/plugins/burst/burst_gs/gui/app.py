"""EMTK immediate-mode UI for Gopich-Szabo photon-by-photon kinetics."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np

if TYPE_CHECKING:
    from .view_model import BurstGsViewModel

WINDOW_BG = (0.12, 0.12, 0.14, 1.0)


class BurstGsApp:
    """EMTK app for photon-by-photon kinetics with dockable, draggable windows."""

    def __init__(
        self,
        model: BurstGsViewModel,
        on_fit: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
    ) -> None:
        self.model = model
        self.on_fit = on_fit
        self.on_export = on_export
        self.threshold_y: float = 1000.0
        self._last_dropped_region: dict[str, Any] | None = None

    def update(self) -> None:
        # Full viewport dockspace
        im.dock_space_over_viewport(1)

        self._render_controls_window()
        self._render_results_window()
        self._render_plot_window()

    def _render_controls_window(self) -> None:
        im.set_next_window_size((440, 560), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((20, 20), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Kinetics Controls")
        if not expanded:
            im.end()
            return

        # Action Buttons
        can_run_msg = self.model.can_run()
        if can_run_msg:
            im.begin_disabled()
            im.button("▶ Fit Kinetics")
            im.end_disabled()
            im.same_line()
            im.text_colored(f"({can_run_msg})", (0.8, 0.5, 0.2, 1.0))
        else:
            if im.button("▶ Fit Kinetics"):
                if self.on_fit:
                    self.on_fit()
                else:
                    self.model.compute()

        im.same_line()
        if self.model.analysis is not None:
            if im.button("💾 Export CSV"):
                if self.on_export:
                    self.on_export()
        else:
            im.begin_disabled()
            im.button("💾 Export CSV")
            im.end_disabled()

        im.separator()

        # Simulation Mode Toggle
        _, self.model.use_simulation = im.checkbox("Use Simulation Mode", self.model.use_simulation)
        if self.model.use_simulation:
            if im.collapsing_header("Simulation Parameters", im.TreeNodeFlags.DEFAULT_OPEN):
                im.set_next_item_width(120)
                _, self.model.sim_k_forward = im.input_float("k_forward (s⁻¹)", self.model.sim_k_forward, step=100.0)
                im.set_next_item_width(120)
                _, self.model.sim_k_backward = im.input_float("k_backward (s⁻¹)", self.model.sim_k_backward, step=100.0)
                im.set_next_item_width(120)
                _, self.model.sim_e1 = im.slider_float("E₁ (State 1)", self.model.sim_e1, 0.0, 1.0)
                im.set_next_item_width(120)
                _, self.model.sim_e2 = im.slider_float("E₂ (State 2)", self.model.sim_e2, 0.0, 1.0)
                im.set_next_item_width(120)
                _, self.model.sim_n_bursts = im.input_int("N Bursts", self.model.sim_n_bursts, step=50)
                im.set_next_item_width(120)
                _, self.model.sim_seed = im.input_int("Seed", self.model.sim_seed, step=1)
        else:
            if im.collapsing_header("Data Input & Channels", im.TreeNodeFlags.DEFAULT_OPEN):
                im.text(f"Loaded .bur files: {len(self.model.bur_files)}")
                im.set_next_item_width(180)
                _, self.model.donor_channels = im.input_text("Donor Channels", self.model.donor_channels)
                im.set_next_item_width(180)
                _, self.model.acceptor_channels = im.input_text("Acceptor Channels", self.model.acceptor_channels)
                im.set_next_item_width(120)
                _, self.model.min_photons = im.input_int("Min Photons/Burst", self.model.min_photons, step=5)

        im.separator()

        # Model Parameters
        if im.collapsing_header("Kinetic Model Settings", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(120)
            _, self.model.n_states = im.slider_int("Number of States", self.model.n_states, 2, 4)
            im.set_next_item_width(120)
            _, self.model.initial_rate = im.input_float("Initial Rate (s⁻¹)", self.model.initial_rate, step=100.0)
            im.set_next_item_width(120)
            _, self.model.max_iterations = im.input_int("Max Iterations", self.model.max_iterations, step=200)
            _, self.model.fix_efficiencies = im.checkbox("Fix Efficiencies", self.model.fix_efficiencies)
            _, self.model.scan_transition_time = im.checkbox("Scan Transition Time", self.model.scan_transition_time)
            _, self.model.decode_states = im.checkbox("Decode State Trajectories", self.model.decode_states)

        im.end()

    def _render_results_window(self) -> None:
        im.set_next_window_size((480, 260), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((480, 20), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Rate Matrix & Report")
        if not expanded:
            im.end()
            return

        ana = self.model.analysis
        if ana is not None:
            im.text_colored("Fitted Kinetic Rates (s⁻¹):", (0.3, 0.85, 0.4, 1.0))
            rates = getattr(ana, "rates", None)
            if rates is not None:
                rates_arr = np.asarray(rates)
                n = rates_arr.shape[0] if rates_arr.ndim == 2 else self.model.n_states
                if im.begin_table("rates_table", n + 1, im.TableFlags.BORDERS | im.TableFlags.ROW_BG):
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
                                val = rates_arr[i, j] if rates_arr.ndim == 2 else 0.0
                                im.text(f"{val:.1f}")
                    im.end_table()

            im.spacing()
            effs = getattr(ana, "efficiencies", None)
            if effs is not None:
                im.text_colored("State Efficiencies:", (0.3, 0.8, 1.0, 1.0))
                eff_strs = [f"E_{i + 1} = {e:.3f}" for i, e in enumerate(effs)]
                im.text(" | ".join(eff_strs))

            im.separator()

        im.text_colored("Fit Summary & Console:", (0.8, 0.8, 0.8, 1.0))
        im.text_wrapped(self.model.results_text)
        im.end()

    def _render_plot_window(self) -> None:
        im.set_next_window_size((480, 280), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((480, 300), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Kinetics Dynamics Plot")
        if not expanded:
            im.end()
            return

        ana = self.model.analysis
        if implot.begin_plot("Kinetics Visualization", (-1, -1)):
            implot.setup_axes("Parameter / Time", "Rate / Likelihood")

            # Interactive drag line for rate threshold
            d_res = implot.drag_line_y(101, self.threshold_y, (0.9, 0.3, 0.3, 0.8), thickness=1.5)
            if d_res.modified:
                self.threshold_y = d_res.value
            implot.tag_y(self.threshold_y, (0.9, 0.3, 0.3, 1.0), fmt=f"Rate: {self.threshold_y:.0f} s⁻¹")

            if ana is not None and hasattr(ana, "transit_times") and hasattr(ana, "transit_profile"):
                tt = np.asarray(ana.transit_times, dtype=np.float64)
                tp = np.asarray(ana.transit_profile, dtype=np.float64)
                if len(tt) > 0 and len(tp) == len(tt):
                    implot.plot_line("Transition profile", tt, tp)
            elif ana is not None and getattr(ana, "rates", None) is not None:
                rates_arr = np.asarray(ana.rates).flatten()
                rates_arr = rates_arr[rates_arr > 0]
                if len(rates_arr) > 0:
                    xs = np.arange(len(rates_arr), dtype=np.float64) + 1.0
                    implot.plot_bars("Fitted Rates", xs, rates_arr, width=0.4)
            else:
                # Placeholder indicator
                demo_x = np.linspace(0, 10, 50, dtype=np.float64)
                demo_y = np.exp(-demo_x / 2.0) * self.threshold_y
                implot.plot_line("Expected Exchange Profile", demo_x, demo_y)

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                except Exception:
                    pass
            im.end_drag_drop_target()

        im.end()
