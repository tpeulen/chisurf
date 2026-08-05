---
type: Subsystem
title: Macros, CLI & Scripting
description: How ChiSurf is driven from code — recordable macros, the `csc` Click CLI, and the in-tree chinsole console.
resource: chisurf/macros/
tags: [scripting, core, cli, console, chinsole]
timestamp: '2026-08-06T00:00:00Z'
---

# Scope

Three overlapping ways to drive ChiSurf without clicking the GUI:

| Surface | Entry | Code |
| --- | --- | --- |
| Macros | `import chisurf.macros` | `chisurf/macros/` |
| CLI | `csc <sub> …` | `chisurf/core/cli.py` |
| Console | in-GUI dock | `chisurf/gui/chinsole/` + `chisurf/core/console/` |

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

**The legacy spellings still work.** `QIPythonWidget` is a shim over `Chinsole`;
`pushVariables`, `set_default_style`, `execute_on_gui_thread` and
`log_on_gui_thread` are aliases. `chisurf.run(...)` still marshals to the GUI
thread through a queued signal.

**Macro recording**: `start_recording` / `stop_recording` accumulate executed
code, which `save_macro` / `run_file` write and replay — the manual counterpart
to history-based replay. Note `save_macro` and `stop_recording` currently have
**no caller**, so *Macro ▸ Record* starts a recording that cannot be stopped;
see [known issues](/references/known-issues.md).

**What existing installations keep.** ChiSurf merges packaged defaults
*underneath* a user's settings file and never overwrites it, so
`console_style: linux` and a `console_init` full of IPython spellings are
permanent on every install. Both keep working rather than being migrated:
`linux`/`lightbg`/`nocolor` are theme aliases, and `%matplotlib inline`,
`%config Completer.use_jedi = False` and `get_ipython().cache_size = 0` are each
implemented — the last as a real property, because accepting the assignment and
ignoring it would reinstate the memory growth that line exists to prevent.

# Scriptability & tests

Because the [core](/subsystems/core.md) is Qt-free, macros and `csc` run
headless against `ChiSurfAPI` in `local`, `hybrid`, or `server` mode.
[PRD-46](/prds/prd-46.md) promotes such scripts to first-class citizens of the
test pipeline.

See also: [overview](/overview.md), [data IO](/subsystems/data-io.md),
[compiled modules](/subsystems/compiled-modules.md).
