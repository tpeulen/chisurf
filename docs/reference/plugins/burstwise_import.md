---
type: Plugin Reference
title: Burstwise→PTO
description: Convert legacy burstwise analysis folders (bi4_bur/bg4/br4/BIDs/Info/.mti) to PTO.MFDB containers.
resource: chisurf/plugins/burst/burstwise_import/
tags: [reference, plugins, burstwise-import, file, data]
anchor: plugin-burstwise_import
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burstwise_import)=
# Burstwise→PTO

Convert legacy burstwise analysis folders (bi4_bur/bg4/br4/BIDs/Info/.mti) to PTO.MFDB containers.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burstwise_import` |
| Menu path | File → Data → **Burstwise→PTO** |
| Categories | File, Data |
| Version | 0.1.0 |
| Surfaces | cli, emtk, services |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burstwise_import.jobs.import_folder` | yes | Convert a legacy burstwise analysis folder to PTO.MFDB containers. |
| `burstwise_import.contract.describe` | no | Return the burstwise_import workflow contract. |

## Source

- Plugin package: `chisurf/plugins/burst/burstwise_import/`
- Manifest: {src}`chisurf/plugins/burst/burstwise_import/manifest.json`
