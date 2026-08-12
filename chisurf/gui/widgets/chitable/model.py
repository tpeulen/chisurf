"""The chitable table model.

:class:`ChiTableModel` is a single :class:`~qtpy.QtCore.QAbstractTableModel` that
sits on any :class:`~chisurf.gui.widgets.chitable.source.TableSource` and provides
— once, rather than once per call site — formatting, alignment, tooltips,
value-scaled backgrounds, vectorised filtering, stable sorting, staged edits and
row paging.

Filtering and sorting are carried by a *visible-row index array* rather than a
:class:`~qtpy.QtCore.QSortFilterProxyModel`. The proxy's ``filterAcceptsRow`` is a
Python call per row, which is untenable at burst scale; an index array is one
numpy pass. It also keeps source row indices stable and recoverable through
:meth:`source_row`, which matters wherever a table's own row numbers are part of
the data (the Global View links parameters by row number).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from qtpy import QtCore, QtGui

from chisurf.gui.widgets.chitable.colorize import ValueColorScheme
from chisurf.gui.widgets.chitable.columns import (
    DEFAULT_FORMAT,
    KIND_BOOL,
    KIND_STR,
    ColumnSpec,
    is_valid_format,
)
from chisurf.gui.widgets.chitable.filters import ColumnCache, FilterSpec
from chisurf.gui.widgets.chitable.source import (
    TableSource,
    coerce_value,
    is_blank,
    is_na,
)

#: Row count above which the model hands the view one page at a time.
LARGE_ROWS = 100_000
#: Rows added per :meth:`ChiTableModel.fetch_more` call.
ROWS_TO_LOAD = 500


class ChiTableModel(QtCore.QAbstractTableModel):
    """Table model over a :class:`TableSource`.

    Parameters
    ----------
    source : TableSource
        The data adapter.
    color_scheme : ValueColorScheme, optional
        Background colouring policy. A disabled default is created when omitted.
    default_format : str
        Printf-style format applied to float columns whose spec sets none.
    staged : bool
        When ``True`` edits are buffered until :meth:`commit` — the
        Apply/Cancel semantics a modal editor needs. When ``False`` edits go
        straight to the source.
    parent : qtpy.QtCore.QObject, optional
        Owner object.
    """

    #: Role returning the raw, unformatted cell value (for copy and export).
    RawRole = QtCore.Qt.UserRole + 512
    #: Role returning the numeric projection of a cell (for sorting aids).
    ValueRole = QtCore.Qt.UserRole + 513

    def __init__(
        self,
        source: TableSource,
        *,
        color_scheme: ValueColorScheme | None = None,
        default_format: str = DEFAULT_FORMAT,
        staged: bool = False,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._cache = ColumnCache(source)
        self._specs = list(source.column_specs())
        self._color = color_scheme or ValueColorScheme()
        self._default_format = default_format if is_valid_format(default_format) else DEFAULT_FORMAT
        self._staged_mode = bool(staged)
        self._staged: dict = {}

        self._filter = FilterSpec()
        self._visible = np.arange(source.row_count(), dtype=np.int64)
        self._sort_column = -1
        self._sort_order = QtCore.Qt.AscendingOrder
        self._ranges: dict = {}
        self._rows_loaded = self._initial_page()

    # ── source management ────────────────────────────────────────────────

    @property
    def source(self) -> TableSource:
        """Return the underlying data adapter.

        Returns
        -------
        TableSource
        """
        return self._source

    @property
    def specs(self) -> list:
        """Return the column specs in table order.

        Returns
        -------
        list of ColumnSpec
        """
        return self._specs

    def spec(self, col: int) -> ColumnSpec:
        """Return one column's spec.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        ColumnSpec
        """
        return self._specs[col]

    def column_index(self, key: str) -> int:
        """Return the position of a column by key.

        Parameters
        ----------
        key : str
            :attr:`ColumnSpec.key` to look up.

        Returns
        -------
        int
            ``-1`` when no column carries that key.
        """
        for i, spec in enumerate(self._specs):
            if spec.key == key:
                return i
        return -1

    def set_source(self, source: TableSource) -> None:
        """Swap in a new data adapter and rebuild every derived view.

        Parameters
        ----------
        source : TableSource
            The new adapter.
        """
        self.beginResetModel()
        self._source = source
        self._cache.set_source(source)
        self._specs = list(source.column_specs())
        self._staged.clear()
        self._ranges.clear()
        self._recompute_visible()
        self.endResetModel()

    def refresh(self) -> None:
        """Re-read everything from the source, keeping filter and sort.

        Use after the source's contents changed underneath the model.
        """
        self.beginResetModel()
        self._cache.invalidate()
        self._ranges.clear()
        self._specs = list(self._source.column_specs())
        self._recompute_visible()
        self.endResetModel()

    # ── shape ────────────────────────────────────────────────────────────

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802, D102 (Qt override)
        if parent.isValid():
            return 0
        return int(min(len(self._visible), self._rows_loaded))

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802, D102 (Qt override)
        return 0 if parent.isValid() else len(self._specs)

    def total_row_count(self) -> int:
        """Return the number of rows passing the filter, ignoring paging.

        Returns
        -------
        int
        """
        return int(len(self._visible))

    def source_row_count(self) -> int:
        """Return the unfiltered row count of the source.

        Returns
        -------
        int
        """
        return int(self._source.row_count())

    def source_row(self, view_row: int) -> int:
        """Map a view row index back to its source row index.

        Parameters
        ----------
        view_row : int
            Row as seen through the current filter and sort.

        Returns
        -------
        int
            Source row index, or ``-1`` when out of range.
        """
        if 0 <= view_row < len(self._visible):
            return int(self._visible[view_row])
        return -1

    def view_row(self, source_row: int) -> int:
        """Map a source row index to its position in the view.

        Parameters
        ----------
        source_row : int
            Row index in the source.

        Returns
        -------
        int
            View row index, or ``-1`` when the row is filtered out.
        """
        hits = np.flatnonzero(self._visible == int(source_row))
        return int(hits[0]) if hits.size else -1

    # ── paging ───────────────────────────────────────────────────────────

    def _initial_page(self) -> int:
        """Return how many rows to expose before the first fetch.

        Returns
        -------
        int
        """
        n = len(self._visible)
        return n if n <= LARGE_ROWS else ROWS_TO_LOAD

    def can_fetch_more(self) -> bool:
        """Return whether more filtered rows are waiting to be exposed.

        Returns
        -------
        bool
        """
        return self._rows_loaded < len(self._visible)

    def fetch_more(self) -> bool:
        """Expose the next page of rows.

        Returns
        -------
        bool
            ``True`` when rows were added.
        """
        if not self.can_fetch_more():
            return False
        start = self._rows_loaded
        stop = int(min(len(self._visible), start + ROWS_TO_LOAD))
        self.beginInsertRows(QtCore.QModelIndex(), start, stop - 1)
        self._rows_loaded = stop
        self.endInsertRows()
        return True

    def fetch_all(self) -> None:
        """Expose every filtered row at once.

        Used by copy/export, which must not be silently truncated by paging.
        """
        while self.fetch_more():
            pass

    # ── filtering and sorting ────────────────────────────────────────────

    @property
    def filter_spec(self) -> FilterSpec:
        """Return the active filter.

        Returns
        -------
        FilterSpec
        """
        return self._filter

    def set_filter(self, spec: FilterSpec | None) -> None:
        """Apply a filter and recompute the visible rows.

        Parameters
        ----------
        spec : FilterSpec or None
            The filter; ``None`` clears it.
        """
        self.beginResetModel()
        self._filter = spec or FilterSpec()
        self._recompute_visible()
        self.endResetModel()

    def _search_columns(self) -> list:
        """Return the columns the global search string looks at.

        Returns
        -------
        list of int
        """
        return [i for i, spec in enumerate(self._specs) if spec.visible]

    def _recompute_visible(self) -> None:
        """Rebuild the visible-row index array from filter and sort state."""
        n = self._source.row_count()
        if self._filter.is_empty:
            self._visible = np.arange(n, dtype=np.int64)
        else:
            mask = self._filter.mask(self._cache, n, self._search_columns())
            self._visible = np.flatnonzero(mask).astype(np.int64)
        if self._sort_column >= 0:
            self._apply_sort()
        self._rows_loaded = self._initial_page()

    def _apply_sort(self) -> None:
        """Reorder the visible-row array by the active sort column."""
        col = self._sort_column
        if col < 0 or col >= len(self._specs) or self._visible.size == 0:
            return
        spec = self._specs[col]
        keys = self._cache.numeric(col) if spec.is_numeric else None
        if keys is None:
            keys = self._cache.lower(col)
        if keys is None:
            return
        try:
            subset = np.asarray(keys, dtype=object)[self._visible]
            order = np.argsort(subset, kind="stable")
        except (TypeError, ValueError):
            return
        if self._sort_order == QtCore.Qt.DescendingOrder:
            order = order[::-1]
        self._visible = self._visible[order]

    def sort(self, column: int, order=QtCore.Qt.AscendingOrder) -> None:  # noqa: D102 (Qt override)
        if column < 0 or column >= len(self._specs):
            return
        self.beginResetModel()
        self._sort_column = int(column)
        self._sort_order = order
        self._recompute_visible()
        self.endResetModel()

    def clear_sort(self) -> None:
        """Drop the sort order and return to source row order."""
        self.beginResetModel()
        self._sort_column = -1
        self._recompute_visible()
        self.endResetModel()

    @property
    def sort_column(self) -> int:
        """Return the sorted column index, or ``-1``.

        Returns
        -------
        int
        """
        return self._sort_column

    # ── column analysis ──────────────────────────────────────────────────

    def column_range(self, col: int) -> tuple | None:
        """Return the ``(min, max)`` of a numeric column, memoised.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        tuple of float or None
            ``None`` for columns with no finite numeric content.
        """
        if col in self._ranges:
            return self._ranges[col]
        arr = self._cache.numeric(col)
        out = None
        if arr is not None and arr.size:
            finite = arr[np.isfinite(arr)]
            if finite.size:
                out = (float(np.min(finite)), float(np.max(finite)))
        self._ranges[col] = out
        return out

    def global_range(self) -> tuple | None:
        """Return the ``(min, max)`` across every colourable numeric column.

        Returns
        -------
        tuple of float or None
        """
        lows, highs = [], []
        for i, spec in enumerate(self._specs):
            if not (spec.is_numeric and spec.colorize):
                continue
            rng = self.column_range(i)
            if rng is not None:
                lows.append(rng[0])
                highs.append(rng[1])
        if not lows:
            return None
        return (min(lows), max(highs))

    def empty_columns(self) -> list:
        """Return the indices of columns whose every value is blank.

        Blank means ``None``, ``NaN``/``NaT`` or the empty string; ``0`` and
        ``False`` are values, not blanks.

        Returns
        -------
        list of int
        """
        out = []
        n = self._source.row_count()
        for col in range(len(self._specs)):
            if n == 0:
                out.append(col)
                continue
            arr = self._cache.raw(col)
            if arr is None:
                if all(is_blank(self._source.value(r, col)) for r in range(n)):
                    out.append(col)
                continue
            if arr.dtype.kind in "fc":
                if not np.any(np.isfinite(np.asarray(arr, dtype="float64"))):
                    out.append(col)
                continue
            if all(is_blank(v) for v in arr):
                out.append(col)
        return out

    # ── colour scheme ────────────────────────────────────────────────────

    @property
    def color_scheme(self) -> ValueColorScheme:
        """Return the background-colouring policy.

        Returns
        -------
        ValueColorScheme
        """
        return self._color

    def set_color_scheme(self, scheme: ValueColorScheme) -> None:
        """Replace the colouring policy and repaint.

        Parameters
        ----------
        scheme : ValueColorScheme
            The new policy.
        """
        self._color = scheme
        self._emit_all_changed()

    def color_affordable(self) -> bool:
        """Return whether this table is small enough to colour.

        Returns
        -------
        bool
        """
        return self._color.affordable(self._source.row_count(), len(self._specs))

    def _background(self, source_row: int, col: int) -> QtGui.QColor | None:
        """Return the background colour for one cell, if colouring applies.

        Parameters
        ----------
        source_row : int
            Source row index.
        col : int
            Column index.

        Returns
        -------
        qtpy.QtGui.QColor or None
        """
        if not self._color.enabled or not self.color_affordable():
            return None
        spec = self._specs[col]
        if not (spec.colorize and spec.is_numeric):
            return None
        rng = self.global_range() if self._color.scope == "global" else self.column_range(col)
        if rng is None:
            return None
        return self._color.color(self._raw_value(source_row, col), rng[0], rng[1])

    # ── values ───────────────────────────────────────────────────────────

    def _raw_value(self, source_row: int, col: int) -> Any:
        """Return a cell's value, honouring any staged edit.

        Parameters
        ----------
        source_row : int
            Source row index.
        col : int
            Column index.

        Returns
        -------
        object
        """
        if self._staged_mode:
            staged = self._staged.get((source_row, col), _MISSING)
            if staged is not _MISSING:
                return staged
        return self._source.value(source_row, col)

    def _display(self, value: Any, spec: ColumnSpec) -> str:
        """Format a raw value for the display role.

        Parameters
        ----------
        value : object
            Raw cell value.
        spec : ColumnSpec
            The column's spec.

        Returns
        -------
        str
        """
        # Missing values render as an empty cell whatever flavour they are:
        # ``None``, ``NaN``, ``NaT`` or ``pandas.NA`` (which would otherwise
        # reach ``str()`` and print the literal "<NA>", and makes ``bool()``
        # raise outright).
        if is_na(value):
            return ""
        if spec.kind == KIND_BOOL:
            return str(bool(value))
        if spec.kind == KIND_STR:
            return str(value)
        fmt = spec.resolved_format(self._default_format)
        if not fmt:
            return str(value)
        try:
            fv = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not np.isfinite(fv):
            return "" if np.isnan(fv) else str(fv)
        try:
            return fmt % fv
        except (TypeError, ValueError):
            return DEFAULT_FORMAT % fv

    def data(self, index, role=QtCore.Qt.DisplayRole):  # noqa: D102 (Qt override)
        if not index.isValid():
            return None
        row = self.source_row(index.row())
        col = index.column()
        if row < 0 or col < 0 or col >= len(self._specs):
            return None
        spec = self._specs[col]

        if role == QtCore.Qt.DisplayRole:
            return self._display(self._raw_value(row, col), spec)
        if role == QtCore.Qt.EditRole:
            value = self._raw_value(row, col)
            if spec.kind == KIND_BOOL:
                return bool(value)
            if spec.is_numeric:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return ""
            return "" if value is None else str(value)
        if role in (self.RawRole, self.ValueRole):
            return self._raw_value(row, col)
        if role == QtCore.Qt.TextAlignmentRole:
            return int(self._alignment(spec))
        if role == QtCore.Qt.BackgroundRole:
            return self._background(row, col)
        if role == QtCore.Qt.ForegroundRole:
            value = self._raw_value(row, col)
            if spec.is_numeric and is_blank(value):
                return QtGui.QColor("#999999")
            return None
        if role == QtCore.Qt.ToolTipRole:
            per_cell = self._source.tooltip(row, col)
            if per_cell:
                return per_cell
            value = self._raw_value(row, col)
            if spec.is_numeric and is_blank(value):
                return "NaN"
            return spec.tooltip or None
        return None

    @staticmethod
    def _alignment(spec: ColumnSpec) -> int:
        """Return the Qt alignment flags for a column.

        Parameters
        ----------
        spec : ColumnSpec
            The column's spec.

        Returns
        -------
        int
        """
        if spec.align == "left":
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        if spec.align == "right":
            return QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        if spec.align == "center":
            return QtCore.Qt.AlignCenter
        if spec.kind == KIND_BOOL:
            return QtCore.Qt.AlignCenter
        if spec.is_numeric:
            return QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802, D102
        if orientation == QtCore.Qt.Horizontal:
            if section < 0 or section >= len(self._specs):
                return None
            spec = self._specs[section]
            if role == QtCore.Qt.DisplayRole:
                cf = self._filter.filter_for(section)
                return f"{spec.title} ⧩" if cf is not None else spec.title
            if role == QtCore.Qt.ToolTipRole:
                cf = self._filter.filter_for(section)
                base = spec.tooltip or spec.title
                return f"{base}\nFilter: {cf.describe()}" if cf is not None else (base or None)
            return None
        if role == QtCore.Qt.DisplayRole:
            row = self.source_row(section)
            return self._source.row_label(row) if row >= 0 else None
        return None

    # ── editing ──────────────────────────────────────────────────────────

    def flags(self, index):  # noqa: D102 (Qt override)
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        base = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        row = self.source_row(index.row())
        col = index.column()
        if row >= 0 and 0 <= col < len(self._specs):
            try:
                if self._source.is_editable(row, col):
                    base |= QtCore.Qt.ItemIsEditable
            except Exception:
                pass
        return base

    def setData(self, index, value, role=QtCore.Qt.EditRole) -> bool:  # noqa: N802, D102
        if role != QtCore.Qt.EditRole or not index.isValid():
            return False
        row = self.source_row(index.row())
        col = index.column()
        if row < 0 or col < 0 or col >= len(self._specs):
            return False
        spec = self._specs[col]
        if not self._source.is_editable(row, col):
            return False
        try:
            coerced = coerce_value(value, spec.kind)
        except (TypeError, ValueError):
            return False

        if self._staged_mode:
            self._staged[(row, col)] = coerced
        elif not self._source.set_value(row, col, coerced):
            return False

        self._cache.invalidate(col)
        self._ranges.pop(col, None)
        self.dataChanged.emit(index, index)
        return True

    # ── staged edits ─────────────────────────────────────────────────────

    @property
    def is_staged(self) -> bool:
        """Return whether edits are buffered rather than written through.

        Returns
        -------
        bool
        """
        return self._staged_mode

    @property
    def has_staged_edits(self) -> bool:
        """Return whether any buffered edit is pending.

        Returns
        -------
        bool
        """
        return bool(self._staged)

    def commit(self) -> int:
        """Write every buffered edit to the source.

        Returns
        -------
        int
            The number of cells written.
        """
        written = 0
        for (row, col), value in self._staged.items():
            if self._source.set_value(row, col, value):
                written += 1
        self._staged.clear()
        self._cache.invalidate()
        self._ranges.clear()
        self._emit_all_changed()
        return written

    def rollback(self) -> None:
        """Discard every buffered edit."""
        if not self._staged:
            return
        self._staged.clear()
        self._cache.invalidate()
        self._ranges.clear()
        self._emit_all_changed()

    def _emit_all_changed(self) -> None:
        """Signal that every visible cell may have changed."""
        rows = self.rowCount()
        cols = self.columnCount()
        if rows and cols:
            self.dataChanged.emit(self.index(0, 0), self.index(rows - 1, cols - 1))

    # ── formatting ───────────────────────────────────────────────────────

    def set_default_format(self, fmt: str) -> bool:
        """Change the table-wide float format.

        Parameters
        ----------
        fmt : str
            Printf-style format, validated before use.

        Returns
        -------
        bool
            ``False`` when ``fmt`` is not a usable format, leaving the old one.
        """
        if not is_valid_format(fmt):
            return False
        self._default_format = fmt
        self._emit_all_changed()
        return True

    def set_column_visible(self, col: int, visible: bool) -> None:
        """Record a column's visibility on its spec.

        The view does the actual hiding; the model tracks it because the global
        search only looks at visible columns.

        Parameters
        ----------
        col : int
            Column index.
        visible : bool
            Whether the column is shown.
        """
        if 0 <= col < len(self._specs):
            self._specs[col] = self._specs[col].with_(visible=bool(visible))

    def visible_columns(self) -> list:
        """Return the indices of columns currently marked visible.

        Returns
        -------
        list of int
        """
        return [i for i, spec in enumerate(self._specs) if spec.visible]

    def to_store(self, *, only_visible: bool = True):
        """Export the current view (filter, sort, visibility) as a store.

        Parameters
        ----------
        only_visible : bool
            Restrict to columns marked visible.

        Returns
        -------
        tttrlib.DataStore
        """
        from chisurf.core.datastore import store_from_arrays

        cols = self.visible_columns() if only_visible else list(range(len(self._specs)))
        data = {}
        for col in cols:
            key = self._specs[col].title
            data[key] = [self._raw_value(int(r), col) for r in self._visible]
        return store_from_arrays(data)

    def rows_as_text(
        self,
        rows: Sequence[int],
        cols: Sequence[int],
        *,
        include_header: bool = False,
        include_row_labels: bool = False,
    ) -> str:
        """Render a rectangular selection as tab-separated text.

        Parameters
        ----------
        rows : sequence of int
            View row indices.
        cols : sequence of int
            Column indices.
        include_header : bool
            Prepend the column titles.
        include_row_labels : bool
            Prepend each row's vertical-header label.

        Returns
        -------
        str
        """
        lines = []
        if include_header:
            head = ([""] if include_row_labels else []) + [self._specs[c].title for c in cols]
            lines.append("\t".join(head))
        for view_row in rows:
            src = self.source_row(int(view_row))
            if src < 0:
                continue
            cells = [self._source.row_label(src)] if include_row_labels else []
            for col in cols:
                cells.append(self._display(self._raw_value(src, col), self._specs[col]))
            lines.append("\t".join(cells))
        return "\n".join(lines)


class _Missing:
    """Sentinel type distinguishing "no staged edit" from a staged ``None``."""


_MISSING = _Missing()
