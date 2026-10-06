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
| Surfaces | emtk, gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Installed Packages

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Filter | `installed_filter` | str |  |  | Show only the installed packages whose name contains this text (case-insensitive). |

### Search & Install

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Package | `search_query` | str |  |  | The package name to search for. Enter starts the search. |

### ChiSurf Package Manager

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Value | `dialog_input` | str |  |  | The text the question asks for. |

### Installed version

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Development | `development` | bool |  |  | ChiSurf currently has no stable release; updates check the development branch. The switch is on and cannot be changed. |

### Startup behavior

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Check for updates on startup | `check_on_startup` | bool |  |  | When enabled, ChiSurf will check for updates during startup. |
| Ignore updates (do not prompt on startup) | `ignore_updates_on_startup` | bool |  |  | If enabled, ChiSurf will not prompt about updates during startup. |

### Update

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Available versions | `selected_version` | choice |  | choices: `version_labels` | The versions the update server lists, newest first. Picking one shows the changes up to it. Empty until Check for Updates has found some. |

## Source

- Plugin package: `chisurf/plugins/core/updater/`
- Manifest: {src}`chisurf/plugins/core/updater/manifest.json`
- UI spec: {src}`chisurf/plugins/core/updater/gui/packages.view.json`
- UI spec: {src}`chisurf/plugins/core/updater/gui/updater.view.json`
