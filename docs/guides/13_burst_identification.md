---
type: Guide
title: Photon burst identification and the burst list
description: In a confocal single-molecule experiment the focus is mostly empty; a molecule crossing it produces a short, intense burst of photons above the diffuse background.
tags: [guides, bursts, photons, corrections]
---

# Photon burst identification and the burst list

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for burst search and the per-burst observables.
:::

## What it does

In a confocal single-molecule experiment the focus is mostly empty; a molecule
crossing it produces a short, intense **burst** of photons above the diffuse
background. Identifying those bursts — and building the **burst list** (the
photon-index ranges of each burst) — is the first step of every burst analysis
([2CDE](01_fret_2cde.md), [BVA](08_burst_variance_analysis.md),
[PDA](11_pda2c.md), MLE lifetimes, HMM).

A **sliding-window** search flags photons whose local count rate (photons per
short window, or the inverse inter-photon time) exceeds a threshold; contiguous
flagged photons that also satisfy a minimum-photon count form a burst. The
other searches — CUSUM/SPRT, a Kalman rate-change detector, Bayesian
change-point detection (BOCPD), coincidence across detectors, a threshold-free
max-tree and Bayesian Blocks — trade sensitivity against false positives.

## In ChiSurf

### Open the tool

The Burst Selection panel is step 2 of the Burst Analysis workflow and also opens
as a window of its own.

```{figure} figures/burst_native_selection_verified.png
:name: fig-burst-native-selection-verified
:width: 100%

The **Burst Selection** tab after **Run** on copies of `m000.spc` and `m001.spc`:
198 bursts (71 and 127), 45 868 of 353 909 photons selected, results in a
`bi4_bur/` folder beside each file. Right: the count rate of the first 10 s of
`m000.spc` and the proximity-ratio histogram of its 71 bursts.
```

**Spectroscopy → Single-Molecule → Burst Analysis → 2. Burst Selection**. The panel has no
menu entry of its own (`python -m chisurf.emtk --plugin burst_selection` opens it
alone); in the workflow the files of step 1 carry over. Add files with **Add files** / **Add folder** (or
drop them on the window), pick the detectors on the **Detector setup** tab,
then **Run**. **Restart** searches again even when nothing changed.

```{figure} figures/13_burst_selection_filter.png
:name: fig-burst-selection-filter
:width: 100%

Burst Selection with the ten bundled SPC-132 dsDNA measurements
(`chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/`) and a
two-detector setup (green 0/8, red 1/9). Left: the **Filter settings** tab;
top right: the inter-photon time dT against photon index for the first 10 s of
`m000.spc`, all photons (blue) and the selected, burst photons (orange); the
white line is the accepted maximum dT of the **Macro time interval**. Bottom
right: the proximity-ratio histogram of that window's eight preview bursts.
```

The **Filter settings** tab holds:

| Control | Default | Meaning |
|---|---|---|
| **Search** | Sliding window | The search: Sliding window, Cumulative (CUSUM / SPRT), Kalman (rate change), Bayesian changepoint (BOCPD), Coincident (multi-detector), Max-tree (threshold-free), Bayesian Blocks (optimal segmentation). Its parameters appear below the choice. |
| **Sliding window** → **Min photons (L)**, **Photons per window**, **Window duration (T)** | 20, 10, 0.0005 s | A burst is where `m` consecutive photons fall inside `T`, at least `L` photons long. |
| **Cumulative (CUSUM / SPRT)** → **Min photons (L)**, **Background rate**, **Signal/background ratio** | 20, 0 kcps, 4 | A sequential likelihood-ratio test between the background rate and a rate that many times higher. The search runs on **every photon of the stream**, so the background is the total over all detectors. The line below the fields gives it, measured on the file, and each detector's share (on `DNA13bp_3.ptu`: 3.53 kcps; green 1.58, red 2.00). **0** uses that measured total. Typing one detector's rate instead makes nearly the whole trace look like signal: a few giant "bursts" instead of real ones. The background is estimated from the gaps between photons: the longest 10 % of the gaps are background, since bursts only add short gaps. One over their mean excess is the rate, which is right within 2 % even with 80 % of the photons in bursts. |
| **Save as setup default** | — | Stores the burst parameters as the selected detector setup's defaults. |
| **Channel selection** → **Detector**, **Micro-time window** | All | Detector and PIE-window gate applied before the search. |
| **Macro time interval** | upper bound 0.15 ms, merge gap 3 | Accepted inter-photon times dT (**Use min dT** / **Use max dT**); gaps of up to **Merge gap** photons are bridged (**Fill gaps**). |
| **Filter** → **Filter on** / **Invert**, **Min photons**, **Count-rate photons** | on / off, 60, 5 | Apply the search; **Invert** keeps the photons it rejects. |
| **Display** | window 10 s | The count-rate trace is in kHz. The visible window of the active file (**Window start**, **Window length**), the plot bin widths (**MCS bin width**, **Decay coarsening**, **Burst bins**) and **Pool all files**. |

The **Burst Selection** tab lists the inputs and says where results go. The destination
follows the input: vendor files get a `bi4_bur/` folder beside them
(*Results go to: a bi4_bur/ folder beside each file*), a `.pto` keeps its bursts
inside. The ten files above gave 1130 bursts from 1 791 775 photons (264 806
selected) in `sliding_window_All 0.1500#60/`; `m000.spc` alone gives 71 bursts
(mean 4.28 ms, 211 photons). **Summary** shows the figures of the run; on the right, **Bursts** is the
per-burst table, **Histogram** a feature histogram with an optional GMM,
**Scatter** two features against each other, and **Count rate**,
**Inter-photon time**, **Micro-time decay** and **Burst duration** are the
diagnostics.

```{figure} figures/13_burst_selection_mcs.png
:name: fig-burst-selection-mcs
:width: 100%

The **Count rate** tab: count rate in 0.25 ms bins over the same 10 s window, all
photons (blue) and burst photons (orange).
```

### Headless

```python
import tttrlib

d = tttrlib.TTTR("m000.spc", "SPC-130")
# sliding-window search: L min photons, m photons per window, T window time (s)
bursts = d.burst_search(L=20, m=10, T=0.5e-3).reshape(-1, 2)   # (first, last) photon rows
```

`burst_search` returns the start and stop photon indices as one flat array;
reshape it to rows. On `m000.spc` it finds 223 bursts, directly on all
channels and without the dT pre-filter of the panel.

The `burst-selection` CLI (`analyze`, `inspect`, `fit-gmm`) runs the panel's
search on files. From the guided facade, bursts are selected on registered
datasets:

```python
from chisurf.plugins.burst.burst_analysis.api.workflow import BurstWorkflow

wf = BurstWorkflow.demo()                                  # private local MMFDB
handles = wf.register_all(["m000.spc", "m001.spc", "m002.spc"])
bursts = wf.select_bursts(handles, method="burst", min_photons=20)
bursts.table                                               # one row per burst
```

### Speed on large batches

A batch of large files is searched in parallel: one worker process per file, as
many as there are cores (at most 8). The results are merged in file order, so
they match a sequential run exactly. Files averaging under 32 MB are searched
one after the other, because starting a worker (about 1 s) would cost more
than the search. So is a batch writing the legacy burstwise folder.
`CHISURF_BURST_WORKERS=1` turns the parallel search off; any other number caps
the workers.

The photon file is read only once for the whole pipeline. BVA, 2CDE, H2MM and
Burst MLE take the reading the search made, even though each of them writes
its results into the analysis container. A new container is created while the
search runs (linking the photon file means hashing it), not after it.

On a 12 M-photon, 311 MB PTU file one search takes 2.1 s. Four such files take
5.7 s in parallel and 7.4 s one after the other.

The standard pipeline (Simple mode: files in, fast-forward) goes from files to
fitted burst lifetimes in about 6 s on that file, and no single frame of the
window takes longer than about 0.25 s. Four things make that possible:

- Each step's work starts ahead of time:
  - the photon file is read in the background as soon as Data Selection has it;
  - the modules the steps need are loaded in the background when the window
    opens;
  - Burst MLE takes the new bursts in its background job, with its setup and
    its IRF and background prepared in the same job.
- The burst fit splits each measurement's bursts into chunks and spreads them
  over every core. Its worker processes stay alive between fits and are
  started while MLE prepares.
- Fast-forward runs Burst MLE's fit as well: once the preparation is done, the
  fit starts.
- The project's analysis container is created while the file sits in Data
  Selection. Linking the photons hashes the whole file (1.5 s for 300 MB), and
  the first search used to wait for that.
- In Simple mode, BVA and 2CDE start as soon as the bursts are there, each in
  a worker process of its own, so they compute while you set up Burst MLE. They
  write into the container exactly what the step computes itself, and the step
  then shows the result.
- The photon file is read once for the whole pipeline (see above).

## Result

A simulated photon stream (diffuse background with occasional bright transits)
and its count rate in 0.5 ms windows; the windows above the threshold (red) are
the detected bursts.

```{figure} figures/burst_search.png
:name: fig-burst-search
:width: 90%

Burst identification.
```

## Reading the diagnostic plots

The plots draw a **window of the active file**, not all of it. Ten seconds by
default: a long measurement is millions of photons, and drawn whole it is an
envelope with no individual burst visible in it.

**Window length** (in the **Display** panel) sets the length and **Window start**
walks it through the file; a length of 0 draws the whole file. Select another
file in the file list to look at that one. The bursts of the window are previewed
before any search has run; **Run** searches every photon of every file.

**Pool all files** (also in **Display**) makes the burst table, the histogram, the
scatter plot and the summary show the bursts of every searched file together, which
is what fitting the proximity-ratio histogram of a whole measurement needs
([FRET-histogram fitting](29_fret_histogram_fitting.md)); the diagnostic plots
stay on the active file.

The count-rate trace is a **count rate**, in Hz, not counts per bin — so changing the
bin width sharpens or smooths the trace without moving it up and down, and a
burst can be compared against the background rate (the **Background** step of
Burst Analysis) directly. With 0.25 ms bins one photon is 4 kHz, which is why the
background in {numref}`fig-burst-selection-mcs` sits in 4 kHz steps.

## See also

- `chisurf/plugins/burst/burst_selection/`; `chisurf/core/fluorescence/burst/`.

## Known defects

- **A fresh settings directory with a `detector_setups.json` stops the panel
  from opening.** On construction the setup list migrates the JSON file into
  MMFDB stamped with the active user, `user_default`
  (`chisurf/core/fio/setup_store.py`, `resolve_active_user_id`), which a new
  database does not contain; `save_setup` fails with *FOREIGN KEY constraint
  failed* and the panel does not open
  (`tttr_detector_setups.py`, `load_detector_setups`). Reproduced with an empty
  `CHISURF_SETTINGS_DIR` plus one setup file.
- **The search writes beside the input.** Running it on the bundled test files
  creates `sliding_window_All …/` inside the source tree; copy test data first.
