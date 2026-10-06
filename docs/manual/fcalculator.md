---
type: Manual Page
title: F-Calculator
description: Fig.25 F-Calculator. Convert between the quantities of a FRET measurement, and compute the F-values used to put a confidence level on a parameter scan.
tags: [manual, fret, fcalculator]
---

# F-Calculator

```{image} _images/image_rId32.png
:align: center
```

**Fig.25 F-Calculator.** Convert between the quantities of a FRET
measurement, and compute the F-values used to put a confidence level on a
{doc}`parameter scan <parameter_scan>`.

The calculator is the **FRET / homoFRET** entry of the calculators hub
(**Tools → Calculators → Calculators**). It is a small
set of coupled fields: change any one of them and the rest follow, which makes
it the fastest way to answer "what distance does that efficiency correspond to"
without setting up a fit.

It relates

- the FRET efficiency $E$,
- the donor-acceptor distance $R$,
- the Förster radius $R_0$,
- the donor lifetimes with and without acceptor, $\tau_{DA}$ and
$\tau_D$,
- the FRET rate constant $k_{FRET}$,
- and the width $\sigma$ of a Gaussian distance distribution.

With $\sigma = 0$ the calculator uses a single distance,
$E = 1/(1 + (R/R_0)^6)$. With $\sigma > 0$ it averages over the
distribution instead — which is the honest calculation whenever a flexible
linker is involved, and gives a different answer: averaging the *rate* and
inverting is not the same as inverting the average distance
({ref}`concept-fret`).

For the theory of the correction factors that stand between measured signals and
$E$, see {ref}`concept-accurate-fret`; for the calculator's own reference
page, {doc}`/reference/plugins/fret_calculator`.
