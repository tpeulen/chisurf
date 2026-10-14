---
type: Fundamentals
title: The optical and detection chain
description: Between the excited state and a recorded photon sit a light source, an optical train, and a detector.
tags: [fundamentals, photons, instrumentation]
anchor: fundamentals-instrumentation
sources:
  - text: Derived in part from the English Wikipedia article "Two-photon absorption"
    url: https://en.wikipedia.org/wiki/Two-photon_absorption
    licence: CC-BY-SA-4.0
  - text: Derived in part from the English Wikipedia article "Two-photon excitation microscopy"
    url: https://en.wikipedia.org/wiki/Two-photon_excitation_microscopy
    licence: CC-BY-SA-4.0
---

(fundamentals-instrumentation)=
# The optical and detection chain

Between the excited state and a recorded photon sit a light source, an optical
train, and a detector. Each imposes limits that appear in the data as if they
were properties of the sample. This page covers what those limits are and how
they show up.

## Excitation

Steady-state work uses arc lamps or LEDs with a monochromator. The methods in
this documentation are pulsed or confocal, and use pulsed diode lasers for
routine TCSPC — tens of picoseconds pulse width, repetition rates selectable
from single-shot to tens of megahertz, one fixed wavelength per head — or
femtosecond titanium–sapphire systems where wavelength tunability or two-photon
excitation is needed.

The repetition rate is not a free choice. The interval between pulses must be
long enough for the sample to decay, conventionally at least four to five times
the longest lifetime present; otherwise the tail of one pulse is still present
when the next arrives. That residue does not disappear — it wraps into the early
channels of the following period and must be modelled as a periodic convolution
({ref}`concept-tcspc-lifetime`). A 12.5 ns lifetime therefore caps the useful
repetition rate near 20 MHz, and that cap in turn caps the achievable photon
rate ({ref}`fundamentals-photon-counting`).

Excitation power has its own ceiling. Beyond a certain intensity the fluorophore
spends a significant fraction of its time in the excited or triplet state and
stops absorbing linearly — optical saturation. In FCS this distorts the
effective observation volume and produces an apparent diffusion time that
depends on laser power ({ref}`concept-fcs-saturation`); it also accelerates
bleaching. Checking that a result is independent of excitation power is the
standard control.

### Two-photon excitation

In two-photon excitation a molecule absorbs two near-infrared photons
quasi-simultaneously and reaches the same excited state one photon of half the
wavelength would reach. Göppert-Mayer predicted the process
{cite}`goeppertmayer1931`; Denk, Strickler and Webb built the scanning
microscope on it {cite}`denk1990`. The rate goes as the square of the photon
flux, so cross-sections carry their own unit, the GM
($10^{-50}\ \mathrm{cm^4\,s\,photon^{-1}}$), and common fluorophores run from a
few to a couple of hundred GM across the 690–1050 nm band
{cite}`xu1996`. Those numbers are why femtosecond pulses are a requirement and
not an optimisation: only a ~100 fs pulse concentrates the instantaneous flux
enough, at an average power the sample survives.

Three consequences reach the data:

- **Sectioning without a pinhole.** Emission is created only where the flux is
  squared — the focus — so out-of-focus background is never generated rather
  than rejected downstream. Emission photons that scatter on the way out are
  still usable signal, so the collection budget differs from a confocal setup
  at the same numerical aperture.
- **Depth is a scattering budget.** Near-infrared excitation scatters roughly an
  order of magnitude less on the way in than the visible light that would
  address the same transition one photon at a time, and creates no out-of-focus
  bleaching or autofluorescence; the usable depth is set by how many excitation
  photons survive the tissue {cite}`helmchen2005`.
- **The data model is unchanged — the clock is not.** Emission is still one
  photon at a time, so the decay histogram, the instrument-response
  convolution, pile-up and the TTTR axes all work as on the following page
  ({ref}`fundamentals-photon-counting`). But a Ti:sapphire cavity runs near
  80 MHz: a 12.5 ns interval. That violates the four-to-five-lifetime rule
  above for any lifetime beyond ~3 ns — the tail of one pulse wraps into the
  next period and must be modelled as the periodic convolution it is
  ({ref}`concept-tcspc-lifetime`), or the repetition rate is divided down with
  a pulse-picker at the cost of count rate.

The power-independence control above matters more here, not less: the peak
intensity at the focus sits close to saturation by design, so an apparent
lifetime or diffusion time that tracks average power is suspect.

## Wavelength selection

Monochromators offer tunability and are used where a spectrum is the
observable. Two of their properties matter here. Their transmission is
polarization-dependent, which biases anisotropy measurements unless the G-factor
correction accounts for it ({ref}`concept-anisotropy`). And gratings pass
second-order light — 600 nm light appears at the 300 nm setting — which is
removed with a cut-off filter rather than by the monochromator itself.

Interference filters and dichroic mirrors are used in confocal and imaging
work: higher throughput, steeper edges, no moving parts, no tunability. The
relevant specification is not the transmission in the passband but the
**blocking outside it**, usually quoted in optical density. Excitation light is
typically six or more orders of magnitude stronger than the fluorescence, so a
filter blocking at OD 5 leaves a scatter background comparable to the signal.
Elastic scatter and Raman scatter from water are the two backgrounds that
survive good filtering, and both arrive with the timing of the excitation pulse
rather than with the fluorescence decay — which is why they are modelled as a
scaled instrument response rather than as a constant
({ref}`concept-tcspc-lifetime`).

## Detectors

| Detector | Timing resolution | Notes |
|---|---|---|
| Photomultiplier tube (dynode chain) | 200–500 ps | Large area, cheap, measurable colour effect |
| Microchannel plate PMT | 25–50 ps | Best timing; expensive, limited count rate |
| Hybrid detector | ~50 ps | No afterpulsing, good for FCS at short lag |
| Single-photon avalanche diode | 40–500 ps | High quantum efficiency in the red; afterpulses; small active area |

Three detector behaviours affect the analysis directly.

**Transit-time spread** is the jitter in the arrival of the output pulse, and it
is usually the dominant contribution to the width of the instrument response
function. It sets how short a lifetime can be recovered.

**Afterpulsing** is a spurious second pulse following a real detection by
hundreds of nanoseconds to microseconds. It is correlated with the real photon,
so it appears in a correlation curve as an amplitude at short lag times, sitting
exactly where the triplet term is expected. Cross-correlating two detectors
looking at the same signal removes it, because the two detectors' afterpulses are
independent — which is why FCS is normally done with two detectors even for a
single colour ({ref}`concept-fcs-correlation`).

**Colour effect** is the wavelength dependence of the transit time: an
instrument response measured on scattered excitation light is not aligned with
one measured at the emission wavelength. It is small in microchannel-plate
detectors and significant in older dynode-chain tubes. It is handled either by
measuring the response on a short-lifetime reference dye emitting in the same
band, or by fitting a sub-channel time shift; getting it wrong biases short
lifetimes most ({ref}`fundamentals-photon-counting`).

Everything on this page is in service of one number: how many of the photons a
molecule emits are actually counted. For a good confocal instrument that is a
few percent, and it is the product of collection solid angle, filter and
dichroic transmission, and detector efficiency — so a factor lost anywhere is
lost outright. {cite}`moerner2003` works the budget through for
single-molecule detection and is the reference to check an instrument against.

## Sample geometry and the inner filter effect

Beer's law is linear only in a dilute sample. Above an absorbance of about 0.1
across the excitation path, the beam is measurably attenuated before reaching
the observed volume, and the observed intensity falls below proportionality to
concentration — the primary inner filter effect. If the sample also absorbs at
the emission wavelength, emitted light is reabsorbed on the way out: the
secondary effect, which additionally distorts the shape of the emission
spectrum.

This is a systematic error that looks like a real concentration dependence, and
the standard remedies are dilution, a shorter path, or front-face illumination.

Anisotropy work has an additional geometric requirement: the polarizers must be
aligned, and the collection optics must not have a large numerical aperture,
because collecting over a wide solid angle mixes the polarizations and lowers
the measured anisotropy independently of any rotation. A high-NA objective, as
used in every confocal experiment here, therefore needs its own depolarization
correction.

## What each artefact looks like in data

- Intensity below proportionality to concentration, spectrum distorted at the
  blue edge — inner filter, not quenching.
- Apparent anisotropy above 0.4 — scattered excitation light in the detection
  channel, not a rigid sample ({ref}`fundamentals-polarization`).
- Correlation amplitude at sub-microsecond lag on a single detector —
  afterpulsing, not triplet.
- Diffusion time that grows with laser power — optical saturation, not slower
  molecules ({ref}`concept-fcs-saturation`).
- A short lifetime component that changes when the instrument response is
  remeasured — colour effect or a mis-set time shift, not a real species.

## See also

- Previous: {ref}`fundamentals-solvent`. Next:
  {ref}`fundamentals-photon-counting`.
- Concepts: {ref}`concept-tcspc-lifetime` (how the model absorbs scatter,
  background and non-linearity) · {ref}`concept-fcs-correlation` ·
  {ref}`concept-fcs-saturation` · {ref}`concept-anisotropy`.
- Literature: {cite}`lakowicz2006`, instrumentation chapter;
  {cite}`becker2005` for the detector and electronics side.
