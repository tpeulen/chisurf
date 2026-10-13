---
type: Manual Page
title: Multiple document interface
description: The Workspace holds every window that is not docked -- fit windows, tools, floated panels -- and arranges them.
tags: [manual, multiple, document, interface, workspace, windows]
---

# Multiple document interface

The centre of the main window is the **Workspace**. Every window that is not docked lives in it: the fit
windows (creating a fit opens one), the tools opened from the menus, the ribbon or the Tools panel, the help
browser and the code editor, and any panel dragged off its dock. A window in the Workspace can be moved,
resized, folded to its title bar, minimized and closed, but it cannot leave the Workspace: dragged past its
edge it stops there, and when the main window shrinks the windows are moved back in. Nothing can end up
behind the main window or off screen. The Workspace itself cannot be closed or hidden; it keeps its place
even when it is empty.

```{image} figures/main_mdi_tiled.png
:align: center
```

```{image} figures/main_mdi_cascade.png
:align: center
```

```{image} figures/main_mdi_tabbed.png
:align: center
```

**Fig.17 The Workspace.** Top: two fit windows, the *Histogram-Microtime* tool and the *Start* page, tiled
(**Tile**). Middle: the same windows cascaded (**Cascade**), the first fit minimized to the strip along the
Workspace's bottom, and the **Windows** list open. Bottom: the same windows as tabs (**Tabbed**), one shown
at a time and chosen by its tab. **×** on a fit window closes only the window; the fit stays in the session.

## Arranging the windows

The Workspace's tool bar (along its top, right) and its right-click menu carry the commands; *View ▸
Workspace* has the same ones:

| Command | What it does |
|---|---|
| **Tile** (*Tile Windows*) | Lays the windows out side by side in a near-square grid. No tile is smaller than 380 × 280 pixels; what does not fit is minimized and waits on the strip. |
| **Cascade** (*Cascade Windows*) | Floats the windows, each a title bar below and right of the last, the last one on top. |
| **Tabbed** (*Tab Windows*) | Makes every window a tab of the Workspace. |
| **Windows ▾** | Lists the windows (a minimized one says so); a click brings that window to the front. |
| *Next Window*, **Ctrl+Tab** | Brings the next window to the front; **Ctrl+Shift+Tab** goes back. Works while a tool has the keyboard. |

A window's **_** button minimizes it to the strip along the bottom of the Workspace; a click on its chip
brings it back. Dragging a window by its title bar onto a drop target docks it in that region; dragging a
tab off its strip floats it in the Workspace again. The arrangement -- which windows are open, where they
are, which are minimized -- is saved with the window layout and comes back at the next start.

Selecting another fit window calls:

```
cs.current_fit = chisurf.fits[0]
```

in the shell. The index "0" is the position of the selected window's fit in the list of open fits.
