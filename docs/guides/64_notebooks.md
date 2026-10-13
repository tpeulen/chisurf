---
type: Guide
title: Notebooks that run inside ChiSurf
description: Open and run an .ipynb in the code editor against the application's own interpreter, so the cells see the fits and datasets the GUI is showing.
tags: [guides, gui, notebooks]
---

# Notebooks that run inside ChiSurf

**What you get:** an `.ipynb` that runs against *this* session — the same
`cs.fits`, the same loaded datasets, the same in-memory objects the windows are
drawing — with figures embedded under the cell that drew them, and a saved file
any Jupyter reader can open.

**What you need:** the Code Editor tool (`Tools → System → Code Editor`)
and a notebook. `File → Open Notebook…` lists the ones ChiSurf ships under
`examples/notebooks`, grouped by their name's prefix; click one to open it.

There is no Jupyter kernel and no browser here. A notebook tab executes its
cells through the same interpreter as the [console](59_console.md), so the two
share variables and there is nothing to synchronise or export.

![A notebook tab: the toolbar, cells with their prompts in their headers, an embedded figure, and the kernel terminal docked beside Diagnostics and Output](figures/notebook_editor.png)

## Running cells

`Ctrl+Enter` runs the cell the cursor is in, `Shift+Enter` runs it and moves to
the next one, and **▶ Run · Shift+Enter** in the cell's header does the same. The
`In [n]` in the header is the execution count, shared with the Kernel dock — one
kernel, two surfaces.

A cell's output appears directly under it and is **exactly as tall as what it
holds**: one line for one line, the whole figure for a figure. Output past
360 px scrolls inside the cell rather than pushing the next cell off screen.

Markdown cells are shown rendered. **Edit Markdown** in the header opens the
source, **Preview** (or running the cell) renders it back.

## The toolbar

| Control | What it does |
| --- | --- |
| **▶ Run all** | Every code cell, top to bottom |
| **＋ Code cell** / **＋ Markdown** | Append a cell |
| **Restart** | Discards the kernel's variables; the cells keep their source |
| **Clear outputs** | Empties every output and execution count |
| **Terminal** | Shows or hides the **Kernel** dock at the bottom of the window |
| **Reload notebook** / **Export Python** | Re-read the file from disk (asks before discarding edits) / write the cells as a `.py` script |

## Plots

`%matplotlib inline` is already on. A cell that draws a figure gets the PNG
embedded in its own output, scaled to the width of the cell — so a wide figure
shrinks rather than needing a sideways scrollbar. Ending a cell with `fig`
shows the image, not the figure's `repr`.

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(4.2, 2.6))
ax.semilogy(t, decay, lw=1.5)
ax.set_xlabel('time / ns')
ax.set_ylabel('intensity')
fig
```

The figure lives in the cell that produced it. It is not also painted into the
Kernel dock — that panel is for stream output and for commands you type there
yourself.

## The kernel terminal

The **Kernel** dock at the bottom of the window -- tabbed with Diagnostics and
Output, and movable like any other panel -- is a full prompt on the notebook's
kernel. Anything defined in a cell is available there and vice versa, which
makes it the natural place to poke at a variable mid-analysis without adding a
cell you will delete again.

Each notebook tab has its own kernel, so the dock follows the tab in front. A
tab that is not a notebook leaves it empty and disabled -- there is no kernel
to talk to.

When a cell runs, a one-line marker of its source is typed onto that prompt so
the log says *which* cell produced the output beneath it:

```
In [1]: import numpy as np  … (+3 lines)
In [2]: for name, value in [('tau', 2.4), …  … (+1 lines)
   tau = 2.4
     n = 512
```

## Adding and removing cells

`＋ Code cell` and `＋ Markdown` on the toolbar append a cell. The `＋` in a
cell's header inserts an empty code cell *below it*, `↑`/`↓` move it, and the
`×` deletes it — including a rendered markdown cell, without opening it for
editing first. The type box switches a cell between code, markdown and raw.

## Saving

`Ctrl+S` writes the tab back as notebook format 4 (byte for byte what
`nbformat` writes; `code_editor/ipynb.py`), so cell metadata the notebook arrived
with survives the round-trip and the outputs currently on screen are written into
the file. A notebook that fails to parse opens as a plain text tab
instead, which is how you fix a corrupt one.

## Where this sits

The notebook tab is part of the code editor plugin's emtk window
(`chisurf/plugins/core/code_editor/gui/notebook_app.py`), and the interpreter
behind it is `chisurf.core.console.shell.Shell` — the same class documented in
[Driving ChiSurf from its console](59_console.md). Every panel of that window,
Kernel included, is a dock of the same dock manager, so they move, float and
tab together.

## Theory

- [Global analysis](../concepts/global_analysis.md): the fits and datasets a notebook sees are the ones the global analysis holds.
