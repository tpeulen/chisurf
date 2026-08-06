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

The burst analyses write per-file sidecars (BVA `.bv4`, 2CDE `.2cde`) into the
burst folder, and the workflow tables are plain pandas DataFrames — so any format
is a one-liner. The H2MM export is designed to open directly in **ndxplorer**:

```python
# burst table -> CSV / the MFD-HDF5 columns ndxplorer plots on
bursts.table.to_csv("bursts.csv", index=False)

# per-burst H2MM export: a per-photon HDF5 + a per-burst CSV with the ndX
# FRET-line columns ("Mean Microtime (green)", "Proximity ratio", ...)
from chisurf.plugins.burst.burst_h2mm.core.export import build_tables
build_tables(result, out_dir="h2mm/")

# per-photon data of the selected bursts
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
| per-burst (`h2mm_bursts.csv`) | burst | `Burst`, `Number of Photons`, `Mean Macro Time (s)`, `Mean Microtime (<stream>)`, `Proximity ratio`, `Dominant State`, `Number of Transitions`, `Mean FRET E` |

`Mean Microtime (…)` is emitted once per photon stream and is in nanoseconds when
the micro-time resolution is known — otherwise `NaN`. Colouring the per-photon
scatter by `State` in ndX gives the recovered state trajectory directly.

## See also

- {src}`chisurf/plugins/burst/burst_h2mm/core/export.py`, `chisurf/plugins/burst/bid_to_analysis/`.
- What the index ranges being exported mean: [timestamps and bursts](33_timestamps_and_bursts.md).
- The analysis that produces the `State` column: [H2MM](19_h2mm_hidden_markov.md).
