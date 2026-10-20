---
type: Guide
title: Driving ChiSurf from its console
description: The ability to ask the running application questions that no dialog answers — what is the chi-square of every fit I have open?, what does this parameter look like across the series?…
tags: [guides, fitting, console]
---

# Driving ChiSurf from its console

**What you get:** the ability to ask the running application questions that no
dialog answers — *what is the chi-square of every fit I have open?*, *what does
this parameter look like across the series?* — and to turn a sequence of commands
into a script you can run again.

**What you need:** nothing. The console is the **Console** dock beside **Log**,
and every example below works on an empty session.

The Console dock hosts the Terminal tool (`chisurf/plugins/core/terminal/`): a
strip of pane actions (**New**, **Terminal**, **Python**, **Split ⇥**,
**Split ⇣**, **Close**, **Guide**, **Help**) over the window's own Python pane. More
Python panes or shell panes open beside it; panes, splits and keys are in
{doc}`110_terminal`, the theory in {doc}`../concepts/terminal`.

```{figure} figures/console_dock.png
:name: fig-console-dock
:width: 100%

The main window with the Console dock in front: the Terminal strip, then
Python pane 1 after `2 + 40`.
```

The Python pane is a prompt *inside* the application, not a separate interpreter
talking to it over a wire: no synchronisation step, no export.

## The first thing to know

Type an expression, press Enter, get a value:

```python
2 + 40
```
```
Out[1]: 42
```

A statement produces nothing, exactly as Python does. `_` is the previous
result, `__` the one before, and `Out[3]` any earlier one by number.

## What is already in scope

| Name | What it is |
| --- | --- |
| `api` | the session's `ChiSurfAPI`: fits, datasets, parameters |
| `cs` | the `chisurf` package |
| `gui` | the main window |
| `np`, `os` | numpy, os |
| `In`, `Out` | everything typed, and every result |

`api` talks to the session on a connection of the console's own, like every
dock; it appears once the session is up.

## Reading a fit

Load some data and add a fit as usual, then:

```python
fits = api.list_fits(statistics=True)
[(f["name"], round(f["chi2r_current"], 3)) for f in fits]
api.get_parameter("N", fit_uid=fits[0]["uid"])["value"]
```

A row's `chi2r` is what the fit's last run reached (`None` for a fit not run
yet); `statistics=True` adds `chi2r_current`, the χ²ᵣ of the parameters as they
are now — the number the fit window shows. Setting a value:

```python
api.set_parameter_value("N", 2.0, fit_uid=fits[0]["uid"])
```

A command that changes the science is one **Undo** step, named after the
command.

```{figure} figures/console.png
:name: fig-console
:width: 100%

The console asking `api` about the FCS demo after **Fit**: the comprehension
reads χ²ᵣ of every open fit at once, and `get_parameter` reads back `N`.
```

Press `Tab` after `api.` to see what else is there — the list comes from asking
that object. `api.list_fits?` opens the signature and docstring in a pane below
the transcript.

## Turning what you did into a script

**Record.** *Macro ▸ Record* starts collecting what runs in the console; click
it again to stop and it offers to save a `.cm.py` file. *Macro ▸ Run Macro…*
replays one.

**Run a script into this session:**

```text
%run -i analysis.py
```

The `-i` runs the file *in the console's namespace*, so anything the script
defines is still there afterwards. Without it the script gets a clean namespace
and leaves nothing behind.

The [Code Editor](../concepts/code_editor.md) is for a script you keep.

## Long commands and Ctrl+C

A cell runs on the console's own worker thread, so the window keeps drawing
while it runs and its `print` output streams into the transcript line by line.
A strip over the input shows **Running… 3.2 s**, how many cells are queued
behind it, and an **Interrupt** button. Typing and pressing Enter while a cell
runs queues the next cell; it starts when the first is done.

**Ctrl+C** (without a selection) or **Interrupt** stops the running cell:

```text
In [3]: while True: pass

KeyboardInterrupt
```

and drops the cells that were queued behind it; the console is ready for the
next command at once. The interrupt lands at the cell's next Python bytecode,
so a cell sitting in one long C call — `time.sleep(60)`, a single large numpy
operation, a blocking file read — stops only when that call returns. Loops of
such calls stop at the next iteration.

What a cell does to the window is done by the window: `gui` is a proxy whose
method calls (`gui.docks.focus("fits")`, `gui.request_frame()`) run on the
window's thread between two frames and hand back their value. `api` needs no
such care — it talks to the session over the console's own connection, so
`api.add_fit(...)`, `api.run_fit(...)` from a cell work as they do from a dock.
A cell cannot call `signal.signal` (that is reserved to the main thread).

## Plotting

Plots appear in the console, under the cell that drew them, as in a notebook —
no `%matplotlib` line needed:

```python
import pylab as plt
x = np.linspace(0, 10); y = np.sin(x)
plt.plot(x, y)
```

```{figure} figures/console_inline_plot.png
:name: fig-console-inline-plot
:width: 80%

The cell's value (`Out[1]`, the list of lines `plt.plot` returns) and, after
the cell, the figure itself. It is narrowed to the console's width with its
aspect kept, re-fitted when the console is resized, and scrolls with the text.
```

What ends up in the transcript as a picture:

* **matplotlib / pylab figures** — every figure the cell drew, after the cell;
  `plt.show()` shows them at once (it never blocks or opens a window) and
  `fig.show()` shows one. Each is closed once shown, so the next cell starts a
  new figure; evaluate `fig` to show a figure you kept a handle on again.
  `%config InlineBackend.figure_format = 'svg'` (or `'retina'`) changes the
  format. matplotlib is not a ChiSurf dependency: install it into the
  environment to plot this way.
* **Anything that draws itself** — an object with `_repr_png_` or `_repr_svg_`
  (an emtk or chiplot figure, a PIL image) shows as its picture. HTML-only
  objects show as their text.
* **Arrays** — `display(arr)` draws a 2-D array as a grey image (minimum to
  maximum) and an `(h, w, 3)` / `(h, w, 4)` array as RGB(A). A trailing `arr`
  stays text.

Right-click an image for **Copy image** (a PNG on the clipboard) and **Save
image as…**. Turning `gui.console.images` off shows the text form instead.

## Keys

* **Enter** runs a complete statement or opens an indented continuation line
  (`for i in range(3):`); a **blank line** ends the block. **Shift+Enter**
  always adds a line.
* **Tab** completes against the live objects; `(` or **Shift+Tab** shows the
  call signature; `obj?` opens the help pane (`obj??` with source), **Esc**
  closes it.
* **Up / Down** walk the history, filtered by what you had typed; **Ctrl+R**
  searches it (while the console has the keys, Ctrl+R is not *Reinitialize*).
* **Ctrl+K / Ctrl+U** cut to the end / start of the line, **Ctrl+Y** puts it
  back, **Ctrl+L** clears, **Ctrl+C** interrupts the running cell, or abandons
  the input when none runs (with a selection it copies).
* Pasted `>>>` and `In [1]:` prompts are stripped.
* `!ls -l` runs a shell command; `files = !ls` captures the output.
* `%quickref` is the one-page summary; `%lsmagic` lists every `%` command.

The input is its own box under the transcript; `input()` raises `EOFError`.
Dead keys, accented letters and an input method (Japanese, Chinese, Korean) type
as in any other field.

## Headless

Everything above works without a window. The interpreter is
`chisurf.core.console`, and a script, the `csc` CLI or the ZMQ server reach the
same API through `chisurf.core.api.ChiSurfAPI`.

## Settings

The console reads `gui.console_init` (run at startup) and the optional
`gui.console` block — scrollback cap, history length, banner, completion,
calltips, paging, inline figures. All of them are documented in
[Settings](../reference/settings.md).

## See also

- Guide: {doc}`110_terminal` — panes, splits, shell panes.
- Concept: {doc}`../concepts/terminal` — what runs where, and the security note.
- Tool: the **Code Editor** (`chisurf/plugins/core/code_editor/`).
- The console itself: `chisurf/emtk/console.py` (the dock) on
  `chisurf/core/console/` (the interpreter).
