---
type: Plugin Reference
title: Tetris
description: Spectral Tetris with line clearing, score tracking, pause and restart.
resource: chisurf/plugins/misc/games/tetris/
tags: [reference, plugins, tetris, tools, games]
anchor: plugin-tetris
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tetris)=
# Tetris

Spectral Tetris with line clearing, score tracking, pause and restart.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tetris` |
| Menu path | Tools → Games → **Tetris** |
| Categories | Tools, Games |
| Version | 2.0.0 |
| Surfaces | cli, emtk, services |
| State namespace | `tetris_game` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/tetris/`
- Manifest: {src}`chisurf/plugins/misc/games/tetris/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/tetris/app.view.json`
