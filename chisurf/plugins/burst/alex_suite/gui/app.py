"""EMTK immediate-mode UIs for the ALEX Suite's own workflow steps.

Three panels, one file, because they are one workflow's steps rather than
three tools: the µs-ALEX alternation (step 3), the titration series and the
ALEX-Suite-compatible CSV export. Each app renders inside the EMTK canvas of
the workflow shell — no Qt widgets, no modal dialogs — while the panels in
:mod:`.alternation`, :mod:`.titration` and :mod:`.legacy_export_panel` keep
the workflow hand-off API (``set_files``, ``set_burst_files``, …) and the
Qt-free models behind them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

if TYPE_CHECKING:
    from .alternation import AlexAlternationPanel
    from .legacy_export_panel import LegacyExportPanel
    from .titration import TitrationPanel

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_ORANGE = (255, 127, 14, 255)
ACCENT_RED = (214, 39, 40, 255)
ACCENT_GRAY = (158, 158, 158, 255)
TEXT_DIM = (160, 160, 160, 255)
TEXT_BRIGHT = (240, 240, 240, 255)
GATE_GREEN_FILL = (44, 160, 44, 48)
GATE_RED_FILL = (214, 39, 40, 48)

_TABLE_FLAGS = im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE


def _make_help(widget: Any, title: str) -> EmTkHelpWindow:
    return EmTkHelpWindow(
        title=title,
        resource=Path(__file__).parent / "help.md",
        owner=widget,
        size=(720.0, 540.0),
    )


def _make_tour(widget: Any, item_rects: dict) -> EmTkGuidedTour:
    return EmTkGuidedTour(
        steps=Path(__file__).parent / "guide.json",
        get_target_rect=lambda k: item_rects.get(k),
        owner=widget,
    )


# ═══════════════════════════════════════════════════════════════════════
# Legacy export — the five CSV files the old ALEX-Suite wrote
# ═══════════════════════════════════════════════════════════════════════


class LegacyExportGui:
    """EMTK GUI for the ALEX-Suite five-file CSV export."""

    def __init__(
        self,
        panel: LegacyExportPanel,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.panel = panel
        self.on_guide = on_guide
        self.on_help = on_help

        # Mirrors the Qt panel's widgets; committed straight to the export call.
        self.selected_index: int = 0
        self.sample_text: str = ""
        self.buffer_text: str = ""
        self.parts: dict[str, bool] = {
            "metadata": True,
            "e_histogram": True,
            "s_histogram": True,
            "histogram_2d": True,
            "original_bursts": False,
        }

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        self.help_window = _make_help(panel, "ALEX-Suite CSV Export — Help & Reference")
        self.tour = _make_tour(panel, self.item_rects)

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def files(self) -> list[str]:
        return [str(p) for p in self.panel._bur_files]

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 760.0)
        height = float(h or vp.size[1] or 560.0)

        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)
        if im.begin(
            "##legacy_export",
            (0.0, 0.0, width, height),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE,
        ):
            im.text_wrapped(
                "The five CSV files the old ALEX-Suite wrote — for scripts "
                "built on that layout. The analysis itself stays in the "
                ".pto container and the burst companions beside it."
            )
            im.separator()

            files = self.files()
            if files:
                if self.selected_index >= len(files):
                    self.selected_index = len(files) - 1
                im.set_next_item_width(-160.0)
                changed, new_idx = im.combo("##BurstFile", self.selected_index, files)
                if changed:
                    self.selected_index = new_idx
                self.remember("burst_file")
            else:
                im.text_colored("No bursts yet — run the burst search first.", (0.9, 0.6, 0.3, 1.0))

            im.spacing()
            ch, self.sample_text = im.input_text_with_hint(
                "Sample", "e.g. dsDNA 15 bp, Cy3B/ATTO647N", self.sample_text
            )
            ch, self.buffer_text = im.input_text_with_hint(
                "Buffer", "e.g. TE + 100 mM NaCl", self.buffer_text
            )

            im.separator()
            labels = (
                ("metadata", "Metadata"),
                ("e_histogram", "E histogram"),
                ("s_histogram", "S histogram"),
                ("histogram_2d", "2-D histogram"),
                ("original_bursts", "All bursts"),
            )
            for i, (key, label) in enumerate(labels):
                if i:
                    im.same_line()
                _, self.parts[key] = im.checkbox(f"{label}##{key}", self.parts[key])
            self.remember("parts")

            im.separator()
            im.push_style_color(Col.BUTTON, ACCENT_GREEN)
            im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
            im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
            if im.button("💾 Write ALEX-Suite CSVs"):
                self.panel.run_export(
                    source=files[self.selected_index] if files else "",
                    sample=self.sample_text,
                    buffer=self.buffer_text,
                    parts=dict(self.parts),
                )
            im.pop_style_color(3)
            self.remember("run")

            im.same_line()
            if im.button("❓ Help"):
                self.show_help()
            self.remember("help")

            im.spacing()
            im.separator()
            im.text_wrapped(self.panel._status_text or "")
        im.end()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)


class LegacyExportApp(ImApp):
    """The EMTK ImApp for the ALEX-Suite CSV export step."""

    def __init__(self, panel: LegacyExportPanel) -> None:
        self.panel = panel
        self.export_gui = LegacyExportGui(
            panel,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.export_gui.item_rects

    def start_guide(self) -> None:
        self.export_gui.start_guide()

    def show_help(self) -> None:
        self.export_gui.show_help()

    def _render(self) -> None:
        self.export_gui.draw()


# ═══════════════════════════════════════════════════════════════════════
# Titration — a concentration series of FRET histograms
# ═══════════════════════════════════════════════════════════════════════


class TitrationGui:
    """EMTK GUI for the titration step, over the Qt-free view model."""

    def __init__(
        self,
        panel: TitrationPanel,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.panel = panel
        self.on_guide = on_guide
        self.on_help = on_help

        # Editable mirrors of the table cells, keyed by (row, key); committed
        # to the model on every edit so the two never drift apart.
        self._cell_edits: dict[tuple[int, str], str] = {}

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        layout = Split(
            "h",
            0.46,
            Region("series"),
            Split("v", 0.58, Region("stack"), Region("binding")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "series", "🧪 Titration series & fit", self._draw_series, closable=False
        )
        self.docks.add_window("stack", "📊 Stack plot", self._draw_stack, closable=False)
        self.docks.add_window("binding", "🔗 Binding isotherm", self._draw_binding, closable=False)

        self.help_window = _make_help(panel, "Titration — Help & Reference")
        self.tour = _make_tour(panel, self.item_rects)

    # ── state plumbing ────────────────────────────────────────────────────

    @property
    def model(self):
        return self.panel.model

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1000.0)
        height = float(h or vp.size[1] or 700.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the series & fit dock ─────────────────────────────────────────────

    def _draw_series(self, box: tuple[float, float, float, float]) -> None:
        model = self.model

        if im.button("➕ Add burst files…"):
            model.browse_files()
        self.remember("add_files")
        im.same_line()
        if im.button("➖"):
            model.remove_last_row()
        im.same_line()
        if im.button("🗑️"):
            model.clear_rows()
        im.same_line()
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        if im.button("📈 Fit series"):
            model.run()
        im.pop_style_color(1)
        self.remember("run")
        im.same_line()
        if im.button("💾 Export CSV"):
            self.panel.export_csv()
        self.remember("export")
        im.same_line()
        if im.button("❓ Help"):
            self.show_help()
        self.remember("help")

        im.separator()
        rows = model.series_rows()
        table_h = min(220.0, max(80.0, len(rows) * 26.0 + 34.0))
        if im.begin_table("titration_rows", 2, _TABLE_FLAGS, (0, table_h)):
            im.table_setup_column("Concentration", im.TableColumnFlags.WIDTH_FIXED, 150.0)
            im.table_setup_column("Burst file", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()
            for i, row in enumerate(rows):
                im.table_next_row()
                im.table_set_column_index(0)
                current = self._cell_edits.get((i, "concentration"), f"{row['concentration']:g}")
                changed, text = im.input_text(f"##c{i}", current)
                if changed:
                    self._cell_edits[(i, "concentration")] = text
                    model.update_series_cell(i, "concentration", text)
                im.table_set_column_index(1)
                im.text_disabled(row["name"])
            im.end_table()
        self.remember("series_table")

        im.spacing()
        if im.collapsing_header("Fit", im.TreeNodeFlags.DEFAULT_OPEN):
            _, model.n_populations = im.input_int("Populations", model.n_populations, step=1)
            model.n_populations = max(1, min(6, int(model.n_populations)))
            options = model.binding_model_options()
            idx = options.index(model.binding_model) if model.binding_model in options else 0
            changed, new_idx = im.combo("Isotherm", idx, options)
            if changed and 0 <= new_idx < len(options):
                model.binding_model = options[new_idx]
            changed, model.concentration_unit = im.input_text("Unit", model.concentration_unit)
            _, model.fix_peak_positions = im.checkbox(
                "Fix peak positions", model.fix_peak_positions
            )

        if im.collapsing_header("Burst filters", 0):
            _, v = im.input_int("Min. photons", model.min_photons, step=10)
            model.min_photons = max(0, v)
            _, v = im.input_int("E bins", model.bins, step=10)
            model.bins = max(11, v)
            _, model.s_low = im.input_float("S gate from", model.s_low, step=0.05)
            _, model.s_high = im.input_float("S gate to", model.s_high, step=0.05)
            _, model.gamma = im.input_float("gamma", model.gamma, step=0.05)
            _, model.beta = im.input_float("beta", model.beta, step=0.05)

        im.spacing()
        im.separator()
        im.text_colored("Result", (0.35, 0.75, 1.0, 1.0))
        for line in (model.summary or "").splitlines():
            im.text_wrapped(line.replace("**", ""))

    # ── the two plots ─────────────────────────────────────────────────────

    def _draw_stack(self, box: tuple[float, float, float, float]) -> None:
        series = self.model.stack_series()
        if implot.begin_plot("##stack", (-1, -1)):
            implot.setup_axes("FRET efficiency E", "Bursts (offset)")
            implot.setup_legend()
            if series:
                for s in series:
                    xs = np.asarray(s.get("x", []), dtype=np.float64)
                    ys = np.asarray(s.get("y", []), dtype=np.float64)
                    if len(xs) == len(ys) and len(xs):
                        # The dashed shared-shape fit keeps its label so the
                        # legend still tells data and fit apart.
                        name = s.get("name") or ("fit" if s.get("style") == "dash" else "hist")
                        if s.get("style") == "dash" and not name.startswith("fit "):
                            name = f"fit {name}"
                        implot.plot_line(name, xs, ys)
            else:
                implot.plot_dummy("fit the series to see the stack")
            implot.end_plot()

    def _draw_binding(self, box: tuple[float, float, float, float]) -> None:
        model = self.model
        series = model.binding_series()
        axes = model.binding_axes()
        if implot.begin_plot("##binding", (-1, -1)):
            implot.setup_axes(axes.get("x_label", "[ligand]"), axes.get("y_label", "fraction"))
            if axes.get("log_x"):
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_legend()
            if series:
                for s in series:
                    xs = np.asarray(s.get("x", []), dtype=np.float64)
                    ys = np.asarray(s.get("y", []), dtype=np.float64)
                    if len(xs) == len(ys) and len(xs):
                        if s.get("no_line"):
                            implot.plot_scatter(s.get("name", "fractions"), xs, ys)
                        else:
                            implot.plot_line(s.get("name", "isotherm"), xs, ys)
            else:
                implot.plot_dummy("the isotherm appears after the fit")
            implot.end_plot()


class TitrationApp(ImApp):
    """The EMTK ImApp for the titration step."""

    def __init__(self, panel: TitrationPanel) -> None:
        self.panel = panel
        self.titration_gui = TitrationGui(
            panel,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.titration_gui.item_rects

    def start_guide(self) -> None:
        self.titration_gui.start_guide()

    def show_help(self) -> None:
        self.titration_gui.show_help()

    def _render(self) -> None:
        self.titration_gui.draw()


# ═══════════════════════════════════════════════════════════════════════
# Alternation — fold µs-ALEX into the micro-time
# ═══════════════════════════════════════════════════════════════════════


class AlexAlternationGui:
    """EMTK GUI for the µs-ALEX alternation step.

    The panel (:class:`~.alternation.AlexAlternationPanel`) keeps the workflow
    logic — detection, conversion, publishing the setup — and this GUI renders
    its state: the channel assignment, the period, the two editable laser
    gates (numbers here, draggable bands on the plot — one edit, as before)
    and the folded phase histogram that says whether the answer is right.
    """

    def __init__(
        self,
        panel: AlexAlternationPanel,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.panel = panel
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        layout = Split(
            "v",
            0.44,
            Region("controls"),
            Region("phase"),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "controls", "🚦 Alternation detection", self._draw_controls, closable=False
        )
        self.docks.add_window(
            "phase", "📉 Folded phase per detector", self._draw_phase, closable=False
        )

        self.help_window = _make_help(panel, "ALEX Alternation — Help & Reference")
        self.tour = _make_tour(panel, self.item_rects)

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1000.0)
        height = float(h or vp.size[1] or 700.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the controls dock ─────────────────────────────────────────────────

    def _draw_controls(self, box: tuple[float, float, float, float]) -> None:
        panel = self.panel

        im.text_wrapped(
            "µs-ALEX only — already PIE / ns-ALEX? Skip this step; the setup "
            "step already has your detector definition."
        )
        im.separator()

        _, panel.donor_text = im.input_text_with_hint("Donor channels", "auto", panel.donor_text)
        _, panel.acceptor_text = im.input_text_with_hint(
            "Acceptor channels", "auto", panel.acceptor_text
        )
        self.remember("channels")

        im.spacing()
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🚦 Detect alternation and convert"):
            panel.run(convert=True)
        im.pop_style_color(3)
        self.remember("run")

        im.same_line()
        if im.button("🔎 Detect only"):
            panel.run(convert=False)
        self.remember("detect_only")
        im.same_line()
        if im.button("❓ Help"):
            self.show_help()
        self.remember("help")

        im.spacing()
        im.separator()
        if panel.detail_text:
            for line in panel.detail_text.splitlines():
                im.text_colored(line, (0.75, 0.85, 1.0, 1.0))
        if panel.detail_note:
            im.text_wrapped(panel.detail_note)

        im.spacing()
        enabled = panel.period > 0
        if enabled:
            _, panel.period = im.input_int("Period (units)", panel.period, step=100)
            panel.period = max(0, panel.period)
            self.remember("period")
            windows = panel.windows or {}
            for name, label in (("green", "Donor excitation"), ("red", "Acceptor excitation")):
                bounds = windows.get(name, [0, 0])
                changed_lo, lo = im.input_int(f"{label} from##{name}", int(bounds[0]), step=10)
                im.same_line()
                changed_hi, hi = im.input_int(f"to##{name}", int(bounds[1]), step=10)
                if changed_lo or changed_hi:
                    panel.set_gate(name, int(lo), int(hi))
            self.remember("gates")
        else:
            im.text_disabled("Period: auto — measured from the data on arrival.")

        im.spacing()
        im.separator()
        im.text_wrapped(panel.status_text or "")

    # ── the phase plot ────────────────────────────────────────────────────

    def _draw_phase(self, box: tuple[float, float, float, float]) -> None:
        panel = self.panel
        hist = panel.phase_hist
        if implot.begin_plot("##phase", (-1, -1)):
            implot.setup_axes("ALEX phase (macro-time units)", "Photons")
            implot.setup_legend()
            centres = hist.get("centres")
            if centres is not None:
                implot.plot_line("donor", centres, hist["donor"])
                implot.plot_line("acceptor", centres, hist["acceptor"])
                period = float(hist.get("period") or 0.0)
                top = float(max(np.max(hist["donor"]), np.max(hist["acceptor"]), 1.0))
                windows = panel.windows or {}
                for name, fill in (("green", GATE_GREEN_FILL), ("red", GATE_RED_FILL)):
                    bounds = windows.get(name)
                    if bounds and period > 0:
                        res = implot.drag_rect(
                            _GATE_IDS[name],
                            float(bounds[0]),
                            0.0,
                            float(bounds[1]),
                            top * 1.1,
                            fill,
                        )
                        if res.modified:
                            panel.set_gate(name, int(round(res.x_min)), int(round(res.x_max)))
                if period > 0:
                    implot.tag_x(
                        period * 0.5,
                        (0.6, 0.6, 0.6, 1.0),
                        fmt=f"period {period:g}",
                    )
            else:
                implot.plot_dummy("arrive with files to see the folded phase")
            implot.end_plot()
        self.remember("phase_plot")


#: Stable drag-rect ids for the two gates (any per-frame id would churn).
_GATE_IDS = {"green": 701, "red": 702}


class AlexAlternationApp(ImApp):
    """The EMTK ImApp for the µs-ALEX alternation step."""

    def __init__(self, panel: AlexAlternationPanel) -> None:
        self.panel = panel
        self.alternation_gui = AlexAlternationGui(
            panel,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.alternation_gui.item_rects

    def start_guide(self) -> None:
        self.alternation_gui.start_guide()

    def show_help(self) -> None:
        self.alternation_gui.show_help()

    def _render(self) -> None:
        self.alternation_gui.draw()


__all__ = [
    "WINDOW_BG",
    "AlexAlternationApp",
    "LegacyExportApp",
    "TitrationApp",
]
