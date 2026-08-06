"""The columnar-store seam — ``DataStore`` in, ``DataFrame`` out, and back.

ChiSurf's tables are moving from :class:`pandas.DataFrame` onto the columnar
store one consumer at a time. This module is the Qt-free layer both sides of
that migration share: the conversions that keep pandas as an *interop* format
rather than the storage model, and the cell-level primitives a store needs
before it can back an editable table. See the
[columnar store concept](/subsystems/columnar-store.md) for the plan and the
measurements.

Why a store rather than a frame — measured on a 1M-row burst table (six float64,
one int32, one float32, one four-label text column): **114.3 MB as a frame,
60.2 MB as a store**, almost all of the difference being the text column, which
pandas holds as a million Python string objects and a store holds as four
strings plus a million ``int32`` codes. Dtypes also survive a round trip: a
float32 column stays float32 instead of being widened, and an integer column
with a missing value stays an integer column instead of becoming floats.

Missing values
--------------
The two containers do not mean the same thing by "missing", and this module
never silently converts one into the other:

* a frame marks a missing number with ``NaN``, which only a float column can
  hold;
* a store carries a per-column validity **mask**, so an integer column can say
  "not measured" without giving up a value or its dtype — which is exactly the
  distinction a burst analysis that skipped a burst needs.

:func:`store_from_dataframe` therefore masks non-finite entries of an integer or
boolean column rather than widening the column, and :func:`dataframe_from_store`
turns a masked entry back into ``NaN``, widening to float where it must. A round
trip through pandas is lossy in that one direction, and it is documented rather
than hidden.

Column lifetime
---------------
A ``Column`` obtained from a store is a **borrowed reference into the store's
own column vector**, and adding a further column reallocates that vector. The
stale proxy does not raise — it reads freed memory and answers with an empty
name and no data. Nothing here keeps a ``Column`` across a call that could add
one; :func:`column_at` re-fetches every time, and callers should do the same
rather than caching proxies. See :func:`column_at` for the whole story.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

__all__ = [
    "BOOL_DTYPE",
    "STRING_DTYPE",
    "clear_cell",
    "column_at",
    "column_values",
    "dataframe_from_store",
    "is_missing",
    "new_store",
    "set_cell",
    "store_from_arrays",
    "store_from_dataframe",
]

#: ``Column.dtype`` for a boolean column.
BOOL_DTYPE = "bool"

#: ``Column.dtype`` for a dictionary-encoded text column.
STRING_DTYPE = "str"


def _tttrlib():
    """Import ``tttrlib`` on first use.

    Kept out of module scope so that importing this module — which the table
    widgets do at GUI-startup time — does not pull in the compiled extension
    before anything asks for a store.

    Returns
    -------
    module
        The imported ``tttrlib`` module.
    """
    import tttrlib

    return tttrlib


def new_store() -> Any:
    """Return an empty ``tttrlib.DataStore``.

    Returns
    -------
    tttrlib.DataStore
    """
    return _tttrlib().DataStore()


def column_at(store: Any, index: int) -> Any:
    """Return the column at ``index``, freshly fetched from ``store``.

    Always call this instead of holding on to a column. A ``Column`` handed out
    by ``DataStore.add`` or ``store[i]`` is a reference into a
    ``std::vector<Column>``; adding another column reallocates that vector and
    every previously handed-out proxy then points at freed memory. It does not
    raise — the stale proxy reports an empty name and an empty array, so the
    symptom is a column that silently goes blank rather than an error.

    Parameters
    ----------
    store : tttrlib.DataStore
        The store to read from.
    index : int
        Positional column index.

    Returns
    -------
    tttrlib.Column
        A proxy valid until the next structural change to ``store``.
    """
    return store[int(index)]


def is_missing(value: Any) -> bool:
    """Return whether a scalar means "no value".

    Covers ``None`` and floating-point ``NaN``. Unlike :func:`pandas.isna` this
    needs no pandas import and does not treat an empty string as missing — a
    text column's empty label is a value.

    Parameters
    ----------
    value : object
        Scalar to test.

    Returns
    -------
    bool
    """
    if value is None:
        return True
    if isinstance(value, float):
        return value != value
    try:
        return bool(np.isnan(value))
    except (TypeError, ValueError):
        return False


def column_values(store: Any, index: int, *, masked_as_nan: bool = True) -> np.ndarray:
    """Return one column as an array, honouring its validity mask.

    Parameters
    ----------
    store : tttrlib.DataStore
        The store to read from.
    index : int
        Positional column index.
    masked_as_nan : bool
        When the column carries a validity mask, return ``float64`` with ``NaN``
        at the masked positions instead of the raw buffer, so that plain numpy
        comparisons see the missing values. When the column has no mask — the
        common case — the column's own buffer is returned **without a copy** and
        in its own dtype, which is the point of the store.

    Returns
    -------
    numpy.ndarray
        A zero-copy view for an unmasked numeric column; a new array otherwise.
    """
    column = column_at(store, index)
    values = column.numpy()
    if not masked_as_nan or not column.has_mask():
        return values
    if column.dtype in (STRING_DTYPE, BOOL_DTYPE):
        out = np.asarray(values, dtype=object)
        out[~column.mask_numpy()] = None
        return out
    out = np.asarray(values, dtype="float64")
    out[~column.mask_numpy()] = np.nan
    return out


def _set_mask_bit(column: Any, row: int, valid: bool) -> None:
    """Set one entry of a column's validity mask.

    The mask is read back as a copy rather than as a view, so a single-cell
    change is a read-modify-write of the whole mask. Creating the mask lazily
    keeps an all-valid column free of one.

    Parameters
    ----------
    column : tttrlib.Column
        Column to modify.
    row : int
        Row index.
    valid : bool
        ``True`` to mark the cell present, ``False`` to mark it missing.
    """
    if column.has_mask():
        mask = column.mask_numpy()
    elif valid:
        return
    else:
        mask = np.ones(column.size(), dtype=bool)
    mask[row] = valid
    column.set_mask(np.ascontiguousarray(mask, dtype=np.uint8))


def clear_cell(store: Any, row: int, index: int) -> bool:
    """Mark one cell as missing without writing a sentinel into it.

    This is the store's answer to a blanked cell: the value stays whatever it
    was and the column's validity mask records that it means nothing. An integer
    column therefore keeps both its dtype and the distinction between "zero" and
    "not measured", which is the thing a frame cannot do.

    Parameters
    ----------
    store : tttrlib.DataStore
        Store to modify.
    row : int
        Row index.
    index : int
        Positional column index.

    Returns
    -------
    bool
        ``True`` when the mask was updated.
    """
    column = column_at(store, index)
    if not 0 <= row < column.size():
        return False
    _set_mask_bit(column, row, False)
    return True


def set_cell(store: Any, row: int, index: int, value: Any) -> bool:
    """Write one cell, by whichever route the column's dtype needs.

    Three different routes, because the library exposes three:

    * a **numeric** column is written straight through its zero-copy view;
    * a **boolean** column has no writable view, so it is a read-modify-write of
      the whole column;
    * a **text** column is dictionary-encoded, so the label is looked up in the
      dictionary — appended to it when new — and the row's integer code is what
      actually changes.

    A missing ``value`` (``None`` or ``NaN``) clears the cell through
    :func:`clear_cell` rather than writing a sentinel.

    Parameters
    ----------
    store : tttrlib.DataStore
        Store to modify.
    row : int
        Row index.
    index : int
        Positional column index.
    value : object
        The new value. Coerced to the column's dtype.

    Returns
    -------
    bool
        ``True`` when the write happened.
    """
    column = column_at(store, index)
    if not 0 <= row < column.size():
        return False

    if is_missing(value):
        _set_mask_bit(column, row, False)
        return True

    dtype = column.dtype
    if dtype == STRING_DTYPE:
        label = str(value)
        dictionary = list(column.dictionary())
        if label not in dictionary:
            dictionary.append(label)
            column.set_dictionary(dictionary)
        column.codes()[row] = dictionary.index(label)
    elif dtype == BOOL_DTYPE:
        values = np.asarray(column.numpy(), dtype=bool)
        values[row] = bool(value)
        column.set_numpy(values)
    else:
        column.numpy()[row] = value

    _set_mask_bit(column, row, True)
    return True


def store_from_arrays(columns: Mapping[str, Any] | Sequence[tuple]) -> Any:
    """Build a store from named arrays, keeping every dtype.

    Parameters
    ----------
    columns : mapping or sequence of (str, array-like)
        Column name to values. Order is preserved. A sequence of strings (or an
        object array of them) becomes a dictionary-encoded text column.

    Returns
    -------
    tttrlib.DataStore

    Raises
    ------
    ValueError
        If the columns are not all the same length.
    """
    items = list(columns.items()) if isinstance(columns, Mapping) else [(str(k), v) for k, v in columns]
    store = new_store()
    lengths = set()
    for name, values in items:
        array = values if _is_text(values) else np.asarray(values)
        lengths.add(len(array))
        if len(lengths) > 1:
            raise ValueError(f"column {name!r} has {len(array)} rows, expected {lengths.pop()}")
        store.add(str(name), array)
    return store


def _is_text(values: Any) -> bool:
    """Return whether ``values`` should become a text column.

    Parameters
    ----------
    values : object
        Candidate column values.

    Returns
    -------
    bool
    """
    array = np.asarray(values)
    return array.dtype.kind in ("U", "S", "O")


def store_from_dataframe(df: Any) -> Any:
    """Convert a :class:`pandas.DataFrame` into a store, dtype for dtype.

    Object and string columns become dictionary-encoded text columns. An integer
    or boolean column whose frame dtype is nullable keeps its integer dtype and
    records the missing entries in the store's validity mask, rather than being
    widened to float the way ``to_numpy`` would.

    Parameters
    ----------
    df : pandas.DataFrame
        The frame to convert. Its index is dropped: a store addresses rows by
        position, and every frame this replaces carries a ``RangeIndex``.

    Returns
    -------
    tttrlib.DataStore
    """
    import pandas as pd

    store = new_store()
    for label in df.columns:
        series = df[label]
        name = str(label)
        if isinstance(series.dtype, pd.CategoricalDtype) or series.dtype == object:
            missing = np.asarray(series.isna())
            # Fill before the cast: ``astype(str)`` would put the literal
            # ``"nan"`` in the dictionary and it would outlive the mask.
            store.add(name, np.asarray(series.fillna("").astype(str), dtype=object))
        elif pd.api.types.is_bool_dtype(series.dtype):
            missing = np.asarray(series.isna())
            store.add(name, np.asarray(series.fillna(False), dtype=bool))
        elif pd.api.types.is_integer_dtype(series.dtype):
            missing = np.asarray(series.isna())
            store.add(name, np.asarray(series.fillna(0), dtype=_numpy_dtype(series.dtype)))
        elif pd.api.types.is_numeric_dtype(series.dtype):
            values = series.to_numpy(dtype=_numpy_dtype(series.dtype), na_value=np.nan)
            store.add(name, values)
            missing = np.zeros(len(values), dtype=bool)
        else:
            missing = np.asarray(series.isna())
            store.add(name, np.asarray(series.fillna("").astype(str), dtype=object))
        if missing.any():
            column = store[store.n_columns() - 1]
            column.set_mask(np.ascontiguousarray(~missing, dtype=np.uint8))
    if store.n_columns() == 0:
        store.set_n_rows(int(len(df.index)))
    return store


def _numpy_dtype(dtype: Any) -> Any:
    """Return the plain numpy dtype behind a possibly-nullable pandas dtype.

    Parameters
    ----------
    dtype : object
        A numpy or pandas extension dtype.

    Returns
    -------
    numpy.dtype
    """
    numpy_dtype = getattr(dtype, "numpy_dtype", None)
    return np.dtype(numpy_dtype if numpy_dtype is not None else dtype)


def dataframe_from_store(store: Any) -> Any:
    """Convert a store back into a :class:`pandas.DataFrame`.

    The interop direction — for a caller that reports to a user, writes a format
    only pandas knows, or hands a table to a notebook. It is lossy in one
    respect and the loss is deliberate: a masked entry becomes ``NaN``, which
    widens an integer column to float, because a frame has nowhere else to put
    it.

    Parameters
    ----------
    store : tttrlib.DataStore
        The store to convert.

    Returns
    -------
    pandas.DataFrame
        A frame with a ``RangeIndex`` and one column per store column.
    """
    import pandas as pd

    data = {}
    for index in range(store.n_columns()):
        column = column_at(store, index)
        values = column.numpy()
        if column.has_mask():
            valid = column.mask_numpy()
            if column.dtype == STRING_DTYPE:
                values = np.asarray(values, dtype=object)
                values[~valid] = None
            else:
                values = np.asarray(values, dtype="float64")
                values[~valid] = np.nan
        else:
            values = np.asarray(values)
        data[column.name()] = values
    return pd.DataFrame(data, index=pd.RangeIndex(store.n_rows()))
