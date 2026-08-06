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

That is the kind of thing the console is for. There is no dialog that compares
chi-square across every open fit, and there does not need to be.

## Turning what you did into a script

Two ways round, and they meet in the middle.

**Record what you click.** *Macro ▸ Record* starts collecting; click it again to
stop and it offers to save a `.py` file. Everything the GUI does goes through
the same action layer the console does, so a recording is real, runnable Python.

**Run a script into this session:**

```ipython
%run -i analysis.py
```

The `-i` is not optional in spirit: it runs the file *in the console's
namespace*, so anything the script defines is still there afterwards for you to
poke at. Without it the script gets a clean namespace and leaves nothing behind.

The [script editor](../reference/settings.md) has a **Run** button that does the
same thing — its *In ChiSurf* endpoint runs in this process, with `cs` in scope,
and streams output to its panel as it goes.

## Plotting

`%matplotlib inline` (the shipped default) draws figures directly in the
console:

```python
import matplotlib.pyplot as plt
plt.plot(fit.data.x, fit.data.y)
```

`%matplotlib qt` switches to figures in their own windows, which is what you
want once you need to zoom.

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
