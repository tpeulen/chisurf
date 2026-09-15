---
type: Plugin Reference
title: Code Editor
description: Shared multi-document code/text editor with project navigation, symbols, diagnostics, and optional Python LSP integration.
resource: chisurf/plugins/core/code_editor/
tags: [reference, plugins, code-editor, tools, miscellaneous]
anchor: plugin-code_editor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-code_editor)=
# Code Editor

Shared multi-document code/text editor with project navigation, symbols, diagnostics, and optional Python LSP integration.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `code_editor` |
| Menu path | Tools → Miscellaneous → **Code Editor** |
| Categories | Tools, Miscellaneous |
| Version | 2.1.0 |
| Surfaces | gui, services |
| State namespace | `code_editor` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `editor.document.list` | no | List open editor documents. |
| `editor.document.get` | no | Get an open editor document. |
| `editor.document.set` | no | Replace an open editor document. |
| `editor.document.apply_edits` | no | Apply text edits to an open editor document. |
| `editor.document.ruff_check` | no | Run Ruff on an open editor document. |
| `editor.document.ruff_fix` | no | Run Ruff fixes on an open editor document. |

## Theory and workflow

- **Workflow** — [Driving ChiSurf from its console](/guides/59_console.md), [Notebooks that run inside ChiSurf](/guides/64_notebooks.md)

## Source

- Plugin package: `chisurf/plugins/core/code_editor/`
- Manifest: {src}`chisurf/plugins/core/code_editor/manifest.json`
