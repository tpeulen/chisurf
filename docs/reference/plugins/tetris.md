---
type: Plugin Reference
title: Tetris
description: Spectral Tetris with line clearing, score tracking, pause and restart; contained in the Games hub.
resource: chisurf/plugins/misc/games/tetris/
tags: [reference, plugins, tetris, tools, miscellaneous, games]
anchor: plugin-tetris
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tetris)=
# Tetris

Spectral Tetris with line clearing, score tracking, pause and restart; contained in the Games hub.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tetris` |
| Menu path | Tools → Miscellaneous → Games → **Tetris** |
| Categories | Tools, Miscellaneous, Games |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `tetris_game` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/tetris/`
- Manifest: {src}`chisurf/plugins/misc/games/tetris/manifest.json`
