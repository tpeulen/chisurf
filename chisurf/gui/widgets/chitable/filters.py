"""Vectorised value filtering for :mod:`chisurf.gui.widgets.chitable`.

Filtering is expressed as a :class:`FilterSpec` — an optional global search
string plus any number of per-column :class:`ColumnFilter` predicates — and
evaluated into a boolean row mask with one numpy pass per column.

That is deliberate. A :class:`~qtpy.QtCore.QSortFilterProxyModel` calls
``filterAcceptsRow`` once per row in Python; on a 10^6-row burst frame that is
seconds per keystroke. Building the mask from
:meth:`~chisurf.gui.widgets.chitable.source.TableSource.column_array` and letting
the model carry a visible-row index array keeps the same work in milliseconds.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chisurf.gui.widgets.chitable.source import TableSource, is_na

#: Predicates understood by :class:`ColumnFilter`.
TEXT_OPS = ("contains", "not_contains", "equals", "not_equals", "startswith", "endswith", "regex")
NUMERIC_OPS = ("gt", "ge", "lt", "le", "between", "outside")
NULL_OPS = ("isnull", "notnull")
ALL_OPS = TEXT_OPS + NUMERIC_OPS + NULL_OPS


def _stringify(arr: np.ndarray) -> np.ndarray:
    """Every value as ``str()`` would render it, vectorised.

    Parameters
    ----------
    arr : numpy.ndarray

    Returns
    -------
    numpy.ndarray
        Fixed-width unicode array, so :mod:`numpy.char` can vectorise the text
        predicates below.

    Notes
    -----
    ``astype(str)`` raises on an **object** column holding sequences -- a colour
    stored as ``[0.0, 0.0, 0.0, 1.0]``, which is an ordinary cell in a settings
    table. numpy tries to broadcast the list into the output element rather than
    formatting it, and the message ("setting an array element with a sequence")
    names neither the column nor the row. So typing a single character into the
    search box raised, and the table's filter was unusable on any table with a
    vector column.
    """
    try:
        return arr.astype(str)
    except (ValueError, TypeError):
        # Element-wise, which is what `str()` on each cell means. Only reached
        # for object columns, where the vectorised path was never doing
        # anything cheaper.
        flat = [str(value) for value in arr.ravel().tolist()]
        return np.array(flat, dtype=str).reshape(arr.shape)


#: Human-readable labels for the filter popup.
OP_LABELS = {
    "contains": "contains",
    "not_contains": "does not contain",
    "equals": "equals",
    "not_equals": "does not equal",
    "startswith": "starts with",
    "endswith": "ends with",
    "regex": "matches regex",
    "gt": ">",
    "ge": "≥",
    "lt": "<",
    "le": "≤",
    "between": "between",
    "outside": "outside",
    "isnull": "is empty",
    "notnull": "is not empty",
}


class ColumnCache:
    """Lazily-built, invalidatable per-column views of a source.

    Holds the numeric and lowercased-text projections of each column so a filter
    or sort touches the underlying source at most once per column.

    Parameters
    ----------
    source : TableSource
        The source to project.
    """

    def __init__(self, source: TableSource) -> None:
        self._source = source
        self._raw: dict = {}
        self._numeric: dict = {}
        self._lower: dict = {}

    def set_source(self, source: TableSource) -> None:
        """Point the cache at a new source and drop everything cached.

        Parameters
        ----------
        source : TableSource
            The new source.
        """
        self._source = source
        self.invalidate()

    def invalidate(self, col: int | None = None) -> None:
        """Drop cached projections.

        Parameters
        ----------
        col : int, optional
            Column to invalidate. ``None`` clears every column.
        """
        if col is None:
            self._raw.clear()
            self._numeric.clear()
            self._lower.clear()
            return
        self._raw.pop(col, None)
        self._numeric.pop(col, None)
        self._lower.pop(col, None)

    def raw(self, col: int) -> np.ndarray | None:
        """Return the column as the source provides it.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        numpy.ndarray or None
        """
        if col not in self._raw:
            self._raw[col] = self._source.column_array(col)
        return self._raw[col]

    def numeric(self, col: int) -> np.ndarray | None:
        """Return the column as ``float64`` with ``NaN`` for non-numbers.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        numpy.ndarray or None
            ``None`` when the column cannot be read at all.
        """
        if col in self._numeric:
            return self._numeric[col]
        arr = self.raw(col)
        if arr is None:
            self._numeric[col] = None
            return None
        if arr.dtype.kind in "fiu":
            out = arr.astype("float64", copy=False)
        elif arr.dtype.kind == "b":
            out = arr.astype("float64")
        else:
            try:
                # The common case -- every entry already parses -- at C speed.
                out = arr.astype("float64")
            except (TypeError, ValueError):
                # A genuinely mixed column: coerce what parses, NaN the rest.
                out = np.full(arr.shape, np.nan, dtype="float64")
                for i, v in enumerate(arr):
                    try:
                        out[i] = float(v)
                    except (TypeError, ValueError):
                        pass
        self._numeric[col] = out
        return out

    def lower(self, col: int) -> np.ndarray | None:
        """Return the column rendered as lowercase strings.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        numpy.ndarray or None
        """
        if col in self._lower:
            return self._lower[col]
        arr = self.raw(col)
        if arr is None:
            self._lower[col] = None
            return None
        out = np.char.lower(_stringify(arr))
        self._lower[col] = out
        return out


@dataclass(frozen=True)
class ColumnFilter:
    """One predicate applied to one column.

    Parameters
    ----------
    column : int
        Column index the predicate applies to.
    op : str
        A member of :data:`ALL_OPS`.
    value : object
        Right-hand operand (text pattern or number).
    value2 : object
        Second operand for ``"between"`` / ``"outside"``.
    case_sensitive : bool
        Whether text comparisons respect case.
    """

    column: int
    op: str = "contains"
    value: Any = None
    value2: Any = None
    case_sensitive: bool = False

    def describe(self) -> str:
        """Return a short human-readable form for tooltips.

        Returns
        -------
        str
        """
        label = OP_LABELS.get(self.op, self.op)
        if self.op in NULL_OPS:
            return label
        if self.op in ("between", "outside"):
            return f"{label} {self.value} and {self.value2}"
        return f"{label} {self.value}"

    def mask(self, cache: ColumnCache, n_rows: int) -> np.ndarray:
        """Evaluate this predicate into a boolean row mask.

        Parameters
        ----------
        cache : ColumnCache
            Column projections for the source being filtered.
        n_rows : int
            Total number of source rows.

        Returns
        -------
        numpy.ndarray
            Boolean array of length ``n_rows``. Unusable predicates accept
            every row rather than hiding the whole table.
        """
        keep = np.ones(n_rows, dtype=bool)

        if self.op in NULL_OPS:
            raw = cache.raw(self.column)
            if raw is None:
                return keep
            null = np.array([is_na(v) for v in raw], dtype=bool)
            empty = np.char.strip(_stringify(raw)) == ""
            blank = null | empty
            return blank if self.op == "isnull" else ~blank

        if self.op in NUMERIC_OPS:
            arr = cache.numeric(self.column)
            if arr is None:
                return keep
            try:
                lo = float(self.value)
            except (TypeError, ValueError):
                return keep
            with np.errstate(invalid="ignore"):
                if self.op == "gt":
                    return arr > lo
                if self.op == "ge":
                    return arr >= lo
                if self.op == "lt":
                    return arr < lo
                if self.op == "le":
                    return arr <= lo
                try:
                    hi = float(self.value2)
                except (TypeError, ValueError):
                    return keep
                if lo > hi:
                    lo, hi = hi, lo
                inside = (arr >= lo) & (arr <= hi)
                return inside if self.op == "between" else ~inside

        pattern = "" if self.value is None else str(self.value)
        if pattern == "" and self.op != "equals":
            return keep
        if self.case_sensitive:
            raw = cache.raw(self.column)
            if raw is None:
                return keep
            arr = _stringify(raw)
        else:
            lowered = cache.lower(self.column)
            if lowered is None:
                return keep
            arr = lowered
            pattern = pattern.lower()

        try:
            if self.op == "contains":
                return np.char.find(arr, pattern) >= 0
            if self.op == "not_contains":
                return np.char.find(arr, pattern) < 0
            if self.op == "equals":
                return arr == pattern
            if self.op == "not_equals":
                return arr != pattern
            if self.op == "startswith":
                return np.char.startswith(arr, pattern)
            if self.op == "endswith":
                return np.char.endswith(arr, pattern)
            if self.op == "regex":
                compiled = re.compile(pattern)
                return np.array([bool(compiled.search(s)) for s in arr], dtype=bool)
        except (re.error, ValueError, TypeError):
            return keep
        return keep


@dataclass(frozen=True)
class FilterSpec:
    """A global search string plus a set of per-column predicates.

    Parameters
    ----------
    query : str
        Case-insensitive substring matched against every searched column; a row
        is kept when *any* of them matches.
    columns : tuple of ColumnFilter
        Per-column predicates, combined with logical AND.
    """

    query: str = ""
    columns: tuple = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        """Return whether this spec would accept every row.

        Returns
        -------
        bool
        """
        return not self.query.strip() and not self.columns

    def filter_for(self, column: int) -> ColumnFilter | None:
        """Return the predicate on ``column``, if any.

        Parameters
        ----------
        column : int
            Column index.

        Returns
        -------
        ColumnFilter or None
        """
        for cf in self.columns:
            if cf.column == column:
                return cf
        return None

    def with_column_filter(self, cf: ColumnFilter | None, column: int) -> FilterSpec:
        """Return a copy with ``column``'s predicate replaced or removed.

        Parameters
        ----------
        cf : ColumnFilter or None
            The new predicate, or ``None`` to clear the column.
        column : int
            Column index to replace.

        Returns
        -------
        FilterSpec
        """
        kept = tuple(c for c in self.columns if c.column != column)
        if cf is not None:
            kept = kept + (cf,)
        return FilterSpec(query=self.query, columns=kept)

    def with_query(self, query: str) -> FilterSpec:
        """Return a copy with a different global search string.

        Parameters
        ----------
        query : str
            The new search text.

        Returns
        -------
        FilterSpec
        """
        return FilterSpec(query=query, columns=self.columns)

    def mask(
        self,
        cache: ColumnCache,
        n_rows: int,
        search_columns: Sequence[int],
    ) -> np.ndarray:
        """Evaluate the whole spec into a boolean row mask.

        Parameters
        ----------
        cache : ColumnCache
            Column projections for the source being filtered.
        n_rows : int
            Total number of source rows.
        search_columns : sequence of int
            Columns the global ``query`` searches — normally the visible ones.

        Returns
        -------
        numpy.ndarray
            Boolean array of length ``n_rows``.
        """
        keep = np.ones(n_rows, dtype=bool)
        if n_rows == 0:
            return keep

        text = self.query.strip().lower()
        if text:
            any_hit = np.zeros(n_rows, dtype=bool)
            for col in search_columns:
                lowered = cache.lower(col)
                if lowered is None:
                    continue
                any_hit |= np.char.find(lowered, text) >= 0
            keep &= any_hit

        for cf in self.columns:
            keep &= cf.mask(cache, n_rows)
        return keep
