---
type: Guide
title: Driving ChiSurf from its console
description: The ability to ask the running application questions that no dialog answers — what is the chi-square of every fit I have open?, what does this parameter look like across the series?…
tags: [guides, fitting, console]
---

# Driving ChiSurf from its console

**What you get:** the ability to ask the running application questions that no
dialog answers — *what is the χ²ᵣ of every fit I have open?*, *what does this
parameter look like across the series?* — and to turn a sequence of clicks
into a script you can run again.

**What you need:** nothing. The console is the **Console** dock beside **Log**
at the bottom of the main window, and every example below works on an empty
session.

The console is a Python prompt *inside* the application. The fits and datasets
the windows show live in the session server; the console reaches them through
`api`, the session's `ChiSurfAPI`, on a connection of its own — the same calls
every dock makes.

## The first thing to know

Type an expression, press Enter, get a value:

```python
2 + 40
```
```
Out[1]: 42
```

A statement produces nothing, exactly as Python does. `_` is the previous
result, `__` the one before, and `Out[3]` any earlier one by number. The input
is its own box under the transcript.

## What is already in scope

| Name | What it is |
| --- | --- |
| `api` | the session's `ChiSurfAPI` (fits, datasets, parameters) |
| `cs` | the whole `chisurf` package |
| `gui` | the main window |
| `np`, `os` | numpy, os |
| `In`, `Out` | everything typed, and every result |

## Reading a fit

Load some data and add a fit as usual, then:

```python
fits = api.list_fits(statistics=True)
[(f["name"], round(f["chi2r_current"], 3)) for f in fits]
```

A row's `chi2r` is what the fit's last run reached (`None` for a fit not run
yet); `statistics=True` adds `chi2r_current`, the χ²ᵣ of the parameters as they
are now — the number the fit window shows. Parameters are read and written by
name:

```python
uid = fits[0]["uid"]
api.get_parameter("N", fit_uid=uid)["value"]
api.set_parameter_value("N", 2.0, fit_uid=uid)
```

A command that changes the science is one **Undo** step, named after the
command.

```{figure} figures/console.png
:name: fig-console
:width: 100%

The console asking about the FCS demo after **Fit**: `api.list_fits` returns the
fit the window shows, with its current χ²ᵣ, and `api.get_parameter` reads back
`N` = 2.0, the value the demo was made with.
```

Press `Tab` after `api.` to see what else is there — the list comes from asking
that object, so it is accurate for *this* session. `api.list_fits?` opens the
signature and docstring in a pane below the transcript (Escape closes it).

That is the kind of thing the console is for. There is no dialog that compares
χ²ᵣ across every open fit, and there does not need to be.

## Turning what you did into a script

Two ways round, and they meet in the middle.

**Record what you click.** *Macro ▸ Record* starts collecting; click it again to
stop and it offers to save a `.cm.py` file. Everything the GUI does goes through
the same action layer the console does, so a recording is real, runnable
Python. *Macro ▸ Run Macro…* replays one.

**Run a script into this session:**

```text
%run -i analysis.py
```

The `-i` is not optional in spirit: it runs the file *in the console's
namespace*, so anything the script defines is still there afterwards for you to
poke at. Without it the script gets a clean namespace and leaves nothing behind.

The **Code Editor** has a **Run** button that does the same thing — its *In
ChiSurf* endpoint runs in this process, with `cs` in scope, and streams output to
its panel as it goes.

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
  matplotlib is not a ChiSurf dependency: install it into the environment to
  plot this way.
* **Anything that draws itself** — an object with `_repr_png_` or `_repr_svg_`
  (an emtk or chiplot figure, a PIL image) shows as its picture. HTML-only
  objects show as their text.
* **Arrays** — `display(arr)` draws a 2-D array as a grey image (minimum to
  maximum) and an `(h, w, 3)` / `(h, w, 4)` array as RGB(A). A trailing `arr`
  stays text.

Right-click an image for **Copy image** (a PNG on the clipboard, to paste into a
slide) and **Save image as…**. Turning `gui.console.images` off in the settings
shows the text form instead.

## Keys

* **Blocks.** `for i in range(3):` then Enter gives an indented continuation
  line; a **blank line** ends the block and runs it. Shift+Enter always adds a
  line.
* **History.** Up and Down walk it, filtered by what you had typed; `Ctrl+R`
  searches it. While the console has the keys, `Ctrl+R` is the history search,
  not **Reinitialize**.
* **Completion.** Tab completes; `(` or Shift+Tab shows the call signature.
* **Editing.** `Ctrl+K` / `Ctrl+U` cut to the end / start of the line, `Ctrl+Y`
  puts it back, `Ctrl+L` clears the transcript.
* **Pasting works.** A snippet copied from a tutorial keeps its `>>>` prompts —
  they are stripped on paste.
* **Shell commands.** `!ls -l` runs one; `files = !ls` captures the output.
* **Interrupting.** `Ctrl+C` without a selection abandons the input. A runaway
  `print` loop cannot lock the window: output is drawn in batches and capped,
  with a note saying how much was dropped.
* **`%quickref`** is the one-page summary; `%lsmagic` lists every `%` command.
* `input()` raises `EOFError`: a frame cannot wait for a line.

Dead keys, accented letters and an input method (Japanese, Chinese, Korean) type
as in any other field: the text being composed is shown underlined at the cursor
until it is committed.

## In the Qt window

`python -m chisurf --qt` opens the legacy Qt window. Its console is the same
interpreter at an inline prompt, with `p` (pylab) in scope as well, and the
session lives in the same process: `cs.fits` and `cs.imported_datasets` are the
objects the windows show, so `cs.fits[0].chi2r` works there and `api` is not
needed. `%matplotlib qt` switches its figures to windows of their own.

## Headless

Everything above works without a GUI. The interpreter is a separate, Qt-free
package (`chisurf.core.console`), so a script, the `csc` CLI or the ZMQ server
reach the same API through `chisurf.core.api.ChiSurfAPI`. See
[Settings](../reference/settings.md) for the macro and scripting settings.

## Settings

The console reads `gui.console_init` (run at startup), `gui.console_style` (the
colour theme) and the optional `gui.console` block — scrollback cap, output
limit, completion style, paging, images. All of them are documented in
[Settings](../reference/settings.md).

## See also

- Tool: the **Code Editor** (`chisurf/plugins/core/code_editor/`).
- The console itself: `chisurf/emtk/console.py` (the dock) on
  `chisurf/core/console/` (the interpreter).
