---
type: Plugin Reference
title: Models
description: List the registered fitting models and switch models off so they leave the model drop-down.
resource: chisurf/plugins/core/model_manager/
tags: [reference, plugins, model-manager, setup]
anchor: plugin-model_manager
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-model_manager)=
# Models

List the registered fitting models and switch models off so they leave the model drop-down.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `model_manager` |
| Menu path | not in the menus (opened from a hub or another tool); display name Setup → **Models** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Registered models

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show disabled models | `show_disabled` | bool |  |  | Include switched-off models in the table. |

### Selected model

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Disabled | `selected_disabled` | bool |  |  | Keep this model out of the model drop-down. It is not removed; nothing else changes. |

## Theory and workflow

- **Theory** — [The application shell: settings, interface, account and help](/concepts/application_shell.md)
- **Workflow** — [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/core/model_manager/`
- Manifest: {src}`chisurf/plugins/core/model_manager/manifest.json`
- UI spec: {src}`chisurf/plugins/core/model_manager/gui/models.view.json`
- UI spec: {src}`chisurf/plugins/core/model_manager/gui/models_emtk.view.json`
