"""EMTK immediate-mode UI for the phasor calculator.

Left: the controls the model declares (frequency, harmonic, reference
lifetimes, the overlay toggles and their parameters). Right: the phasor plot —
the universal semicircle plus the selected reference geometry, drawn from the
same :func:`~chisurf.plugins.microscopy.img_pixel_phasor.analysis.build_overlays`
the imaging plugin and the ``phasor.overlays`` RPC method use, so all three
stay in sync. Below the controls: the τ → (g, s) table the old results HTML
showed, as a real table.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import json

import emtk.im as im
import emtk.implot as implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

if TYPE_CHECKING:
    from .tool import PhasorCalculatorTool, _PhasorCalcModel

WINDOW_BG = (30, 32, 38, 255)

def _leaves(section: dict):
    """Every section inside *section*, toggles of a row included."""
    for inner in section.get("sections") or []:
        yield inner
        yield from _leaves(inner)
    for item in section.get("items") or []:
        yield dict(item, type="toggle")


def _has_attr(section: dict, attr: str) -> bool:
    """Whether *section* or one inside it edits the model field *attr*."""
    if section.get("attr") == attr or any(i.get("attr") == attr for i in section.get("items") or []):
        return True
    return any(_has_attr(inner, attr) for inner in section.get("sections") or [])

#: pyqtgraph's single-letter colours, which the shared overlay builder emits.
_LETTER_COLOURS = {
    "w": (255, 255, 255, 255),
    "y": (255, 255, 0, 255),
    "r": (255, 80, 80, 255),
    "g": (80, 255, 80, 255),
    "c": (80, 200, 255, 255),
    "m": (255, 80, 255, 255),
    "k": (0, 0, 0, 255),
}


def _rgba(col) -> tuple[int, int, int, int]:
    """One overlay colour: a pyqtgraph letter, a hex string or an RGB tuple."""
    if isinstance(col, str):
        if col in _LETTER_COLOURS:
            return _LETTER_COLOURS[col]
        col = col.lstrip("#")
        return (int(col[0:2], 16), int(col[2:4], 16), int(col[4:6], 16), 255)
    if len(col) == 3:
        return (*col, 255)
    return tuple(col)


#: Grid items the overlay builder names per contour; kept out of the legend.
_GRID_PREFIXES = ("tau_m=", "tau_phi", "r=", "angle=", "unit circle", "mix line")


def _in_legend(name: str) -> bool:
    return not name.startswith(_GRID_PREFIXES)


SPEC = json.loads((Path(__file__).parent / "phasor_emtk.view.json").read_text(encoding="utf-8"))

#: The model attributes that make up a saved session (everything the controls edit).
SETTINGS = ("frequency", "harmonic", "taus", "show_grid", "show_ticks", "show_polar_grid", "show_fret", "tau_d0",
            "show_component", "g1", "s1", "g2", "s2", "show_mixing", "frac1", "show_cursor", "cursor_g", "cursor_s",
            "cursor_radius")


class PhasorForm:
    """What the specs read and call: the model's fields, and the derived texts and rows of the results."""

    def __init__(self, gui: "PhasorGui") -> None:
        object.__setattr__(self, "_gui", gui)

    def __getattr__(self, name: str):
        return getattr(self._gui.model, name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._gui.model, name, value)

    def effective_text(self) -> str:
        m = self._gui.model
        return f"Effective f = {float(m.frequency) * int(m.harmonic):g} MHz"

    def reference_rows(self) -> list[dict]:
        return [{"tau": tau, "g": g, "s": s} for tau, g, s in self._gui._rows()]

    def guide(self) -> None:
        self._gui.start_guide()

    def help(self) -> None:
        self._gui.show_help()


class PhasorGui(TourTarget):
    """EMTK GUI for the phasor calculator."""

    def __init__(
        self,
        tool: PhasorCalculatorTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        # The controls on the left over the reference table; the plot takes the rest.
        layout = Split(
            "h",
            0.36,
            Split("v", 0.66, Region("controls"), Region("results")),
            Region("plot"),
        )
        self.docks = DockManager(layout)
        self.docks.add_window("controls", "Controls", self._draw_controls, dock="controls", closable=False)
        self.docks.add_window("results", "Reference lifetimes", self._draw_results, dock="results", closable=False)
        self.docks.add_window("plot", "Phasor plot", self._draw_plot, dock="plot", closable=False)

        self.help_window = EmTkHelpWindow(
            title="Phasor calculator - Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.form = FormState()
        self.results_form = FormState()
        self.toolbar_form = FormState()
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=tool,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        for state in (self.form, self.results_form, self.toolbar_form):
            state.on_used = self.tour.notify_used
        self.panel = PhasorForm(self)

    # -- plumbing ------------------------------------------------------------------------------------------ #

    @property
    def model(self) -> _PhasorCalcModel:
        return self.tool._model

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 780.0)
        height = float(h or vp.size[1] or 540.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # -- controls ------------------------------------------------------------------------------------------ #

    def _controls_spec(self) -> dict:
        """The Controls specs (a copy the folds of which are this form's state)."""
        return SPEC["controls"]

    def reveal_step(self, index, step) -> None:
        """Unfold the group a guide step points into (Fraction c1 sits in a folded one)."""
        target = EmTkGuidedTour._target_key(step.get("target"))
        for panel in SPEC["controls"]["sections"]:
            if panel.get("type") == "panel" and _has_attr(panel, target):
                self.form.folds[panel["title"]] = True

    def _draw_controls(self, box: tuple[float, float, float, float]) -> None:
        self.toolbar_form.rects.clear()
        draw_form(SPEC["toolbar"], self.panel, self.toolbar_form, titles=False)
        self.item_rects.update(self.toolbar_form.rects)
        im.separator()
        self.form.rects.clear()
        draw_form(SPEC["controls"], self.panel, self.form)
        self.model.harmonic = max(1, int(self.model.harmonic))
        self.model.frac1 = min(max(float(self.model.frac1), 0.0), 1.0)
        self.item_rects.update(self.form.rects)

    def _overlays(self) -> list[dict]:
        m = self.model
        from chisurf.plugins.microscopy.img_pixel_phasor import analysis

        # The semicircle comes from the same builder as everything else — one
        # geometry, shared with the imaging plugin and the RPC method.
        return analysis.build_overlays(
            frequency_mhz=float(m.frequency),
            harmonic=int(m.harmonic),
            sets=m._sets() + ["semicircle"],
            taus=m._tau_list(),
            c1=(m.g1, m.s1),
            c2=(m.g2, m.s2),
            tau_d0=float(m.tau_d0),
            components=[[m.g1, m.s1], [m.g2, m.s2]],
            fractions=[float(m.frac1), 1.0 - float(m.frac1)],
            cursors=[
                {
                    "center": [m.cursor_g, m.cursor_s],
                    "radius": float(m.cursor_radius),
                    "name": "cursor",
                }
            ],
        )

    def _draw_plot(self, box: tuple[float, float, float, float]) -> None:
        m = self.model
        # Equal scale: the semicircle and the cursor are circles (they drew as ellipses).
        if implot.begin_plot("##phasor", (-1, -1), implot.FLAGS_EQUAL):
            implot.setup_axes("g (real)", "s (imaginary)")
            implot.setup_axes_limits(*m.PHASOR_G_RANGE, *m.PHASOR_S_RANGE, implot.COND_ONCE)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for overlay in self._overlays():
                name = str(overlay.get("name") or "?")
                style = overlay.get("style") or {}
                colour = _rgba(style.get("color", "w"))
                xs = overlay.get("x")
                ys = overlay.get("y")
                if xs is None or ys is None or not len(xs):
                    continue
                if overlay.get("kind") == "scatter":
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 5.0, colour)
                    implot.plot_scatter(name, xs, ys, spec=None if _in_legend(name)
                                        else implot.PlotSpec(flags=implot.ITEM_FLAGS_NO_LEGEND))
                else:
                    dash = style.get("dash")
                    implot.set_next_line_style(
                        colour,
                        float(style.get("width", 1.0)),
                        dash=(4.0, 3.0) if dash else None,
                    )
                    # The iso-lifetime grid names one item per contour; in the
                    # legend that is noise on top of noise. The geometric
                    # references stay listed.
                    # The grids name one item per contour (tau_m=…, r=…, angle=…); listed,
                    # they covered the plot. The named references stay in the legend.
                    spec = None
                    if not _in_legend(name):
                        spec = implot.PlotSpec(flags=implot.ITEM_FLAGS_NO_LEGEND)
                    implot.plot_line(name, xs, ys, spec=spec)
                # Lifetime ticks carry their τ as labels; drawn beside the marker.
                labels = overlay.get("labels")
                if labels:
                    for lx, ly, text in zip(xs, ys, labels):
                        implot.plot_text(str(text), float(lx), float(ly), (9, -13))
            implot.end_plot()
            im.set_item_tooltip(
                "The universal semicircle with the selected reference geometry: "
                "a single exponential of lifetime τ sits on the semicircle, a "
                "mixture inside on the chord between its components."
            )
        self.remember("plot", tuple(box))  # the window's content: the plot fills it
        self.remember("phasor", tuple(box))  # the spec's name for the plot section, which the guide targets
        if im.is_item_clicked():
            self.tour.notify_used("plot")
            self.tour.notify_used("phasor")

    # ── the τ → (g, s) table ──────────────────────────────────────────────

    def _rows(self) -> list[tuple[float, float, float]]:
        m = self.model
        from chisurf.plugins.microscopy.img_pixel_phasor import analysis

        freq = float(m.frequency) * int(m.harmonic)
        return [(tau, *analysis.lifetime_to_phasor(tau, freq)) for tau in m._tau_list()]

    def _draw_results(self, box: tuple[float, float, float, float]) -> None:
        self.results_form.rects.clear()
        draw_form(SPEC["results"], self.panel, self.results_form, titles=False)
        self.item_rects.update(self.results_form.rects)
        self.remember("results", tuple(box))


class PhasorCalcApp(ImApp):
    """The EMTK ImApp for the phasor calculator."""

    def __init__(self, tool: PhasorCalculatorTool) -> None:
        self.tool = tool
        self.phasor_gui = PhasorGui(
            tool,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        self.native_layouts = {"main": self.phasor_gui.docks}
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.phasor_gui.item_rects

    def start_guide(self) -> None:
        self.phasor_gui.start_guide()

    def show_help(self) -> None:
        self.phasor_gui.show_help()

    def _render(self) -> None:
        self.phasor_gui.draw()

    # -- persistence: the session's inputs (the Qt tool kept the window geometry only) ----------------------- #
    def export_settings(self) -> dict:
        """Every value the controls edit."""
        model = self.tool._model
        return {name: getattr(model, name) for name in SETTINGS}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; unusable entries are ignored and numbers are clamped to the field's range."""
        if not isinstance(settings, dict):
            return
        model = self.tool._model
        limits = {s["attr"]: s for s in _leaves(SPEC["controls"]) if s.get("type") == "value"}
        for name in SETTINGS:
            if name not in settings:
                continue
            value, current = settings[name], getattr(model, name)
            if isinstance(current, bool):
                if isinstance(value, bool):
                    setattr(model, name, value)
            elif isinstance(current, (int, float)):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
                    continue
                spec = limits.get(name, {})
                lo, hi = spec.get("minimum"), spec.get("maximum")
                value = min(max(value, lo if lo is not None else value), hi if hi is not None else value)
                setattr(model, name, int(value) if isinstance(current, int) else float(value))
            elif isinstance(current, str) and isinstance(value, str):
                setattr(model, name, value)


__all__ = ["PhasorCalcApp", "WINDOW_BG"]


def make_app(**kwargs):
    """Construct the standalone EMTK phasor calculator."""
    from chisurf.emtk.i18n import install

    install()
    from types import SimpleNamespace

    from .model import _PhasorCalcModel

    return PhasorCalcApp(SimpleNamespace(_model=_PhasorCalcModel()))
