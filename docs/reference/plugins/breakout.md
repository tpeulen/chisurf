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
| Menu path | Tools → Miscellaneous → Games → **Breakout** |
| Categories | Tools, Miscellaneous, Games |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `breakout_game` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/breakout/`
- Manifest: {src}`chisurf/plugins/misc/games/breakout/manifest.json`
