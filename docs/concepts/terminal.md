---
type: Concept
title: 'Terminal and Python console: shells and Python inside the session'
description: What the Terminal and Python Terminal tools are, how their panes, splits and floating windows work, what the Python console has in scope, and why both run code with the user's own rights.
tags: [concepts, terminal, console, scripting]
anchor: concept-terminal
---

(concept-terminal)=
# Terminal and Python console: shells and Python inside the session

Two tools share one app (`chisurf/plugins/core/terminal/app.py`):

- **Terminal** (**Tools → System → Terminal**, `chisurf/plugins/core/terminal/`) opens a shell pane first.
- **Python Terminal** (**Tools → System → Python Terminal**, `chisurf/plugins/core/python_terminal/`) opens a
  Python pane first.

The **Console** dock of the main window is the same app, opened on the window's own Python console. Neither
tool measures anything; they are where a command is typed.

## Two kinds of pane

| Pane | What runs | Needs |
| --- | --- | --- |
| shell `▮` | the user's shell (`$SHELL -i`, or `CHISURF_TERMINAL_SHELL`) as a child process on a pseudo-terminal | a POSIX `pty` (not Windows) |
| Python `🐍` | ChiSurf's console engine (`chisurf/core/console/`), in the ChiSurf process | nothing |

A **shell pane** is a real terminal: the child sees `isatty()`, job control and a window size, and gets
`TERM=xterm-256color`. The pane emulates the subset of a VT100/xterm that shells and full-screen programs use
(cursor addressing, erase, insert/delete, scroll regions, the alternate screen, 256 and true colour); OSC titles
and charset shifts are dropped. A resize of the pane resizes the grid and sends the child `SIGWINCH`. A pane
whose process exits keeps its output and says *process exited*.

A **Python pane** is the console of the main window: an input box under a transcript, `In [n]:` / `Out[n]:`,
blocks, history, completion against live objects, `obj?` help, `%` magics, inline plots. Its behaviour is
described in [Driving ChiSurf from its console](../guides/59_console.md). A cell runs on the console's worker thread: the
window keeps drawing, output streams in, a *Running…* strip with an *Interrupt* button shows while it runs, and
Ctrl+C raises `KeyboardInterrupt` in it. Calls on `gui` are marshalled to the window's thread.

## Panes, splits, windows

The panes are dock windows of the app's own dock manager, the tmux picture:

- **New** adds a pane of the active pane's kind as a tab next to it.
- **Split ⇥** / **Split ⇣** divide the active pane's region side by side or stacked; the new pane inherits the
  kind.
- A tab dragged out floats as its own window; dragged onto a region it docks there.
- **Close** ends the active pane's session (the child is killed, a Python pane saves its history) and prunes
  the empty region.

Panes are not saved with the project: closing the tool or the window ends every session.

## What a Python pane has in scope

| Name | What it is |
| --- | --- |
| `cs` | the `chisurf` package |
| `np`, `os` | numpy, os |
| `gui` | the main window (when one is running) |
| `api` | the session's `ChiSurfAPI`, on a connection of the console's own (once a session is up) |
| `_`, `__`, `___` | the last three results |
| `In`, `Out` | every input and every result |

Fits and datasets of the main window are reached through `api` (`api.list_fits()`), which goes through the
session server like every dock. `cs.fits` is the process-local legacy list and is empty in the main window.
`gui.console_init` (see [Settings](../reference/settings.md)) runs once when a console starts.

Every command is appended to the session log (`settings.session_file`); while **Macro ▸ Record** is on, the
main window's console also records it into a macro, replayed with `%run -i`.

## Security

Both panes run code **as the user**, with the user's files, network and credentials. A shell pane is your own
interactive shell; a Python pane runs in the ChiSurf process and can change or delete anything the
session holds. Nothing is sandboxed, and nothing typed is sent anywhere. Run only commands and scripts you
would run in a terminal of your own.

## See also

- Guide: [Terminal panes: shells and Python side by side](../guides/110_terminal.md).
- Guide: [Driving ChiSurf from its console](../guides/59_console.md).
- Concept: [Code Editor](code_editor.md) — for a script you keep.
