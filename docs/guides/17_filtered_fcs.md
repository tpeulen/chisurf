---
type: Guide
title: Filtered FCS (fFCS / 2D-FLCS)
description: When two species share the same diffusion time but differ in fluorescence lifetime (or spectrum, or polarisation), ordinary FCS cannot separate them.
tags: [guides, fcs, diffusion, tcspc, lifetime]
---

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
**Filtered FCS** ({cite}`gregor2005,felekyan2012`) uses the
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

If the total decay has empty micro-time bins where a pattern still has weight
(for example a decay gated to a PIE window against an ungated pattern), pass
`empty_bins="exclude"` so those bins are left out instead of being weighted as
one-photon bins; see "Empty bins" in {ref}`concept-filtered-fcs`. For parallel
and perpendicular detectors sharing one filter, concatenate their decays and
patterns on one micro-time axis.

The `fcs_filter_calculator` and `flc_2d` plugins provide the interactive
filter-design and 2D-FLCS workflow, and the lifetime-FCS simulator closes the
loop for validation.

### Instrument parameters

When a species is a coupled smFRET decay rather than a plain lifetime spectrum,
its green/red/yellow patterns depend on the correction factors, so the filter
calculator carries an **Instrument** dock holding $\alpha$ (donor leakage),
$\beta$ (excitation-flux ratio of the acceptor to the donor laser), $\gamma$
(detection / quantum yield), $\delta$ (direct acceptor excitation), the
polarization calibration $G$, $l_1$, $l_2$, the Förster radius $R_0$ and the
laser period.

These are **pre-filled from the detector setup** you pick at the top of the
panel. Measure them once with the [Accurate FRET tool](41_accurate_fret.md) and
press *🔬 Store on setup*; every later session that selects the same setup starts
from the measured values instead of the defaults. Anything you edit here wins
over the stored value for the current session.

```{note}
$\beta$ is a *ratio*, so its neutral value is **1**, not 0. The excitation
matrix is $\begin{pmatrix}1 & \delta\\ 0 & \beta\end{pmatrix}$: at $\beta = 0$
the acceptor laser excites nothing and the acceptor-excitation (yellow) pattern
is identically zero, which silently removes that channel from the filters.
```

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

- {src}`chisurf/core/fluorescence/fcs/filtered.py`; plugins `fcs_filter_calculator`, `flc_2d`.
- Tool: the **FCS Filter Calculator** (`chisurf/plugins/fcs/fcs_filter_calculator/`) and **2D-FLCS** (`chisurf/plugins/fcs/flc_2d/`).
