---
type: Guide
title: Diffusion FCS
description: Fluorescence correlation spectroscopy (FCS) measures the temporal autocorrelation of fluorescence fluctuations as molecules diffuse through the confocal volume.
tags: [guides, diffusion, fcs]
---

# Diffusion FCS

**Fluorescence correlation spectroscopy (FCS)** measures the temporal
autocorrelation of fluorescence fluctuations as molecules diffuse through the
confocal volume. The correlation amplitude gives the mean number of molecules
$N$ (hence the concentration); the decay time gives the diffusion time $\tau_D$
(hence the diffusion coefficient / hydrodynamic radius); fast photophysics
(triplet blinking) adds a short-lag shoulder.

:::{admonition} Theory
:class: seealso
The physics — the $G(\tau)$ decomposition, the confocal Gaussian volume, the
$\tau_D$-vs-$D$ parameterizations, and the photodynamic factors — is in the
concept page {ref}`concept-fcs-correlation`. This guide shows how to run the
analysis in ChiSurf.
:::

## In ChiSurf

Correlation curves are computed from TTTR photon data by the **`fcs_correlator`**
plugin (multi-tau, with optional fine/ns-scale correlation; see
{doc}`16_fret_fcs` and {doc}`17_filtered_fcs`) and fitted in the **FCS
experiment** against the model catalogue in
{src}`chisurf/core/models/fcs/models.yaml`.

The **composable FCS model editor** builds the correlation function from
independent factors — pick a diffusion geometry, then add bunching /
anti-correlation terms as needed:

```{figure} figures/fcs_model_editor.png
:name: fig-fcs-model-editor
:width: 90%

The composable FCS model editor. The **Type** selector switches the diffusion
term (MDF / single-focus Gauss / two-focus). The live **Equation** box shows the
currently active $G(\tau)$; the parameter table exposes $N$, the diffusion
coefficient $D$, the lateral/axial waists $w_r$/$w_z$, the offset $b$, and the
background rate `BG`. **Bunching**, **Anticorr**, and **Outputs** fold-outs add
triplet/blinking, reaction dynamics, and derived quantities ($V_\text{eff}$,
concentration, brightness).
```

Each row of the parameter table in {numref}`fig-fcs-model-editor` maps onto the
theory in {ref}`concept-fcs-correlation`: $N$ is the amplitude ($G(0)=1/N$),
$D$/$w_r$/$w_z$ set the diffusion shoulder via $\tau_D=w_r^2/4D$, `BG` drives the
$(1-B/I)^2$ background correction, and the Bunching/Anticorr terms are the
photodynamic factor $P(\tau)$.

### Steps

1. Correlate a photon stream with the **FCS Correlator** (or load a `.cor`/
   Kristine curve) — see {doc}`12_handling_tttr_files` for reading TTTR data.
2. Add an **FCS fit** on the resulting curve; the model editor
   ({numref}`fig-fcs-model-editor`) opens.
3. Choose the diffusion **Type** and, if the curve rises at short lag, add a
   **Bunching** term (triplet). Fit.
4. Read $N$, $D$ (or $\tau_D$) and the derived concentration/brightness from the
   **Outputs** panel.

### Headless / scripting

The same model computes without the GUI:

```python
import numpy as np

def g_3d_gauss(tau, N, td, s, trip_a=0.0, trip_t=1e-6):
    g = (1.0 / N) / (1 + tau / td) / np.sqrt(1 + (tau / td) / s ** 2)
    return g * (1 - trip_a + trip_a * np.exp(-tau / trip_t))

tau = np.logspace(-6, 0, 300)          # seconds
G = g_3d_gauss(tau, N=2.0, td=1e-4, s=5.0, trip_a=0.2, trip_t=3e-6)
```

## Result

The 3-D Gaussian diffusion correlation for three diffusion times (faster
diffusion → shorter decay), and the effect of adding a triplet term (dashed): a
short-lag rise above the diffusion plateau.

```{figure} figures/fcs_diffusion.png
:name: fig-fcs-diffusion
:width: 80%

3-D Gaussian diffusion FCS for three diffusion times, with (dashed) and without
a triplet term.
```

## See also

- Concept: {ref}`concept-fcs-correlation` · all FCS plugins:
  {doc}`/reference/plugins/index`.
- Model catalogue: {src}`chisurf/core/models/fcs/models.yaml`; correlator:
  `chisurf/plugins/fcs/fcs_correlator/`.
- Absolute concentrations & two-focus: {doc}`05_enderlein_mdf_two_focus_fcs`.
- Higher-order statistics: {doc}`06_nsfcs_second_order`.
