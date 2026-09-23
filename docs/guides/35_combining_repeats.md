---
type: Guide
title: Combining measurements / technical repeats
description: Single-molecule datasets are often split across several files — technical repeats of the same sample, a titration series, or long acquisitions saved in chunks.
tags: [guides, combining, repeats]
---

# Combining measurements / technical repeats

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the per-burst observables being pooled and
why each file must be background-corrected on its own rate first.
:::

## What it does

Single-molecule datasets are often split across several files — technical
repeats of the same sample, a titration series, or long acquisitions saved in
chunks. Pooling their bursts into one dataset improves statistics (more bursts →
tighter histograms and fit parameters) while keeping the per-file provenance for
quality control. Each file should be background-corrected on its **own** rate
(background drifts between acquisitions) before the bursts are combined.

## In ChiSurf

**Burst Selection** (and step 2 of **Burst Analysis**) takes any number of
files: drop a folder on the **Files** tab or add files with the toolbar, and
▶ Run searches every file with the same settings, writing one `.bur` per file
into one output folder. Each burst row keeps its `First File`, so per-file
provenance survives pooling. Background is a separate step
([background rates](15_background_rates.md)) and is estimated per file there.

```{figure} figures/35_burst_selection_files.png
:name: fig-35-burst-selection-files
:width: 100%

Burst Selection on ten repeats of a double-labelled DNA measurement
(`m000.spc` … `m009.spc`, BH SPC-130), **Show a window of** unticked and all
files selected: the **dT** tab on the pooled photon index, one colour per file
(1.79 M photons), burst photons in cyan. The search finds 71–134 bursts per
file, 1130 in total, and the **Histogram** tab then histograms and fits all of
them together ([FRET-histogram fitting](29_fret_histogram_fitting.md)).
```

Pooling and per-file quality control from the `.bur` files the search wrote:

```python
import glob
import numpy as np
from chisurf.core.datastore import numeric_column
from chisurf.core.fluorescence.burst.photons import load_bur_dataframe
from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio

combined = load_bur_dataframe(sorted(glob.glob("sliding_window_All 0.1500#60/bi4_bur/*.bur")))
files = np.asarray(combined["First File"]).astype(str)
real = numeric_column(combined, "Number of Photons") > 0      # drop separator rows
pr = proximity_ratio(combined)

per_file = {f: np.nanmedian(pr[real & (files == f)]) for f in np.unique(files[real])}
pooled = pr[real]
```

On the ten repeats the per-file median proximity ratio is 0.32–0.36 for nine
files and 0.21 for `m006.spc` — the file to look at before it goes into the
pool. The facade's `BurstWorkflow.register_all([...])` followed by
`select_bursts(handles, setup=setup)` searches several registered files in one
call and keeps their MMFDB provenance
({src}`chisurf/plugins/burst/burst_analysis/api/workflow.py`).

:::{admonition} Known defects
:class: warning
With **Show a window of** unticked, the caption and the time-axis plots (MCS)
place files 2–10 on top of each other: the ten files last 642 s together, the
caption says *Whole measurement — 126.3 s*. The photon-index plots (dT) are
unaffected.
:::

## Result

A script figure: FRET-efficiency histograms of three simulated technical repeats (outlines) and their
combined histogram (filled) — the repeats agree, and pooling sharpens the two
populations.

```{figure} figures/combining_repeats.png
:name: fig-combining-repeats
:width: 90%

Combining technical repeats.
```

## See also

- {src}`chisurf/plugins/burst/burst_analysis/api/workflow.py` (`register_all`, `select_bursts`).
- Tools: **Burst Selection** (`chisurf/plugins/burst/burst_selection/`); for FCS curves of repeats, **FCS-Merger** (`chisurf/plugins/fcs/fcs_merger/`).
