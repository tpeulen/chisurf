---
type: Plugin Reference
title: FCS Definitions
description: Define which detector channels are correlated with which, per detector setup.
resource: chisurf/plugins/fcs/fcs_channel_preset/
tags: [reference, plugins, fcs-channel-preset, setup]
anchor: plugin-fcs_channel_preset
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_channel_preset)=
# FCS Definitions

Define which detector channels are correlated with which, per detector setup.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_channel_preset` |
| Menu path | not in the menus (opened from a hub or another tool); display name Setup → **FCS Definitions** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector setup | `current_setup` | choice |  | choices: `setup_names` | Detector setup whose logical channels are paired for correlation. Detector setups are managed in the channel-definition wizard. |
| Public | `is_public` | bool |  |  | When checked, this setup is visible to all users in the MMFDB. Only the owner can change this setting. |

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [FCS toolbox: from photon stream to a curve worth fitting](/guides/75_fcs_toolbox.md), [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_channel_preset/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_channel_preset/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_channel_preset/gui/fcs_channel_preset.view.json`
