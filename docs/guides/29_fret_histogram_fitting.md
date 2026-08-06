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

Burst features are clustered/fit with a scikit-learn `GaussianMixture` in
{src}`chisurf/plugins/burst/burst_selection/api/features.py`; the same one-dimensional
fit applies to the FRET efficiency:

```python
import numpy as np
from sklearn.mixture import GaussianMixture

E = fret["E"].to_numpy()
gm = GaussianMixture(n_components=3, random_state=0).fit(E.reshape(-1, 1))
centres   = gm.means_.ravel()
widths    = np.sqrt(gm.covariances_.ravel())
fractions = gm.weights_
```

For a fully model-based description that also accounts for the shot-noise line
shape (rather than Gaussians), fit the histogram with a
[PDA model](11_pda2c.md) instead.

## Result

The FRET-efficiency histogram of the doubly-labelled bursts, fitted with a
three-component Gaussian mixture; each component's centre is its population's
mean FRET efficiency, and the black curve is their sum.

```{figure} figures/e_hist_fit.png
:name: fig-e-hist-fit
:width: 90%

FRET-efficiency histogram fit.
```

## See also

- {src}`chisurf/plugins/burst/burst_selection/api/features.py`; shot-noise-aware fitting: [PDA](11_pda2c.md).
