---
type: Manual Page
title: 'Global view: overview'
description: In ChiSurf dependencies between parameters can be introduced by linking and visualized in graphs (Fig.31).
tags: [manual, fitting, global-analysis]
---

# Global view: overview

In ChiSurf dependencies between parameters can be introduced by linking and visualized in graphs (**Fig.31**). The *Global View* (*i*) draws the parameters of all fits and their links as a network, (*ii*) saves the network, values and links to a file, and (*iii*) restores them from one.

```{image} figures/globalview_include_fixed.png
:align: center
```

**Fig.31. A parameter network.** Four lifetime fits (a donor-only decay and three FRET decays) whose lifetime `t0` follows the donor-only fit's. Each fit is a large cyan node, owning its parameters; a linked parameter (green) has an arrow to the parameter it follows; free parameters are magenta, and with **Include fixed** ticked the fixed ones are shown too (grey).

```{image} figures/globalview_tool.png
:align: center
```

The *Global View* opens from **Tools ▸ Views ▸ Global View**, in a window of its own (**Fig.32**).

**Fig.32. The Global View window.** The network fills the **Network** tab (the **Parameters** tab lists the same parameters as a table); the minimap at the bottom right shows the part in view. The toolbar: **Load…** and **Save…** read and write a network file (GraphML), **Refresh** rebuilds the picture, **auto** redraws when a fit or a link changes, **Link** makes the second selected parameter follow the first, **Unlink** removes the selection's links (every link with **all**), **Fit view** fits the graph back into the panel, and **Guide** and **?** explain the window. On the right, **Selection** edits the selected parameters and **View** sets how the network is drawn (see [Changing visualizations](changing_visualizations.md)). The status line counts owners, parameters and links.
