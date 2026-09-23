---
type: Guide
title: A complete µs-ALEX smFRET burst-analysis workflow
description: This tutorial walks the full end-to-end pipeline for freely-diffusing single-molecule FRET with alternating-laser excitation (µs-ALEX), the way a typical analysis notebook is structured…
tags: [guides, fret, smfret, bursts]
---

# A complete µs-ALEX smFRET burst-analysis workflow

:::{admonition} Theory
:class: seealso
The burst-analysis theory behind this workflow — burst search, accurate $E$/$S$,
and the leakage/direct-excitation/$\gamma$/$\beta$ corrections — is in the
concept page {ref}`concept-smfret-bursts`.
:::

This tutorial walks the full end-to-end pipeline for freely-diffusing
single-molecule FRET with alternating-laser excitation (µs-ALEX), the way a
typical analysis notebook is structured — but using ChiSurf's guided
`BurstWorkflow` facade, where each step is one plain-English line.

## The steps

1. **Load** the TTTR data (PTU/HT3/Photon-HDF5) and declare the detector setup.
2. **Corrections** — leakage, direct excitation, γ (and β for stoichiometry).
3. **Background** — estimate the per-detector rate from the inter-photon-time tail.
4. **Burst search** — sliding window (min photons L, window m, threshold factor F).
5. **E–S histogram** — the 2-D map, gating out donor-only / acceptor-only.
6. **Select** the FRET sub-population(s) and **fit** the FRET histogram.

## In ChiSurf

The guided window is **Burst Analysis** (`chisurf/plugins/burst/burst_analysis/`):
a numbered pipeline on the left — *1. Data Selection*, *2. Burst Selection*,
*3. Burst Fusion (optional)*, *4. Burst BVA*, *5. Burst 2CDE*, *6. Burst MLE*,
*7. Burst segmentation (H2MM)*, *8. Burst segment MLE* — and the side tools
(Browser, Accurate FRET, Burst FCS, Kinetics (GS), Background,
IRF & Background) below the separator. Each step reads the previous step's
output folder; **Next ▶** moves on.

```{figure} figures/27_burst_analysis_pipeline.png
:name: fig-27-burst-analysis-pipeline
:width: 100%

Burst Analysis on step 2 after ▶ Run on the ten BH SPC-130 files of a
double-labelled DNA sample (`burst_selection/tests/data/bh_spc132_sm_dna`):
the inter-photon-time trace of the first 10 s window, with the
sliding-window search (L = 20, m = 10, max dT 0.15 ms) marking the selected
burst photons in cyan — 71 bursts in this window, 1130 over all ten files.
```

The same pipeline from Python is the `BurstWorkflow` facade, where each step is
one line:

```python
from chisurf.plugins.burst.burst_analysis.api.workflow import BurstWorkflow, Detector, Setup

wf = BurstWorkflow.demo()                         # private MMFDB; or BurstWorkflow.connect(url, ...)
h = wf.register("m000.spc")                       # store the measurement, get its handle

# PIE on a BH SPC-130: donor- and acceptor-excitation windows split the micro time
setup = Setup([
    Detector("green", (0, 8)),
    Detector("red", (1, 9), ((0, 2048),)),        # acceptor emission after donor excitation
    Detector("yellow", (1, 9), ((2048, 4095),)),  # acceptor emission after acceptor excitation
], file_type="SPC-130")
bursts = wf.select_bursts(h, setup=setup, method="burst", min_photons=20)

# derived observables + downstream analyses, each a one-liner:
bursts.two_cde("green", "red")                   # dynamics filter  (tutorial 1)
bursts.bva("green", "red")                       # variance analysis (tutorial 8)
wf.close()
```

Run on `m000.spc` of that dataset this finds 110 bursts, a mean FRET-2CDE of
12.0 and a BVA dynamic fraction of 0.41. `Setup.from_channels(green=(0, 8),
red=(1, 9))` is the shorthand when no micro-time gating is needed.

The correction factors are managed by {src}`chisurf/core/fluorescence/fret/calibration.py`
(see [tutorial 14](14_multiparameter_es.md)); the background by
[tutorial 15](15_background_rates.md); and the burst search by
[tutorial 13](13_burst_identification.md). `BurstWorkflow.simulate(fret=…,
exchange_rate=…)` generates a known-ground-truth dataset to validate the
whole pipeline.

:::{admonition} Known defects
:class: warning
`select_bursts` runs the search without the setup's detectors, so the burst
table it returns carries no per-detector photon counts and no proximity ratio.
`Bursts.recurrence()` therefore raises *no FRET efficiency / proximity-ratio
column*, and the micro-time windows of a `Detector` do not gate the search
itself (BVA, 2CDE and H2MM, which read the photons, do honour them).
:::

## Result

The µs-ALEX $E$–$S$ jointplot: two FRET populations at mid stoichiometry, plus
the donor-only ($S\to1$) and acceptor-only ($S\to0$) species that the
stoichiometry gate removes. The marginal histograms are the projected $E$ and
$S$ distributions.

```{figure} figures/alex_workflow.png
:name: fig-alex-workflow
:width: 90%

µs-ALEX smFRET burst analysis.
```

## See also

- The same pipeline as a guided window, in the order the ALEX-Suite program had
  it: [Coming from ALEX-Suite](66_alex_suite.md).
- Guided facade: {src}`chisurf/plugins/burst/burst_analysis/api/workflow.py`.
- Population selection: [tutorial 28](28_selecting_fret_populations.md); histogram fitting: [tutorial 29](29_fret_histogram_fitting.md).
