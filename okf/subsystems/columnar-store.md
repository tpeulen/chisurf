---
type: Subsystem
title: The columnar store — the table container underneath ChiSurf's tables
description: The Qt-free seam that lets a table be held as a typed, masked, dictionary-encoded columnar store instead of a DataFrame — half the memory on a burst table, dtypes and missing values that survive a file, and the container the chitable adapter, the HDF5 writers and the CSV readers are migrating onto.
resource: chisurf/core/datastore.py
tags: [tables, storage, dependencies, burst, hdf5, csv, memory, chitable]
timestamp: '2026-08-06T00:00:00Z'
---

# Why it exists

ChiSurf held every table as a `pandas.DataFrame`. That is a reasonable default
and a poor fit for the tables this application actually has, which are burst
tables: a few million rows, mostly `float32`/`int32`, one or two columns of
short repeated labels, and a per-row notion of *this analysis skipped this
burst*. A frame gets all three of those wrong at once — it widens narrow dtypes,
it stores a repeated label as one Python string object per row, and it can only
say "missing" in a column that is already floating point.

The simulation library's `DataStore` is the same shape as the data: typed
columns in their own dtype, a dictionary-encoded text column, and a per-column
validity **mask**. `chisurf/core/datastore.py` is the seam between the two.

**Measured** on a 1M-row burst table (six `float64`, one `int32`, one `float32`,
one four-label text column), macOS arm64:

| | frame + its HDF5 writer | columnar store |
|---|---|---|
| in memory | 109.5 MB | **60.2 MB** |
| write, numeric only | 0.071 s | **0.025 s** |
| read, numeric only | 0.042 s | **0.011 s** |
| file, numeric only | 64.0 MB | **56.0 MB** |
| write, with the text column | 0.293 s | **0.037 s** |
| read, with the text column | 0.133 s | **0.011 s** |
| file, with the text column | 72.6 MB | **60.0 MB** |

Almost the whole memory difference is the text column: a million Python string
objects against four strings plus a million `int32` codes.

**The text column used to be where this lost**, and it was the one thing
blocking the storage path: the HDF5 writer materialised the labels, so that
file was 96.0 MB against the frame's 72.6 MB. Fixed at the library source — the
dataset is now the `int32` codes and the labels are a `dictionary` attribute on
it, so the file is self-describing and a reader that ignores the attribute
still gets valid category codes. Both older layouts still read (variable-length
and fixed-width strings), and codes that do not index their dictionary are read
as the integers they literally are rather than as a column whose every access
is out of bounds.

**Dropping `pandas` is not the goal and does not follow from any of this.** It
was measured: removing it from the recipe's run list moves the solved closure
256 → 255, and in the dev environment it does not leave at all because another
dependency requires it. pandas stays as the interop format. What is actually
achievable is the memory, the surviving dtypes, and finally making the removal
of the HDF5 table dependency *true* rather than declared.

# What the seam guarantees

## Missing is not NaN

The two containers do not mean the same thing by "missing", and the seam never
silently converts one to the other:

* a frame marks a missing number with `NaN`, which only a float column can hold
  — an integer column with one missing value comes back from pandas as floats;
* a store carries a per-column validity mask, so an integer column says "not
  measured" without giving up a value or its dtype.

That distinction is exactly what a burst analysis that skipped a burst needs,
and it is what the [burst-companion contract](burst-companions.md) currently
encodes with sentinel rows.

`store_from_dataframe` therefore masks rather than widens, and
`dataframe_from_store` turns a masked entry back into `NaN`, widening where it
must. **The round trip is lossy in that one direction**, and it is documented
rather than hidden. Code moved onto a store has to say which of the two it
means: a masked cell is *not* visible to `np.isnan`.

## The column data is a view, and it *used* to dangle

**Fixed in the library on 2026-08-07** — an array from `column_values` now holds
its store alive through its base chain, by every accessor. Kept here because the
defect is instructive and because the *view* part is still true.

What was wrong: no object in the returned array's base chain owned the buffer or
referenced the store, so an array outliving its store read freed memory — and
**did not raise**. Measured when the burst reader hit it: 84 of 154 rows of
`First Photon` read as `3.3e-319` instead of `2755`, and a synthetic case read
`[0, 3, 0, 9]` for `[0, 3, 6, 9]`, correct values alternating with reused memory.
It was intermittent because numpy *collapses* a view-of-a-view to the root, so a
derived array did not even keep the array it came from alive.

**What is still true**: the array is the store's own buffer, so writing through
it writes into the store, and keeping it keeps the *whole* store alive — columns
the caller never asked for included. A reader returning a few columns out of a
wide table therefore still copies, to let the rest go. That is the reason in the
code now; it is no longer a correctness one.

`test/test_datastore_seam.py` pins the guarantee from this side, through every
accessor the fix had to cover. It can no longer fail by accident, which is the
point: a regression in that ownership should surface as a failing test here
rather than as wrong numbers in an analysis.

**The other half of the lesson has nothing to do with lifetimes.** The parity
test that should have caught it passed while the reader it was testing never
ran: a delimiter sniffer preferring the most frequent character chose the space
over the tab, because burst column names contain spaces, so every file went down
the frame fallback and the check compared pandas against pandas. **A parity test
over a seam with a fallback has to count the fallbacks and assert there were
none**, or it proves nothing. That fallback is now gone entirely, which removes
the failure mode as well as the trap.

## A column proxy is borrowed, and it dangles silently

A `Column` obtained from a store — from `add()`, from `store[i]` — is a borrowed
reference into the store's own column container. A structural change can
invalidate it, and **it does not raise**: the stale proxy reports an empty name
and an empty array, so the symptom is a column that silently goes blank.

Appending used to invalidate everything, which was the worse case because it
happens while a table is merely being built. That is fixed at the library source
(the columns now live in a container whose references survive an append) —
measured by holding a proxy across fifty `add()` calls in a scratch build: name,
data and write-through all intact, where the shipped build answers `''` and
`[]`. The fix is **not in any built environment here yet**.

Removal still invalidates, and unevenly: whether a given proxy survives depends
on the index and the container. So *whether* a proxy is still good is not a
contract in either build.

**The rule is therefore unchanged: never cache a `Column`.** `column_at(store, i)`
re-fetches, and every accessor in this seam and in `DataStoreSource` goes
through it. The test asserts the positive invariant — `column_at` answers with
live data across an append *and* a removal — rather than asserting that a stale
proxy breaks, which would be pinning a bug whose presence depends on the build.

## Three routes to write one cell

The library exposes three, and `set_cell` picks by dtype:

* **numeric** — straight through the zero-copy view;
* **boolean** — no writable view exists, so it is a read-modify-write of the
  whole column;
* **text** — dictionary-encoded, so the label is looked up in the dictionary,
  appended when new, and the row's integer *code* is what changes.

Blanking a cell sets the mask bit instead of writing a sentinel.

# Where it is used

| Consumer | State |
|---|---|
| `DataStoreSource` in [chitable](gui-tables.md) | landed — a store backs a table widget, with a text column editing as a drop-down of its dictionary |
| the HDF5 writers | landed — all seven, through `write_table` / `read_table` / `read_table_frame` in this module |
| the CSV writers | landed, the `.bur` burst table included — **45 of 45 real files byte-identical** to the frame writer; only the three companion writers are excluded, and those belong to `write_companion` |
| the burst-table layer and its readers | not started, and it is what everything else is now waiting on |
| the CSV readers | measured and deferred: **7.6× into a store, 1.1× back into a frame** |

`write_table` is the only way a table enters HDF5 in the shipped package now,
and `test/test_pandas_hdf5_seam.py` fails on a frame writer reappearing. Frame
*readers* are allow-listed in `test/pandas_hdf5_read_allowlist.txt` — a
**shrinking** record of the two places that still open the older layout so files
from earlier releases keep working.

The [burst-companion contract](burst-companions.md) is deliberately untouched:
`burst_companion.write_companion` is numpy-only and stays the canonical writer.

# Known library-side gaps

Found by exercising the store from this seam; each is a real limit rather than a
preference.

| Gap | Consequence here |
|---|---|
| ~~A text column is written to HDF5 with its labels materialised~~ | **Closed.** The codes are the dataset and the dictionary is an attribute on it: 96.0 → 60.0 MB, write 0.185 → 0.037 s, read 0.191 → 0.011 s |
| ~~A file holds one table; the writer truncates~~ | **Closed.** A store is a tree of named child groups and the file is its serialisation, which is what the imaging format (`results` plus a `meta` back-reference) needs |
| **No reader for the frame-written layout, and none wanted here** | a library that reads photon data has no business knowing another ecosystem's container layout. Files from earlier releases are opened by `read_table_frame`, which falls back to that ecosystem's own reader and turns a missing optional package into a named `LegacyTableError` rather than an empty table |
| A `Column` handed out by `add()`/`[i]` is **invalidated** by a structural change | silently blank columns; the append case is fixed at the library source but is in no built environment here yet, and removal still invalidates — worked around by never caching a proxy |
| A boolean column has **no zero-copy view**, and decodes through a per-row Python loop | filtering a large boolean column is O(n) in Python, and a write through the returned array is silently lost |
| `mask_numpy()` returns a **copy** | a single-cell mask change is a read-modify-write of the whole mask |
| `set_numpy` on a text column **appends** instead of replacing | a second call doubles the column |
| No `take`/`compact`, `concat`, `argsort`, or group-by over a dictionary column | a selection can be expressed but not *realised*; six plugins would hand-roll the same loop |

A single-cell **text** write was expected to be a gap and is not: it is
expressible over `dictionary()` / `set_dictionary()` / `codes()`, which is what
`set_cell` does. It still belongs in the library eventually, so that every
consumer does not re-derive it.

# Where to pick this up

**The burst-table layer holds a store** (2026-08-07), which was the item
everything else waited on: reading a 200k-row burst table costs 541 ms as a
frame, **71 ms into a store (7.6×)**, and 485 ms into a store and back to a
frame (**1.1×**) — so a consumer that converts back gains nothing, and until the
producer moved, every port was churn. `read_bur_file`,
`read_bur_with_companions`, the `.bur`/HDF5/CSV writers, fusion, BVA, 2CDE, the
burst browser and the MFD preparation are all store-native now, and
`test/pandas_import_allowlist.txt` is **47 → 20**.

1. **The remaining 20 files**, of which seven are interop that should stay.
   `test/pandas_import_allowlist.txt` is the ordered worklist and
   [PRD-82](../prds/prd-82.md) carries it, together with the four idioms that
   fail *silently* when a store arrives where a frame was expected — `columns`
   is the dangerous one, because a store has both `names` and `columns` and its
   `columns` are `Column` objects, so a lookup answers "absent" rather than
   raising. Read that list before porting one.
2. **The `.dstore` native file** is worth a look for anything written and read
   only by ChiSurf. It keeps the row selection and the whole tree, needs no
   HDF5 at all, and on a compressed table it is dramatically faster — but it is
   not readable by anything else, so it is wrong for the burst and imaging
   files, which are interchange formats. Measured a wash against uncompressed
   HDF5 on bulk I/O.
3. **The CSV *reader* is deliberately not migrated.** Same measurement as
   above from the other side: 7.6× into a store, 1.1× into a store and back to
   a frame. It is worth doing for a consumer that has already moved, and worth
   nothing for one that has not — so it follows point 1 rather than leading it.
4. **`write_csv_table` no longer copies the table to write it.** The library's
   `nan_rep` says what a `NaN` is written as, which is a question `na_rep` does
   not answer: `na_rep` covers a cell the *mask* says was never measured, and a
   `NaN` is a value. Before it existed this masked every non-finite entry
   first — and the mask is part of the table, so doing it in place meant
   **writing a table changed it**. Kept here because the shape recurs: any
   formatting choice expressed by editing the table is the same bug.

.. seealso::

   [chitable](gui-tables.md) — the table widget family whose fourth adapter this
   store backs.
   [burst companions](burst-companions.md) — the numpy-only contract that is
   deliberately untouched.
