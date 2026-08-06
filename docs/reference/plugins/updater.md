---
type: Plugin Reference
title: Updates & Packages
description: Update checker/installer and conda package manager. Surfaced as panels inside the unified Settings dialog.
resource: chisurf/plugins/core/updater/
tags: [reference, plugins, updater, setup]
anchor: plugin-updater
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-updater)=
# Updates & Packages

Update checker/installer and conda package manager. Surfaced as panels inside the unified Settings dialog.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `updater` |
| Menu path | Setup → **Updates & Packages** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/updater/`
- Manifest: {src}`chisurf/plugins/core/updater/manifest.json`
