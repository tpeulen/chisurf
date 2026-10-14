---
type: Plugin Reference
title: Pong
description: Classic Pong game with CPU opponent, score tracking, and particle effects; contained in the Games hub.
resource: chisurf/plugins/misc/games/pong/
tags: [reference, plugins, pong, tools, miscellaneous, games]
anchor: plugin-pong
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-pong)=
# Pong

Classic Pong game with CPU opponent, score tracking, and particle effects; contained in the Games hub.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `pong` |
| Menu path | not in the menus (opened from a hub or another tool); display name Tools → Miscellaneous → Games → **Pong** |
| Categories | Tools, Miscellaneous, Games |
| Version | 2.0.0 |
| Surfaces | cli, emtk, services |
| State namespace | `pong_game` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/pong/`
- Manifest: {src}`chisurf/plugins/misc/games/pong/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/pong/app.view.json`
