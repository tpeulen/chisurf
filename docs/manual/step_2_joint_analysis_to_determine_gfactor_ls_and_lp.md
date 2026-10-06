---
type: Manual Page
title: 'Step 2: Joint analysis to determine g-factor, ls and lp'
description: In the next step, the g-factor, l1 and l2 are no longer kept fixed to the initially estimated values but will also be fit and their respective check boxes are unticked.
tags: [manual, fitting, step, joint, analysis, determine, gfactor]
---

# Step 2: Joint analysis to determine g-factor, ls and lp

In the next step, the g-factor, l1 and l2 are no longer kept fixed to the initially estimated values
but are fit as well: untick their *Fixed* boxes in the *Anisotropy* section of the VV fit (the VH fit
follows through its links).

```{image} figures/anisotropy_step2_corrections_free.png
:align: center
```

The VV fit's editor with *g*, *l1* and *l2* free (their *Fixed* boxes empty).

Next, activate the "Global anisotropy" window and press **Fit** for the joint fit.

```{image} figures/anisotropy_step2_global_fit.png
:align: center
```

After the joint fit of VV and VH: flat residuals and a decaying autocorrelation. With a single dye the
three corrections are poorly determined -- here they drift to g ≈ 2.5 -- which is why the procedure
continues with a second, slowly rotating fluorophore (next pages).

The fit is not yet good. It seems there is a component missing the in beginning of the decay. A second lifetime can be added and linked between VV and VH.

```{image} _images/image_rId133.png
:align: center
```

Once the modifications have been done to the VV and VH datasets, switch back to the "Global fit" and press the update button before performing a global fit again. Now, the fit looks good with flat residuals and a decaying autocorrelation function.
