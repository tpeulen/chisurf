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
| Menu path | not in the menus; display name Uncategorized → **Imaging Common** |
| Version | 1.0.0 |

## Parameters

This plugin opens no window and has no parameters: it is shared code that other plugins import.

## Theory and workflow

- **Theory** — [FLIM and the phasor approach](/concepts/imaging_flim_phasor.md)
- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/imaging_common/`
- Manifest: {src}`chisurf/plugins/microscopy/imaging_common/manifest.json`
