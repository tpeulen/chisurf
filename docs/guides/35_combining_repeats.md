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

The guided workflow registers many files and selects bursts across all of them;
because the per-burst results are DataFrames tagged by `First File`, combining is
a `concat` and per-file grouping is a `groupby`:

```python
import pandas as pd
from chisurf.plugins.burst.burst_analysis.api.workflow import BurstWorkflow

wf = BurstWorkflow()
handles = wf.register_all(["rep1.ptu", "rep2.ptu", "rep3.ptu"])
bursts = wf.select_bursts(handles, setup=setup)   # background estimated per file

combined = bursts.table                            # all repeats, tagged by 'First File'
per_file_E = combined.groupby("First File")["E"].mean()
```

Files imported this way are registered in MMFDB, so the combined analysis keeps a
provenance record of which measurement each burst came from.

## Result

FRET-efficiency histograms of three technical repeats (outlines) and their
combined histogram (filled) — the repeats agree, and pooling sharpens the two
populations.

```{figure} figures/combining_repeats.png
:name: fig-combining-repeats
:width: 90%

Combining technical repeats.
```

## See also

- {src}`chisurf/plugins/burst/burst_analysis/api/workflow.py` (`register_all`, `select_bursts`).
- Tool: **FCS-Merger** (`chisurf/plugins/fcs/fcs_merger/`).
