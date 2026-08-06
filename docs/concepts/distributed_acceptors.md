---
type: Concept
title: Transfer to distributed acceptors, and dimensionality
description: Every expression in assumes one donor and one acceptor at one distance.
tags: [concepts, fret, distributed, acceptors]
anchor: concept-distributed-acceptors
---

(concept-distributed-acceptors)=
# Transfer to distributed acceptors, and dimensionality

Every expression in {ref}`concept-fret` assumes one donor and one acceptor at
one distance. That assumption fails whenever the acceptors are *not placed* but
*spread*: dye molecules dissolved in solution, lipid-attached probes across a
membrane, intercalators along a double helix. The donor is then surrounded by
many acceptors at many distances, and the quantity the experiment determines is
an acceptor **density**, not a distance.

The useful surprise is that the donor decay still has a closed form, and that
its shape depends on the **dimensionality** of the acceptor distribution. A
volume, a plane and a line give three different decay laws, distinguishable in
practice.

## The three decay laws

For a random distribution with no diffusion and no excluded volume,

$$
I_{DA}(t) = I_D^0 \exp\!\left[-\frac{t}{\tau_{D(0)}}
            - 2\,\eta_d\left(\frac{t}{\tau_{D(0)}}\right)^{d/6}\right],
\qquad
\eta_d = \tfrac{1}{2}\,\Gamma\!\left(1 - \tfrac{d}{6}\right)\frac{C}{C_0},
$$

with $d = 3, 2, 1$ for a volume, a plane and a line. The stretch exponent
$d/6$ — a half, a third, a sixth — is the signature. Written out:

| Dimensionality | Physical case | Exponent | $C_0$ | $\eta_d$ at $C=C_0$ |
|---|---|---|---|---|
| 3 | dyes in solution | $t^{1/2}$ | $\left(\tfrac{4}{3}\pi R_0^3\right)^{-1}$ | $\sqrt\pi/2 = 0.886$ |
| 2 | probes in a membrane | $t^{1/3}$ | $\left(\pi R_0^2\right)^{-1}$ | $0.677$ |
| 1 | intercalators along DNA | $t^{1/6}$ | $\left(2R_0\right)^{-1}$ | $0.564$ |

$C_0$ is defined so that $C/C_0$ is literally *the number of acceptors within
$R_0$ of the donor* — in a sphere of radius $R_0$, a circle of radius $R_0$, or
a segment of half-length $R_0$. That makes the density immediately interpretable
in a way a bare molar concentration is not.

```{figure} /guides/figures/distributed_acceptors.png
:alt: donor decays and transfer efficiencies for 1-, 2- and 3-dimensional acceptor distributions
:width: 100%

Left, on log time: at the same $C/C_0$ and the same $\tau_{D(0)}$, the curves
**cross**. Lower dimensionality quenches harder at short times — the $t^{1/6}$
term rises fastest — and less overall, because there are fewer directions from
which an acceptor can be close. Right: transfer efficiency against density, with
$C = C_0$ marked. Computed with
{src}`chisurf/core/fluorescence/fret/dimensionality.py#donor_decay`.
```

At $C = C_0$ the transfer efficiencies are **72.4 %, 67.2 % and 64.2 %** in
three, two and one dimensions.

:::{note}
The standard reference rounds the last two to 66 % and 63 %. Those do not
reproduce: the same integral evaluated both by adaptive quadrature and by a
dense trapezoid rule gives 67.2 % and 64.2 %, and the constants are exact gamma
values that the tests assert independently
(`test/fluorescence/test_fret_dimensionality.py`). The computed values are what
this page quotes.
:::

## What this changes about the experiment

**Concentrations must be high.** $C_0$ corresponds to a few to tens of
millimolar for typical Förster radii. That is orders of magnitude above the
concentrations used in single-molecule work — which is exactly why distributed
transfer is a non-issue there, and why it is unavoidable in a labelled membrane
where the *local* two-dimensional density is high even though the bulk
concentration is not.

**The observable is a density, not a distance.** Fitting a single distance to a
distributed acceptor population returns a number with no physical referent.
Conversely, a measured $C/C_0$ combined with a known $R_0$ gives the surface
density of acceptors, which for a membrane is a real structural quantity.

**The decay is non-exponential by construction.** A stretched exponential with
$t^{1/6}$ has infinite slope at the origin and no characteristic time. A sum of
exponentials will fit it, and the components will not be species — the same trap
as in {ref}`concept-maximum-entropy`, reached from a different direction. If a
multi-exponential fit of a membrane donor returns three lifetimes, ask whether
the model should have been this one instead.

**Dimensionality is itself measurable.** The three laws are distinguishable:
data generated in one dimensionality cannot be fitted acceptably by the law for
another. That makes the decay shape a probe of the *geometry* the acceptors
occupy, not just of how many there are — which is how the approach is used to
ask whether probes are confined to a plane or leaking into the volume.

## Assumptions, and when they break

- **No diffusion.** Donor–acceptor diffusion during the excited-state lifetime
  brings fresh acceptors into range and increases transfer above these
  expressions. In fluid membranes at room temperature this is not negligible;
  the frozen-solution case is where the closed forms are exact.
- **No excluded volume.** Acceptors are allowed arbitrarily close to the donor.
  A real molecule has a distance of closest approach, which reduces the
  early-time quenching most — the same region where the dimensionality
  signature lives.
- **Random distribution.** Clustering, phase separation or binding all break it,
  and they do so by producing a *local* density that is not the mean density.
  This is a feature if clustering is the question and a systematic error if it
  is not.
- **$\kappa^2 = 2/3$**, folded into $R_0$ as always. A rotationally frozen
  three-dimensional solution averages to $\langle\kappa^2\rangle = 0.476$
  instead and needs 1.18-fold more acceptor for the same transfer
  ({ref}`concept-kappa2-orientation`).
- **One donor population.** Homo-transfer between donors is assumed absent,
  which requires the donor concentration to be low even when the acceptor
  concentration is high ({ref}`concept-energy-migration`).

## Fitting it

The model is **FRET: distributed acceptors** in the model selector. It releases
the density `C/C0` and the donor lifetimes, and the dimensionality is a radio
button rather than a fitted parameter — the three laws are distinguishable, so
the right way to choose is to fit each and compare, not to let an optimizer
wander between them.

Two things about it are deliberate and worth knowing before you reach for a
control that is not there:

- **There is no anisotropy panel.** The polarized channels are built from a
  lifetime spectrum, and this decay is a stretched exponential rather than a
  finite mixture, so there is nothing to hand the anisotropy mixing. Fit
  magic-angle or total decays.
- **There is no distance.** The fitted quantity is a density; $R_0$ and
  $\tau_{D(0)}$ are *inputs* that define $C_0$, so changing them rescales the
  reported density rather than improving the fit. They are fixed by default for
  that reason.

### Choosing the geometry: fit all three

The dimensionality is not fitted, so the way to establish it is to fit each and
compare. That works because the wrong law does not merely fit slightly worse —
it fits *hopelessly* worse. Fitting simulated decays (donor $\tau_{D(0)} = 4$ ns,
no convolution, density released from a deliberately wrong start):

| Simulated | Fitted as 1-D | Fitted as 2-D | Fitted as 3-D |
|---|---|---|---|
| **1-D**, $C/C_0 = 1.7$ | **1.700**, SSR 2e-14 | 0.931, SSR 2e-03 | 0.595, SSR 8e-03 |
| **2-D**, $C/C_0 = 1.3$ | 1.820, SSR 2e-02 | **1.300**, SSR 3e-14 | 0.866, SSR 7e-03 |
| **3-D**, $C/C_0 = 0.9$ | 1.415, SSR 7e-02 | 1.070, SSR 2e-02 | **0.900**, SSR 1e-13 |

The right law recovers the density exactly and the residual falls to numerical
noise; the wrong ones are eight to eleven orders of magnitude worse. On real
data the separation is smaller — noise, an imperfect instrument response and a
donor that is not single-exponential all narrow it — but the ordering is robust,
and this is what makes the decay shape a measurement of geometry rather than an
assumption about it.

:::{warning}
Note what the wrong rows still do: they return a **plausible** density. Fitting
1-D data with the 2-D law gives $C/C_0 = 0.93$ rather than 1.7 — a number that
looks perfectly reasonable and is wrong by 45 %. Reporting a density without
having compared the three geometries is reporting an assumption.
:::

The panel reports the implied transfer efficiency and the absolute density
alongside `C/C0`. Both are computed from the fitted density, so neither carries
an error bar of its own — propagate the uncertainty on `C/C0` instead
({ref}`concept-parameter-uncertainty`).

## Using it headlessly

The functions are Qt-free and usable directly:

```python
import numpy as np
from chisurf.core.fluorescence.fret.dimensionality import (
    characteristic_density, donor_decay, transfer_efficiency,
)

r0 = 52.0                                   # Angstrom
c0 = characteristic_density(r0, dimension=2)   # acceptors per A^2
print(f"one acceptor per {1/c0:.0f} A^2")

t = np.linspace(0.0, 20.0, 512)             # ns
decay = donor_decay(t, tau_d0=4.0, c_over_c0=0.8, dimension=2)
print(transfer_efficiency(0.8, dimension=2))
```

To go from a measured surface density $\sigma$ (acceptors per Å²) to the
argument these take, divide by $C_0$: `c_over_c0 = sigma / c0`.

## See also

- Fundamentals: {ref}`fundamentals-energy-transfer` (the $1/R^6$ mechanism these
  laws integrate over).
- Related concepts: {ref}`concept-fret` (the single-distance case) ·
  {ref}`concept-distance-distributions` (a distribution of *linked* pairs, which
  is a different problem) · {ref}`concept-energy-migration` ·
  {ref}`concept-kappa2-orientation` · {ref}`concept-maximum-entropy`.
- Guide: {doc}`/guides/03_polymer_distance_distributions` — the linked-pair
  alternative, for when the acceptor is attached rather than dissolved.
- Implementation: the fittable model
  `chisurf/core/models/tcspc/distributed_acceptor.py`
  (`DistributedAcceptorModel`) with its editor layout
  `distributed_acceptor.view.json`; the physics in
  {src}`chisurf/core/fluorescence/fret/dimensionality.py#donor_decay` ·
  {src}`chisurf/core/fluorescence/fret/dimensionality.py#characteristic_density`
  · {src}`chisurf/core/fluorescence/fret/dimensionality.py#transfer_efficiency`;
  tests in `test/fluorescence/test_fret_dimensionality.py`.
- Literature: {cite}`lakowicz2006`, the chapter on energy transfer to multiple
  acceptors in one, two or three dimensions.
