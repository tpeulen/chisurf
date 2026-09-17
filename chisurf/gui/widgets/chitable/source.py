"""Table sources — the adapter layer of :mod:`chisurf.gui.widgets.chitable`.

A :class:`TableSource` is the only thing :class:`~chisurf.gui.widgets.chitable.model.ChiTableModel`
knows about. Three adapters cover every tabular shape in the tree:

``DataStoreSource``
    a ``tttrlib.DataStore`` — the [columnar store](/subsystems/columnar-store.md)
    every table in the tree is built on;
``ArraySource``
    named ``numpy`` column arrays (fit curves: x / data / model / residuals);
``RecordSource``
    a list of objects or dicts plus an explicit column spec (fitting-parameter
    rows, plugin record tables).

Every adapter exposes ``column_array``, a vectorised view used for filtering,
sorting and colour ranges — that is what keeps a 10^6-row table responsive
without a per-row Python callback.

Notes
-----
This module has no pandas dependency at all, not even an optional one. It
used to: a fourth adapter, ``DataFrameSource``, wrapped a caller-held
:class:`pandas.DataFrame` directly, and :func:`kind_from_dtype` fell through to
:func:`pandas.api.types.is_numeric_dtype` for a dtype plain ``numpy.dtype()``
could not classify (a pandas *extension* dtype such as the nullable
``Float64``/``Int64``/``boolean`` a nullable-dtype reader produces — plain
``numpy.issubdtype`` does not raise there, it is simply wrong, which was the
root cause of a long-standing crash in ndX's table editor). Both are gone: the
tree has no producer of a frame left to wrap, and :class:`DataStoreSource`
cannot reproduce that class of bug at all — a store column states its type
outright, so nothing has to be inferred from a dtype object.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from chisurf.gui.widgets.chitable.columns import (
    KIND_AUTO,
    KIND_BOOL,
    KIND_FLOAT,
    KIND_INT,
    KIND_STR,
    ColumnSpec,
)


def kind_from_dtype(dtype: Any) -> str:
    """Map a numpy dtype onto a :class:`ColumnSpec` kind.

    Classified from ``numpy.dtype.kind`` directly. Anything ``numpy.dtype()``
    does not recognise (nothing in this tree produces such a value; every
    column is a plain numpy array) is treated as text rather than raising.

    Parameters
    ----------
    dtype : object
        A numpy dtype, or anything ``numpy.dtype()`` accepts.

    Returns
    -------
    str
        One of ``"bool"``, ``"int"``, ``"float"`` or ``"str"``.
    """
    try:
        np_dtype = np.dtype(dtype)
    except TypeError:
        return KIND_STR
    kind = np_dtype.kind
    if kind == "b":
        return KIND_BOOL
    if kind in "iu":
        return KIND_INT
    if kind == "f":
        return KIND_FLOAT
    return KIND_STR


def coerce_value(raw: Any, kind: str) -> Any:
    """Convert a user-entered value to the type a column expects.

    Parameters
    ----------
    raw : object
        Value as typed by the user (usually a string) or already-typed.
    kind : str
        Target :class:`ColumnSpec` kind.

    Returns
    -------
    object
        The coerced value. Empty strings and ``"nan"`` become ``numpy.nan`` for
        numeric columns and ``""`` for text columns.

    Raises
    ------
    ValueError
        If a numeric column receives text that is not a number.
    """
    if kind == KIND_STR or kind == KIND_AUTO:
        return raw if not isinstance(raw, str) else raw
    text = str(raw).strip() if not isinstance(raw, (bool, np.bool_)) else raw

    if kind == KIND_BOOL:
        if isinstance(text, (bool, np.bool_)):
            return bool(text)
        return str(text).strip().lower() in ("1", "true", "t", "yes", "y", "on")

    if isinstance(text, str) and (text == "" or text.lower() in ("nan", "none")):
        return np.nan

    if kind == KIND_INT:
        try:
            return int(text)
        except (TypeError, ValueError):
            return int(float(text))
    return float(text)


def _is_missing_numpy(value: Any) -> bool:
    """numpy/stdlib-only missing check: ``NaN`` and ``NaT``, no pandas involved.

    Parameters
    ----------
    value : object
        Scalar cell value.

    Returns
    -------
    bool
    """
    try:
        return bool(np.isnan(value))
    except (TypeError, ValueError):
        pass
    try:
        return bool(np.isnat(value))
    except (TypeError, ValueError):
        pass
    return False


def is_na(value: Any) -> bool:
    """Return whether a scalar is a missing value.

    Covers ``None``, ``NaN`` and ``NaT``.

    Parameters
    ----------
    value : object
        Scalar cell value.

    Returns
    -------
    bool
    """
    if value is None:
        return True
    return _is_missing_numpy(value)


def is_blank(value: Any) -> bool:
    """Return whether a cell value counts as empty.

    Used by the *hide empty columns* feature: ``None``, NaN/NaT and the empty
    string are blank; ``0`` and ``False`` are not.

    Parameters
    ----------
    value : object
        Raw cell value.

    Returns
    -------
    bool
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return is_na(value)


class TableSource:
    """Base class for chitable data adapters.

    Subclasses must implement :meth:`column_specs`, :meth:`row_count`,
    :meth:`value` and — if editable — :meth:`set_value`. Everything else has a
    workable default.
    """

    def column_specs(self) -> Sequence[ColumnSpec]:
        """Return the columns in table order.

        Returns
        -------
        sequence of ColumnSpec
        """
        raise NotImplementedError

    def row_count(self) -> int:
        """Return the number of rows.

        Returns
        -------
        int
        """
        raise NotImplementedError

    def column_count(self) -> int:
        """Return the number of columns.

        Returns
        -------
        int
        """
        return len(self.column_specs())

    def value(self, row: int, col: int) -> Any:
        """Return the raw, unformatted value of a cell.

        Parameters
        ----------
        row : int
            Source row index.
        col : int
            Column index.

        Returns
        -------
        object
        """
        raise NotImplementedError

    def set_value(self, row: int, col: int, value: Any) -> bool:
        """Write a value back into the underlying data.

        Parameters
        ----------
        row : int
            Source row index.
        col : int
            Column index.
        value : object
            Already coerced to the column's kind.

        Returns
        -------
        bool
            ``True`` when the write happened.
        """
        return False

    def is_editable(self, row: int, col: int) -> bool:
        """Return whether one cell accepts edits.

        Parameters
        ----------
        row : int
            Source row index.
        col : int
            Column index.

        Returns
        -------
        bool
        """
        specs = self.column_specs()
        return bool(specs[col].editable) if 0 <= col < len(specs) else False

    def column_array(self, col: int) -> np.ndarray | None:
        """Return the whole column as an array, or ``None`` if not vectorisable.

        Returning an array is what lets filtering, sorting and colour ranges run
        as a single numpy pass instead of a per-row Python loop.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        numpy.ndarray or None
        """
        n = self.row_count()
        try:
            return np.array([self.value(r, col) for r in range(n)], dtype=object)
        except Exception:
            return None

    def row_label(self, row: int) -> str:
        """Return the vertical-header text for a row.

        Parameters
        ----------
        row : int
            Source row index.

        Returns
        -------
        str
        """
        return str(row)

    def tooltip(self, row: int, col: int) -> str | None:
        """Return a per-cell tooltip, or ``None`` to use the column default.

        Parameters
        ----------
        row : int
            Source row index.
        col : int
            Column index.

        Returns
        -------
        str or None
        """
        return None


#: Largest dictionary a text column may have before its cells stop offering a
#: combo box. Four labels is a stream name and belongs in a drop-down; ten
#: thousand is free text and a drop-down would be unusable.
MAX_CHOICE_LABELS = 64

#: ``Column.dtype`` strings that make an integer column.
_INT_DTYPES = frozenset({"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"})


def kind_from_column_dtype(dtype: str) -> str:
    """Map a ``tttrlib`` column dtype string onto a :class:`ColumnSpec` kind.

    A store column *states* its type, so unlike :func:`kind_from_dtype` this
    needs no inference and cannot raise on an unexpected dtype object.

    Parameters
    ----------
    dtype : str
        ``Column.dtype`` — one of ``"float64"``, ``"float32"``, the signed and
        unsigned integer names, ``"bool"`` or ``"str"``.

    Returns
    -------
    str
        One of ``"bool"``, ``"int"``, ``"float"`` or ``"str"``.
    """
    if dtype == "bool":
        return KIND_BOOL
    if dtype in _INT_DTYPES:
        return KIND_INT
    if dtype in ("float32", "float64"):
        return KIND_FLOAT
    return KIND_STR


class DataStoreSource(TableSource):
    """Adapter over a ``tttrlib.DataStore`` columnar table.

    The store answers this class's five obligations more directly than a frame
    does. ``column_array`` is the column's own buffer in its own dtype, where
    :class:`DataFrameSource` converts to ``float64``; ``set_value`` writes
    through that same buffer; and ``column_specs`` reads a stated column type
    instead of inferring one from a dtype object.

    Two behaviours have no ``DataFrameSource`` equivalent:

    * **Blanking a cell sets the validity mask** rather than writing ``NaN``,
      so an integer column keeps both its dtype and the difference between
      "zero" and "not measured".
    * **A text column edits as a drop-down** of its dictionary labels when the
      dictionary is small enough (:data:`MAX_CHOICE_LABELS`), because the store
      already knows the distinct values. Typing a label that is not in the
      dictionary adds it.

    Parameters
    ----------
    store : tttrlib.DataStore
        The store to expose. Held by reference; edits mutate it in place.
    editable : bool
        Make every column editable. Per-column exceptions go through
        ``readonly_columns`` or explicit ``specs``.
    specs : sequence of ColumnSpec, optional
        Explicit column specs. When given they must match the store's columns
        in length and order; anything omitted is synthesised from the types.
    readonly_columns : sequence of str
        Column names to force read-only, even when ``editable`` is set.
    colorize_columns : sequence of str, optional
        Column names opted into value colouring. ``None`` colours every numeric
        column.

    Notes
    -----
    No ``Column`` is ever cached. A column proxy is a borrowed reference into
    the store's column container and removing a column invalidates it, after
    which the stale proxy silently reads freed memory — an empty name and no
    data, with no exception. Every access re-fetches through
    :func:`chisurf.core.datastore.column_at`.
    """

    def __init__(
        self,
        store: Any,
        *,
        editable: bool = False,
        specs: Sequence[ColumnSpec] | None = None,
        readonly_columns: Sequence[str] = (),
        colorize_columns: Sequence[str] | None = None,
    ) -> None:
        self._store = store
        self._editable = bool(editable)
        self._readonly = set(readonly_columns or ())
        self._colorize = None if colorize_columns is None else set(colorize_columns)
        self._specs = tuple(specs) if specs else self._build_specs()

    # -- construction -----------------------------------------------------

    def _build_specs(self) -> tuple:
        """Derive one column spec per store column.

        Returns
        -------
        tuple of ColumnSpec
        """
        return tuple(self._spec_for(i) for i in range(int(self._store.n_columns())))

    def _spec_for(self, col: int) -> ColumnSpec:
        """Derive the spec of one column from its stated type.

        Parameters
        ----------
        col : int
            Positional column index.

        Returns
        -------
        ColumnSpec
        """
        column = self._column(col)
        name = str(column.name())
        kind = kind_from_column_dtype(column.dtype)
        numeric = kind in (KIND_FLOAT, KIND_INT)
        colorize = numeric if self._colorize is None else (name in self._colorize)
        editable = self._editable and name not in self._readonly

        delegate, choices = "", ()
        if kind == KIND_BOOL:
            delegate = "bool"
        elif kind == KIND_STR:
            labels = tuple(str(label) for label in column.dictionary())
            if editable and 0 < len(labels) <= MAX_CHOICE_LABELS:
                delegate, choices = "choice", labels
        label, tooltip = self._label_for(column, name)
        return ColumnSpec(
            key=name,
            label=label,
            kind=kind,
            editable=editable,
            colorize=colorize,
            delegate=delegate,
            choices=choices,
            tooltip=tooltip,
        )

    @staticmethod
    def _label_for(column: Any, name: str) -> tuple[str, str]:
        """Return the header text and tooltip for one column.

        A store column can state its unit and its prose (a container writes both
        -- see :meth:`chisurf.core.fio.pto.Measurement.column_units`), and the
        table used to show neither: every header was the bare column name, so a
        duration in milliseconds and a lifetime in nanoseconds looked alike and
        the convention in the *name* was the only thing left to read them by.
        That is precisely what recording the unit was meant to end.

        Parameters
        ----------
        column : tttrlib.Column
        name : str
            The column's name, already read.

        Returns
        -------
        tuple of str
            ``(header, tooltip)``. The header gains ``" [symbol]"`` when the
            column states a unit that has one, and is the bare name otherwise --
            a unit the dictionary has no symbol for is not worth an empty pair of
            brackets.
        """
        try:
            code = str(column.attribute("units") or "")
            description = str(column.attribute("description") or "")
        except Exception:  # a column type without attributes
            return name, ""
        label = name
        if code:
            from chisurf.core.support.units import symbol

            unit = symbol(code)
            if unit and f"[{unit}]" not in name:
                label = f"{name} [{unit}]"
        tooltip = description
        if code and code not in tooltip:
            tooltip = f"{tooltip}\n({code})".strip() if tooltip else f"in {code}"
        return label, tooltip

    def _column(self, col: int) -> Any:
        """Return a freshly fetched column proxy.

        Parameters
        ----------
        col : int
            Positional column index.

        Returns
        -------
        tttrlib.Column
        """
        from chisurf.core.datastore import column_at

        return column_at(self._store, col)

    # -- TableSource ------------------------------------------------------

    @property
    def store(self) -> Any:
        """Return the wrapped store.

        Returns
        -------
        tttrlib.DataStore
        """
        return self._store

    def set_store(self, store: Any) -> None:
        """Replace the wrapped store and rebuild the column specs.

        Parameters
        ----------
        store : tttrlib.DataStore
            The new store.
        """
        self._store = store
        self._specs = self._build_specs()

    def column_specs(self) -> Sequence[ColumnSpec]:
        """Return the derived or supplied column specs.

        Returns
        -------
        sequence of ColumnSpec
        """
        return self._specs

    def row_count(self) -> int:
        """Return the number of rows.

        Returns
        -------
        int
            The store's declared row count, falling back to the longest column
            for a store assembled without one.
        """
        rows = int(self._store.n_rows())
        if rows:
            return rows
        return max(
            (int(self._column(i).size()) for i in range(int(self._store.n_columns()))),
            default=0,
        )

    def value(self, row: int, col: int) -> Any:
        """Return one cell, or a missing marker when the mask says so.

        Parameters
        ----------
        row : int
            Positional row index.
        col : int
            Positional column index.

        Returns
        -------
        object
            ``numpy.nan`` for a masked float cell, ``None`` for any other masked
            cell or an out-of-range position, and otherwise the value in the
            column's own dtype.
        """
        try:
            column = self._column(col)
        except Exception:
            return None
        if not 0 <= row < int(column.size()):
            return None
        if column.has_mask() and not column.valid(row):
            return np.nan if column.dtype in ("float32", "float64") else None
        dtype = column.dtype
        if dtype == "str":
            return column.string_at(row)
        if dtype == "bool":
            return bool(column.value_at(row))
        try:
            return column.numpy()[row]
        except Exception:
            return None

    def set_value(self, row: int, col: int, value: Any) -> bool:
        """Write one cell through the store.

        A blank or ``NaN`` value clears the cell's validity bit instead of
        writing a sentinel; a new text label is appended to the column's
        dictionary and the column's spec picks it up.

        Parameters
        ----------
        row : int
            Positional row index.
        col : int
            Positional column index.
        value : object
            Already coerced to the column's kind.

        Returns
        -------
        bool
        """
        from chisurf.core.datastore import set_cell

        try:
            was_choice = self._specs[col].choices
            if not set_cell(self._store, row, col, value):
                return False
        except Exception:
            return False
        if was_choice and str(value) not in was_choice:
            specs = list(self._specs)
            specs[col] = self._spec_for(col)
            self._specs = tuple(specs)
        return True

    def column_array(self, col: int) -> np.ndarray | None:
        """Return a column as an array, honouring its validity mask.

        An unmasked numeric column comes back as the store's own buffer, in its
        own dtype and without a copy — that is what keeps filtering and colour
        ranges over a million rows cheap. A masked column is widened to
        ``float64`` with ``NaN`` at the masked positions, so downstream numpy
        comparisons see the missing values.

        Parameters
        ----------
        col : int
            Positional column index.

        Returns
        -------
        numpy.ndarray or None
        """
        from chisurf.core.datastore import column_values

        try:
            return column_values(self._store, col)
        except Exception:
            return None


class ArraySource(TableSource):
    """Adapter over named ``numpy`` column arrays.

    Columns may differ in length; short columns read as ``NaN`` past their end,
    which is what fit curves need when the model is shorter than the data.

    Parameters
    ----------
    columns : mapping or sequence of (str, numpy.ndarray)
        Column name to array. Order is preserved.
    specs : sequence of ColumnSpec, optional
        Explicit specs; synthesised from the arrays when omitted.
    on_set : callable, optional
        ``on_set(key, row, value) -> bool`` invoked after a cell is written, so
        the owner can push the change onward (e.g. re-run a fit).
    editable_keys : sequence of str
        Column keys that accept edits when ``specs`` is not given.
    """

    def __init__(
        self,
        columns: Any,
        *,
        specs: Sequence[ColumnSpec] | None = None,
        on_set: Callable[[str, int, Any], bool] | None = None,
        editable_keys: Sequence[str] = (),
    ) -> None:
        if isinstance(columns, Mapping):
            items = list(columns.items())
        else:
            items = [(str(k), v) for k, v in columns]
        self._keys = [str(k) for k, _ in items]
        self._arrays = [np.asarray(v) for _, v in items]
        self._on_set = on_set
        self._editable = set(editable_keys or ())
        self._specs = tuple(specs) if specs else self._build_specs()

    def _build_specs(self) -> tuple:
        """Derive one float column spec per array.

        Returns
        -------
        tuple of ColumnSpec
        """
        return tuple(
            ColumnSpec(
                key=key,
                label=key,
                kind=kind_from_dtype(arr.dtype),
                editable=key in self._editable,
                colorize=True,
            )
            for key, arr in zip(self._keys, self._arrays)
        )

    def set_columns(self, columns: Any, *, specs: Sequence[ColumnSpec] | None = None) -> None:
        """Replace every column array.

        Parameters
        ----------
        columns : mapping or sequence of (str, numpy.ndarray)
            The new columns.
        specs : sequence of ColumnSpec, optional
            Replacement specs; re-derived when omitted.
        """
        if isinstance(columns, Mapping):
            items = list(columns.items())
        else:
            items = [(str(k), v) for k, v in columns]
        self._keys = [str(k) for k, _ in items]
        self._arrays = [np.asarray(v) for _, v in items]
        self._specs = tuple(specs) if specs else self._build_specs()

    def column_specs(self) -> Sequence[ColumnSpec]:
        """Return the column specs.

        Returns
        -------
        sequence of ColumnSpec
        """
        return self._specs

    def row_count(self) -> int:
        """Return the length of the longest column.

        Returns
        -------
        int
        """
        return max((int(a.size) for a in self._arrays), default=0)

    def value(self, row: int, col: int) -> Any:
        """Return one array element, or ``NaN`` past the column's end.

        Parameters
        ----------
        row : int
            Row index.
        col : int
            Column index.

        Returns
        -------
        object
        """
        try:
            arr = self._arrays[col]
        except IndexError:
            return None
        if row < 0 or row >= arr.size:
            return np.nan
        return arr[row]

    def set_value(self, row: int, col: int, value: Any) -> bool:
        """Write one array element and notify ``on_set``.

        Parameters
        ----------
        row : int
            Row index.
        col : int
            Column index.
        value : object
            Already-coerced value.

        Returns
        -------
        bool
        """
        try:
            arr = self._arrays[col]
            if row < 0 or row >= arr.size:
                return False
            arr[row] = value
        except Exception:
            return False
        if self._on_set is not None:
            try:
                self._on_set(self._keys[col], row, value)
            except Exception:
                return True
        return True

    def column_array(self, col: int) -> np.ndarray | None:
        """Return a column, padded with ``NaN`` to the table's row count.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        numpy.ndarray or None
        """
        try:
            arr = self._arrays[col]
        except IndexError:
            return None
        n = self.row_count()
        if arr.size == n:
            return arr
        out = np.full(n, np.nan, dtype="float64")
        try:
            out[: arr.size] = arr.astype("float64", copy=False)
        except (TypeError, ValueError):
            return arr
        return out


class RecordSource(TableSource):
    """Adapter over a sequence of row objects or dicts plus explicit specs.

    This is the shape used by parameter tables: each row is a domain object and
    each column is an attribute read through ``getter`` and written through
    ``setter``.

    Parameters
    ----------
    rows : sequence
        Row objects (any type) or dicts.
    specs : sequence of ColumnSpec
        Column definitions; ``ColumnSpec.key`` is passed to the accessors.
    getter : callable, optional
        ``getter(row_obj, key) -> value``. Defaults to attribute access with a
        mapping fallback.
    setter : callable, optional
        ``setter(row_obj, key, value) -> bool``. Defaults to attribute
        assignment with a mapping fallback. This is the injection point for an
        RPC mutator.
    editable_check : callable, optional
        ``editable_check(row_obj, key) -> bool``, consulted in addition to the
        spec's ``editable`` flag.
    row_labeller : callable, optional
        ``row_labeller(row_obj, index) -> str`` for the vertical header.
    """

    def __init__(
        self,
        rows: Sequence[Any],
        specs: Sequence[ColumnSpec],
        *,
        getter: Callable[[Any, str], Any] | None = None,
        setter: Callable[[Any, str, Any], bool] | None = None,
        editable_check: Callable[[Any, str], bool] | None = None,
        row_labeller: Callable[[Any, int], str] | None = None,
    ) -> None:
        self._rows = list(rows)
        self._specs = tuple(specs)
        self._getter = getter or _default_getter
        self._setter = setter or _default_setter
        self._editable_check = editable_check
        self._row_labeller = row_labeller

    @property
    def rows(self) -> list:
        """Return the row objects.

        Returns
        -------
        list
        """
        return self._rows

    def set_rows(self, rows: Sequence[Any]) -> None:
        """Replace the row objects.

        Parameters
        ----------
        rows : sequence
            The new rows.
        """
        self._rows = list(rows)

    def column_specs(self) -> Sequence[ColumnSpec]:
        """Return the supplied column specs.

        Returns
        -------
        sequence of ColumnSpec
        """
        return self._specs

    def row_count(self) -> int:
        """Return the number of records.

        Returns
        -------
        int
        """
        return len(self._rows)

    def value(self, row: int, col: int) -> Any:
        """Read one field of one record.

        Parameters
        ----------
        row : int
            Record index.
        col : int
            Column index.

        Returns
        -------
        object
        """
        try:
            return self._getter(self._rows[row], self._specs[col].key)
        except Exception:
            return None

    def set_value(self, row: int, col: int, value: Any) -> bool:
        """Write one field of one record through the setter.

        Parameters
        ----------
        row : int
            Record index.
        col : int
            Column index.
        value : object
            Already-coerced value.

        Returns
        -------
        bool
        """
        try:
            return bool(self._setter(self._rows[row], self._specs[col].key, value))
        except Exception:
            return False

    def is_editable(self, row: int, col: int) -> bool:
        """Return whether a record field accepts edits.

        Parameters
        ----------
        row : int
            Record index.
        col : int
            Column index.

        Returns
        -------
        bool
        """
        spec = self._specs[col]
        if not spec.editable:
            return False
        if self._editable_check is None:
            return True
        try:
            return bool(self._editable_check(self._rows[row], spec.key))
        except Exception:
            return False

    def column_array(self, col: int) -> np.ndarray | None:
        """Return one field across every record as an array.

        Numeric columns come back as ``float64`` so filters and colour ranges
        stay vectorised.

        Parameters
        ----------
        col : int
            Column index.

        Returns
        -------
        numpy.ndarray or None
        """
        spec = self._specs[col]
        values = [self.value(r, col) for r in range(len(self._rows))]
        if spec.is_numeric:
            out = np.full(len(values), np.nan, dtype="float64")
            for i, v in enumerate(values):
                try:
                    out[i] = float(v)
                except (TypeError, ValueError):
                    pass
            return out
        return np.array(values, dtype=object)

    def row_label(self, row: int) -> str:
        """Return the vertical-header text for a record.

        Parameters
        ----------
        row : int
            Record index.

        Returns
        -------
        str
        """
        if self._row_labeller is not None:
            try:
                return str(self._row_labeller(self._rows[row], row))
            except Exception:
                pass
        return str(row + 1)


def _default_getter(obj: Any, key: str) -> Any:
    """Read ``key`` from an object, falling back to mapping access.

    Parameters
    ----------
    obj : object
        Row object or mapping.
    key : str
        Field name.

    Returns
    -------
    object
    """
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _default_setter(obj: Any, key: str, value: Any) -> bool:
    """Write ``key`` on an object, falling back to mapping assignment.

    Parameters
    ----------
    obj : object
        Row object or mapping.
    key : str
        Field name.
    value : object
        Value to store.

    Returns
    -------
    bool
    """
    if isinstance(obj, dict):
        obj[key] = value
        return True
    try:
        setattr(obj, key, value)
    except Exception:
        return False
    return True
