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
| Menu path | Tools → Miscellaneous → Games → **Pong** |
| Categories | Tools, Miscellaneous, Games |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `pong_game` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/pong/`
- Manifest: {src}`chisurf/plugins/misc/games/pong/manifest.json`
