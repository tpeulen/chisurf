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
| Surfaces | cli, gui, services |
| State namespace | `pong_game` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/pong/`
- Manifest: {src}`chisurf/plugins/misc/games/pong/manifest.json`
