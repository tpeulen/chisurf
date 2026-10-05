---
type: Guide
title: Checking that every plugin starts (Plugin Check)
description: What a plugin startup check proves, how to sweep all plugins or a safe subset, how to read the table and a failure's traceback, and the same check from the command line and from Python.
tags: [guides, plugins, tools, plugin-check]
---

# Checking that every plugin starts (Plugin Check)

**What you get:** a table of every ChiSurf plugin with the result of a startup check, and for a failure the whole
error and traceback. ChiSurf has well over a hundred plugins, most of them with their own window; a change in a shared
module can break any of them without anyone opening it. Plugin Check opens each one for you, in a separate process, and
tells you which do not start.

## What a check proves

A check builds the plugin's native (emtk) window, draws it at two window sizes (1200 × 800 and 800 × 600), and closes it.
The child process refuses any Qt import, so a native window that quietly depends on Qt fails. It does **not** run the
plugin's analysis: a pass means *the window opens*, not that the science behind it is right. The tests of each plugin
(and the parity reports under `okf/plugins/emtk-ports/`) are what establish that.

Every check runs in its own process on throw-away settings and a throw-away home folder, so a plugin that writes a
settings file or a log while starting cannot touch yours, and a hung or crashing plugin cannot take the sweep down: it
is terminated after 30 seconds (5 in a safe sweep) and reported as a failure.

## 1. Open the tool

Plugin Check is under **File → Setup → Settings → Plugin Check**. The window lists every discovered plugin, the ones that
ship with ChiSurf and the ones in your own plugin directory, with every row *pending* until a sweep reaches it.

```{figure} figures/plugin_check.png
:name: fig-plugin-check
:width: 100%

Plugin Check after a **Test safe plugins** sweep on the real plugin list. The left window holds the sweep buttons, the
two options, the progress bar and the table; the right window the selected plugin. Rows a sweep has not reached stay
*pending* and dimmed.
```

## 2. Run a sweep

1. **Test safe plugins** checks only the first ten plugins, with a short timeout. It is a quick way to see what a sweep
   looks like and whether the machine is in a good state.
2. **Test all plugins** checks every plugin, one at a time. It takes minutes. The bar and the status line count the
   plugins; the **Status** column fills in as each result arrives, and the window stays responsive.
3. **Stop** ends the sweep and terminates the plugin that is being checked right now; the status line says *Cancelled*.

The sweep buttons and **Refresh** are greyed while a sweep runs, **Stop** while none does.

Two options shape a sweep. **Delay between plugins** (0 to 5 s) pauses between two checks so a slow machine is not
overloaded. **Skip blacklisted** leaves out plugins that failed five checks in a row, so a broken plugin does not slow
every sweep; they show as *skipped*. **Clear blacklist** takes them off the list again.

## 3. Read the table

| Column | Means |
| --- | --- |
| Plugin | The plugin's menu path. |
| Status | *pass*, *fail*, *skipped* (blacklisted), *Qt only* (no native window yet), *no GUI*, or *pending*. |
| Source | *built-in*, or *user* for a plugin in your own plugin directory. |
| Depends on | Plugins that must load first; optional dependencies are counted, `(+3 optional)`. |
| Error | The first line of the startup error. |

Click a header to sort, again to reverse. Type in the **filter** box to keep the rows that contain the text in any
column: `fcs` finds every correlation tool, `fail` the failures, `user` your own plugins. A right click on the header
chooses the columns.

## 4. Read a failure

Select a row. The right-hand window shows the plugin's module, version, source and status, what it requires and what it
may use, any **Problems** the dependency resolver found (a requirement that is missing or out of range), its description
and entry points, and, for a failed check, the whole **Startup error** with its traceback. The text can be selected with
the mouse and copied.

```{figure} figures/plugin_check_failure.png
:name: fig-plugin-check-failure
:width: 100%

A failed check selected: the row is highlighted, its first error line is in the **Error** column, and the details window
holds the full text.
```

A *timed out* failure in a safe sweep is often only the short timeout on a busy machine: run **Test all plugins**, or
check that one plugin alone from the command line (below), before concluding it is broken.

## From the command line and from Python

The check itself is one command per plugin; this is what the window runs for each row:

```bash
python -m chisurf.emtk.validation --factory chisurf.plugins.core.about.gui.app:make_app
```

It prints one JSON line with `"status": "pass"` or `"fail"` (with `error`, `error_type` and `traceback`) and exits 0 on
a pass. The factory is the plugin's `entrypoints.emtk` from its `manifest.json`. To sweep from a script:

```python
from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel

model = PluginCheckModel()          # discovers the plugins, no window
model.delay = 0
model.test_safe()                   # or test_all(); runs in a worker thread
while model.running:
    model.poll()
print(model.message, model.status_of("about"))
```

## See also

- [Plugin reference: Plugin-Check](../reference/plugins/plugin_check.md)
- [Plugin manager](../reference/plugins/plugin_manager.md): switch plugins off, read the dependency graph.
