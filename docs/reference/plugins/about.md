---
type: Plugin Reference
title: About ChiSurf
description: 'ChiSurf About Plugin This plugin provides information about ChiSurf, including version, developer, and contact information. Features: - Display ChiSurf logo - Show version information - Display developer contact details'
resource: chisurf/plugins/core/about/
tags: [reference, plugins, about, help]
anchor: plugin-about
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-about)=
# About ChiSurf

ChiSurf About Plugin  This plugin provides information about ChiSurf, including version, developer, and contact information.  Features: - Display ChiSurf logo - Show version information - Display developer contact details

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `about` |
| Menu path | Help → **About ChiSurf** |
| Categories | Help |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/about/`
- Manifest: {src}`chisurf/plugins/core/about/manifest.json`
