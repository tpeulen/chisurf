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
search (**Run**), then open the **Histogram** tab:

- **Feature** — the burst column to histogram; `Proximity Ratio` for this fit.
- **Bins**, **Range from** / **Range to** (**Auto range** fits it to the data) and **Log counts**.
- **GMM components** — the number of components; **Auto components** instead picks
  the count with the lowest BIC (up to the maximum set under **GMM settings**).
- **Fit GMM** — fits once and draws the components and their sum over the
  histogram; the table lists each component's weight, mean and standard
  deviation.
- **GMM settings** — covariance type, random seed, initialisations, iterations,
  tolerance, regularisation and the maximum component count of the mixture.

The histogram is built from every burst of the file on show (not only those of the
visible time window: the **Burst duration** tab above is the one that follows the
window, and says so). Tick **Pool all files** (**Display** section of **Filter
settings**) to histogram and fit the bursts of every searched file together, which
is what the whole measurement needs.

```{figure} figures/29_burst_selection_gmm.png
:name: fig-29-burst-selection-gmm
:width: 100%

Burst Selection, **Histogram** tab with **Pool all files** on: the proximity ratio of all 1130 bursts
from ten BH SPC-130 files of a double-labelled DNA sample, fitted with three
Gaussians. The donor-only peak sits at PR = 0.031 (σ = 0.016, weight 0.35),
the FRET population at PR = 0.428 (σ = 0.063, weight 0.47); the third
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

On the same ten files this returns the numbers in the figure (centres 0.031 /
0.428 / 0.405, weights 0.349 / 0.466 / 0.185). The search folder name encodes
the filter settings; a repeated search writes a new folder with a `_0`, `_1`, …
suffix, so glob one folder, not all of them.

For a fully model-based description that also accounts for the shot-noise line
shape (rather than Gaussians), fit the histogram with a
[PDA model](11_pda2c.md) instead.

## Result

A simulated FRET-efficiency histogram of two populations, fitted with three
Gaussian components; the black curve is their sum. The extra component splits the
high-FRET peak (E = 0.68 and 0.76) — what an unasked-for component does, and why
the count is chosen by BIC (**Auto components**).

```{figure} figures/e_hist_fit.png
:name: fig-e-hist-fit
:width: 90%

FRET-efficiency histogram fit.
```

## See also

- {src}`chisurf/plugins/burst/burst_selection/api/features.py`; shot-noise-aware fitting: [PDA](11_pda2c.md).
