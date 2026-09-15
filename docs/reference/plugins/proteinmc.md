---
type: Plugin Reference
title: Protein Monte Carlo
description: Protein Monte Carlo CLI plugin. Expose the ProteinMC cmd tool via the unified ChiSurf CLI.
resource: chisurf/plugins/modelling/proteinmc/
tags: [reference, plugins, proteinmc, structure, computation]
anchor: plugin-proteinmc
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-proteinmc)=
# Protein Monte Carlo

Protein Monte Carlo CLI plugin.  Expose the ProteinMC cmd tool via the unified ChiSurf CLI.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `proteinmc` |
| Menu path | Structure → Computation → **Protein Monte Carlo** |
| Categories | Structure, Computation |
| Version | 1.0.0 |
| Surfaces | cli |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/modelling/proteinmc/`
- Manifest: {src}`chisurf/plugins/modelling/proteinmc/manifest.json`
