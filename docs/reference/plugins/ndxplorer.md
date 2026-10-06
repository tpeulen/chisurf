---
type: Plugin Reference
title: ndX
description: Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data.
resource: chisurf/plugins/ndxplorer/
tags: [reference, plugins, ndxplorer, tools, views]
anchor: plugin-ndxplorer
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-ndxplorer)=
# ndX

Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `ndxplorer` |
| Menu path | Tools → Views → **ndX** |
| Categories | Tools, Views |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui |
| State namespace | `ndxplorer` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Density-based clustering](/concepts/density_clustering.md), [Interactive multidimensional exploration](/concepts/multidimensional_exploration.md)
- **Workflow** — [Exploring & fitting multidimensional data (ndX)](/guides/46_ndxplorer.md), [From a selection to a fit: the ndX analysis bridges](/guides/47_ndxplorer_bridges.md), [Sending a gated burst population to FCS, TCSPC, PDA or PCH](/guides/52_send_bursts_to_analysis.md)

## Source

- Plugin package: `chisurf/plugins/ndxplorer/`
- Manifest: {src}`chisurf/plugins/ndxplorer/manifest.json`
