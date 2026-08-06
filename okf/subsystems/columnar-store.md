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
| in memory | 114.3 MB | **60.2 MB** |
| write, numeric only | 0.46 s | **0.08 s** |
| read, numeric only | 0.45 s | **0.02 s** |
| file, numeric only | 64.0 MB | **56.0 MB** |
| file, with the text column | **77.3 MB** | 100.0 MB ← the open gap |

Almost the whole memory difference is the text column: a million Python string
objects against four strings plus a million `int32` codes.

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

## A column proxy is borrowed, and it dangles silently

A `Column` obtained from a store — from `add()`, from `store[i]` — is a
reference into the store's own column vector. **Adding another column
reallocates that vector and every previously handed-out proxy then points at
freed memory.** It does not raise: the stale proxy reports an empty name and an
empty array, so the symptom is a column that silently goes blank.

Never cache a `Column`. `column_at(store, i)` re-fetches, and every accessor in
this seam and in `DataStoreSource` goes through it. The root cause is being
fixed in the library (a container with stable references); the rule stands
regardless, because `remove_column` invalidates references under any container.

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
| the burst-table layer and its readers | not started |
| the HDF5 writers | blocked on the library writing a text column dictionary-encoded (see the table above — today the file goes *past* pandas) |
| the CSV readers | blocked on a writer in the library |

The [burst-companion contract](burst-companions.md) is deliberately untouched:
`burst_companion.write_companion` is numpy-only and stays the canonical writer.

# Known library-side gaps

Found by exercising the store from this seam; each is a real limit rather than a
preference.

| Gap | Consequence here |
|---|---|
| A text column is written to HDF5 with its labels **materialised** | the file is larger than the pandas one it would replace — the single thing blocking the storage-path migration |
| No CSV writer | the reader is fast and the writer would still go through a frame |
| No reader for the legacy frame-written HDF5 layout | files written by earlier releases must stay openable after the HDF5 table dependency goes |
| A `Column` handed out by `add()`/`[i]` **dangles** on the next `add()` | silently blank columns; worked around by never caching a proxy |
| A boolean column has **no zero-copy view**, and decodes through a per-row Python loop | filtering a large boolean column is O(n) in Python, and a write through the returned array is silently lost |
| `mask_numpy()` returns a **copy** | a single-cell mask change is a read-modify-write of the whole mask |
| `set_numpy` on a text column **appends** instead of replacing | a second call doubles the column |
| No `take`/`compact`, `concat`, `argsort`, or group-by over a dictionary column | a selection can be expressed but not *realised*; six plugins would hand-roll the same loop |

A single-cell **text** write was expected to be a gap and is not: it is
expressible over `dictionary()` / `set_dictionary()` / `codes()`, which is what
`set_cell` does. It still belongs in the library eventually, so that every
consumer does not re-derive it.

# Where to pick this up

1. **The text column in HDF5.** Everything downstream is judged on the
   comparison in the table above, and today the store loses it. Re-derive with a
   benchmark that *includes a text column* — numeric-only the store wins by 6×
   on write and 22× on read, and that number flatters.
2. **The burst-table layer**, then its readers, then the plugins. Each stage
   deletes its frame conversion rather than keeping it beside the store; two
   containers living side by side is how a second full copy of the table
   appeared in the companion viewer before it was deleted again.
3. **Compression default.** The library's HDF5 writer defaults to level 4, which
   costs 2.58 s against 0.08 s on a numeric table to save 8% of the file. These
   files are written once per analysis and read repeatedly.

.. seealso::

   [chitable](gui-tables.md) — the table widget family whose fourth adapter this
   store backs.
   [burst companions](burst-companions.md) — the numpy-only contract that is
   deliberately untouched.
