---
type: Guide
title: 'Terminal panes: shells and Python side by side'
description: Open the Terminal or Python Terminal tool, add, split and close panes, and know which keys the panes keep for themselves.
tags: [guides, python, terminal]
---

# Terminal panes: shells and Python side by side

**Tools → System → Terminal** (`chisurf/plugins/core/terminal/`) or **Tools → System → Python Terminal**
(`chisurf/plugins/core/python_terminal/`). Theory: {doc}`../concepts/terminal`.

**What you need:** nothing. A shell pane needs a POSIX system (macOS, Linux); Python panes work everywhere.

```{figure} figures/110_terminal_panes.png
:name: fig-terminal-panes
:width: 100%

Terminal, split side by side: pane 1 (`▮`) is a shell that listed this plugin's package, pane 2 (`🐍`) a Python
pane that evaluated `cs.__name__` and `np.arange(5) ** 2`. The strip above holds the pane actions, *Guide* and
`?`.
```

## 1. Open it

Terminal starts with one shell pane, Python Terminal with one Python pane. The **Console** dock of the main
window (beside **Log**) is the same tool on the window's own console.

## 2. Add a pane

**New** (Ctrl+T, Cmd+T on a Mac) adds a pane of the active pane's kind as a tab. **Python** adds a Python pane;
in Python Terminal and the Console dock, **Terminal** adds a shell pane.

## 3. Split

**Split ⇥** puts a new pane beside the active one, **Split ⇣** under it. The new pane has the active pane's
kind. Drag a pane's tab out to float it as its own window, or onto another region to dock it there.

```{figure} figures/110_python_terminal.png
:name: fig-python-terminal
:width: 100%

Python Terminal after **Split ⇣**: two Python panes, each with its own input box, `In [n]` count and
namespace, both seeded with `cs`, `np` and `os` (`x` exists only in pane 1).
```

## 4. Close

**Close** (Ctrl+W) ends the active pane's session; the × on a tab does the same for that pane. Ctrl+Tab and
Ctrl+Shift+Tab cycle the panes. A shell pane whose process exited keeps its output until closed.

## Keys

| Key | Where | Does |
| --- | --- | --- |
| Ctrl+T / Ctrl+W / Ctrl+Tab | any pane | new pane / close / next pane (the app keeps these; a shell never sees them) |
| typing, arrows, Ctrl+letters | shell pane | sent to the child as a terminal sends them |
| wheel | shell pane | scrollback |
| drag, then Ctrl+C | shell pane | copies the selection (without one, Ctrl+C is ^C to the child) |
| Ctrl+V | shell pane | pastes the clipboard into the child |
| Enter, Shift+Enter, Tab, Up/Down, `obj?` | Python pane | as in the [console](59_console.md) |

## Headless

There is no headless terminal: a shell is a shell, and the Python engine is reachable without a window as
`chisurf.core.console.shell.Shell`, or through `ChiSurfAPI` from a script or `csc`. The tool alone runs with
`python -m chisurf.emtk --plugin terminal` (or `--plugin python_terminal`).

`CHISURF_TERMINAL_SHELL` replaces the shell a shell pane runs, e.g.
`CHISURF_TERMINAL_SHELL="/bin/bash --norc --noprofile -i"` (the figures above were made with it).

Both pane kinds run with your own rights; see the
[security note](../concepts/terminal.md#security).
