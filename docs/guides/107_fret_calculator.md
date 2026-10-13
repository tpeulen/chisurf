---
type: Guide
title: The FRET calculator
description: 'Tool: Tools → FRET-Calculator (fret_calculator). Converts between donor-acceptor distance, lifetime, efficiency and transfer rate for a single distance or a distance distribution, and between anisotropy migration time and distance for homo-FRET.'
tags: [guides, fret, calculators]
---

# The FRET calculator

**Tool:** *Tools → FRET-Calculator* (`fret_calculator`). **What you get:** the four linked quantities of a
donor-acceptor pair, $R$, $\tau_\mathrm{DA}$, $E$ and $k_\mathrm{FRET}$, for given $R_0$ and $\tau_{D0}$, with the
distance and rate distributions drawn. Use it to plan an experiment ("which efficiency will a 45 Å pair give?") and
to read a measured efficiency or lifetime as a distance. Theory: [FRET](../concepts/fret.md) and
[energy migration](../concepts/energy_migration.md).

## 1. HeteroFRET

```{figure} figures/107_fret_calculator.png
:name: fig-fret-calculator
:width: 100%

HeteroFRET at $\tau_{D0}$ = 4 ns, $R_0$ = 52 Å, $R$ = 50 Å, σ = 6 Å. Left, the linked fields; right, the Gaussian
(solid) and non-central χ (dashed) distance distribution and the transfer-rate distribution each induces.
```

The fields are $\tau_{D0}$ (donor without acceptor), $R_0$, $R$, $\tau_\mathrm{DA}$, $E$, $k_\mathrm{FRET}$ and the
width σ. Edit one and the others follow:

- Editing $\tau_{D0}$, $R_0$, $R$ or σ computes $E$, $\tau_\mathrm{DA}$ and $k_\mathrm{FRET}$ from $R$.
- Editing $\tau_\mathrm{DA}$, $E$ or $k_\mathrm{FRET}$ solves for the distance.

With σ > 0 the efficiency is averaged over the distance distribution, $\langle E\rangle=\sum_i p(R_i)\,E(R_i)$,
and $\tau_\mathrm{DA}=\tau_{D0}(1-\langle E\rangle)$. The rate shown is the one consistent with $\langle E\rangle$,
$k=\langle E\rangle/\bigl((1-\langle E\rangle)\tau_{D0}\bigr)$, because the mean of $k(R)\propto R^{-6}$ diverges at
contact. The inverse fields (lifetime, efficiency, rate to distance) describe one effective distance and are not
the exact inverse of a broad distribution. The **χ distribution** toggle replaces the Gaussian by the radial
distribution of an isotropic three-dimensional Gaussian, which is non-negative and vanishes at contact; $\kappa^2$ is fixed at 2/3.
For a case with the example's numbers: 50 Å, σ 6 Å, $R_0$ 52 Å gives $\langle E\rangle$ = 0.560 and
$\tau_\mathrm{DA}$ = 1.76 ns (Gaussian).

## 2. HomoFRET

The second tab links the anisotropy migration time $t_\mathrm{RM}$ and the rotational correlation time ρ to the
energy-migration rate and an effective distance,

$$
k_\mathrm{homo}=\tfrac12\left(\frac1{t_\mathrm{RM}}-\frac1{\rho}\right),\qquad
R_\mathrm{DA}=R_0\,(k_\mathrm{homo}\tau_{D0})^{-1/6}.
$$

Edit $t_\mathrm{RM}$ to compute the distance; edit the distance to solve back for $t_\mathrm{RM}$. The migration
rate is an output. A $t_\mathrm{RM}\ge\rho$ gives zero rate and no distance.

## 3. Python

The calculation is Qt-free:

```python
from chisurf.plugins.calculator.fret_calculator.core.algorithms import (
    compute_fret_from_distance, compute_fret_from_efficiency, compute_homo_fret,
)

compute_fret_from_distance(R=50.0, R0=52.0, tau0=4.0, sigma=6.0, distribution="gaussian")
# {'E': ..., 'tau_DA': ..., 'kFRET': ..., ...}
compute_fret_from_efficiency(E=0.5, R0=52.0, tau0=4.0)   # the effective distance
compute_homo_fret(t_RM=1.0, rho=10.0, tau0=4.0, R0=52.0)
```

The same functions are the `fret_calculator.*` services of the plugin. Settings of the last session are restored
when the window reopens. The window has **Guide** and **Help** buttons.

## Theory

[FRET](../concepts/fret.md), [energy migration](../concepts/energy_migration.md); the Förster radius itself is
computed in [Spectra, overlap integrals and R₀](83_spectra_and_r0.md). Tool: FRET-Calculator
(`chisurf/plugins/calculator/fret_calculator/`).
