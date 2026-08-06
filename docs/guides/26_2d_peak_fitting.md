---
type: Guide
title: 2-D peak fitting
description: Multi-parameter histograms — most often the E–S plot, but also lifetime-vs-E or any two burst observables — contain several populations as 2-D peaks.
tags: [guides, fitting, peak]
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

Burst features are extracted and clustered with a **Gaussian mixture model** in
{src}`chisurf/plugins/burst/burst_selection/api/features.py`:

```python
from chisurf.plugins.burst.burst_selection.api.features import extract_features
from sklearn.mixture import GaussianMixture

feat = extract_features(burst_frames)                 # nphotons, duration, fret, ...
gmm = GaussianMixture(n_components=3).fit(feat[["fret", "brightness"]].to_numpy())
means, covs, weights = gmm.means_, gmm.covariances_, gmm.weights_
```

The burst-selection GUI fits and overlays the mixture components on the 2-D
histogram and lets the user gate bursts by component; the same features feed the
downstream burst analyses.

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

- {src}`chisurf/plugins/burst/burst_selection/api/features.py`; the E–S histogram it operates on ([multi-parameter E–S](14_multiparameter_es.md)).
- Gating and comparing the resulting populations: [selecting FRET populations](28_selecting_fret_populations.md).
- 1-D efficiency-histogram fitting: [FRET-histogram fitting](29_fret_histogram_fitting.md).
