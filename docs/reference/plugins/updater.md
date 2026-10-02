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
| Surfaces | gui, emtk |

## Parameters

The native window is declared in `gui/updater.view.json` (version, status, startup switches, version list, Check for Updates, Update Now, Package Manager) and the package manager in `gui/packages.view.json` (installed packages, search and install, environments, channels, operation log). Every control carries a tooltip; the workflow is in [guide 90](../../guides/90_updater.md). The startup switches are stored as `plugins.updater.check_on_startup` and `plugins.updater.ignore_updates_on_startup` in the user's settings file.

## Source

- Plugin package: `chisurf/plugins/core/updater/`
- Manifest: {src}`chisurf/plugins/core/updater/manifest.json`
