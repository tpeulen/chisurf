---
type: Guide
title: 2-D peak fitting
description: Multi-parameter histograms — most often the E–S plot, but also lifetime-vs-E or any two burst observables — contain several populations as 2-D peaks.
tags: [guides, fitting, tcspc, lifetime, bursts]
---

# 2-D peak fitting

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the E–S map the 2-D peaks are fitted on.
:::

## What it does

Multi-parameter histograms — most often the [E–S plot](14_multiparameter_es.md),
but also lifetime-vs-E or any two burst observables — contain several populations
as 2-D peaks. Fitting them with a sum of 2-D (Gaussian) components gives each
population's **centre, width and fraction** objectively, instead of reading them
off by eye, and is the basis for gating sub-populations and for quantitative
comparison between conditions.

## In ChiSurf

The 2-D fit is interactive in **ndX** (`ndxplorer`): put the two observables on
the x and y axes of the 2-D histogram, open **View → Fit Gaussians**, click one
seed on each population, and press **Fit**. Each component's centre (`x`, `y`),
widths (`sd_x`, `sd_y`), correlation `rho` and weight `w` land in the fit table,
where any of them can be held fixed; the 1σ/2σ/3σ ellipses are drawn over the
histogram and each component's marginal over the projections.

```{figure} figures/26_ndx_2d_gaussians.png
:name: fig-26-ndx-2d-gaussians
:width: 100%

ndX with four 2-D Gaussians fitted to an E–S burst table: two FRET populations
at S ≈ 0.5, donor-only at (0.03, 0.95) and acceptor-only at (0.95, 0.08). The
2 400 bursts are simulated with binomial shot noise (60 + 20 photons per burst)
so the answer is known: the fit returns weights 0.375 / 0.292 / 0.208 / 0.125
(truth 900 / 700 / 500 / 300 bursts) and centres within 0.005 of the truth.
```

The same mixture fit without a GUI is ChiSurf's own `GaussianMixture`
({src}`chisurf/core/ml/mixture/_gaussian_mixture.py`), a drop-in for the scikit-learn class:

```python
import numpy as np
from chisurf.core.ml import GaussianMixture

X = np.column_stack([E, S])                       # one row per burst
fits = {k: GaussianMixture(n_components=k, covariance_type="full", random_state=0).fit(X)
        for k in (2, 3, 4, 5)}
bic = {k: m.bic(X) for k, m in fits.items()}      # choose the count by BIC
gmm = fits[min(bic, key=bic.get)]
means, covs, weights = gmm.means_, gmm.covariances_, gmm.weights_
```

On the four-population table above BIC is lowest at four components
(−7008, against −6967 for five).

The **Burst Selection** tool fits the same mixture in one dimension — the
histogram of whichever burst feature is selected
([FRET-histogram fitting](29_fret_histogram_fitting.md)).
{src}`chisurf/plugins/burst/burst_selection/api/features.py` builds the per-burst
feature table it clusters (`extract_features` → a `tttrlib.DataStore` with
`nphotons`, `duration`, `brightness`, `interphoton`, `fret`), and `fit_gmm`
fits it.

## Result

Fitting the mixture returns each population's centre, covariance and weight as
numbers rather than as an eyeballed gate — and the covariance ellipses show
directly how much two populations overlap, which is what decides whether they can
be separated at all.

```{figure} figures/peak_fit_2d.png
:name: fig-peak-fit-2d
:width: 95%

**Left:** the 2-D E–S histogram of four simulated populations (donor-only,
acceptor-only and two FRET species). **Right:** the 4-component Gaussian mixture
fitted to the same bursts, with 1σ and 2σ covariance ellipses and the recovered
centre, stoichiometry and weight of each component.
```

Choose the component count deliberately: a mixture will happily fit whatever
number of components you ask for. Compare candidate counts by BIC, and check that
each component corresponds to a population you can justify physically (a
donor-only corner, a known FRET state) rather than to a tail of the shot-noise
distribution.

## See also

- ndX's Gaussian fit and the 1-D fit in Burst Selection; the E–S histogram they operate on ([multi-parameter E–S](14_multiparameter_es.md)).
- Gating and comparing the resulting populations: [selecting FRET populations](28_selecting_fret_populations.md).
- 1-D efficiency-histogram fitting: [FRET-histogram fitting](29_fret_histogram_fitting.md).
