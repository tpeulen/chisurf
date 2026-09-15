---
type: Plugin Reference
title: Screenshot
description: 'Screenshot A minimal plugin that captures a screenshot of the ChiSurf main window and copies it to the clipboard. Behavior: - It captures the current main window and copies the image to the clipboard. - It displays a temporary message box confirming the action.'
resource: chisurf/plugins/core/screenshot/
tags: [reference, plugins, screenshot, main, tools]
anchor: plugin-screenshot
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-screenshot)=
# Screenshot

Screenshot  A minimal plugin that captures a screenshot of the ChiSurf main window and copies it to the clipboard.  Behavior: - It captures the current main window and copies the image to the clipboard. - It displays a temporary message box confirming the action.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `screenshot` |
| Menu path | Main → Tools → **Screenshot** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/screenshot/`
- Manifest: {src}`chisurf/plugins/core/screenshot/manifest.json`
