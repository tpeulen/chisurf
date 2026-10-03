---
type: Plugin Reference
title: Wizards
description: Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view.
resource: chisurf/plugins/core/wizards/
tags: [reference, plugins, wizards, main, tools]
anchor: plugin-wizards
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-wizards)=
# Wizards

Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `wizards` |
| Menu path | Main → Tools → **Wizards** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `wizards` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Native window (emtk)

The default window is drawn with emtk (`gui/app.py`, on the shared hub base of the calculator hub; the catalogue is `core/registry.py`).

| Area | Controls |
| --- | --- |
| List | one entry per wizard (*Anisotropy*, *Batch analysis*), tooltip with its description, arrow keys, **Guide**, **Help** |
| Header | the wizard's name and one-line description; a load error is shown here |
| Page | the selected wizard's own native window, built on first use and kept |

## Source

- Plugin package: `chisurf/plugins/core/wizards/`
- Manifest: {src}`chisurf/plugins/core/wizards/manifest.json`
