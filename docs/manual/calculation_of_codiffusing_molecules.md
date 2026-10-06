---
type: Manual Page
title: Calculation of co-diffusing molecules
description: Based on the (apparent) number of molecules in focus and our determined correction factors for the confocal overlap volume from the DNA measurements, the fraction of double-labeled molecules can be calculated.
tags: [manual, corrections, calculation, codiffusing, molecules]
---

# Calculation of co-diffusing molecules

Based on the (apparent) number of molecules in focus and our determined correction factors for the confocal overlap volume from the DNA measurements, the fraction of double-labeled molecules can be calculated.

```{image} _images/image_rId92.png
:align: center
```

Here, *NeGFP* = 7.4, *NSNAP* = 12.1 and *Napp,PIE* = 91. The amplitudes at zero correlation time, G(*tc* = 0), are therefore: GeGFP(0) = 0.135, GSNAP(0) = 0.082, and GPIE(0) = 0.011.

Using the correction factors from the DNA measurement, only 15–26 % of the molecules carry both labels. However, (i) the data is quite noisy and (ii) the correlation amplitudes are very low. Both factors lead to large errors.

*Conclusion: Search for cells with low expression level, i.e. low fluorescence and take your time to collect a decent amount of photons to correlate!*
