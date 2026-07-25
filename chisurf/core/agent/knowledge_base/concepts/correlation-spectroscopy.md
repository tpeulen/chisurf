---
type: Concept
title: Correlation spectroscopy (FCS)
description: >-
  What a correlation curve carries, which of its parameters are calibration
  rather than result, and what the numbers can and cannot mean.
tags: [fcs, correlation, diffusion, calibration]
timestamp: '2026-07-25T00:00:00Z'
---

# What is measured

An FCS curve is the temporal autocorrelation of the fluorescence intensity
from a small observation volume. Molecules diffusing through it make the
signal fluctuate; the correlation of those fluctuations carries two things:

* its **amplitude** at short lag — how many molecules are in the volume, since
  fewer molecules make relatively larger fluctuations;
* its **decay** — how quickly they cross the volume, i.e. the diffusion time.

Fast photophysics — triplet blinking, protonation — adds a further decay at
much shorter lag, typically microseconds, well separated from diffusion.

# Calibration is not a result

The correlation models are closed-form: there is no instrument response to
deconvolve and no component count to raise. What decides the fit is **which
parameters are free**.

The shape of the observation volume — the beam waist and its axial extent —
is a property of the instrument, measured by calibrating with a dye of known
diffusion coefficient. In a fresh fit these arrive *free*. Fitting them
together with the diffusion coefficient makes both meaningless: a wider
volume and slower diffusion produce the same curve. Fix them at the
calibrated values, then fit the particle number and the diffusion
coefficient.

Because of this, a diffusion time is only comparable between measurements on
the same calibrated instrument, and an absolute concentration is only as good
as the effective volume behind it.

# What the numbers can bear

* A brighter species contributes to the correlation **quadratically**, so a
  correlation-derived particle number is not a headcount of a mixed sample.
* A curve that does not flatten at long lag, or rises again, indicates drift,
  aggregates or bleaching — a measurement problem that no model choice fixes.
* Structure in the residuals only at long lag usually means the measurement
  was too short: the long-lag points are the noisiest and the least weighted.
