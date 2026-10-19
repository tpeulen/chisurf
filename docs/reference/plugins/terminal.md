---
type: Plugin Reference
title: Terminal
description: 'Terminal panes like tmux: tabs, splits and floating windows of real PTY sessions.'
resource: chisurf/plugins/core/terminal/
tags: [reference, plugins, terminal, tools, system]
anchor: plugin-terminal
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-terminal)=
# Terminal

Terminal panes like tmux: tabs, splits and floating windows of real PTY sessions.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `terminal` |
| Menu path | Tools → System → **Terminal** |
| Categories | Tools, System |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Terminal and Python console: shells and Python inside the session](/concepts/terminal.md)
- **Workflow** — [Terminal panes: shells and Python side by side](/guides/110_terminal.md), [Driving ChiSurf from its console](/guides/59_console.md)

## Source

- Plugin package: `chisurf/plugins/core/terminal/`
- Manifest: {src}`chisurf/plugins/core/terminal/manifest.json`
