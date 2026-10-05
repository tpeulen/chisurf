"""The Data-table plot page, drawn by emtk.

The "Data table" page used to be a classic Qt widget stack: a
``ChiTableWidget`` with Qt tool buttons under an emtk tab/dock shell. This
module renders the same table through emtk's ``DataTable`` — sortable,
filterable, with real checkbox cells for the fit mask and typed cell edits
for ``x``/``data`` — plus emtk ``SmallButton`` for the toolbar and the emtk
status line under the rows. It subclasses the Qt page and reuses everything
that never was widget code: reading the fit into aligned arrays, writing
edits back to the fit and the fitting client, and the model-parameter frame.

The fit window draws all of its pages on one emtk surface
(``chisurf/gui/widgets/fitting/fit_plots_area.py``), so this is the page the
``fit_table`` registry key gives.
"""

from __future__ import annotations

import math

import numpy as np
from qtpy import QtWidgets

from chisurf.gui.plots import plotbase
from chisurf.gui.plots import table_plot as _qt_table_plot
from chisurf.gui.plots.table_plot import _BASE_COLUMNS, _EDITABLE_COLUMNS


class FitTablePlotEmtk(_qt_table_plot.FitTablePlot):
    """emtk-drawn table of a fit's data, model, residuals and mask."""

    name = "Data table"
    emtk = True

    def __init__(
        self,
        fit,
        parent: QtWidgets.QWidget | None = None,
        **kwargs,
    ):
        # Skip the Qt page's widget build; keep its array plumbing.
        plotbase.Plot.__init__(self, fit, parent=parent, **kwargs)

        self._source_arrays: dict[str, np.ndarray] = {}
        self._applying_edit = False
        self._info_text = ""
        self._btn_boxes: dict[int, tuple[float, float, float, float]] = {}
        self._table_box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

        from emtk.qt_host import ControlHost
        from emtk.widgets.buttons import SmallButton
        from emtk.widgets.data_table import DataTable, TableColumn

        self._TableColumn = TableColumn
        self.table = DataTable(filter_box=True, status=True, on_edit=self._on_table_edit)
        self.table.auto_fit = True

        self.btn_show_model = SmallButton("Model")
        self.btn_copy = SmallButton("Copy table")
        # The table tools the Qt page carried beside its search field.
        self.btn_columns = SmallButton("Columns")
        self.btn_empty = SmallButton("Hide empty")
        self.btn_shade = SmallButton("Shade")
        self.btn_scope = SmallButton("∥")
        self.btn_export = SmallButton("Export CSV")
        self.hide_empty = False
        self._hidden_empty: set[str] = set()
        self._tips = {
            id(self.btn_show_model): "Show the model's parameters for this fit.",
            id(self.btn_copy): "Copy the visible rows and columns to the clipboard (tab separated).",
            id(self.btn_columns): "Choose which columns are shown (also: right-click the header).",
            id(self.btn_empty): "Hide columns that contain no values; press again to show them.",
            id(self.btn_shade): "Shade numeric cells by their value.",
            id(self.btn_scope): "Scale the shading across all columns instead of per column.",
            id(self.btn_export): "Export the visible rows and columns as CSV.",
        }

        self._host = ControlHost(self)
        self.layout.addWidget(self._host, 1)

        self._refresh_arrays_into_model()

    # ── emtk control surface (what ControlHost forwards) ────────────────

    def animating(self) -> bool:
        """Nothing here moves on its own."""
        return False

    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        self.draw_content(p, x, y, w, h)

    def draw_content(self, p, x: float, y: float, w: float, h: float) -> None:
        """Toolbar row, then the table filling the rest."""
        from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
        from emtk.style import TEXT

        row_h = p.line_height()
        pad = 6.0
        cx = x + pad
        cy = y + 4.0
        self._btn_boxes.clear()
        self.btn_empty.label = "● Hide empty" if self.hide_empty else "Hide empty"
        shading = self.table.colour_values
        self.btn_shade.label = "● Shade" if shading else "Shade"
        self.btn_scope.label = "● ∥" if shading == "table" else "∥"
        # The fit summary sits at the right of the first row; buttons that
        # would run into it wrap onto another row instead of drawing over it.
        info_w = p.text_width(self._info_text) + 12.0 if self._info_text else 0.0
        right = x + w - pad
        row_top = cy
        for btn in self._buttons():
            bw, _bh = btn.size(p)
            limit = right - (info_w if row_top == cy else 0.0)
            if cx + bw > limit and cx > x + pad:
                cx = x + pad
                row_top += row_h + 3.0
            box = (cx, row_top, bw, row_h)
            self._btn_boxes[id(btn)] = box
            btn.draw(p, *box)
            cx += bw + (14.0 if btn is self.btn_copy else 6.0)
        if self._info_text:
            tw = p.text_width(self._info_text)
            p.text(
                x + w - pad - tw,
                cy,
                tw + 2.0,
                row_h,
                ALIGN_LEFT | ALIGN_VCENTER,
                self._info_text,
                TEXT,
            )
        cy = row_top
        ty = cy + row_h + 4.0
        self._table_box = (
            x + 2.0,
            ty,
            max(w - 4.0, 40.0),
            max(h - (ty - y) - 2.0, row_h),
        )
        self.table.draw(p, *self._table_box)
        self._draw_column_picker()

    def _buttons(self) -> tuple:
        return (self.btn_show_model, self.btn_copy, self.btn_columns, self.btn_empty,
                self.btn_shade, self.btn_scope, self.btn_export)

    def _draw_column_picker(self) -> None:
        """The column list, while it is open, on the surface drawing this page."""
        try:
            from emtk.im_core import get_current_context
            from emtk.widgets.data_table import _column_picker

            get_current_context()
        except Exception:
            return  # not inside an emtk frame: no overlay to draw the list on
        _column_picker(self.table, "fit-table")

    def tooltip_at(self, px: float, py: float) -> str:
        """The toolbar button's tooltip, else the table's own (a cell, a header)."""
        btn, _box = self._button_at(px, py)
        if btn is not None:
            return self._tips.get(id(btn), "")
        return self.table.tooltip_at(px, py)

    def _on_button(self, btn, box) -> None:
        if btn is self.btn_copy:
            self.on_copy_table_to_clipboard()
        elif btn is self.btn_show_model:
            self.on_show_model()
        elif btn is self.btn_columns:
            bx, by, _bw, bh = box
            self.table.picker_at = (bx, by + bh)
        elif btn is self.btn_empty:
            self.set_hide_empty(not self.hide_empty)
        elif btn is self.btn_shade:
            self.table.colour_values = None if self.table.colour_values else "column"
        elif btn is self.btn_scope:
            if self.table.colour_values:
                self.table.colour_values = "column" if self.table.colour_values == "table" else "table"
        elif btn is self.btn_export:
            self.export_csv()
        self._request_repaint()

    def empty_columns(self) -> list[str]:
        """Keys of the columns with no finite value in any row."""
        empty = []
        for column in self.table.columns:
            data = (self.table.arrays or {}).get(column.key)
            if data is None:
                continue
            values = np.asarray(data)
            if values.dtype.kind in "fc" and not np.isfinite(values).any():
                empty.append(column.key)
            elif values.size == 0:
                empty.append(column.key)
        return empty

    def set_hide_empty(self, enabled: bool) -> None:
        """Hide the columns holding no values (``True``), or show them again."""
        self.hide_empty = bool(enabled)
        for key in self._hidden_empty:
            self.table.set_column_hidden(key, False)
        self._hidden_empty = set(self.empty_columns()) if self.hide_empty else set()
        for key in self._hidden_empty:
            self.table.set_column_hidden(key, True)

    def table_text(self, separator: str = "\t") -> str:
        """The visible rows and columns, header first, as delimited text."""
        table = self.table
        cols = table.visible_columns()
        lines = [separator.join(c.key for c in cols)]
        for index in table.order():
            row = []
            for col in cols:
                value = table.value(index, col.key)
                if col.key == "mask":
                    row.append("1" if value else "0")
                else:
                    row.append(col.text(value))
            lines.append(separator.join(row))
        return "\n".join(lines)

    def export_csv(self, path: str | None = None) -> str | None:
        """Write the visible rows and columns to a CSV file; ask where when *path* is None."""
        if path is None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                None, "Export data table", "", "CSV files (*.csv)"
            )
        if not path:
            return None
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.table_text(",") + "\n")
        return path

    def _button_at(self, px: float, py: float):
        for btn in self._buttons():
            box = self._btn_boxes.get(id(btn))
            if box is None:
                continue
            bx, by, bw, bh = box
            if bx <= px <= bx + bw and by <= py <= by + bh:
                return btn, box
        return None, None

    def press(
        self, px: float, py: float, x=0.0, y=0.0, w=0.0, h=0.0, modifiers: int = 0, clicks: int = 1
    ) -> bool:
        btn, box = self._button_at(px, py)
        if btn is not None:
            if btn.press(px, py, *box):
                self._on_button(btn, box)
            return True
        self.table.press(px, py, *self._table_box, modifiers=int(modifiers), clicks=int(clicks))
        return True

    def drag(self, px: float, py: float, *box) -> bool:
        self.table.drag(px, py, *self._table_box)
        return True

    def hover(self, px: float, py: float, *box) -> None:
        for btn in self._buttons():
            hit = self._btn_boxes.get(id(btn))
            if hit is not None:
                btn.hover(px, py, *hit)
        self.table.hover(px, py, *self._table_box)

    def release(self) -> None:
        for btn in self._buttons():
            btn.release()
        self.table.release()

    def scroll(self, rows: int) -> int:
        return self.table.scroll(int(rows))

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        return bool(self.table.key(int(key), text, int(modifiers)))

    # ── contents ─────────────────────────────────────────────────────────

    def _refresh_arrays_into_model(self) -> None:
        """Re-read the fit into the emtk table, keeping filter, sort, selection."""
        x, y, ym, wres, mask, support = self._get_arrays()
        if mask is None:
            mask = np.ones_like(x)
        columns: list[tuple[str, np.ndarray]] = list(zip(_BASE_COLUMNS, (x, y, ym, wres, mask)))
        columns += support
        keys = tuple(k for k, _ in columns)

        # The mask is a checkbox in emtk: feed bools, route the flip back
        # through the float mask the fit expects.
        display: dict[str, np.ndarray] = {}
        for key, arr in columns:
            display[key] = (arr != 0) if key == "mask" else np.asarray(arr, dtype=float)
        self._source_arrays = display

        from emtk.widgets.data_table import TableColumn

        make = self._TableColumn or TableColumn
        specs = []
        for key in keys:
            specs.append(
                make(
                    key=key,
                    title=key,
                    editable=key in _EDITABLE_COLUMNS,
                    tooltip=(
                        "1 includes the channel in the fit, 0 excludes it" if key == "mask" else ""
                    ),
                )
            )
        self.table.columns = list(specs)
        self.table.set_arrays({k: display[k] for k in keys})

        chi2r = getattr(self.fit, "chi2r", float("nan"))
        self._info_text = f"N={np.asarray(x).size}  |  χ²ᵣ={chi2r:.4g}"
        self._request_repaint()

    def _on_table_edit(self, index: int, key: str, value) -> None:
        """Route an emtk cell edit to the fit, like the Qt page's ``_on_cell_set``."""
        if self._applying_edit:
            return
        self._applying_edit = True
        try:
            if key == "mask":
                mask = self._source_arrays.get("mask")
                if mask is None:
                    return
                float_mask = np.asarray(mask, dtype=float).copy()
                float_mask[index] = 1.0 if value else 0.0
                self._set_mask(float_mask)
            elif key in ("x", "data"):
                for k in ("x", "data"):
                    arr = self._source_arrays.get(k)
                    if arr is None:
                        return
                if key in ("x", "data"):
                    try:
                        self._source_arrays[key][index] = float(value)
                    except (TypeError, ValueError):
                        return
                self._set_arrays(
                    np.asarray(self._source_arrays["x"], dtype=float).copy(),
                    np.asarray(self._source_arrays["data"], dtype=float).copy(),
                )
            else:
                return
            self._refresh_arrays_into_model()
        finally:
            self._applying_edit = False

    def on_copy_table_to_clipboard(self) -> None:
        """Copy every visible row and column, with header keys, to the clipboard."""
        QtWidgets.QApplication.clipboard().setText(self.table_text("\t"))

    def set_refresh_target(self, callback) -> None:
        """Send repaint requests to *callback* (the surface that draws this page)."""
        self._refresh_target = callback

    def _request_repaint(self) -> None:
        """Ask whatever shows the table to repaint."""
        target = getattr(self, "_refresh_target", None)
        if target is not None:
            target()
            return
        host = self._host
        update = getattr(host, "update", None)
        if callable(update):
            update()
