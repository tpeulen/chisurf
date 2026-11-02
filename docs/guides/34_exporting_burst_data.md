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
writes a `bv4/`, `2c4/`, `bh4/` … companion folder any more, and the burst search
writes no `.bur` table either — on a vendor file (`.spc`, `.ptu`, …) its container
simply sits beside the measurement, and every later step reads the bursts back out
of a container. When an older tool
(ndX's folder reader, the Seidel/Margarita software, ALEX-Suite-era scripts) needs
the old layouts, you ask for it once, explicitly. Theory: {doc}`../concepts/legacy_export`.

### Legacy Export

**File › Data › Legacy Export** (`chisurf/plugins/core/legacy_export/`) is the
dedicated way out:

1. **Open…** a `.pto` container, drop one on the window, or press **🧪 Load
   example** for a demo container (the Burst Selection demo stream, 12 planted
   bursts, with the burst-search run `burstwise` and a BVA run `bva`). The table
   lists every analysis: its **Run**, the **Table** inside it, its **Operation**
   and the **Companion** ending it becomes (`bur` for a burst table, `bv4`, `2c4`,
   `bg4`/`br4`/`by4`, `bh4`, `td4`, `bf4` for analyses). A dash in *Run* means the
   table is stored outside any run; a dash in *Companion* means that analysis has
   no registered companion and is skipped. *Refresh* re-reads the container;
   **📖 Guide** walks the window step by step.
2. **Output folder** defaults to the container's folder.
3. **📤 Export burst folder** writes the folder. The status line counts the files
   and lists the last ones written.
4. *ALEX-Suite CSVs (optional)*: pick the **Run** (only runs holding a burst
   table are offered; the first is preselected), type **Sample** and **Buffer**
   (free text, written into `_meta`), tick the parts (`meta`, `hist_E`, `hist_S`,
   `hist_2D`, `original_bursts`) and press **Write ALEX-Suite CSVs**. The files go
   into the output folder as `<container stem>_alex_<part>.csv`.

```{figure} figures/34_legacy_export_folder.png
:width: 100%

The Burst Selection demo stream (12 planted bursts) in a container with two
runs: the burst search (`burst_selection` → `bur`) and tttrlib's BVA
(`burst_variance_analysis` → `bv4`). After *Export burst folder*:
`burstwise/bi4_bur/bs_demo.bur`, the BVA companion `burstwise/bv4/bs_demo.bv4`
with 12 rows on the burst grid, and the BVA table as text, `bs_demo/bva.csv`.
```

```{figure} figures/34_legacy_export_alex.png
:width: 100%

The same container after *Write ALEX-Suite CSVs* on the run `burstwise`, sample
"demo bursts", buffer "PBS", the four default parts ticked: `bs_demo_alex_meta.csv`,
`_hist_E`, `_hist_S` and `_hist_2D` in the output folder.
```

The same export without a window:

```bash
csc legacy-export plan m000.pto                        # what each run becomes
csc legacy-export burst-folder m000.pto out_folder     # out_folder defaults to beside m000.pto
csc legacy-export alex-csvs m000.pto/burstwise stem \
    --sample "dsDNA" --buffer "TE" --parts meta,hist_E,hist_S,hist_2D,original_bursts
csc alex-suite export-legacy m000.pto/burstwise stem   # the same CSVs from the ALEX Suite CLI
```

and in Python:

```python
from chisurf.plugins.core.legacy_export import core

core.export_plan("m000.pto")                       # [{"run", "container_run", "operation", "ending"}, ...]
core.export_burst_folder("m000.pto", "out_folder") # every file written
core.export_alex_csvs("m000.pto/burstwise", "out_folder/m000_alex", sample="dsDNA")
```

`export_burst_folder` is `chisurf.core.fio.fluorescence.legacy_export.export_legacy`.
The PTO inspector's **Export legacy (Seidel/Margarita)** button and
`csc csg_pto_inspect export-legacy m000.pto out_folder` call the same writer.
`alex-csvs` takes a run inside a container (`m000.pto/<run>`) or an exported
`.bur` table. Both ALEX-Suite CSV commands take the same options and write the same files
(see the [ALEX Suite guide](66_alex_suite.md)): default thresholds, neutral
corrections and no fit curves in `_meta` and the histogram files.

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
# FRET-line columns ("Mean Microtime (G|G)", "Proximity ratio", ...), from the
# engine's photon data, its Viterbi path and the state efficiencies
# (`data, meta, path, fret` as in burst_h2mm/examples/H2MM_01_Simulated_smFRET.ipynb)
from chisurf.plugins.burst.burst_h2mm.core import export
tables = export.build_tables(data, meta, path, fret, base_time_s=1e-6,
                             stream_groups=[("G|G", (0, 8)), ("R|G", (1, 9))])
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
auto-selects, `Mean Microtime (G|G)`/`(R|G)` are its FRET-line X axis in
nanoseconds, and `Proximity ratio` its Y axis.

The rows are a check as much as an illustration. This export was made from a
simulated trace whose bursts alternate between $E = 0.25$ and $E = 0.75$, so
`Dominant State` alternating 0/1 in step with `Proximity ratio` is H2MM having
recovered the two states — a column of constant zeros would mean the fit
collapsed, which a screenshot of an empty table would not have told you.
```

## See also

- {src}`chisurf/plugins/burst/burst_h2mm/core/export.py`, `chisurf/core/fio/fluorescence/legacy_export.py`, `chisurf/plugins/core/legacy_export/`, `chisurf/plugins/burst/bid_to_analysis/`.
- What the legacy export writes and loses: {doc}`../concepts/legacy_export`.
- The companion contract the export keeps: `okf/subsystems/burst-companions.md`.
- What the index ranges being exported mean: [timestamps and bursts](33_timestamps_and_bursts.md).
- The analysis that produces the `State` column: [H2MM](19_h2mm_hidden_markov.md).
