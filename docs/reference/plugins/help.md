---
type: Plugin Reference
title: Documentation
description: Documentation browser and help resource viewer for ChiSurf.
resource: chisurf/plugins/core/help/
tags: [reference, plugins, help]
anchor: plugin-help
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-help)=
# Documentation

Documentation browser and help resource viewer for ChiSurf.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `help` |
| Menu path | Help → **Documentation** |
| Categories | Help |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `help` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `help.docs.list` | no | List all available documentation files with metadata. |
| `help.docs.read` | no | Read a documentation file and return its content. |
| `help.docs.save` | no | Save content to a documentation file. |
| `help.docs.search` | no | Search documentation files for matching text. |
| `help.docs.ask` | yes | Puts a question to ChiSurf's documentation and returns a grounded answer together with the pages it was taken from. Needs a language-model provider configured in Settings -> AI; the assistant can only browse, search and read documentation - it cannot load data, fit or run code. |
| `help.docs.contract` | no | Return the Help plugin workflow contract. |

## Source

- Plugin package: `chisurf/plugins/core/help/`
- Manifest: {src}`chisurf/plugins/core/help/manifest.json`
