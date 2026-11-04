---
type: Concept
title: Calibrating with a buffer, an IRF and a reference dye
description: The G factor from a fast-rotating reference dye, the confocal volume from its correlation and known diffusion coefficient, and the background rate from the buffer.
tags: [concepts, bursts, anisotropy, fcs, calibration]
anchor: concept-reference-dye-calibration
---

(concept-reference-dye-calibration)=
# Calibrating with a buffer, an IRF and a reference dye

A single-molecule session measures more than the sample. Beside it the lab records

- the **buffer** without dye: the background of every detector;
- a **scatterer** (water, Ludox): the instrument response function (IRF);
- a **reference dye** per colour: a small, free, fast-rotating dye such as
  Rhodamine 110 (green) or Alexa Fluor 647 (red).

Burst Analysis' *1. Data Selection* has a row for each of these roles, made from the detector
setup (one IRF and one reference-dye row per emission colour), and computes from them what they
give. This page explains what is computed and under which assumptions; the workflow is in
{doc}`/guides/13_burst_identification` ("What the workflow works on").

## The background rate from the buffer

For every detector $d$ the photons of its channels inside its micro-time gate, per second of
the buffer measurement:

$$B_d = \frac{N_d^\mathrm{buffer}}{T^\mathrm{buffer}}\quad[\mathrm{kHz}].$$

Several buffer files are pooled ($\sum N / \sum T$). The rate is reported per detector as
$B_{G|G}$, $B_{R|G}$, … . In Burst MLE the buffer corrects a **scatter IRF** for its background
(the buffer's counts per second, scaled to the scatter's duration, are taken off); the
**background of the lifetime fit** stays the photons *outside* the bursts of the measurement
itself (the reverse burst selection), so a buffer that differs from the sample's own background
cannot bias the fit. The buffer's rate is an independent check of that estimate.

## The G factor from a fast-rotating reference dye

The two polarised detectors of a colour see the parallel ($VV$) and perpendicular ($VH$)
emission with different efficiencies; their ratio is the G factor
({ref}`concept-anisotropy`). For a dye that depolarises long before it emits, the anisotropy
$r(t) = r_0 e^{-t/\rho}$ has vanished in the tail of the decay ($t \gg \rho$, Rh110:
$\rho \approx 0.2$ ns against $\tau \approx 4$ ns), where the emitted intensities are equal and
the detected ones differ only by the efficiencies:

$$G = \frac{\langle VV(t) - b_{VV}\rangle_\mathrm{tail}}{\langle VH(t) - b_{VH}\rangle_\mathrm{tail}}.$$

ChiSurf takes the tail from 1.5 ns after the peak to where the decay fell to 2 % of the peak
(the rest is noise), subtracts the background level $b$ of the bins before the rise when the
gate leaves room for it, and averages the per-bin ratio — the tail matching of the VV/VH
G-factor tool (`calculate_g_factor_core`), with the same convention as the setup's G-Factor
column ($G$ multiplies $VH$). Detectors on the same channels (``R|G`` and ``R|R``: one red pair,
two PIE windows) share one value, taken in the window that saw the dye best. The value is shown
into the setup's G-Factor column as soon as it is computed; a G the user then edits in the setup is kept
(the role row says *hand-edited*).

Assumptions: the dye rotates much faster than it decays ($\rho \ll \tau$); no polarisation
mixing by the objective ($l_1, l_2$ are separate parameters of the setup); the gate covers the
tail.

## The confocal volume from the reference dye's correlation

The reference dye's photons on the colour's detector with the most photons are correlated —
the parallel against the perpendicular channel, which removes detector dead time and
afterpulsing — in ten parts of the measurement, whose spread weights the fit. Free 3-D diffusion
through a Gaussian detection volume $\exp(-2(x^2+y^2)/w_0^2 - 2z^2/z_0^2)$ gives

$$G(\tau) = b + \frac{1}{N}\left(1+\frac{\tau}{\tau_D}\right)^{-1}
\left(1+\frac{\tau}{s^2\tau_D}\right)^{-1/2},\qquad s = z_0/w_0,$$

fitted from 2 µs (past antibunching and most of the triplet) to a twentieth of a part's
duration. With the dye's diffusion coefficient $D$:

$$w_0 = \sqrt{4 D \tau_D},\qquad z_0 = s\,w_0,\qquad
V_\mathrm{eff} = \pi^{3/2} w_0^2 z_0,\qquad c = \frac{N}{V_\mathrm{eff} N_A}$$

(`chisurf.core.fluorescence.diffusion`). The structure parameter $s$ is the least determined
quantity; on the simulated session $w_0$ is recovered within a few per cent and $z_0$ within
about 20 %.

### Which $D$

$D$ comes from the **dye database** ({mod}`chisurf.core.fluorescence.dyes`, the MMFDB reference
species the FCS calculator uses): its $D(25\,^\circ\mathrm{C}, \mathrm{water})$, corrected to the
temperature of the measurement with the viscosity of water,

$$D(T) = D_{25}\,\frac{T}{298.15\,\mathrm{K}}\,\frac{\eta(25\,^\circ\mathrm{C})}{\eta(T)}$$

— about 2.6 % per °C, so the temperature matters (default 22.5 °C). The dye of a row is found in
the file's header comments, else in its name, through the database's names and aliases
(``Rh110``, ``R110``, ``rhodamine110``, ``A647``, ``Atto655``, ``Cy5``), never a dye of another
colour; else the colour's usual dye (Rhodamine 110 green, Alexa Fluor 647 red). *Other (custom
D)* takes your own value. The calibration panel names the entry and its source.

Literature values differ: the database lists Rh110 at 470 µm²/s (25 °C, PFG-NMR, Kapusta 2010);
Gendron et al. propose 440 µm²/s, many labs use 430 µm²/s at 22.5 °C. Use the value your lab's
volumes were calibrated with — through the temperature or a custom $D$ — so volumes stay
comparable. $V_\mathrm{eff}$ scales with $D^{3/2}$.

## What the table shows, and what a good value is

The role table holds one number per column; the rest is in the analysis report below.

| Column | Row | Good value |
|---|---|---|
| G | reference dye | 0.8–1.3 (1: both polarisations detected alike) |
| V_eff (fL) | reference dye | 0.5–2 fL for a well-aligned confocal |
| τ_D (µs) | reference dye | Rh110 in a 0.5 µm focus: 100–200 µs |
| w0 (µm) | reference dye | 0.2–0.6 µm |
| s | reference dye | 3–8; much larger: a long, poorly defined focus |
| cpm (kHz) | reference dye | count rate / N, the brightness of one molecule: higher is better |
| B (kHz) | buffer | below about 2 kHz per detector |
| IRF (ps) | IRF | FWHM: a few hundred ps (SPAD), under 100 ps (hybrid detector) |

The IRF width is the full width at half maximum of the scatter's VV + VH decay above the median
floor of the gate, at the full micro-time resolution.

## The analysis report

Everything else -- the files with their SHA-256, the dye with its database entry, temperature,
D and its literature source, the correlation fit (N, τ_D, s, offset, w0, z0, V_eff, c,
brightness) with standard errors from the fit's curvature scaled by χ²r, the fit range and χ²r,
G per detector with its spread, tail and background regions, which G was written to the setup
(or kept as edited by hand), the buffer rates per detector, the IRF files and width, and what was
estimated for want of a file -- is the calibration report
(`chisurf.plugins.burst.burst_analysis.calibration_report.build_report`). It is the workflow
context's `calibration_report`, part of the workflow's payload, and once the bursts exist it is
written into each measurement's analysis container as the object `burst_calibration`
(`calibration_data`, JSON, operation `calibration`, derived from the photon streams);
`read_report(container)` reads it back.

## Without calibration files

None of the rows is required. Without a buffer the background is the photons outside the bursts;
without an IRF measurement the IRF is estimated from the non-burst photons (a skewed Gaussian),
or blindly from the burst decay; without a reference dye the G factor is the setup's and no
volume is computed. The step says so in one warning line, and the workflow records which values
were estimated rather than measured (`BurstWorkflowContext.estimated`, written with the bursts'
provenance).

## References

- Gendron P-O, Avaltroni F, Wilkinson KJ (2008). Diffusion coefficients of several rhodamine
  derivatives as determined by pulsed field gradient-nuclear magnetic resonance and fluorescence
  correlation spectroscopy. *J Fluoresc* 18:1093–1101.
  [10.1007/s10895-008-0357-7](https://doi.org/10.1007/s10895-008-0357-7)
- Petrášek Z, Schwille P (2008). Precise measurement of diffusion coefficients using scanning
  fluorescence correlation spectroscopy. *Biophys J* 94:1437–1448.
  [10.1529/biophysj.107.108811](https://doi.org/10.1529/biophysj.107.108811)
- Kapusta P (2010). Absolute diffusion coefficients: compilation of reference data for FCS
  calibration. PicoQuant application note.
  [appnote_diffusioncoefficients.pdf](https://www.picoquant.com/images/uploads/page/files/7353/appnote_diffusioncoefficients.pdf)
- Lakowicz JR (2006). *Principles of Fluorescence Spectroscopy*, 3rd ed., ch. 10 (G factor).
- Related: {ref}`concept-anisotropy`, {ref}`concept-fcs-correlation`,
  {ref}`concept-smfret-bursts`.
