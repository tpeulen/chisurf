---
type: Plugin Reference
title: Breakout
description: Classic Breakout game with progressive difficulty, multiple brick types, mouse/keyboard control, and particle effects; contained in the Games hub.
resource: chisurf/plugins/misc/games/breakout/
tags: [reference, plugins, breakout, tools, miscellaneous, games]
anchor: plugin-breakout
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-breakout)=
# Breakout

Classic Breakout game with progressive difficulty, multiple brick types, mouse/keyboard control, and particle effects; contained in the Games hub.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `breakout` |
| Menu path | not in the menus (opened from a hub or another tool); display name Tools → Miscellaneous → Games → **Breakout** |
| Categories | Tools, Miscellaneous, Games |
| Version | 2.0.0 |
| Surfaces | cli, emtk, services |
| State namespace | `breakout_game` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Games and generated round data](/concepts/games.md)
- **Workflow** — [Games: a break between fits](/guides/95_games.md)

## Source

- Plugin package: `chisurf/plugins/misc/games/breakout/`
- Manifest: {src}`chisurf/plugins/misc/games/breakout/manifest.json`
- UI spec: {src}`chisurf/plugins/misc/games/breakout/app.view.json`
