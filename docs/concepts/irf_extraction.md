---
type: Concept
title: Extracting the instrument response
description: Where an IRF comes from -- a scatter, a reference dye of known lifetime, the photons outside the bursts, or a blind estimate -- and how each is recovered, by one implementation every tool calls.
tags: [concepts, tcspc, decay, bursts]
anchor: concept-irf-extraction
---

(concept-irf-extraction)=
# Extracting the instrument response

A reconvolution fit is only as good as the instrument response function (IRF) it
convolves with ({ref}`concept-tcspc-lifetime`). The IRF is rarely measured on
the day exactly as the sample is; it is *extracted* from whatever the lab
recorded beside it. ChiSurf does that in one place, the **IRF Estimation** tool
(`chisurf/plugins/fluorescence_decay/irf_estimator/core/extraction.py`). Burst
MLE, Burst IRF & Background and the MFD burst fit hand their histograms to it
and take the IRF back; none extracts one of its own, and the tool's window shows
and tunes the same extraction (Burst MLE's **IRF tool** button).

In order of preference (`AUTO_ORDER`, the one order every "Auto" follows): a
reference dye first -- the owner's choice, because it is measured in the same
conditions as the sample -- then a scatter, then the photons outside the bursts,
then a blind estimate. A scatter stays selectable (Burst MLE's **IRF from**). The
sections below are in the order the sources were introduced.

## A scatter (water, Ludox)

Scattered excitation light arrives with no delay, so its micro-time histogram
*is* the IRF -- on a background. The buffer measurement (the same solvent
without scatterer, its counts scaled to the scatter's acquisition time) carries
the Raman line and the detector's afterpulsing; it is subtracted first. The
flat floor left (dark counts) is the 10 % quantile of the detector's gate. The
IRF is the contiguous peak standing two Poisson σ above the noise.

## A reference dye of known lifetime

A dye with one lifetime τ and a rotational correlation time ρ, excited by the
IRF, decays in the two polarisations as

$$
D_{VV}(t) = \mathrm{IRF}_{VV} \otimes (1 + 2r(t))\,e^{-t/\tau}, \qquad
D_{VH}(t) = \mathrm{IRF}_{VH} \otimes (1 - r(t))\,e^{-t/\tau}, \qquad
r(t) = r_0\,e^{-t/\rho},
$$

with $r_0 = 0.38$. The kernels are known once τ and ρ are, and the IRF is
recovered by deconvolving them:

- **τ** from the tail of the magic-angle sum $VV + 2\,VH$ (where rotation does
  not bend it), 1.5 ns past the peak, a weighted straight line through the
  logarithm of the floor-free counts; the listed lifetime
  (`chisurf/core/fio/reference_dyes.yaml`) when that fails or lands more than a
  factor two off.
- **ρ** from the data: with the right ρ the IRFs deconvolved from VV and VH
  have one shape; a wrong one leaves rotation in one and takes it out of the
  other. The ρ minimising the distance between the two (their centroids
  aligned: the two detectors may sit at different delays) is taken.
- **Deconvolution** by Richardson–Lucy {cite}`richardson1972,lucy1974` -- the
  update the blind estimate uses {cite}`gomezsanchez2024`, with the kernel known
  instead of fitted -- masked to the detector's gate, positive throughout, and
  stopped when the forward model fits the counts at their Poisson noise
  (reduced χ² ≤ 1) or stops improving. Where it stops is the regularisation:
  about 100 iterations for an IRF ten bins wide, about 700 for one of three.
- **Binning.** A photon's bin minus its pulse's bin is the delay binned with a
  triangle (both instants fall anywhere in their bins), so the kernel is the
  decay integrated with that triangle, not sampled at the bin starts -- at
  64 ps bins and ρ = 0.2 ns the point sample put the IRF 70 ps late.

The exact difference used before, $\mathrm{IRF}[i] = D[i] - e^{-\Delta t/\tau}D[i-1]$,
is the inverse of the plain exponential: it amplifies the noise of every bin,
and on one polarisation it takes the dye's rotation for part of the IRF.

**Measured** on a simulated Rh110 (τ = 4 ns, ρ = 0.2 ns, 1.2 M photons, an IRF
of 0.5 ns with a slow 3 % tail, 80 ps bins, five noise draws), against the IRF
of the simulation; the last column is the lifetime a reconvolution fit recovers
for a 2.5 ns sample with each IRF:

| IRF | TV distance | centroid | τ of a 2.5 ns sample |
|---|---|---|---|
| measured scatter | 0.005 | +4 ps | 2.495 ns |
| exact difference, VV | 0.159 | −120 ps | 2.626 ns |
| exact difference, VH | 0.157 | +39 ps | 2.462 ns |
| deconvolved, VV | 0.026 | +3 ps | 2.496 ns |
| deconvolved, VH | 0.037 | −17 ps | 2.518 ns |

On the simulated session of Burst Analysis (Gaussian IRF σ = 80 ps, 64 ps bins,
`burst_analysis/demo.py`), against its measured water scatter: VH 0.26 → 0.07
(centroid +82 → +7 ps, the 2.5 ns sample 2.405 → 2.486 ns); VV 0.05 → 0.10
(−1 → +29 ps, 2.495 → 2.463 ns) -- the narrow Gaussian is the case the exact
difference handles best and the stopped deconvolution leaves slightly wide.
The worst channel's lifetime error fell from 0.13 to 0.04 ns.

A gate that shows the dye no decay (Rh110 in the red detectors after the red
pulse) gives no IRF: its strongest peak must stand clear of the noise. The IRF's
area reported is the excitations the decay stands on, its floor-free counts
times $1 - e^{-\Delta t/\tau}$; Burst MLE takes a dye with at least 500.

## The photons outside the bursts

Between the molecules a single-molecule measurement records scatter -- and dim
molecules below the burst threshold, whose fluorescence decays on top of it. A
flat floor subtraction leaves that tail in place; convolving a lifetime model
with it biased a 2.2 ns lifetime to 1.1 ns on real data. A Gaussian (or a
skewed Gaussian) fitted to the prompt's *rising* edge -- instrument-only -- keeps
the measured position and width and leaves the tail behind.

## Blind, from the decay itself

The last resort: a truncated exponential fitted to the decay's tail and
Richardson–Lucy deconvolution with it {cite}`gomezsanchez2024`. What a
multi-exponential sample leaves of its decay in the estimate is shed by fitting
a skewed Gaussian to its prompt. An IRF estimated from the decay it then fits
absorbs whatever the model lacks: a good fit is no evidence.

## The time shift, calibrated against a reference dye

An IRF measured or extracted apart from the sample need not sit at the sample's
delay: count rate, pile-up, a cable or a filter between the two measurements
move it by a fraction of a bin or a few bins, and a burst fit would take that
into its lifetime. Before any fit Burst MLE therefore calibrates the shift of
each detector's IRF, VV and VH on their own, against a reference dye: the dye's
decay is fitted with the IRF convolved with its polarised exponential, an
amplitude and a flat background per polarisation, **the shift free and the
lifetime fixed** to the dye's known one (`calibrate_shifts`: a quarter-bin grid,
then golden section; Poisson deviance). The lifetime is the dye database's,
stored beside D with its source (`chisurf/core/fluorescence/dyes.py`, an exact
export of MMFDB's curated set: Rh110 4.0 ns, Rh6G 4.08 ns, fluorescein 4.1 ns,
Alexa 647 1.0 ns, ...); a dye without one has it fitted with the shift, which the
status and the report say. A dye measured at **single-molecule conditions**
(in 1 ms bins its median count under a fifth of the 99.5th percentile: dark most
of the time, bright bursts) is preferred: the timing response of a SPAD moves
with the photon count rate, so a reference measured at single-molecule rates
has the same timing offset as the bursts, while a bulk dye measured at a high
rate is shifted. A bulk measurement serves otherwise; the count rates of the
reference and of the bursts are recorded, and a bulk reference at more than
three times the bursts' rate is warned of (⚠ in the status, the numbers in its
tooltip and in the calibration report). The shifts are the fit's
`shift_sp` (VV) and `shift_ss` (VH), fixed; **Opt** refines them within half a
bin. Shifts set in the IRF tool (Advanced) replace them.

On a simulated Rh110 with the IRF measured 1.25 or −2.5 bins away, the shift is
recovered within 0.06 bins (lifetime fixed) and 0.05 bins with the lifetime
fitted (3.98 ns for 4.0). On the Burst Analysis demo the water scatter and the
Rh110 share the instrument: the calibrated shift is within 0.4 bins of zero.

## What extraction is not

The clip and the background levels a fit applies to its IRF belong to the fit,
not to the extraction; Burst MLE keeps them at their defaults.

## See also

- [IRF estimation](../guides/irf_estimation.md) -- the tool, its sources and its API.
- [Fluorescence lifetime from photon bursts](../guides/21_lifetime_from_bursts.md) -- Burst MLE's IRF sources.
- [Calibrating with a buffer, an IRF and a reference dye](reference_dye_calibration.md).
- [TCSPC and fluorescence lifetimes](tcspc_lifetime.md).
