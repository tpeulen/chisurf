---
type: Guide
title: Driving ChiSurf from its console
description: The ability to ask the running application questions that no dialog answers — what is the chi-square of every fit I have open?, what does this parameter look like across the series?…
tags: [guides, fitting, console]
---

# Driving ChiSurf from its console

**What you get:** the ability to ask the running application questions that no
dialog answers — *what is the chi-square of every fit I have open?*, *what does
this parameter look like across the series?* — and to turn a sequence of clicks
into a script you can run again.

**What you need:** nothing. The console is the dock at the bottom of the main
window, and every example below works on an empty session.

The console is a Python prompt *inside* the application, not a separate
interpreter talking to it over a wire. There is no synchronisation step and no
export: the objects at the prompt **are** the objects the GUI is showing.

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
| `cs` | the whole `chisurf` package |
| `gui` | the main window |
| `np`, `os`, `p` | numpy, os, pylab |
| `In`, `Out` | everything typed, and every result |

The two that matter in practice:

```python
cs.imported_datasets      # everything loaded
cs.fits                   # every fit open
```

## Reading a fit

Load some data and add a fit as usual, then:

```python
fit = cs.fits[0]
fit.chi2r
```
```
Out[2]: 1.0312...
```

Press `Tab` after `fit.` to see what else is there — the list comes from asking
that object, so it is accurate for *this* fit rather than for a class in
general. `fit?` opens the type, signature and docstring in a pane below the
console.

Parameters come back as a dictionary:

```python
fit.model.parameters_all_dict
```

which makes a question across several fits a one-liner:

```python
[(f.name, round(f.chi2r, 3)) for f in cs.fits]
```

```{figure} figures/console.png
:name: fig-console
:width: 100%

The console answering exactly that, on a session with two fits open. `cs.fits`
is the live list — the objects the GUI is showing, not a copy — so `fit.chi2r`
reads the number the fit window is displaying, and the comprehension asks the
same question of every fit at once without touching a dialog. Note `Out[3]` and
the entry for *Donor-only* in `Out[4]` agree: there is only one object.
```

That is the kind of thing the console is for. There is no dialog that compares
chi-square across every open fit, and there does not need to be.

## Turning what you did into a script

Two ways round, and they meet in the middle.

**Record what you click.** *Macro ▸ Record* starts collecting; click it again to
stop and it offers to save a `.py` file. Everything the GUI does goes through
the same action layer the console does, so a recording is real, runnable Python.

**Run a script into this session:**

```text
%run -i analysis.py
```

The `-i` is not optional in spirit: it runs the file *in the console's
namespace*, so anything the script defines is still there afterwards for you to
poke at. Without it the script gets a clean namespace and leaves nothing behind.

The [script editor](../reference/settings.md) has a **Run** button that does the
same thing — its *In ChiSurf* endpoint runs in this process, with `cs` in scope,
and streams output to its panel as it goes.

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
  format, `%matplotlib inline` is accepted (older settings files start with
  it), and `%matplotlib qt` switches to figures in their own windows, which is
  what you want once you need to zoom. matplotlib is not a ChiSurf dependency:
  install it into the environment to plot this way.
* **Anything that draws itself** — an object with `_repr_png_` or `_repr_svg_`
  (an emtk or chiplot figure, a PIL image) shows as its picture. HTML-only
  objects show as their text.
* **Arrays** — `display(arr)` draws a 2-D array as a grey image (minimum to
  maximum) and an `(h, w, 3)` / `(h, w, 4)` array as RGB(A). A trailing `arr`
  stays text.

Right-click an image for **Copy image** (a PNG on the clipboard, to paste into a
slide) and **Save image as…**. Turning `gui.console.images` off shows the text
form instead.

## Things worth knowing

* **Blocks.** `for i in range(3):` then Enter gives an indented continuation
  line; a **blank line** ends the block and runs it.
* **Pasting works.** A snippet copied from a tutorial keeps its `>>>` prompts —
  they are stripped on paste. Copying out of the console gives runnable code
  with the `In [n]:` labels removed.
* **Shell commands.** `!ls -l` runs one; `files = !ls` captures the output.
* **Interrupting.** `Ctrl+C` stops a long command. A runaway `print` loop cannot
  lock the window: output is drawn in batches and capped, with a note saying how
  much was dropped.
* **`%quickref`** is the one-page summary; `%lsmagic` lists every `%` command.

## In the native window

The native window (`python -m chisurf --emtk-shell`, opt-in while it replaces
the Qt window) has the same console as a **Console** dock beside **Log**, with
the same keys: Enter runs or continues a block, Shift+Enter adds a line, Up and
Down walk the history (filtered by what you had typed), `Ctrl+R` searches it,
Tab completes and `(` or Shift+Tab shows the call signature, `obj?` opens the
help pane under the transcript, `Ctrl+K` / `Ctrl+U` / `Ctrl+Y` cut and paste
the line, `Ctrl+L` clears. While the console has the keys, `Ctrl+R` is the
history search, not **Reinitialize**.

Two differences:

* The input is its own box under the transcript instead of an inline prompt.
* The session's fits and datasets are reached through **`api`** — the session's
  `ChiSurfAPI`, on a connection of the console's own — rather than `cs.fits`:

  ```python
  api.list_fits()
  api.set_parameter_value("N", 2.0, fit_uid=api.list_fits()[0]["uid"])
  ```

  A command that changes the science is one **Undo** step, named after the
  command.
* HTML displays as its text form, and `input()` raises `EOFError`.

Plots and images appear in the transcript as in the Qt window (see *Plotting* above),
with the same right-click **Copy image** / **Save image as…**.

**Macro ▸ Record** and **Macro ▸ Run Macro…** record and replay as above; the
macro is saved through the native file dialog. Dead keys, accented letters and
an input method (Japanese, Chinese, Korean) type as in any other field: the
text being composed is shown underlined at the cursor until it is committed.

## Headless

Everything above works without a GUI. The interpreter is a separate, Qt-free
package, so a script, the `csc` CLI or the ZMQ server reach the same API through
`chisurf.core.api.ChiSurfAPI`. See
[Macros, CLI & scripting](../reference/settings.md) for the settings that apply.

## Settings

The console reads `gui.console_init` (run at startup), `gui.console_style` (the
colour theme) and the optional `gui.console` block — scrollback cap, output
limit, completion style, paging. All of them are documented in
[Settings](../reference/settings.md).

## See also

- Tool: the **Code Editor** (`chisurf/plugins/core/code_editor/`).
