---
type: Manual Page
title: 'Step 1: Approximating g-factor with small fluorophore'
description: To start the analysis, first go to the "VV" dataset and perform a quick, individual fit of this dataset.
tags: [manual, fitting, step, approximating, gfactor, small, fluorophore]
---

# Step 1: Approximating g-factor with small fluorophore

To start the analysis, first activate the VV fit window and press **Fit** in the **Analysis** dock: a
quick, individual fit of this dataset. This sets at least the time shift between IRF and decay and the
background correctly.

```{image} figures/anisotropy_step1_vv_fit.png
:align: center
```

The VV and VH fits after their individual fits, with the corrections still fixed: the residuals show
that a single polarisation cannot be described on its own (bundled recording of
`test/data/tcspc/Jordi`).

In this step, still the g-factor, l1 and l2 are fixed to the initially estimated values. Next, also perform a quick fit on the VH dataset. Important note: The fit will not be good! This only serves to initialize the parameter.
