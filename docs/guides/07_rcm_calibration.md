---
type: Guide
title: RCM detection calibration from dye solutions
description: Quantitative multi-parameter fluorescence needs the detection/routing correction matrix (RCM) — the linear map that corrects measured per-channel count rates for detection efficiencies and cross-talk between the spectral (and…
tags: [guides, calibration, corrections, spectra]
---

# RCM detection calibration from dye solutions

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the FRET-efficiency corrections that calibration determines.
:::

## What it does

Quantitative multi-parameter fluorescence needs the **detection/routing
correction matrix (RCM)** — the linear map that corrects measured per-channel
count rates for detection efficiencies and cross-talk between the spectral (and,
with a polarising beam-splitter, polarisation) channels. Instead of entering
correction factors by hand, the RCM can be **calibrated from two reference
measurements**: a **donor-only** and an **acceptor-only** dye solution.

From the per-channel count rates of the two solutions, their relative absorbance
$\alpha = A_A/A_D$ and the detector layout (which channels are acceptor/donor,
and their polarisation), a small linear system is solved for the RCM. It supports
a 2-channel setup and a 4-channel setup (a polarising beam splitter, using the
dye anisotropies, or a 50/50 split).

## In ChiSurf

```python
from tttrlib import rcm_from_dye_solutions

assignment = [("A", "P"), ("D", "P"), ("A", "S"), ("D", "S")]   # per channel: (species, pol.)
donor    = [0.06, 1.00, 0.05, 0.95]   # background-corrected rate/channel, donor solution
acceptor = [1.00, 0.04, 0.90, 0.03]   # ... acceptor solution

rcm = rcm_from_dye_solutions(
    donor, acceptor,
    absorbance_ratio=1.15,
    detector_assignment=assignment,
    anisotropy=(0.20, 0.15),          # (r_donor, r_acceptor) for a polarising BS
)
```

The returned matrix is the identity on unused channels and normalised so its
first ordered element is 1; apply it to measured channel rates to obtain
corrected, species-resolved signals. For the rates above it is

```text
[[ 1.    -0.06   0.     0.   ]
 [-0.037  0.915  0.     0.   ]
 [ 0.     0.     0.726 -0.038]
 [ 0.     0.    -0.018  0.55 ]]
```

one 2 × 2 block per polarisation, the off-diagonal terms being the donor→acceptor
leakage and acceptor→donor cross-talk.

There is no GUI for this calibration: `tttrlib.rcm_from_dye_solutions` is an API
function. The **Accurate FRET** tool determines the scalar factors α, δ, γ and β
from the bursts of a FRET sample instead (see
[Multi-parameter E–S histograms](14_multiparameter_es.md) and
[RCM from FRET samples](25_rcm_from_fret_samples.md)).

## Result

The correction matrix recovered for a 4-channel polarising-beam-splitter setup
with mild inter-channel leakage. Off-diagonal elements encode the cross-talk the
matrix removes; the block structure reflects the parallel/perpendicular split.

```{figure} figures/rcm.png
:name: fig-rcm
:width: 90%

Routing-correction matrix from dye solutions.
```

## See also

- `tttrlib.rcm_from_dye_solutions` (with tttrlib's γ/β/leakage/direct-excitation
  estimators); {src}`chisurf/core/fluorescence/fret/calibration.py` holds the
  calibration parameters.
- Related tool: **Accurate FRET** (`chisurf/plugins/burst/accurate_fret/`), which
  estimates α/δ/γ/β from bursts rather than the channel matrix from dye solutions.
