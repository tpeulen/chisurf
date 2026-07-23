# Working with timestamps and bursts (the data model)

## What it does

Every burst analysis rests on three per-photon arrays and one per-burst
structure. Understanding them lets you compute any custom observable.

- **Macro times** — photon arrival on the experiment clock (for burst search,
  correlation, burst timing).
- **Micro times** — TCSPC channel = delay after the laser pulse (for lifetime,
  filtered FCS, PIE gating).
- **Routing channels** — the detector (→ colour / polarisation).
- The **burst list** — for each burst, the *first* and *last* photon **index**
  into those arrays. Everything about a burst (its photons, per-stream counts,
  duration, E, S) derives from that index range.

## In ChiSurf

```python
import numpy as np
import tttrlib

d = tttrlib.TTTR("measurement.ptu", "PTU")
macro = np.asarray(d.macro_times)               # clock ticks
micro = np.asarray(d.micro_times)               # TCSPC channel
route = np.asarray(d.routing_channels)           # detector

# a photon-stream mask (donor-excitation, donor emission)
mask_dd = np.isin(route, donor_channels) & (micro >= dex_lo) & (micro <= dex_hi)

# bursts as inclusive [first, last] photon-index ranges
bursts = d.burst_search(L=20, m=10, T=0.5e-3)    # [s0, e0, s1, e1, ...]
for s, e in np.asarray(bursts).reshape(-1, 2):
    n_donor = mask_dd[s:e + 1].sum()             # donor photons in this burst
    duration_s = (macro[e] - macro[s]) * d.header.macro_time_resolution
```

Bursts can be sliced into time bins (the basis of [BVA](08_burst_variance_analysis.md)),
fused if separated by short gaps, or filtered by size/duration/background. The
`burst_selection` plugin and the `BurstFeature` engines (`tttrlib.BVA`,
`tttrlib.TwoCDE`) all consume exactly this index-range representation.

## See also

- `tttrlib.TTTR`, `TTTR.burst_search`; [handling TTTR files](12_handling_tttr_files.md), [burst identification](13_burst_identification.md).
