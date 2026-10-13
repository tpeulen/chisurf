---
type: Plugin Reference
title: Games
description: 'A collection of built-in games: Number Quest, Minesweeper, Tetris, Pong, and Breakout.'
resource: chisurf/plugins/misc/games/
tags: [reference, plugins, games, tools, system]
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
| Menu path | Tools → System → **Games** |
| Categories | Tools, System |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/`
- Manifest: {src}`chisurf/plugins/misc/games/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/breakout/app.view.json`
- UI spec: {src}`chisurf/plugins/misc/games/game_header.view.json`
- UI spec: {src}`chisurf/plugins/misc/games/gui/app.view.json`
- UI spec: {src}`chisurf/plugins/misc/games/minesweeper/gui/app.view.json`
- UI spec: {src}`chisurf/plugins/misc/games/number_quest/app.view.json`
- UI spec: {src}`chisurf/plugins/misc/games/pong/app.view.json`
- UI spec: {src}`chisurf/plugins/misc/games/tetris/app.view.json`
