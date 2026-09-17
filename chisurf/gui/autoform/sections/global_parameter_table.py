"""Global parameter table — every fitting parameter across fits *and* plugins.

This is the AutoForm ``global_parameter_table`` custom section that backs the
Global View's *Parameters* tab. Unlike
:class:`~chisurf.gui.autoform.sections.parameter_table.ParameterGroupTableWidget`
(one group, in-process edits), this widget:

* spans **multiple owners** — every fit in ``chisurf.fits`` (descending into
  :class:`FitGroup` members, skipping the aggregate :class:`GlobalFitModel`) plus
  every out-of-fit group registered via
  :mod:`chisurf.core.registry.parameter_groups` (e.g. a plugin working model);
* routes all edits/links through an injected **mutator** (default: the
  :class:`~chisurf.gui.widgets.fitting.fitting_client.FittingClient`) so mutations
  are RPC-mediated, and out-of-fit parameters are addressed by their global
  ``unique_identifier`` (see the ``parameter_uid`` path in
  :mod:`chisurf.server.services.parameters`);
* carries an **Owner** column and a cross-owner **Link** column so any parameter
  can be linked to any other by row number.

Registered under the key ``"global_parameter_table"``; emit it from a model's
``view_spec`` as a :class:`~chisurf.core.dataspec.CustomSection`.
"""

from __future__ import annotations

import re

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

import chisurf as cs
from chisurf import logging
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.parameter import Parameter
from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups
from chisurf.gui import dialogs
from chisurf.gui.autoform.sections.parameter_table import (
    _BooleanToggleDelegate,
    _FloatEditDelegate,
    _RichTextDelegate,
)
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.chitable import ChiTableWidget, TableFeature
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

# ── column enumeration ──────────────────────────────────────────────────

COL_ROW = 0
COL_OWNER = 1
COL_LOCAL = 2
COL_PARAM = 3
COL_VALUE = 4
COL_FIXED = 5
COL_LO = 6
COL_HI = 7
COL_BOUNDS_ON = 8
COL_ERROR = 9
COL_LINK = 10

HEADERS = [
    "Row",
    "Owner",
    "Local",
    "Parameter",
    "Value",
    "Fixed",
    "Lo",
    "Hi",
    "Bounds",
    "Error",
    "Link row",
]


class GlobalParamRow:
    """One table row: a parameter and everything needed to address its owner.

    ``kind`` is ``"fit"`` (owner is a :class:`Fit`; addressed by ``fit_uid`` /
    ``fit_index`` [+ ``local_idx``] + name) or ``"group"`` (an out-of-fit
    registered group; addressed by the parameter's global ``param_uid`` and the
    group's ``owner_uid``).
    """

    __slots__ = (
        "kind",
        "owner_label",
        "local_label",
        "param",
        "param_uid",
        "owner_uid",
        "fit_uid",
        "fit_index",
        "local_idx",
    )

    def __init__(
        self,
        kind,
        owner_label,
        local_label,
        param,
        param_uid,
        owner_uid=None,
        fit_uid=None,
        fit_index=None,
        local_idx=None,
    ):
        self.kind = kind
        self.owner_label = owner_label
        self.local_label = local_label
        self.param = param
        self.param_uid = param_uid
        self.owner_uid = owner_uid
        self.fit_uid = fit_uid
        self.fit_index = fit_index
        self.local_idx = local_idx


def _uid(obj) -> str:
    return str(getattr(obj, "unique_identifier", "") or "")


def enumerate_global_rows() -> list[GlobalParamRow]:
    """Return every fitting parameter across fits and registered plugin groups.

    Fits come from the live ``chisurf.fits`` list (descending into
    :class:`FitGroup` members and skipping the aggregate
    :class:`GlobalFitModel`); out-of-fit groups come from
    :func:`iter_registered_parameter_groups`.
    """
    from chisurf.core.models.global_model import GlobalFitModel

    rows: list[GlobalParamRow] = []
    fits = list(getattr(cs, "fits", []) or [])

    for fi, fit in enumerate(fits):
        model = getattr(fit, "model", None)
        if isinstance(model, GlobalFitModel):
            continue
        owner_label = str(getattr(fit, "name", f"Fit {fi}"))
        if isinstance(fit, FitGroup) and getattr(fit, "grouped_fits", None):
            for li, local_fit in enumerate(fit.grouped_fits):
                lmodel = getattr(local_fit, "model", None)
                for p in getattr(lmodel, "parameters_all", []) or []:
                    rows.append(
                        GlobalParamRow(
                            "fit",
                            owner_label,
                            f"[{li}]",
                            p,
                            _uid(p),
                            owner_uid=_uid(lmodel),
                            fit_uid=_uid(fit),
                            fit_index=fi,
                            local_idx=li,
                        )
                    )
        else:
            for p in getattr(model, "parameters_all", []) or []:
                rows.append(
                    GlobalParamRow(
                        "fit",
                        owner_label,
                        "",
                        p,
                        _uid(p),
                        owner_uid=_uid(model),
                        fit_uid=_uid(fit),
                        fit_index=fi,
                    )
                )

    for owner_id, label, group in iter_registered_parameter_groups():
        for p in getattr(group, "parameters_all", []) or []:
            rows.append(
                GlobalParamRow(
                    "group",
                    label,
                    "",
                    p,
                    _uid(p),
                    owner_uid=_uid(group),
                )
            )

    return rows


# ── mutator ─────────────────────────────────────────────────────────────


class FittingClientParamMutator:
    """Route parameter edits/links through the :class:`FittingClient`.

    Fit rows keep the proven fit-addressed RPC path; group (out-of-fit) rows use
    the ``parameter_uid`` / ``owner_uid`` path so their parameters resolve via the
    server's global ``Base._uuid_index``.
    """

    def _addr(self, row: GlobalParamRow) -> dict:
        """Return the RPC kwargs that address *row*'s parameter for the source."""
        if row.kind == "fit":
            return {
                "parameter_name": str(getattr(row.param, "name", "")),
                "fit_uid": row.fit_uid or None,
                "fit_index": row.fit_index,
                "local_idx": row.local_idx,
            }
        return {
            "parameter_name": str(getattr(row.param, "name", "")),
            "parameter_uid": row.param_uid,
            "owner_uid": row.owner_uid,
        }

    def set_value(self, row, value):
        fc = get_fitting_client()
        return fc.set_parameter_value(value=value, **self._addr(row)) if fc else {"ok": False}

    def set_fixed(self, row, fixed):
        fc = get_fitting_client()
        return fc.set_parameter_fixed(fixed=fixed, **self._addr(row)) if fc else {"ok": False}

    def set_bounds(self, row, bounds):
        fc = get_fitting_client()
        return fc.set_parameter_bounds(bounds=bounds, **self._addr(row)) if fc else {"ok": False}

    def set_bounds_on(self, row, bounds_on):
        fc = get_fitting_client()
        return (
            fc.set_parameter_bounds_on(bounds_on=bounds_on, **self._addr(row))
            if fc
            else {"ok": False}
        )

    def link(self, src, target):
        fc = get_fitting_client()
        if fc is None:
            return {"ok": False}
        kw = self._addr(src)
        # Target is always addressable by its global uid, regardless of owner kind.
        kw["target_parameter_name"] = str(getattr(target.param, "name", ""))
        kw["target_parameter_uid"] = target.param_uid
        return fc.link_parameters(**kw)

    def unlink(self, row):
        fc = get_fitting_client()
        return fc.unlink_parameter(**self._addr(row)) if fc else {"ok": False}


# ── table model ─────────────────────────────────────────────────────────


class GlobalParameterTableModel(QtCore.QAbstractTableModel):
    """Flat table over :func:`enumerate_global_rows`, edited via a *mutator*."""

    def __init__(self, mutator=None, parent=None):
        super().__init__(parent)
        self._rows: list[GlobalParamRow] = []
        self._mutator = mutator or FittingClientParamMutator()

    # -- population -------------------------------------------------------

    def refresh(self):
        """Re-enumerate rows from the live fits + registered groups."""
        self.beginResetModel()
        self._rows = enumerate_global_rows()
        self.endResetModel()

    def row_at(self, r: int) -> GlobalParamRow | None:
        return self._rows[r] if 0 <= r < len(self._rows) else None

    # -- shape ------------------------------------------------------------

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self._rows) if not parent.isValid() else 0

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(HEADERS) if not parent.isValid() else 0

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return HEADERS[section]
        return None

    # -- data -------------------------------------------------------------

    @staticmethod
    def _is_follower(param) -> bool:
        return bool(getattr(param, "is_linked", False)) and not bool(
            getattr(param, "is_link_master", False)
        )

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        p = row.param
        col = index.column()

        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if col == COL_ROW:
                return str(index.row() + 1)
            if col == COL_OWNER:
                return row.owner_label
            if col == COL_LOCAL:
                return row.local_label
            if col == COL_PARAM:
                return str(getattr(p, "name", ""))
            if col == COL_VALUE:
                v = getattr(p, "value", None)
                return f"{v:.6g}" if v is not None else ""
            if col == COL_FIXED:
                return bool(getattr(p, "fixed", False))
            if col in (COL_LO, COL_HI):
                b = getattr(p, "bounds", None)
                i = 0 if col == COL_LO else 1
                if b is not None and len(b) > i and b[i] is not None:
                    return f"{b[i]:.6g}"
                return ""
            if col == COL_BOUNDS_ON:
                return bool(getattr(p, "bounds_on", False))
            if col == COL_ERROR:
                e = getattr(p, "error_estimate", None)
                if e is not None and np.isfinite(e):
                    return f"{e:.4g}"
                return ""
            if col == COL_LINK:
                tr = self._link_target_row(index.row())
                return str(tr + 1) if tr is not None else ""

        if role == QtCore.Qt.ToolTipRole:
            if col == COL_PARAM:
                return getattr(p, "description", "") or None
            if col == COL_LINK:
                return "Enter the target Row number to link this parameter to it."

        if role == QtCore.Qt.TextAlignmentRole:
            if col in (COL_VALUE, COL_LO, COL_HI, COL_ERROR):
                return int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            if col in (COL_ROW, COL_FIXED, COL_BOUNDS_ON, COL_LINK):
                return int(QtCore.Qt.AlignCenter)

        # Same reading as the parameter tables: italic where the value is
        # borrowed from another parameter, dimmed where the fit will not move it.
        if role == QtCore.Qt.FontRole and self._is_follower(p):
            font = QtGui.QFont()
            font.setItalic(True)
            return font
        if role == QtCore.Qt.ForegroundRole and col == COL_VALUE:
            if bool(getattr(p, "fixed", False)) or self._is_follower(p):
                palette = QtWidgets.QApplication.palette()
                return palette.brush(QtGui.QPalette.Disabled, QtGui.QPalette.Text)

        return None

    def _link_target_row(self, r: int) -> int | None:
        """Return the table-row index of the parameter *r* is linked to."""
        link = getattr(self._rows[r].param, "link", None)
        if link is None:
            return None
        for i, other in enumerate(self._rows):
            if other.param is link:
                return i
        return None

    # -- editing ----------------------------------------------------------

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        f = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        col = index.column()
        p = self._rows[index.row()].param
        follower = self._is_follower(p)
        if col == COL_VALUE and not follower:
            f |= QtCore.Qt.ItemIsEditable
        if col in (COL_FIXED, COL_BOUNDS_ON, COL_LINK):
            f |= QtCore.Qt.ItemIsEditable
        if col in (COL_LO, COL_HI) and getattr(p, "bounds_on", False) and not follower:
            f |= QtCore.Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role != QtCore.Qt.EditRole or not index.isValid():
            return False
        row = self._rows[index.row()]
        col = index.column()

        if col == COL_VALUE:
            try:
                ok = self._mutator.set_value(row, float(value)).get("ok", False)
            except (TypeError, ValueError):
                return False
        elif col == COL_FIXED:
            ok = self._mutator.set_fixed(row, _as_bool(value)).get("ok", False)
        elif col == COL_BOUNDS_ON:
            ok = self._mutator.set_bounds_on(row, _as_bool(value)).get("ok", False)
        elif col in (COL_LO, COL_HI):
            try:
                b = list(getattr(row.param, "bounds", (0.0, 0.0)))
                b[0 if col == COL_LO else 1] = float(value)
                ok = self._mutator.set_bounds(row, tuple(b)).get("ok", False)
            except (TypeError, ValueError):
                return False
        elif col == COL_LINK:
            return self._set_link(index, value)
        else:
            return False

        if ok:
            self.dataChanged.emit(index, index)
        return bool(ok)

    def _set_link(self, index, value) -> bool:
        row = self._rows[index.row()]
        text = str(value).strip()
        if not text:
            ok = self._mutator.unlink(row).get("ok", False)
            if ok:
                self.dataChanged.emit(index, index)
            return bool(ok)
        if not re.fullmatch(r"\d+", text):
            return False
        tr = int(text) - 1
        if not 0 <= tr < len(self._rows):
            return False
        target = self._rows[tr]
        if target.param is row.param:
            _warn("Cannot link a parameter to itself.")
            return False
        try:
            if Parameter.check_recursive_link(target.param, row.param):
                _warn(
                    f"Cannot link '{getattr(row.param, 'name', '')}' → "
                    f"'{getattr(target.param, 'name', '')}': this would create a "
                    "cyclic dependency."
                )
                return False
        except Exception:
            pass
        result = self._mutator.link(row, target)
        if not result.get("ok", False):
            _warn(f"Link failed: {result.get('error', 'unknown error')}")
            return False
        self.dataChanged.emit(index, index)
        return True


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _warn(message: str) -> None:
    """Show a modal warning if a Qt app is running, else log it."""
    if QtWidgets.QApplication.instance() is None:
        logging.warning(message)
        return
    try:
        dialogs.warning(QtWidgets.QApplication.activeWindow(), "Linking", message)
    except Exception:
        logging.warning(message)


# ── widget ───────────────────────────────────────────────────────────────


class GlobalParameterTableWidget(QtWidgets.QWidget):
    """Every parameter across fits and registered plugin groups, as a table.

    The table itself is a :class:`~chisurf.gui.widgets.chitable.ChiTableWidget`
    wrapped around :class:`GlobalParameterTableModel` through the *foreign model*
    path: the model keeps its own semantics — RPC-mediated edits, and the Link
    column addressing parameters by **source** row number — while gaining search,
    per-column filters, sorting, column hiding, headered copy and CSV export.

    Rewriting the model onto a chitable source was deliberately not done: the row
    numbers in the Link column are part of the data, and they stay meaningful
    only because filtering and sorting happen in a layer above the model.

    Opts into ``AUTOFORM_REFRESH`` so :meth:`AutoForm.refresh_plots` re-reads the
    rows; also refreshes on registry changes and ``parameter.`` RPC events.
    """

    AUTOFORM_REFRESH = True

    def __init__(self, mutator=None, parent=None):
        super().__init__(parent)
        self._model = GlobalParameterTableModel(mutator=mutator, parent=self)

        self._table = ChiTableWidget(
            model=self._model,
            features=(
                TableFeature.SEARCH
                | TableFeature.COLUMN_FILTERS
                | TableFeature.SORT
                | TableFeature.COLUMN_PICKER
                | TableFeature.COLOR_BY_VALUE
                | TableFeature.EXPORT
                | TableFeature.STATUSBAR
            ),
            parent=self,
        )

        self._view = self._table.table_view
        self._view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.SelectedClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self._view.setItemDelegateForColumn(COL_PARAM, _RichTextDelegate(self._view))
        self._view.setItemDelegateForColumn(COL_VALUE, _FloatEditDelegate(self._view))
        self._view.setItemDelegateForColumn(COL_LO, _FloatEditDelegate(self._view))
        self._view.setItemDelegateForColumn(COL_HI, _FloatEditDelegate(self._view))
        self._view.setItemDelegateForColumn(COL_FIXED, _BooleanToggleDelegate(self._view))
        self._view.setItemDelegateForColumn(COL_BOUNDS_ON, _BooleanToggleDelegate(self._view))
        self._view.horizontalHeader().setStretchLastSection(True)
        # Only Value and Error carry a magnitude worth shading; the rest are
        # identifiers, flags and row numbers.
        proxy = self._table.proxy
        if proxy is not None:
            proxy.set_color_scheme(None, columns={COL_VALUE, COL_ERROR})

        refresh_btn = QtWidgets.QToolButton(self)
        refresh_btn.setText(Glyphs.REFRESH)
        refresh_btn.setToolTip("Reload parameters from all fits and plugins")
        refresh_btn.clicked.connect(self.refresh)

        # No title of its own: the hosting section already captions this widget,
        # and printing "All fitting parameters" twice, one line apart, only
        # costs a row of the table.
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addStretch(1)
        bar.addWidget(refresh_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(bar)
        layout.addWidget(self._table, 1)

        # A table is the whole point of the panel it sits in, so it takes the
        # spare height instead of being capped at its size hint with dead space
        # under it. The marker is what AutoForm looks for when deciding which
        # section gets the stretch.
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._autoform_expanding = True

        self._subscribe_events()
        self.refresh()

    # -- accessors --------------------------------------------------------

    @property
    def table_model(self) -> GlobalParameterTableModel:
        """Return the source model (never the filter proxy).

        Returns
        -------
        GlobalParameterTableModel
        """
        return self._model

    @property
    def table_view(self) -> QtWidgets.QTableView:
        """Return the view.

        Returns
        -------
        qtpy.QtWidgets.QTableView
        """
        return self._view

    @property
    def table(self) -> ChiTableWidget:
        """Return the chitable container.

        Returns
        -------
        chisurf.gui.widgets.chitable.ChiTableWidget
        """
        return self._table

    # -- refresh wiring ---------------------------------------------------

    def refresh(self):
        """Re-enumerate rows and resize columns, keeping filter and sort."""
        self._table.refresh()
        self._view.auto_resize_columns()

    def _subscribe_events(self):
        # Registry changes (a plugin (un)registers its working model).
        try:
            from chisurf.core.registry import parameter_groups as reg

            reg.subscribe(self._on_external_change)
            self._registry_cb = self._on_external_change
        except Exception:
            self._registry_cb = None
        # parameter.* / fit.* RPC events (a parameter changed, or fits were
        # added/removed/reordered elsewhere).
        try:
            fc = get_fitting_client()
            if fc is not None:

                def cb(*a, **k):
                    return self._on_external_change()

                fc.subscribe("parameter.", cb)
                fc.subscribe("fit.", cb)
        except Exception:
            pass

    def _on_external_change(self, *args, **kwargs):
        # Coalesce onto the GUI thread; refresh is cheap enough to run directly.
        try:
            self.refresh()
        except Exception:
            logging.exception("GlobalParameterTableWidget: refresh on event failed")

    def closeEvent(self, event):
        cb = getattr(self, "_registry_cb", None)
        if cb is not None:
            try:
                from chisurf.core.registry import parameter_groups as reg

                reg.unsubscribe(cb)
            except Exception:
                pass
        super().closeEvent(event)


# ── AutoForm section registration ────────────────────────────────────────


@register_section("global_parameter_table")
def _global_parameter_table_factory(model=None, target=None, **options):
    """AutoForm factory for the ``global_parameter_table`` custom section.

    ``model`` / ``target`` are ignored (rows come from the live fit list and the
    parameter-group registry, not a single bound model). An optional ``mutator``
    may be supplied in the view-spec ``options`` for testing.
    """
    return GlobalParameterTableWidget(mutator=options.get("mutator"))
