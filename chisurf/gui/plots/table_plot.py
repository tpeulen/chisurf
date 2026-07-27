"""The "Data table" plot — a fit's curves as a table.

Shows ``x``, the data, the model, the weighted residuals, the fit mask and every
support curve the model exposes, with ``x``/data/mask editable and edits routed
back through the fitting client so the fit recomputes.

Both the main table and the "Show model" parameter editor are
:mod:`chisurf.gui.widgets.chitable` widgets. They previously leaned on a
third-party ``DataFrameEditor`` that had to be fought after construction — its
background colouring stripped by one proxy, its ``name`` column locked by
another, checkboxes grafted onto its boolean columns — which is what motivated
having a table of our own.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from qtpy import QtCore, QtWidgets

import chisurf.core.fitting
from chisurf.core.actions import record_action
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.plots import plotbase
from chisurf.gui.widgets.chitable import (
    ArraySource,
    ChiTableWidget,
    ColumnSpec,
    edit_dataframe,
)
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

#: Curves that already have a dedicated column and must not be repeated.
_SUPPORT_EXCLUSIONS = {"data", "model", "weighted residuals", "autocorrelation"}

#: The fixed leading columns, in order, with the keys used for edit routing.
_BASE_COLUMNS = ("x", "data", "model", "w. res.", "mask")

#: Columns whose cells the user may edit.
_EDITABLE_COLUMNS = ("x", "data", "mask")


def _fit_column_specs(keys: Sequence[str]) -> list[ColumnSpec]:
    """Build the column specs for a fit table.

    Parameters
    ----------
    keys : sequence of str
        Column keys in table order, base columns first.

    Returns
    -------
    list of ColumnSpec
    """
    specs = []
    for key in keys:
        if key == "mask":
            specs.append(
                ColumnSpec(
                    key=key,
                    label="mask",
                    kind="float",
                    editable=True,
                    width=55,
                    tooltip="1 includes the channel in the fit, 0 excludes it",
                )
            )
            continue
        specs.append(
            ColumnSpec(
                key=key,
                label=key,
                kind="float",
                editable=key in _EDITABLE_COLUMNS,
                colorize=True,
                width=90 if key != "x" else 80,
            )
        )
    return specs


class FitTablePlot(plotbase.Plot):
    """Table view of a fit's data, model and residuals.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        The fit to display.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    **kwargs
        Forwarded to :class:`chisurf.gui.plots.plotbase.Plot`.
    """

    name = "Data table"

    def __init__(
        self,
        fit: chisurf.core.fitting.fit.Fit,
        parent: QtWidgets.QWidget | None = None,
        **kwargs,
    ):
        super().__init__(fit, parent=parent, **kwargs)

        self._source: ArraySource | None = None
        self._column_keys: tuple[str, ...] = ()
        self._refresh_pending = False
        self._applying_edit = False

        controls = QtWidgets.QWidget(self)
        h = QtWidgets.QHBoxLayout(controls)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        self.btn_show_model = QtWidgets.QToolButton(controls)
        self.btn_show_model.setText(f"{Glyphs.SETTINGS} Model")
        self.btn_show_model.setToolTip("Open a table editor for the model parameters")
        self.btn_show_model.clicked.connect(self.on_show_model)

        self.btn_copy = QtWidgets.QToolButton(controls)
        self.btn_copy.setText(Glyphs.COPY)
        self.btn_copy.setToolTip("Copy the whole table, with headers, to the clipboard")
        self.btn_copy.clicked.connect(self.on_copy_table_to_clipboard)

        self.lbl_info = QtWidgets.QLabel("", controls)
        self.lbl_info.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        h.addWidget(self.btn_show_model)
        h.addWidget(self.btn_copy)
        h.addStretch(1)
        h.addWidget(self.lbl_info)

        self.table = ChiTableWidget(parent=self)

        self.layout.addWidget(controls)
        self.layout.addWidget(self.table)

        self._refresh_arrays_into_model()

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

    def _on_cell_set(self, key: str, _row: int, _value) -> None:
        """Route a cell edit back to the fit.

        Parameters
        ----------
        key : str
            Column key that was edited.
        _row : int
            Edited row (unused; whole columns are pushed).
        _value : object
            New value (unused; read back from the source).
        """
        if self._applying_edit or self._source is None:
            return
        self._applying_edit = True
        try:
            if key in ("x", "data"):
                x = np.asarray(self._source.column_array(0), dtype=float)
                y = np.asarray(self._source.column_array(1), dtype=float)
                self._set_arrays(x, y)
            elif key == "mask":
                self._set_mask(np.asarray(self._source.column_array(4), dtype=float))
            else:
                return
        finally:
            self._applying_edit = False
        self._refresh_arrays_into_model()

    def _refresh_arrays_into_model(self) -> None:
        """Re-read the fit into the table, keeping filter, sort and visibility."""
        if not self.isVisible():
            self._refresh_pending = True
            return
        x, y, ym, wres, mask, support = self._get_arrays()
        if mask is None:
            mask = np.ones_like(x)
        columns = list(zip(_BASE_COLUMNS, (x, y, ym, wres, mask))) + support
        keys = tuple(k for k, _ in columns)
        specs = _fit_column_specs(keys)

        if self._source is None or keys != self._column_keys:
            # A changed column set means new headers and delegates; anything
            # else would leave the view describing the previous model.
            self._column_keys = keys
            self._source = ArraySource(columns, specs=specs, on_set=self._on_cell_set)
            self.table.set_source(self._source)
        else:
            self._source.set_columns(columns, specs=specs)
            self.table.refresh()

        chi2r = getattr(self.fit, "chi2r", float("nan"))
        self.lbl_info.setText(f"N={x.size}  |  χ²ᵣ={chi2r:.4g}")
        self._refresh_pending = False

    # ── Qt / Plot API ────────────────────────────────────────────────────

    def showEvent(self, event):  # noqa: N802, D102 (Qt override)
        super().showEvent(event)
        if getattr(self, "_refresh_pending", False):
            self._refresh_arrays_into_model()

    def update(self, *args, **kwargs) -> None:
        """Re-read the fit after a recompute.

        Parameters
        ----------
        *args
            Forwarded to the base plot.
        **kwargs
            Forwarded to the base plot.
        """
        super().update(*args, **kwargs)
        self._refresh_arrays_into_model()

    def on_copy_table_to_clipboard(self) -> None:
        """Copy every visible row and column, with headers, to the clipboard."""
        view = self.table.table_view
        model = view.chitable_model()
        if model is not None:
            model.fetch_all()
        view.clearSelection()
        view.copy_selection(include_header=True)

    # ── model-parameter editor ───────────────────────────────────────────

    def _parameter_frame(self, param_dict) -> pd.DataFrame:
        """Build the editable frame of model parameters.

        Parameters
        ----------
        param_dict : dict
            Mapping of parameter name to parameter object.

        Returns
        -------
        pandas.DataFrame
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
        return pd.DataFrame(rows).reset_index(drop=True)

    def on_show_model(self) -> None:
        """Open the model-parameter table and apply the accepted edits."""
        model = self.fit.model
        try:
            param_dict = model.parameters_all_dict
        except Exception:
            param_dict = {p.name: p for p in getattr(model, "parameters", [])}

        df = self._parameter_frame(param_dict)
        if df.empty:
            QtWidgets.QMessageBox.information(
                self, "No parameters", "Model exposes no editable parameters."
            )
            return

        new_df = edit_dataframe(
            df,
            parent=self,
            title="Model parameters",
            readonly_columns=("name",),
            bool_columns=("fixed", "bounds_on", "linked"),
            colorize_columns=(),
        )
        if new_df is None:
            return
        self._apply_parameter_frame(new_df, param_dict)

    def _apply_parameter_frame(self, new_df: pd.DataFrame, param_dict) -> None:
        """Push an edited parameter frame back through the fitting client.

        Parameters
        ----------
        new_df : pandas.DataFrame
            The accepted frame, in the layout :meth:`_parameter_frame` produces.
        param_dict : dict
            Mapping of parameter name to parameter object.
        """
        fc = get_fitting_client()
        if fc is None:
            return
        fit_uid = str(getattr(self.fit, "unique_identifier", "") or "")
        fit_idx = getattr(self.fit, "fit_idx", None)

        for _, row in new_df.iterrows():
            name = row.get("name")
            if name not in param_dict:
                continue

            try:
                if pd.notna(row.get("value")):
                    fc.set_parameter_value(
                        name, float(row["value"]), fit_uid=fit_uid, fit_index=fit_idx
                    )
            except Exception:
                pass

            try:
                if pd.notna(row.get("lb")) and pd.notna(row.get("ub")):
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
