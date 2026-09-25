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

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp

from chisurf.core.datastore import column_names, column_values, is_missing

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
REGION_FILL = (46, 117, 182, 60)
REGION_BORDER = (90, 160, 240, 255)


def _format_cell(val: Any) -> str:
    if is_missing(val):
        return ""
    if isinstance(val, (float, np.floating)):
        return f"{val:.4g}"
    return str(val)


class BurstBrowserGui:
    """Immediate-mode GUI logic and rendering for the Burst Browser with dockable windows."""

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
        """Draw the dockable Burst Browser into (w, h) display pixels."""
        # Enable full dockspace over the viewport so all windows can be docked,
        # split, tabbed, dragged, or undocked as floating windows.
        im.dock_space_over_viewport(1)

        ctrl_w = min(max(260.0, w * 0.26), 320.0)
        remaining_w = max(w - ctrl_w - 16.0, 320.0)
        tbl_w = max(remaining_w * 0.50, 200.0)
        hist_w = max(remaining_w - tbl_w - 8.0, 180.0)

        # ── Window 1: Controls (Source & Selection) ──────────────────────
        im.set_next_window_pos((4.0, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((ctrl_w, (h - 12.0) * 0.42), im.Cond.FIRST_USE_EVER)
        if im.begin("Controls"):
            self._draw_source_controls()
            im.spacing()
            im.separator()
            im.spacing()
            self._draw_column_selectors()
            im.end()

        # ── Window 2: Gating (Interactive thresholds & region presets) ───
        im.set_next_window_pos((4.0, 8.0 + (h - 12.0) * 0.42), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((ctrl_w, (h - 12.0) * 0.58), im.Cond.FIRST_USE_EVER)
        if im.begin("Gating"):
            self._draw_gating_controls()
            im.end()

        # ── Window 3: Bursts Table ───────────────────────────────────────
        im.set_next_window_pos((8.0 + ctrl_w, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((tbl_w, h - 8.0), im.Cond.FIRST_USE_EVER)
        if im.begin("Bursts Table"):
            self._draw_table_view()
            im.end()

        # ── Window 4: Histogram (Live distribution & region dragging) ────
        im.set_next_window_pos((12.0 + ctrl_w + tbl_w, 4.0), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size((hist_w, h - 8.0), im.Cond.FIRST_USE_EVER)
        if im.begin("Histogram"):
            self._draw_histogram_view()
            im.end()

    def _draw_source_controls(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        im.text_colored(ACCENT_BLUE, "Data Source")
        btn_w = max(60.0, (avail_w - 6.0) * 0.5)
        if im.button("Open Folder", (btn_w, 24.0)):
            self.track("open_folder")
            if callable(self.on_open_folder):
                self.on_open_folder()
        self.remember("open_folder")

        im.same_line()
        if im.button("Open File", (btn_w, 24.0)):
            self.track("open_file")
            if callable(self.on_open_file):
                self.on_open_file()
        self.remember("open_file")

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

    def _draw_gating_controls(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        half_w = max(50.0, (avail_w - 8.0) * 0.5)

        im.text_colored(ACCENT_BLUE, "Burst Filters")

        # E Range
        if self.model.have_E:
            im.text("E Range:")
            im.set_next_item_width(half_w)
            ch_lo, new_e_lo = im.slider_float("##e_min", float(self.model.e_min), 0.0, 1.0, "%.3f")
            im.same_line()
            im.set_next_item_width(half_w)
            ch_hi, new_e_hi = im.slider_float("##e_max", float(self.model.e_max), 0.0, 1.0, "%.3f")
            if ch_lo or ch_hi:
                self.model.e_min = min(new_e_lo, new_e_hi)
                self.model.e_max = max(new_e_lo, new_e_hi)
                self.model.refresh()
        else:
            im.text_disabled("E Range (not available)")

        # S Range
        if self.model.have_S:
            im.text("S Range:")
            im.set_next_item_width(half_w)
            ch_lo, new_s_lo = im.slider_float("##s_min", float(self.model.s_min), 0.0, 1.0, "%.3f")
            im.same_line()
            im.set_next_item_width(half_w)
            ch_hi, new_s_hi = im.slider_float("##s_max", float(self.model.s_max), 0.0, 1.0, "%.3f")
            if ch_lo or ch_hi:
                self.model.s_min = min(new_s_lo, new_s_hi)
                self.model.s_max = max(new_s_lo, new_s_hi)
                self.model.refresh()
        else:
            im.text_disabled("S Range (not available)")

        # Size Range
        if self.model._col_size is not None:
            im.text("Photon Size Range:")
            im.set_next_item_width(half_w)
            ch_lo, new_sz_lo = im.input_int(
                "##sz_min", int(self.model.size_min), step=1, step_fast=50
            )
            im.same_line()
            im.set_next_item_width(half_w)
            ch_hi, new_sz_hi = im.input_int(
                "##sz_max", int(self.model.size_max), step=1, step_fast=50
            )
            if ch_lo or ch_hi:
                self.model.size_min = max(0, min(new_sz_lo, new_sz_hi))
                self.model.size_max = max(0, max(new_sz_lo, new_sz_hi))
                self.model.refresh()
        else:
            im.text_disabled("Size Range (not available)")

        im.spacing()
        ch_sel, new_use_sel = im.checkbox("Use table selection for hist", self.model.use_selection)
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
        for name, r_min, r_max in presets:
            if im.button(f"Region: {name} [{r_min:.2f}-{r_max:.2f}]", (avail_w, 22.0)):
                self.model.e_min, self.model.e_max = r_min, r_max
                self.model.refresh()
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
            im.text_disabled("No bursts loaded. Open a .bur folder or file.")
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
        if im.button("<<", (28.0, 22.0)) and self.page > 0:
            self.page -= 1
        im.same_line()
        im.text(f"Page {self.page + 1} / {max_page + 1} ({total_rows} bursts)")
        im.same_line()
        if im.button(">>", (28.0, 22.0)) and self.page < max_page:
            self.page += 1

        im.same_line()
        if im.button("Clear Sel", (65.0, 22.0)):
            self.model.selected_indices.clear()
            if self.model.use_selection:
                self.model.notify("selection")

        im.spacing()

        # Render table
        flags = (
            im.TableFlags.ROW_BG
            | im.TableFlags.BORDERS
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SCROLL_X
            | im.TableFlags.RESIZABLE
        )
        tbl_h = max(60.0, avail_h - 32.0)
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

    def _draw_histogram_view(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
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
