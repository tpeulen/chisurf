# Exporting burst data

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

## See also

- `chisurf/plugins/burst/burst_h2mm/core/export.py`, `chisurf/plugins/burst/bid_to_analysis/`.
