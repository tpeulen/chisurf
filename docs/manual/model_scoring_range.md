---
type: Manual Page
title: Model scoring range
description: The value of the score depends on the data that is used for scoring.
tags: [manual, model, scoring, range]
---

# Model scoring range

The value of the score depends on the data that is used for scoring. Often, the model is scored in a particular data range. In cases where the data are curves, the scoring range is defined by an upper and lower value (fit range). In the graphical user interface, the scoring range is adjusted either in the Fit box of the Analysis dock or directly in a plot of the data and the model (**Fig.12**).

```{image} figures/manual_scoring_range.png
:align: center
```

**Fig.12 Adjusting the scoring range.** The range is set by **First** and
**Last** (channels) in the Fit box of the Analysis dock (left), or by dragging
the edges of the shaded region on the *Fit* plot (right); the two follow each
other, and the box in the plot reports the range and the resulting χ²ᵣ.
**auto** in the Fit box picks the range from the data.

In the programming shell the fit range of the current fit is adjusted using integers as lower and upper bounds that correspond the index of the data.

```
fit = cs.current_fit
fit.fit_range = 61, 649
```

In this example, 61, 649 is the lower and upper bound, respectively.
