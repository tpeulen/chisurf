"""Tests for the columnar-store seam, :mod:`chisurf.core.datastore`.

Covers the two conversions, the three cell-write routes, the mask semantics that
distinguish a store from a frame, and the borrowed-column trap that makes a
cached column proxy read freed memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from chisurf.core.datastore import (
    clear_cell,
    column_at,
    column_values,
    dataframe_from_store,
    is_missing,
    new_store,
    set_cell,
    store_from_arrays,
    store_from_dataframe,
)


@pytest.fixture
def frame():
    """Return a small mixed-dtype frame.

    Returns
    -------
    pandas.DataFrame
    """
    return pd.DataFrame(
        {
            "name": ["alpha", "beta", "gamma", "delta"],
            "value": [1.0, 20.0, 300.0, np.nan],
            "count": np.array([1, 2, 3, 4], dtype="int32"),
            "flag": [True, False, True, False],
            "small": np.array([0.5, 1.5, 2.5, 3.5], dtype="float32"),
        }
    )


# ── conversions ──────────────────────────────────────────────────────────


def test_store_from_dataframe_keeps_every_dtype(frame):
    """A frame's narrow dtypes survive the conversion instead of being widened."""
    store = store_from_dataframe(frame)
    dtypes = {store[i].name(): store[i].dtype for i in range(store.n_columns())}
    assert dtypes == {
        "name": "str",
        "value": "float64",
        "count": "int32",
        "flag": "bool",
        "small": "float32",
    }
    assert store.n_rows() == 4


def test_text_column_is_dictionary_encoded(frame):
    """A text column becomes labels plus codes, not one string object per row."""
    store = store_from_dataframe(frame)
    column = store["name"]
    assert list(column.dictionary()) == ["alpha", "beta", "gamma", "delta"]
    assert list(column.codes()) == [0, 1, 2, 3]


def test_repeated_labels_cost_one_dictionary_entry_each():
    """The memory claim: a repeated label is stored once, not once per row."""
    store = store_from_arrays({"stream": ["GG"] * 500 + ["RR"] * 500})
    column = store["stream"]
    assert list(column.dictionary()) == ["GG", "RR"]
    assert column.size() == 1000
    # 1000 int32 codes plus two short strings — far below 1000 string objects.
    assert column.nbytes() < 1000 * 8


def test_nullable_integer_keeps_its_dtype_and_masks_the_hole():
    """The distinction a frame cannot make: a missing integer is still an integer.

    ``pandas`` widens an integer column with one missing value to float. The
    store keeps ``int32`` and records the hole in the validity mask.
    """
    series = pd.array([1, 2, None, 4], dtype="Int32")
    store = store_from_dataframe(pd.DataFrame({"n": series}))
    column = store["n"]
    assert column.dtype == "int32"
    assert column.has_mask()
    assert [column.valid(i) for i in range(4)] == [True, True, False, True]


def test_missing_object_entry_does_not_enter_the_dictionary():
    """A missing text cell is masked, not stored as the literal string "nan"."""
    store = store_from_dataframe(pd.DataFrame({"s": ["a", None, "b"]}))
    column = store["s"]
    assert "nan" not in list(column.dictionary())
    assert column.valid(1) is False


def test_dataframe_round_trip_is_value_exact(frame):
    """Everything but a masked cell survives a trip through the store."""
    back = dataframe_from_store(store_from_dataframe(frame))
    assert list(back.columns) == list(frame.columns)
    pd.testing.assert_series_equal(back["name"], frame["name"], check_dtype=False)
    np.testing.assert_array_equal(back["count"].to_numpy(), frame["count"].to_numpy())
    np.testing.assert_allclose(back["small"].to_numpy(), frame["small"].to_numpy())
    np.testing.assert_array_equal(back["flag"].to_numpy(), frame["flag"].to_numpy())


def test_round_trip_back_to_pandas_is_lossy_in_one_documented_direction():
    """A masked integer becomes a float ``NaN`` — a frame has nowhere else to put it."""
    store = store_from_dataframe(pd.DataFrame({"n": pd.array([1, 2, None], dtype="Int32")}))
    back = dataframe_from_store(store)
    assert back["n"].dtype == np.dtype("float64")
    assert np.isnan(back["n"].to_numpy()[2])


def test_store_from_arrays_rejects_ragged_columns():
    with pytest.raises(ValueError, match="rows"):
        store_from_arrays({"a": [1, 2, 3], "b": [1, 2]})


# ── cell writes ──────────────────────────────────────────────────────────


def test_numeric_cell_writes_through_the_view(frame):
    store = store_from_dataframe(frame)
    assert set_cell(store, 1, 1, 42.5)
    assert store["value"].numpy()[1] == 42.5


def test_float32_cell_write_stays_float32(frame):
    """Writing a cell must not widen the column."""
    store = store_from_dataframe(frame)
    assert set_cell(store, 0, 4, 9.25)
    assert store["small"].dtype == "float32"
    assert store["small"].numpy()[0] == np.float32(9.25)


def test_boolean_cell_write_lands(frame):
    """A boolean column has no writable view, so the write goes the long way round."""
    store = store_from_dataframe(frame)
    assert set_cell(store, 0, 3, False)
    assert list(store["flag"].numpy()) == [False, False, True, False]


def test_text_cell_write_reuses_an_existing_label(frame):
    store = store_from_dataframe(frame)
    assert set_cell(store, 0, 0, "gamma")
    column = store["name"]
    assert column.string_at(0) == "gamma"
    assert list(column.dictionary()) == ["alpha", "beta", "gamma", "delta"]


def test_text_cell_write_appends_a_new_label(frame):
    store = store_from_dataframe(frame)
    assert set_cell(store, 0, 0, "omega")
    column = store["name"]
    assert column.string_at(0) == "omega"
    assert "omega" in list(column.dictionary())


def test_blanking_a_cell_masks_it_instead_of_writing_a_sentinel(frame):
    """The point of the mask: an integer column stays integer and keeps its value."""
    store = store_from_dataframe(frame)
    assert set_cell(store, 2, 2, None)
    column = store["count"]
    assert column.dtype == "int32"
    assert column.valid(2) is False
    # The buffer still holds what it held — "missing" is the mask, not a value.
    assert column.numpy()[2] == 3


def test_clear_then_write_restores_validity(frame):
    store = store_from_dataframe(frame)
    clear_cell(store, 1, 1)
    assert store["value"].valid(1) is False
    set_cell(store, 1, 1, 7.0)
    assert store["value"].valid(1) is True
    assert store["value"].numpy()[1] == 7.0


def test_write_out_of_range_is_refused(frame):
    store = store_from_dataframe(frame)
    assert set_cell(store, 99, 1, 1.0) is False
    assert clear_cell(store, 99, 1) is False


# ── column reads ─────────────────────────────────────────────────────────


def test_column_values_is_zero_copy_when_unmasked(frame):
    """An unmasked numeric column is the store's own buffer, in its own dtype."""
    store = store_from_dataframe(frame)
    values = column_values(store, 4)
    assert values.dtype == np.dtype("float32")
    values[0] = 11.0
    assert store["small"].numpy()[0] == np.float32(11.0)


def test_column_values_reports_a_mask_as_nan(frame):
    """Filters and colour ranges use plain numpy, so a masked cell must read NaN."""
    store = store_from_dataframe(frame)
    clear_cell(store, 1, 2)
    values = column_values(store, 2)
    assert values.dtype == np.dtype("float64")
    assert np.isnan(values[1])
    assert list(values[[0, 2, 3]]) == [1.0, 3.0, 4.0]


def test_column_values_raw_keeps_the_buffer(frame):
    store = store_from_dataframe(frame)
    clear_cell(store, 1, 2)
    raw = column_values(store, 2, masked_as_nan=False)
    assert raw.dtype == np.dtype("int32")
    assert raw[1] == 2


# ── the borrowed-column trap ─────────────────────────────────────────────


def test_a_cached_column_proxy_goes_stale_when_a_column_is_added():
    """Pin the library behaviour this seam exists to route around.

    A ``Column`` is a reference into the store's column vector. Adding another
    column reallocates it and the held proxy reads freed memory — silently, with
    an empty name and no data, rather than raising. If this test ever fails
    because the proxy stayed valid, the library has been fixed and the
    re-fetching in this module is merely belt and braces.
    """
    store = new_store()
    held = store.add("f", np.arange(5, dtype="float64"))
    for i in range(8):
        store.add(f"x{i}", np.arange(5, dtype="float64"))
    assert held.name() == "" or len(held.numpy()) == 0, (
        "the borrowed-column reference survived a reallocation — see the "
        "columnar-store concept and drop this workaround"
    )


def test_column_at_always_answers_with_live_data():
    """The seam's rule — re-fetch — is immune to the reallocation above."""
    store = new_store()
    store.add("f", np.arange(5, dtype="float64"))
    for i in range(8):
        store.add(f"x{i}", np.arange(5, dtype="float64"))
    column = column_at(store, 0)
    assert column.name() == "f"
    np.testing.assert_array_equal(column.numpy(), np.arange(5, dtype="float64"))


# ── helpers ──────────────────────────────────────────────────────────────


def test_is_missing_does_not_treat_an_empty_string_as_missing():
    """A text column's empty label is a value, unlike in pandas."""
    assert is_missing(None)
    assert is_missing(float("nan"))
    assert not is_missing("")
    assert not is_missing(0)
    assert not is_missing(False)
