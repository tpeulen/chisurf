---
type: Guide
title: Working with timestamps and bursts (the data model)
description: Every burst analysis rests on three per-photon arrays and one per-burst structure.
tags: [guides, bursts, photons, structure]
---

# Working with timestamps and bursts (the data model)

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for burst search over the photon timestamps.
:::

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

# a photon-stream mask (donor-excitation window, donor emission)
donor_channels, dex_lo, dex_hi = (0, 8), 0, 2047
mask_dd = np.isin(route, donor_channels) & (micro >= dex_lo) & (micro <= dex_hi)

# bursts as inclusive [first, last] photon-index ranges
bursts = d.burst_search(L=20, m=10, T=0.5e-3)    # [s0, e0, s1, e1, ...]
for s, e in np.asarray(bursts).reshape(-1, 2):
    n_donor = mask_dd[s:e + 1].sum()             # donor photons in this burst
    duration_s = (macro[e] - macro[s]) * d.header.macro_time_resolution
```

On `m000.spc` of the double-labelled DNA fixture
(`burst_selection/tests/data/bh_spc132_sm_dna`, SPC-130) this reads 174 438
photons and returns 223 bursts; the first three are `[382, 401]`,
`[1785, 1807]` and `[1995, 2034]`.

The **Burst Selection** tool draws exactly this representation. Its **dT** tab
plots the inter-photon time against the photon *index* — the x axis is the
index into the three arrays — and colours the photons inside bursts:

```{figure} figures/33_burst_selection_dt.png
:name: fig-33-burst-selection-dt
:width: 100%

Burst Selection, **dT** tab, the first second of `m000.spc` (**Show a window
of** 1.00 s). Outside bursts the photons (orange: all photons) arrive
~0.1–1 ms apart; the three dips to ~0.01 ms (cyan: selected photons) are bursts, at photon indices 382–401, 1785–1807 and
1995–2034 — the same ranges `burst_search` returns above. The **Bursts** tab
lists the search result as rows of `First Photon` / `Last Photon` with the
reductions over each slice (duration, mean macro time, photon counts per
detector).
```

Bursts can be sliced into time bins (the basis of [BVA](08_burst_variance_analysis.md)),
fused if separated by short gaps, or filtered by size/duration/background. The
`burst_selection` plugin and the `BurstFeature` engines (`tttrlib.BVA`,
`tttrlib.TwoCDE`) all consume exactly this index-range representation.

## Result

The key idea is that a burst is **not** a copy of any photons: it is a pair of
indices into the per-photon arrays. Every burst observable is a reduction over
that slice, which is why adding a new observable never requires re-reading the
file.

```{figure} figures/timestamps_bursts.png
:name: fig-timestamps-bursts
:width: 100%

**Top:** the photon stream, one tick per photon, on two routing channels; the
shaded spans are three bursts, labelled with their `[first, last]` photon
indices. **Bottom:** the same stream binned into a count-rate trace — the bursts
are the spikes the search flags.
```

:::{admonition} Known defects
:class: warning
In Burst Selection the dT trace joins the burst photons of the window with one
continuous line across the gaps between bursts. The **Bursts** table does not
follow a change of the window length (after 10 s → 1 s it still lists the
bursts of the 10 s window) and applies the search's photon threshold, so the
three short bursts marked in the trace above are not in it.
:::

## See also

- `tttrlib.TTTR`, `TTTR.burst_search`; [handling TTTR files](12_handling_tttr_files.md), [burst identification](13_burst_identification.md).
- Binning the same stream: [binned photon traces](22_binned_photon_traces.md).
- Getting the slices back out: [exporting burst data](34_exporting_burst_data.md).
- Tool: the **TTTR Toolbox** (`chisurf/plugins/tttr/tttr_toolbox/`) and **Burst Analysis** (`chisurf/plugins/burst/burst_analysis/`).
