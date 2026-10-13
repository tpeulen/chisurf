---
type: Manual Page
title: Multiple document interface
description: The Workspace is where the fit windows live and are arranged; every tool is a dock beside it.
tags: [manual, multiple, document, interface, workspace, windows]
---

# Multiple document interface

The centre of the main window is the **Workspace**: it is where the fits live. Creating a fit opens its
window there, and the *Start* page fills it while there is none. A fit window can be moved, resized, folded
to its title bar, minimized and closed, but it cannot leave the Workspace: dragged past its edge it stops
there, it cannot be docked in another panel, and when the main window shrinks the windows are moved back
in. The Workspace itself cannot be closed or hidden; it keeps its place even when it is empty.

Tools are not Workspace windows. A tool opened from the menus, the ribbon or the Tools panel -- and the
help browser and the code editor -- opens as a **dock**, a tab of the panel right of the Workspace. Like
the *Read data*, *Analysis* or *Console* docks it can be dragged to another panel, tabbed with other docks,
floated over the main window or closed; it is never one of the Workspace's windows, and the Workspace's
commands leave it where it is.

```{image} figures/main_mdi_tiled.png
:align: center
```

```{image} figures/main_mdi_cascade.png
:align: center
```

```{image} figures/main_mdi_tabbed.png
:align: center
```

**Fig.17 The Workspace.** Top: two fit windows tiled in the Workspace (**Tile**); the *Histogram-Microtime*
and *Calculators* tools are docks right of it. Middle: the fits cascaded (**Cascade**), the first minimized
to the strip along the Workspace's bottom, and the **Windows** list open -- it lists the fits only. Bottom:
the fits as tabs (**Tabbed**), one shown at a time and chosen by its tab. The tools stay docked throughout.
**×** on a fit window closes only the window; the fit stays in the session.

## Arranging the windows

The Workspace's tool bar (along its top, right) and its right-click menu carry the commands; *View ▸
Workspace* has the same ones. They act on the fit windows (and *Start*), never on the tool docks:

| Command | What it does |
|---|---|
| **Tile** (*Tile Windows*) | Lays the windows out side by side in a near-square grid. No tile is smaller than 380 × 280 pixels; what does not fit is minimized and waits on the strip. |
| **Cascade** (*Cascade Windows*) | Floats the windows, each a title bar below and right of the last, the last one on top. |
| **Tabbed** (*Tab Windows*) | Makes every window a tab of the Workspace. |
| **Windows ▾** | Lists the windows (a minimized one says so); a click brings that window to the front. |
| *Next Window*, **Ctrl+Tab** | Brings the next window to the front; **Ctrl+Shift+Tab** goes back. Works while a tool has the keyboard; skips the tools. |

A fit window's **_** button minimizes it to the strip along the bottom of the Workspace; a click on its
chip brings it back. Dragging a fit window's tab off the Workspace's tab strip floats it in the Workspace
again; dropped elsewhere it stays in the Workspace. Dragging a tool dock by its title bar or tab onto a drop
target docks it in that panel (or beside the Workspace); the Workspace's own centre is not offered to it. The
arrangement -- which fits and tools are open, where they are, which are minimized -- is saved with the
window layout and comes back at the next start; a tool that an older layout had put into the Workspace
comes back as a dock.

Selecting another fit window calls:

```
cs.current_fit = chisurf.fits[0]
```

in the shell. The index "0" is the position of the selected window's fit in the list of open fits.
