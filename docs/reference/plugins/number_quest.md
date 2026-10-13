---
type: Plugin Reference
title: Number Quest
description: A small number-guessing game contained in the Games hub.
resource: chisurf/plugins/misc/games/number_quest/
tags: [reference, plugins, number-quest, tools, miscellaneous, games]
anchor: plugin-number_quest
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-number_quest)=
# Number Quest

A small number-guessing game contained in the Games hub.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `number_quest` |
| Menu path | Tools → Miscellaneous → Games → **Number Quest** |
| Categories | Tools, Miscellaneous, Games |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/number_quest/`
- Manifest: {src}`chisurf/plugins/misc/games/number_quest/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/number_quest/app.view.json`
