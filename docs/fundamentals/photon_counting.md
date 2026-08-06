---
type: Fundamentals
title: Time-correlated single-photon counting
description: TCSPC measures a decay by timing individual photons relative to the excitation pulse and accumulating a histogram of those delays.
tags: [fundamentals, photons, tcspc, decay]
anchor: fundamentals-photon-counting
---

(fundamentals-photon-counting)=
# Time-correlated single-photon counting

TCSPC measures a decay by timing individual photons relative to the excitation
pulse and accumulating a histogram of those delays. This page covers the
principle, what limits the count rate, what the instrument response is made of,
and the data model that results. How the fitted model handles the resulting
nuisances — reconvolution, scatter, background, pile-up, non-linearity — is in
{ref}`concept-tcspc-lifetime`.

## Principle

A pulse excites the sample. A timing circuit starts, and stops on the first
detected photon. The measured delay increments one bin of a histogram, and the
cycle repeats millions of times.

The histogram converges to the decay shape only if **at most one photon is
detected per excitation cycle**. The electronics record the first arrival and
are then blind, so if two photons arrive the second is discarded. Since early
photons are more likely to be first, running at high detection probability
systematically discards late photons, and the measured decay is shortened and
distorted. This is **pile-up**.

The classical rule of thumb is to keep detected photons below 1% of excitation
pulses. That is conservative: the shift in a measured lifetime is under 1% up to
about a 10% detection rate, and the distortion is still modest at 30%. Modern
electronics also time-stamp rather than start–stop, which changes the details
but not the principle. ChiSurf's forward model applies a per-channel pile-up
correction rather than requiring a low rate
({src}`chisurf/core/fluorescence/tcspc/corrections.py#add_pile_up_to_model`).

## What limits the count rate

Three separate ceilings apply, and the lowest one wins:

- **The sample's lifetime** caps the repetition rate, because pulses must be
  separated by several lifetimes ({ref}`fundamentals-instrumentation`). A 12.5 ns
  lifetime means roughly 20 MHz.
- **The repetition rate and the pile-up limit** together cap the photon rate. At
  20 MHz and the 1% rule, that is 200 kHz — regardless of what the electronics
  can do.
- **The electronics' dead time**, of order 100 ns, caps the raw throughput.
  Quoting the inverse of the dead time as a maximum count rate is misleading:
  at that rate the electronics are busy almost always and counting efficiency
  collapses. The usable figure is the rate at which efficiency has fallen to
  about half.

The practical consequence is that the electronics are rarely the bottleneck for
a nanosecond-lifetime sample, and that acquisition time is bought by parallel
detectors rather than by pushing any one channel harder. Dead time is not merely
a throughput matter for correlation work: a detector that cannot register a
second photon for 100 ns distorts the correlation curve at exactly the lags used
to fit the triplet term.

## The instrument response function

The instrument response function is the histogram a zero-lifetime emitter would
produce. It is the convolution of everything that broadens the timing:

- the finite width of the excitation pulse;
- the transit-time spread of the detector, usually the dominant term;
- jitter in the discriminators and the timing converter;
- the finite width of a histogram bin.

It is measured either from elastic scatter off a non-fluorescent scatterer, or
from a reference dye with a known short lifetime.

Which one is used matters. A scatter measurement is at the *excitation*
wavelength, while the sample emits at a longer one, and detector transit times
depend on wavelength — the colour effect
({ref}`fundamentals-instrumentation`). The reference-dye method measures the
response in the correct spectral band at the cost of needing an accurately known
reference lifetime. Either way a residual sub-channel **time shift** between the
instrument response and the data is fitted; it is a genuine physical parameter,
not a fudge, and an error in it biases short lifetime components most.

Two failure modes are worth naming because they are silent. An instrument
response measured on a different day, at a different count rate, or after any
optical adjustment no longer matches the data, and the fit will absorb the
mismatch into an extra exponential. And an instrument response with a
significant background of its own imposes that background on every fit that uses
it.

## Time bins are not identical

The time-to-digital conversion does not produce exactly equal bin widths. The
variation is the **differential non-linearity** of the converter, and it appears
as a fixed, reproducible ripple across the histogram — a pattern that persists
regardless of the sample.

It is measured by illuminating the detector with light uncorrelated with the
excitation, which would give a flat histogram from a perfect converter; the
deviations are the correction table. The correction belongs on the model, not on
the data, so that the residuals remain Poisson-distributed
({src}`chisurf/core/fluorescence/tcspc/corrections.py#compute_linearization_table`).

Some detectors additionally require a per-channel linearization of the
micro-time axis, applied at read time
({doc}`/guides/37_tttr_microtime_lut`).

## Time-tagged data

Modern hardware does not accumulate a histogram. It records every photon
individually with:

- a **macro time** — the arrival time relative to the start of the experiment,
  counted in excitation periods, resolving down to the pulse interval;
- a **micro time** — the delay since the most recent excitation pulse, at the
  resolution of the timing electronics;
- a **routing channel** — which detector, and by extension which polarization
  and which colour, registered the photon.

This is the TTTR (time-tagged, time-resolved) model, and it is what every
single-molecule analysis in ChiSurf reads
({doc}`/guides/12_handling_tttr_files`).

The two time axes span nine orders of magnitude and are used for different
things. Micro times give lifetimes and anisotropy. Macro times give correlation
curves, burst detection and intensity traces. The important property is that no
choice is baked in at acquisition: the same file can be histogrammed into a
decay, correlated into an FCS curve, or segmented into bursts, and those views
can be combined per photon — which is what multiparameter analysis is
({ref}`concept-mfd-fitting`, {doc}`/guides/33_timestamps_and_bursts`).

The cost is volume. A long measurement is hundreds of millions of photon
records, and analyses have to stream rather than load.

## See also

- Previous: {ref}`fundamentals-instrumentation`. Next:
  {ref}`fundamentals-photon-statistics`.
- Concepts: {ref}`concept-tcspc-lifetime` (the forward model and its nuisance
  terms) · {ref}`concept-mfd-fitting` · {ref}`concept-smfret-bursts`.
- Guides: {doc}`/guides/12_handling_tttr_files` ·
  {doc}`/guides/33_timestamps_and_bursts` ·
  {doc}`/guides/37_tttr_microtime_lut`.
- Implementation:
  {src}`chisurf/core/fluorescence/tcspc/corrections.py#add_pile_up_to_model` ·
  {src}`chisurf/core/fluorescence/tcspc/corrections.py#compute_linearization_table`.
- Literature: {cite}`oconnor1984` · {cite}`becker2005` · {cite}`lakowicz2006`,
  time-domain chapter.
