---
type: Manual Page
title: Changing visualizations
description: The visualization of the graph is controlled by widgets in the visualization box (Fig.33).
tags: [manual, changing, visualizations]
---

# Changing visualizations

The drawing of the graph is set in the **View** tab on the right of the Global View (**Fig.33**).

```{image} figures/globalview_view_tab.png
:align: center
```

```{image} figures/globalview_include_fixed.png
:align: center
```

**Fig.33.** The **View** tab (top). **Show** chooses the *Parameter network* (fits, their parameters and links) or the *Factor graph* (each dataset's likelihood and the parameters it reads); **Layout** the algorithm that places the nodes (*kamada_kawai* and *spring* keep linked parameters together); **Node size** the radius of a parameter node in pixels; **Spread** pulls a crowded graph apart without changing its layout; **Connect base** draws a line between every pair of owners; **Include fixed** also shows parameters held fixed. Bottom: the same network with a node size of 9 and **Include fixed** ticked.

The position of nodes can be controlled by dragging nodes of the graph.
