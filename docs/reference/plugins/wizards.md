---
type: Plugin Reference
title: Wizards
description: Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view.
resource: chisurf/plugins/core/wizards/
tags: [reference, plugins, wizards, tools, calculators]
anchor: plugin-wizards
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-wizards)=
# Wizards

Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `wizards` |
| Menu path | Tools → Calculators → **Wizards** |
| Categories | Tools, Calculators |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `wizards` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [The application shell: settings, interface, account, help and hubs](/concepts/application_shell.md)
- **Workflow** — [Working in the shell: interface, account and the two hubs](/guides/105_application_shell.md)

## Source

- Plugin package: `chisurf/plugins/core/wizards/`
- Manifest: {src}`chisurf/plugins/core/wizards/manifest.json`
