---
type: Plugin Reference
title: Switch User
description: Switch the active MMFDB user for this ChiSurf session.
resource: chisurf/plugins/core/switch_user/
tags: [reference, plugins, switch-user, setup]
anchor: plugin-switch_user
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-switch_user)=
# Switch User

Switch the active MMFDB user for this ChiSurf session.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `switch_user` |
| Menu path | Setup → **Switch User** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `switch_user` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/switch_user/`
- Manifest: {src}`chisurf/plugins/core/switch_user/manifest.json`
