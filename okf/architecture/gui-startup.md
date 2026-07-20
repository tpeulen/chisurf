---
type: Architecture
title: GUI Startup
description: The staged, JSON-declared GUI startup path and the laziness invariants that keep it fast.
resource: chisurf/startup/
tags: [startup, gui, performance, plugins]
timestamp: '2026-07-20T00:00:00Z'
---

# Staged startup

GUI startup is declarative. `AppStartupServiceManager`
(`chisurf/startup/services.py`) loads service specs from JSON files in
`chisurf/startup/services.d/` and runs them in dependency order, grouped by
`surface` (`gui`) and `phase`. The entrypoints live in
`chisurf/startup/gui_services.py`.

Two phases matter:

* **`splash`** — the critical path behind the splash screen, ending with a
  usable main window (`20_gui_splash.json`).
* **`post_show`** — work deferred until after the window is up
  (`30_gui_post_show.json`), including `deferred_gui_imports` and plugin
  population.

`_start_service` times every stage. Stages slower than `_SLOW_STAGE_SECONDS`
log at INFO; the full map is available as `AppStartupServiceManager.timings`.
That timing is the measurement tool for any startup regression — read it before
optimizing anything here.

# Laziness invariants

Startup cost is dominated by work that is *discarded*, not by work that is
inherently needed. Four invariants keep it that way; breaking any of them
silently costs seconds.

**Aggregator packages do not import their sub-packages eagerly.**
`chisurf/core/fio/__init__.py` and `chisurf/core/fluorescence/__init__.py`
expose sub-modules through a PEP 562 module `__getattr__`. Importing a small
reader (e.g. `chisurf.core.fio.ascii`) must not drag in the whole
fluorescence/pandas/scipy stack behind the package `__init__`.

**Plugin discovery is cached.** `chisurf.plugins.iter_plugins()` memoizes a
full-tree walk that reads and parses every plugin `__init__.py` and
`manifest.json`. Startup calls it from several places (main window, ribbon
categories). Anything that installs, renames or removes a plugin must call
`invalidate_plugin_cache()`.

**Menu construction does not import plugin code.** Names, descriptions and
icons all come from `manifest.json` and on-disk icon files. `icon_utils.
create_plugin_icon_with_fallback` accepts a *callable* module provider so the
import happens only for the few plugins whose icon comes from a module
attribute. Importing plugins to build a menu is what made the ribbon slow, and
plugin modules have import-time GUI side effects that make it fragile besides.

**Reader controllers are built on demand.** `ExperimentReader.controller`
(`chisurf/core/experiments/core/reader.py`) is a property backed by a factory
registered via `set_controller_factory`. The GUI configures many experiments
with several readers each but shows only the selected one, so eager
construction built roughly eighteen widgets to display one.

# Stylesheet

The application stylesheet is applied once. `_apply_stylesheet`
(`chisurf/gui/__init__.py`) early-returns when the sheet is unchanged, because
re-applying an identical sheet makes Qt rebuild `QStyleSheetStyle` and
re-polish the entire widget tree for no visual change.
