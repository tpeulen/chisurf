---
type: Plugin Reference
title: Legacy Export
description: 'The dedicated way out of the .pto world: unpack a container into the Seidel/Margarita legacy burst folder (bi4_bur/*.bur plus one companion directory per analysis), and write the five ALEX-Suite CSVs from a container run. The workflow tools read and write .pto only; legacy formats are reached from here.'
resource: chisurf/plugins/core/legacy_export/
tags: [reference, plugins, legacy-export, file, data]
anchor: plugin-legacy_export
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-legacy_export)=
# Legacy Export

The dedicated way out of the .pto world: unpack a container into the Seidel/Margarita legacy burst folder (bi4_bur/*.bur plus one companion directory per analysis), and write the five ALEX-Suite CSVs from a container run. The workflow tools read and write .pto only; legacy formats are reached from here.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `legacy_export` |
| Menu path | File → Data → **Legacy Export** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | cli, emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Legacy export: the burst folder and the ALEX-Suite CSVs as views of a container](/concepts/legacy_export.md)
- **Workflow** — [Exporting burst data](/guides/34_exporting_burst_data.md)

## Source

- Plugin package: `chisurf/plugins/core/legacy_export/`
- Manifest: {src}`chisurf/plugins/core/legacy_export/manifest.json`
