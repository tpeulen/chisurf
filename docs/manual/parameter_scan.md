---
type: Manual Page
title: Parameter scan
description: A Chi Square support plane analysis around the minimum (the fitted solution) can be performed in in fits/model that offer a "Parameter scan".
tags: [manual, parameter, scan]
---

# Parameter scan

A Chi Square support plane analysis around the minimum (the fitted solution) can be performed in in fits/model that offer a "Parameter scan". In the parameter scan a free model parameter can be selected from a dropdown menu. The selected parameter is varied in a defined range. Other free model parameters are optimized.

```{image} figures/fit_window_parameter_scan.png
:align: center
```

**Fig.19 Parameter scan plots** are offered by fits of certain models. In the
**Plot settings** dock (left) pick the *Parameter*, the *Scan range* (relative
below and above the fitted value, and the number of steps) and press **scan**;
the other free parameters are re-optimised at every step, and the $\chi^2_r$
curve of the scanned parameter is drawn (right; the lifetime `t0` of the IBH
sample fit). **Smart scan** walks out from the optimum until each *p value*
threshold is crossed; *Bound range* keeps the scan inside the parameter's
bounds. The $\chi^2_r$ curve can be used to estimate the uncertainty of the
parameter.

This procedure (Support plane analysis) produces a $\chi^2_r$ curve of the scanned parameter that can be used to estimate uncertainties (**Fig.19**). Upper limits of $\chi^2_r$ at a chosen confidence level are computed with the {doc}`FRET/F-Calculator <fcalculator>`.

Reduced Chi Square
