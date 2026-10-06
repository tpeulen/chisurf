---
type: Manual Page
title: Multiple document interface
description: The multiple document interface displays fits created using the graphical user interface as windows.
tags: [manual, multiple, document, interface]
---

# Multiple document interface

The multiple document interface displays fits created using the graphical user interface as windows. Creating a fit opens a window for it (**Fig.17**). Fit documents in the MDI are windows that can be freely positioned, minimized, and closed. Closing a document closes the corresponding instance of a fit.

```{image} _images/image_rId24.png
:align: center
```

**Fig.17 Elements controlling windows in the multi document interface.** The toolbar of a ChiSurf window can be used to open data (with the current data reader), save fits to files, close the currently open fit, tile windows in the multi document interface (MDI), stack windows in the MDI, and to control macros. When windows are tiled, all windows will be displayed in the MDI at once (top right). When windows are stacked a toolbar in the MDI controls which window is currently displayed in the MDI.

Fit documents can be tiled and stacked from that toolbar (**Fig.17**). Selecting another fit window calls:

```
cs.current_fit = chisurf.fits[0]
```

in the shell. The index "0" is the position of the selected window's fit in the list of open fits.
