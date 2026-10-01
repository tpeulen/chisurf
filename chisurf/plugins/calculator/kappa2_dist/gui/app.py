"""EMTK immediate-mode UI for the k² distribution calculator.

Left: the model choice and the anisotropy / calculation parameters. Right: the
k² distribution the selected model produces, and the resulting orientation
statistics. The widget (:class:`~.tool.Kappa2Dist`) keeps the RPC-backed
client, the save path and the backward-compat surface; this app renders its
state and calls back. Immediate mode reads the model every frame, so an edit
in the controls is the model's state on the same frame — Compute just runs the
distribution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

if TYPE_CHECKING:
    from .tool import Kappa2Dist, _Kappa2DistModel

WINDOW_BG = (30, 32, 38, 255)
#: The distribution's line colour (data colour, kept from the earlier app).
ACCENT_BLUE = (31, 119, 180, 255)
#: The marker of the assumed κ² (data colour).
TRUE_K2_COLOUR = (200, 200, 200, 160)

MODEL_OPTIONS = ("cone", "diffusion", "isotropic")

#: What a computation writes (everything else on the model is an input).
_RESULT_FIELDS = {"k2_mean", "k2_sd", "Rapp_mean", "RappSD", "delta_deg"}

#: The input panels of the Qt tool's spec (k2dist.view.json): model, anisotropies, options.
_SPEC_PATH = Path(__file__).resolve().parent.parent / "k2dist.view.json"

#: The orientation statistics, declared (the Qt Results panel plus the two order parameters).
RESULTS_TABLE = {
    "sections": [{
        "type": "custom",
        "key": "data_table",
        "description": "Orientation statistics of the κ² distribution; SD R_app/R_DA is the relative "
                       "systematic uncertainty on the distance -- the number to quote.",
        "options": {
            "source": "result_rows",
            "editable": False,
            "columns": [
                {"key": "quantity", "title": "Quantity", "description": "What is reported."},
                {"key": "value", "title": "Value", "description": "Its value for the last computation."},
            ],
        },
    }]
}


class Kappa2Gui(TourTarget):
    """EMTK GUI for the k² orientation-factor distribution calculator."""

    def __init__(
        self,
        tool: Kappa2Dist,
        on_compute: Callable[[], None] | None = None,
        on_edit: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_compute = on_compute
        self.on_edit = on_edit
        self.on_save = on_save
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        spec = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
        # Inputs only: the Results panel is the statistics window, the plot its own window.
        self.input_spec = {"sections": [s for s in spec["sections"]
                                        if s.get("type") == "panel" and s.get("title") != "Results"]}
        # The Qt radio row does not wrap in a narrow dock ("Isotropic" was cut at
        # 800 px); a combo with the same labels fits any width.
        for panel in self.input_spec["sections"]:
            for section in panel.get("sections", []):
                if section.get("type") == "choice":
                    section.pop("style", None)
        self.form = FormState()
        self.results_form = FormState()

        layout = Split(
            "h",
            0.40,
            Region("controls"),
            Split("v", 0.62, Region("plot"), Region("results")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "controls",
            "Model & parameters",
            self._draw_controls,
            dock="controls",
            closable=False,
        )
        self.docks.add_window(
            "plot",
            "κ² distribution",
            self._draw_plot,
            dock="plot",
            closable=False,
        )
        self.docks.add_window(
            "results",
            "Orientation statistics",
            self._draw_results,
            dock="results",
            closable=False,
        )

        self.help_window = EmTkHelpWindow(
            title="κ² distribution — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
            wait_for_controls=True,
        )

    # ── plumbing ──────────────────────────────────────────────────────────

    @property
    def model(self) -> _Kappa2DistModel:
        return self.tool._model

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()


    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 860.0)
        height = float(h or vp.size[1] or 620.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── controls ──────────────────────────────────────────────────────────

    def _draw_controls(self, box: tuple[float, float, float, float]) -> None:
        before_inputs = {
            k: v for k, v in vars(self.model).items() if isinstance(v, (float, int, str, bool))
        }
        busy = bool(getattr(self.tool, "busy", False))
        self._toolbar(busy)
        im.separator()

        im.begin_disabled(busy)
        self.form.rects.clear()
        draw_form(self.input_spec, self.model, self.form, titles=True)
        self.item_rects.update(self.form.rects)
        im.end_disabled()

        changed = [name for name, before in before_inputs.items()
                   if getattr(self.model, name, before) != before]
        for name in changed:
            self.tour.notify_used(name)
        if changed:
            # Parameter edits recompute, as the Qt tool's debounce timer did.
            self._schedule_compute()

    def _toolbar(self, busy: bool) -> None:
        im.begin_disabled(busy)
        if im.button("Compute"):
            if callable(self.on_compute):
                self.on_compute()
                self.tour.notify_used("compute")
        im.set_item_tooltip(
            "Run the selected orientation model and draw its κ² distribution "
            "and orientation statistics."
        )
        self.remember("compute")
        im.end_disabled()
        for label, key, tip, action in (
            ("Save", "save", "Save the κ² distribution and the orientation statistics.", self.on_save),
            ("Guide", "guide", "A step-by-step walk through the tool.", self.start_guide),
            ("Help", "help", "The short help page: the three models, the anisotropies to measure "
                             "first, and reading the result.", self.show_help),
        ):
            # A narrow dock wraps the row instead of clipping a button at its border.
            if im.get_line_avail() < im.calc_text_size(label)[0] + 24.0:
                im.new_line()
            else:
                im.same_line()
            if im.button(label) and callable(action):
                action()
            im.set_item_tooltip(tip)
            self.remember(key)

    def _schedule_compute(self) -> None:
        """Parameter edits recompute through the tool, like the old timer."""
        if callable(self.on_edit):
            self.on_edit()

    # ── the distribution plot ─────────────────────────────────────────────

    def _draw_plot(self, box: tuple[float, float, float, float]) -> None:
        m = self.model
        if implot.begin_plot("##k2dist", (-1, -1)):
            implot.setup_axes("κ²", "p(κ²)")
            implot.setup_legend()
            if m._k2scale is not None and m._k2hist is not None and len(m._k2hist):
                x = np.asarray(m._k2scale[1:], dtype=float)
                y = np.asarray(m._k2hist, dtype=float)
                implot.set_next_line_style(ACCENT_BLUE, 2.0)
                implot.plot_line("p(κ²)", x, y)
                # The assumed value the distribution should reproduce, as a line in the
                # legend (an axis tag printed over the x tick labels).
                implot.set_next_line_style(TRUE_K2_COLOUR, 1.0)
                implot.plot_inf_lines(f"true κ² = {m.kappa2_true:.3g}", [float(m.kappa2_true)])
            else:
                implot.plot_dummy("press Compute to draw the distribution")
            implot.end_plot()
            im.set_item_tooltip(
                "Probability distribution of κ² the selected orientation model "
                "produces, with the assumed true κ² marked."
            )
        self.remember("plot")

    # ── the results ───────────────────────────────────────────────────────

    def _draw_results(self, box: tuple[float, float, float, float]) -> None:
        draw_form(RESULTS_TABLE, self, self.results_form)
        self.remember("results")

    def result_rows(self) -> list[dict]:
        """The statistics table: the Qt Results panel's five values and the two order parameters."""
        m = self.model
        return [
            {"quantity": "Mean κ²", "value": f"{m.k2_mean:.4f}"},
            {"quantity": "SD κ²", "value": f"{m.k2_sd:.4f}"},
            {"quantity": "Mean R_app/R_DA", "value": f"{m.Rapp_mean:.4f}"},
            {"quantity": "SD R_app/R_DA", "value": f"{m.RappSD:.4f}"},
            {"quantity": "δ (deg)", "value": f"{m.delta_deg:.2f}"},
            {"quantity": "SD₂ (donor)", "value": f"{m.SD2:.4f}"},
            {"quantity": "Sₐ₂ (acceptor)", "value": f"{m.SA2:.4f}"},
        ]


class Kappa2App(ImApp):
    """The EMTK ImApp for the k² distribution calculator."""

    def __init__(
        self,
        tool: Kappa2Dist,
        on_compute: Callable[[], None] | None = None,
        on_edit: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.kappa2_gui = Kappa2Gui(
            tool,
            on_compute=on_compute,
            on_edit=on_edit,
            on_save=on_save,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        self.native_layouts = {"main": self.kappa2_gui.docks}
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.kappa2_gui.item_rects

    def start_guide(self) -> None:
        self.kappa2_gui.start_guide()

    def show_help(self) -> None:
        self.kappa2_gui.show_help()

    def _render(self) -> None:
        self.kappa2_gui.draw()


__all__ = ["Kappa2App", "WINDOW_BG"]


def make_app(**kwargs):
    """Construct the standalone EMTK orientation calculator and CSV export."""
    from chisurf.emtk.i18n import install

    install()
    from types import SimpleNamespace

    from chisurf.plugins.calculator.export import install_csv_export

    from ..backend.services import _kappa2_compute_handler
    from .model import _Kappa2DistModel

    client = SimpleNamespace(compute=_kappa2_compute_handler)
    state = SimpleNamespace(_model=_Kappa2DistModel())

    def compute():
        state._model.compute(client)

    import copy
    import threading

    state.busy = False
    #: An edit arrived while a computation ran: run again when it is in (the Qt
    #: tool's debounce timer computed after the last edit; this dropped it).
    state.dirty = False
    pending = []

    def schedule():
        if state.busy:
            state.dirty = True
            return
        state.busy = True
        state.dirty = False
        snapshot = copy.copy(state._model)

        def run():
            snapshot.compute(client)
            pending.append(snapshot)

        threading.Thread(target=run, daemon=True).start()

    app = Kappa2App(state, on_compute=schedule, on_edit=schedule)
    render = app.gui

    def draw():
        if pending:
            result = pending.pop()
            inputs = {k: v for k, v in state._model.__dict__.items() if not k.startswith("_")
                      and k not in _RESULT_FIELDS}
            state._model.__dict__.update(result.__dict__)
            # Keep what the user typed meanwhile; only the results come from the run.
            state._model.__dict__.update(inputs)
            state.busy = False
            if state.dirty:
                schedule()
        render()

    app.gui = draw
    app.continuous = True

    def write(path):
        m = state._model
        if m._k2scale is None or m._k2hist is None:
            raise ValueError("Compute a distribution before exporting.")
        header = [
            "# Kappa2 Distribution",
            f"# Model: {m.model_type}",
            f"# SD2: {m.SD2:.6f}",
            f"# SA2: {m.SA2:.6f}",
            f"# Mean kappa2: {m.k2_mean:.6f}",
            f"# SD kappa2: {m.k2_sd:.6f}",
            f"# Assumed kappa2: {m.kappa2_true:.6f}",
            f"# Mean Rapp: {m.Rapp_mean:.6f}",
            f"# SD Rapp: {m.RappSD:.6f}",
            "#",
            "# kappa2,probability",
        ]
        lines = [f"{x:.6f},{y:.6f}" for x, y in zip(m._k2scale[1:], m._k2hist)]
        path.write_text("\n".join(header + lines) + "\n")

    app.kappa2_gui.on_save = install_csv_export(app, "kappa2.csv", write)
    app.write_csv = write
    compute()
    return app
