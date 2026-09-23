---
type: Guide
title: Binned photon traces (MCS)
description: 'Binning the photon stream into fixed time windows (multi-channel scaler, MCS, traces) is the simplest view of the data and the input to intensity-based methods: burst search, time-trace inspection, camera-style HMM (ebFRET)…'
tags: [guides, photons, bursts, kinetics, hmm]
---

# Binned photon traces (MCS)

:::{admonition} Theory
:class: seealso
Binning is the step that turns a photon stream into the intensity trace the
burst search runs on ({ref}`concept-smfret-bursts`) and that camera-style HMMs
model directly ({ref}`concept-ebfret`). The bin time sets which dynamics survive
averaging.
:::

## What it does

Binning the photon stream into fixed time windows (multi-channel scaler, MCS,
traces) is the simplest view of the data and the input to intensity-based
methods: burst search, time-trace inspection, camera-style HMM
([ebFRET](20_ebfret_binned_hmm.md)), photon-counting histograms
([FIDA](04_fida_pch.md)), and coincidence analysis. Overlaying the green and red
detectors shows coincident FRET bursts at a glance.

## In ChiSurf

```python
import numpy as np
import tttrlib

tttr = tttrlib.TTTR("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc",
                    "SPC-130")
t_s = tttr.macro_times * tttr.header.macro_time_resolution      # photon times (s)
route = tttr.routing_channels

bin_s = 1e-3
edges = np.arange(0, t_s[-1] + bin_s, bin_s)
green = np.histogram(t_s[np.isin(route, [0, 8])], edges)[0]
red = np.histogram(t_s[np.isin(route, [1, 9])], edges)[0]
```

On this 69.2 s measurement that gives 69 244 bins with 119 940 green and
54 498 red photons (mean 1.7 and 0.8 per ms, bursts up to 166 and 148).

The `trace_browser` / `tttr_image_browser` tools and the burst-selection preview
build and display these traces (with adjustable bin time and micro-time gating)
directly from TTTR data.

### Trace Browser

**Spectroscopy ▸ Single-Molecule ▸ Trace Browser** pages through a folder of
point measurements. The first page is the detector definition (which channels
make which trace, and the file type, which also decides the listed
extensions); *Continue* opens the browser: the file table (**File**,
**Rating** 0–3 stars, **Size**), a **Filter** on the rating, the **bin** width
(ms, fractional values allowed), fixed **Ymin/Ymax**, one trace per detector
plus their sum with a count histogram beside each, and a free-text
**Annotation** per file (ratings and annotations are stored in a metadata file
in the folder). The toolbar opens a folder, clears the list or the trace
caches, exports the selected files, CSV traces or a DOCX report, and hands the
selected trace to *Intensity Trace* (**HMM**), *TTTR Time Window* (**TW**) or
ndXplorer (**NDX**); **Subfolders** includes nested folders.

```{figure} figures/22_trace_browser.png
:name: fig-22-trace-browser
:width: 100%

Trace Browser on the ten BH SPC-132 smFRET files of the burst-selection test
folder (green 0/8, red 1/9, SPC-130), `m000.spc` selected, 10 ms bins (the
default). The coincident green/red spikes are FRET bursts; the right column is
the count histogram of each trace. Taken with the image probe corrected — see
*Known defects*.
```

### Known defects

- **The list stays empty for point measurements.** `_is_clsm_compatible`
  (`chisurf/plugins/tttr/trace_browser/__init__.py`, the image probe) counts a
  file as an image when `tttrlib.CLSMImage` exposes an `intensity`; for these
  SPC files it builds an empty `(1, 0, 0)` image, so every file is filtered out
  as "image TTTR" and the table shows 0 rows. The figure above seeds the probe's
  cache with the right answer.
- Top row overlaps: the *Include subfolders* checkbox is clipped under
  *← Select setup* and the folder path runs into *Filter:*; the per-trace y
  tick labels (`1000` over `0`) collide between stacked plots.

## Result

A 1 ms-binned green/red intensity trace (green up, red down); the coincident
green+red spikes are single-molecule FRET bursts.

```{figure} figures/mcs.png
:name: fig-mcs
:width: 90%

Binned photon trace (MCS).
```

## See also

- `chisurf/plugins/tttr/trace_browser/`; the burst search consumes these traces ([burst identification](13_burst_identification.md)).
