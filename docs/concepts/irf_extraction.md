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
bin.

**Three shifts, each a parameter.** A burst fit has three time shifts per
detector, rows of Burst MLE's *Fit parameters* table in Simple and Advanced:
**IRF shift VV** and **IRF shift VH** (`shift_sp`, `shift_ss`: the IRF moved
against the VV and the VH data by linear interpolation of the fraction) and
**Shift VV/VH** (`shift`: the VH decay moved against the VV decay in whole bins,
its IRF and background with it). *Start* is the calibration above (0 without a
reference dye; Shift VV/VH the setup's saved value), *Fixed* holds it and is set
by default, *Result* is what the fit used. Unfixed, the decay fit refines a
shift within ±0.5 bin of its start (±1 bin for Shift VV/VH, whole bins tried)
for the lowest 2I*, and the bursts are fitted with the refined value. A start
typed by hand, or set in the IRF tool, or found by **Opt**, replaces the
calibration until **Reset shifts**; the calibration report keeps both the
calibrated and the used values (`calibrated_vv`, `shift_vv`, `edited`) and the
reference fit's χ²ᵣ at the shifts used (`used_fit_chi2r`).

**One detection pair, one calibration.** Under PIE the red detectors are two
detectors of the setup: `R|R` (red-excited) and `R|G` (the same channels, gated
on the green pulse). The G factor is the detection side's -- the efficiencies of
the VV and VH detectors, whatever laser excited -- and so are the IRF's shape and
the SPAD's timing. So both are calibrated once, on the reference dye of their
colour (Alexa 647) in the window that sees it (`R|R`'s), with that detector's G,
l1 and l2: `R|G` gets `R|R`'s IRF placed at the green pulse by the setup's PIE
windows (the offset of their gates, `R|G` start − `R|R` start; said in the
tooltip and the report as `calibrated_on` / `offset_bins`), and `R|R`'s shifts
and reference fit. Nothing is fitted in a window the dye barely reaches: on
DNA13bp_3 that used to give `R|G` its own Alexa 647 fit (+0.86 / +0.73 bins,
χ²ᵣ 10.9) beside `R|R`'s (+0.55 / +0.47, 242, both with G 1). A green dye never
calibrates the red pair, nor a red dye the green detector.

On a simulated Rh110 with the IRF measured 1.25 or −2.5 bins away, the shift is
recovered within 0.06 bins (lifetime fixed) and 0.05 bins with the lifetime
fitted (3.98 ns for 4.0). On the Burst Analysis demo the water scatter and the
Rh110 share the instrument: the calibrated shift is within 0.4 bins of zero.

## The reference fit: is the IRF right?

A shift calibration says where the IRF sits; it does not say that the IRF, G and
the rotation describe the sample. So the reference dye is then fitted with the
IRF and **the model a burst fit uses** (`reference_fit`): for polarisation
$p$,

$$
F_p(t) = A\,\big[\mathrm{IRF}_p(t - s_p) \otimes k_p\big](t) + b_p,\quad
k_{VV} = e^{-t/\tau}\big(1 + r_0(2 - 3l_1)e^{-t/\rho}\big),\quad
k_{VH} = \tfrac{1}{G}\,e^{-t/\tau}\big(1 + r_0(3l_2 - 1)e^{-t/\rho}\big),
$$

one amplitude $A$, a flat $b_p$ and a shift $s_p$ per polarisation free; $\tau$
fixed to the dye database's, $\rho$ read from the dye, $r_0 = 0.38$, and $G$,
$l_1$, $l_2$ the detector's -- the kernels of Fit23, binned like photons. The
shifts come from the same fit with $G$ free, so a wrong $G$ shows as a bad fit
instead of moving the IRF. With the right IRF and corrections a dye of one
lifetime fits at $\chi^2_r \approx 1$; its weighted residuals
$(d - F)/\sqrt{F}$ tell what is wrong: a wave at the rise is the IRF, VV and VH
pulling apart G or $l_1$/$l_2$, the first nanosecond the rotation. The fit with
$G$ free gives the $G$ the reference asks for.

On a simulated Rh110 (G 1.3) the IRF deconvolved from it gives $\chi^2_r < 1.2$
and $G$ within 2 %; with $G$ 1.0 the fit is ten times worse and still finds
1.3. On Rh110_thick_1 (bulk, 61 kHz, 80 ps bins): $\chi^2_r$ 309 with the
setup's $G$ 1.000, 1.45 with Data Selection's 1.436 (free: 1.428, 1.40); with the
lifetime free 1.10 at 4.02 ns.

**One description of the dye.** The IRF deconvolved from a dye, the shift
calibration and the reference fit must all use the same lifetime, rotation and
initial anisotropy, or the fit measures their disagreement rather than the IRF:
Alexa647_thick_1, deconvolved at its tail's 1.15 ns and fitted at the database's
1.0 ns, gave $\chi^2_r$ 31. So:

- *Lifetime* (`reference_lifetime`): the dye database's while the tail of
  $VV + 2VH$ agrees within 5 % (Rh110: 4.02 against 4.0 ns), else the tail's,
  and the database's is reported as not describing this measurement (status ⚠,
  tooltip, report: `tau_listed_ns`, `tau_tail_ns`, `tau_consistent`). Alexa 647's
  1.0 ns comes from the Molecular Probes handbook's table of the Alexa Fluor
  dyes in water (the database entry carries no URL); a cyanine's lifetime moves
  with temperature, viscosity and buffer (its cis--trans isomerisation), and the
  owner's measurement says 1.15--1.16 ns in both polarisations.
- *Rotation and $r_0$* (`irf_from_reference(g_factor=)`): the rotation is read
  from the two polarisations (`reference_rotation`); given the detector pair's G
  from Data Selection, the dye is fitted at it, and when that fit is poor
  ($\chi^2_r > 2$) the initial anisotropy is taken from the data as well: the
  $r_0$ of 0.30 ... 0.10, each with its own rotation and IRF, that fits best.
  Alexa 647 starts far below the ideal 0.38: $r_0$ 0.15, $\rho$ 1.0 ns,
  $\chi^2_r$ 1.3 at the tail-ratio G 1.54 (0.38 gave 16). A second rotation or
  a residual anisotropy was not needed.
- *Swapped channels* (`reference_anisotropy`): a free dye's anisotropy right
  after the pulse is positive. Below −0.05 the detector's VV and VH channels are
  swapped in the setup, and Data Selection (*VV/VH swapped?*) and Burst MLE (⚠)
  say so: RVZMT150's red pair reads −0.10 as defined, +0.12 swapped. G and the
  rotation are wrong until the order is put right in step 0.

## What extraction is not

The clip and the background levels a fit applies to its IRF belong to the fit,
not to the extraction; Burst MLE keeps the clip open and takes no background
level off (an extracted IRF has none; 0.02 of the peak cut a deconvolved IRF's
tail and took the reference fit from 1.5 to 4). Nor is a burst fit's
*background* extraction: it is the buffer, else a strict selection of the
measurement's background photons, else a flat + scatter model
([Fluorescence lifetime from photon bursts](../guides/21_lifetime_from_bursts.md),
*The background*).

## See also

- [IRF estimation](../guides/irf_estimation.md) -- the tool, its sources and its API.
- [Fluorescence lifetime from photon bursts](../guides/21_lifetime_from_bursts.md) -- Burst MLE's IRF sources.
- [Calibrating with a buffer, an IRF and a reference dye](reference_dye_calibration.md).
- [TCSPC and fluorescence lifetimes](tcspc_lifetime.md).
