---
type: Concept
title: The orientation factor κ² and what it costs
description: The Förster radius contains $kappa^2$, the mutual orientation of the donor emission dipole and the acceptor absorption dipole.
tags: [concepts, kappa2, orientation]
anchor: concept-kappa2-orientation
---

(concept-kappa2-orientation)=
# The orientation factor κ² and what it costs

The Förster radius contains $\kappa^2$, the mutual orientation of the donor
emission dipole and the acceptor absorption dipole. Every tabulated $R_0$ assumes
$\kappa^2 = 2/3$, and every distance derived from it inherits that assumption.
This page is about when the assumption holds, what to do when it does not, and
how ChiSurf turns measured anisotropies into a *bounded* distance error rather
than an unbounded one.

The physics of the transfer itself is in {ref}`fundamentals-energy-transfer`;
the anisotropy measurement that feeds this page is in {ref}`concept-anisotropy`.
For the calculator, see {doc}`/guides/61_kappa2_distribution`.

## The geometry

With $\theta_T$ the angle between the two dipoles and $\theta_D$, $\theta_A$ the
angles each makes with the donor–acceptor vector,

$$
\kappa^2 = \left(\cos\theta_T - 3\cos\theta_D\cos\theta_A\right)^2
         = \left(\sin\theta_D\sin\theta_A\cos\varphi
                 - 2\cos\theta_D\cos\theta_A\right)^2,
$$

where $\varphi$ is the angle between the two planes. The range is $0 \le
\kappa^2 \le 4$: collinear head-to-tail dipoles give 4, parallel dipoles give 1,
and perpendicular dipoles give 0 — as do several non-perpendicular
arrangements, which is the case that actually causes trouble.

Because $R \propto (\kappa^2)^{1/6}$ at fixed efficiency, the sixth root damps
most of this. The whole range from $\kappa^2 = 1$ to $4$ is a 26% change in
distance; relative to the $2/3$ assumption the error is bounded by about 35% on
the high side. The failure is entirely at the bottom: as $\kappa^2 \to 0$ the
inferred distance diverges.

## Which average applies

$\kappa^2$ is not a constant to be measured once. What enters $R_0$ is an
average, and *which* average depends on how fast the dipoles reorient relative to
the donor lifetime.

**Dynamic (isotropic) averaging.** Both dyes explore all orientations within
$\tau_{D(0)}$. Then $\langle\kappa^2\rangle = 2/3$ and every molecule has the
same transfer rate. This is the standard assumption, and it is what a long
flexible linker is for.

**Static isotropic distribution.** The dyes are randomly oriented but frozen on
the lifetime timescale. The population average is
$\langle\kappa^2\rangle = 0.476$, not $2/3$ — but more importantly each molecule
now has its *own* $\kappa^2$ and therefore its own transfer rate, so the
observable is a distribution, not a shifted mean. The probability density for
this case is closed-form and ChiSurf provides it
({src}`chisurf/core/fluorescence/anisotropy/kappa2.py#p_isotropic_orientation_factor`):
it is sharply peaked near zero and has a long tail, which is exactly the shape
that makes a static ensemble dangerous.

**Restricted.** The realistic case. Each dye reorients, but only within a cone
set by its linker and its local environment. This is what the models below
describe.

The distinction matters more than the numbers: a shifted mean biases a distance,
whereas a distribution of $\kappa^2$ *broadens the measured efficiency
histogram*. Width attributed to conformational heterogeneity may be orientational
heterogeneity instead.

```{figure} /guides/figures/kappa2_models.png
:alt: kappa-squared distributions and the distance error each implies
:width: 100%

All three distributions have a mean of $2/3$ — and imply distance errors of 2%,
15% and 24%. **A correct mean is not a safe assumption**; it is the spread that
moves distances. Mobile dyes (green) are sharply peaked, restricted dyes
(orange) are broad, and the static isotropic case (grey) piles up near zero
where the inferred distance diverges. Computed with
{src}`chisurf/plugins/calculator/kappa2_dist/core/algorithms.py#compute_kappa2_dist`.
```

## Reading mobility off the anisotropy

The experimental handle is the residual anisotropy. A dye that reorients freely
depolarizes completely; one that is restricted retains anisotropy at long times.
The second-rank order parameter

$$
S^2 = \frac{r_\infty}{r_0}
$$

is 0 for a freely reorienting dye and 1 for a rigidly fixed one, and it is the
quantity both models take as input. ChiSurf calls the donor and acceptor values
$S_D^2$ and $S_A^2$, obtained from the residual anisotropies of the donor and of
the *directly excited* acceptor.

A third measurement adds the piece the first two cannot supply. $S_D^2$ and
$S_A^2$ describe how much each dye moves, but not how the two are oriented
*relative to each other*. The residual anisotropy of the **FRET-sensitized**
acceptor, $r_\infty^{AD}$, does, because the sensitized acceptor inherits its
orientation from the donor. From it,

$$
S^2_\delta = \frac{r_\infty^{AD}}{r_0\,S_D^2\,S_A^2},
\qquad
\delta = \arccos\sqrt{\frac{2S^2_\delta + 1}{3}},
$$

with $\delta$ the angle between the two dyes' symmetry axes
({src}`chisurf/core/fluorescence/anisotropy/kappa2.py#s2delta`). This is the
difference between "both dyes are somewhat restricted" — which bounds $\kappa^2$
loosely — and a specific mutual geometry, which bounds it tightly.

:::{warning}
$r_\infty^{AD}$ is the hardest of the three to measure: it needs the sensitized
acceptor emission separated from directly excited acceptor emission and from
donor leakage. If it is not available, run the calculator with **r_AD known**
switched off, which drops $\delta$ and returns the wider bound rather than a
falsely tight one.
:::

## Two models, two questions

ChiSurf implements two distributions, and they answer different questions.

**Wobbling-in-a-cone (WIC).** Each dye reorients freely within a cone whose
half-angle follows from its order parameter, and the two cone axes are separated
by $\delta$. The distribution is built by sampling the remaining free angles —
$\beta_1$ over $(0, \pi/2)$ weighted by $\sin\beta_1$, and $\varphi$ over
$(0, 2\pi)$ — and evaluating

$$
\kappa^2 = \tfrac{2}{3}\Bigl[1 + S_D^2\,\Sigma_{\beta_1}
  + S_A^2\,\Sigma_{\beta_2}
  + S_D^2 S_A^2\bigl(\Sigma_\delta + 6\Sigma_{\beta_1}\Sigma_{\beta_2} + 1
  + 2\Sigma_{\beta_1} + 2\Sigma_{\beta_2}
  - 9\cos\beta_1\cos\beta_2\cos\delta\bigr)\Bigr],
$$

writing $\Sigma_x = (3\cos^2 x - 1)/2$ for the second-rank term of each angle
({cite}`sindbert2011`, eq. 9;
{src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq_all_delta`). Setting
both order parameters to zero recovers $\kappa^2 = 2/3$ exactly, which is the
check to run when the numbers look wrong.

Use WIC when you have the anisotropies and want the range of $\kappa^2$ that is
*geometrically consistent* with them.

**Diffusion with traps (DWT).** A different physical picture: a fraction of the
molecules has the dye trapped in a fixed orientation while the rest reorients
freely, and $S^2$ is read as that trapped fraction rather than as a cone angle.
Four sub-populations follow — both free, donor trapped, acceptor trapped, both
trapped — each with its own transfer rate. The observable efficiency is their
weighted sum, and the reported $\kappa^2$ is the single value that would
reproduce that efficiency
({src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq_dwt`).

This is why DWT needs the **FRET efficiency** as an input and WIC does not: DWT
averages *efficiencies*, which is non-linear in distance, so it has to know where
on the $E(R)$ curve the molecule sits. Averaging rates and averaging efficiencies
give different answers, and the difference is largest at mid-range $E$ — exactly
where most experiments are run.

Use DWT when the suspicion is sticking or a distinct immobile sub-population
rather than a uniformly restricted linker.

## From a κ² distribution to a distance error

The output that matters is not $\langle\kappa^2\rangle$ but the spread of
distances consistent with the data. For each sampled $\kappa^2$ the apparent
distance rescales as

$$
\frac{R_{\text{app}}}{R_{DA}}
  = \left(\frac{\kappa^2}{\kappa^2_{\text{assumed}}}\right)^{1/6},
$$

so the $\kappa^2$ histogram converts directly into a distribution of relative
distance error ({src}`chisurf/core/fluorescence/general.py#kappa2_to_distance_ratio`).
That distribution is the number to quote — a distance with a stated systematic
range, rather than a distance with an unstated assumption.

Typical outcomes: dyes on long flexible linkers with $S^2 \lesssim 0.2$ give
distance errors under about 10%, which is smaller than most people expect and is
the empirical reason $\kappa^2 = 2/3$ has survived. Order parameters above
roughly 0.5 in either dye widen the bound quickly, and a large $r_\infty^{AD}$
with small $\delta$ is the worst case, because it means the dyes are both
restricted *and* mutually aligned.

The $\kappa^2$ distribution can also be propagated into a fitted distance
distribution rather than reported alongside it, which is what
{src}`chisurf/core/fluorescence/general.py#convolve_distance_with_k2_ratio` does
for the TCSPC FRET models ({ref}`concept-distance-distributions`).

## What to do about it

In order of cost:

1. **Measure the donor and acceptor anisotropy decays** on the donor-only and
   acceptor-only samples. This is not optional in quantitative FRET, and it is
   the input to everything above.
2. **Use longer or more flexible linkers.** Reducing $S^2$ shrinks the bound at
   the source, at the price of a larger positional uncertainty that the
   accessible-volume model then has to carry
   ({ref}`concept-accessible-volume`).
3. **Measure $r_\infty^{AD}$** if the bound is still too wide, and use $\delta$.
4. **Report the bound.** A distance quoted with a $\kappa^2$-derived systematic
   range is a result; the same distance quoted bare is an assumption.

Two things that do *not* help: assuming $\kappa^2 = 2/3$ harder, and averaging
over many labelling positions in the hope that orientation errors cancel — they
do not, because $E(R)$ is non-linear.

## See also

- Fundamentals: {ref}`fundamentals-energy-transfer` (where $\kappa^2$ enters
  $R_0$) · {ref}`fundamentals-polarization` (photoselection, $r_\infty$, and the
  cone).
- Guide: {doc}`/guides/61_kappa2_distribution`.
- Related concepts: {ref}`concept-fret` · {ref}`concept-anisotropy` ·
  {ref}`concept-accessible-volume` · {ref}`concept-accurate-fret`.
- Implementation: {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq`
  (the WIC expression) ·
  {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq_all_delta` ·
  {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#kappasq_dwt` ·
  {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#s2delta` ·
  {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#p_isotropic_orientation_factor`;
  plugin `chisurf/plugins/calculator/kappa2_dist/`.
- Literature: {cite}`dale1979` established that measured depolarization bounds
  $\kappa^2$; {cite}`sindbert2011` gives the order-parameter form used here and
  the linker-length measurements behind it; {cite}`lakowicz2006`,
  energy-transfer chapters, for the geometry and the averaging regimes.
