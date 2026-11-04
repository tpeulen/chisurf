---
type: Plugin Reference
title: Excitation Windows
description: Detect the PIE pulses (micro time) or µs-ALEX alternation (macro time) of a measurement, propose prompt/delayed windows, and check a setup's windows against the data.
resource: chisurf/plugins/core/excitation_windows/
tags: [reference, plugins, excitation-windows, setup, tttr]
anchor: plugin-excitation_windows
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-excitation_windows)=
# Excitation Windows

Detect the PIE pulses (micro time) or µs-ALEX alternation (macro time) of a measurement, propose prompt/delayed windows, and check a setup's windows against the data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `excitation_windows` |
| Menu path | Setup → **Excitation Windows** |
| Categories | Setup, TTTR |
| Version | 1.0.0 |
| Surfaces | cli, emtk, services |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `excitation_windows.detect` | no | Detect the excitation scheme of a measurement (pie / alex / single / unclear) and propose windows. |
| `excitation_windows.check` | no | Check a setup's windows against a measurement: issues with severity and a proposal. |

## Theory and workflow

- **Workflow** — [Detecting and checking excitation windows](/guides/115_excitation_windows.md)

## Source

- Plugin package: `chisurf/plugins/core/excitation_windows/`
- Manifest: {src}`chisurf/plugins/core/excitation_windows/manifest.json`
- UI spec: {src}`chisurf/plugins/core/excitation_windows/gui/app.view.json`
