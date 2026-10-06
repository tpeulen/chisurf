---
type: Manual Page
title: Multiple document interface
description: The multiple document interface displays fits created using the graphical user interface as windows.
tags: [manual, multiple, document, interface]
---

# Multiple document interface

The multiple document interface displays fits created using the graphical user interface as windows. Creating a fit opens a window for it (**Fig.17**). Fit documents in the MDI are windows that can be freely positioned, minimized, and closed. Closing a document closes the corresponding instance of a fit.

```{image} figures/main_mdi_tiled.png
:align: center
```

```{image} figures/main_mdi_tabbed.png
:align: center
```

**Fig.17 Fit windows in the multiple document interface.** The toolbar under the menu bar holds, from the left: **Add dataset** (with the current reader), **Save all fits**, **Close fit**, then **Tile Windows**, **Tab Windows** and **Reset Layout**, **Screenshot**, and **Quit**. Top: two fit windows tiled, every window visible at once. Bottom: the same windows tabbed, one shown at a time and chosen by its tab; **Tile Windows** returns to separate windows.

Fit windows are tiled or tabbed from that toolbar (**Fig.17**). Selecting another fit window calls:

```
cs.current_fit = chisurf.fits[0]
```

in the shell. The index "0" is the position of the selected window's fit in the list of open fits.
