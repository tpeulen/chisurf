---
type: Guide
title: RCM from FRET-labelled samples (PIE/ALEX)
description: The dye-solution RCM calibration needs separate donor-only and acceptor-only reference solutions.
tags: [guides, fret, calibration]
---

# RCM from FRET-labelled samples (PIE/ALEX)

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the E/S corrections and the calibration factors.
:::

## What it does

The [dye-solution RCM calibration](07_rcm_calibration.md) needs separate
donor-only and acceptor-only reference solutions. When only **doubly-labelled
FRET samples** measured under **PIE/ALEX** are available, the detection-correction
matrix can instead be obtained from the sample itself: the acceptor-excitation
(Aex) period isolates the acceptor detection, and the donor-excitation (Dex)
period the donor + sensitised-acceptor, so the same linear relations between
channel rates that define the RCM can be solved from the ALEX sub-populations
(donor-only, acceptor-only and FRET species that the [E–S histogram](14_multiparameter_es.md)
separates).

## In ChiSurf

The correction machinery lives in {src}`chisurf/core/fluorescence/fret/calibration.py`
(γ/β, leakage, direct excitation, and the routing-correction matrix), and the
ALEX/PIE stream handling in {src}`chisurf/core/fluorescence/burst/es.py`. The
E–S-based `global_es_correction` / `refine_calibration` derive the correction
factors from the sample's own donor-only / acceptor-only / FRET populations; the
`ptu_alex_creator` and micro-time-gating tools prepare PIE/ALEX streams.

```python
from chisurf.core.fluorescence.fret import calibration as cal

calib = cal.calibrate_from_samples(cal.CalibrationParameters(), fret,
                                   donor_only=..., acceptor_only=...)
```

## Result

Applying the factors recovered from the sample's own ALEX sub-populations moves
each FRET population from its *apparent* efficiency to its *accurate* one. The
donor-only and acceptor-only corners are what pin $\alpha$ and $\delta$; the two
FRET populations pin $\gamma$ and $\beta$.

```{figure} figures/rcm_alex.png
:name: fig-rcm-alex
:width: 95%

Simulated PIE/ALEX data with a known instrument
($\gamma=1.35$, $\alpha=0.09$, $\delta=0.06$, $\beta=0.95$). **Left:** the raw
$E_\text{app}$/$S_\text{app}$ map. **Right:** after correction — the two FRET
populations land on their true efficiencies (dashed lines at E = 0.30 and 0.70),
computed with the real `corrected_es`.
```

## See also

- {src}`chisurf/core/fluorescence/fret/calibration.py`, `.../burst/es.py`; the dye-solution route: [RCM calibration](07_rcm_calibration.md).
- The full correction algebra and the general crosstalk-matrix form: [accurate FRET calibration](fret_calibration.md).
- The E–S map these populations are read from: [multi-parameter E–S](14_multiparameter_es.md).
- Tool: **Accurate FRET** (`chisurf/plugins/burst/accurate_fret/`).
