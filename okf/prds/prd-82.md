---
type: PRD
prd: "82"
title: "PRD-82: The table layer onto tttrlib's DataStore — chitable first, then pandas and pytables out of the storage path"
description: chitable, the burst tables and the HDF5 writers move onto tttrlib's DataStore one adapter at a time. The dependency count is not the argument -- pandas stays installed either way -- the arguments are half the memory, dtypes and missing values that survive a file, and the removal of pytables, which is already broken in a freshly solved environment.
status: in-progress
phase: "stage 1 landed"
resource: chisurf/gui/widgets/chitable/source.py
tags: [prd, chitable, datastore, tttrlib, pandas, pytables, dependencies, burst, hdf5, csv]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

**Stage 1 has landed** (2026-08-06): `chisurf/core/datastore.py` is the Qt-free
seam and `DataStoreSource` is chitable's fourth adapter, with 75 tests green
across `test/test_datastore_seam.py` and `test/gui/test_chitable.py`. The
adapter is asserted equal to `DataFrameSource` cell for cell, and does the three
things a frame cannot: keeps a narrow dtype through an edit, blanks an integer
cell by mask rather than by widening, and edits a text column as a drop-down of
its dictionary. The durable description is the new
[columnar-store concept](../subsystems/columnar-store.md) — **source may not
name this PRD**, so that concept is what the code points at.

Next is **stage 2 (HDF5)**, and it is blocked on **T1** exactly as predicted;
nothing about that has changed. Before starting it, note what stage 1 turned up:

1. **T8 was not a blocker and is off the critical path.** A single-cell text
   write is expressible today over `dictionary()` / `set_dictionary()` /
   `codes()`, which is what `set_cell` does. It still belongs in the library so
   six consumers do not re-derive it, but it blocks nothing.
2. **A borrowed `Column` is not safe to cache — and the append case is now
   fixed at the library source but is in no built environment here.** Every
   stage below wants to fetch columns once and keep them, so every stage meets
   this. Rebuilding the library is what makes the fix real: `pixi run
   build-tttrlib` could not configure on macOS at all until `hdf5` was declared
   for every platform rather than for `win-64`/`linux-64` only, which is why the
   shipped binary was stale. *Removal* still invalidates unevenly, so
   `column_at()` and the never-cache rule stay regardless. Detail in
   [known issues](../references/known-issues.md).
3. **Two smaller library gaps**, both worked around in the seam: a boolean
   column has no zero-copy view (it decodes through a per-row Python loop, and a
   write through the returned array is silently lost), and `mask_numpy()`
   returns a copy.
4. **148 files in the shipped package still name a PRD**, tracked by
   `test/prd_mention_allowlist.txt`. Every file this migration touches gets its
   PRD references ported to the owning concept in the same change.

Two measurements to re-derive before trusting anything here, and the trap in
each:

* **The dependency saving is one package, not a stack.** Solve it, do not assume
  it: `conda create --dry-run --json -c conda-forge -n probe <recipe run: list>`
  with and without `pandas` is 256 → 255. The trap is measuring in the dev env,
  where `pdb2pqr` requires `pandas >=1.0` and it never leaves at all.
* **The HDF5 comparison inverts on a text column.** Numeric-only, tttrlib is
  ~6× faster to write and ~22× faster to read at compression 0; add one
  four-label text column and its file goes *past* pandas (100 MB against 77 MB),
  because the writer materialises the labels. Benchmark with a text column or
  the result is flattering and wrong.

# Summary

`chisurf.gui.widgets.chitable` is already an adapter architecture: the model
knows only `TableSource`, and three adapters (`DataFrameSource`, `ArraySource`,
`RecordSource`) cover everything in the tree. This PRD adds a fourth —
`DataStoreSource` over `tttrlib.DataStore` — and then moves the tables that
feed it, the HDF5 writers and the CSV readers across one at a time, keeping
pandas as an interop and fallback layer rather than as the storage model.

[PRD-79](prd-79.md) already did exactly this for NDXplorer: `pa.Table` became
`DataStore`, `arrow_backend.py` (710 lines) and a second full copy of the table
were deleted, and `pyarrow` went with them. The same container is now proposed
for the ChiSurf side of the same tables.

# Motivation

## The dependency argument is the weakest one, and it should be stated plainly

Measured 2026-08-06 against the recipe's `run:` list: dropping `pandas` moves
the closure **256 → 255**. It is worth exactly itself — `python-dateutil`
belongs to matplotlib and the Jupyter client, `pytz`/`python-tzdata` to `arrow`
— and in the dev environment it would not leave at all, because `pdb2pqr`
requires `pandas >=1.0`. **Removing pandas is not the goal of this PRD** and
should not be used to justify it. What *is* achievable, and worth doing on its
own merits:

* **`pytables` genuinely leaves.** It has already been dropped from every
  dependency declaration ([PRD-80](prd-80.md)), while five live, unguarded
  pandas HDF5 call sites still require it — see
  [known issues](../references/known-issues.md). The current tree works only
  because developer environments still carry the package. This PRD is what makes
  that removal true rather than declared.
* **Half the memory on a burst table.** 1M rows × 9 columns (6 float64, one
  int32, one float32, one four-label text column): **114.3 MB as a DataFrame,
  60.2 MB as a DataStore**. The difference is almost entirely the text column,
  which pandas stores as a million Python string objects and DataStore stores as
  four strings plus a million int32 codes.
* **Types and missing values survive a file.** A float32 column read back as
  float64 is twice the memory for no more information; an integer column with
  one missing value comes back from pandas as floats. DataStore carries a
  per-column bit mask, so "not measured" and "zero" stay different in an integer
  column — which is exactly the distinction a burst analysis that skipped a
  burst needs, and which the
  [burst-companion contract](../subsystems/burst-companions.md) currently
  encodes with sentinel rows.
* **The selection and histogram machinery is already there.** Row masks are part
  of the store, bit-packed, and honoured by a histogram fill; a text column's
  codes are a category axis. Today chitable filters, ndX selections and burst
  gates each rebuild that.

## The surface is much smaller than the file count suggests

80 files import pandas, 31 at module scope — but an AST scan of what is actually
*called* comes to 223 `pd.*` calls and ~130 frame-method calls, concentrated in a
handful of names:

| `pd.*` | n | frame method | n |
|---|---|---|---|
| `DataFrame` | 84 | `to_csv` | 8 |
| `to_numeric` | 52 | `groupby` | 6 |
| `concat` | 26 | `select_dtypes` | 5 |
| `read_csv` | 25 | `itertuples` | 4 |
| `HDFStore` | 11 | `dropna` | 4 |
| `Series` | 7 | `to_hdf` | 3 |
| `Categorical` | 6 | `iterrows` | 3 |
| `read_hdf` | 4 | `reset_index` | 2 |

No pivot, no merge on a real frame, no multi-index, no resample. `DataFrame` is
overwhelmingly *construction from a dict of arrays*, which is `DataStore.add`
per column; `to_numeric` is `astype`; `Categorical` is a dictionary column,
which DataStore has natively.

## chitable is the right entry point

`TableSource` needs five methods (`column_specs`, `row_count`, `value`,
`set_value`, `column_array`). A DataStore answers all five more directly than a
DataFrame does:

* `column_array` is `Column.numpy()` — a **zero-copy view in the column's own
  dtype**, where `DataFrameSource` currently converts to float64 with
  `to_numpy(dtype="float64", na_value=np.nan)`;
* `set_value` writes through that view. Verified against the installed tttrlib
  0.27.0: the numeric view is writable and the write lands in the store;
* `column_specs` reads `ColumnType` directly, which removes this module's
  dependence on `pandas.api.types` — the module docstring records that
  `numpy.issubdtype` raises on pandas extension dtypes and was the root cause of
  a long-standing crash in ndX's table editor. An explicit type enum cannot
  reproduce that class of bug.

Nothing else in chitable changes: `DataFrameSource` stays for callers that hold
a frame, which is what makes this migration piecewise rather than a flag day.

# Proposal

## Stage 1 — `DataStoreSource` (no tttrlib change needed) — **landed**

A fourth adapter in `chisurf/gui/widgets/chitable/source.py`, over a Qt-free
seam in `chisurf/core/datastore.py` that stages 2–4 share (`store_from_dataframe`,
`dataframe_from_store`, `store_from_arrays`, `column_at`, `column_values`,
`set_cell`, `clear_cell`). The conversions live in core rather than in the
widget so that the GUI does not become the seam:

```python
source = DataStoreSource(store, editable=True)     # tttrlib.DataStore
widget = ChiTableWidget(source)
```

* `column_specs` from `ColumnType` (`Float64/Float32` → float, `Int*/UInt*` →
  int, `Bool` → bool, `String` → str, with the dictionary as the delegate's
  choice list — a text column with 4 labels should edit as a combo box, which is
  something no `DataFrameSource` column can offer today).
* `value`/`set_value` through the typed view; masked rows render as the blank a
  NaN renders as now, and clearing a cell sets the mask bit rather than writing
  a sentinel.
* `row_label` is the row position — DataStore has no index concept and does not
  need one; the frames being replaced all carry a `RangeIndex`.

Acceptance for this stage alone: the existing chitable test suite passes against
a `DataStoreSource` built from the same data as its `DataFrameSource` fixtures,
cell for cell. **Met** — the filter, sort, colour-range and filtered-edit tests
are parametrised over both sources, and a dedicated test walks every cell of
both and asserts equality. One design choice worth knowing: a text column edits
as a combo box only while its dictionary is small (`MAX_CHOICE_LABELS = 64`);
beyond that it is free text, because a drop-down of ten thousand burst ids is
not an editor.

## Stage 2 — HDF5: the writers move, and `pytables` is actually gone

Five call sites, all of them writing tables that are already numeric-plus-labels:

| Call site | What it writes |
|---|---|
| `plugins/burst/burst_h2mm/core/export.py:279` | the **ndX-openable** burst export |
| `plugins/burst/bid_to_analysis/__init__.py:317,322,331` | `pd.HDFStore` burst tables |
| `core/fluorescence/imaging/pixel_maps.py:699,703,713,753` | pixel-map store + `add_maps_to_hdf5` |
| `core/fio/fluorescence/burst_states.py:88` | `pd.read_hdf` of a state table |
| `core/fitting/fit.py:2363` | the MCMC chain |

They become `tttrlib.write_hdf5` / `tttrlib.read_hdf5` (one dataset per column).
The reader half is **already wired on the ndX side**:
`ndxplorer/io/reader.py:881` has `read_hdf5_store` on
`tttrlib.read_hdf5_table_columns`, with `pd.read_hdf` as the other branch. This
stage needs **T1** and **T8** below.

## Stage 3 — the burst tables

In dependency order, each independently landable, each with the store built once
and the frame conversion deleted rather than kept alongside:

1. `core/fluorescence/burst/table.py`, `photons.py` — the burst-table layer
   everything else reads;
2. `core/fio/fluorescence/burst.py`, `pqres.py` — the readers;
3. `burst_selection` (15 files — the largest single consumer), `burst_h2mm`
   (10), `burst_2cde`, `burst_bva`, `burst_fusion`, `burst_browser`;
4. `core/fluorescence/mfd/prepare.py`, the two microscopy MLE plugins.

The [burst-companion contract](../subsystems/burst-companions.md) is **not
affected**: `burst_companion.write_companion` is numpy-only and stays the
canonical writer. A store is a better fit for it than a frame, but that is a
follow-up, not a prerequisite.

## Stage 4 — CSV

`pd.read_csv` (25 sites) → `tttrlib.read_csv`, with the same *named limits* ndX
uses (decimal comma, skipped preamble, whitespace alignment fall back to pandas,
declared rather than silently switched). `to_csv` (8 sites) needs **T2**.

## Non-goals

* **Removing pandas.** It stays as an interop layer (`to_dataframe` /
  `from_dataframe` on the seam) and as the documented fallback for files
  `tttrlib.read_csv` declines. Anything that reports to a user, or that a user
  pastes into a notebook, may keep returning a frame.
* **Migrating `chisurf/core/roi/props.py`,`structure/topology.py` and the
  acquisition reader**, whose pandas use is a docstring example, one export and
  one optional import respectively. They are not in the storage path.

# What tttrlib needs

Ordered by what blocks the most. T1–T3 are required for stages 2–4; T4–T7 are
required to finish stage 3 without hand-rolling the same loop in six plugins.

| id | What | Why, with the measurement where there is one |
|---|---|---|
| **T1** | **String columns round-trip dictionary-encoded through HDF5** | The one place the current writer loses. Numeric-only, tttrlib writes 56 MB in 0.08 s and reads it in 0.02 s against pandas' 64 MB / 0.46 s / 0.45 s. Add one four-label text column and the file goes to **100 MB against pandas' 77 MB** — the labels are materialised. Writing the dictionary plus an int32 code array is ~4 MB for that column instead of ~44 MB. |
| **T2** | **`write_csv`** | 8 call sites, and without it stage 4 is half a migration: the reader is fast and the writer still goes through a frame. |
| **T3** | **A reader for the legacy pandas HDF5 layout** | Files already written with `format="table"` must stay openable *without* pytables, otherwise the removal breaks existing user data. tttrlib already links HDF5, so this belongs beside `hdf5_table` rather than in chisurf. |
| **T4** | **`take` / `compact`** — materialise the selected rows into a new store | `dropna` (4), filtered exports and every burst-selection write. Today a selection is a mask and there is no way to *realise* it. |
| **T5** | **`concat` / row append** | `pd.concat` is 26 call sites, the second-largest `pd.*` name after the constructor. |
| **T6** | **`argsort` / sort by column** | Table sorting; chitable currently sorts through the proxy on a numpy array per column, which is fine for one column and not for a stable multi-column sort. |
| **T7** | **Group-by aggregation over a dictionary column** | 6 call sites. Most of it is `codes` + `np.bincount`, which is *why* it belongs in the library: every consumer writing that loop by hand is how the codes get copied. |
| ~~T8~~ | ~~Single-cell string write~~ | **Not a gap.** Expressible over `dictionary()` / `set_dictionary()` / `codes()`, which is what `set_cell` does. Worth having in the library so six consumers do not re-derive it; blocks nothing. |
| T9 | `describe`-shaped summary | `profile()` already covers most of it; listed so it is not rediscovered as missing. |
| ~~T10~~ | ~~A `Column` reference that survives `add()`~~ | **Fixed at the library source** (a stable-reference container in `modules/core/include/DataStore.h`), verified in a scratch build: a proxy survives fifty `add()` calls where the shipped build answers `''` and `[]`. **Not in any built environment here yet**, and *removal* still invalidates unevenly, so the never-cache rule and `column_at()` stay. |
| T11 | A zero-copy view for a **boolean** column | Today `numpy()` decodes it through a per-row Python loop, so filtering a large boolean column is O(n) in Python — and the array it returns is a *copy*, so a write through it is silently lost. |
| T12 | `mask_numpy()` as a view rather than a copy | A single-cell mask change is currently a read-modify-write of the whole mask. Also: `set_numpy` on a text column **appends** instead of replacing, so a second call doubles it. |

**Compression default is worth a look while T1 is open**: `write_hdf5` defaults
to compression level 4, which costs **2.58 s against 0.08 s** on a numeric table
to save 8% of the file. A default of 0 with an explicit opt-in matches how these
files are used (written once per analysis, read repeatedly).

# Measurements

1M rows × 9 columns (6 float64, int32, float32, one text column of 4 labels),
macOS arm64, tttrlib 0.27.0, pandas 2.3.3, pytables 3.7.0:

| | pandas + pytables | tttrlib DataStore |
|---|---|---|
| in-memory | 114.3 MB | **60.2 MB** |
| write, numeric only | 0.46 s (`fixed`) / 2.35 s (`table`) | **0.08 s** (compression 0) |
| read, numeric only | 0.45 s | **0.02 s** |
| file, numeric only | 64.0 MB | **56.0 MB** (51.4 MB at level 4) |
| write, with text | 0.56 s / 1.23 s | 0.34 s |
| read, with text | 0.71 s | 0.40 s |
| file, with text | **77.3 MB** | 100.0 MB ← T1 |

Reproduce with the script pattern in the scratchpad note in
[build-and-env](../workflows/build-and-env.md); it must include a text column.

# Acceptance criteria

1. `DataStoreSource` passes the chitable suite cell-for-cell against the
   `DataFrameSource` fixtures, including editing, filtering, sorting and colour
   ranges, and a text column edits through a dictionary-backed delegate.
2. `import tables` is required by nothing in the tree, and a guardrail test
   fails on a `to_hdf`/`read_hdf`/`HDFStore` call reappearing — the same shape of
   test `pyarrow` needed.
3. A burst HDF5 file written by ChiSurf opens in ndX, and a file written by the
   *previous* release still opens in this one (T3).
4. A burst table with a text column is **smaller** on disk than the pandas file
   it replaces, not merely faster (T1).
5. `pandas` remains importable and declared; no code path silently switches
   between two engines — every fallback is a named, tested decline.
6. End-to-end burst analysis, selection and export are no slower than today,
   measured on a real burst folder rather than a synthetic table.

# Risks

* **A file format that another tool reads.** The h2mm export is an interchange
  contract with ndX, not an internal cache. T3 and criterion 3 exist for this;
  the migration must not land before both.
* **Two containers in the tree at once.** Deliberate and temporary, but it is how
  a "second full copy of the table" appeared in ndX before PRD-79 deleted it. The
  rule for each stage: the conversion is *deleted*, not kept beside the store.
* **The pandas fallback becoming a silent path.** ndX's experience is the
  precedent — declining a file explicitly is a limit; falling back quietly is a
  bug that shows up as "the same file loads differently on two machines".
* **Nullability semantics differ.** A masked DataStore cell and a `NaN` in a
  float column are not the same thing, and code that tests `np.isnan` will not
  see the mask. Anything moved has to say which it means.
* **This is a many-session migration.** It is staged so that stopping after any
  stage leaves the tree consistent; a stage that cannot be finished should be
  reverted rather than left half-applied.

.. seealso::

   [PRD-79](prd-79.md) — the same container replacing pyarrow in ndX, including
   the threaded CSV reader this PRD's stage 4 depends on.
   [PRD-80](prd-80.md) — the pytables removal this PRD completes.
   [known issues](../references/known-issues.md) — the five HDF5 call sites that
   are broken in a freshly solved environment today.
   [burst companions](../subsystems/burst-companions.md) — the numpy-only
   contract that is deliberately untouched.
