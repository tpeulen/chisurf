---
type: Manual Page
title: Nuisances
description: Convolution. In time-resolved fluorescence experiments, usually, the model function is convolved with an instrument response function before comparing the model to the recorded data (iterative (re)convolution).
tags: [manual, nuisances]
---

# Nuisances

*Convolution.* In time-resolved fluorescence experiments, usually, the model function is convolved with an instrument response function before comparing the model to the recorded data (iterative (re)convolution). Depending on the experimental conditions and the used model function IRF convolution settings need to be adapted (**Fig.20**).

Certain convolution settings can be optimized during fitting or varied during sampling. However, usually, the convolution parameters are fixed. Nevertheless, convolution settings can be treated as a variable model parameter.

```{image} figures/manual_convolution.png
:align: center
```

**Fig.20 The Convolution box** of a lifetime fit (Analysis dock), here with the
measured prompt of the IBH sample loaded as IRF. **IRF**: the measured
instrument response (**…** loads one, **×** unloads it; without one a synthetic
IRF is computed), with its full width at half maximum (**FWHM**, ns) beside it.
**Type**: *per* fast periodic exponential convolution, *exp* fast exponential
convolution (both for lifetime models), *full* direct convolution of the curve
with the IRF (needed for parsed equations). **Convolve** switches the
convolution on or off. The table holds the convolution parameters, each with
*Fixed*, the bounds *Lo*/*Hi* and *Bounds*, and the fitted *Error*: *n₀* the
number of photons (the scale of the model), *dt* the bin width, *rep* the
repetition rate (MHz) for periodic convolution, *stop* the end of the
convolution, *IRF_start*/*IRF_stop* the part of the IRF used, *lb* the IRF
background, *ts* the IRF time shift, and *IRF_w*, *IRF_k*, *IRF_pos* the width,
skewness and position of the synthetic IRF.

The primary challenge in time-resolved fluorescence experiments lies in the convolution with the instrument response function (IRF). Corrections are necessary to account for periodic excitation, and adjustments to parameters such as convolution start and stop points, as well as scaling of the model fluorescence decay to match the data (optional auto-scaling), are crucial. Incorporating background into the IRF and accounting for time shifts of the IRF further complicate the process. When an experimental IRF is unavailable, a synthetic IRF can be generated, often modeled as a skewed normal distribution. Parameters such as width and skewness of the synthetic IRF can then become free (variable) parameters during fitting and sampling, offering greater flexibility in the analysis process.

*Background.* The background is another significant nuisance in time-resolved fluorescence experiments. The fluorescence intensity is a combination of fluorescence signal and background components. Background can include constant elements, such as afterpulsing over long time scales, as well as other sources like scattered light, which is especially prominent in samples with weak fluorescence and strong scattering. Effectively accounting for background is essential for accurate analysis and interpretation of fluorescence data.

```{image} figures/manual_generic.png
:align: center
```

**Fig.21 The Generic box: background.** **Background**: a measured background
pattern (**…** loads one, **×** unloads it). *sc* the scatter pre-factor (the
IRF added as scattered light), *bg* a constant background offset, *tBg* and
*tMeas* the acquisition times of the background and of the measurement, and
*#Ph_B*, *#Ph_F* the numbers of background and fluorescence photons they give.

Various options exist for modeling the background: (1) incorporating scattering effects into the instrument response function, (2) including a constant offset to account for dark counts, and (3) employing a patterned offset (**Fig.21**). The acquisition times of both the background file and the experiment are essential, as they influence pile-up corrections. These acquisition times are utilized to compute the number of photons contributed by both the background and the fluorescence. The model used is typically a combination of the background and fluorescence components.

*Additional corrections.* TCSPC data can suffer from pile-up and differential non-linearities, which distort measurements and compromise accuracy. In this context, pile-up refers to the phenomenon where multiple photons arrive within the same time bin, while differential non-linearities, DNL, arise due to the system's response varying the time since the last sync pulse. Systems perturbed by DNLs show correlations for uncorrelated light. Considering these artifacts is crucial for extracting reliable information from TCSPC data.

```{image} figures/manual_corrections.png
:align: center
```

**Fig.22 The Corrections box: pile-up and differential non-linearity.**
**Lin. table**: the linearisation (white-light) table for the DNL correction
(**…** loads one, **×** unloads it). **Smoothing**: the window function used to
smooth the table, over *win-size* channels. **Pile-up**, **DNL** and
**Reverse** switch the pile-up correction, the DNL correction and reversing the
table. *tDead* is the instrument dead time used by the pile-up correction.

ChiSurf offers options to consider pile-up and DNLs. Instead of modifying the acquired data, the model function is perturbed to preserve the counting statistics for accurate error estimates.
