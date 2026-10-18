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

**Fig.9 The Analysis dock.** Opened by the **Analysis** tab at the bottom of the dock area, it shows the active fit window's analysis (here the FRET decay of the IBH sample, the second window). At the top, the **Fit** section: **▶ Fit** runs the optimizer on the fit, **MCTS** searches the structures the model declares (Monte Carlo tree search) and keeps the best scored, **Sample** samples the posterior of the free parameters, ⚙ holds the sampling and fitting settings, **auto** chooses the fit range from the data, **…** attaches a different dataset, and **Local first** optimizes each dataset on its own before a global fit. **Dataset** selects which fit of the window the controls act on, **Result** which stored result is shown, and **First** / **Last** are the first and last channel of the fit. Below are the model's sections (*Convolution*, *Generic*, ...): each parameter in a row with its value, **Fixed**, its lower and upper bounds (**Lo**, **Hi**, active while **Bounds** is ticked) and the fitted **Error**.

The analysis dock contains the controls for optimizing the active fit, setting its fitting range, and sampling over the free model parameters (see **Fig.9**). For a fit over a dataset group, **Dataset** selects which member the controls act on.

The ChiSurf window has the same dock: the **Fit** section, then the model's own sections, each parameter group a table whose names carry their units (`D [µm²/s]`, `w_r [nm]`). **Code** in a fit window's top-right corner turns the window over to the model's source and its `view.json`; **Plots** turns it back. A dataset dragged from the **Datasets** table onto a fit window is attached to that fit, as **…** does.

In the native window the model's special sections are drawn too:

- **Curve pickers** (IRF, Background, Lin. table, a described model's measurements): **…** lists the session's datasets and the pick is copied into the model; **✕** unloads it. The IRF shows its FWHM.
- **Component tables** pair a component's parameters on one row (`x_L | τ_L`).
- **Right-click** a parameter (or a rate cell) for the link menu: *Link … to* → a fit → its parameter, and *Unlink*. A rate cell's menu also toggles *Fixed*.
- **κ² controls**: *dynamic κ²* / *static κ²*, *show κ²* (the κ² and R_app/R_DA distributions; *Fast* picks the loop-based convolution there), *compute κ²* (the κ² distribution calculator; *OK* uses its mean and distribution) and *calc R0* (the Förster radius calculator; *Apply* writes R₀).
- **Anisotropy**: *VV/VH diag* and *show r(t)* (data and model r(t), uncorrected and corrected, with g, l1, l2, the backgrounds and the VH–VV shift as live fields, *Reset* and *Save CSV*).
- **L-curve**: the sweep window (*min*, *max*, *N*), *⟳ sweep*, *⌾ corner*, and a click on the curve picks that weight.
- **Rate matrices**, **scalar tables**, a structure fit's **PDB ensemble** list, a mixture's **fits** (add, remove, fractions), a sampler's **start / stop** with its progress, and the global fit's **parameter table** (filter, column picker, *Link row*, export to CSV).

Every change goes to the model through the server; a section accepts only what the model's `view.json` declares.
