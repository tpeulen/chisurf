---
type: Manual Page
title: Equation parsing
description: ChiSurf Equation Parser enables the computation of fluorescence decay according to any specified function, with equation parameters serving as model parameters.
tags: [manual, tcspc, decay]
---

# Equation parsing

ChiSurf Equation Parser enables the computation of fluorescence decay according to any specified function, with equation parameters serving as model parameters. Users can pick a predefined equation or type their own (**Fig.23**).

```{image} figures/manual_equation_parsing.png
:align: center
```

**Fig.23 A parsed decay equation** (model *Parse-Model*) fitted to the IBH
sample decay. In the **Equation** box, **Model** picks one of the predefined
equations (here *2-Lifetimes*); they ship with ChiSurf in
`chisurf/core/models/tcspc/parse/tcspc_model.yaml`, each with its initial
values and a description, shown under the equation. **f(x)** holds the equation
in Python syntax, with `x` the time: it is checked as it is typed (✓), committed
when you leave the field, and drawn as a formula under it. Every free name
becomes a parameter in the **Equation parameters** table (here `a1`, `tau1`,
`a2`, `tau2`, fitted). The Convolution, Generic and Corrections boxes are the
same as for the lifetime models ({doc}`nuisances`).

The Equation Parser operates by generating a curve for the equation on the time-axis, with the variable 'x' representing time. This curve is then convolved with the Instrument Response Function (IRF). ChiSurf offers various convolution modes, including fast convolution, fast periodic convolution, and curve convolution (*exp*, *per* and *full* under **Type** in the Convolution box). The latter mode is slower but necessary when parsing equations. Additionally, ChiSurf handles other nuisances in a similar manner as with fluorescence lifetime-based model functions.
