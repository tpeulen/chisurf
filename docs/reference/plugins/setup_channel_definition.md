---
type: Plugin Reference
title: Channel Definition
description: Detector Channel and PIE-window definition wizard
resource: chisurf/plugins/core/setup_channel_definition/
tags: [reference, plugins, setup-channel-definition, setup]
anchor: plugin-setup_channel_definition
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-setup_channel_definition)=
# Channel Definition

Detector Channel and PIE-window definition wizard

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `setup_channel_definition` |
| Menu path | not in the menus (opened from a hub or another tool); display name Setup → **Channel Definition** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Detector setups: routing, windows, timing and calibration](/concepts/detector_setup.md)
- **Workflow** — [Detector setup: channels, PIE windows, timing and LUTs](/guides/87_channel_definition.md), [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/core/setup_channel_definition/`
- Manifest: {src}`chisurf/plugins/core/setup_channel_definition/manifest.json`
- UI spec: {src}`chisurf/plugins/core/setup_channel_definition/gui/app.view.json`
