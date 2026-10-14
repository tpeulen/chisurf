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
from emtk.i18n import tr
from emtk.im_core import Col

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.typed_field import typed_number_field
from chisurf.plugins.emtk_layout import action_button, action_caption, same_line_or_wrap

if TYPE_CHECKING:
    from .alternation import AlexAlternationPanel
    from .legacy_export_panel import LegacyExportPanel
    from .titration import TitrationPanel

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BORDER = (55, 60, 72, 255)
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


def _typed_number(gui: Any, key: str, label: str, value, minimum, maximum, integer: bool = True):
    """A typed number field of *gui* (rect remembered as *key*); the committed number, else *value*."""
    committed, _ = typed_number_field(
        key,
        value,
        gui._number_buffers,
        integer=integer,
        minimum=minimum,
        maximum=maximum,
        label=label,
    )
    gui.remember(key)
    return value if committed is None else committed


class LegacyExportGui(TourTarget):
    """EMTK GUI for the ALEX-Suite five-file CSV export."""

    def __init__(
        self,
        panel: Any,
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

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def files(self) -> list[str]:
        return [str(p) for p in getattr(self.panel, "_bur_files", [])]

    def draw(self, w: float = 0.0, h: float = 0.0, y_offset: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 760.0)
        height = float(h or vp.size[1] or 560.0)

        im.set_next_window_pos((0.0, y_offset), im.Cond.ALWAYS)
        im.set_next_window_size((width, max(100.0, height - y_offset)), im.Cond.ALWAYS)
        if im.begin(
            "##legacy_export",
            (0.0, y_offset, width, max(100.0, height - y_offset)),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE,
        ):
            im.text_wrapped(
                tr(
                    "The five CSV files the old ALEX-Suite wrote — for scripts "
                    "built on that layout. The analysis itself stays in the "
                    ".pto container and the burst companions beside it."
                )
            )
            im.separator()

            files = self.files()
            if files:
                if self.selected_index >= len(files):
                    self.selected_index = len(files) - 1
                im.set_next_item_width(-160.0)
                changed, new_idx = im.combo("##BurstFile", self.selected_index, files)
                im.set_item_tooltip(
                    tr("Burst file (from the burst search) whose data is exported.")
                )
                if changed:
                    self.selected_index = new_idx
                self.remember("burst_file")
            else:
                im.text_colored("No bursts yet — run the burst search first.", (0.9, 0.6, 0.3, 1.0))

            im.spacing()
            # Leave room for the labels on the right (a full-width field pushed "Buffer" past the edge).
            im.set_next_item_width(-80.0)
            ch, self.sample_text = im.input_text_with_hint(
                "Sample", self.sample_text, "e.g. dsDNA 15 bp, Cy3B/ATTO647N"
            )
            im.set_item_tooltip(tr("Sample description written into the CSV metadata."))
            im.set_next_item_width(-80.0)
            ch, self.buffer_text = im.input_text_with_hint(
                "Buffer", self.buffer_text, "e.g. TE + 100 mM NaCl"
            )
            im.set_item_tooltip(tr("Buffer description written into the CSV metadata."))

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
                im.set_item_tooltip(tr("Include this part in the CSV export."))
            self.remember("parts")

            im.separator()
            if im.button(tr("💾 Write ALEX-Suite CSVs"), role="primary"):
                self.panel.run_export(
                    source=files[self.selected_index] if files else "",
                    sample=self.sample_text,
                    buffer=self.buffer_text,
                    parts=dict(self.parts),
                )
            im.set_item_tooltip(
                tr("Write the five ALEX-Suite CSV files beside the selected burst file.")
            )
            self.remember("run")

            same_line_or_wrap(action_caption("help"))
            if action_button("help"):
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


class TitrationGui(TourTarget):
    """EMTK GUI for the titration step, over the Qt-free view model."""

    def __init__(
        self,
        panel: Any,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.panel = panel
        self.on_guide = on_guide
        self.on_help = on_help

        # Editable mirrors of the table cells, keyed by (row, key); committed
        # to the model on every edit so the two never drift apart.
        self._cell_edits: dict[tuple[int, str], str] = {}
        self._number_buffers: dict[str, str] = {}

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
            "series",
            "🧪 Titration series & fit",
            self._draw_series,
            dock="series",
            closable=False,
        )
        self.docks.add_window(
            "stack", "📊 Stack plot", self._draw_stack, dock="stack", closable=False
        )
        self.docks.add_window(
            "binding", "🔗 Binding isotherm", self._draw_binding, dock="binding", closable=False
        )

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

    def draw(self, w: float = 0.0, h: float = 0.0, y_offset: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1000.0)
        height = float(h or vp.size[1] or 700.0)
        self.docks.draw((0.0, y_offset, width, max(100.0, height - y_offset)))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the series & fit dock ─────────────────────────────────────────────

    def _draw_series(self, box: tuple[float, float, float, float]) -> None:
        model = self.model

        if im.button(tr("➕ Add burst files…")):
            model.browse_files()
        im.set_item_tooltip(tr("Add burst files as titration points (one concentration each)."))
        self.remember("add_files")
        same_line_or_wrap("➖")
        if im.button("➖"):
            model.remove_last_row()
        im.set_item_tooltip(tr("Remove the last row of the titration series."))
        same_line_or_wrap("🗑️")
        if im.button("🗑️"):
            model.clear_rows()
        im.set_item_tooltip(tr("Clear the whole titration series."))
        same_line_or_wrap(tr("📈 Fit series"))
        if im.button(tr("📈 Fit series"), role="primary"):
            model.run()
        im.set_item_tooltip(tr("Fit the selected binding model to the titration series."))
        self.remember("run")
        same_line_or_wrap(tr("💾 Export CSV"))
        if im.button(tr("💾 Export CSV")):
            self.panel.export_csv()
        im.set_item_tooltip(tr("Export the titration series and fit results to a CSV file."))
        self.remember("export")
        same_line_or_wrap(action_caption("help"))
        if action_button("help"):
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
                im.set_item_tooltip(tr("Concentration of this titration point (see Unit below)."))
                if changed:
                    self._cell_edits[(i, "concentration")] = text
                    model.update_series_cell(i, "concentration", text)
                im.table_set_column_index(1)
                im.text_disabled(row["name"])
            im.end_table()
        self.remember("series_table")

        im.spacing()
        if im.collapsing_header("Fit", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip(tr("Configure fit model and parameters."))
            model.n_populations = _typed_number(
                self, "n_populations", "Populations", model.n_populations, 1, 6
            )
            im.set_item_tooltip(tr("Number of FRET populations fitted in each histogram."))
            options = model.binding_model_options()
            idx = options.index(model.binding_model) if model.binding_model in options else 0
            changed, new_idx = im.combo("Isotherm", idx, options)
            im.set_item_tooltip(tr("Binding model fitted to the fractions across the series."))
            if changed and 0 <= new_idx < len(options):
                model.binding_model = options[new_idx]
            changed, model.concentration_unit = im.input_text("Unit", model.concentration_unit)
            im.set_item_tooltip(tr("Concentration unit label used on the axes (e.g. nM)."))
            _, model.fix_peak_positions = im.checkbox(
                tr("Fix peak positions"), model.fix_peak_positions
            )
            im.set_item_tooltip(
                tr(
                    "Hold the peak positions and widths at their starting values (the old program's "
                    "fixed x0 and sigma). Off: they are fitted, shared by every concentration."
                )
            )

        # The tooltip follows the header whether it is open or not (inside the branch a closed header had none).
        filters_open = im.collapsing_header("Burst filters", 0)
        im.set_item_tooltip(tr("Configure photon and stoichiometry filters."))
        if filters_open:
            # Ranges of the Qt form (titration.view.json).
            model.min_photons = _typed_number(
                self, "min_photons", "Min. photons", model.min_photons, 0, 100000
            )
            im.set_item_tooltip(tr("Minimum photons per burst included in the histograms."))
            model.bins = _typed_number(self, "bins", "E bins", model.bins, 11, 501)
            im.set_item_tooltip(tr("Number of bins of the FRET efficiency histograms."))
            model.s_low = _typed_number(
                self, "s_low", "S gate from", model.s_low, -1.0, 2.0, integer=False
            )
            im.set_item_tooltip(tr("Lower stoichiometry gate applied before fitting."))
            model.s_high = _typed_number(
                self, "s_high", "S gate to", model.s_high, -1.0, 2.0, integer=False
            )
            im.set_item_tooltip(tr("Upper stoichiometry gate applied before fitting."))
            model.gamma = _typed_number(
                self, "gamma", "gamma", model.gamma, 0.0, 100.0, integer=False
            )
            im.set_item_tooltip(tr("Gamma detection-efficiency correction used by the fit."))
            model.beta = _typed_number(self, "beta", "beta", model.beta, 0.0, 100.0, integer=False)
            im.set_item_tooltip(tr("Beta direct-excitation correction used by the fit."))

        im.spacing()
        im.separator()
        im.text_colored("Result", (0.35, 0.75, 1.0, 1.0))
        _draw_summary(model.summary or "")

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
                        if s.get("style") == "dash":
                            implot.set_next_line_style((170, 170, 170, 255), 2.0, dash=(5.0, 3.0))
                        implot.plot_line(s.get("name") or "histogram", xs, ys)
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


class AlexAlternationGui(TourTarget):
    """EMTK GUI for the µs-ALEX alternation step.

    The panel (:class:`~.alternation.AlexAlternationPanel`) keeps the workflow
    logic — detection, conversion, publishing the setup — and this GUI renders
    its state: the channel assignment, the period, the two editable laser
    gates (numbers here, draggable bands on the plot — one edit, as before)
    and the folded phase histogram that says whether the answer is right.
    """

    def __init__(
        self,
        panel: Any,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.panel = panel
        self.on_guide = on_guide
        self.on_help = on_help
        self._number_buffers: dict[str, str] = {}

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
            "controls",
            "🚦 Alternation detection",
            self._draw_controls,
            dock="controls",
            closable=False,
        )
        self.docks.add_window(
            "phase",
            "📉 Folded phase per detector",
            self._draw_phase,
            dock="phase",
            closable=False,
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

    def draw(self, w: float = 0.0, h: float = 0.0, y_offset: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1000.0)
        height = float(h or vp.size[1] or 700.0)
        self.docks.draw((0.0, y_offset, width, max(100.0, height - y_offset)))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the controls dock ─────────────────────────────────────────────────

    def _draw_controls(self, box: tuple[float, float, float, float]) -> None:
        panel = self.panel

        im.text_wrapped(
            tr(
                "µs-ALEX only — already PIE / ns-ALEX? Skip this step; the setup "
                "step already has your detector definition."
            )
        )
        im.separator()

        _, panel.donor_text = im.input_text_with_hint("Donor channels", panel.donor_text, "auto")
        im.set_item_tooltip(
            tr("Routing channels of the donor; leave 'auto' to detect them from the data.")
        )
        _, panel.acceptor_text = im.input_text_with_hint(
            "Acceptor channels", panel.acceptor_text, "auto"
        )
        im.set_item_tooltip(
            tr("Routing channels of the acceptor; leave 'auto' to detect them from the data.")
        )
        self.remember("channels")

        im.spacing()
        if im.button(tr("🚦 Detect alternation and convert"), role="primary"):
            panel.run(convert=True)
        im.set_item_tooltip(
            tr(
                "Detect the µs-ALEX period and fold the photons into donor/acceptor excitation periods."
            )
        )
        self.remember("run")

        im.same_line()
        if im.button(tr("🔎 Detect only")):
            panel.run(convert=False)
        im.set_item_tooltip(tr("Detect the alternation period without converting the data."))
        self.remember("detect_only")
        im.same_line()
        if action_button("help"):
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
            # Ranges of the Qt spin boxes: the period up to 1e8, each gate edge inside the period.
            panel.period = _typed_number(
                self, "period", "Period (units)", panel.period, 0, 100_000_000
            )
            im.set_item_tooltip(
                tr(
                    "ALEX alternation period in macro-time units; leave 0 to measure it from the data."
                )
            )
            windows = panel.windows or {}
            for name, label in (("green", "Donor excitation"), ("red", "Acceptor excitation")):
                bounds = windows.get(name, [0, 0])
                old_lo, old_hi = int(bounds[0]), int(bounds[1])
                # A full-row first field would push the "to" field off the dock's right edge.
                im.set_next_item_width(120)
                lo = _typed_number(self, f"{name}_from", f"{label} from", old_lo, 0, panel.period)
                im.set_item_tooltip(f"Start of the {label.lower()} gate in macro-time units.")
                im.same_line()
                im.set_next_item_width(120)
                hi = _typed_number(self, f"{name}_to", "to", old_hi, 0, panel.period)
                im.set_item_tooltip(f"End of the {label.lower()} gate in macro-time units.")
                if (lo, hi) != (old_lo, old_hi):
                    panel.set_gate(name, lo, hi)
            self.remember("gates")
        else:
            im.text_disabled(tr("Period: auto — measured from the data on arrival."))

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
                    # An x tag marks a position: at the half period it said "period 8000" at x = 4000.
                    implot.tag_x(
                        period * 0.5,
                        (0.6, 0.6, 0.6, 1.0),
                        fmt=f"period/2 = {period * 0.5:g}",
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


class AlexAlternationState:
    """Standalone state container for the µs-ALEX alternation step."""

    def __init__(self) -> None:
        self.donor_text: str = "auto"
        self.acceptor_text: str = "auto"
        self.period: int = 0
        self.windows: dict[str, list[int]] | None = None
        self.status_text: str = "µs-ALEX alternation: drop TTTR files or set channel routing."
        self.detail_text: str = ""
        self.detail_note: str = ""
        self.phase_hist: dict[str, Any] = {}
        self._files: list[Path] = []
        self._converted: list[Path] = []
        self._result: dict[str, Any] | None = None

    def set_files(self, files: list[str | Path]) -> None:
        self._files = [Path(p) for p in files]
        if self._files:
            self.status_text = f"{len(self._files)} file(s) loaded."

    def set_gate(self, name: str, lo: int, hi: int) -> None:
        if self.windows is None:
            self.windows = {}
        self.windows[name] = [int(lo), int(hi)]
        self.status_text = (
            f"Gates updated: green {self.windows.get('green')}, red {self.windows.get('red')}."
        )

    def run(self, *, convert: bool = True) -> None:
        if not self._files:
            self.status_text = "No files loaded — drop TTTR files (.sm, .ptu) first."
            return
        try:
            donor = [
                int(c.strip()) for c in self.donor_text.split(",") if c.strip().isdigit()
            ] or None
            acceptor = [
                int(c.strip()) for c in self.acceptor_text.split(",") if c.strip().isdigit()
            ] or None
        except Exception as exc:
            self.status_text = f"Invalid channels: {exc}"
            return
        from chisurf.plugins.burst.alex_suite.api.convert import detect_and_convert

        manual_period = int(self.period) or None
        try:
            outcome = detect_and_convert(
                self._files,
                donor_channels=donor,
                acceptor_channels=acceptor,
                period=manual_period,
                dry_run=not convert,
            )
            self._result = outcome
            self.period = int(outcome["period"])
            self.windows = dict(outcome["windows"])
            self.donor_text = ", ".join(str(c) for c in outcome["donor_channels"])
            self.acceptor_text = ", ".join(str(c) for c in outcome["acceptor_channels"])
            self.phase_hist = outcome.get("phase_hist", {})
            self._converted = list(outcome.get("converted", []))
            self.status_text = f"Detected period: {self.period} units."
            self.detail_text = f"Period: {self.period} | Green: {self.windows.get('green')} | Red: {self.windows.get('red')}"
        except Exception as exc:
            self.status_text = f"Detection failed: {exc}"


class TitrationState:
    """Standalone state container for the titration step."""

    def __init__(self) -> None:
        from .titration_view_model import TitrationViewModel

        self.model = TitrationViewModel()

    def set_burst_files(self, files: list[str | Path]) -> None:
        self.model.add_files([str(p) for p in files])

    def export_csv(self, path: str = "titration.csv") -> None:
        try:
            self.model.export_csv(path)
        except Exception as exc:
            logger.warning(f"Titration export failed: {exc}")


class LegacyExportState:
    """Standalone state container for the ALEX-Suite CSV export step."""

    def __init__(self) -> None:
        self._bur_files: list[Path] = []
        self._status_text: str = "Drop burst files (.bur, .pto) here to export."

    def set_burst_files(self, files: list[str | Path]) -> None:
        self._bur_files = [Path(p) for p in files]
        if self._bur_files:
            self._status_text = f"{len(self._bur_files)} burst file(s) available."

    def run_export(self, source: str, sample: str, buffer: str, parts: dict) -> None:
        if not source:
            self._status_text = "Pick a burst file first."
            return
        from chisurf.plugins.burst.alex_suite.api.histograms import es_histograms
        from chisurf.plugins.burst.alex_suite.api.legacy_export import (
            LegacyExport,
            Metadata,
            write_legacy_export,
        )

        path = Path(source)
        try:
            histograms = es_histograms(path)
            burst_table = None
            if parts.get("original_bursts"):
                from chisurf.core.fluorescence.burst.table import read_burst_table

                burst_table = read_burst_table(path)
            written = write_legacy_export(
                path.with_suffix(""),
                histograms,
                metadata=Metadata(sample_name=sample, buffer=buffer),
                parts=LegacyExport(**{key: bool(v) for key, v in parts.items()}),
                burst_table=burst_table,
            )
            self._status_text = f"Wrote {len(written)} file(s) in {path.parent}"
        except Exception as exc:
            self._status_text = f"Export failed: {exc}"


class AlexSuiteGui(TourTarget):
    """Unified immediate-mode GUI for the ALEX Suite workflow steps."""

    def __init__(
        self,
        owner: Any = None,
        on_help: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
    ) -> None:
        self.owner = owner
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        self.alternation_state = AlexAlternationState()
        self.titration_state = TitrationState()
        self.export_state = LegacyExportState()

        self.alternation_gui = AlexAlternationGui(self.alternation_state)
        self.titration_gui = TitrationGui(self.titration_state)
        self.export_gui = LegacyExportGui(self.export_state)

        self.selected_tab: str = "alternation"
        self.on_help = on_help
        self.on_guide = on_guide
        self.help_window = _make_help(self.owner or self, "ALEX Suite — Help & Reference")
        self.tour = _make_tour(self.owner or self, self.item_rects)

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

        bar_h = 36.0
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, bar_h), im.Cond.ALWAYS)
        flags = (
            im.WindowFlags.NO_TITLE_BAR
            | im.WindowFlags.NO_RESIZE
            | im.WindowFlags.NO_MOVE
            | im.WindowFlags.NO_SCROLLBAR
        )
        if im.begin("##alex_suite_tabs", (0.0, 0.0, width, bar_h), flags):
            im.text_colored("ALEX Suite", (0.35, 0.75, 1.0, 1.0))
            im.same_line()
            im.separator()
            im.same_line()

            tabs = [
                ("alternation", "🚦 Alternation"),
                ("titration", "🧪 Titration"),
                ("export", "💾 Legacy Export"),
            ]
            for tab_id, tab_label in tabs:
                is_selected = self.selected_tab == tab_id
                if is_selected:
                    im.push_style_color(Col.BUTTON, ACCENT_BLUE)
                if im.button(f"{tab_label}##nav_{tab_id}"):
                    self.selected_tab = tab_id
                im.set_item_tooltip(f"Switch to {tab_label}.")
                self.remember(f"tab_{tab_id}")
                if is_selected:
                    im.pop_style_color(1)
                im.same_line()

            im.separator()
            im.same_line()
            if action_button("guide", id="suite_guide"):
                self.start_guide()
            self.remember("guide_button")

            im.same_line()
            if action_button("help", id="suite_help"):
                self.show_help()
            self.remember("help_button")
        im.end()

        # Render active tab sub-gui below the top navigation bar
        if self.selected_tab == "alternation":
            self.alternation_gui.draw(width, height, y_offset=bar_h)
        elif self.selected_tab == "titration":
            self.titration_gui.draw(width, height, y_offset=bar_h)
        elif self.selected_tab == "export":
            self.export_gui.draw(width, height, y_offset=bar_h)

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)


class AlexSuiteApp(ImApp):
    """The unified EMTK ImApp for the ALEX Suite."""

    def __init__(self, **kwargs: Any) -> None:
        self.suite_gui = AlexSuiteGui(owner=self)
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        rects = dict(self.suite_gui.item_rects)
        rects.update(self.suite_gui.alternation_gui.item_rects)
        rects.update(self.suite_gui.titration_gui.item_rects)
        rects.update(self.suite_gui.export_gui.item_rects)
        return rects

    def start_guide(self) -> None:
        self.suite_gui.start_guide()

    def show_help(self) -> None:
        self.suite_gui.show_help()

    def on_files_dropped(self, paths: list[str]) -> bool:
        paths = [str(p) for p in paths]
        if not paths:
            return False
        tttr_exts = {".sm", ".ptu", ".spc", ".ht3", ".t3r"}
        burst_exts = {".bur", ".pto", ".csv", ".txt"}
        for p in paths:
            ext = Path(p).suffix.lower()
            if ext in tttr_exts:
                self.suite_gui.alternation_state.set_files([p])
                self.suite_gui.selected_tab = "alternation"
            elif ext in burst_exts:
                self.suite_gui.titration_state.set_burst_files([p])
                self.suite_gui.export_state.set_burst_files([p])
                if self.suite_gui.selected_tab == "alternation":
                    self.suite_gui.selected_tab = "titration"
        return True

    files_dropped = on_files_dropped

    def _render(self) -> None:
        vp = im.get_main_viewport()
        w, h = vp.size[0] or 1200.0, vp.size[1] or 800.0
        self.suite_gui.draw(w, h)


def make_app(**kwargs: Any) -> AlexSuiteApp:
    from chisurf.emtk.i18n import install

    install()
    return AlexSuiteApp(**kwargs)


def _draw_summary(summary: str) -> None:
    """Draw the fit summary: its text lines, and its population table as a table.

    The summary is markdown (``**bold**`` and a ``| … |`` table). Printed line by line it showed the table as raw
    ``| 0 | 0.218 |`` and ``|---|`` rows; the canvas's markdown renderer uses a face the rest of the panel does not.
    """
    rows: list[list[str]] = []

    def flush() -> None:
        if not rows:
            return
        header, *body = rows
        if im.begin_table("titration_summary", len(header)):
            for name in header:
                im.table_setup_column(name)
            im.table_headers_row()
            for row in body:
                im.table_next_row()
                for cell in row:
                    im.table_next_column()
                    im.text(cell)
            im.end_table()
        rows.clear()

    for line in summary.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):  # not the |---| separator
                rows.append(cells)
            continue
        flush()
        if stripped:
            text = stripped.replace("**", "")
            if (
                len(text) > 1 and text.startswith("_") and text.endswith("_")
            ):  # an _emphasised_ line
                text = text[1:-1]
            im.text_wrapped(text)
    flush()


__all__ = [
    "WINDOW_BG",
    "AlexAlternationApp",
    "AlexAlternationGui",
    "AlexAlternationState",
    "AlexSuiteApp",
    "AlexSuiteGui",
    "LegacyExportApp",
    "LegacyExportGui",
    "LegacyExportState",
    "TitrationApp",
    "TitrationGui",
    "TitrationState",
    "make_app",
]
