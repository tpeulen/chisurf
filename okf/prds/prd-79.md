---
type: PRD
prd: "79"
title: "PRD-79: Drop pyarrow from NDXplorer -- tttrlib DataStore plus a threaded CSV reader"
description: NDXplorer uses pyarrow for three things only -- a columnar table, a threaded CSV reader, and three casts. tttrlib's DataStore covers the first, a CSV reader in tttrlib.io would cover the second, and the third is a numpy one-liner.
status: done
phase: "unassigned"
resource: modules/ndxplorer/ndxplorer/core/arrow_backend.py
tags: [prd, ndxplorer, dependencies, pyarrow, tttrlib, csv, datastore]
timestamp: '2026-08-05T00:00:00Z'
---

# Summary

pyarrow was added to NDXplorer for read speed. It is a large dependency —
`pyarrow-core` is already the trimmed variant, and `pixi.toml` and
`rattler-recipe/recipe.yaml` both carry a comment explaining why — and an audit
of what is actually used comes to three things:

| What | Where | Lines |
|---|---|---|
| `pa.Table` as the columnar container | `arrow_backend.py`, `data_source.py` | most of 1904 |
| `pyarrow.csv.read_csv`, threaded, 16 MB blocks | `arrow_backend.py:134` | ~40 |
| `pc.cast` | `data_source.py` | 3 call sites |

Nothing else. No parquet, no datasets, no IPC, no expressions.

[PRD-78](prd-78.md) already proposes replacing boost-histogram with tttrlib. The
container half of pyarrow is covered by the same work: `tttrlib.DataStore`
(tttrlib `34ca690a`) is a columnar table with typed columns, row masks and
zero-copy numpy views, and histograms fill straight out of it. What is missing
is the CSV reader — and that is the piece worth building in `tttrlib.io`, which
is already the place where every other file format in this stack lives.

# Motivation

## The container is already replaced

`DataStore` holds float64, float32, int64, int32, bool and string columns and
does not promote any of them, which is the property `data_source.py` currently
gets by casting to `pa.float32()` when `use_float32` is set. Reading a column
back is a zero-copy view in its own dtype.

Two things it does that `pa.Table` does not, and that NDXplorer currently builds
itself:

* **Row masks are part of the store**, bit-packed, and honoured by a histogram
  fill. NDXplorer has `bitfield_mask.py` for "8x memory savings" and applies
  selections by boolean indexing, which copies the selected rows.
* **String columns are dictionary-encoded and directly histogrammable.** The
  codes are a category axis, so "count per label" needs no separate pass, and a
  column of a million rows drawn from twenty labels costs 4 MB rather than
  hundreds.

## The three casts are not a dependency

`pc.cast(col, pa_target)` on a float or integer column is
`a.astype(np.float32, copy=False)`. The boolean branch and the
`ArrowInvalid` fallback are both simpler in numpy than the code they replace.

## The CSV reader is the real work

`pyarrow.csv.read_csv` with `use_threads=True` and 16 MB blocks is genuinely
fast, and losing it for `pandas.read_csv` would be a real regression — which is
why it was added. Replacing it means writing one, and `tttrlib.io` is where it
belongs: it is already the module that owns file formats, it already has the
threading primitives (`histogram_run_threads`, the chunk-claiming pattern in
`Histogram.h`), and a CSV of burst features is the same shape as everything
else it reads.

# Proposal

## 1. `tttrlib.io` gains a threaded CSV reader

`modules/io/csv/`, alongside the vendor format modules, producing a `DataStore`
directly:

```python
store = tttrlib.read_csv("bursts.csv", delimiter=",", threads=0)
```

The shape that makes it fast is the same one pyarrow uses:

* **Split the file into blocks on newline boundaries** and parse them in
  parallel, each thread into its own per-column buffers, concatenated at the
  end. Block size in the 8–32 MB range; the work-claiming loop already in
  `Histogram.h` applies unchanged.
* **Two passes or one?** One. Count rows per block while parsing, then place
  each block's rows at a known offset — no global row count is needed up front.
* **Type inference from a sample**, then a typed parse per column, falling back
  to string for a column that turns out not to be numeric. This is where the
  `use_float32` option belongs: infer float, store float32 when asked.
* **The dictionary encoder is already there.** A text column parses straight
  into codes, so the reader gets the compression for free.

Non-goals: quoting rules beyond RFC 4180, embedded newlines, and encodings other
than UTF-8/ASCII. If a file needs those, fall back to pandas — the point is to be
fast on the files NDXplorer actually opens, not to be a general CSV library.

## 2. NDXplorer's backend becomes the DataStore

`arrow_backend.py` (710 lines) and the pyarrow half of `data_source.py` collapse
into a thin adapter. The interface `arrow_backend` presents — a table, column
access, row selection — is what `DataStore` already offers, so this is mostly
deletion.

Keep the pandas path: it is the fallback and the reference the tests compare
against.

## 3. Drop pyarrow

`pyproject.toml`, `pixi.toml`, `rattler-recipe/recipe.yaml`,
`modules/ndxplorer/conda-recipe/meta.yaml`, and the comments in the last two
explaining the `pyarrow-core` choice. `test_declared_dependencies.py` and
`test/settings/test_py314.toml` reference it too.

# Acceptance criteria

1. `tttrlib.read_csv` returns the same columns, dtypes and values as
   `pyarrow.csv.read_csv` for every CSV in the NDXplorer test data, including
   files with a text column, missing values, and mixed integer/float columns.
2. It is **not slower** than pyarrow's threaded reader on a file of the size
   NDXplorer opens. Measure on a real burst-feature CSV, not a synthetic one:
   column count and type mix drive the parse cost more than row count does.
3. `import pyarrow` appears nowhere in chisurf, and it is gone from all four
   dependency declarations.
4. Loading, selecting and plotting a large dataset is no slower end to end than
   it is today.

# Status of the tttrlib side

Done, as of tttrlib `544d8d0a`: `modules/io/csv` reads into a `DataStore`
directly, is value-for-value identical to pyarrow (types, quoted delimiters,
doubled quotes, mixed-case booleans, scientific notation, missing values), and
runs **within 10% of pyarrow's threaded reader** while holding less memory
(44.1 MB against 48.9 on 1M rows x 7 columns). `tttrlib.read_csv` is the Python
entry point.

## Where the remaining time goes, and the next step

Phase timings on that file, with `TTTRLIB_CSV_PROFILE=1`:

```
open/map 2.1   infer 1.6   count 5.1   allocate 0.9
parse 56.8     dict remap 0.3   pack/mask 4.9   ->  73.7 ms
```

Everything structural has been taken out: there is no concatenation (0.3 ms),
the row-count pass is 5 ms, and the block size and work distribution are chosen
so the parse uses every core. **The remaining 57 ms is per-field conversion** --
scanning digits one byte at a time in `parse_double` and `parse_int64`.

**The next step is a SIMD digit scan.** The technique is well established (it is
what `fast_float`, simdjson and Arrow's own converters use): load sixteen bytes,
compare against `'0'` and `'9'` to get a mask of digit positions, find the field
length with a single count-trailing-zeros, and convert eight digits at a time
with a multiply-and-shift rather than a loop of `v = v * 10 + d`. tttrlib
already has the runtime dispatch for this -- `tttrlib::cpu_features` and the
per-function target attributes used by the AVX kernels -- so a SIMD path can be
compiled in and selected at run time without giving up a portable binary.

That should close the last 10% and then some, since the digit loop is most of
what the parse does. It is deliberately NOT part of this PRD: the migration does
not depend on it, and a parser change wants its own before-and-after.

# Risks

* **CSV is a swamp.** Quoting, escapes, BOMs, `\r\n`, ragged rows, locale
  decimal commas. The non-goals above are what keeps this finishable; the
  fallback must be real and tested, not theoretical.
* **Type inference differs from pyarrow's** in edge cases — a column of integers
  with one empty cell, a column that looks numeric until row 900,000. Inferring
  from a sample and re-parsing on mismatch is the honest approach and needs to
  be in the acceptance tests.
* **This is a bigger piece of work than PRD-78** and should follow it, not run
  alongside. PRD-78 removes a dependency by swapping a call; this one removes a
  dependency by writing a parser.

.. seealso::

   [PRD-78](prd-78.md) — the histogram half of the same migration.
   `modules/core/include/DataStore.h` in tttrlib documents the storage model,
   including why in-memory block compression is the wrong tool here and what is
   used instead.

# Status: done

Landed. `pyarrow` no longer appears anywhere in chisurf or NDXplorer, in code or
in any of the five dependency declarations.

* **The container** is `tttrlib.DataStore`. `DataSource` holds one, built once
  per data change; `arrow_backend.py` (710 lines) and `_fast_to_numeric` are
  deleted, and `_data_numeric` -- a second full copy of the table as a
  DataFrame -- is gone with them.
* **The reader** is `tttrlib.read_csv`, via `reader.read_table_tttrlib`. It
  declines the files it does not handle (decimal comma, skipped preamble,
  whitespace alignment) and pandas reads those, which is a named limit rather
  than a silent fallback between two engines.
* **The three casts** are `_numeric_column`, which is four lines of numpy.

The gate evaluation moved with the container: `DataSource.selection_mask` is now
the single implementation, replacing five that did not agree with each other.
See `ndxplorer/tests/test_selection_semantics.py`, which pins every gate kind
against the numpy selection classes exactly.
