---
type: Concept
title: Fluorescence recovery after photobleaching
description: Bleach a region, watch it fill back in — the recovery gives a diffusion coefficient and a mobile fraction.
tags: [concept, imaging, diffusion, frap]
anchor: concept-frap
sources:
  - text: Derived in part from the English Wikipedia article "Fluorescence recovery after photobleaching"
    url: https://en.wikipedia.org/wiki/Fluorescence_recovery_after_photobleaching
    licence: CC-BY-SA-4.0
---

(concept-frap)=
# Fluorescence recovery after photobleaching

Bleach the fluorophores in a region with a strong pulse, then watch the region
fill back in. The bleached molecules stay dark — bleaching is irreversible on
the measurement timescale — so recovery happens only by *exchange*: unbleached
fluorophores diffuse in. How fast the region fills gives a **diffusion
coefficient** $D$; how completely it fills gives the **mobile fraction** — the
part of the population that moves at all. Anything that binds immobile shows up
as recovery that stops short.

## The model in ChiSurf

The familiar FRAP analysis ({cite}`axelrod1976`) bleaches a small spot and fits
the averaged intensity of one region of interest. ChiSurf implements the
rectangle variant, **rFRAP**, which fits the *whole image at every time point*
({src}`chisurf/core/fluorescence/imaging/frap.py#fit_rfrap`):

$$
F(x, y, t) = F_0 - \tfrac{1}{4} K_0 F_0\,
    \Bigl[\operatorname{erf}\tfrac{x + L_x/2}{N(t)}
         - \operatorname{erf}\tfrac{x - L_x/2}{N(t)}\Bigr]
    \Bigl[\operatorname{erf}\tfrac{y + L_y/2}{N(t)}
         - \operatorname{erf}\tfrac{y - L_y/2}{N(t)}\Bigr],
\qquad N(t) = \sqrt{4 D t + r^2}.
$$

A sharp bleached rectangle convolved with the (Gaussian) resolution gives the
difference of two error functions per axis, and diffusion simply widens
$N(t)$ with time. Fitting the spatial profile at every frame uses far more of
the data than collapsing each frame to one number, and it keeps the bleach
geometry ($L_x$, $L_y$, $r$) separate from the transport ($D$) instead of
entangling them. The half-time of the fit is a derived, reported quantity
({src}`chisurf/core/fluorescence/imaging/frap.py#FrapResult`); stacks are
normalised against pre-bleach and unbleached references before fitting
({src}`chisurf/core/fluorescence/imaging/frap.py#normalise_frap_stack`).

The closed-form route descends from the analytical recovery solutions of
{cite}`soumpasis1983`; the original spot-bleach treatment is
{cite}`axelrod1976`.

## Recovery is not always diffusion

{cite}`sprague2004` separates the regimes. If molecules *bind* while they
diffuse, the recovery shape depends on which process is slower: in the
reaction-dominant regime the curve reports the binding off-rate and the
diffusion coefficient is only a lower bound. The practical diagnostic is the
**bleach size**: a pure diffusive process gives a recovery time that scales
with the square of the region size; a reaction-limited one recovers at the same
rate whatever the size. A bleach-size dependence where none is expected is the
signature of binding, not of slower diffusion.

## What artefacts look like in data

- Recovery that overshoots the pre-bleach level — the unbleached reference is
  bleaching too, so the normalisation is drifting, not the sample recovering.
- A mobile fraction that shrinks when the bleach takes longer — the bleach was
  not instantaneous, and diffusion during it flattens the profile the fit
  starts from. Fit from the first post-bleach frame and keep the pulse short.
- Recovery that stops well short of pre-bleach — an immobile fraction, binding,
  or continued erosion by the monitoring beam; a whole-image fit distinguishes
  the third (it spreads, not shrinks).
- A diffusion coefficient that depends on the bleached area — not free
  diffusion ({cite}`sprague2004`).

FRAP measures transport, not mechanism: an active transport process and
diffusion can produce the same curve. The measurement is also a perturbation —
the complementary equilibrium measurement, watching fluctuations instead of
imposing one, is correlation spectroscopy ({ref}`concept-fcs-correlation`),
which reaches much shorter timescales but needs the sample to stay in
equilibrium.

## See also

- Concepts: {ref}`concept-fcs-correlation` (equilibrium fluctuations vs
  imposed bleaches) · {ref}`concept-particle-tracking` (single-particle
  transport) · {ref}`concept-image-correlation`.
- Implementation:
  {src}`chisurf/core/fluorescence/imaging/frap.py#fit_rfrap` ·
  {src}`chisurf/core/fluorescence/imaging/frap.py#recovery_curve`.
- Literature: {cite}`axelrod1976` the original analysis; {cite}`soumpasis1983`
  the closed-form solutions; {cite}`sprague2004` the binding regimes.
