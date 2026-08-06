---
type: Concept
title: 'Pair correlation and flow maps: where molecules go'
description: 'Pair-correlation functions and flow maps: correlating one place against another to measure where molecules go, not just how fast they move.'
tags: [concepts, correlation, pair]
anchor: concept-pair-correlation
---

(concept-pair-correlation)=
# Pair correlation and flow maps: where molecules go

{ref}`Image correlation <concept-image-correlation>` measures how quickly the
signal at a place decorrelates. That answers *how fast*. It does not answer
*where to*, and a surprising amount of biology is a question about where to: is
this compartment connected to that one, does this molecule move along the
filament or across it, which way does the cytoplasm stream.

The pair correlation function answers those. Instead of correlating a position
with itself, correlate it with a position a distance $\delta$ away:

$$
G(\tau, x, \delta) =
  \frac{\bigl\langle F(t, x)\, F(t+\tau,\; x+\delta) \bigr\rangle}
       {\bigl\langle F(\cdot, x)\bigr\rangle \bigl\langle F(\cdot, x+\delta)\bigr\rangle}
  - 1
$$

The result is not a decay. It is a **distribution of transit times** — how long
molecules take to get from one point to the other — and its maximum is the
typical crossing time.

For the workflow, see the {doc}`pair-correlation guide </guides/55_pair_correlation>`.
For the carpet this is a reading of, {ref}`concept-image-correlation`; for the
single-point analogue, {ref}`concept-fcs-correlation`.

## What the peak time means

| transport | peak of $G(\tau,\delta)$ | scaling |
| --- | --- | --- |
| free diffusion, 1-D | $\tau_\mathrm{max} = \delta^2/(4D)$ | $\delta^2$ |
| directed flow $v$ | $\tau_\mathrm{max} = \delta/v$ | $\delta$ |
| anomalous, exponent $\alpha$ | $\tau_\mathrm{max}\propto \delta^{2/\alpha}$ | — |

The scaling is the measurement. Doubling $\delta$ and watching whether the peak
doubles or quadruples separates flow from diffusion without fitting anything,
and it does so per position.

## Three properties nothing else has

**Direction is signed.** Flow towards $+x$ correlates $x$ with $x+\delta$ and
*not* with $x-\delta$. So $+\delta$ peaks and $-\delta$ does not, and which of
the two peaks is the direction of transport. An analysis that folds $\pm\delta$
together — or that takes $|\xi|$ anywhere — has thrown the transport away and
will not complain.

**A barrier deletes the peak, it does not delay it.** This is the property pair
correlation was introduced for. An impermeable boundary between the two points
removes the correlation entirely, while:

- the intensity at both points is unchanged — nothing in the image marks the wall;
- the *auto*correlation at either point is unchanged — each point still sees the
  same molecules arriving and leaving, just from one side.

So a barrier is invisible to every other measurement in the family and obvious
to this one.

**Position survives.** The FFT-based image correlator transforms over *space*,
which averages every position in the region together by construction — and a
barrier lives at one position. The pair correlation is computed with an FFT
along **time** instead, one transform per position, so the output is a carpet of
position against lag time in which a barrier is a horizontal band of missing
correlation.

```{figure} /guides/figures/pcf_barrier.png
:alt: pair-correlation carpet across a barrier
:width: 100%

A simulated line with an impermeable wall at pixel 32 and a different drift on
each side. The intensity (grey, right panel) is flat across the wall and the
local autocorrelation is unremarkable; only the pair correlation notices.
```

## From transit times to a velocity field

A velocity is a transit time divided into a distance, so a map of transit times
is a map of velocities — the **arrows**. ChiSurf builds them two ways, and they
share no kernel, which is why agreement between them means something.

### STICS: track where the peak sits

Correlate frame $i$ against frame $i+\Delta$. Directed transport carries the
correlation peak away from zero spatial lag by the distance the sample moved, so

$$
\xi(\Delta) = -\,\frac{v_x\,\Delta\,t_\mathrm{frame}}{a},
\qquad
\psi(\Delta) = -\,\frac{v_y\,\Delta\,t_\mathrm{frame}}{a}
$$

with pixel size $a$. A straight line through the tracked peaks is the velocity
vector. Do that on a grid of tiles and the field of view becomes a quiver plot.

```{note}
**The minus sign is physics, not bookkeeping.** With frame $i$ conjugated
against frame $i+\Delta$, the peak moves *against* the flow. Get it wrong and
every number stays plausible — the speed is right, the peak is sharp, the fit is
good — while the arrows point backwards. ChiSurf pins the convention with a test
on a phantom of known drift.
```

### pCF: track when the peak arrives

For every position, correlate it with the point $\pm\delta$ away; whichever sign
peaks gives the direction, and the peak time gives the speed,
$v = \delta a / \tau_\mathrm{max}$. This is one-dimensional — along the fast
scan axis only — but it resolves position to the pixel and it can report *no
transport*, which a peak-tracking method cannot: where a barrier removes the
peak the velocity is undefined, not small.

## What limits the arrows

Three effects set what a flow map can honestly claim, and all three are
properties of the method rather than of the implementation.

**Sub-pixel displacement.** A realistic flow moves the peak by a fraction of a
pixel per frame, so the peak position has to be interpolated. A centre of mass
over a window narrower than the peak *locks to whole pixels*: on a phantom
drifting 0.2 pixels per frame it overstated the velocity by 19 %, while a
Gaussian fit — exact for a Gaussian peak sampled at integer lags — stayed within
5 %. At whole-pixel displacements the two agree exactly, which is what makes the
bias easy to ship. ChiSurf fits the Gaussian by default.

**The tile size and the largest lag are coupled.** A correlation map is
periodic. A peak driven past the edge of its tile does not disappear, it
**wraps** — and the tracker then fits a clean straight line through a
displacement that has changed sign. On a phantom flowing at 2 pixels per frame
through a 16-pixel tile this produced a velocity of about the right magnitude,
pointing the wrong way, with a respectable $R^2$ of 0.7. ChiSurf refuses such a
tile rather than reporting it, and counts the refusals.

**Shear inside a tile costs magnitude, not direction.** Where the flow varies
across the tile the correlation peak is smeared as well as displaced, and the
recovered speed comes out low. Measured on a cellular flow with four
counter-rotating cells: direction correct to $\pm 3°$, correlation $r = 0.996$,
and magnitude **20 % low**. The same estimator on a uniform flow is accurate to
a few percent, and shrinking the tile does not fix it — so a flow map is a
reliable picture of *where the sample is going* and a conservative estimate of
*how fast*.

```{figure} /guides/figures/pcf_flow_arrows.png
:alt: recovered velocity field of a cellular flow
:width: 100%

A simulated cellular flow (left), the field recovered tile by tile (middle), and
every tile's two velocity components against the truth (right).
```

**Directed transport has to beat diffusion to be visible at all.** A molecule
crossing $\delta$ by flow takes $\delta/v$; by diffusion, $\delta^2/4D$. The
flow peak only stands out once

$$
\mathrm{Pe} = \frac{v\,\delta}{D} \gtrsim 20,
$$

which is the pair-correlation counterpart of the FCS visibility threshold
$v \gtrsim 4D/w_0$ ({ref}`concept-fcs-correlation`). Below it there is nothing
to find and no amount of acquisition will produce it.

## Practical conventions

**Linear, zero-padded correlation.** A circular correlation wraps the end of the
record onto its start, which biases exactly the long-lag tail where a
large-$\delta$ peak lives. ChiSurf pads the time axis past $2N$.

**Normalise by the overlap.** Lag $\tau$ has $N-\tau$ contributing products, not
$N$. Dividing by $N$ tilts the curve down at long lag, which drags a
transit-time peak towards shorter times — that is, towards a *faster* transport
than the sample has.

**Errors come from segments.** The record is split into equal segments,
correlated separately, and reported as mean ± standard error. A curve handed to
a fit without that has no honest weighting.

**Correct bleaching before correlating, amplitude included.** Subtracting a
slow trend is only half of it: shot noise scales as the square root of the count
rate, so the fluctuations shrink as the trace decays. A plain high-pass leaves
$G$ drifting through the record, and since $G(0) = 1/N$ is read as a
concentration that drift is reported as molecules disappearing. ChiSurf rescales
the fluctuations by $\sqrt{\langle F\rangle / \bar F(t)}$ as well as removing
the trend.

## Reading the numbers

| what you see | what it means |
| --- | --- |
| peak at $\tau_\mathrm{max}$, only for $+\delta$ | directed transport towards $+x$ at $\delta a/\tau_\mathrm{max}$ |
| peak at both signs, same time | diffusion; check $\tau_\mathrm{max}\propto\delta^2$ |
| no peak at either sign, normal autocorrelation | a barrier between the two points |
| no peak and no autocorrelation | nothing there — look at the intensity first |
| peak time flat, then a step | two compartments with different transport |
| arrows everywhere on a still sample | the quality threshold is too low; peak jitter fitted to a line is always *some* velocity |

## See also

- Tools in ChiSurf: **Flow Maps** (`chisurf/plugins/microscopy/img_flow/`) draws the velocity field one arrow per tile; the pCF carpet itself is computed alongside it.

## References

- {cite}`digman2009` — pair correlation itself: diffusion measured between two points, not within one.
- {cite}`digman2012` — the scanning-ICS family this belongs to, and how the scan sets the timescales.
- {cite}`hebert2005` — spatiotemporal image correlation - the velocity field a pCF carpet complements.
- {cite}`cardarelli2010` — pCF applied to transport through the nuclear pore, the canonical demonstration.
