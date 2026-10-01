"""Native emtk surface for the lifetime-FCS simulator.

The Qt widget's layout: a strip with **Simulate + Correlate**, Guide and ?, the
``lfcs_sim.view.json`` form on the left (its Run panel holds the status line) and
the species-filtered correlations on the right (log lag axis, species 1 blue,
species 2 red, their cross-correlation green). The simulation runs on a worker,
so the window stays responsive for the few seconds it takes.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from emtk import i18n, im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col, get_current_context
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import LifetimeFcsSimModel
from .strings import install_translations

install_translations()

GUI_DIR = Path(__file__).resolve().parent / "gui"
#: The Qt widget's pens: species 1, species 2, their cross-correlation.
SPECIES_COLOURS = ((31, 119, 180, 255), (214, 39, 40, 255))
CROSS_COLOUR = (44, 160, 44, 255)
SIMULATE = "Simulate + Correlate"

__all__ = ["LifetimeFcsSimApp", "LifetimeFcsSimModel", "make_app"]


def tr(text: str) -> str:
    return i18n.tr(text, context="Lifetime-FCS simulator")


class LifetimeFcsSimApp(ImApp):
    """Configure, run and inspect lifetime-filtered correlation simulations."""

    def __init__(self, model: LifetimeFcsSimModel | None = None) -> None:
        self.model = model or LifetimeFcsSimModel()
        self.message = tr("Set parameters and simulate.")
        self.spec = json.loads((GUI_DIR / "lfcs_sim.view.json").read_text())
        for panel in self.spec["sections"]:  # the Qt form's panels fold
            panel["collapsible"] = True
        self.form = FormState()
        self.form.custom["lfcs_sim_controls"] = self._draw_run_panel
        self.item_rects: dict[str, tuple] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lfcs-sim")
        self._future = None
        self.help_window = EmTkHelpWindow(title="Lifetime-FCS simulator — help", resource=GUI_DIR / "help.md",
                                          owner=self)
        self.tour = EmTkGuidedTour(steps=GUI_DIR / "guide.json", get_target_rect=self.target_rect, owner=self,
                                   wait_for_controls=True)
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.3, Region("form"), Region("plot")))
        self.docks.add_window("form", tr("Lifetime-FCS simulator"), self.draw_form_pane, dock="form",
                              closable=False)
        self.docks.add_window("plot", tr("Filtered correlations"), self.draw_plot, dock="plot", closable=False)
        super().__init__(self.render)

    # -- the run ------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        """True while a simulation is on the worker."""
        return self._future is not None

    def simulate(self) -> None:
        """Start a simulation with the current settings (the Qt button's slot, off the UI thread)."""
        if self.running:
            return
        self.message = tr("Simulating…")
        self.tour.notify_used("lfcs_sim_controls")
        self._future = self._executor.submit(self.model.run)

    def poll(self) -> None:
        """Take a finished simulation: the status line, or why it failed."""
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            future.result()
            self.message = self.model.status()
        except Exception as exc:  # noqa: BLE001 - shown, as the Qt tool's error dialog does
            self.model.datasets = []
            self.message = f"{tr('Simulation failed')}: {exc}"

    def close(self) -> None:
        """Release the worker."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- drawing ------------------------------------------------------------- #
    def target_rect(self, name):
        return self.item_rects.get(name) or self.form.rects.get(name)

    def draw_form_pane(self, box) -> None:
        busy = self.running
        im.begin_disabled(busy)
        im.push_style_color(Col.BUTTON, (31, 122, 31, 255))
        im.push_style_color(Col.BUTTON_HOVERED, (36, 145, 36, 255))
        if im.button(tr(SIMULATE)):
            self.simulate()
        im.pop_style_color(2)
        im.set_item_tooltip(tr("Generate synthetic photons, build lifetime filters and calculate correlations."))
        self.item_rects["lfcs_sim_controls"] = im.get_item_rect()
        im.end_disabled()
        im.same_line()
        if im.button(tr("Guide")):
            self.tour.start()
        im.set_item_tooltip(tr("Walk through the simulator step by step."))
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button("?"):
            self.help_window.show()
        im.set_item_tooltip(tr("What the simulation does, the formulas and their assumptions."))
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        im.begin_disabled(busy)
        draw_form(self.spec, self.model, self.form)
        im.end_disabled()

    def _draw_run_panel(self, section, model, state, width) -> None:
        """The spec's Run panel: the status line (its button is on the strip, as in the Qt widget)."""
        im.text_wrapped(self.message)
        im.set_item_tooltip(tr("Curves made and the filter condition number of the last simulation."))
        self.item_rects["status"] = im.get_item_rect()

    def draw_plot(self, box) -> None:
        w, h = im.get_content_region_avail()
        if implot.begin_plot("##lfcs-correlations", (w, max(h, 200.0))):
            implot.setup_axes(tr("lag time (ms)"), "G(τ)")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for data in self.model.datasets:
                x = np.asarray(data.get("x", []), dtype=float)
                y = np.asarray(data.get("y", []), dtype=float)
                good = x > 0
                if not np.any(good):
                    continue
                a, b = data.get("species_a", 0), data.get("species_b", 0)
                colour = SPECIES_COLOURS[a % len(SPECIES_COLOURS)] if a == b else CROSS_COLOUR
                implot.set_next_line_style(colour, 2.0)
                implot.plot_line(str(data.get("name", "G(τ)")), x[good], y[good])
            implot.end_plot()

    def render(self) -> None:
        self.poll()
        if self.running:  # look again in 0.1 s while the worker runs
            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)


def make_app() -> LifetimeFcsSimApp:
    from chisurf.emtk.i18n import install

    install()
    return LifetimeFcsSimApp()
