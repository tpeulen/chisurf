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

Tables in a file
----------------
:func:`write_table` and :func:`read_table` are the file half of the same seam:
one dataset per column, in the column's own dtype, with a text column stored as
its dictionary codes. That layout needs no optional HDF5 package, where the
frame writer it replaces does — and on a 1M-row burst table with one four-label
text column it is **0.037 s against 0.29 s to write and 60.0 MB against
72.6 MB** on disk.

There is **no fallback to a frame-based reader** anywhere in this module. That
reader needs an optional package a solved environment does not carry, so a
fallback is a path that works on a developer's machine and fails on everyone
else's — which is exactly how the writers this replaced went unnoticed. A file
in the older frame layout is a file to *convert*, and :func:`read_table` says so
by declining it.

The declining is the part that needs care: handed a file it does not recognise
the columnar reader answers with **no columns** rather than an error, so a
caller that only catches exceptions opens it blank and reports success. Hence
the column-count guard in :func:`read_table`.

Column lifetime
---------------
A ``Column`` obtained from a store is a **borrowed reference into the store's
own column container**, and removing a column invalidates every reference into
it. The stale proxy does not raise — it reads freed memory and answers with an
empty name and no data. Nothing here keeps a ``Column`` across a call that could
invalidate one; :func:`column_at` re-fetches every time, and callers should do
the same. See :func:`column_at` for the whole story.
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
    "column_names",
    "column_values",
    "concat_stores",
    "dataframe_from_store",
    "is_missing",
    "new_store",
    "numeric_column",
    "read_csv_table",
    "read_table",
    "read_table_frame",
    "row_count",
    "rows_from_table",
    "set_cell",
    "store_from_arrays",
    "store_from_dataframe",
    "store_from_rows",
    "take_columns",
    "take_rows",
    "take_where",
    "write_csv_table",
    "write_table",
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
    by ``DataStore.add`` or ``store[i]`` is a reference into the store's column
    container, and **removing** a column invalidates every reference into it.
    It does not raise — the stale proxy reports an empty name and an empty
    array, so the symptom is a column that silently goes blank rather than an
    error.

    Appending used to invalidate too, which was the worse case because it
    happens while a table is merely being built. The library now holds its
    columns in a container whose references survive an append, but an
    environment carrying the older build still dangles there, so this is the
    rule on both counts.

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

    Notes
    -----
    That view is the **store's own buffer**, so writing through it writes into
    the store — which is what makes an in-place edit possible, and what makes an
    accidental one invisible.

    It is safe to keep: the array holds the store alive through its base chain
    (fixed in the library on 2026-08-07; before that it dangled, and a burst
    column read back 84 of 154 rows as ``3.3e-319``). Keeping it also keeps the
    *whole* store alive, columns the caller never asked for included, so a
    reader returning a few columns out of a wide table still has reason to copy.
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


def column_names(table: Any) -> list[str]:
    """Return a table's column names, whatever kind of table it is.

    A store has **both** ``names`` and ``columns``, and its ``columns`` are
    ``Column`` objects rather than names — so asking for ``columns`` first
    matches nothing and every lookup quietly answers "absent". ``names`` first.

    Parameters
    ----------
    table : mapping, tttrlib.DataStore, or pandas.DataFrame

    Returns
    -------
    list of str
    """
    names = getattr(table, "names", None)
    if names is None:
        names = getattr(table, "columns", None)
    if names is None:
        names = list(table.keys())
    return [str(n) for n in names]


def row_count(table: Any) -> int:
    """Return a table's number of **rows**, whatever kind of table it is.

    ``len()`` is the trap this exists for: it is the row count of a frame and
    the *column* count of a mapping, and a store may not define it at all. Code
    written against one silently answers the wrong question for another — a
    3-column table reads as 3 rows, an empty table reads as non-empty, and
    neither raises.

    Parameters
    ----------
    table : mapping, tttrlib.DataStore, or pandas.DataFrame

    Returns
    -------
    int
    """
    n_rows = getattr(table, "n_rows", None)
    if callable(n_rows):
        return int(n_rows())
    names = column_names(table)
    return len(np.asarray(table[names[0]])) if names else 0

def numeric_column(table: Any, name: str) -> np.ndarray:
    """Return one column of any column-addressable table as ``float64``.

    The replacement for ``to_numeric(frame[name], errors="coerce")``: a value
    that is not a number becomes ``NaN`` rather than raising, and a column that
    is not there is all-``NaN`` rather than a ``KeyError`` — which is what the
    burst code around it already expected.

    Works on a frame, a ``{name: array}`` mapping, or a store's columns, because
    none of the arithmetic that follows cares which it got.

    Parameters
    ----------
    table : mapping, tttrlib.DataStore, or pandas.DataFrame
        The table.
    name : str
        Column name.

    Returns
    -------
    numpy.ndarray
        ``float64``, one entry per row.
    """
    # A store has BOTH `names` and `columns`, and its `columns` are Column
    # objects, not names -- so asking for `columns` first silently answers with
    # something that matches nothing, and every lookup returns "absent" rather
    # than failing. Ask for `names` first.
    if name not in column_names(table):
        return np.full(row_count(table), np.nan, dtype=float)

    values = np.asarray(table[name])
    if values.dtype.kind in "fiub":
        return values.astype(float)
    out = np.full(len(values), np.nan, dtype=float)
    for i, value in enumerate(values):
        try:
            out[i] = float(value)
        except (TypeError, ValueError):
            pass
    return out

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


def write_table(
    path: Any,
    data: Any,
    *,
    group: str = "/",
    compression: int = 0,
    meta: Mapping[str, Any] | None = None,
    replace: bool = True,
) -> None:
    """Write a table to HDF5 as one dataset per column.

    The columnar layout: a group of 1-D datasets, one per column, in the
    column's own dtype, with a text column stored as its dictionary codes and a
    validity mask beside any column that has one. It is the shape a store
    already has, so writing is a buffer per column rather than a conversion —
    measured on a 1M-row burst table with one four-label text column, **0.037 s
    against 0.29 s and 60.0 MB against 72.6 MB** for the frame writer it
    replaces, and it needs no optional HDF5 package.

    Parameters
    ----------
    path : path-like
        Target file. Existing groups it does not write are left alone, so two
        tables can live in one file.
    data : tttrlib.DataStore, pandas.DataFrame, or mapping of str to array-like
        The table. A frame or a mapping is converted with
        :func:`store_from_dataframe` / :func:`store_from_arrays`.
    group : str
        Group to write into. ``"/"`` — the root — is what a burst reader looks
        at first, so it is the default.
    compression : int
        gzip level, 0 for none. These files are written once per analysis and
        read repeatedly, and level 4 costs roughly thirty times the write to
        save eight percent of the size, so the default is off.
    meta : mapping, optional
        A one-row side table, written as a child group named ``meta``. This is
        where a back-reference to the photon file belongs: beside the results
        rather than as a column repeated once per row.
    replace : bool
        Whether the file ends up holding **this table and nothing else**, which
        is what every writer that rewrites a table in place means. The
        alternative keeps whatever else is in the file, and is right only for a
        caller deliberately adding a group beside an existing one. The
        difference is not cosmetic: an in-place rewrite that drops a column
        leaves the old dataset behind under the other mode, and the column comes
        back on the next read.
    """
    import tttrlib

    store = _as_store(data)
    if meta:
        child = store.add_group("meta")
        for name, value in meta.items():
            child.add(str(name), np.asarray([value], dtype=object))
        child.set_n_rows(1)
    mode = tttrlib.Hdf5WriteMode_Truncate if replace else tttrlib.Hdf5WriteMode_Update
    if not tttrlib.write_hdf5(str(path), store, group, int(compression), mode):
        raise OSError(f"could not write a table to {path}")


def _as_store(data: Any) -> Any:
    """Return ``data`` as a store, converting a frame or a mapping.

    Parameters
    ----------
    data : object
        A ``tttrlib.DataStore``, a :class:`pandas.DataFrame`, or a mapping of
        column name to values.

    Returns
    -------
    tttrlib.DataStore
    """
    if isinstance(data, Mapping):
        return store_from_arrays(data)
    if hasattr(data, "n_columns"):
        return data
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        return store_from_rows(data)
    return store_from_dataframe(data)




def rows_from_table(table: Any) -> list[dict[str, Any]]:
    """Return a table as a list of row mappings — the inverse of
    :func:`store_from_rows`.

    For the boundaries that are row-oriented because something else demands it:
    a JSON-RPC payload, a service result, anything crossing a process. Not for
    computation — a per-row dict of a million-row table is a million dicts, and
    the column arrays are right there.

    Parameters
    ----------
    table : mapping, tttrlib.DataStore, or pandas.DataFrame

    Returns
    -------
    list of dict
    """
    names = column_names(table)
    columns = [np.asarray(table[name]) for name in names]
    return [
        {name: column[i].item() if hasattr(column[i], "item") else column[i]
         for name, column in zip(names, columns)}
        for i in range(row_count(table))
    ]

def store_from_rows(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str] | None = None
) -> Any:
    """Build a store from a sequence of row mappings.

    The row-oriented shape an API hands back, and the one that otherwise goes
    through a frame purely to be turned column-wise again. Column order is
    first-seen across the rows, so a table stays in the order it was built in
    rather than alphabetically.

    A key some rows lack is **masked** in those rows rather than filled with a
    sentinel, which is the distinction a store has and a frame does not: an
    integer column keeps its dtype and still says "not measured".

    Parameters
    ----------
    rows : sequence of mapping
        One mapping per row.
    columns : sequence of str, optional
        Column order, as a frame constructor's ``columns=`` argument. Names no
        row carries become an all-missing column, which is how a caller keeps a
        table's shape fixed regardless of what the rows happened to have.

    Returns
    -------
    tttrlib.DataStore
    """
    rows = list(rows)
    if columns is not None:
        names = [str(c) for c in columns]
    else:
        names = []
        seen: set[str] = set()
        for row in rows:
            for name in row:
                if name not in seen:
                    seen.add(name)
                    names.append(str(name))

    store = new_store()
    if not rows:
        return store
    for name in names:
        raw = [row.get(name) for row in rows]
        # A key a row lacks and a key whose value is None are the same thing
        # here: not measured. The old expression masked only the first, and the
        # second silently became 0.
        present = np.array([v is not None for v in raw], dtype=bool)
        if any(isinstance(v, str) for v in raw if v is not None):
            values = np.array(["" if v is None else str(v) for v in raw], dtype=object)
        elif all(
            isinstance(v, (bool, int)) and not isinstance(v, bool) or isinstance(v, np.integer)
            for v in raw
            if v is not None
        ) and any(v is not None for v in raw):
            # An integer column stays one. Forcing float here is not cosmetic:
            # these rows are written straight out as text, and "10" becoming
            # "10.0" changes a shipped file format that other programs parse.
            values = np.array([0 if v is None else int(v) for v in raw], dtype=np.int64)
        else:
            values = np.array([np.nan if v is None else v for v in raw], dtype=float)
        store.add(name, values)
        if not present.all():
            column = store[store.n_columns() - 1]
            column.set_mask(np.ascontiguousarray(present, dtype=np.uint8))
    store.set_n_rows(len(rows))
    return store

def concat_stores(stores: Sequence[Any], *, inner: bool = False) -> Any:
    """Stack stores row-wise, the way a burst folder is combined.

    The operation a frame was being built for: several measurements read
    separately and put together. Columns line up **by name**, not by position,
    because two runs need not have listed them in the same order.

    A column missing from one side keeps its dtype and its rows are marked
    *not measured*. That is the whole advantage over a frame here and it is not
    a small one — a frame has to widen an ``int64`` column to ``float64`` to
    hold a ``NaN``, and the dtype cannot be recovered afterwards.

    Parameters
    ----------
    stores : sequence of tttrlib.DataStore, pandas.DataFrame or mapping
        The tables to stack. An empty sequence gives an empty store.
    inner : bool
        Keep only the columns every store has, rather than the union.

    Returns
    -------
    tttrlib.DataStore

    Raises
    ------
    ValueError
        When a column has a different dtype in two stores. It is not promoted:
        widening a float32 to meet a float64 loses the dtype the store exists to
        keep, and does it silently.
    """
    import tttrlib

    # Frames are accepted, as everywhere else on this seam: a migration moves
    # one producer at a time, and until the last one moves, a caller legitimately
    # holds a mixture.
    stores = [_as_store(s) for s in stores if s is not None]
    if not stores:
        return new_store()
    try:
        return tttrlib.concat(stores, join="inner" if inner else "outer")
    except Exception as exc:  # the library names the offending column
        raise ValueError(str(exc)) from exc


def take_columns(store: Any, names: Sequence[str]) -> Any:
    """Return a new store holding only ``names``, in that order.

    The column-wise counterpart of :func:`take_rows`, for putting a subset of
    one table beside another — a burst companion contributes its new columns and
    not the ones the burst table already has.

    Parameters
    ----------
    store : tttrlib.DataStore
        The table to take from.
    names : sequence of str
        Column names.

    Returns
    -------
    tttrlib.DataStore
    """
    out = new_store()
    present = column_names(store)
    for name in names:
        if name not in present:
            continue
        column = column_at(store, present.index(name))
        # np.array: these outlive nothing here, but the copy keeps the new store
        # independent of the one it came from, which is what a caller expects of
        # a "new store" rather than a view.
        out.add(str(name), np.array(column_values(store, present.index(name))))
    out.set_n_rows(row_count(store))
    return out

def take_rows(store: Any, rows: Any) -> Any:
    """Return a new store holding ``rows``, in that order.

    Materialises a selection, which is what a mask alone cannot do — the reason
    filtering a table used to need a frame. A copy, not a view; column order,
    dtypes, dictionaries and validity all come across.

    Parameters
    ----------
    store : tttrlib.DataStore
        The table to take from.
    rows : array-like of int
        Row positions.

    Returns
    -------
    tttrlib.DataStore
    """
    return store.take([int(i) for i in np.asarray(rows).ravel()])


def take_where(store: Any, mask: Any) -> Any:
    """Return a new store holding the rows where ``mask`` is true.

    Parameters
    ----------
    store : tttrlib.DataStore
        The table to filter.
    mask : array-like of bool
        One entry per row.

    Returns
    -------
    tttrlib.DataStore
    """
    return take_rows(store, np.nonzero(np.asarray(mask, dtype=bool).ravel())[0])

def read_table(path: Any, *, group: str = "/") -> Any:
    """Return a columnar HDF5 table as a store, or ``None`` if it is not one.

    ``None`` means the file is a different shape — a frame-written table, a
    photon-data file — and the caller should read it another way. Returning
    ``None`` rather than raising is what keeps the two readable side by side;
    :func:`read_table_frame` is the caller that does both.

    The column-count guard matters: handed a file it does not recognise the
    reader can answer with an *empty* table rather than declining, so a caller
    that only checks for an exception opens every foreign file as a blank table
    and reports success.

    Parameters
    ----------
    path : path-like
        File to read.
    group : str
        Group to read.

    Returns
    -------
    tttrlib.DataStore or None
    """
    import tttrlib

    try:
        columns = tttrlib.read_hdf5_table_columns(str(path), group)
    except Exception:
        return None
    if len(columns) < 1:
        return None
    try:
        store = tttrlib.read_hdf5(str(path), group)
    except Exception:
        return None
    return store if store.n_columns() > 0 else None


#: Text a CSV writer puts where a value is missing. An empty field, which is
#: what a frame's writer produces and what :func:`read_csv_table` takes back as
#: missing.
CSV_NA = ""


def write_csv_table(
    path: Any,
    data: Any,
    *,
    delimiter: str = "\t",
    header: bool = True,
    columns: Sequence[str] | None = None,
    keep_decimal_point: bool = True,
) -> None:
    """Write a table as delimited text, in parallel.

    Measured against the frame writer it replaces, including the conversion into
    a store: **5.0x on 5k rows and 7.2x on 200k** (1.97 s -> 0.27 s), at byte-
    identical file size.

    The text matches what a frame's writer produces, which is what makes this a
    drop-in for it. That needs saying because the writer's *own* default is
    different: a shortest-form writer spells an integral value in a real column
    ``12`` rather than ``12.0``, since they are the same double. They are not the
    same *column* to a reader inferring types from text — an all-integral column
    stops looking like a real one, and an all-zero column is exactly what a
    burst companion carries for the bursts an analysis skipped. So
    ``keep_decimal_point`` is on here, and turning it off is a deliberate choice
    to write the shorter spelling.

    The burst companion formats are still **not** written through this: their
    canonical writer is
    :func:`chisurf.core.fio.fluorescence.burst_companion.write_companion`, which
    owns their ``%.6f``, their zero interleaving and their one-row-per-burst
    rule, none of which is a formatting question.

    Non-finite floats are masked rather than written as ``nan``, so a missing
    value comes out as the empty field a frame writes and this module's reader
    takes back as missing. Infinities are values, not gaps, and are left alone.

    Parameters
    ----------
    path : path-like or None
        Target file, or ``None`` to return the text instead of writing it.
    data : tttrlib.DataStore, pandas.DataFrame, or mapping of str to array-like
        The table.
    delimiter : str
        Field separator. Tab, because that is what the tables here use.
    header : bool
        Whether to write the column-name row.
    columns : sequence of str, optional
        Which columns, in this order. All of them by default.
    keep_decimal_point : bool
        Write an integral value in a real column as ``12.0`` rather than ``12``,
        so the column still reads back as a real one. On by default; see above.

    Returns
    -------
    str or None
        The text when ``path`` is ``None``.
    """
    import tttrlib

    store = _as_store(data)
    # On a copy: masking is how a NaN reaches the file as an empty field, and
    # doing it in place would mean WRITING A TABLE CHANGES IT -- every NaN row
    # coming back marked "not measured" afterwards. Verified before the copy was
    # added: has_mask() went False -> True across a write.
    if _has_non_finite(store):
        store = _mask_non_finite(store.copy())
    return tttrlib.write_csv(
        None if path is None else str(path),
        store,
        delimiter=delimiter,
        header=header,
        na_rep=CSV_NA,
        columns=None if columns is None else list(columns),
        keep_decimal_point=keep_decimal_point,
    )


def _has_non_finite(store: Any) -> bool:
    """Whether any float column holds a ``NaN``.

    Asked first so the copy in :func:`write_csv_table` is only paid for by the
    tables that need it.

    Parameters
    ----------
    store : tttrlib.DataStore

    Returns
    -------
    bool
    """
    for index in range(store.n_columns()):
        column = column_at(store, index)
        if column.dtype in (STRING_DTYPE, BOOL_DTYPE):
            continue
        values = np.asarray(column.numpy())
        if values.dtype.kind == "f" and np.isnan(values).any():
            return True
    return False


def _mask_non_finite(store: Any) -> Any:
    """Mark ``NaN`` entries of every float column as missing, in place.

    A store says "missing" with its validity mask and a frame says it with
    ``NaN``, so a frame converted straight across writes the literal text
    ``nan`` where the frame's own writer would have written an empty field.
    This puts the two back in step at the CSV boundary only — an HDF5 write
    keeps the ``NaN``, because there it is a value the reader gets back
    unchanged.

    Parameters
    ----------
    store : tttrlib.DataStore
        Store to adjust.

    Returns
    -------
    tttrlib.DataStore
        The same store.
    """
    for index in range(store.n_columns()):
        column = column_at(store, index)
        if column.dtype in (STRING_DTYPE, BOOL_DTYPE):
            continue
        values = np.asarray(column.numpy())
        if values.dtype.kind != "f":
            continue
        missing = np.isnan(values)
        if not missing.any():
            continue
        valid = ~missing
        if column.has_mask():
            valid &= column.mask_numpy().astype(bool)
        column.set_mask(np.ascontiguousarray(valid, dtype=np.uint8))
    return store


def read_csv_table(path: Any, *, delimiter: str = "\t", header: bool = True) -> Any:
    """Read delimited text into a store, or ``None`` if this reader declines it.

    The threaded reader handles a plain delimited file whose header is its first
    line. It does **not** handle a decimal comma, a skipped preamble or
    whitespace alignment, and it does not guess: those come back as ``None`` so
    the caller reads them with the general reader. Declining explicitly is the
    point — a quiet fallback is what makes the same file load differently on two
    machines.

    Parameters
    ----------
    path : path-like
        File to read.
    delimiter : str
        Field separator.
    header : bool
        Whether the first line names the columns.

    Returns
    -------
    tttrlib.DataStore or None
    """
    import tttrlib

    try:
        store = tttrlib.read_csv(str(path), delimiter=delimiter, has_header=header)
    except Exception:
        return None
    return store if store.n_columns() > 0 else None


def read_table_frame(path: Any, *, key: str = "results") -> Any:
    """Return a columnar HDF5 table as a frame, for a caller that wants one.

    The conversion, not a second reader: the file must be in the columnar layout
    this module writes. There is deliberately **no fallback to a frame-based
    HDF5 reader** — that reader needs an optional package a solved environment
    does not carry, so a fallback is a path that works on a developer's machine
    and fails on everyone else's, which is how the writers it replaced went
    unnoticed for so long.

    Parameters
    ----------
    path : path-like
        File to read.
    key : str
        Group holding the table. The root is tried first, then ``/<key>``.

    Returns
    -------
    pandas.DataFrame

    Raises
    ------
    OSError
        When the file holds no columnar table — including when it holds a
        frame-written one, which is a file to convert rather than a file to
        read.
    """
    # The root first, which is where a table is written and where the burst
    # readers look; then the key as a group, for a file that puts one there.
    store = read_table(path, group=str(key) if str(key).startswith("/") else "/")
    if store is None and not str(key).startswith("/"):
        store = read_table(path, group=f"/{key}")
    if store is None:
        raise OSError(
            f"{path} holds no columnar table. A file written by an earlier "
            "release is in the frame layout and has to be converted rather than "
            "read here."
        )
    return dataframe_from_store(store)


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
