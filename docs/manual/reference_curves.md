---
type: Manual Page
title: Reference curves
description: Fig.24 FRET model fit plots. (a) The fluorescence decay of the donor in the presence of an acceptor, $f_{D(A)}(t)$, can be plotted against the decay of the donor in the absence of an acceptor, $f_{D(0)}(t)$, as a reference.
tags: [manual, fret, fitting, tcspc, decay]
---

# Reference curves

```{image} _images/image_rId31.png
:align: center
```

**Fig.24 FRET model fit plots.** (a) The fluorescence decay of the donor in the presence of an acceptor, $f_{D(A)}(t)$, can be plotted against the decay of the donor in the absence of an acceptor, $f_{D(0)}(t)$, as a reference. Choosing the reference in the **Reference** selector of the plot settings displays the ratio $f_{D(A)}(t) / f_{D(0)}(t)$ — the FRET-induced donor decay, which isolates the transfer from everything the donor does on its own. (b) FRET models can be displayed as distance distribution, FRET rate constant distribution of as fluorescence lifetime distribution. Fluorescence lifetime distributions can adopt more complex shapes for multi exponential donor fluorophores.

The selector is in the **Plot settings** of a FRET model's *Fit* plot (see [Fit plots](fit_plots.md), **Fig.18**); the transforms a model offers are listed there, with their parameters under it, 🔄 to reset them and 💾 to keep the current axis range as that transform's default. A reference curve is only meaningful when the two decays were measured under the same conditions — same IRF, same time axis, same background — because the ratio divides those out only if they are identical.
