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

The *Analysis* dock of the VV fit with *g*, *l1* and *l2* free (their *Fixed* boxes empty).

Next, activate the "Global anisotropy" window and press **Fit** for the joint fit.

```{image} figures/anisotropy_step2_global_fit.png
:align: center
```

After the joint fit of VV and VH (the *Global anisotropy* window in the centre, the *Analysis* dock
listing its local fits): a joint χ²ᵣ of about 2 (VV ≈ 1.2, VH ≈ 2.8), the residuals flat but for the
first channels of VH, under the peak. With a
single dye the three corrections are poorly determined -- on the bundled recording g wanders anywhere
between ≈ 1 and ≈ 10 at the same chi2r, and l1 and l2 with it -- which is why the procedure continues with
a second, slowly rotating fluorophore (next pages).

The bundled recording is not the manual's original Alexa488/eGFP data (those were 20 ps channels at
20 MHz) but a small, fast-rotating dye (tau ≈ 2.9 ns, rho < 1 ns, 80 MHz at 8 ps). Its curves rise again
over the last ≈ 100 channels of the gate; no model describes that edge, so the default fit range stops in
front of it (and starts at 90 % of the peak). The *Repetition rate (MHz)* of the wizard is the model's excitation
period, so type the rate of your laser. The g-factor, l1 and l2 values of the original data (below) are
not reproduced by the bundled recording.

The fit is not yet good. It seems there is a component missing the in beginning of the decay. A second lifetime can be added and linked between VV and VH.

```{image} _images/image_rId133.png
:align: center
```

Once the modifications have been done to the VV and VH datasets, switch back to the "Global fit" and press the update button before performing a global fit again. Now, the fit looks good with flat residuals and a decaying autocorrelation function.
