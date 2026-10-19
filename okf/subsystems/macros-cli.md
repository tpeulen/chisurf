---
type: Subsystem
title: Macros, CLI & Scripting
description: How ChiSurf is driven from code — recordable macros, the `csc` Click CLI, and the in-tree chinsole console.
resource: chisurf/macros/
tags: [scripting, core, cli, console, chinsole]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

1. **Measure:** console cells run on a worker (2026-10-19). `test/native_emtk/test_emtk_console_worker.py`
   drives the shell with keys: frames drawn while `time.sleep(2)` runs (max frame < 0.5 s), `print`
   ticks arriving one by one, `while True: pass` stopped by Ctrl+C in < 1 s, a queued second cell,
   the *Interrupt* button, `api.add_fit` and `gui.…` from a cell; the screenshot is
   `/private/tmp/chisurf-native-gpu/emtk_console_running.png`. Trap: a behaviour test asserting right
   after Enter needs `console.frame_budget = 60.0` (the console test fixtures set it) or
   `console.wait()`, because a first-cell import outlasts the 50 ms budget under a full suite. A
   pure-Python busy cell contends for the GIL: frames slow (the fps readout showed ~8 fps during a
   busy-loop screenshot) but keep coming.
2. **Open:** a cell inside one long C call (`time.sleep(60)`, one big numpy operation) is
   interrupted only when the call returns; the async exception lands at the next bytecode. An
   interruptible sleep would mean patching the cell's `time.sleep`; not done.
3. **Open:** `ConsoleSession` (`chisurf/plugins/core/terminal/console_session.py`, a grid-drawn Python
   engine no pane uses any more, only its own tests) still runs cells synchronously; delete it or
   route it through `ShellConsole`.
4. **Open:** `EmtkShellApp._draw_console` rewrites `console.control.boxes` into window coordinates
   after drawing (so tests can click them) while presses arrive in the control's own frame; in-console
   clicks (completion rows, pager ✕, *Interrupt*) missed. `ConsoleControl._to_boxes` now maps a press
   into the boxes' frame; the cleaner fix is to stop rewriting `control.boxes` and let tests click
   `item_rects` only (the plot tests read `control.boxes` / `image_boxes` in window coordinates).
5. **Open:** the Qt-era `gui.console.max_output_chars` / `flush_interval_ms` defaults in
   `chisurf/core/console/settings.py` are read by nothing in the emtk console (its output is
   coalesced per frame instead).
6. **Open:** i18n: the Terminal guide step, the help text and the console's new strings (*Running…*,
   *Interrupt*, *queued cell(s) dropped*) are not in the `.ts` catalogues yet (catalogue work is
   queued separately); the deleted console guide's strings are stale there.

# Scope

Three overlapping ways to drive ChiSurf without clicking the GUI:

| Surface | Entry | Code |
| --- | --- | --- |
| Macros | `import chisurf.macros` | `chisurf/macros/` |
| CLI | `csc <sub> …` | `chisurf/core/cli.py` |
| Console | Console dock = Terminal app (`chisurf/plugins/core/terminal/`) | `chisurf/emtk/console.py` + `chisurf/core/console/` |

All three ultimately go through the [API facade](/architecture/api-facade.md)
(`chisurf.core.api`, the stable surface for "GUI, macros, plugins, and the
console") and record into [history](/subsystems/history.md).

# Macros (`chisurf/macros/`)

Plain Python functions that perform domain operations; the package re-exports
`core_fit` and `core_data` with `*` and pulls in `model`, `model_parse`,
`plugin_check`.

| Module | Role |
| --- | --- |
| `core_data.py` | `add_dataset`, `group_datasets`, `remove_datasets`, `reinitialize_application`, reader resolution |
| `core_fit.py` | fit lifecycle, linking, project archive save/load, `export_action_catalog` |
| `model.py`, `model_parse.py` | model configuration / parsed-model control |
| `plugin_check.py` | `PluginTestRunner` — plugin self-test logic (UI-free) |

Macros call `record_action(...)` (`chisurf/macros/*._record_history`) so
scripted state changes land in the [action layer](/architecture/action-layer.md)
and history exactly like GUI clicks.

# CLI — `csc` (`chisurf/core/cli.py`)

A Click `Group` (`PluginCLI`) that lazily discovers and registers
plugin-provided subcommands on first invocation (no plugin import at load
time). Declared as the `csc` console script in `[project.scripts]`; a second
script `chimol-cli` targets the chimol app. Examples from the group docstring:
`csc lltf`, `csc burst-background`, `csc count-rate analyze`.
[PRD-30](/prds/prd-30.md) extends these into stdin/stdout Unix pipe stages.

# GUI entry points (`[project.gui-scripts]`)

`chisurf` (`chisurf.__main__:main`) plus ~20 standalone `csg_*` plugin GUIs
(e.g. `csg_kappa2distribution`, `csg_fret_dock`, `csg_ndxplorer`,
`csg_batch_analysis`) and `chisurf_update`. Each maps to a plugin `__main__:main`.
The headless [server](/architecture/server.md) runs via `python -m chisurf.server`.

# Console — chinsole (`chisurf/gui/chinsole/`, `chisurf/core/console/`)

The in-GUI console is ChiSurf's own, written to replace the `qtconsole`
dependency (retired 2026-08-06). It is split in two, and the split is the point:

| Package | Holds | Imports Qt |
| --- | --- | --- |
| `chisurf/core/console/` | the interpreter — input transformation, completeness detection, compilation, execution, output capture, tracebacks, magics, completion, introspection, history | **no** |
| `chisurf/gui/chinsole/` | the widget — view, prompts, themes, completion popup, calltips, inline images, output pump | yes |

An AST test enforces the Qt-free half, so the whole interpreter is testable
without a `QApplication` — which the qtconsole-based console never was, because
execution lived inside an in-process Jupyter kernel.

**One widget, three roles.** `ConsoleRole.INTERACTIVE` (main-window dock),
`COMMAND` (a one-line input under the output, for chimol) and `OUTPUT`
(read-only, for the code editor's panel). Where input lives was the only
structural difference between ChiSurf's three hand-rolled consoles.

**Command or Python is one rule, in `chisurf/core/console/dispatch.py`.** A
console that accepts both has to decide per line, and the rule is short but
every clause of it was paid for by a bug report — so it lives in the Qt-free
half and every prompt calls it. It was written out once per prompt until
2026-08-06 (the widget, chimol's ptpython binding, that REPL's `input()`
fallback) and the three had drifted into three different rules, two carrying
defects the third had already fixed.

The rule: a line that does not compile is a command; a line that compiles is
Python only when the name it would evaluate is actually bound. So `fetch 1f5n`
and `color red, all` are commands because they are syntax errors, `set` stays
the builtin, and `ray` / `zoom` / `orient` / `undo` are commands because they
are bound to nothing and evaluating them could only raise. Whether the
dispatcher *recognises* the word is deliberately not asked — it cannot change
an answer, and asking it splits the rule into two branches that then have to be
kept identical by hand.

`is_incomplete_python` is the companion a *line-at-a-time* prompt needs and the
widget does not: where Enter can continue a block, `for i in range(3):` must
reach the buffer rather than the command layer, or the body can never be typed.
The widget submits whole cells and never sees a partial block. Guarded by
`test/console/test_dispatch_rule.py`, which fails on any prompt that compiles
the line itself.

**The legacy spellings still work.** `QIPythonWidget` is a shim over `Chinsole`;
`pushVariables`, `set_default_style`, `execute_on_gui_thread` and
`log_on_gui_thread` are aliases. `chisurf.run(...)` still marshals to the GUI
thread through a queued signal.

**Macro recording**: `start_recording` / `stop_recording` accumulate executed
code, which `save_macro` / `run_file` write and replay — the manual counterpart
to history-based replay. *Macro ▸ Record* is a **toggle**: untoggling stops the
recording and offers to save it. It was a one-shot wired only to
`start_recording` until 2026-08-06, with nothing in the tree calling
`stop_recording` or `save_macro`, so the recording could never be written out.

**What existing installations keep.** ChiSurf merges packaged defaults
*underneath* a user's settings file and never overwrites it, so
`console_style: linux` and a `console_init` full of IPython spellings are
permanent on every install. `console_style` is no longer read (the emtk console reads
`gui.console` in `chisurf/emtk/console.py`; the key was struck from the shipped YAML
2026-10-19), and `console_init` keeps working rather than being migrated: `%matplotlib inline`,
`%config Completer.use_jedi = False` and `get_ipython().cache_size = 0` are each
implemented — the last as a real property, because accepting the assignment and
ignoring it would reinstate the memory growth that line exists to prevent.

**Inline plots and images (2026-10-11).** Both consoles show figures in the
transcript like a notebook, with no `%matplotlib` line: the engine selects its
own matplotlib backend at start-up (`chisurf/core/console/mpl_inline.py`,
`mpl_backend.py`; see [matplotlib retirement](/subsystems/matplotlib-retirement.md)),
`plt.show()` publishes at once, `_repr_png_`/`_repr_svg_` objects (emtk and
chiplot figures, PIL images) render, and `display(arr)` draws a numpy image
(`formatters.image_array_png`). The Qt view fits each image to the viewport
width (and height, never below 240 px) on every resize; the emtk console
(`chisurf/emtk/console.py`) lays an `InlineImage` out as blank transcript rows
and paints it over them, SVG rasterised by `emtk.svg`, with a right-click
*Copy image* (`emtk.clipboard.copy_image`) / *Save image as…*. Tests:
`test/console/test_inline_figures.py`,
`test/native_emtk/test_emtk_shell_console_plots.py`; screenshots under
`/private/tmp/chisurf-console-plots` and `/private/tmp/chisurf-native-gpu`.

**Console help lives with the Terminal app (2026-10-19).** The Console dock hosts the Terminal
app; its `?` / *Guide* are `chisurf/plugins/core/terminal/help.md` / `guide.json`, which carry the
console reference (scope, keys, magics, plots, macros). Docs: `docs/concepts/terminal.md`,
`docs/guides/110_terminal.md`, `docs/guides/59_console.md`; figures from
`docs/guides/screenshots/terminal_shot.py`.

**Cells run off the frame (2026-10-19).** The emtk console runs a cell on its worker thread, so the
window keeps drawing; a *Running…* strip (elapsed time, queued count, *Interrupt*) sits over the
input; Ctrl+C raises `KeyboardInterrupt` in the cell; a second cell queues. Window calls from a
cell go through `gui`'s `FrameProxy` to the frame thread; `api` is used directly (its ZMQ client
serialises calls with its own lock). How: one daemon worker per console; output, displays, `%clear` and the echo
reach the transcript through an outbox the frame drains in `poll()` (consecutive writes coalesce);
Ctrl+C uses `PyThreadState_SetAsyncExc`, armed only inside user code by the interpreter's
`run_guard` context manager (`chisurf/core/console/interpreter.py`; a context manager adds no frame
to user tracebacks, a wrapper did); interrupt drops the queued cells; window objects (types from
`emtk`, `chisurf.emtk`, `chisurf.gui`) are wrapped in `FrameProxy`; the submitting frame waits
`frame_budget` (50 ms) so a quick cell shows in the same frame. Open items: "Where to pick this up".

# Scriptability & tests

Because the [core](/subsystems/core.md) is Qt-free, macros and `csc` run
headless against `ChiSurfAPI` in `local`, `hybrid`, or `server` mode.
[PRD-46](/prds/prd-46.md) promotes such scripts to first-class citizens of the
test pipeline.

See also: [overview](/overview.md), [data IO](/subsystems/data-io.md),
[compiled modules](/subsystems/compiled-modules.md).
