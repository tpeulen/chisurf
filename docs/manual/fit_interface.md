---
type: Manual Page
title: Fit interface
description: The analysis dock displays an interface for sampling and optimization for the currently active window in the fit window Multiple Document Interface (MDI) (Fig.8).
tags: [manual, fitting, sampling]
---

# Fit interface

The analysis dock displays an interface for sampling and optimization for the currently active window in the fit window Multiple Document Interface (MDI) (**Fig.8**). The fitting and sampling interface allows to select the current dataset in a data group, replace a dataset with another loaded dataset, sample over variable model parameters, fit/optimize variable model parameters, and adjust the model range (**Fig.11**).

```{image} figures/manual_fit_controller.png
:align: center
```

**Fig.11 The Fit box at the top of the Analysis dock.** **▶ Fit** optimises
the free parameters ({doc}`parameter_optimization`); **MCTS** searches the
model structures the model declares with a Monte Carlo tree search; **Sample**
samples the posterior of the free parameters ({doc}`parameter_sampling`); **⚙**
opens the sampling and fitting settings; **auto** chooses the fit range from the
data (the rising edge to where the signal reaches the background); **…**
attaches a different dataset to this fit. **Local first** optimises each dataset
of a group on its own before the global fit. **Dataset** selects the dataset of
a group that is shown, **Result** which stored result of the fit is shown, and
**First**/**Last** are the first and last channel of the scoring range
({doc}`model_scoring_range`).
