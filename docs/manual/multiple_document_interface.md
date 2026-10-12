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

**Fig.17 Fit windows in the shell.** Each fit window is a dock window. Top: two fit windows floated side by side, every window visible at once. Bottom: the same windows docked as tabs of the central area, one shown at a time and chosen by its tab. Drag a window's title bar to float or tile it, drop it on the tab strip to dock it again; **×** closes only the window, the fit stays in the session.

Fit windows are arranged by dragging them (**Fig.17**). Selecting another fit window calls:

```
cs.current_fit = chisurf.fits[0]
```

in the shell. The index "0" is the position of the selected window's fit in the list of open fits.
