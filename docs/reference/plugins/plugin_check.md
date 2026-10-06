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

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Delay between plugins | `delay` | float |  | 0.0 … 5.0 (step 0.1) | Pause between two plugin checks so the machine is not overloaded; Stop stays responsive during the pause. |
| Skip blacklisted | `skip_blacklisted` | bool |  |  | Do not check plugins that failed five times in a row; they show as skipped. |

## Source

- Plugin package: `chisurf/plugins/core/plugin_check/`
- Manifest: {src}`chisurf/plugins/core/plugin_check/manifest.json`
- UI spec: {src}`chisurf/plugins/core/plugin_check/gui/plugin_check_emtk.view.json`
