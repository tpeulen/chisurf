---
type: Plugin Reference
title: Protein Monte Carlo
description: 'Command-line Protein Monte Carlo: torsion-angle sampling of a structure under FRET distance restraints, written as an RMF trajectory.'
resource: chisurf/plugins/modelling/proteinmc/
tags: [reference, plugins, proteinmc, structure, computation]
anchor: plugin-proteinmc
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-proteinmc)=
# Protein Monte Carlo

Command-line Protein Monte Carlo: torsion-angle sampling of a structure under FRET distance restraints, written as an RMF trajectory.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `proteinmc` |
| Menu path | not in the menus; display name Structure → Computation → **Protein Monte Carlo** |
| Categories | Structure, Computation |
| Version | 1.0.0 |
| Surfaces | cli |

## Parameters

This plugin opens no window: it is a command-line tool (`csc proteinmc --help` lists its options).

## Theory and workflow

- **Theory** — [Protein Monte Carlo: torsion-angle sampling under distance restraints](/concepts/protein_monte_carlo.md)
- **Workflow** — [Sampling a protein under FRET distance restraints](/guides/106_protein_monte_carlo.md)

## Source

- Plugin package: `chisurf/plugins/modelling/proteinmc/`
- Manifest: {src}`chisurf/plugins/modelling/proteinmc/manifest.json`
