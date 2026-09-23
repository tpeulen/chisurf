---
type: Guide
title: Enderlein MDF & two-focus FCS
description: The ordinary FCS models approximate the confocal detection volume by a 3-D Gaussian, which is only a rough description of a real confocal spot.
tags: [guides, fcs, enderlein, focus]
---

# Enderlein MDF & two-focus FCS

:::{admonition} Theory
:class: seealso
See {ref}`concept-fcs-correlation` for the FCS correlation function, the confocal volume, and the two-focus absolute-distance ruler.
:::

## What it does

The ordinary FCS models approximate the confocal detection volume by a 3-D
Gaussian, which is only a rough description of a real confocal spot. The
**molecule-detection function** (MDF; {cite}`enderlein2005`) is a more faithful,
semi-analytic profile — a **Gauss–Lorentz** shape built from the overlap of a
Gaussian excitation beam and a Gaussian-imaged pinhole, whose lateral width and
collection efficiency vary with axial position:

$$U(\rho,z) = \frac{\kappa(z)}{w(z)^2}\,e^{-2\rho^2/w(z)^2}\Big/\text{norm}.$$

It yields an accurate **effective volume**
$V_\text{eff}=\pi(\int\kappa\,dz)^2/\int(\kappa^2/w^2)\,dz$ — hence absolute
concentrations — and the diffusion autocorrelation without the Gaussian
approximation.

**Two-focus FCS** cross-correlates two foci a *known* distance `d` apart. The
lateral overlap of the two MDFs is attenuated by
$\exp[-d^2/(4D\tau + (w^2+w'^2)/2)]$, which decays with lag and yields an
**absolute** diffusion coefficient calibrated by `d` (no separate volume
calibration).

## In ChiSurf

### In the GUI: the FCS model

Load a correlation curve into an **FCS** fit (Kristine `.cor`, FCS-CSV,
Confocor3, …) and pick the model **FCS MDF (Gauss-Lorentz)**
(`MdfFCSModel`). Its editor has four panels:

- **Physical** — `N`, `D` [µm²/s], `w0` and `wem` [nm] (the excitation and
  emission/pinhole widths; `R0` in the core functions below), the offset `b`,
  the two-focus separation `d_foci` [nm] (`0` = single-focus
  auto-correlation) and a background rate `BG` [kHz].
- **Bunching terms** — optional extra exponential relaxations.
- **Optics** — `λex`, `λem`, refractive index `n`, pinhole [µm] and
  magnification, fixed by default.
- **Outputs** (computed) — `Veff` [fL], concentration `c` [nM], `τD` [ms] and
  brightness `ε` [kHz].

The model equation is shown on top: $G(\tau) = b + (1/N)\,
\text{MDF}_\text{Enderlein}(\tau; w_0, w_\text{em}, D)$; the lag axis is read in
**milliseconds**.

```{figure} figures/05_mdf_editor.png
:name: fig-mdf-editor
:width: 70%

The MDF model fitted to the bundled `test/data/fcs/kristine/Kristine_with_error.cor`
(lags > 1 µs): χ²ᵣ = 1.20 with `N` = 0.368, `D` = 379 µm²/s and `w0` = 521 nm
free. The errors (±362 µm²/s on `D`, ±282 nm on `w0`) show that one curve does not
separate `D` from the focus size; fixing `w0` = `wem` = 250 nm gives
`D` = 134 µm²/s at χ²ᵣ = 3.90. An absolute `D` needs the calibrated optics or the
two-focus `d_foci`.
```

The general composable model **GeneralFCSModel** offers MDF or the classic
3-D Gaussian as its diffusion term, with bunching/anticorrelation terms added.

### Headless

```python
import numpy as np
from chisurf.core.fluorescence.fcs import enderlein as en

tau = np.logspace(-6, -1, 120)               # seconds
auto  = en.g_diff(tau, w0=0.25, R0=0.25, diffusion=300.0, separation=0.0)   # µm, µm²/s
cross = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.5)          # 0.5 µm apart

veff = en.effective_volume(0.25, 0.25)       # µm^3 = fL  ->  absolute concentration
```

This runs in 0.4 s; `veff` = 2.727 fL (the same value the model's
**Outputs** panel shows for its default 250 nm widths), and the cross-correlation
peaks at τ ≈ 0.10 ms.

The diffusion autocorrelation is obtained by convolving the MDF with the 3-D
diffusion propagator; the lateral integral is analytic and the axial convolution
uses Gauss–Hermite quadrature in the difference direction, so the propagator is
resolved at any lag.

## Result

**Left:** the Gauss–Lorentz MDF $U(\rho,z)$ — the confocal detection profile,
elongated along the optical axis. **Right:** the single-focus autocorrelation
(blue) and the two-focus cross-correlation (red); the cross-correlation is
suppressed at short lag and peaks at a finite lag set by the transit time between
the foci — the signature that fixes an absolute `D`.

```{figure} figures/mdf.png
:name: fig-mdf
:width: 90%

Enderlein MDF and two-focus FCS.
```

## See also

- {src}`chisurf/core/fluorescence/fcs/enderlein.py` (`mdf`, `effective_volume`, `g_diff`, `acf`)
- Model: {src}`chisurf/core/models/fcs/mdf.py` (`MdfFCSModel`, table-view `mdf.view.json`), and the
  general composable model {src}`chisurf/core/models/fcs/general.py` (`GeneralFCSModel`), which lets
  you pick MDF vs. classic 3D-Gaussian diffusion and add bunching/anticorrelation terms.
- Tool: the **Diffusion/Volume Calculator** (`chisurf/plugins/fcs/fcs_calculator/`) converts
  τ, D, rₕ, V_eff, N and c — with the 3-D Gaussian volume
  $V_\text{eff}=\pi^{3/2}w_{xy}^3S$, not the MDF.
