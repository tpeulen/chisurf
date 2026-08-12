---
type: PRD
prd: "89"
title: "PRD-89: Consume the tttrlib spectroscopy data standard (decay, FCS, PDA, PCH) in ChiSurf"
description: tttrlib PRD-028 defines self-describing .dstore/.pto tables for decay curves, FCS curves, PDA histograms, and PCH. This is the consumer side: ChiSurf reads those tables through the standard read_table vocabulary and feeds them to its fit/analysis GUIs — no private format, no tttrlib-specific glue.
status: Draft
created: 2026-08-08
owner: tpeulen
sibling: tttrlib/okf/prds/PRD-028-spectroscopy-data-standard.md
---

# PRD-89 — Consume the tttrlib spectroscopy data standard in ChiSurf

## Summary

tttrlib PRD-028 defines `.dstore` / `.pto`-mmfdb table schemas for TCSPC decay
curves (VV/VH/VM), FCS correlation curves, PDA histograms, and photon-counting
histograms (PCH). Each table has mmfdb/flrCIF column names, units, grain, and
metadata — self-describing, round-tripping through `.dstore`, HDF5, and `.pto`.

ChiSurf must **consume these tables natively**. Today ChiSurf reads decay data
and FCS curves through private file formats and ad-hoc array passing. After
this PRD, ChiSurf opens a `.pto` or `.dstore` file, reads a `decay_curve` or
`fcs_curve` group through the standard `tttrlib.read_table` vocabulary, and
hands it to the fit/analysis GUI — with zero tttrlib-specific glue for the data
layout.

This is the sibling of tttrlib PRD-028. The producer (tttrlib) defines the
schema; the consumer (ChiSurf) reads it.

## Problem / motivation

### How ChiSurf gets decay data today

ChiSurf loads TCSPC decay curves through its own HDF5 data-frame layer — a
private format with its own column conventions that nothing else reads. A fit
session hardcodes the expected layout (parallel in column 0, perpendicular in
column 1, IRF in a sidecar). The column names, units, and polarisation
convention are tribal knowledge, not metadata a reader can discover.

### What changes

After PRD-028 and this PRD, a decay curve arrives as a `.dstore` table where:

- Column `vv_counts` carries the parallel intensity, column `vh_counts` the
  perpendicular — named, not positional.
- The group metadata says `polarization = "vv_vh"`, `dt = 0.0049`, `n_bins =
  4096`.
- The mmfdb item `_mmfdb_decay_curve.vv_counts` in the column metadata says
  what the column *means* — readable by any tool, not just ChiSurf.

ChiSurf's fit panel reads these columns by name, not by position, and displays
the metadata (bin width, g-factor, fit range) without the user typing it.

## Goals

- ChiSurf opens a `.pto` or `.dstore` file containing `decay_curve`,
  `fcs_curve`, `pda_histogram`, or `pch` groups and reads them through
  `tttrlib.read_table(path, group=...)`.
- The fit/analysis GUIs populate from the column metadata: the polarisation
  channels, the IRF, the bin width, the fit range — all read from the table's
  described columns, not entered by hand.
- ChiSurf can **write** fit results (model curve, residuals) back into the
  same table through `tttrlib.write_table`, appending the `model` and
  `residuals` columns to the existing `decay_curve` group.
- No ChiSurf-specific data format remains for decay, FCS, PDA, or PCH data.
  The `.pto`/`.dstore` tables replace it.
- ndx (the DataFrame editor) can browse these groups and display the curves
  without knowing the schema — because the column metadata tells it what each
  column is.

## Non-goals

- **Redefining ChiSurf's fit models.** The models stay; only the data source
  changes.
- **Breaking existing session files.** Legacy ChiSurf sessions read through a
  compatibility shim that translates the old private format into the new
  table schema on load.
- **The flrCIF dictionary definitions.** Those live in the mmfdb repo; this
  PRD consumes them.

## Part 1 — reading a decay curve

```python
import tttrlib

store = tttrlib.read_table("experiment.pto", group="decay_vv_vh")
vv = store.column_by_name("vv_counts").numpy()
vh = store.column_by_name("vh_counts").numpy()
irf = store.column_by_name("irf").numpy()
dt = float(store.group("meta").column_by_name("dt")[0])
```

The fit panel auto-detects:
- `polarization` in metadata → configures VV/VH or VM mode.
- `fit_start` / `fit_stop` → sets the fit range spinboxes.
- `n_channels` → determines whether anisotropy is available.

## Part 2 — writing fit results back

After a fit, ChiSurf appends the model and residuals:

```python
store.column_by_name("model")[:] = model_curve
store.column_by_name("residuals")[:] = residuals
tttrlib.write_table("experiment.pto", store, group="decay_vv_vh", mode="update")
```

The fit result is now persisted in the same table, with provenance tags
(`_mmfdb_operation.operation_type = "decay_fit"`, settings, hash) set by
tttrlib's provenance system.

## Part 3 — FCS curves

ChiSurf's FCS viewer reads an `fcs_curve` group:

```python
store = tttrlib.read_table("experiment.pto", group="fcs/green_green")
tau = store.column_by_name("correlation_time").numpy()
g  = store.column_by_name("correlation").numpy()
```

Multi-curve measurements (green-green + green-red) are sibling groups under
`fcs/`, enumerated by `table_groups("experiment.pto", group="fcs")`.

## Part 4 — PDA and PCH

PDA histograms and PCH tables are read the same way. ChiSurf's PDA viewer
reads the `pda_histogram` group; the 2D histogram is reconstructed from the
long-format `(s1_count, s2_count, probability)` rows.

## Criteria

1. ChiSurf opens a `.pto` file containing a `decay_curve` group and displays
   the VV/VH decay and IRF in the fit panel without manual configuration.

2. The fit panel reads `polarization`, `dt`, `fit_start`, `fit_stop`,
   `excitation_period`, and `g_factor` from the group metadata and pre-fills
   the corresponding GUI fields.

3. After a fit, ChiSurf writes the model curve and residuals back to the
   same `.pto` table through `write_table(..., mode="update")`.

4. ChiSurf reads an `fcs_curve` group and plots the correlation curve with
   correct time axis units.

5. ChiSurf reads a `pda_histogram` group and displays the 2D histogram.

6. A legacy ChiSurf session file loads through a compatibility shim that maps
   the old private format to the new table schema.

7. No ChiSurf-specific data format code remains for decay, FCS, PDA, or PCH
   data — all I/O goes through `read_table` / `write_table`.

8. ndx can browse a `.pto` containing these groups and display the column
   metadata (mmfdb item, units) without any schema-specific code.
