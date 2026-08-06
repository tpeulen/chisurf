---
type: Plugin Reference
title: Games
description: 'A collection of built-in games: Number Quest, Minesweeper, Tetris, Pong, and Breakout.'
resource: chisurf/plugins/misc/games/
tags: [reference, plugins, games, tools, miscellaneous]
anchor: plugin-games
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-games)=
# Games

A collection of built-in games: Number Quest, Minesweeper, Tetris, Pong, and Breakout.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `games` |
| Menu path | Tools → Miscellaneous → **Games** |
| Categories | Tools, Miscellaneous |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/`
- Manifest: {src}`chisurf/plugins/misc/games/manifest.json`
