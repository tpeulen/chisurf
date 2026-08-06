---
type: Plugin Reference
title: User Editor
description: User editor plugin for Chisurf to manage users registered in the MMFDB.
resource: chisurf/plugins/core/user_editor/
tags: [reference, plugins, user-editor, setup]
anchor: plugin-user_editor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-user_editor)=
# User Editor

User editor plugin for Chisurf to manage users registered in the MMFDB.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `user_editor` |
| Menu path | Setup → **User Editor** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `user_editor` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/user_editor/`
- Manifest: {src}`chisurf/plugins/core/user_editor/manifest.json`
