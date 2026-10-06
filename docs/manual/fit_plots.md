---
type: Manual Page
title: Fit Plots
description: Fits display (depending on the model) different plots, chosen from the tab bar of the fit window; the settings of the current plot are shown in the Plot settings dock.
tags: [manual, fitting, plots, plot-settings]
---

# Fit Plots

Fits display (depending on the model) different plots, chosen from the tab bar of
the fit window in the MDI (**Fig.18**). The settings of the current plot are
shown in the **Plot settings** dock; switching tabs, or fit windows, switches
what the dock shows. A plot without settings says so in the dock.

```{image} figures/fit_window_plot_settings.png
:align: center
```

**Fig.18 Plots in fit windows.** Right: a lifetime fit of the IBH sample decay
with its measured prompt; the tab bar of the fit window selects the plot (*Fit*,
*Data table*, *Info*, *Parameter scan*, ...). Left: the **Plot settings** of the
*Fit* plot. Both are drawn by emtk; the dock is one surface that draws the
current plot's settings.

Most fit models display line plots of the data and the model function, with the
weighted residuals and their autocorrelation above them (**Fig.18**, right). The
*Fit* plot's settings (**Fig.18**, left):

| Control | What it does |
|---|---|
| logX, logY(fit) | Logarithmic x axis; logarithmic data and model (the residual strips stay linear). |
| Density | Divide data and model by the bin width, so curves with different binnings compare. |
| display group | Draw every fit of a group; the current one is highlighted, the others transparent. |
| Reference, 🔄, 💾 | Draw the curves relative to a reference the model offers (see [Reference curves](reference_curves.md)); reset its parameters; save the current axis range as that mode's default. |
| xmin, xmax, ymin, ymax | Ticked: fix that end of the axis to the value beside it. Unticked: the axis follows the data. |
| x-shift, y-shift | Shift every curve for display; the fit is unchanged. |
| # / E / Name | The curves; untick **E** to hide one. |

```{image} figures/fit_window_reference_settings.png
:align: center
```

**Fig.18b logX.** The same fit with *logX* ticked: the rise and the IRF take the
width they need, the tail is compressed.

```{image} figures/fit_window_info_settings.png
:align: center
```

**Fig.18c The Info plot.** The fit report (right) and its settings (left): the
analysis record (*Analysis*), free-form *Metadata*, *External data* references
(drop files on the dock to add them) and the mmCIF *Export*.

The figures are made by `docs/guides/screenshots/fit_window_emtk.py`.
