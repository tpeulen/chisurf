---
type: Plugin Reference
title: Lazy Lifetime Analysis
description: Lazy Lifetime Analysis for TCSPC fluorescence decay data.
resource: chisurf/plugins/fluorescence_decay/lltf/
tags: [reference, plugins, lltf, spectroscopy, fluorescence-decay]
anchor: plugin-lltf
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-lltf)=
# Lazy Lifetime Analysis

Lazy Lifetime Analysis for TCSPC fluorescence decay data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lltf` |
| Menu path | Spectroscopy → Fluorescence decay → **Lazy Lifetime Analysis** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `lltf` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/lltf/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/lltf/manifest.json`
