---
type: Concept
title: 'Legacy export: the burst folder and the ALEX-Suite CSVs as views of a container'
description: What the legacy export writes from a .pto container -- the Seidel/Margarita burst folder and the five ALEX-Suite CSVs -- why the folder is merged by position, and what the export loses.
tags: [concepts, bursts, export, legacy, pto]
anchor: concept-legacy-export
---

(concept-legacy-export)=
# Legacy export: the burst folder and the ALEX-Suite CSVs as views of a container

A burst analysis lives in the measurement's `.pto`: one run per analysis, every
result a table joined to the bursts by declared parentage
({ref}`concept-smfret-bursts` for the observables). No workflow tool writes the
old layouts. Older readers -- ndX's folder reader, the Seidel/Margarita software,
ALEX-Suite-era scripts -- need them, so the export is one explicit action:
**File › Data › Legacy Export** (`chisurf/plugins/core/legacy_export/`), the PTO
inspector's *Export legacy*, or the CLI. All three call one writer,
{src}`chisurf/core/fio/fluorescence/legacy_export.py`.

## The burst folder

```text
<out_dir>/
  <run>/bi4_bur/<stem>.bur      one row per burst (the burst table)
  <run>/bv4/<stem>.bv4          one companion per analysis
  <run>/bg4/<stem>.bg4 ...
  <run or stem>/<table>.csv     every other table of the container, as text
```

A burst-table run becomes `bi4_bur/<stem>.bur`. Each per-burst analysis
becomes a **companion** `<ending>/<stem>.<ending>` beside it, with the ending
chosen by the run's `operation_type`:

| operation | ending |
| --- | --- |
| `kde_cde`, `burst_2cde` | `2c4` |
| `burst_variance_analysis` | `bv4` |
| `burst_lifetime_fitting` | `bg4` / `br4` / `by4` (green / red / yellow, from the artifact name) |
| `photon_hmm` | `bh4` |
| `burst_correlation`, `time_delay` | `td4` |
| `burst_fusion` | `bf4` |

Any other operation has no companion and is skipped. Its ending is never
guessed. `burst_selection`, `import`, `calibration` and
`background_correction` are never companions. Every table in the container is
also unpacked as text by `export_tree`. That is where a skipped analysis can
still be read.

A reader merges the folder by concatenating the `.bur` files and adding each
companion **column-wise, by position**. Nothing checks the alignment at read
time: a companion one row short does not fail, it shifts every later burst. So
the writer keeps the companion contract
({src}`chisurf/core/fio/fluorescence/burst_companion.py`, `write_companion`):

1. one file per measurement, named for the `.bur` stem;
2. the directory name ends in `4` (that is how a folder reader discovers it);
3. one row per burst of the measurement, in burst-table order, including bursts
   the analysis skipped;
4. zero-interleaved rows: `2N + 1` physical rows for `N` bursts, data on the odd
   rows;
5. tab-separated, with a trailing tab on the header line;
6. every column numeric and uniquely named.

A result that covers only some bursts (H2MM, burst FCS) is placed by the burst
number its artifact declares (`_mmfdb_edge.source_row_column`). Bursts with no
result get the sentinel row, zeros. A result that cannot be placed (no key, row
count matching no burst table, key outside the burst range) raises
`CompanionError` instead of being written misaligned. When two runs of one
analysis write the same column, the most recent one wins.

The **plan** (`plan_legacy`, shown in the window's table and by
`csc legacy-export plan`) applies the same rules as the writer. One row per
analysis: `run` (the table's name inside its run, e.g. `bi4_bur/m000.bur`),
`container_run` (the run itself, e.g. `burstwise`, empty for a table stored
outside any run), `operation`, and `ending`, the companion it becomes; an
empty ending means skipped.

## The ALEX-Suite CSVs

`export_alex_csvs` writes the files the old ALEX-Suite wrote, sharing one stem.
They are fully quoted CSV with the old section headers
({src}`chisurf/plugins/burst/alex_suite/api/legacy_export.py`):

| file | content |
| --- | --- |
| `<stem>_meta.csv` | blocks `BURST SEARCH PARAMETERS`, `THRESHOLDS`, `EXPERIMENTAL` (sample, buffer, date), `ACCURATE FRET` (backgrounds, α, δ, γ, β), `PLOT OPTIONS` (bins, burst counts) |
| `<stem>_hist_E.csv` | `BIN CENTERS E`, `E HISTOGRAM`, `E FIT`, `E GUESS n` |
| `<stem>_hist_S.csv` | the same for S |
| `<stem>_hist_2D.csv` | `2D HISTOGRAM`, the E–S matrix |
| `<stem>_original_bursts.csv` | `BURSTS`, then the burst table (optional) |

The histograms come from `es_histograms` of the chosen burst table, either a
`.bur` file or a container run (`m000.pto/<run>`). A container path names the
**run**, not the table inside it, so only runs that hold a burst table
(`container_run` of a plan row with ending `bur`) can feed the CSVs; the window
offers exactly those, and `csc legacy-export alex-csvs` takes either form. The export writes default
thresholds and neutral corrections (γ = β = 1, α = δ = 0, zero backgrounds) into
`_meta`, and no fit curves: the `E FIT` and `S FIT` columns are zeros. The same holds for
`csc alex-suite export-legacy` ([ALEX Suite guide](../guides/66_alex_suite.md)).

## A view, not a backup

The legacy layouts hold less than the container:

- **Provenance.** Operation, parameters, parentage and checksums stay in the
  `.pto`. The folder holds bare numbers.
- **Missing values.** A zero in a companion is the export's "skipped". The
  container holds the real NaN, so a true zero and a skipped burst look the same.
- **Text columns.** Non-numeric columns are left out of companions.
- **Run history.** Repeated runs of one analysis collapse to the most recent.
- **Unregistered analyses.** They get no companion, only the text dump.

Keep the `.pto` as the record and export again when a reader needs the old
layout. The way back in, a legacy burstwise folder to `.pto`, is
**Burstwise→PTO** (`chisurf/plugins/burst/burstwise_import/`).

## See also

- Workflow: [Exporting burst data](../guides/34_exporting_burst_data.md).
- The container format: {src}`chisurf/core/fio/pto.py`.
