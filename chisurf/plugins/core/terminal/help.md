# Terminal

Panes like tmux: tabs, splits and floating windows. A pane is a real shell (`▮`, a pseudo-terminal
session) or ChiSurf's Python console (`🐍`). The **Console** dock of the main window is this tool on
the window's own console.

- **New** (Ctrl+T) opens a pane of the active pane's kind.
- **Python** opens a Python pane; **Terminal** (Python Terminal, Console dock) opens a shell pane.
- **Split ⇥** / **Split ⇣** divide the active pane side by side or stacked.
- **Close** (Ctrl+W) ends the active pane; Ctrl+Tab cycles panes. Drag a tab out to float it.

A shell pane needs a POSIX pseudo-terminal; on Windows only Python panes work. In a shell pane
Ctrl+C with a selection copies it, Ctrl+V pastes, the wheel scrolls back.

Both kinds run code **as you**: nothing is sandboxed.

## The Python pane

A Python prompt inside the running application: the objects at the prompt are the objects the
windows show. Type an expression and press Enter; the value comes back under `Out[n]:`.

| Name | What it is |
| --- | --- |
| `cs` | the `chisurf` package |
| `gui` | the main window |
| `api` | the session's `ChiSurfAPI` (fits, datasets, parameters) |
| `np`, `os` | numpy, os |
| `_`, `__`, `___` | the last three results |
| `In`, `Out` | every input, every result |

`api.list_fits(statistics=True)` lists the fits with their χ²ᵣ; a command that changes a fit is one
**Undo** step.

## Editing

- Enter runs a complete statement, or opens an indented continuation line (`for i in range(3):`);
  a **blank line** ends the block. Shift+Enter always adds a line.
- **Tab** completes against the live objects; **Shift+Tab** or `(` shows the call signature.
- **Up / Down** walk the history, filtered by what you typed; **Ctrl+R** searches it.
- Ctrl+K / Ctrl+U cut to the end / start of the line, Ctrl+Y puts it back, **Ctrl+L** clears.
- **Ctrl+C** without a selection interrupts the running cell (and drops the cells queued behind
  it); with no cell running it abandons the input. With a selection it copies.
- Pasted `>>>` and `In [1]:` prompts are stripped.

## Magics and help

`%lsmagic` lists the `%` commands, `%quickref` is a one-page summary. `%run -i script.py` runs a
file in this namespace; `%time`, `%timeit`, `%prun` time and profile; `%who`, `%whos`, `%history`;
`%edit thing` prints where its source is (`file:line`); `!ls` runs a shell command, `files = !ls`
captures it. `obj?` shows type, signature and docstring in a pane below the transcript, `obj??`
the source; **Esc** closes it.

## Plots and images

A matplotlib figure appears under the cell that drew it (`plt.show()` at once); anything with
`_repr_png_` / `_repr_svg_` shows as its picture; `display(array)` draws a numpy image.
Right-click an image for **Copy image** / **Save image as…**.

## Macros and long commands

**Macro ▸ Record** collects what runs in the main window's console; click again to save a `.cm.py`,
replayed with **Macro ▸ Run Macro…** or `%run -i`.

A cell runs beside the window, not in it: the window keeps drawing, `print` output appears as it
is written, and a strip over the input shows **Running…** with the elapsed time, how many cells
wait behind it and an **Interrupt** button. Enter while a cell runs queues the next one.
**Ctrl+C** or **Interrupt** stops the cell with `KeyboardInterrupt` at its next Python line; a cell
inside one long C call (`time.sleep(60)`, a large numpy operation) stops when that call returns.
`gui.…` calls are made by the window between two frames, so a cell can open tools and focus docks
safely; `api` talks to the session directly. The transcript keeps the last `gui.console.max_blocks`
lines.

## Further reading

- [Terminal and Python console](docs/concepts/terminal.md)
- [Terminal panes: shells and Python side by side](docs/guides/110_terminal.md)
- [Driving ChiSurf from its console](docs/guides/59_console.md)
- [Console settings](docs/reference/settings.md)
