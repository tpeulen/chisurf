"""Table sources — the adapter layer of :mod:`chisurf.gui.widgets.chitable`.

A :class:`TableSource` is the only thing :class:`~chisurf.gui.widgets.chitable.model.ChiTableModel`
knows about. Three adapters cover every tabular shape already in the tree:

``DataFrameSource``
    a :class:`pandas.DataFrame` (ndX burst frames, model-parameter tables);
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
Numeric dtype tests go exclusively through :func:`pandas.api.types.is_numeric_dtype`.
``numpy.issubdtype`` raises on pandas extension dtypes (the nullable ``Float64``
the pyarrow reader produces), which is the root cause of a long-standing crash in
ndX's table editor.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from chisurf.gui.widgets.chitable.columns import (
    KIND_AUTO,
    KIND_BOOL,
    KIND_FLOAT,
    KIND_INT,
    KIND_STR,
    ColumnSpec,
)


def kind_from_dtype(dtype: Any) -> str:
    """Map a numpy/pandas dtype onto a :class:`ColumnSpec` kind.

    Parameters
    ----------
    dtype : object
        A numpy dtype, pandas extension dtype, or anything ``pandas`` accepts.

    Returns
    -------
    str
        One of ``"bool"``, ``"int"``, ``"float"`` or ``"str"``.
    """
    try:
        if pd.api.types.is_bool_dtype(dtype):
            return KIND_BOOL
        if pd.api.types.is_integer_dtype(dtype):
            return KIND_INT
        if pd.api.types.is_numeric_dtype(dtype):
            return KIND_FLOAT
    except (TypeError, ValueError):
        pass
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


def is_na(value: Any) -> bool:
    """Return whether a scalar is a pandas/numpy missing value.

    Covers ``None``, ``NaN``, ``NaT`` and ``pandas.NA`` — the last of which the
    nullable extension dtypes produce and which renders as the literal string
    ``"<NA>"`` if it reaches ``str()``.

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
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


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
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


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


class DataFrameSource(TableSource):
    """Adapter over a :class:`pandas.DataFrame`.

    Parameters
    ----------
    df : pandas.DataFrame
        The frame to expose. Held by reference; edits mutate it in place unless
        the caller passes a copy.
    editable : bool
        Make every column editable. Per-column overrides go through ``specs``.
    specs : sequence of ColumnSpec, optional
        Explicit column specs. When given they must match ``df.columns`` in
        length and order; anything omitted is synthesised from the dtype.
    readonly_columns : sequence of str
        Column labels to force read-only, even when ``editable`` is set.
    bool_columns : sequence of str
        Column labels to render with a checkbox delegate.
    colorize_columns : sequence of str, optional
        Column labels opted into value colouring. ``None`` colours every
        numeric column.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        *,
        editable: bool = False,
        specs: Sequence[ColumnSpec] | None = None,
        readonly_columns: Sequence[str] = (),
        bool_columns: Sequence[str] = (),
        colorize_columns: Sequence[str] | None = None,
    ) -> None:
        self._df = df
        self._editable = bool(editable)
        self._readonly = set(readonly_columns or ())
        self._bool_columns = set(bool_columns or ())
        self._colorize = None if colorize_columns is None else set(colorize_columns)
        self._specs = tuple(specs) if specs else self._build_specs()

    # -- construction -----------------------------------------------------

    def _build_specs(self) -> tuple:
        """Derive column specs from the frame's dtypes.

        Returns
        -------
        tuple of ColumnSpec
        """
        out = []
        for label in self._df.columns:
            dtype = self._df[label].dtype
            kind = KIND_BOOL if str(label) in self._bool_columns else kind_from_dtype(dtype)
            numeric = kind in (KIND_FLOAT, KIND_INT)
            colorize = numeric if self._colorize is None else (str(label) in self._colorize)
            out.append(
                ColumnSpec(
                    key=str(label),
                    label=str(label),
                    kind=kind,
                    editable=self._editable and str(label) not in self._readonly,
                    colorize=colorize,
                    delegate="bool" if kind == KIND_BOOL else "",
                )
            )
        return tuple(out)

    # -- TableSource ------------------------------------------------------

    @property
    def dataframe(self) -> pd.DataFrame:
        """Return the wrapped frame.

        Returns
        -------
        pandas.DataFrame
        """
        return self._df

    def set_dataframe(self, df: pd.DataFrame) -> None:
        """Replace the wrapped frame and rebuild the column specs.

        Parameters
        ----------
        df : pandas.DataFrame
            The new frame.
        """
        self._df = df
        self._specs = self._build_specs()

    def column_specs(self) -> Sequence[ColumnSpec]:
        """Return the derived or supplied column specs.

        Returns
        -------
        sequence of ColumnSpec
        """
        return self._specs

    def row_count(self) -> int:
        """Return the number of frame rows.

        Returns
        -------
        int
        """
        return int(len(self._df.index))

    def value(self, row: int, col: int) -> Any:
        """Return one cell of the frame.

        Parameters
        ----------
        row : int
            Positional row index.
        col : int
            Positional column index.

        Returns
        -------
        object
            ``None`` when the position is out of range or unreadable.
        """
        try:
            return self._df.iat[row, col]
        except Exception:
            try:
                return self._df.iloc[row, col]
            except Exception:
                return None

    def set_value(self, row: int, col: int, value: Any) -> bool:
        """Write one cell of the frame.

        Parameters
        ----------
        row : int
            Positional row index.
        col : int
            Positional column index.
        value : object
            Already-coerced value.

        Returns
        -------
        bool
        """
        try:
            self._df.iat[row, col] = value
        except Exception:
            try:
                self._df.iloc[row, col] = value
            except Exception:
                return False
        return True

    def column_array(self, col: int) -> np.ndarray | None:
        """Return a column as a numpy array.

        Numeric columns — including pandas extension dtypes — are returned as
        ``float64`` with ``NaN`` for missing values, so downstream code can use
        plain numpy comparisons.

        Parameters
        ----------
        col : int
            Positional column index.

        Returns
        -------
        numpy.ndarray or None
        """
        try:
            series = self._df.iloc[:, col]
        except Exception:
            return None
        try:
            if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(
                series.dtype
            ):
                return series.to_numpy(dtype="float64", na_value=np.nan)
        except (TypeError, ValueError):
            pass
        try:
            return series.to_numpy()
        except Exception:
            return None

    def row_label(self, row: int) -> str:
        """Return the frame index entry as the row header.

        Parameters
        ----------
        row : int
            Positional row index.

        Returns
        -------
        str
        """
        try:
            return str(self._df.index[row])
        except Exception:
            return str(row)


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
