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

**Spectroscopy ▸ Single-Molecule ▸ Trace Browser** opens an emtk window that
pages through a folder of point measurements. The first page is the detector
definition (which channels make which trace, and the file type, which also
decides the listed extensions); **Continue** opens the browser (a setup that
was used before opens it directly; **← Select setup** goes back). The left
window holds the controls and the file table (**File**, **Rating** 0–3,
**Size (MB)**, **Notes**; double click a rating or a note to edit it), the
right window the trace of the selected file: one line per detector plus their
sum, the count histogram beside it, and the **Annotation** box (the same text
as the Notes cell; ratings and notes are stored in a metadata file in the
folder). **Open** (or a dropped folder) chooses the folder, **Include
subfolders**, **Filter** (rating), **Bin window [ms]** (fractional values
allowed) and **Y min / Y max** shape the list and the plot; **Precompute**
caches the traces of all listed files in the background, **Clear** and
**Clear caches** reset the list or the caches.

The buttons under the folder row act on the selected files (click a row, or
**Select all**):

| Button | What it does |
|---|---|
| **Export** | copies the selected files, unchanged, into a folder you choose |
| **CSV** | writes each selected trace (time and one column per series, at the current bin window) into a folder you choose |
| **DOCX** | writes a Word report (name, folder, rating, annotation, trace picture) into the opened folder; needs the optional `python-docx` package and is greyed without it |
| **Delete** | after a confirmation, moves the selected files and the files that share their name to the `.trash` folder of the opened folder (nothing is deleted for good); the Delete key in the table does the same |
| **HMM**, **TW**, **NDX** | open the first selected file in a new *Intensity Trace* window (the bin window and the detector setup are passed on), a new *TTTR Time Window* tool holding the file and the bin window, or a new ndXplorer window; they work inside ChiSurf and are greyed when the Trace Browser runs on its own (**NDX** first writes the burst table next to the data and opens ndX on that folder) |

**Help** explains the window and **Guide** walks through the first steps.

```{figure} figures/22_trace_browser.png
:name: fig-22-trace-browser
:width: 100%

Trace Browser on the ten BH SPC-132 smFRET files of the burst-selection test
folder (green 0/8, red 1/9, SPC-130), `m000.spc` selected, 10 ms bins (the
default). The coincident green/red spikes are FRET bursts; the right column is
the count histogram of each trace. HMM, TW and NDX are enabled because a
ChiSurf session (a Qt application) is running; they are greyed when the Trace
Browser runs without one. DOCX is greyed because `python-docx` is not
installed.
```

### Known limits

- The CSV written by the plugin's RPC export labels its first column
  `time_ms`, but the values are seconds (the last row of a 62 s measurement
  reads 62.32).
- The list shows point measurements only: files that are scan images are
  skipped.

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
