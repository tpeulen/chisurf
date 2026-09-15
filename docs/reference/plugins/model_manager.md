---
type: Plugin Reference
title: Models
description: Model Manager for ChiSurf
resource: chisurf/plugins/core/model_manager/
tags: [reference, plugins, model-manager, setup]
anchor: plugin-model_manager
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-model_manager)=
# Models

Model Manager for ChiSurf

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `model_manager` |
| Menu path | Setup → **Models** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |

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

## Source

- Plugin package: `chisurf/plugins/core/model_manager/`
- Manifest: {src}`chisurf/plugins/core/model_manager/manifest.json`
- UI spec: {src}`chisurf/plugins/core/model_manager/gui/models.view.json`
