---
type: Plugin Reference
title: Boarding Wizard
description: Startup onboarding wizard for first-run ChiSurf configuration.
resource: chisurf/plugins/core/boarding/
tags: [reference, plugins, boarding, help]
anchor: plugin-boarding
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-boarding)=
# Boarding Wizard

Startup onboarding wizard for first-run ChiSurf configuration.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `boarding` |
| Menu path | Help → **Boarding Wizard** |
| Categories | Help |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `boarding` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/boarding/`
- Manifest: {src}`chisurf/plugins/core/boarding/manifest.json`
- UI spec: {src}`chisurf/plugins/core/boarding/boarding.view.json`
- UI spec: {src}`chisurf/plugins/core/boarding/boarding_emtk.view.json`
