---
type: Plugin Reference
title: Metadata Editor
description: 'The one metadata editor: a schema of typed fields plus free-form extras, validated, shared by every plugin that has metadata (burst selection''s flrCIF metadata, the Zenodo deposit, ...). Standalone it edits a JSON metadata file.'
resource: chisurf/plugins/core/metadata_editor/
tags: [reference, plugins, metadata-editor, file, data]
anchor: plugin-metadata_editor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-metadata_editor)=
# Metadata Editor

The one metadata editor: a schema of typed fields plus free-form extras, validated, shared by every plugin that has metadata (burst selection's flrCIF metadata, the Zenodo deposit, ...). Standalone it edits a JSON metadata file.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `metadata_editor` |
| Menu path | File → Data → **Metadata Editor** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Metadata records — typed fields plus free-form extras](/concepts/metadata_editor.md)
- **Workflow** — [Editing a metadata record](/guides/113_metadata_editor.md)

## Source

- Plugin package: `chisurf/plugins/core/metadata_editor/`
- Manifest: {src}`chisurf/plugins/core/metadata_editor/manifest.json`
