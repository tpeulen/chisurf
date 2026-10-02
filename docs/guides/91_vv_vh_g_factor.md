---
type: Guide
title: The G-factor of a polarised setup (VV/VH G-Factor Calculator)
description: Measuring the detection-efficiency ratio G of two polarisation channels by tail matching on a fast-rotating dye, estimating the linked polarisation mixing from a slow protein, and applying the calibration to a batch of decays.
tags: [guides, tcspc, anisotropy, calibration, g-factor]
---

# The G-factor of a polarised setup (VV/VH G-Factor Calculator)

**What you get:** the factor $G$ that makes the parallel (VV) and perpendicular (VH) channels of your
instrument comparable, with its standard deviation, an estimate of the linked polarisation mixing
$l_1 = l_2$, a check of the corrected anisotropy $r(t)$, and the steady anisotropy $r_\infty$ of any
number of further decays under the same calibration.

## Theory

Gratings, mirrors and detectors are not polarisation-neutral: the two channels see the same photons with
different efficiency. The ratio is $G = S_\mathrm{VV}/S_\mathrm{VH}$ and it multiplies $I_\mathrm{VH}$ in
$r(t) = (I_\mathrm{VV} - G I_\mathrm{VH})/(I_\mathrm{VV} + 2 G I_\mathrm{VH})$, so an error in $G$ scales
every anisotropy you report. $G$ is measured on a dye that depolarises within the pulse width: in the
tail its anisotropy is zero and $I_\mathrm{VV}/I_\mathrm{VH}$ equals $G$ alone (tail matching). A high
numerical aperture additionally mixes the polarisations geometrically; one steady-state observable
(a slow, long-lived reference with a known Perrin anisotropy) fixes only the single linked value
$l_1 = l_2$, and an estimate outside 0 to 0.5 is shown but not applied. See {ref}`concept-anisotropy`.

## 1. Open the tool and load the fast reference

*Spectroscopy → Fluorescence decay → VV/VH G-Factor Calculator*. Press **Fast reference...** and choose the
VV/VH file of the fast dye (or drop it on the window). The status line reports $G$ and the results table
lists $G$ raw and its standard deviation.

```{figure} figures/vv_vh_g_factor_calibrated.png
:name: fig-vv-vh-g-factor
:width: 100%

Fast dye (rho 0.2 ns) and slow protein (rho 16 ns) loaded, background correction on. The yellow lines in
the decay plot are the tail region, the blue ones the background region; r(t) of the fast dye sits near
zero in the tail.
```

## 2. Match the tails

Set the tail with **Tail start** / **Tail stop** (type a bin and press Enter, use the arrows, or drag the
yellow lines in the plot; the mouse wheel zooms). Tick **Background correction** and set the blue region
on a signal-free stretch when the pre-pulse level matters: the table then shows $G$ corrected and the
background of each channel. **VH shift** moves the VH axis by fractional bins; **Flip VV/VH** swaps the
channels of a file written the other way round. **Manual G** replaces the calculated value by one you type.

## 3. Slow reference and mixing

**Slow protein...** loads the slow reference. Set **dt**, **rho** and **r0**; the first-moment lifetime and
the Perrin steady anisotropy give the linked $l_1 = l_2$ estimate in the *Mixing estimate* table. The
manual toggles override the lifetime, the target anisotropy or the mixing parameter.

## 4. Batch, export, archive

The **Batch anisotropy** tab queues further decays (**Add files...**; Delete removes the selected one),
**Run batch** evaluates $r_\infty$ of each with the frozen calibration and **Save table...** writes a
tab-separated file. **Export calibration JSON...** writes the values and settings;
**Archive reference calibration** registers the reference decay, corrected traces and provenance in MMFDB.

## Headless and Python

```python
from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel

m = GFactorModel(); m.load("fast.dat"); m.load("slow.dat", slow=True); m.background = True; m.compute()
print(m.g_factor, m.fp_result["l1"])
```

`vv-vh-g-factor` is the command line entry point of the same calculation.

## See also

- Concept: {ref}`concept-anisotropy`; workflow: [Fluorescence lifetime and anisotropy decay fitting](10_lifetime_anisotropy_fitting.md).
- The g-factor and l1/l2 enter the [Anisotropy Wizard](10_lifetime_anisotropy_fitting.md).
