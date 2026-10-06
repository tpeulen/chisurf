---
type: Manual Page
title: Calculation of the overlap volume and co-diffusion amplitude
description: 'From our double-labeled DNA measurements, we need to derive two important parameter:'
tags: [manual, diffusion, calculations]
---

# Calculation of the overlap volume and co-diffusion amplitude

From our double-labeled DNA measurements, we need to derive two important parameter:

The size of the overlapping confocal detection volume *Veff,PIE*

The Cross-correlation amplitude, which reflects 100 % co-diffusion

The size of the overlapping confocal detection volume can be determined using the already provided equations used in the sections above for the calculations of the confocal detection volume of the green and red channel.

In a first step, we use the obtained diffusion times from our *DNA_gp* and *DNA_rd* fits and determine the translational diffusion coefficient of our DNA sample:

and

Here, we obtain a value of **DDNA,green** **= 81.8 µm²/s** and **DDNA,red** **= 72.4 µm²/s** using the value of wo from A488 and A568 dye, respectively. Thus, in average **DDNA** **= 77.1 µm²/s**.

Based on this value, we can obtain *w0,PIE* and *z0,PIE*:

and

Here, **w0,PIE** **= 400 nm** and **z0,PIE** **= 1.85 µm**. This results in a **Veff,PIE** of **1.66 fL**:

Next, we observe the amplitudes of the auto- and cross correlation functions: In an ideal system the amplitudes of the three curves, *DNA_gp*, *DNA_rd* and *DNA_PIE* should be identical. However, as the detection volumes differ with the excitation and emission wavelength, this is rarely the case. In the next-optimal setting, the amplitude of *DNA_PIE* would be identical to the amplitude of the autocorrelation curve with the lower amplitude.

In common experimental settings, the overlap of the green and red confocal detection volumes is suboptimal and the apparent amplitude of a 100 % co-diffusion sample is required for calibration.

The concentration, and thus, later the fraction of co-diffusing particles in your sample, of double-labeled particles can be calculated based on the ratio of the correlation amplitudes:

and

where the amplitudes *G0,ACFgreen* and *G0ACF,red* are the inverse of the respective number of particles, *Ngreen* and *Nred*, in focus.

Here, we obtain amplitude ratios for 100 % co-diffusion of **ratioGR** **= 0.57** for the green and of **ratioRG** **= 0.68** for the red autocorrelation curves.

```{image} _images/image_rId82.png
:align: center
```

Now we are ready to switch to our real samples measured in live cells.
