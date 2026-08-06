---
type: Plugin Reference
title: VV/VH Anisotropy Decay
description: Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift.
resource: chisurf/plugins/vv_vh_anisotropy/
tags: [reference, plugins, vv-vh-anisotropy, spectroscopy, fluorescence-decay]
anchor: plugin-vv_vh_anisotropy
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-vv_vh_anisotropy)=
# VV/VH Anisotropy Decay

Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `vv_vh_anisotropy` |
| Menu path | Spectroscopy → Fluorescence decay → **VV/VH Anisotropy Decay** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `vv_vh_anisotropy` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/vv_vh_anisotropy/`
- Manifest: {src}`chisurf/plugins/vv_vh_anisotropy/manifest.json`
