"""Proxy giving chitable features to models chitable does not own.

Some tables carry irreplaceable semantics in a bespoke
:class:`~qtpy.QtCore.QAbstractTableModel` — the Global View's parameter table
routes every edit through an RPC mutator and addresses parameters by row number.
Rewriting those onto a :class:`~chisurf.gui.widgets.chitable.source.TableSource`
would be a behavioural change, so :class:`ForeignTableProxy` instead layers
searching, filtering, sorting and value colouring *on top* of the existing model.

This is explicitly the small-table path. It evaluates predicates per row in
Python, which is fine for the few thousand rows such tables hold and wrong for
burst-scale data — those use :class:`~chisurf.gui.widgets.chitable.model.ChiTableModel`,
whose filtering is vectorised.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtGui

from chisurf.gui.widgets.chitable.colorize import ValueColorScheme
from chisurf.gui.widgets.chitable.filters import NULL_OPS, NUMERIC_OPS, FilterSpec

#: Row count beyond which this proxy's per-row filtering becomes a bad idea.
LARGE_FOREIGN_ROWS = 50_000


def _as_float(value) -> float:
    """Coerce a cell value to ``float``, yielding ``NaN`` when impossible.

    Parameters
    ----------
    value : object
        Cell value from the source model.

    Returns
    -------
    float
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


class ForeignTableProxy(QtCore.QSortFilterProxyModel):
    """Add search, filtering and value colouring to an arbitrary table model.

    Parameters
    ----------
    parent : qtpy.QtCore.QObject, optional
        Owner object.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._filter = FilterSpec()
        self._color: ValueColorScheme | None = None
        self._colorize_columns: set = set()
        self._ranges: dict = {}
        self.setDynamicSortFilter(False)

    # ── filtering ────────────────────────────────────────────────────────

    @property
    def filter_spec(self) -> FilterSpec:
        """Return the active filter.

        Returns
        -------
        FilterSpec
        """
        return self._filter

    def set_filter(self, spec: FilterSpec | None) -> None:
        """Apply a filter spec and re-evaluate every row.

        Parameters
        ----------
        spec : FilterSpec or None
            The filter; ``None`` clears it.
        """
        self._filter = spec or FilterSpec()
        self.invalidateFilter()

    def _cell_text(self, row: int, col: int) -> str:
        """Return a source cell rendered as text.

        Parameters
        ----------
        row : int
            Source row index.
        col : int
            Source column index.

        Returns
        -------
        str
        """
        model = self.sourceModel()
        value = model.data(model.index(row, col), QtCore.Qt.DisplayRole)
        return "" if value is None else str(value)

    def filterAcceptsRow(self, row, parent) -> bool:  # noqa: N802, D102 (Qt override)
        model = self.sourceModel()
        if model is None or self._filter.is_empty:
            return True
        n_cols = model.columnCount()

        query = self._filter.query.strip().lower()
        if query:
            if not any(query in self._cell_text(row, c).lower() for c in range(n_cols)):
                return False

        for cf in self._filter.columns:
            col = cf.column
            if col < 0 or col >= n_cols:
                continue
            text = self._cell_text(row, col)
            if not self._accepts(cf, text):
                return False
        return True

    @staticmethod
    def _accepts(cf, text: str) -> bool:
        """Evaluate one predicate against one cell's text.

        Parameters
        ----------
        cf : ColumnFilter
            The predicate.
        text : str
            The cell's display text.

        Returns
        -------
        bool
        """
        if cf.op in NULL_OPS:
            blank = text.strip() == ""
            return blank if cf.op == "isnull" else not blank

        if cf.op in NUMERIC_OPS:
            value = _as_float(text)
            if not np.isfinite(value):
                return False
            lo = _as_float(cf.value)
            if not np.isfinite(lo):
                return True
            if cf.op == "gt":
                return value > lo
            if cf.op == "ge":
                return value >= lo
            if cf.op == "lt":
                return value < lo
            if cf.op == "le":
                return value <= lo
            hi = _as_float(cf.value2)
            if not np.isfinite(hi):
                return True
            if lo > hi:
                lo, hi = hi, lo
            inside = lo <= value <= hi
            return inside if cf.op == "between" else not inside

        pattern = "" if cf.value is None else str(cf.value)
        haystack = text if cf.case_sensitive else text.lower()
        needle = pattern if cf.case_sensitive else pattern.lower()
        if cf.op == "contains":
            return needle in haystack
        if cf.op == "not_contains":
            return needle not in haystack
        if cf.op == "equals":
            return haystack == needle
        if cf.op == "not_equals":
            return haystack != needle
        if cf.op == "startswith":
            return haystack.startswith(needle)
        if cf.op == "endswith":
            return haystack.endswith(needle)
        if cf.op == "regex":
            import re

            try:
                flags = 0 if cf.case_sensitive else re.IGNORECASE
                return re.search(pattern, text, flags) is not None
            except re.error:
                return True
        return True

    # ── colouring ────────────────────────────────────────────────────────

    def set_color_scheme(
        self,
        scheme: ValueColorScheme | None,
        columns: set | None = None,
    ) -> None:
        """Enable value-scaled backgrounds over the source model.

        Parameters
        ----------
        scheme : ValueColorScheme or None
            The policy; ``None`` strips colouring entirely, which is also how a
            source model's own background roles are suppressed.
        columns : set of int, optional
            Columns to colour. ``None`` colours every column whose values parse
            as numbers.
        """
        self._color = scheme
        self._colorize_columns = set(columns) if columns is not None else set()
        self._ranges.clear()
        self._emit_all_changed()

    def _column_range(self, col: int) -> tuple | None:
        """Return a source column's finite ``(min, max)``, memoised.

        Parameters
        ----------
        col : int
            Source column index.

        Returns
        -------
        tuple of float or None
        """
        if col in self._ranges:
            return self._ranges[col]
        model = self.sourceModel()
        out = None
        if model is not None:
            values = [_as_float(self._cell_text(r, col)) for r in range(model.rowCount())]
            arr = np.asarray(values, dtype="float64")
            finite = arr[np.isfinite(arr)]
            if finite.size:
                out = (float(np.min(finite)), float(np.max(finite)))
        self._ranges[col] = out
        return out

    def invalidate_ranges(self) -> None:
        """Drop cached colour ranges after the source data changed."""
        self._ranges.clear()

    def _emit_all_changed(self) -> None:
        """Signal that every proxied cell may have changed."""
        rows, cols = self.rowCount(), self.columnCount()
        if rows and cols:
            self.dataChanged.emit(self.index(0, 0), self.index(rows - 1, cols - 1))

    def lessThan(self, left, right) -> bool:  # noqa: N802, D102 (Qt override)
        # The source models this wraps render numbers as formatted strings, so
        # Qt's default comparison sorts "10" before "9". Compare numerically
        # whenever both cells parse as numbers, and fall back to text otherwise.
        lv = self.sourceModel().data(left, QtCore.Qt.DisplayRole)
        rv = self.sourceModel().data(right, QtCore.Qt.DisplayRole)
        lf, rf = _as_float(lv), _as_float(rv)
        if np.isfinite(lf) and np.isfinite(rf):
            return lf < rf
        return str(lv or "") < str(rv or "")

    def data(self, index, role=QtCore.Qt.DisplayRole):  # noqa: D102 (Qt override)
        if role in (QtCore.Qt.BackgroundRole, QtCore.Qt.BackgroundColorRole):
            if self._color is None:
                # Strips any background the source model paints — the behaviour
                # the old NoBackgroundProxy existed for.
                return None
            if not self._color.enabled:
                return None
            col = index.column()
            if self._colorize_columns and col not in self._colorize_columns:
                return None
            src = self.mapToSource(index)
            rng = self._column_range(col)
            if rng is None:
                return None
            value = _as_float(self._cell_text(src.row(), col))
            color = self._color.color(value, rng[0], rng[1])
            return color if color is not None else None
        return super().data(index, role)


class ReadOnlyColumnProxy(QtCore.QIdentityProxyModel):
    """Strip ``ItemIsEditable`` from columns named in a header set.

    Parameters
    ----------
    parent : qtpy.QtCore.QObject, optional
        Owner object.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._readonly_headers: set = set()

    def set_readonly_headers(self, headers) -> None:
        """Name the columns that must not be edited.

        Parameters
        ----------
        headers : iterable of str
            Header texts to lock.
        """
        self._readonly_headers = set(headers or ())

    def flags(self, index):  # noqa: D102 (Qt override)
        f = super().flags(index)
        header = self.headerData(index.column(), QtCore.Qt.Horizontal)
        if isinstance(header, str) and header in self._readonly_headers:
            f &= ~QtCore.Qt.ItemIsEditable
        return f


def foreground_for_missing() -> QtGui.QColor:
    """Return the grey used for blank numeric cells.

    Returns
    -------
    qtpy.QtGui.QColor
    """
    return QtGui.QColor("#999999")
