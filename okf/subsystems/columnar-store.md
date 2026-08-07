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

## The column *data* is borrowed too, and that is the sharper edge

The proxy hazard below is documented and worked around. The **array** has the
same lifetime and is easier to get wrong, because the guard against it is one
word:

* `column_values` returns the column's own buffer for an unmasked numeric
  column — the zero-copy view that is the point of the store;
* `np.asarray(values, dtype=float)` on an already-`float64` array returns **that
  same view**, not a copy. `np.array` copies.

So an array that outlives its store is reading freed memory, and it **does not
raise**: it comes back as denormal garbage. Measured when the burst reader hit
it — 84 of 154 rows of `First Photon` read as `3.3e-319` instead of `2755`, and
a synthetic case reads `[0, 3, 0, 9]` for `[0, 3, 6, 9]`, correct values
alternating with reused memory.

**The rule: anything that outlives its store copies.** Three tests in
`test/test_datastore_seam.py` pin it — that the reader's arrays survive their
store, that `column_values` still *is* a view (so the rule can be relaxed
deliberately if that ever changes rather than assumed away), and that a frame
built from a store survives it, which `read_table_frame` depends on and which
holds only because the frame constructor copies a dict of arrays.

**And it was invisible to a parity test that compared answers.** The check that
should have caught it passed while the columnar reader was never running: a
delimiter sniffer preferring the most frequent character chose the space over
the tab, because burst column names contain spaces, so every file went down the
frame fallback and the test compared pandas against pandas. A parity test over a
seam with a fallback has to **count the fallbacks and assert there were none**,
or it proves nothing.

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

**One number sets the order of everything below.** Reading a 200k-row burst
table costs 541 ms as a frame, **71 ms into a store (7.6×)**, and 485 ms into a
store and back to a frame (**1.1×**). The speed is in *not being a frame*. Every
remaining consumer hands a DataFrame to its caller, so nothing else is worth
migrating until the burst-table layer holds a store.

1. **The burst-table layer**, then its readers, then the plugins —
   `core/fluorescence/burst/table.py` and `photons.py` first, since everything
   else reads them. Each stage deletes its frame conversion rather than keeping
   it beside the store; two containers living side by side is how a second full
   copy of the table appeared in the companion viewer before it was deleted
   again. The writers are done and are **not** the same job: they convert a
   frame at the file boundary, so the frame still exists in memory everywhere.
2. **CSV**, which needs a writer in the library. The reader is already fast and
   without the writer half the migration is a one-way street.
3. **The `.dstore` native file** is worth a look for anything written and read
   only by ChiSurf. It keeps the row selection and the whole tree, needs no
   HDF5 at all, and on a compressed table it is dramatically faster — but it is
   not readable by anything else, so it is wrong for the burst and imaging
   files, which are interchange formats. Measured a wash against uncompressed
   HDF5 on bulk I/O.
4. **A frame is still built before every write.** `write_burst_hdf5` converts
   one at the boundary, so the memory saving in the table above is not being
   collected yet — only the file size and the write time are. That is what
   point 1 is for.

.. seealso::

   [chitable](gui-tables.md) — the table widget family whose fourth adapter this
   store backs.
   [burst companions](burst-companions.md) — the numpy-only contract that is
   deliberately untouched.
