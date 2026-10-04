"""The Data-table plot page, drawn by emtk.

The "Data table" page used to be a classic Qt widget stack: a
``ChiTableWidget`` with Qt tool buttons under an emtk tab/dock shell. This
module renders the same table through emtk's ``DataTable`` — sortable,
filterable, with real checkbox cells for the fit mask and typed cell edits
for ``x``/``data`` — plus emtk ``SmallButton`` for the toolbar and the emtk
status line under the rows. It subclasses the Qt page and reuses everything
that never was widget code: reading the fit into aligned arrays, writing
edits back to the fit and the fitting client, and the model-parameter frame.

Selection stays explicit. The retained Qt page is the default;
``gui.plot.fit_table: emtk`` in the settings or
``CHISURF_FIT_TABLE_BACKEND=emtk`` in the environment selects this one
(``chisurf/gui/autoform/sections/builtin.py`` resolves the registry key).
That matches the repo's acceptance rule: a port becomes the default only
after visual, click and parity evidence — swap it then, not here.
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
        for btn in (self.btn_show_model, self.btn_copy):
            bw, _bh = btn.size(p)
            box = (cx, cy, bw, row_h)
            self._btn_boxes[id(btn)] = box
            btn.draw(p, *box)
            cx += bw + 10.0
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
        ty = cy + row_h + 4.0
        self._table_box = (
            x + 2.0,
            ty,
            max(w - 4.0, 40.0),
            max(h - (ty - y) - 2.0, row_h),
        )
        self.table.draw(p, *self._table_box)

    def _button_at(self, px: float, py: float):
        for btn in (self.btn_show_model, self.btn_copy):
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
                if btn is self.btn_copy:
                    self.on_copy_table_to_clipboard()
                else:
                    self.on_show_model()
            return True
        self.table.press(px, py, *self._table_box, modifiers=int(modifiers), clicks=int(clicks))
        return True

    def drag(self, px: float, py: float, *box) -> bool:
        self.table.drag(px, py, *self._table_box)
        return True

    def hover(self, px: float, py: float, *box) -> None:
        for btn in (self.btn_show_model, self.btn_copy):
            hit = self._btn_boxes.get(id(btn))
            if hit is not None:
                btn.hover(px, py, *hit)
        self.table.hover(px, py, *self._table_box)

    def release(self) -> None:
        self.btn_show_model.release()
        self.btn_copy.release()
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
        table = self.table
        cols = table.visible_columns()
        lines = ["\t".join(c.key for c in cols)]
        for index in table.order():
            row = []
            for col in cols:
                value = table.value(index, col.key)
                if col.key == "mask":
                    row.append("1" if value else "0")
                else:
                    row.append(col.text(value))
            lines.append("\t".join(row))
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))

    def _request_repaint(self) -> None:
        host = self._host
        update = getattr(host, "update", None)
        if callable(update):
            update()
