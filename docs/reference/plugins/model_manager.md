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

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/model_manager/`
- Manifest: {src}`chisurf/plugins/core/model_manager/manifest.json`
