---
type: Plugin Reference
title: Number Quest
description: A small number-guessing game.
resource: chisurf/plugins/misc/games/number_quest/
tags: [reference, plugins, number-quest, tools, games]
anchor: plugin-number_quest
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-number_quest)=
# Number Quest

A small number-guessing game.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `number_quest` |
| Menu path | Tools → Games → **Number Quest** |
| Categories | Tools, Games |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/number_quest/`
- Manifest: {src}`chisurf/plugins/misc/games/number_quest/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/number_quest/app.view.json`
