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
| Menu path | Tools → Miscellaneous → Games → **Minesweeper** |
| Categories | Tools, Miscellaneous, Games |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/minesweeper/`
- Manifest: {src}`chisurf/plugins/misc/games/minesweeper/manifest.json`
