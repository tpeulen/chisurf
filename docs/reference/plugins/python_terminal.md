---
type: Plugin Reference
title: Python Terminal
description: 'ChiSurf''s built-in Python console as a terminal pane: tmux-style tabs, splits and floating windows around the console engine.'
resource: chisurf/plugins/core/python_terminal/
tags: [reference, plugins, python-terminal, tools, system]
anchor: plugin-python_terminal
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-python_terminal)=
# Python Terminal

ChiSurf's built-in Python console as a terminal pane: tmux-style tabs, splits and floating windows around the console engine.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `python_terminal` |
| Menu path | Tools → System → **Python Terminal** |
| Categories | Tools, System |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Terminal and Python console: shells and Python inside the session](/concepts/terminal.md)
- **Workflow** — [Terminal panes: shells and Python side by side](/guides/110_terminal.md)

## Source

- Plugin package: `chisurf/plugins/core/python_terminal/`
- Manifest: {src}`chisurf/plugins/core/python_terminal/manifest.json`
