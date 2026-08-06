---
type: Fundamentals
title: Resonance energy transfer
description: Förster transfer is dipole–dipole coupling between an excited donor and a ground-state acceptor whose absorption overlaps the donor's emission.
tags: [fundamentals, energy, transfer]
anchor: fundamentals-energy-transfer
---

(fundamentals-energy-transfer)=
# Resonance energy transfer

Förster transfer is dipole–dipole coupling between an excited donor and a
ground-state acceptor whose absorption overlaps the donor's emission. This page
covers where the $1/R^6$ dependence and the Förster radius come from, what
$\kappa^2$ actually is, and the averaging regimes that decide whether $2/3$ is
an acceptable assumption. The measurement of $E$, the correction factors, and
the distance precision are in {ref}`concept-fret` and
{ref}`concept-accurate-fret`.

## Mechanism

Transfer is non-radiative. No photon is emitted and reabsorbed; the two
transition dipoles are coupled through the near field. The coupling energy
between two dipoles falls as $1/R^3$, and the rate goes as the square of the
coupling, hence $1/R^6$. This was confirmed experimentally on poly-L-proline
oligomers of known length, which is worth knowing because the $1/R^6$ law is
occasionally described as an assumption rather than a measured result.

The transfer rate is

$$
k_T(R) = \frac{1}{\tau_{D(0)}}\left(\frac{R_0}{R}\right)^{6},
$$

which is the general rate expression from
{ref}`fundamentals-lifetime-quantum-yield` with $k_X = k_T$. Substituting gives
the efficiency

$$
E = \frac{k_T}{\tau_{D(0)}^{-1} + k_T} = \frac{R_0^6}{R_0^6 + R^6}.
$$

Note what the $1/\tau_{D(0)}$ prefactor implies: the transfer rate scales with
the donor's *emission* rate, so a long-lived donor does not reach further. A
donor with a 10 ms lifetime and one with a 10 ns lifetime transfer at the same
efficiency at the same $R_0$. This is why lanthanide donors, despite
millisecond lifetimes, work over ordinary FRET distances.

Two mechanisms are sometimes confused with Förster transfer and are not it.
**Dexter exchange** requires wavefunction overlap, falls off exponentially, and
is only relevant at van der Waals contact. **Trivial reabsorption** — the donor
emits a photon and the acceptor absorbs it — depends on sample geometry and
concentration rather than on the donor–acceptor distance, and it is suppressed
by working optically dilute.

Transfer between chemically identical molecules (**homo-transfer**) obeys the
same physics and is common for dyes with small Stokes shifts. It does not change
the fluorescence lifetime, because donor and acceptor are the same species, but
it does depolarize the emission — which is how it is usually detected
({ref}`fundamentals-polarization`).

```{figure} /guides/figures/energy_transfer_window.png
:alt: FRET efficiency against R/R0 and the distance error it implies
:width: 100%

Left: $E(R)$, with the usable window shaded — 98.5% at $0.5R_0$ and 1.5% at
$2R_0$. Right: the distance error a fixed $\Delta E = 0.01$ produces. It is
minimal at $R_0$ and rises steeply either side, which is why choosing a dye pair
is choosing the window the experiment can see.
```

## The Förster radius

$R_0$ is the distance at which transfer and all other de-excitation routes are
equally probable, so $E = 0.5$. It is computed, not fitted:

$$
R_0^6 \;\propto\; \kappa^2\, n^{-4}\, Q_D\, J,
$$

with $\kappa^2$ the orientation factor, $n$ the refractive index of the medium
between the dyes, $Q_D$ the donor quantum yield in the *absence* of acceptor,
and $J$ the spectral overlap integral

$$
J = \frac{\int F_D(\lambda)\,\varepsilon_A(\lambda)\,\lambda^4\,\mathrm{d}\lambda}
         {\int F_D(\lambda)\,\mathrm{d}\lambda},
$$

where $F_D$ is the donor emission spectrum (its absolute scale cancels) and
$\varepsilon_A$ the acceptor molar extinction coefficient — the real one, in
M⁻¹ cm⁻¹, not a peak-normalized spectrum. The $\lambda^4$ weighting is why
red-shifted pairs give large $R_0$ even at modest overlap.

Because every factor enters under a sixth root, $R_0$ is remarkably tolerant of
errors in its inputs: a factor-of-two error in $Q_D$ moves $R_0$ by about 12%,
and a 40% error in $J$ by under 6%. This tolerance is what makes FRET a usable
ruler despite the difficulty of measuring its inputs — and it is also why
reported $R_0$ values that disagree by 10% between sources are not evidence that
one is wrong.

What the sixth root does *not* forgive is $\kappa^2$, which can legitimately
range over three orders of magnitude.

:::{warning}
Three conventions are folded into any quoted $R_0$ and none of them is visible
in the number: the assumed $\kappa^2$ (almost always $2/3$), the refractive
index (1.33 for water, 1.4 is also common for a protein interior), and the donor
quantum yield in the specific environment measured. A tabulated $R_0$ is a
property of a dye pair *in some conditions*, not a constant. ChiSurf's
implementation defaults to $\kappa^2 = 2/3$ and $n = 1.33$
({src}`chisurf/core/fluorescence/fret/forster.py#forster_radius`); the units
convention is $J$ in M⁻¹ cm⁻¹ nm⁴, and the function returns $R_0$ in ångström
even though the underlying prefactor $0.02108$ yields nanometres. Literature
formulas working in ångström use a prefactor of $9.78\times10^3$ instead.
:::

## The orientation factor

$\kappa^2$ describes the mutual geometry of the donor emission dipole and the
acceptor absorption dipole:

$$
\kappa^2 = \left(\cos\theta_T - 3\cos\theta_D\cos\theta_A\right)^2,
$$

with $\theta_T$ the angle between the two dipoles, and $\theta_D$, $\theta_A$
the angles each makes with the vector joining them. It ranges from 0 to 4:
$\kappa^2 = 4$ for collinear head-to-tail dipoles, $1$ for parallel dipoles, and
$0$ for perpendicular dipoles — and also $0$ for certain non-perpendicular
arrangements, which is the case that causes trouble.

Which value to use depends entirely on how much the dipoles reorient during the
excited-state lifetime:

- **Dynamic averaging.** Both dyes rotate freely and fully within the donor
  lifetime, so every orientation is sampled and $\langle\kappa^2\rangle = 2/3$.
  This is the standard assumption and the one built into tabulated $R_0$ values.
- **Static isotropic distribution.** The dyes are randomly but *rigidly*
  oriented and do not move during the lifetime. The population average is then
  $\langle\kappa^2\rangle = 0.476$, not $2/3$, and each molecule has its own
  transfer rate, which broadens the distribution of measured efficiencies rather
  than merely shifting it.
- **Restricted.** The realistic case for linker-attached dyes: partial
  reorientation, bounded by the residual anisotropies.

The sixth root again limits the damage. Varying $\kappa^2$ between 1 and 4
changes the distance by only 26%, and relative to the assumption $\kappa^2=2/3$
the error is at most about 35%. The failure mode is $\kappa^2 \to 0$, where the
computed distance diverges.

The defence is experimental, not theoretical: measure the residual anisotropy of
donor and acceptor and use it to bound the possible range of $\kappa^2$
({ref}`fundamentals-polarization`, following {cite}`dale1979`). Dyes with substantial local mobility —
which is what a long flexible linker is for — and fundamental anisotropies below
0.4 restrict the range considerably, typically to distance errors under 10%.
ChiSurf computes these bounds and the resulting distance distributions directly
({src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq_all_delta`).

## Beyond a single fixed distance

The efficiency expression above assumes one donor, one acceptor, one distance.
Each of these fails in a common situation, and each failure has its own
treatment:

- **A distribution of distances.** A flexible linker or a conformationally
  heterogeneous molecule gives a distribution $p(R)$, and the measured
  efficiency is an average over it. Because $E(R)$ is steep and non-linear, that
  average is not $E(\langle R\rangle)$ — a symmetric $p(R)$ produces an
  asymmetric distribution of efficiencies biased toward the high-$E$ side. The
  donor decay in the presence of acceptor is what carries the information about
  the width ({ref}`concept-mfd-fitting`).
- **The dyes move.** The distance itself fluctuates during the lifetime. Whether
  the average is taken over the rate or over the distance depends on how fast
  that motion is relative to $\tau_{D(0)}$ — the same fast/slow distinction as
  for $\kappa^2$.
- **The dye is not at the attachment point.** A linker places the fluorophore in
  a cloud of accessible positions several ångström from the labelled residue.
  Comparing a measured distance to a structure requires modelling that cloud
  ({ref}`concept-accessible-volume`).
- **More than one acceptor.** With acceptors distributed in a plane or a volume
  rather than at a point, the donor decay follows a different functional form
  entirely, and the useful observable becomes the acceptor surface density
  rather than a distance.

## Working range

$E$ is a steep function of $R/R_0$, which is what makes it a precise ruler near
$R_0$ and useless away from it. At $R = 2R_0$ the efficiency is about 1.5%; at
$R = 0.5R_0$ it is about 98.5%. Outside roughly $0.5R_0$ to $2R_0$ the
efficiency no longer changes measurably with distance, so distances in that
range are not determined regardless of how many photons are collected. Choosing
a dye pair is therefore choosing the window the experiment can see.

## See also

- Previous: {ref}`fundamentals-polarization`. Next:
  {ref}`fundamentals-fluorophores`.
- Concepts: {ref}`concept-fret` (efficiency, precision, the ruler) ·
  {ref}`concept-accurate-fret` (correction factors) ·
  {ref}`concept-smfret-bursts` · {ref}`concept-accessible-volume`.
- Implementation:
  {src}`chisurf/core/fluorescence/fret/forster.py#overlap_integral` ·
  {src}`chisurf/core/fluorescence/fret/forster.py#forster_radius` ·
  {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq_all_delta`.
- Literature: {cite}`foerster1948` · {cite}`dale1979` for the $\kappa^2$
  bounds · {cite}`lakowicz2006`, energy-transfer
  chapters · {cite}`hellenkamp2018` for the measurement conventions.
