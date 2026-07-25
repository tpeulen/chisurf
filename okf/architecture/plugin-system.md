---
type: Architecture
title: Plugin System
description: Manifest-discovered plugins and the plugin infrastructure under chisurf/core/plugin/.
resource: chisurf/core/plugin/
tags: [plugins, manifest, extensibility]
timestamp: '2026-07-05T00:00:00Z'
---

# Discovery

Plugins live under `chisurf/plugins/` and are discovered via `manifest.json`
files; the plugin infrastructure lives in `chisurf/core/plugin/`. Migrated
plugins receive a `PluginContext` (API + client + main window) rather than
reaching for [runtime globals](/architecture/runtime-globals.md).

# Scale

The tree ships ~86 plugin manifests, grouped by domain — e.g. `burst/`
(smFRET burst analysis), `fcs/` (correlation), `fluorescence_decay/`
(TCSPC lifetime), `modelling/` (FRET/HydroPro/FPS), and `core/`
(infrastructure tools like `mmfdb_admin`, `setup`, `plugin_manager`,
`user_editor`).

A cookiecutter template for new plugins lives at
`chisurf/plugins/cookiecutter-chisurf-plugin/`.

# Discovery cost

`iter_plugins()` walks the whole tree and parses every plugin `__init__.py` and
`manifest.json`, so its result is memoized; mutating the plugin set requires
`invalidate_plugin_cache()`. Menus are built from manifest metadata and on-disk
icons **without importing plugin code** — see
[GUI Startup](/architecture/gui-startup.md) for why both matter.

# Command line

Plugin CLIs reach the `csc` command line through the **manifest**:
`entrypoints.cli` (`"alias=module:attr"`) is the authoritative declaration, read
by `chisurf/core/cli.py` in the same filesystem+AST scan that finds plugin names —
still without importing any plugin. The older module-level `cli_entrypoint`
assignment remains a fallback for plugins without a manifest, and when a plugin
carries both they must agree (a guardrail test enforces it).

Two consequences worth knowing: a manifest whose entry omits the `alias=` prefix
registers under the plugin id instead of being dropped, and a plugin's command is
imported only when it is actually invoked, so a broken plugin CLI cannot slow —
or break — `csc --help`.

# AutoForm

GUI plugins increasingly declare their UI as data — a `*.view.json` scheme
rendered by the AutoForm framework (see the [GUI subsystem](/subsystems/gui-autoform.md))
instead of hand-built Qt widgets.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
