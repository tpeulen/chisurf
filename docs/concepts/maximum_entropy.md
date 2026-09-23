---
type: Concept
title: Lifetime distributions and maximum entropy
description: A multi-exponential fit answers "which two or three lifetimes?" — a question that presupposes there are two or three.
tags: [concepts, tcspc, lifetime, fitting]
anchor: concept-maximum-entropy
---

(concept-maximum-entropy)=
# Lifetime distributions and maximum entropy

A multi-exponential fit answers "which two or three lifetimes?" — a question
that presupposes there are two or three. Many samples do not have discrete
states: a dye sampling a continuum of environments, a quencher at a range of
distances, or a disordered chain produce a *distribution* of decay times, and
forcing a sum of exponentials onto one returns components that fit well and mean
nothing.

Maximum entropy fits the distribution instead. This page covers what it
regularizes, how the regularization weight is chosen, and — the part that
decides whether a result is publishable — what a MEM distribution can and cannot
claim. The decay model it sits on is {ref}`concept-tcspc-lifetime`; the
statistics are in {ref}`fundamentals-photon-statistics`.

## The problem: the inversion is ill-posed

Write the decay as a continuous superposition over a lifetime grid,

$$
I(t) = \int p(\tau)\, e^{-t/\tau}\, \mathrm{d}\tau ,
$$

reconvolved with the instrument response as usual. Recovering $p(\tau)$ from
$I(t)$ is an inverse Laplace transform, and it is **ill-posed**
{cite}`istratov1999`: arbitrarily
different $p(\tau)$ produce decays that differ by less than the photon noise.
Discretizing onto a grid does not fix this — it turns it into a linear system
whose least-squares solution is wildly oscillatory, with spikes and negative
excursions that shift when a single count changes.

Two responses are possible. Reduce the number of parameters until the problem is
determined, which is what a two- or three-exponential fit does at the cost of
assuming the answer's form. Or keep the grid and add a criterion that selects
one solution from the many that fit — which is regularization. MEM was brought
to fluorescence decays for exactly this reason {cite}`livesey1987`
{cite}`brochon1994`.

## Entropy as the criterion

MEM selects the distribution that fits the data *and* is otherwise as
uninformative as possible {cite}`jaynes1957`. "Uninformative" is made precise
by the Skilling–Gull entropy relative to a prior $m(\tau)$ {cite}`gull1984`:

$$
S = \sum_i \left[ p_i - m_i - p_i \ln\frac{p_i}{m_i} \right] .
$$

$S$ is maximal when $p = m$ and falls as $p$ develops structure. The fit
minimizes

$$
Q = \chi^2 - \tfrac{1}{2}\,\nu\,S ,
$$

so $\nu$ buys smoothness with goodness of fit; it is minimized by the
Skilling–Bryan iteration {cite}`skilling1984`
({src}`chisurf/plugins/fluorescence_decay/maxent_decay/core/solver.py#solve_lifetime_mem`).

Three properties follow, and they are the reason entropy is used rather than,
say, a curvature penalty:

- **Positivity is automatic.** $\ln(p_i/m_i)$ is undefined for $p_i \le 0$, so
  the solution cannot go negative. A negative amplitude in a decay distribution
  is unphysical and a curvature penalty does not forbid it.
- **Structure must be paid for.** Every peak costs entropy, so a feature appears
  only when the data insist on it. This is the sense in which MEM is the
  *least committal* answer consistent with the measurement.
- **The prior is explicit.** $m(\tau)$ is what you get where the data say
  nothing. A flat $m$ is the usual choice and means "no preference across the
  grid"; the grid itself is a prior too, and a logarithmically spaced grid says
  something different from a linear one.

ChiSurf also reports the **unregularized** ($\nu \to 0$) solution beside the MEM
one. It is not a better fit to compare against — it is the oscillatory mess that
shows what the regularization is suppressing, and it is worth looking at once.

```{figure} /guides/figures/maxent_nu.png
:alt: MEM lifetime distributions at three regularization weights
:width: 100%

One broad distribution (dashed), recovered at three values of $\nu$ from the
decay on the right — which all three fit. The under-regularized solution
(orange) has the **best** $\chi^2_r$ of the three and splits the truth into two
sharp peaks that are not there. This is why $\nu$ cannot be chosen by goodness
of fit: the wrong answer fits better. Over-regularized (blue), $\chi^2_r$ has
risen to 2.98 and the distribution is visibly too wide. Computed with
{src}`chisurf/plugins/fluorescence_decay/maxent_decay/core/solver.py#solve_lifetime_mem`.
```

## Choosing ν: the L-curve

$\nu$ is not a nuisance parameter to fit; it is a choice about how much
structure to believe. Too small and the solution oscillates; too large and every
distribution comes back as a single broad hump centred on the prior.

Plotting the residual norm against the solution norm as $\nu$ is swept gives the
**L-curve**, and its corner is the standard compromise: the point past which
buying more smoothness starts costing real fit quality {cite}`hansen1992`. ChiSurf samples the
curve and locates the corner by maximum curvature in log–log space
{cite}`hansen1993` ({src}`chisurf/core/math/regularization.py#sample_lcurve`), exposed as
`compute_l_curve` on both MEM models.

:::{warning}
The corner is a heuristic, not a criterion with a confidence level, and it can
mis-select {cite}`hanke1996`. Two things
to do rather than trust it blindly: check that the recovered features survive a
factor of a few either side of the corner, and check that $\chi^2_r$ at the
chosen $\nu$ is still acceptable ({ref}`fundamentals-photon-statistics`). A
feature that appears only within a narrow window of $\nu$ is a regularization
artefact.
:::

## The two models

**Lifetime: MaxEnt** (`tcspc_maxent_lifetime`) recovers $p(\tau)$ on a lifetime
grid. Use it when the question is whether the sample has discrete states at all.

**FRET: MaxEnt distances** (`tcspc_maxent_fret`) recovers $p(R)$ directly on a
distance grid: each grid distance quenches the donor through the same transfer
rates the parametric FRET models use, and the same solver distributes the
amplitude.
This is the model-free counterpart to the parametric distance distributions in
{ref}`concept-distance-distributions`: no Gaussian, no chain model, no assumed
shape. That freedom is exactly why it needs more photons and more care — a
parametric model with two parameters is far better conditioned than a
hundred-bin grid, *when the model is right*.

Both run in IMP.bff: the grid's decays are the instrument's own basis (the
same response preparation and convolution as every other lifetime fit), and
the entropy-regularised programme is IMP.bff's Skilling–Bryan engine
{cite}`skilling1984`, ported from tttrlib. Both
carry the usual TCSPC nuisances — time shift, background, scatter, IRF
background — and fit them alongside the distribution. Beside the $\chi^2_r$
the programme minimises, the fit reports a second $\chi^2_r$ weighted by the
model rather than the data, which was never optimised against and so can
disagree.

## Reading a MEM result

The failure mode is over-reading. A MEM distribution is a *smoothed, positive
estimate* of a quantity the data determine only loosely, and peak positions are
much better determined than peak widths, which are better determined than the
number of peaks.

Before claiming a feature:

1. **Vary $\nu$** around the corner by a factor of a few. Features that move,
   split or vanish are not features.
2. **Vary the grid.** Change the range and the spacing. A peak that sits at the
   grid edge is the solver putting mass where it cannot be constrained.
3. **Vary the prior.** Structure that follows $m(\tau)$ is the prior showing
   through.
4. **Check the photon budget.** Resolving a distribution costs far more photons
   than resolving a mean ({ref}`fundamentals-photon-statistics`). Two peaks
   closer than about a factor of two in lifetime will merge regardless of $\nu$
   — the information is not in the data {cite}`istratov1999`.
5. **Check against a parametric fit.** If two exponentials fit with an
   acceptable $\chi^2_r$ and MEM returns two narrow peaks at the same lifetimes,
   they agree and the discrete reading is safe. If MEM returns one broad hump
   where the exponentials returned two components, the two "states" were a
   parameterization of a continuum.

Point 5 is the honest use of MEM even when a discrete model is what you intend
to report: it is the check on whether the discreteness was in the sample or in
the model.

## What it does not do

MEM does not give a posterior. It returns one distribution — the maximum-entropy
one at the chosen $\nu$ — with no uncertainty attached to the bins, and bin
uncertainties are strongly correlated. For error bars on a derived quantity,
sample the parametric model instead ({ref}`concept-parameter-uncertainty`), or
repeat the MEM inversion over bootstrap resamples of the decay and look at the
spread of the feature you care about.

## See also

- Fundamentals: {ref}`fundamentals-lifetime-quantum-yield` (why decays are
  multi-exponential, and the difference between a distribution and discrete
  states) · {ref}`fundamentals-photon-statistics`.
- Guide: {doc}`/guides/62_maxent_decay`.
- Related concepts: {ref}`concept-tcspc-lifetime` (the forward model and its
  nuisance terms) · {ref}`concept-distance-distributions` (the parametric
  alternative) · {ref}`concept-parameter-uncertainty`.
- Implementation: IMP.bff `MaxEntSpectrum` and the `tcspc_maxent_lifetime` /
  `tcspc_maxent_fret` descriptions, shown by `chisurf.core.models.description` ·
  {src}`chisurf/plugins/fluorescence_decay/maxent_decay/core/solver.py#solve_lifetime_mem`
  · {src}`chisurf/core/math/regularization.py#sample_lcurve`; plugin
  `chisurf/plugins/fluorescence_decay/maxent_decay/`.
- Literature: {cite}`lakowicz2006`, the time-domain chapter, for lifetime
  distributions; {cite}`livesey1987` and {cite}`brochon1994` for MEM on
  fluorescence decays; {cite}`vinogradov2000`, the lifetime-distribution MEM the
  tool was first built on; {cite}`skilling1984` and {cite}`gull1984` for the
  algorithm and the entropy; {cite}`hansen1992` for the L-curve.
