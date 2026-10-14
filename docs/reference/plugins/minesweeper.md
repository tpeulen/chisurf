---
type: Plugin Reference
title: Minesweeper
description: A Minesweeper game with selectable playfield size and mine count, contained in the Games hub.
resource: chisurf/plugins/misc/games/minesweeper/
tags: [reference, plugins, minesweeper, tools, miscellaneous, games]
anchor: plugin-minesweeper
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-minesweeper)=
# Minesweeper

A Minesweeper game with selectable playfield size and mine count, contained in the Games hub.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `minesweeper` |
| Menu path | not in the menus (opened from a hub or another tool); display name Tools → Miscellaneous → Games → **Minesweeper** |
| Categories | Tools, Miscellaneous, Games |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/minesweeper/`
- Manifest: {src}`chisurf/plugins/misc/games/minesweeper/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/minesweeper/gui/app.view.json`
