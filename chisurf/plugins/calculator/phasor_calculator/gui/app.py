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

import emtk.im as im
import emtk.implot as implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int

if TYPE_CHECKING:
    from .tool import PhasorCalculatorTool, _PhasorCalcModel

WINDOW_BG = (30, 32, 38, 255)
ACCENT_GREEN = (46, 160, 67, 255)

_TABLE_FLAGS = im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE

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

        # Both halves of the left column must fit: four collapsible groups
        # above, and the τ/g/s table below with all five reference rows
        # visible — a share either way clips one of them.
        layout = Split(
            "h",
            0.38,
            Split("v", 0.70, Region("controls"), Region("results")),
            Region("plot"),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "controls",
            "🎛️ Controls",
            self._draw_controls,
            dock="controls",
            closable=False,
        )
        self.docks.add_window(
            "results",
            "🔢 Reference lifetimes",
            self._draw_results,
            dock="results",
            closable=False,
        )
        self.docks.add_window(
            "plot",
            "📍 Phasor plot",
            self._draw_plot,
            dock="plot",
            closable=False,
        )

        self.help_window = EmTkHelpWindow(
            title="Phasor calculator — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.form = FormState()
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=tool,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        self.form.on_used = self.tour.notify_used

    # ── plumbing ──────────────────────────────────────────────────────────

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

    # ── controls ──────────────────────────────────────────────────────────

    def _controls_spec(self) -> dict:
        """The spec's Controls panel without its Results panel (drawn as a table in its own dock)."""
        if getattr(self, "_spec", None) is None:
            import json

            spec = json.loads((Path(__file__).parent / "phasor.view.json").read_text())
            controls = spec["sections"][0]["sections"][0]
            sections = [s for s in controls["sections"] if s.get("title") != "Results"]
            for section in sections:  # the groups fold, as the Qt AutoForm panels do
                if section.get("type") == "panel":
                    section["collapsible"] = True
            self._spec = {"sections": sections}
        return self._spec

    def reveal_step(self, index, step) -> None:
        """Unfold the group a guide step points into (Fraction c1 sits in a folded one)."""
        target = EmTkGuidedTour._target_key(step.get("target"))
        for panel in self._controls_spec()["sections"]:
            if panel.get("type") == "panel" and any(f.get("attr") == target for f in panel.get("sections", [])):
                self.form.folds[panel["title"]] = True

    def _draw_controls(self, box: tuple[float, float, float, float]) -> None:
        if im.button("📖 Guide"):
            self.start_guide()
        im.set_item_tooltip("A step-by-step walk through the tool.")
        self.remember("guide")
        im.same_line()
        if im.button("❓ Help"):
            self.show_help()
        im.set_item_tooltip("The short help page: reading the semicircle and every control.")
        self.remember("help")
        im.separator()
        # The form is the spec the Qt tool renders (phasor.view.json): one declaration,
        # labels, bounds and tooltips (its descriptions) shared by both hosts.
        self.form.rects.clear()
        draw_form(self._controls_spec(), self.model, self.form)
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
        self.remember("plot")
        if im.is_item_clicked():
            self.tour.notify_used("plot")

    # ── the τ → (g, s) table ──────────────────────────────────────────────

    def _rows(self) -> list[tuple[float, float, float]]:
        m = self.model
        from chisurf.plugins.microscopy.img_pixel_phasor import analysis

        freq = float(m.frequency) * int(m.harmonic)
        return [(tau, *analysis.lifetime_to_phasor(tau, freq)) for tau in m._tau_list()]

    def _draw_results(self, box: tuple[float, float, float, float]) -> None:
        m = self.model
        freq = float(m.frequency) * int(m.harmonic)
        im.text_colored(f"Effective f = {freq:g} MHz", (0.35, 0.75, 1.0, 1.0))
        rows = self._rows()
        table_h = min(float(box[3]) - 46.0, len(rows) * 24.0 + 34.0)
        if im.begin_table("phasor_rows", 3, _TABLE_FLAGS, (0, max(60.0, table_h))):
            im.table_setup_column("τ (ns)", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("g", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("s", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()
            im.set_item_tooltip(
                "Each reference lifetime τ and its phasor coordinates at the "
                "effective frequency: g the real part, s the imaginary part."
            )
            for tau, g, s in rows:
                im.table_next_row()
                im.table_set_column_index(0)
                im.text_unformatted(f"{tau:g}")
                im.table_set_column_index(1)
                im.text_unformatted(f"{g:.3f}")
                im.table_set_column_index(2)
                im.text_unformatted(f"{s:.3f}")
            im.end_table()


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


__all__ = ["PhasorCalcApp", "WINDOW_BG"]


def make_app(**kwargs):
    """Construct the standalone EMTK phasor calculator."""
    from chisurf.emtk.i18n import install

    install()
    from types import SimpleNamespace

    from .model import _PhasorCalcModel

    return PhasorCalcApp(SimpleNamespace(_model=_PhasorCalcModel()))
