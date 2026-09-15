---
type: Plugin Reference
title: Imaging Common
description: 'Shared base classes for the per-pixel imaging tools: the common tool shell, the image/frame plumbing and the MMFDB bridge they all reuse.'
resource: chisurf/plugins/microscopy/imaging_common/
tags: [reference, plugins, imaging-common]
anchor: plugin-imaging_common
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-imaging_common)=
# Imaging Common

Shared base classes for the per-pixel imaging tools: the common tool shell, the image/frame plumbing and the MMFDB bridge they all reuse.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `imaging_common` |
| Menu path | Uncategorized → **Imaging Common** |
| Version | 1.0.0 |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/microscopy/imaging_common/`
- Manifest: {src}`chisurf/plugins/microscopy/imaging_common/manifest.json`
