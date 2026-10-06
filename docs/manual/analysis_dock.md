---
type: Manual Page
title: Analysis dock
description: The analysis dock gathers variables and parameters of the currently active fit window (see Fig.9).
tags: [manual, fitting, analysis, dock]
---

# Analysis dock

The analysis dock gathers variables and parameters of the currently active fit window (see **Fig.9**). The Analysis dock changes its content depending on the currently active fit (the activated fit window).

```{image} figures/main_analysis_dock.png
:align: center
```

**Fig.9 The Analysis dock.** Opened by the **Analysis** tab at the bottom of the dock area, it shows the active fit window's analysis (here the FRET decay of the IBH sample, the left window). At the top, the **Fit** section: **▶ Fit** runs the optimizer on the fit, **MCTS** searches the structures the model declares (Monte Carlo tree search) and keeps the best scored, **Sample** samples the posterior of the free parameters, ⚙ holds the sampling and fitting settings, **auto** chooses the fit range from the data, **…** attaches a different dataset, and **Local first** optimizes each dataset on its own before a global fit. **Dataset** selects which fit of the window the controls act on, **Result** which stored result is shown, and **First** / **Last** are the first and last channel of the fit. Below are the model's sections (*Convolution*, *Generic*, ...): each parameter in a row with its value, **Fixed**, its lower and upper bounds (**Lo**, **Hi**, active while **Bounds** is ticked) and the fitted **Error**.

The analysis dock contains the controls for optimizing the active fit, setting its fitting range, and sampling over the free model parameters (see **Fig.9**). For a fit over a dataset group, **Dataset** selects which member the controls act on.
