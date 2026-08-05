---
type: PRD
prd: "81"
title: "PRD-81: chinsole — one console seam, and the end of qtconsole"
description: ChiSurf had three hand-rolled consoles and a Jupyter kernel running inside the GUI process to provide a text box that runs Python. chinsole is the in-tree replacement — a Qt-free interpreter under a Qt widget — and the seam every console in the application goes through.
status: in-progress
phase: "cutover done; chimol and code-editor ports open"
resource: chisurf/gui/chinsole/
tags: [prd, gui, console, chinsole, dependencies, qtconsole, chimol, code-editor]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

1. **The parity bar, and how to re-derive it.** `pytest test/console/ -q` is the
   definition of "at least as good as qtconsole" — 71 tests, no `QApplication`
   involved. *Trap*: a console suite that only checks `execute("1+1")` passes on
   a badly broken engine. The load-bearing cases are the compound-statement rule
   in `check_complete` (without it, Enter after the first line of a `for` body
   *runs* the loop instead of continuing it) and the traceback frame trimming.
2. **`ipython` and `notebook<7` are still declared, and that is where the
   remaining 83 packages live.** Measured on the recipe's `run:` list: dropping
   `qtconsole` alone is **264 → 262**; dropping the whole Jupyter stack is
   **264 → 181**. Retiring qtconsole did *not* get the prize, because
   `notebook<7` pulls `ipykernel` and hence `ipython` back in regardless. The
   open question is the external notebook server (the `start_jupyter` service,
   the Notebooks ribbon tab, `~/notebooks`), which is a **user-visible feature
   removal** and was deliberately out of scope. `pygments` is now imported by
   nothing in the tree, so its declaration goes with that same change.
3. **chimol's `CommandDock` and the code editor's output panel are not yet
   ported.** The widget supports them today — `ConsoleRole.COMMAND` and
   `ConsoleRole.OUTPUT` exist and the `CommandDispatcher` protocol is defined —
   but `chisurf/plugins/chimol/chimol/app/command_dock.py` (453 lines) is still
   live and the editor still has its own `_Tee`. Two things to know before
   starting: chimol's completion tables exist **twice** (`command_dock.py:64-116`
   and `cli.py:63-155`) and have already drifted — `cli.py` is missing six
   `metaball_*` entries — so they must converge into one Qt-free
   `chimol/cmd/completion.py` first; and `command_dock.py`'s
   `_resolve_history_path` carries a legacy fallback
   (`molview_cmd_history.txt` → `chimol_cmd_history.txt`) which must move with
   it or users silently lose their command history.
4. **The code-editor port is gated on a defect.** `run_endpoint` is missing from
   `EDITOR_SETTINGS_KEYS` (`chisurf/plugins/core/code_editor/settings.py`), so
   the endpoint dropdown is inert and the "IPython" path *has never actually
   run*. Fix that first or the port cannot be verified. While there: the panel's
   `_exec_on_main_thread` only emits captured output from its `finally` block, so
   a long script shows nothing until it finishes — routing it through an
   `OUTPUT`-role console fixes that by construction.
5. **Do not rename `dockWidget_console`.** The saved
   `QSettings("ChiSurf","MainWindow")` layout keys off the object name, and
   `_LAYOUT_VERSION` does not cover a rename — every existing user would lose the
   console from their layout.
6. **Tried and rejected: migrating `console_init`.** The obvious plan was to
   tolerate the legacy IPython spellings and rewrite the setting. It is
   unnecessary and was dropped: `get_chisurf_settings` merges packaged defaults
   *underneath* the user's file and never overwrites it, so those lines are
   permanent on every install — implementing them is the only thing that
   actually works. All four lines of the shipped `console_init` now run with no
   stderr.
7. **Still to do:** `%debug` is wired but unexercised; the pager
   (`gui.console.paging`) is a setting with no widget behind it yet, so `obj?`
   output goes to the scrollback; and `Macro ▸ Record` still cannot be stopped
   (see [known issues](/references/known-issues.md)).

# Why

The in-GUI console was `QIPythonWidget`, a 250-line subclass of qtconsole's
`RichJupyterWidget` driving an in-process Jupyter kernel. To provide a text box
that runs Python, ChiSurf installed qtconsole, IPython, ipykernel,
jupyter_client, jupyter_core, traitlets, pyzmq, tornado, debugpy, jedi, parso,
prompt-toolkit and stack_data — and inherited their breakage, including a
qtconsole/ipykernel-7 incompatibility open upstream since 2024-10-15.

Two smaller consoles had been hand-rolled beside it anyway — chimol's
`CommandDock` and the code editor's output panel — so the application had three
implementations of the same idea and none of them shared a line.

A survey of the alternatives found nothing that meets ChiSurf's "PyQt and qtpy
only" constraint: `pyqtconsole` is the only real lightweight option (MIT, ~2000
lines) but is a new dependency with a bus factor of ~1 and has no rich output,
no magics and no calltips; everything else is a wrapper *around* qtconsole
(napari-console, silx), an IDE-internal widget (spyder, pyzo, eric), or GPL and
stale (QScintilla, no release since 2023-06).

# Shape

```
chisurf/core/console/     the interpreter        imports no Qt (AST-enforced)
chisurf/gui/chinsole/     the widget             Qt
chisurf/gui/syntax.py     one highlighter        shared with both editors
```

Splitting the interpreter out is what makes the whole of execution testable
without a `QApplication`, which the Jupyter-kernel design could never be. The
Qt seam is five callbacks; pass none and the shell is a working head-less REPL.

`ConsoleRole` — `INTERACTIVE`, `COMMAND`, `OUTPUT` — covers all three of
ChiSurf's consoles, because where input lives was their only structural
difference.

# Decisions

* **Rich output is in scope.** matplotlib figures render inline, via a `Gcf`
  sweep in a post-execute hook — the mechanism `ipykernel.pylab.backend_inline`
  uses, minus ipykernel.
* **The cutover is a shim.** `chisurf/gui/widgets/ipython.py` became 60 lines
  (`QIPythonWidget` subclasses `Chinsole`), so no call site changed on the day
  the dependency was dropped.
* **Contrast is measured, not eyeballed.** `test/console/test_theme_contrast.py`
  holds every theme colour to 4.5:1. Writing it found the continuation prompt at
  2.42:1 in all three themes and the dark theme printing the exception *message*
  at 3.24:1.

# Definition of done

- [x] Qt-free interpreter with magics, completion, introspection and history
- [x] Widget with prompt protection, keymap, ANSI, inline images, bounded output
- [x] Shipped `console_init` runs verbatim, no settings migration
- [x] `qtconsole` retired from every manifest and banned by the guardrail
- [x] Two duplicate syntax highlighters converged into one
- [ ] chimol's `CommandDock` ported onto `ConsoleRole.COMMAND`
- [ ] Code editor's output panel ported onto `ConsoleRole.OUTPUT`
- [ ] `Macro ▸ Record` made stoppable
- [ ] Pager widget behind `gui.console.paging`
- [ ] User guide page

See also: [macros, CLI & scripting](/subsystems/macros-cli.md),
[known issues](/references/known-issues.md).
