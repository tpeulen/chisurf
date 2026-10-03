---
type: Plugin Reference
title: Plugin-Check
description: Tests all ChiSurf plugins for startup errors and reports successes, failures, and skipped checks.
resource: chisurf/plugins/core/plugin_check/
tags: [reference, plugins, plugin-check, tools, miscellaneous]
anchor: plugin-plugin_check
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-plugin_check)=
# Plugin-Check

Tests all ChiSurf plugins for startup errors and reports successes, failures, and skipped checks.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `plugin_check` |
| Menu path | Tools → Miscellaneous → **Plugin-Check** |
| Categories | Tools, Miscellaneous |
| Version | 2.1.0 |
| Surfaces | emtk, gui |
| State namespace | `plugin_check` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Native window (emtk)

The default window is drawn with emtk (`gui/app.py`; the form comes from `gui/plugin_check_emtk.view.json`).

| Area | Controls |
| --- | --- |
| Actions | **Test all plugins**, **Test safe plugins** (the first ten, short timeout), **Stop**, **Refresh**, **Clear blacklist**, **Help**, **Guide** |
| Options | *Delay between plugins* (0 to 5 s, step 0.1), *Skip blacklisted* |
| Progress | bar and status line |
| Table | *Plugin*, *Status*, *Source*, *Depends on*, *Error*; sort, filter, column picker |
| Details | module, version, source, status, requires, optional, problems, description, entry points, the whole startup error (selectable) |

## Theory and workflow

- **Guide** — [Checking that every plugin starts](/guides/96_plugin_check.md)

## Source

- Plugin package: `chisurf/plugins/core/plugin_check/`
- Manifest: {src}`chisurf/plugins/core/plugin_check/manifest.json`
