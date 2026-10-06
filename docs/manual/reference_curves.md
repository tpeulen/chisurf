---
type: Manual Page
title: Reference curves
description: Fig.24 FRET model fit plots. (a) The fluorescence decay of the donor in the presence of an acceptor, $f_{D(A)}(t)$, can be plotted against the decay of the donor in the absence of an acceptor, $f_{D(0)}(t)$, as a reference.
tags: [manual, fret, fitting, tcspc, decay]
---

# Reference curves

```{image} figures/manual_donor_reference.png
:align: center
```

**Fig.24 A FRET fit drawn against its donor reference.** A FRET model with a
Gaussian distance distribution (*FRET: Gaussian distances*) fitted to the IBH
donor–acceptor sample (`Decay_577D+577A+GTPgS`). (**a**) The decay of the donor
in the presence of the acceptor, $f_{D(A)}(t)$, as measured. (**b**) The *Fit*
plot's settings with **Reference** set to *Donor reference* (its *scale*:
*data peak*), logY(fit) off and the IRF curve hidden (**E** unticked).
(**c**) The same curves divided by the donor-only decay the model predicts,
$f_{D(0)}(t)$ (the model with its donor-only fraction at one: same donor,
instrument and response): the ratio $f_{D(A)}(t) / f_{D(0)}(t)$ is the
FRET-induced donor decay, which isolates the transfer from everything the donor
does on its own. The distance distribution of a FRET fit is on the fit window's
*Distribution* page.

The selector is in the **Plot settings** of a FRET model's *Fit* plot (see [Fit plots](fit_plots.md), **Fig.18**); the transforms a model offers are listed there, with their parameters under it, 🔄 to reset them and 💾 to keep the current axis range as that transform's default. A reference curve is only meaningful when the two decays were measured under the same conditions — same IRF, same time axis, same background — because the ratio divides those out only if they are identical.
