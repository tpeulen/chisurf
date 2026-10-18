"""The Burst Browser tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstBrowserApp`) over
:class:`~.view_model.BurstBrowserViewModel`:
- Docking & Draggable Windows: All panels (Controls, Gating, Bursts, Histogram) are
  dockable, draggable, resizable and floatable via an EMTK dockspace.
- Interactive Region Dropping & Dragging:
  - On the Histogram plot, an interactive shaded region (:func:`implot.drag_rect`)
    and tag labels (:func:`implot.tag_x`) allow dragging boundaries live on the plot.
  - Drag-and-drop region payloads can be dropped directly onto the plot target.
- Left pane: Data source (Open folder/file, path display), detector & column selection.
- Gating pane: Interactive E/S/size limits, region presets with drag-source, status.
- Center pane: Gated per-burst table with pagination and multi-row selection.
- Right pane: Live histogram of the selected column with emtk.implot.

Runs toolkit-free in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.im_core import get_current_context
from emtk.widgets.data_table import TableBinding, draw_table

from chisurf.core.datastore import column_names, column_values, is_missing
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.typed_field import typed_number_field
from chisurf.plugins.emtk_layout import action_button, window_size

from ..view_model import BurstBrowserViewModel

__all__ = ["BurstBrowserApp", "BurstBrowserGui", "WINDOW_BG"]

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)
REGION_FILL = (46, 117, 182, 60)
REGION_BORDER = (90, 160, 240, 255)


class BurstBrowserGui:
    """Immediate-mode GUI logic and rendering for the Burst Browser with dockable windows."""

    def __init__(
        self,
        model: BurstBrowserViewModel | None = None,
        on_open_folder: Callable[[], None] | None = None,
        on_open_file: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else BurstBrowserViewModel()
        self.on_open_folder = on_open_folder
        self.on_open_file = on_open_file
        self.on_guide = on_guide
        self.on_help = on_help

        self.page: int = 0
        self.page_size: int = 50
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self._number_buffers: dict[str, str] = {}
        self.on_used: Callable[[str], None] | None = None
        self.controller: Any | None = None
        self._burst_table: TableBinding | None = None
        self._table_token: tuple[Any, ...] | None = None
        self._table_rows: list[dict[str, Any]] = []
        from pathlib import Path

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Browser — Help & Reference",
            resource=help_resource,
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.model,
            wait_for_controls=True,
        )
        self.on_used = self.tour.notify_used  # an action step waits for its control
        self.model.add_observer(self._on_model_event)
        from emtk.docking import DockManager, Region, Split

        self.docks = DockManager(
            Split(
                "h",
                0.30,
                Split("v", 0.5, Region("controls"), Region("gates")),
                Split("h", 0.55, Region("table"), Region("histogram")),
            ),
            name="burst_browser",
        )
        self.docks.add_window("controls", "Data & columns", self._draw_controls, dock="controls")
        self.docks.add_window(
            "gates", "Burst gates", lambda box: self._draw_gating_controls(), dock="gates"
        )
        self.docks.add_window(
            "table", "Bursts table", lambda box: self._draw_table_view(), dock="table"
        )
        self.docks.add_window(
            "histogram", "Histogram", lambda box: self._draw_histogram_view(), dock="histogram"
        )

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def _draw_controls(self, box):
        self._draw_source_controls()
        if getattr(self, "controller", None):
            self.controller.draw_controls(remember=self.remember, track=self.track)
        self._draw_column_selectors()

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def _on_model_event(self, event: str) -> None:
        self._table_token = None
        if event in ("data", "gating"):
            self.page = 0

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float, h: float) -> None:
        self.docks.draw((0.0, 0.0, float(w), float(h)))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))

        if self.tour.active:
            self.tour.draw(float(w), float(h))

    def _draw_source_controls(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        im.text_colored(ACCENT_BLUE, "Data Source")
        btn_w = max(60.0, (avail_w - 6.0) * 0.5)
        if im.button(tr("Open Folder"), (btn_w, 24.0)):
            self.track("open_folder")
            if callable(self.on_open_folder):
                self.on_open_folder()
        im.set_item_tooltip(tr("Open a folder of .bur burst files (with their companions)."))
        self.remember("open_folder")

        im.same_line()
        if im.button(tr("Open File"), (btn_w, 24.0)):
            self.track("open_file")
            if callable(self.on_open_file):
                self.on_open_file()
        im.set_item_tooltip(tr("Open a single .bur burst file or .pto container."))
        self.remember("open_file")

        if action_button("guide", size=(btn_w, 24.0)):
            self.track("guide")
            self.start_guide()
        self.remember("guide")

        im.same_line()
        if action_button("help", size=(btn_w, 24.0)):
            self.track("help")
            self.show_help()
        self.remember("help")

        path = self.model.path_text
        if len(path) > 36:
            path = "…" + path[-34:]
        im.text_colored(ACCENT_GRAY, f"Path: {path}")

    def _draw_column_selectors(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        im.text_colored(ACCENT_BLUE, "Columns & Detectors")

        # Detector combo
        dets = self.model.detector_options()
        cur_det_idx = 0
        if self.model.detector in dets:
            cur_det_idx = dets.index(self.model.detector)
        im.set_next_item_width(avail_w)
        im.text(tr("Detector:"))
        # The first entry is the "All" choice, a word of the window; the rest are detector names.
        changed, new_det_idx = im.combo("##det", cur_det_idx, [tr(dets[0]), *dets[1:]])
        im.set_item_tooltip(tr("Detector (channel group) whose bursts are shown."))
        self.remember("detector")
        if changed and 0 <= new_det_idx < len(dets):
            self.track("detector")
            self.model.on_detector_changed(dets[new_det_idx])

        im.spacing()

        # Histogram column combo
        cols = self.model.hist_column_options()
        cur_col_idx = 0
        if self.model.hist_column in cols:
            cur_col_idx = cols.index(self.model.hist_column)
        im.set_next_item_width(avail_w)
        im.text(tr("Histogram column:"))
        changed, new_col_idx = im.combo("##col", cur_col_idx, cols)
        im.set_item_tooltip(tr("Table column whose distribution is plotted in the histogram."))
        self.remember("hist_column")
        if changed and 0 <= new_col_idx < len(cols):
            self.track("hist_column")
            self.model.hist_column = cols[new_col_idx]
            self.model.refresh()

    def _draw_gating_controls(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        half_w = max(50.0, (avail_w - 8.0) * 0.5)

        im.text_colored(ACCENT_BLUE, "Burst Filters")

        # E Range
        if self.model.have_E:
            im.text(tr("E Range:"))
            gate_lo, gate_hi = self._gate_bounds(
                self.model._col_E, self.model.e_min, self.model.e_max
            )
            im.set_next_item_width(half_w)
            ch_lo, new_e_lo = im.slider_float(
                "##e_min", float(self.model.e_min), gate_lo, gate_hi, "%.3f"
            )
            im.set_item_tooltip(tr("Lower FRET-efficiency gate; bursts below it are hidden."))
            self.remember("e_range")
            im.same_line()
            im.set_next_item_width(half_w)
            ch_hi, new_e_hi = im.slider_float(
                "##e_max", float(self.model.e_max), gate_lo, gate_hi, "%.3f"
            )
            im.set_item_tooltip(tr("Upper FRET-efficiency gate; bursts above it are hidden."))
            if ch_lo or ch_hi:
                self.track("e_range")
                self.model.e_min = min(new_e_lo, new_e_hi)
                self.model.e_max = max(new_e_lo, new_e_hi)
                self.model.refresh()
        else:
            im.text_disabled(tr("E Range (not available)"))

        # S Range
        if self.model.have_S:
            im.text(tr("S Range:"))
            gate_lo, gate_hi = self._gate_bounds(
                self.model._col_S, self.model.s_min, self.model.s_max
            )
            im.set_next_item_width(half_w)
            ch_lo, new_s_lo = im.slider_float(
                "##s_min", float(self.model.s_min), gate_lo, gate_hi, "%.3f"
            )
            im.set_item_tooltip(tr("Lower stoichiometry gate; bursts below it are hidden."))
            im.same_line()
            im.set_next_item_width(half_w)
            ch_hi, new_s_hi = im.slider_float(
                "##s_max", float(self.model.s_max), gate_lo, gate_hi, "%.3f"
            )
            im.set_item_tooltip(tr("Upper stoichiometry gate; bursts above it are hidden."))
            if ch_lo or ch_hi:
                self.model.s_min = min(new_s_lo, new_s_hi)
                self.model.s_max = max(new_s_lo, new_s_hi)
                self.model.refresh()
        else:
            im.text_disabled(tr("S Range (not available)"))

        # Size Range
        if self.model._col_size is not None:
            im.text(tr("Photon Size Range:"))
            im.set_next_item_width(half_w)
            # No -/+ buttons: at half the pane they left too little room and a
            # 3-digit photon count showed as its first two digits.
            size_lo, size_hi = int(self.model.size_min), int(self.model.size_max)
            typed_lo, _ = typed_number_field(
                "sz_min", size_lo, self._number_buffers, minimum=0, maximum=10_000_000
            )
            self.remember("sz_min")
            im.set_item_tooltip(tr("Minimum number of photons per burst."))
            im.same_line()
            im.set_next_item_width(half_w)
            typed_hi, _ = typed_number_field(
                "sz_max", size_hi, self._number_buffers, minimum=0, maximum=10_000_000
            )
            self.remember("sz_max")
            im.set_item_tooltip(tr("Maximum number of photons per burst."))
            if typed_lo is not None or typed_hi is not None:
                lo = size_lo if typed_lo is None else typed_lo
                hi = size_hi if typed_hi is None else typed_hi
                self.model.size_min, self.model.size_max = min(lo, hi), max(lo, hi)
                self.model.refresh()
        else:
            im.text_disabled(tr("Size Range (not available)"))

        im.spacing()
        ch_sel, new_use_sel = im.checkbox(
            tr("Use table selection for hist"), self.model.use_selection
        )
        im.set_item_tooltip(tr("Histogram only the rows currently selected in the bursts table."))
        if ch_sel:
            self.model.use_selection = new_use_sel
            self.model.refresh()

        im.spacing()
        im.separator()
        im.spacing()

        # Region Drag & Drop Presets
        im.text_colored(ACCENT_BLUE, "Draggable Region Presets")
        presets = [
            ("Low FRET", 0.05, 0.35),
            ("Mid FRET", 0.35, 0.65),
            ("High FRET", 0.65, 0.95),
            ("Full Range", 0.0, 1.0),
        ]
        for i, (name, r_min, r_max) in enumerate(presets):
            if im.button(f"Region: {name} [{r_min:.2f}-{r_max:.2f}]", (avail_w, 22.0)):
                self.track("region_presets")
                self.model.e_min, self.model.e_max = r_min, r_max
                self.model.refresh()
            im.set_item_tooltip(f"Apply the {name} FRET gate, or drag this button onto a plot.")
            if i == 0:
                self.remember("region_presets")
            # Enable dragging region payload from button
            if im.begin_drag_drop_source():
                payload = json.dumps({"min": r_min, "max": r_max, "name": name})
                im.set_drag_drop_payload("BURST_REGION", payload.encode("utf-8"))
                im.text(f"Drag region {name}: [{r_min:.2f}, {r_max:.2f}]")
                im.end_drag_drop_source()

        im.spacing()
        im.separator()
        im.spacing()
        im.text_colored(ACCENT_GREEN, self.model.status_text())

    def _draw_table_view(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        if self.model.table is None:
            im.text_disabled(tr("No bursts loaded. Open a .bur folder or file."))
            return

        names = column_names(self.model.table)
        if not names:
            im.text_disabled(tr("Table has no columns."))
            return

        masked_rows = self.model.masked_row_indices()
        total_rows = len(masked_rows)
        max_page = max(0, (total_rows - 1) // self.page_size) if total_rows > 0 else 0
        self.page = max(0, min(self.page, max_page))

        # Pagination toolbar
        if im.button("<<", (28.0, 22.0)) and self.page > 0:
            self.page -= 1
        im.set_item_tooltip(tr("Previous page of bursts."))
        im.same_line()
        im.text(f"Page {self.page + 1} / {max_page + 1} ({total_rows} bursts)")
        im.same_line()
        if im.button(">>", (28.0, 22.0)) and self.page < max_page:
            self.page += 1
        im.set_item_tooltip(tr("Next page of bursts."))

        im.same_line()
        if im.get_content_region_avail()[0] < 65.0:  # a narrow pane: on its own row, not cut off
            im.new_line()
        if im.button(tr("Clear Sel"), (65.0, 22.0)):
            self.model.selected_indices.clear()
            if self.model.use_selection:
                self.model.notify("selection")
        im.set_item_tooltip(tr("Deselect all rows in the table."))

        im.spacing()

        if self._burst_table is None:
            from pathlib import Path

            spec = json.loads(Path(__file__).with_name("burst_table.view.json").read_text())
            self._burst_table = TableBinding(spec["sections"][0], self)
        tx, ty = im.get_cursor_screen_pos()
        table_height = max(60.0, im.get_content_region_avail()[1])
        self._burst_table.refresh()
        visible_indices = {row["_burst_index"] for row in self._table_rows}
        self._burst_table.control.also_selected = set(self.model.selected_indices) & visible_indices
        draw_table(self._burst_table, width=avail_w, height=table_height, name="burst_data_table")
        self.remember("table", (tx, ty, avail_w, table_height))

    def _gate_bounds(self, column, lower: float, upper: float) -> tuple[float, float]:
        """Include measured and current gate limits without clipping corrected values."""
        measured_lo, measured_hi = self.model._col_range(column, 0.0, 1.0, as_int=False)
        return min(0.0, lower, measured_lo), max(1.0, upper, measured_hi)

    def burst_table_rows(self) -> list[dict]:
        """Return typed values and stable source identities for the current page."""
        names = column_names(self.model.table)
        indices = self.model.masked_row_indices()
        visible = indices[self.page * self.page_size : (self.page + 1) * self.page_size]
        token = (id(self.model.table), tuple(names), tuple(int(i) for i in visible))
        if token != self._table_token:
            columns = [column_values(self.model.table, i) for i in range(len(names))]
            self._table_rows = [
                {
                    "_burst_index": int(row),
                    **{
                        name: None if is_missing(values[int(row)]) else values[int(row)]
                        for name, values in zip(names, columns)
                    },
                }
                for row in visible
            ]
            self._table_token = token
        return self._table_rows

    def burst_table_columns(self) -> list[dict]:
        """Declare readable, described columns from the loaded measurement vocabulary."""
        return [
            {
                "key": name,
                "label": name,
                "format": "%.4g" if column_values(self.model.table, i).dtype.kind == "f" else "",
                "width": max(im.calc_text_size(name)[0], im.calc_text_size("0.0000")[0]) + 14.0,
                "min_width": max(im.calc_text_size(name)[0], im.calc_text_size("0.0000")[0]) + 14.0,
                "description": tr("Recorded {column} value for this burst.").format(column=name),
            }
            for i, name in enumerate(column_names(self.model.table))
        ]

    def toggle_burst_row(self, record) -> None:
        """Toggle the original burst identity without changing the gated source table."""
        if record is None:
            return
        row = int(record["_burst_index"])
        self.track("table")
        if row in self.model.selected_indices:
            self.model.selected_indices.remove(row)
        else:
            self.model.selected_indices.append(row)
        if self._burst_table is not None:
            self._burst_table.control.selected_key = None
        if self.model.use_selection:
            self.model.notify("selection")

    def _draw_histogram_view(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        h = self.model.histogram()
        if h is None or len(h.get("centers", [])) == 0:
            im.text_disabled(tr("No histogram data available."))
            return

        origin = im.get_cursor_screen_pos()
        plot_w = max(avail_w, 150.0)
        plot_h = max(avail_h - 10.0, 150.0)

        col_name = h.get("label", "Value")
        if implot.begin_plot("Distribution##hist_plot", (plot_w, plot_h)):
            implot.setup_axes(col_name, "Counts")
            implot.set_next_fill_style(ACCENT_BLUE)
            xs = h["centers"]
            ys = h["counts"]
            width = float(h.get("width", 0.05))
            implot.plot_bars(col_name, xs, ys=ys, bar_size=width)

            # ── Interactive Draggable Region Dropping & Manipulation ─────
            # If the plotted column is E, S, or size, provide interactive draggable
            # region boundaries directly on the plot.
            max_cnt = float(np.max(ys)) if len(ys) > 0 else 1.0
            if col_name in ("E", "Proximity Ratio"):
                r_res = implot.drag_rect(
                    0,
                    float(self.model.e_min),
                    0.0,
                    float(self.model.e_max),
                    max_cnt,
                    col=REGION_FILL,
                )
                if r_res.modified:
                    self.track("browser_histogram")
                    self.model.e_min = max(0.0, min(r_res.x_min, r_res.x_max))
                    self.model.e_max = min(1.0, max(r_res.x_min, r_res.x_max))
                    self.model.refresh()
                implot.tag_x(self.model.e_min, REGION_BORDER, f"E min: {self.model.e_min:.2f}")
                implot.tag_x(self.model.e_max, REGION_BORDER, f"E max: {self.model.e_max:.2f}")

            elif col_name == "S":
                r_res = implot.drag_rect(
                    1,
                    float(self.model.s_min),
                    0.0,
                    float(self.model.s_max),
                    max_cnt,
                    col=REGION_FILL,
                )
                if r_res.modified:
                    self.track("browser_histogram")
                    self.model.s_min = max(0.0, min(r_res.x_min, r_res.x_max))
                    self.model.s_max = min(1.0, max(r_res.x_min, r_res.x_max))
                    self.model.refresh()
                implot.tag_x(self.model.s_min, REGION_BORDER, f"S min: {self.model.s_min:.2f}")
                implot.tag_x(self.model.s_max, REGION_BORDER, f"S max: {self.model.s_max:.2f}")

            elif "Number of Photons" in col_name:
                r_res = implot.drag_rect(
                    2,
                    float(self.model.size_min),
                    0.0,
                    float(self.model.size_max),
                    max_cnt,
                    col=REGION_FILL,
                )
                if r_res.modified:
                    self.track("browser_histogram")
                    self.model.size_min = max(0, int(min(r_res.x_min, r_res.x_max)))
                    self.model.size_max = max(0, int(max(r_res.x_min, r_res.x_max)))
                    self.model.refresh()
                implot.tag_x(self.model.size_min, REGION_BORDER, f"Min: {self.model.size_min}")
                implot.tag_x(self.model.size_max, REGION_BORDER, f"Max: {self.model.size_max}")

            implot.end_plot()

        # Region Drop Target over the plot
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                    if col_name in ("E", "Proximity Ratio"):
                        self.model.e_min = float(data.get("min", 0.0))
                        self.model.e_max = float(data.get("max", 1.0))
                        self.model.refresh()
                    elif col_name == "S":
                        self.model.s_min = float(data.get("min", 0.0))
                        self.model.s_max = float(data.get("max", 1.0))
                        self.model.refresh()
                except Exception:
                    logger.debug("Failed to apply dropped region payload", exc_info=True)
            im.end_drag_drop_target()

        self.remember("browser_histogram", (origin[0], origin[1], plot_w, plot_h))


class BurstBrowserApp(ImApp):
    """Immediate-mode EMTK application for the Burst Browser with docking & region dropping."""

    def __init__(
        self,
        model: BurstBrowserViewModel | None = None,
        on_open_folder: Callable[[], None] | None = None,
        on_open_file: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        from pathlib import Path

        spec = json.loads(Path(__file__).with_name("burst_browser.view.json").read_text())
        self.window_size = window_size(spec, (1200, 800))
        self.controller = None
        if on_open_folder is None and on_open_file is None:
            from .controller import BurstBrowserController

            model = model if model is not None else BurstBrowserViewModel()
            self.controller = BurstBrowserController(model)

            def on_open_folder():
                self.controller.browse("folder")

            def on_open_file():
                self.controller.browse("file")

        self.browser_gui = BurstBrowserGui(
            model=model,
            on_open_folder=on_open_folder,
            on_open_file=on_open_file,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.browser_gui.model
        self.item_rects = self.browser_gui.item_rects
        self.browser_gui.controller = self.controller
        super().__init__(gui=self._render)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.browser_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.browser_gui.show_help()

    def _render(self) -> None:
        if self.controller is not None:
            self.controller.poll()
            if self.controller.running:  # look again in 0.1 s while a read runs
                ctx = get_current_context()
                ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.browser_gui.draw(w, h)
        if self.controller is not None:
            self.controller.draw_dialogs((0.0, 0.0, float(w), float(h)))

    @property
    def table(self):
        return self.model.table

    def load_folder(self, folder):
        if self.controller is not None:
            self.controller.load(folder)
        else:
            self.model.load_folder(folder)

    def load_bur(self, path):
        self.load_folder(path)

    def close(self):
        if self.controller is not None:
            self.controller.close()

    def on_paths_dropped(self, paths):
        if self.controller is not None:
            self.controller.on_paths_dropped(paths)


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return BurstBrowserApp(**kwargs)
