# The ChiSurf console

A Python prompt inside the running application. Everything you can see in the
GUI you can also reach here — the loaded datasets, the open fits, the plots —
and anything you do here is real, immediately.

Type an expression and press Enter. The value is echoed under an `Out[n]:`
label; a statement produces nothing, exactly as Python does.

## What is already in scope

| Name | What it is |
| --- | --- |
| `cs` | the whole `chisurf` package — `cs.fits`, `cs.imported_datasets`, `cs.macros` |
| `gui` | the main window |
| `np`, `os` | numpy and os |
| `p` | pylab, from the startup snippet |
| `_`, `__`, `___` | the last three results |
| `In`, `Out` | everything typed, and every result |

So `cs.fits[0].chi2r` reads the reduced chi-square of the first fit, and
`cs.fits[0].model.parameters_all_dict` lists its parameters.

## Editing

Blocks work as they do in a terminal REPL. Typing `for i in range(3):` and
pressing Enter gives you a continuation line, already indented; a **blank line
ends the block** and runs it. `Shift+Enter` always adds a line, `Ctrl+Enter`
always runs.

* **Tab** completes — names, attributes, dictionary keys, file paths inside
  strings, and magic names. Completion looks at the *live* objects, so
  `fit.model.<Tab>` lists what that model actually has.
* **Shift+Tab** shows the signature of the call you are inside.
* **Up / Down** walk the history, filtered by what you have already typed.
* **Ctrl+R** searches the history.
* **Ctrl+C** interrupts a running command. **Ctrl+L** clears the screen.
* Pasting a snippet copied from a tutorial works — `>>>` and `In [1]:` prompts
  are stripped. Copying gives you back runnable code, without the prompts.

## Magics

Commands that are not Python, prefixed with `%`. `%lsmagic` lists them all and
`%quickref` is a one-page summary.

| | |
| --- | --- |
| `%run -i script.py` | run a file **in this namespace**, so its variables stay |
| `%time`, `%timeit`, `%prun` | time and profile |
| `%who`, `%whos` | what is defined |
| `%history` | what you have typed |
| `%matplotlib inline` \| `qt` | figures in the console, or in their own windows |
| `%edit thing` | open something's source in the ChiSurf editor |
| `!ls -l` | run a shell command; `files = !ls` captures the output |

## Asking what something is

`obj?` shows the type, signature and docstring; `obj??` adds the source. Both
open in a pane below the console rather than filling the transcript. Press
**Esc** or **q** to close it.

## Recording a macro

*Macro ▸ Record* starts collecting everything you run. Click it again to stop,
and it offers to save what you did as a `.py` file. Replay it with
`%run -i thatfile.py`.

## If output runs away

A command that prints without end cannot lock the window up: output is drawn in
batches, the scrollback is capped, and anything past the per-command limit is
dropped with a note saying how much. Raise `gui.console.max_output_chars` if you
need more.

## Further reading

* [Console and scripting settings](docs/reference/settings.md)
* [Driving ChiSurf from code](docs/guides/59_console.md)
