"""EMTK immediate-mode UI for Accurate FRET calibration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np

if TYPE_CHECKING:
    from .view_model import AccurateFretViewModel

from emtk.app import ImApp

WINDOW_BG = (30, 32, 38, 255)


class AccurateFretGui:
    """EMTK GUI for Accurate FRET calibration with dockable, draggable windows."""

    def __init__(
        self,
        model: AccurateFretViewModel,
        on_calibrate: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        on_from_ndx: Callable[[], None] | None = None,
        on_to_ndx: Callable[[], None] | None = None,
        on_share: Callable[[], None] | None = None,
        on_store_setup: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model
        self.on_calibrate = on_calibrate
        self.on_export = on_export
        self.on_from_ndx = on_from_ndx
        self.on_to_ndx = on_to_ndx
        self.on_share = on_share
        self.on_store_setup = on_store_setup
        self.on_guide = on_guide
        self.on_help = on_help

        self.gate_x_min: float = 0.2
        self.gate_x_max: float = 0.8
        self.gate_y_min: float = 0.2
        self.gate_y_max: float = 0.8
        self._last_dropped_region: dict[str, Any] | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        from pathlib import Path

        from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Accurate FRET — Help & Reference",
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

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

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
        im.dock_space_over_viewport(1)

        self._render_controls_window()
        self._render_results_window()
        self._render_plots_window()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, w, h))

        if self.tour.active:
            self.tour.draw(w, h)

    def _render_controls_window(self) -> None:
        im.set_next_window_size((420, 560), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((20, 20), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Calibration Controls")
        if not expanded:
            im.end()
            return

        # Action Buttons
        can_run_msg = self.model.can_run()
        if can_run_msg:
            im.begin_disabled()
            im.button("🎯 Calibrate")
            im.end_disabled()
            im.same_line()
            im.text_colored(f"({can_run_msg})", (0.8, 0.5, 0.2, 1.0))
        else:
            if im.button("🎯 Calibrate"):
                if self.on_calibrate:
                    self.on_calibrate()
                else:
                    self.model.calibrate()

        im.same_line()
        if self.on_from_ndx and im.button("📥 ndX"):
            self.on_from_ndx()
        im.same_line()
        if self.model.result is not None:
            if self.on_to_ndx and im.button("📤 ndX"):
                self.on_to_ndx()
            im.same_line()
            if self.on_export and im.button("💾 CSV"):
                self.on_export()
            if self.on_share:
                im.same_line()
                if im.button("🔗 Share"):
                    self.on_share()
            if self.on_store_setup:
                im.same_line()
                if im.button("🔬 Setup"):
                    self.on_store_setup()

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

        # Data & Channels
        if im.collapsing_header("Burst Data & Columns", im.TreeNodeFlags.DEFAULT_OPEN):
            if self.model.filename:
                import pathlib

                im.text_wrapped(f"File: {pathlib.Path(self.model.filename).name}")
            else:
                im.text_colored("No burst file loaded.", (0.6, 0.6, 0.6, 1.0))

            im.set_next_item_width(180)
            _, self.model.column_i_dd = im.input_text("I_DD (Donor)", self.model.column_i_dd)
            im.set_next_item_width(180)
            _, self.model.column_i_da = im.input_text("I_DA (FRET)", self.model.column_i_da)
            im.set_next_item_width(180)
            _, self.model.column_i_aa = im.input_text("I_AA (Acceptor)", self.model.column_i_aa)
            im.set_next_item_width(180)
            _, self.model.column_tau_f = im.input_text("Lifetime (Tau)", self.model.column_tau_f)

        im.separator()

        # Photophysics & Instrument Settings
        if im.collapsing_header("Photophysics & Prior", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_next_item_width(120)
            _, self.model.donor_lifetime = im.input_float(
                "Donor Tau (ns)", self.model.donor_lifetime, step=0.1
            )
            im.set_next_item_width(120)
            _, self.model.forster_radius = im.input_float(
                "Förster R₀ (Å)", self.model.forster_radius, step=1.0
            )
            im.set_next_item_width(120)
            _, self.model.linker_sigma = im.input_float(
                "Linker σ (Å)", self.model.linker_sigma, step=0.5
            )

            im.set_next_item_width(120)
            _, self.model.background_dd = im.input_float(
                "BG DD", self.model.background_dd, step=0.5
            )
            im.set_next_item_width(120)
            _, self.model.background_da = im.input_float(
                "BG DA", self.model.background_da, step=0.5
            )
            im.set_next_item_width(120)
            _, self.model.background_aa = im.input_float(
                "BG AA", self.model.background_aa, step=0.5
            )

            _, self.model.use_priors = im.checkbox(
                "Combine with Optics Prior", self.model.use_priors
            )
            _, self.model.show_dynamic_line = im.checkbox(
                "Show Dynamic FRET Line", self.model.show_dynamic_line
            )

        im.end()

    def _render_results_window(self) -> None:
        im.set_next_window_size((460, 260), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((460, 20), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Calibration Factors & Populations")
        if not expanded:
            im.end()
            return

        res = self.model.result
        if res is not None:
            im.text_colored("Correction Factors:", (0.3, 0.85, 0.4, 1.0))
            factors = getattr(res, "factors", {})
            uncert = getattr(res, "uncertainty", {})
            if im.begin_table("factors_tbl", 3, im.TableFlags.BORDERS | im.TableFlags.ROW_BG):
                im.table_setup_column("Factor", im.TableColumnFlags.WIDTH_FIXED, 90.0)
                im.table_setup_column("Value", im.TableColumnFlags.WIDTH_FIXED, 110.0)
                im.table_setup_column("Uncertainty", im.TableColumnFlags.WIDTH_STRETCH)
                im.table_headers_row()

                names = [
                    ("γ (Detection)", "gamma"),
                    ("β (Direct Excitation)", "beta"),
                    ("α (Crosstalk)", "alpha"),
                    ("δ (Acceptor Crosstalk)", "delta"),
                ]
                for label, key in names:
                    im.table_next_row()
                    im.table_set_column_index(0)
                    im.text(label)
                    im.table_set_column_index(1)
                    val = factors.get(key)
                    im.text(f"{val:.4f}" if val is not None else "—")
                    im.table_set_column_index(2)
                    u = uncert.get(key)
                    im.text(f"± {u:.4f}" if u is not None else "—")
                im.end_table()

            im.spacing()
            pops = getattr(res, "populations", None)
            if pops:
                im.text_colored("FRET Populations:", (0.3, 0.8, 1.0, 1.0))
                pop_strs = [f"E={p.e:.2f}, S={p.s:.2f}" for p in pops if hasattr(p, "e")]
                im.text(" | ".join(pop_strs[:4]))

            im.separator()

        im.text_colored("Status & Console:", (0.8, 0.8, 0.8, 1.0))
        im.text_wrapped(self.model.results_text)
        im.end()

    def _render_plots_window(self) -> None:
        im.set_next_window_size((460, 280), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((460, 300), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Accurate FRET Scatter Plots")
        if not expanded:
            im.end()
            return

        if implot.begin_plot("E–S Burst Scatter & FRET Line", (-1, -1)):
            implot.setup_axes("Proximity Ratio / FRET E", "Stoichiometry S")
            implot.setup_axes_limits(0.0, 1.0, 0.0, 1.0)

            # Interactive Gate Box
            res_rect = implot.drag_rect(
                201,
                self.gate_x_min,
                self.gate_y_min,
                self.gate_x_max,
                self.gate_y_max,
                (0.3, 0.8, 0.4, 0.3),
            )
            if res_rect.modified:
                self.gate_x_min, self.gate_x_max = res_rect.x_min, res_rect.x_max
                self.gate_y_min, self.gate_y_max = res_rect.y_min, res_rect.y_max

            implot.tag_x(self.gate_x_min, (0.3, 0.8, 0.4, 1.0), fmt=f"E_min: {self.gate_x_min:.2f}")
            implot.tag_x(self.gate_x_max, (0.3, 0.8, 0.4, 1.0), fmt=f"E_max: {self.gate_x_max:.2f}")

            # Plot static FRET line
            e_line = np.linspace(0.01, 0.99, 50, dtype=np.float64)
            s_line = np.full_like(e_line, 0.5)
            implot.plot_line("Static FRET Line (S=0.5)", e_line, s_line)

            # Plot burst scatter data if available
            series = self.model.scatter_series() if hasattr(self.model, "scatter_series") else []
            for s in series:
                x = np.asarray(s.get("x", []), dtype=np.float64)
                y = np.asarray(s.get("y", []), dtype=np.float64)
                if len(x) > 0 and len(x) == len(y):
                    name = s.get("name", "Bursts")
                    implot.plot_scatter(name, x, y, size=3.0)

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                    x_rng = data.get("x_range", [0.2, 0.8])
                    if len(x_rng) == 2:
                        self.gate_x_min, self.gate_x_max = float(x_rng[0]), float(x_rng[1])
                except Exception:
                    pass
            im.end_drag_drop_target()

        im.end()


class AccurateFretApp(ImApp):
    """Immediate-mode EMTK application for Accurate FRET calibration."""

    def __init__(
        self,
        model: AccurateFretViewModel,
        on_calibrate: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        on_from_ndx: Callable[[], None] | None = None,
        on_to_ndx: Callable[[], None] | None = None,
        on_share: Callable[[], None] | None = None,
        on_store_setup: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.fret_gui = AccurateFretGui(
            model=model,
            on_calibrate=on_calibrate,
            on_export=on_export,
            on_from_ndx=on_from_ndx,
            on_to_ndx=on_to_ndx,
            on_share=on_share,
            on_store_setup=on_store_setup,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.fret_gui.model
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.fret_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.fret_gui.show_help()

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.fret_gui.draw(float(w), float(h))
