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
`chisurf/plugins/burst/burst_selection/api/features.py`:

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

## See also

- `chisurf/plugins/burst/burst_selection/api/features.py`; the E–S histogram it operates on ([multi-parameter E–S](14_multiparameter_es.md)).
