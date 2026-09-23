---
type: Guide
title: FRET-efficiency histogram fitting
description: The proximity-ratio / FRET-efficiency histogram of a burst set is a sum of populations, each broadened by shot noise (and possibly dynamics).
tags: [guides, fret, fitting, bursts, dynamics]
---

# FRET-efficiency histogram fitting

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the accurate FRET efficiency E the histogram is built from.
:::

## What it does

The proximity-ratio / FRET-efficiency histogram of a burst set is a sum of
populations, each broadened by shot noise (and possibly dynamics). Fitting it
with a **mixture of Gaussians** turns the qualitative picture into numbers: the
**centre** (mean FRET efficiency), **width** and **fraction** of every
population. These are the quantities compared across mutants, ligand conditions
or time points, and the input to distance interpretation via the
[polymer / distance-distribution models](03_polymer_distance_distributions.md).
A kernel-density estimate (KDE) of the histogram gives a robust starting guess
for the peak positions.

## In ChiSurf

In the **Burst Selection** tool (also step 2 of **Burst Analysis**), run the
search (▶), then open the **Histogram** tab:

- **Feature** — the burst column to histogram; `Proximity Ratio` for this fit.
- **# Bins**, **Range** (**⚡ Auto** fits it to the data) and **Log x**.
- **GMM** — the number of components; **Auto components** instead picks the
  count with the lowest BIC (up to the maximum set under **⚙️**).
- **🎯 Fit GMM** — fits once and draws the components (dashed) and their sum
  (red) over the histogram; the table lists each component's weight, mean and
  standard deviation.
- **⚙️** — covariance type, random seed, initialisations, iterations,
  tolerance, regularisation and the maximum component count of the mixture.

The histogram is built from the bursts on screen. With **Show a window of**
ticked (the default) that is only the bursts of the visible window, so untick
it and select all files in **Files** before fitting the whole measurement.

```{figure} figures/29_burst_selection_gmm.png
:name: fig-29-burst-selection-gmm
:width: 100%

Burst Selection, **Histogram** tab: the proximity ratio of all 1130 bursts
from ten BH SPC-130 files of a double-labelled DNA sample, fitted with three
Gaussians. The donor-only peak sits at PR = 0.023 (σ = 0.014, weight 0.35),
the FRET population at PR = 0.400 (σ = 0.063, weight 0.46); the third
component (σ = 0.24, weight 0.19) absorbs the flat background between them.
```

The same fit without the GUI, on the `.bur` files the search wrote, uses
ChiSurf's own `GaussianMixture` (the class `fit_gmm` in
{src}`chisurf/plugins/burst/burst_selection/api/features.py` uses):

```python
import glob
import numpy as np
from chisurf.core.datastore import numeric_column
from chisurf.core.fluorescence.burst.photons import load_bur_dataframe
from chisurf.core.ml import GaussianMixture
from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio

bursts = load_bur_dataframe(sorted(glob.glob("sliding_window_All 0.1500#60/bi4_bur/*.bur")))
E = proximity_ratio(bursts)                           # red / (green + red), per burst
E = E[np.isfinite(E) & (numeric_column(bursts, "Number of Photons") > 0)]
gm = GaussianMixture(n_components=3, random_state=0).fit(E.reshape(-1, 1))
centres   = gm.means_.ravel()
widths    = np.sqrt(gm.covariances_.ravel())
fractions = gm.weights_
```

On the same ten files this returns the numbers in the figure (centres 0.023 /
0.400 / 0.387, weights 0.351 / 0.456 / 0.193). The search folder name encodes
the filter settings; a repeated search writes a new folder with a `_0`, `_1`, …
suffix, so glob one folder, not all of them.

For a fully model-based description that also accounts for the shot-noise line
shape (rather than Gaussians), fit the histogram with a
[PDA model](11_pda2c.md) instead.

:::{admonition} Known defects
:class: warning
After ▶ Run the Bursts and Histogram tabs show the bursts of the visible window
only (8 of 1130 in the first 10 s of this dataset), and **Fit GMM** fits those;
nothing on the tab says so. With the window unticked the caption reports
*Whole measurement — 126.3 s* for ten files that last 642 s: the per-file time
offsets do not accumulate, so the time-axis plots (MCS) draw files 2–10 on top
of each other.
:::

## Result

A simulated FRET-efficiency histogram, fitted with a
three-component Gaussian mixture; each component's centre is its population's
mean FRET efficiency, and the black curve is their sum.

```{figure} figures/e_hist_fit.png
:name: fig-e-hist-fit
:width: 90%

FRET-efficiency histogram fit.
```

## See also

- {src}`chisurf/plugins/burst/burst_selection/api/features.py`; shot-noise-aware fitting: [PDA](11_pda2c.md).
