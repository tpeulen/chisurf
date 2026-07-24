# Filtered FCS (fFCS / 2D-FLCS)

:::{admonition} Theory
:class: seealso
The micro-time filter construction (the weighted pseudo-inverse
$F=(D^\mathsf{T}WD)^{-1}D^\mathsf{T}W$), afterpulse removal, species auto/cross
correlations, and 2D-FLCS lifetime–lifetime maps are explained in the concept
page {ref}`concept-filtered-fcs`.
:::

## What it does

When two species share the same diffusion time but differ in **fluorescence
lifetime** (or spectrum, or polarisation), ordinary FCS cannot separate them.
**Filtered FCS** (Enderlein & Gregor 2005; Felekyan et al. 2012) uses the
micro-time (TCSPC) pattern as a fingerprint: from the species' reference decay
patterns it computes statistical **weighting filters** such that correlating the
filter-weighted photons yields the *species-selective* auto- and
cross-correlations. **2D-FLCS** extends this to a lifetime–lifetime correlation
map.

The filters are the weighted least-squares solution
$F = (D^\top W D)^{-1} D^\top W$ for the column-normalised pattern matrix $D$ and
the diagonal weight $W = \mathrm{diag}(1/I)$.

## In ChiSurf

```python
import numpy as np
from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters

patterns = np.vstack([decay_species_1, decay_species_2])   # normalised micro-time patterns
filters, reconstruction, weights = calc_ffcs_filters(total_decay, patterns)
# weight each photon by filters[:, its micro-time channel], then correlate
```

The `fcs_filter_calculator` and `flc_2d` plugins provide the interactive
filter-design and 2D-FLCS workflow, and the lifetime-FCS simulator closes the
loop for validation.

## Result

**Left:** two species with a long and a short lifetime and their measured mix.
**Right:** the statistical filters (from the real `calc_ffcs_filters`) — the
long-lifetime filter up-weights late micro-time channels, the short-lifetime
filter the early ones, so the filtered correlations separate the species.

```{figure} figures/filtered_fcs.png
:name: fig-filtered-fcs
:width: 90%

Filtered FCS patterns and filters.
```

## See also

- `chisurf/core/fluorescence/fcs/filtered.py`; plugins `fcs_filter_calculator`, `flc_2d`.
