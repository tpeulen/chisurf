---
type: Plugin Reference
title: Project data
description: 'The data files a project links instead of copying: which are found, which are missing or changed, where a moved original is now (search a folder by name, confirm by checksum, or point at the file), and Make self-contained, which stores every linked file inside the project so it needs no other file -- before sharing or depositing it.'
resource: chisurf/plugins/core/project_data/
tags: [reference, plugins, project-data, file, data]
anchor: plugin-project_data
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-project_data)=
# Project data

The data files a project links instead of copying: which are found, which are missing or changed, where a moved original is now (search a folder by name, confirm by checksum, or point at the file), and Make self-contained, which stores every linked file inside the project so it needs no other file -- before sharing or depositing it.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `project_data` |
| Menu path | File → Data → **Project data** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [The photon container: one measurement, one file](/concepts/photon_container.md)
- **Workflow** — [Linked data in a project — find moved files, make a project self-contained](/guides/114_project_data.md)

## Source

- Plugin package: `chisurf/plugins/core/project_data/`
- Manifest: {src}`chisurf/plugins/core/project_data/manifest.json`
- UI spec: {src}`chisurf/plugins/core/project_data/gui/project_data.view.json`
