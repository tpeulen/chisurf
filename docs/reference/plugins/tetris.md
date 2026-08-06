(plugin-tetris)=
# Tetris

Classic Tetris game with line clearing, score tracking, and next-piece preview; contained in the Games hub.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tetris` |
| Menu path | Tools → Miscellaneous → Games → **Tetris** |
| Categories | Tools, Miscellaneous, Games |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `tetris_game` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/misc/games/tetris/`
- Manifest: {src}`chisurf/plugins/misc/games/tetris/manifest.json`
