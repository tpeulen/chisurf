---
type: Guide
title: Exporting burst data
description: Analysed bursts are exported for downstream visualisation, sharing, or use in other tools.
tags: [guides, bursts, exporting, burst, data]
---

# Exporting burst data

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the per-burst observables that make up the
exported columns.
:::

## What it does

Analysed bursts are exported for downstream visualisation, sharing, or use in
other tools. Three levels are common:

- the **burst table** — one row per burst with its observables (size, duration,
  E, S, lifetime, 2CDE, …);
- the **per-photon data** of the selected bursts (timestamps, micro-times,
  channels), for re-analysis or custom correlation;
- the **burst timestamps** alone (start/stop macro times), e.g. for external
  correlators.

## In ChiSurf

Every burst step writes its result as a **run into the measurement's `.pto`**:
the burst search, BVA, 2CDE, the lifetime fits, H2MM, burst FCS, fusion. Nothing
writes a `bv4/`, `2c4/`, `bh4/` … companion folder any more. The one folder still
written is the burst search's own on a vendor file (`.spc`, `.ptu`, …), which has
no container to hold it: `<search>/bi4_bur/<stem>.bur` beside the file (Burst
Selection says so under **Output**); the later steps then write into a `.pto`
beside each measurement. When an older tool
(ndX's folder reader, the Seidel/Margarita software) needs the folder layout, you
ask for it once, explicitly:

- in the **PTO inspector**: open the container, press **Export legacy…** and
  choose a folder;
- on the command line: `csc csg_pto_inspect export-legacy m000.pto out_folder`;
- in Python: `chisurf.core.fio.fluorescence.legacy_export.export_legacy(container, out_dir)`.

The export writes `bi4_bur/<stem>.bur` for each burst run and, beside it, one
`<ending>4/<stem>.<ending>` companion per analysis (`bv4`, `2c4`, `bg4`/`br4`/`by4`,
`bh4`, `td4`, `bf4`) with **one row per burst of the measurement** — a burst the
analysis skipped is a row of zeros, never a missing row, because the folder is
merged by position. A result that covers only some bursts (H2MM, burst FCS) is
placed by the burst number its table declares; one that cannot be placed is refused
rather than guessed. A zero in a companion is therefore the export's "skipped";
the container still holds the real value.

The door swings both ways: **Burstwise→PTO** (`chisurf/plugins/burst/burstwise_import/`,
**File → Data**) reads a legacy burstwise folder back in — `bi4_bur/` (or `bur/`),
the `…4` companions, `BIDs/`, `Info/` and the `.mti` list — and writes one `.pto`
container per measurement, its columns carried under their flrCIF dictionary
names, with any column the dictionary cannot place named in the report instead of
silently renamed. Each stem's raw TTTR file is found beside the folder or through
the paths the `.mti` records, with an old drive or server prefix rewritten to a
local root; by default the container references that file beside it rather than
embedding it (the deposition layout), and **Dry run** reports every container it
would write before writing one. Without a window, `csc burstwise_import --help`
lists the same conversion.

The **Runs** table in Burst Selection and H2MM lists the analyses in a container;
pick one and the next step reads that run. **Decay from selected bursts** (Burst
Selection) pools the micro times of the bursts inside the histogram range of the
chosen run into one TCSPC decay, stores it beside that run and offers it to the
TCSPC fit window; the histogram sums to the selected photon count.

The workflow tables are plain tables, so any other format is a one-liner. The H2MM
export is designed to open directly in **ndxplorer**:

```python
# burst table -> CSV (the burst table is a column store, not a pandas frame)
from chisurf.core.datastore import write_csv_table
from chisurf.core.fluorescence.burst.photons import load_bur_dataframe
bursts = load_bur_dataframe(["burstwise_All 0.1000#15/bi4_bur/m000.bur"])
write_csv_table("bursts.csv", bursts, delimiter=",")

# per-burst H2MM export: a per-photon HDF5 + a per-burst CSV with the ndX
# FRET-line columns ("Mean Microtime (green)", "Proximity ratio", ...), from the
# engine's photon data, its Viterbi path and the state efficiencies
# (`data, meta, path, fret` as in burst_h2mm/examples/H2MM_01_Simulated_smFRET.ipynb)
from chisurf.plugins.burst.burst_h2mm.core import export
tables = export.build_tables(data, meta, path, fret, base_time_s=1e-6,
                             stream_groups=[("green", (0, 8)), ("red", (1, 9))])
export.write_hdf5(tables.photons, "h2mm/h2mm_photons.h5")
export.write_csv(tables.bursts, "h2mm/h2mm_bursts.csv")

# per-photon data of the selected bursts ([first, last] index pairs, guide 33)
import numpy as np
sel = np.concatenate([np.arange(s, e + 1) for s, e in burst_bounds])
photons = dict(macro=macro[sel], micro=micro[sel], channel=route[sel])
```

The `bid_to_analysis` helper converts external Burst-ID files into a ChiSurf
burstwise analysis folder (BUR/Info/MTI, optional HDF5/SL5) and back, for
interoperability with companion multiparameter-fluorescence suites.

## Result

`build_tables` writes two tables whose column names are chosen so ndxplorer picks
them up without any mapping — in particular the time axis is named
`Mean Macro Time (s)`, which is the column ndX auto-selects.

| table | one row per | columns |
|---|---|---|
| per-photon (`h2mm_photons.h5`) | photon | `Mean Macro Time (s)`, `Macro Time`, `Micro Time`, `Channel`, `Stream`, `State`, `Burst` |
| per-burst (`h2mm_bursts.csv`) | burst | `Burst`, `Number of Photons`, `Mean Macro Time (s)`, `Mean Microtime (<stream>)`, `FRET efficiency`, `Proximity ratio`, `Dominant State`, `Number of Transitions`, `Mean FRET E` |

`Mean Microtime (…)` is emitted once per photon stream and is in nanoseconds when
the micro-time resolution is known — otherwise `NaN`. Colouring the per-photon
scatter by `State` in ndX gives the recovered state trajectory directly.

```{figure} figures/burst_export_table.png
:name: fig-burst-export-table
:width: 100%

The per-burst table as `build_tables` writes it, opened in ChiSurf's table
widget. Every column above is numeric — ndX silently drops any that is not —
and the names are the contract: `Mean Macro Time (s)` is the time axis ndX
auto-selects, `Mean Microtime (green)`/`(red)` are its FRET-line X axis in
nanoseconds, and `Proximity ratio` its Y axis.

The rows are a check as much as an illustration. This export was made from a
simulated trace whose bursts alternate between $E = 0.25$ and $E = 0.75$, so
`Dominant State` alternating 0/1 in step with `Proximity ratio` is H2MM having
recovered the two states — a column of constant zeros would mean the fit
collapsed, which a screenshot of an empty table would not have told you.
```

## See also

- {src}`chisurf/plugins/burst/burst_h2mm/core/export.py`, `chisurf/core/fio/fluorescence/legacy_export.py`, `chisurf/plugins/burst/bid_to_analysis/`.
- The companion contract the export keeps: `okf/subsystems/burst-companions.md`.
- What the index ranges being exported mean: [timestamps and bursts](33_timestamps_and_bursts.md).
- The analysis that produces the `State` column: [H2MM](19_h2mm_hidden_markov.md).
