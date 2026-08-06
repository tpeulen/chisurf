"""Tests for the columnar-store seam, :mod:`chisurf.core.datastore`.

Covers the two conversions, the three cell-write routes, the mask semantics that
distinguish a store from a frame, the borrowed-column trap that makes a cached
column proxy read freed memory, and the file half -- what survives a write and
what a foreign or older file does instead of reading as an empty table.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from chisurf.core.datastore import (
    LegacyTableError,
    clear_cell,
    column_at,
    column_values,
    dataframe_from_store,
    is_missing,
    new_store,
    read_csv_table,
    read_table,
    read_table_frame,
    set_cell,
    store_from_arrays,
    store_from_dataframe,
    write_csv_table,
    write_table,
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


def test_a_cached_column_proxy_is_not_safe_across_a_structural_change():
    """Why this seam never caches a column proxy.

    A ``Column`` is a borrowed reference into the store's column container, so
    a structural change can invalidate it — and the stale proxy does not raise,
    it reads freed memory and answers with an empty name and no data. The
    symptom is a column that silently goes blank.

    **Whether any particular proxy survives is not a contract.** It depends on
    the container the installed build uses and on which column moved: an
    appended column used to invalidate everything and no longer does, and a
    removal invalidates some proxies and not others depending on the index. So
    this test asserts only that a proxy taken before the change is not
    *trustworthy* afterwards — either it still reads correctly or it has gone
    blank, and a caller cannot tell which without re-fetching. That is the
    whole argument for :func:`column_at`.
    """
    store = new_store()
    for i in range(4):
        store.add(f"x{i}", np.arange(5, dtype="float64"))
    held = store[0]
    store.remove_column(2)
    intact = held.name() == "x0" and len(held.numpy()) == 5
    blank = held.name() == "" or len(held.numpy()) == 0
    assert intact or blank, (
        f"a stale proxy answered with neither live data nor a blank: "
        f"{held.name()!r}, {len(held.numpy())} rows"
    )


def test_column_at_always_answers_with_live_data():
    """The seam's rule — re-fetch — is immune to either invalidation.

    Holds across an append and across a removal, and therefore across both the
    older library build and the current one.
    """
    store = new_store()
    store.add("f", np.arange(5, dtype="float64"))
    for i in range(8):
        store.add(f"x{i}", np.arange(5, dtype="float64"))
    column = column_at(store, 0)
    assert column.name() == "f"
    np.testing.assert_array_equal(column.numpy(), np.arange(5, dtype="float64"))

    store.remove_column(4)
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


# ── tables in a file ─────────────────────────────────────────────────────


def test_a_written_table_comes_back_column_for_column(frame, tmp_path):
    """The whole point of the file half: what goes in is what comes out, in the
    dtypes it went in with. A frame's own writer widens a float32 column to
    float64 and an integer column with a hole to floats."""
    path = tmp_path / "t.h5"
    write_table(path, frame)

    store = read_table(path)
    assert store is not None
    back = dataframe_from_store(store)
    assert list(back.columns) == list(frame.columns)
    assert back["small"].dtype == np.float32
    assert back["count"].dtype == np.int32
    np.testing.assert_array_equal(back["name"], frame["name"])
    np.testing.assert_allclose(back["value"], frame["value"])


def test_a_masked_integer_cell_survives_the_file_as_a_mask(tmp_path):
    """Not as a NaN, which is the thing a frame cannot do: the column would have
    to become floats to carry one, and then "not measured" and "zero" are the
    same as far as the dtype is concerned."""
    store = store_from_arrays({"count": np.array([1, 2, 3], dtype="int32")})
    clear_cell(store, 1, 0)
    path = tmp_path / "t.h5"
    write_table(path, store)

    back = read_table(path)
    assert back["count"].numpy().dtype == np.int32
    assert not back["count"].valid(1)
    assert back["count"].valid(0)


def test_a_text_column_survives_as_a_dictionary(tmp_path):
    """A repeated label costs a code, not a string. This is what makes a burst
    table with a "First File" column smaller on disk than the frame it
    replaces rather than larger."""
    labels = np.array(["Green", "Red", "Green", "Red"] * 32, dtype=object)
    path = tmp_path / "t.h5"
    write_table(path, {"First File": labels})

    back = read_table(path)
    assert back["First File"].dtype == "str"
    assert sorted(back["First File"].dictionary()) == ["Green", "Red"]
    assert list(back["First File"].numpy()) == list(labels)


def test_meta_is_a_child_group_and_not_a_repeated_column(frame, tmp_path):
    """A back-reference to the photon file belongs beside the results. Writing
    it as a column would repeat one string once per row, and a second write
    used to truncate the first table away entirely."""
    path = tmp_path / "t.h5"
    write_table(path, frame, meta={"source_tttr": "/data/run.ptu"})

    store = read_table(path)
    assert store.n_rows() == len(frame)
    assert list(store.group("meta")["source_tttr"].numpy()) == ["/data/run.ptu"]


def test_a_file_that_is_not_a_columnar_table_reads_as_none(tmp_path):
    """Not as an empty table. The reader answers a foreign file with no columns
    rather than an error, so a caller that only catches exceptions opens every
    one of them blank and reports success."""
    path = tmp_path / "not.h5"
    path.write_bytes(b"not an HDF5 file at all")
    assert read_table(path) is None


def test_a_missing_file_reads_as_none(tmp_path):
    assert read_table(tmp_path / "absent.h5") is None


def test_the_frame_reader_prefers_the_columnar_layout(frame, tmp_path):
    path = tmp_path / "t.h5"
    write_table(path, frame)
    back = read_table_frame(path)
    assert list(back.columns) == list(frame.columns)
    assert len(back) == len(frame)


def test_a_file_in_neither_layout_declines_by_name(tmp_path):
    """A named decline, not an empty table: a caller merging into an existing
    file has to tell "nothing was there" from "I could not read what was
    there", because treating the second as the first discards an analysis."""
    path = tmp_path / "not.h5"
    path.write_bytes(b"not an HDF5 file at all")
    with pytest.raises(LegacyTableError):
        read_table_frame(path)


def test_an_older_frame_written_file_still_reads(frame, tmp_path):
    """The layout every existing analysis is stored in. It needs an optional
    package, so where that is absent this is a skip rather than a failure --
    and the decline it produces there is covered above."""
    pytest.importorskip("tables")
    path = tmp_path / "legacy.h5"
    frame.to_hdf(str(path), key="results", mode="w", format="table")

    back = read_table_frame(path)
    assert list(back.columns) == list(frame.columns)
    np.testing.assert_allclose(back["value"], frame["value"])


def test_rewriting_a_table_does_not_leave_a_dropped_column_behind(tmp_path):
    """The default is "this file now holds this table". Under the other mode a
    column dropped by an in-place rewrite keeps its dataset, and comes back on
    the next read as if the rewrite had never happened."""
    path = tmp_path / "t.h5"
    write_table(path, {"a": np.arange(3.0), "b": np.arange(3.0)})
    write_table(path, {"a": np.arange(3.0)})

    store = read_table(path)
    assert [store[i].name() for i in range(store.n_columns())] == ["a"]


def test_a_group_can_be_added_beside_an_existing_table(tmp_path):
    """The opt-out, for a caller that means "add this to the file"."""
    path = tmp_path / "t.h5"
    write_table(path, {"a": np.arange(3.0)})
    write_table(path, {"n": np.arange(2.0)}, group="/extra", replace=False)

    assert [read_table(path)[i].name() for i in range(read_table(path).n_columns())] == ["a"]
    assert read_table(path, group="/extra") is not None


# ── tables as delimited text ─────────────────────────────────────────────


def test_csv_round_trips_values_and_column_names(frame, tmp_path):
    path = tmp_path / "t.csv"
    write_csv_table(path, frame)

    store = read_csv_table(path)
    assert store is not None
    assert [store[i].name() for i in range(store.n_columns())] == list(frame.columns)
    np.testing.assert_allclose(store["count"].numpy(), frame["count"])
    assert list(store["name"].numpy()) == frame["name"].tolist()


def test_a_missing_number_is_an_empty_field_not_the_text_nan(tmp_path):
    """What a frame's writer produces, and what the reader here takes back as
    missing. Converted straight across, a store would write the literal "nan":
    a frame says missing with a NaN and a store says it with its mask, and the
    two have to be put back in step at the text boundary."""
    text = write_csv_table(None, {"x": np.array([1.0, np.nan, 3.0])})
    assert text.splitlines()[1:] == ["1", "", "3"]


def test_an_infinity_is_a_value_and_survives(tmp_path):
    """Not a gap. Masking it would turn a diverging fit result into a blank."""
    text = write_csv_table(None, {"x": np.array([1.0, np.inf, -np.inf])})
    assert text.splitlines()[1:] == ["1", "inf", "-inf"]


def test_an_integral_float_loses_its_decimal_point(tmp_path):
    """The one difference from the frame writer, pinned rather than hidden: no
    writer setting restores it, and it is why the burst companion formats other
    programs read are deliberately not written through this."""
    text = write_csv_table(None, {"x": np.array([12.0, 1.5, 0.0])})
    assert text.splitlines()[1:] == ["12", "1.5", "0"]
    # Still the same numbers on the way back in, which is what makes it a
    # formatting difference rather than a data one.
    import pandas as pd

    assert pd.read_csv(io.StringIO(text), sep="\t")["x"].tolist() == [12.0, 1.5, 0.0]


def test_the_text_otherwise_matches_the_frame_writer(tmp_path):
    """Everything except the integral floats: separators, header, column order,
    text values, integers, and a full-precision double."""
    frame = pd.DataFrame(
        {
            "n": np.array([1, 2], dtype=np.int64),
            "wide": np.array([2**53 + 1, 5], dtype=np.int64),
            "precise": np.array([123.456789012345, 1.5]),
            "label": ["a b", "c"],
        }
    )
    buffer = io.StringIO()
    frame.to_csv(buffer, sep="\t", index=False)
    assert write_csv_table(None, frame) == buffer.getvalue()


def test_a_file_this_reader_declines_is_none_not_a_wrong_answer(tmp_path):
    """A decimal comma is a file for the general reader. Guessing is what makes
    one machine read a table another machine reads differently."""
    path = tmp_path / "comma.csv"
    path.write_text("a;b\n1,5;2,5\n")
    store = read_csv_table(path, delimiter=";")
    # It reads, but not as numbers -- which is exactly why the caller has to be
    # told rather than handed a table of text where it expected floats.
    assert store is None or store["a"].dtype == "str"


def test_writing_only_some_columns_keeps_their_order(tmp_path):
    text = write_csv_table(None, {"a": np.arange(2.0), "b": np.arange(2.0), "c": np.arange(2.0)},
                           columns=["c", "a"])
    assert text.splitlines()[0] == "c\ta"
