"""The fit window's *Data table* page: a fit's curves as a table, drawn by emtk.

Shows ``x``, the data, the model, the weighted residuals, the fit mask and every
support curve the model exposes, through emtk's ``DataTable`` -- sortable,
filterable, checkbox cells for the mask, typed edits for ``x`` and the data --
with a toolbar of emtk buttons and the fit's N and chi2r beside them. Edits are
routed back through the fitting client so the fit recomputes.

The page is no widget. It draws itself on the fit window's emtk surface
(:meth:`FitTablePlotEmtk.emtk_draw`): the toolbar and the table are one retained
control (:meth:`FitTablePlotEmtk.draw_content`), and what used to be Qt dialogs
-- the model-parameter editor, the CSV file chooser -- are drawn in the page's
place while they are open. A hidden page does not re-read the fit: an update
only marks it stale, and the next frame that shows it reads it.
"""

from __future__ import annotations

import math

import numpy as np

import chisurf.core.fitting
from chisurf.core.actions import record_action
from chisurf.core.datastore import row_count, rows_from_table, store_from_rows
from chisurf.gui.plots import plotbase
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

#: Curves that already have a dedicated column and must not be repeated.
_SUPPORT_EXCLUSIONS = {"data", "model", "weighted residuals", "autocorrelation"}

#: The fixed leading columns, in order, with the keys used for edit routing.
_BASE_COLUMNS = ("x", "data", "model", "w. res.", "mask")

#: Columns whose cells the user may edit.
_EDITABLE_COLUMNS = ("x", "data", "mask")

#: The model-parameter editor's columns: key, tooltip.
_PARAMETER_COLUMNS = (
    ("name", "The parameter."),
    ("value", "Its value."),
    ("lb", "Lower bound."),
    ("ub", "Upper bound."),
    ("fixed", "Fixed: not varied by the fit."),
    ("bounds_on", "Whether the bounds are enforced."),
    ("linked", "Linked to another parameter (link_target)."),
    ("link_target", "The parameter this one is linked to."),
)


def column_specs(keys):
    """The emtk table columns of a fit table, in *keys* order.

    Parameters
    ----------
    keys : sequence of str
        Column keys, base columns first.

    Returns
    -------
    list of emtk.widgets.data_table.TableColumn
    """
    from emtk.widgets.data_table import TableColumn

    return [
        TableColumn(
            key=key,
            title=key,
            editable=key in _EDITABLE_COLUMNS,
            tooltip="1 includes the channel in the fit, 0 excludes it" if key == "mask" else "",
        )
        for key in keys
    ]


class FitTablePlotEmtk(plotbase.Plot):
    """The *Data table* page: a fit's data, model, residuals and mask."""

    name = "Data table"
    emtk = True

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, parent=None, **kwargs):
        super().__init__(fit, parent=parent, **kwargs)
        self._source_arrays: dict[str, np.ndarray] = {}
        self._applying_edit = False
        self._info_text = ""
        self._btn_boxes: dict[int, tuple[float, float, float, float]] = {}
        self._table_box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        #: The fit changed since the table last read it (read on the next frame).
        self._stale = True
        #: The model-parameter editor while it is open: ``(store, DataTable, message)``.
        self.parameter_editor = None
        self._csv_dialog = None

        from emtk.widgets.buttons import SmallButton
        from emtk.widgets.data_table import DataTable

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
            id(self.btn_show_model): "Edit the model's parameters for this fit.",
            id(self.btn_copy): "Copy the visible rows and columns to the clipboard (tab separated).",
            id(self.btn_columns): "Choose which columns are shown (also: right-click the header).",
            id(self.btn_empty): "Hide columns that contain no values; press again to show them.",
            id(self.btn_shade): "Shade numeric cells by their value.",
            id(self.btn_scope): "Scale the shading across all columns instead of per column.",
            id(self.btn_export): "Export the visible rows and columns as CSV.",
        }
        self._refresh_arrays_into_model()

    # ── the page on the fit window's surface ────────────────────────────

    def emtk_draw(self, box) -> None:
        """The table page, or the parameter editor / CSV chooser while one is open."""
        from emtk import im

        if self._csv_dialog is not None:
            result = self._csv_dialog.draw()
            if result:
                self.export_csv(result[0])
                self._csv_dialog = None
            elif result is False:
                self._csv_dialog = None
            return
        if self.parameter_editor is not None:
            self._draw_parameter_editor()
            return
        if self._stale:
            self._refresh_arrays_into_model()
        im.host_control("##fit-table", self)

    # ── emtk control surface (what ControlHost forwards) ────────────────

    def animating(self) -> bool:
        """Nothing here moves on its own."""
        return False

    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        if self._stale:
            self._refresh_arrays_into_model()
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
            from emtk.file_dialog import FileDialog

            self._csv_dialog = FileDialog(
                "Export data table", mode="save", filters="CSV files (*.csv)",
                filename="data_table.csv",
            )
            self._request_repaint()
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

    def _refresh_arrays_into_model(self) -> None:
        """Re-read the fit into the emtk table, keeping filter, sort, selection."""
        self._stale = False
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

        self.table.columns = column_specs(keys)
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

    def update(self, *args, **kwargs) -> None:
        """The fit recomputed: re-read it when the page is next drawn."""
        super().update(*args, **kwargs)
        self._stale = True
        self._request_repaint()

    def on_copy_table_to_clipboard(self) -> None:
        """Copy every visible row and column, with header keys, to the clipboard."""
        from emtk import clipboard

        clipboard.copy(self.table_text("\t"))

    def _request_repaint(self) -> None:
        """Ask whatever shows the table to repaint."""
        self.request_redraw()

    # ── array plumbing ───────────────────────────────────────────────────

    def _get_arrays(self):
        """Return the fit's arrays, all aligned to the data length.

        ``x`` and the data are the full data arrays; the model and residuals are
        truncated or NaN-padded to match, and the residuals are placed inside the
        fit range rather than at the start.

        Returns
        -------
        tuple
            ``(x, y, model, weighted_residuals, mask, support_columns)`` where
            ``support_columns`` is a list of ``(name, array)`` pairs.
        """
        fit = self.fit
        data_curve = fit.data
        model_curve = fit.model
        wres_curve = fit.weighted_residuals

        x = np.asarray(data_curve.x, dtype=float)
        y = np.asarray(data_curve.y, dtype=float)
        nd = min(len(x), len(y))
        if nd == 0:
            return np.array([]), np.array([]), np.array([]), np.array([]), None, []
        x = x[:nd].copy()
        y = y[:nd].copy()

        ym_raw = np.asarray(model_curve.y, dtype=float)
        wres_raw = np.asarray(wres_curve.y, dtype=float)

        def align(arr: np.ndarray, n: int) -> np.ndarray:
            """Truncate or NaN-pad ``arr`` to length ``n``.

            Parameters
            ----------
            arr : numpy.ndarray
                Source array.
            n : int
                Target length.

            Returns
            -------
            numpy.ndarray
            """
            if arr is None:
                return np.full(n, np.nan, dtype=float)
            m = len(arr)
            if m >= n:
                return arr[:n].astype(float, copy=True)
            out = np.empty(n, dtype=float)
            out[:m] = arr.astype(float, copy=False)
            out[m:] = np.nan
            return out

        ym = align(ym_raw, nd)

        try:
            xmin, xmax = self.fit.fit_range
        except Exception:
            xmin, xmax = 0, nd - 1
        xmin = int(np.clip(xmin, 0, nd - 1))
        xmax = int(np.clip(xmax, 0, nd - 1))
        if xmax < xmin:
            xmin, xmax = xmax, xmin
        wres = np.full(nd, np.nan, dtype=float)
        try:
            seg_len = min(wres_raw.size, xmax - xmin + 1, nd - xmin)
            if seg_len > 0:
                wres[xmin : xmin + seg_len] = wres_raw[:seg_len].astype(float, copy=False)
        except Exception:
            wres = align(wres_raw, nd)

        try:
            mask_raw = getattr(self.fit, "mask", None)
        except Exception:
            mask_raw = None
        mask = np.ones(nd, dtype=float)
        if mask_raw is not None:
            try:
                m = np.asarray(mask_raw, dtype=float).ravel()
            except Exception:
                m = np.array([], dtype=float)
            k = min(nd, m.size)
            if k > 0:
                mask[:k] = m[:k]
        if wres.size == nd:
            try:
                wres = wres * mask
            except Exception:
                pass

        support_columns: list[tuple[str, np.ndarray]] = []
        try:
            curves = self.fit.get_curves(copy_curves=False)
        except Exception:
            curves = {}
        for name, curve in getattr(curves, "items", lambda: [])():
            if name in _SUPPORT_EXCLUSIONS:
                continue
            try:
                arr = np.asarray(curve.y, dtype=float)
            except Exception:
                continue
            support_columns.append((name, align(arr, nd)))

        return x, y, ym, wres, mask, support_columns

    def _set_arrays(self, x: np.ndarray, y: np.ndarray) -> None:
        """Write ``x`` and the data back to the fit and trigger a recompute.

        Parameters
        ----------
        x : numpy.ndarray
            Independent variable.
        y : numpy.ndarray
            Measured data.
        """
        data_curve = self.fit.data
        ex = getattr(data_curve, "ex", None)
        ey = getattr(data_curve, "ey", None)
        if ex is None or len(ex) != len(x):
            ex = np.ones_like(x)
        if ey is None or len(ey) != len(y):
            ey = np.ones_like(y)
        data_curve.set_data(x=x, y=y, ex=ex, ey=ey)

        fc = get_fitting_client()
        if fc is not None:
            fit_uid = str(getattr(self.fit, "unique_identifier", "") or "")
            if fit_uid:
                fc.update_fit(fit_uid=fit_uid)

    def _set_mask(self, mask: np.ndarray) -> None:
        """Send an edited fit mask to the backend and trace it.

        Parameters
        ----------
        mask : numpy.ndarray
            One weight per data channel; non-zero includes the channel.
        """
        try:
            m = np.asarray(mask, dtype=float).ravel()
        except Exception:
            return
        fc = get_fitting_client()
        if fc is not None:
            fit_uid = str(getattr(self.fit, "unique_identifier", "") or "")
            if fit_uid:
                fc.set_fit_mask(mask=m.tolist(), fit_uid=fit_uid)
        try:
            fit_group_name = str(getattr(self.fit, "name", ""))
            record_action(
                action_type="fit_mask_set",
                summary=(
                    f"set fit mask for '{fit_group_name}' "
                    f"({int(np.count_nonzero(m))}/{int(m.size)} active)"
                ),
                payload={
                    "fit_group": fit_group_name,
                    "mask_size": int(m.size),
                    "mask_active": int(np.count_nonzero(m)),
                    "source": "table_plot",
                },
            )
        except Exception:
            pass

    # ── model-parameter editor ───────────────────────────────────────────

    def _parameter_frame(self, param_dict):
        """Build the editable table of model parameters.

        Parameters
        ----------
        param_dict : dict
            Mapping of parameter name to parameter object.

        Returns
        -------
        tttrlib.DataStore
            Columns ``name``, ``value``, ``lb``, ``ub``, ``fixed``,
            ``bounds_on``, ``linked`` and ``link_target``.
        """
        rows = []
        for name, p in param_dict.items():
            try:
                value = float(p.value)
            except Exception:
                value = np.nan
            lb, ub = p.bounds
            try:
                lb_val = float(lb) if lb is not None else np.nan
            except Exception:
                lb_val = np.nan
            try:
                ub_val = float(ub) if ub is not None else np.nan
            except Exception:
                ub_val = np.nan
            link_obj = getattr(p, "link", None)
            rows.append(
                {
                    "name": name,
                    "value": value,
                    "lb": lb_val,
                    "ub": ub_val,
                    "fixed": bool(p.fixed),
                    "bounds_on": bool(getattr(p, "bounds_on", False)),
                    "linked": bool(getattr(p, "is_linked", False)),
                    "link_target": str(getattr(link_obj, "name", "") or ""),
                }
            )
        return store_from_rows(rows)

    def on_show_model(self) -> None:
        """Open the model-parameter editor in the page's place."""
        from emtk.widgets.data_table import DataTable, TableColumn

        model = self.fit.model
        try:
            param_dict = model.parameters_all_dict
        except Exception:
            param_dict = {p.name: p for p in getattr(model, "parameters", [])}
        store = self._parameter_frame(param_dict)
        records = [dict(row) for row in rows_from_table(store)] if row_count(store) else []
        for record in records:
            for key in ("fixed", "bounds_on", "linked"):
                record[key] = _parse_bool(record.get(key))
        table = DataTable(filter_box=True)
        table.columns = [
            TableColumn(key=key, title=key, editable=key != "name", tooltip=tip)
            for key, tip in _PARAMETER_COLUMNS
        ]
        table.set_records(records)
        message = "" if records else "The model exposes no editable parameters."
        self.parameter_editor = (records, param_dict, table, message)
        self._request_repaint()

    def apply_parameter_editor(self) -> None:
        """Push the edited parameters through the fitting client and close the editor."""
        if self.parameter_editor is None:
            return
        records, param_dict, _table, _message = self.parameter_editor
        self.parameter_editor = None
        if records:
            self._apply_parameter_table(store_from_rows(records), param_dict)
        self._request_repaint()

    def cancel_parameter_editor(self) -> None:
        """Close the editor, changing nothing."""
        self.parameter_editor = None
        self._request_repaint()

    def _draw_parameter_editor(self) -> None:
        from emtk import im

        records, _params, table, message = self.parameter_editor
        im.text("Model parameters")
        if message:
            im.text_disabled(message)
        else:
            width, height = im.get_content_region_avail()
            row = im.get_frame_height_with_spacing()
            im.host_control("##fit-table-parameters", table, (width, max(height - row - 4.0, 60.0)))
        if im.button("Apply"):
            self.apply_parameter_editor()
        im.set_item_tooltip("Write the edited values, bounds, fixes and links to the fit.")
        im.same_line()
        if im.button("Cancel"):
            self.cancel_parameter_editor()
        im.set_item_tooltip("Close the editor; nothing changes.")

    def _apply_parameter_table(self, table, param_dict) -> None:
        """Push an edited parameter table back through the fitting client.

        Parameters
        ----------
        table : tttrlib.DataStore
            The accepted table, in the layout :meth:`_parameter_frame` produces.
        param_dict : dict
            Mapping of parameter name to parameter object.
        """
        fc = get_fitting_client()
        if fc is None:
            return
        fit_uid = str(getattr(self.fit, "unique_identifier", "") or "")
        fit_idx = getattr(self.fit, "fit_idx", None)

        def notna(v):
            return v is not None and not (isinstance(v, float) and math.isnan(v))

        for row in rows_from_table(table):
            name = row.get("name")
            if name not in param_dict:
                continue

            try:
                if notna(row.get("value")):
                    fc.set_parameter_value(
                        name, float(row["value"]), fit_uid=fit_uid, fit_index=fit_idx
                    )
            except Exception:
                pass

            try:
                if notna(row.get("lb")) and notna(row.get("ub")):
                    fc.set_parameter_bounds(
                        name,
                        (float(row["lb"]), float(row["ub"])),
                        fit_uid=fit_uid,
                        fit_index=fit_idx,
                    )
            except Exception:
                pass

            try:
                fc.set_parameter_fixed(
                    name, _parse_bool(row.get("fixed")), fit_uid=fit_uid, fit_index=fit_idx
                )
            except Exception:
                pass

            try:
                fc.set_parameter_bounds_on(
                    name, _parse_bool(row.get("bounds_on")), fit_uid=fit_uid, fit_index=fit_idx
                )
            except Exception:
                pass

            target = str(row.get("link_target") or "").strip()
            try:
                if _parse_bool(row.get("linked")) and target in param_dict and target != name:
                    fc.link_parameters(name, target, fit_uid=fit_uid, fit_index=fit_idx)
                else:
                    fc.unlink_parameter(name, fit_uid=fit_uid, fit_index=fit_idx)
            except Exception:
                pass

        fc.update_fit(fit_uid=fit_uid, fit_index=fit_idx)
        fc.model_finalize(fit_uid=fit_uid, fit_index=fit_idx)
        self._refresh_arrays_into_model()


def _parse_bool(value) -> bool:
    """Interpret a table cell as a boolean.

    Parameters
    ----------
    value : object
        A bool, number or string such as ``"True"``.

    Returns
    -------
    bool
    """
    try:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)):
            return int(value) != 0
        if isinstance(value, (float, np.floating)):
            return float(value) != 0.0
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "t", "yes", "y", "on")
    except Exception:
        pass
    return False
