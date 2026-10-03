---
type: Plugin Reference
title: Traj Tools
description: Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools.
resource: chisurf/plugins/traj/traj_tools/
tags: [reference, plugins, traj-tools, structure, tools]
anchor: plugin-traj_tools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_tools)=
# Traj Tools

Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_tools` |
| Menu path | Structure → Structure → **Traj Tools** |
| Categories | Structure, Tools |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `traj_tools` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Native window (emtk)

The default window is drawn with emtk (`app.py`, on the shared hub base of the calculator hub; the catalogue is `registry.py`).

| Area | Controls |
| --- | --- |
| List | the eight tools (*Align*, *Convert*, *Energy Calc*, *FRET*, *Join*, *Remove Clashed*, *Rot Translate*, *Save Topol*), tooltip with the description, arrow keys, **Guide**, **Help** |
| Header | the tool's name and description |
| Tool | the selected tool's own native window, built on first use and kept |
| Status line | `Active tool: X`, what became of a dropped file |

## Source

- Plugin package: `chisurf/plugins/traj/traj_tools/`
- Manifest: {src}`chisurf/plugins/traj/traj_tools/manifest.json`
