---
type: Concept
title: 'Micro-time histograms: the decay of a detector, a polarization and a window'
description: How a photon stream becomes a decay histogram per detector, how the parallel and perpendicular streams are combined into the magic-angle-like VV + 2G·VH trace, and what the histogram-level shifts, binning and FWHM mean.
tags: [concepts, tcspc, tttr, micro-time, polarization, decay]
anchor: concept-microtime-histogram
---

(concept-microtime-histogram)=
# Micro-time histograms: the decay of a detector, a polarization and a window

A TCSPC photon carries a **micro time** (the bin of the time between the photon and the next laser pulse), a **routing
channel** (the detector) and a macro time. The decay that lifetime fits need is the histogram of the micro times of the
photons that belong together: one detector (or several that look at the same signal), one excitation window, optionally
only the photons of selected bursts ({ref}`concept-tcspc-lifetime` explains what is done with it).

## Selecting photons

- **Detector and channels.** A detector of the setup is a list of routing channels, interleaved parallel, perpendicular,
  parallel, ... when the detector is polarization resolved; the histogram of the even entries is the **VV** (parallel)
  decay $I_\parallel(t)$, that of the odd ones the **VH** (perpendicular) decay $I_\perp(t)$. Without polarization
  resolution all channels form one stream.
- **Excitation window.** A micro-time gate $[t_a, t_b]$ (inclusive) keeps the photons excited by one pulse of an
  alternating scheme (PIE / nsALEX).
- **Bursts.** A burst-index file lists inclusive photon-index ranges; only photons inside any range are used and
  overlapping ranges count a photon once.
- **Binning** groups $b$ adjacent micro-time bins: the time step becomes $b\,\Delta t$.

## The combined trace

The two polarized decays are not equally detected, so the intensity that does not depend on the orientation of the
emission dipole is built with the **G-factor** $G$ (the relative sensitivity of the perpendicular and parallel
detection, {ref}`concept-anisotropy`):

$$
I_{\mathrm{VV}+2G\mathrm{VH}}(t) = I_\parallel(t) + 2\,G\,I_\perp(t).
$$

This is the trace shown as *VV + 2G VH*. Its full width at half maximum (the distance between the last bin before the
peak and the first bin after it at or below half the maximum) is a quick diagnostic of the instrument response of the
channel pair, not a lifetime.

## Histogram shifts

The VV and VH histograms can be shifted against each other by whole bins to line up the two detectors' prompt response.
The shift pads with zeros and clips at the edge: counts are not wrapped. This differs from the photon-level shift of
{ref}`concept-microtime-shift`, which moves the micro time of every photon cyclically and writes a new file.

## Export

The decay is written as one integer column, the VV bins followed by the VH bins, the layout the TCSPC reader for
polarized decays takes.

## See also

- Workflow: {doc}`/guides/89_microtime_histogram`.
- Implementation: {src}`chisurf/plugins/tttr/microtime_histogram/gui/model.py`.
- Key literature: {cite}`becker2005`, {cite}`lakowicz2006`.
