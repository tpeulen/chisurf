"""The Burst Browser tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstBrowserApp`) over
:class:`~.view_model.BurstBrowserViewModel`:
- Left pane: Data source (Open folder/file, path display), detector & column selection,
  and interactive Gating controls (E, S, Size, selection mode).
- Center pane: Gated per-burst table with pagination and multi-row selection.
- Right pane: Live histogram of the selected column with emtk.implot.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp

from chisurf.core.datastore import column_names, column_values, is_missing, row_count

from ..view_model import BurstBrowserViewModel

__all__ = ["BurstBrowserApp", "BurstBrowserGui", "WINDOW_BG"]

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)


def _format_cell(val: Any) -> str:
    if is_missing(val):
        return ""
    if isinstance(val, (float, np.floating)):
        return f"{val:.4g}"
    return str(val)


class BurstBrowserGui:
    """Immediate-mode GUI logic and rendering for the Burst Browser."""

    def __init__(
        self,
        model: BurstBrowserViewModel | None = None,
        on_open_folder: Callable[[], None] | None = None,
        on_open_file: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else BurstBrowserViewModel()
        self.on_open_folder = on_open_folder
        self.on_open_file = on_open_file

        self.page: int = 0
        self.page_size: int = 50
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        self.model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        if event in ("data", "gating"):
            self.page = 0

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
        """Draw the 3-pane Burst Browser into (w, h) display pixels."""
        ctrl_w = min(max(260.0, w * 0.28), 340.0)
        remaining_w = max(w - ctrl_w - 12.0, 300.0)

        # In wide layouts, split remaining space between table and histogram.
        # In narrower layouts, use 55% table, 45% histogram.
        tbl_w = max(remaining_w * 0.52, 200.0)
        hist_w = max(remaining_w - tbl_w - 6.0, 180.0)

        # ── Left pane: Controls & Gating ─────────────────────────────────
        if im.begin("Controls", (4.0, 4.0, ctrl_w, h - 8.0)):
            self._draw_source_controls(ctrl_w - 16.0)
            im.spacing()
            im.separator()
            im.spacing()
            self._draw_column_selectors(ctrl_w - 16.0)
            im.spacing()
            im.separator()
            im.spacing()
            self._draw_gating_controls(ctrl_w - 16.0)
            im.spacing()
            im.separator()
            im.spacing()
            im.text_colored(ACCENT_GRAY, self.model.status_text())
            im.end()

        # ── Middle pane: Bursts Table ────────────────────────────────────
        tbl_x = 4.0 + ctrl_w + 4.0
        if im.begin("Bursts", (tbl_x, 4.0, tbl_w, h - 8.0)):
            self._draw_table_view(tbl_w - 16.0, h - 36.0)
            im.end()

        # ── Right pane: Histogram ────────────────────────────────────────
        hist_x = tbl_x + tbl_w + 4.0
        if im.begin("Histogram", (hist_x, 4.0, hist_w, h - 8.0)):
            self._draw_histogram_view(hist_w - 16.0, h - 36.0)
            im.end()

    def _draw_source_controls(self, avail_w: float) -> None:
        im.text_colored(ACCENT_BLUE, "Data Source")
        if im.button("Open Folder", (avail_w * 0.48, 26.0)):
            self.track("open_folder")
            if callable(self.on_open_folder):
                self.on_open_folder()
        self.remember("open_folder")

        im.same_line()
        if im.button("Open File", (avail_w * 0.48, 26.0)):
            self.track("open_file")
            if callable(self.on_open_file):
                self.on_open_file()
        self.remember("open_file")

        path = self.model.path_text
        if len(path) > 36:
            path = "…" + path[-34:]
        im.text_colored(ACCENT_GRAY, f"Path: {path}")

    def _draw_column_selectors(self, avail_w: float) -> None:
        im.text_colored(ACCENT_BLUE, "Columns & Detectors")

        # Detector combo
        dets = self.model.detector_options()
        cur_det_idx = 0
        if self.model.detector in dets:
            cur_det_idx = dets.index(self.model.detector)
        im.set_next_item_width(avail_w)
        changed, new_det_idx = im.combo("Detector##det", cur_det_idx, dets)
        if changed and 0 <= new_det_idx < len(dets):
            self.model.on_detector_changed(dets[new_det_idx])

        im.spacing()

        # Histogram column combo
        cols = self.model.hist_column_options()
        cur_col_idx = 0
        if self.model.hist_column in cols:
            cur_col_idx = cols.index(self.model.hist_column)
        im.set_next_item_width(avail_w)
        changed, new_col_idx = im.combo("Hist Column##col", cur_col_idx, cols)
        if changed and 0 <= new_col_idx < len(cols):
            self.model.hist_column = cols[new_col_idx]
            self.model.refresh()

    def _draw_gating_controls(self, avail_w: float) -> None:
        im.text_colored(ACCENT_BLUE, "Gating")

        # E Range
        if self.model.have_E:
            im.text("E Range:")
            im.set_next_item_width(avail_w * 0.46)
            changed_lo, new_e_lo = im.slider_float(
                "##e_min", float(self.model.e_min), 0.0, 1.0, "%.3f"
            )
            im.same_line()
            im.set_next_item_width(avail_w * 0.46)
            changed_hi, new_e_hi = im.slider_float(
                "##e_max", float(self.model.e_max), 0.0, 1.0, "%.3f"
            )
            if changed_lo or changed_hi:
                self.model.e_min = new_e_lo
                self.model.e_max = new_e_hi
                self.model.refresh()
        else:
            im.text_disabled("E Range (not available)")

        # S Range
        if self.model.have_S:
            im.text("S Range:")
            im.set_next_item_width(avail_w * 0.46)
            changed_lo, new_s_lo = im.slider_float(
                "##s_min", float(self.model.s_min), 0.0, 1.0, "%.3f"
            )
            im.same_line()
            im.set_next_item_width(avail_w * 0.46)
            changed_hi, new_s_hi = im.slider_float(
                "##s_max", float(self.model.s_max), 0.0, 1.0, "%.3f"
            )
            if changed_lo or changed_hi:
                self.model.s_min = new_s_lo
                self.model.s_max = new_s_hi
                self.model.refresh()
        else:
            im.text_disabled("S Range (not available)")

        # Size Range
        if self.model._col_size is not None:
            im.text("Photon Size Range:")
            im.set_next_item_width(avail_w * 0.46)
            changed_lo, new_sz_lo = im.input_int(
                "##sz_min", int(self.model.size_min), step=1, step_fast=50
            )
            im.same_line()
            im.set_next_item_width(avail_w * 0.46)
            changed_hi, new_sz_hi = im.input_int(
                "##sz_max", int(self.model.size_max), step=1, step_fast=50
            )
            if changed_lo or changed_hi:
                self.model.size_min = max(0, new_sz_lo)
                self.model.size_max = max(0, new_sz_hi)
                self.model.refresh()
        else:
            im.text_disabled("Size Range (not available)")

        im.spacing()
        changed, new_use_sel = im.checkbox("Use table selection for hist", self.model.use_selection)
        if changed:
            self.model.use_selection = new_use_sel
            self.model.refresh()

    def _draw_table_view(self, avail_w: float, avail_h: float) -> None:
        if self.model.table is None:
            im.text_disabled("No bursts loaded.")
            return

        names = column_names(self.model.table)
        if not names:
            im.text_disabled("Table has no columns.")
            return

        masked_rows = self.model.masked_row_indices()
        total_rows = len(masked_rows)
        max_page = max(0, (total_rows - 1) // self.page_size) if total_rows > 0 else 0
        self.page = max(0, min(self.page, max_page))

        # Pagination toolbar
        if im.button("<<", (30.0, 22.0)) and self.page > 0:
            self.page -= 1
        im.same_line()
        im.text(f"Page {self.page + 1} / {max_page + 1} ({total_rows} bursts)")
        im.same_line()
        if im.button(">>", (30.0, 22.0)) and self.page < max_page:
            self.page += 1

        im.spacing()

        # Render table
        flags = (
            im.TableFlags.ROW_BG
            | im.TableFlags.BORDERS
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SCROLL_X
            | im.TableFlags.RESIZABLE
        )
        tbl_h = max(60.0, avail_h - 40.0)
        if im.begin_table("burst_data_table", len(names), flags, size=(avail_w, tbl_h)):
            im.table_setup_scroll_freeze(0, 1)
            for name in names:
                im.table_setup_column(name)
            im.table_headers_row()

            # Pre-extract column arrays for fast indexed lookup
            cols_data = [column_values(self.model.table, i) for i in range(len(names))]
            start_idx = self.page * self.page_size
            end_idx = min(start_idx + self.page_size, total_rows)

            for vi in range(start_idx, end_idx):
                base_row = int(masked_rows[vi])
                im.table_next_row()

                # First column is selectable
                im.table_next_column()
                val_0 = _format_cell(cols_data[0][base_row])
                is_selected = base_row in self.model.selected_indices
                clicked = im.selectable(
                    f"{val_0}##r_{base_row}",
                    selected=is_selected,
                    flags=im.SelectableFlags.SPAN_ALL_COLUMNS,
                )
                if clicked:
                    if is_selected:
                        self.model.selected_indices.remove(base_row)
                    else:
                        self.model.selected_indices.append(base_row)
                    if self.model.use_selection:
                        self.model.notify("selection")

                # Remaining columns
                for c in range(1, len(names)):
                    im.table_next_column()
                    im.text(_format_cell(cols_data[c][base_row]))

            im.end_table()

    def _draw_histogram_view(self, avail_w: float, avail_h: float) -> None:
        h = self.model.histogram()
        if h is None or len(h.get("centers", [])) == 0:
            im.text_disabled("No histogram data available.")
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
            implot.end_plot()
        self.remember("browser_histogram", (origin[0], origin[1], plot_w, plot_h))


class BurstBrowserApp(ImApp):
    """Immediate-mode EMTK application for the Burst Browser."""

    def __init__(
        self,
        model: BurstBrowserViewModel | None = None,
        on_open_folder: Callable[[], None] | None = None,
        on_open_file: Callable[[], None] | None = None,
    ) -> None:
        self.browser_gui = BurstBrowserGui(
            model=model,
            on_open_folder=on_open_folder,
            on_open_file=on_open_file,
        )
        self.model = self.browser_gui.model
        super().__init__(gui=self._render, continuous=False)

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.browser_gui.draw(w, h)
