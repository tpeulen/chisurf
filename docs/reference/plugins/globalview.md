---
type: Plugin Reference
title: Global View
description: Interactive network graph for visualizing and managing parameter relationships across fits in global analysis.
resource: chisurf/plugins/core/globalview/
tags: [reference, plugins, globalview, tools, views]
anchor: plugin-globalview
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-globalview)=
# Global View

Interactive network graph for visualizing and managing parameter relationships across fits in global analysis.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `globalview` |
| Menu path | Tools → Views → **Global View** |
| Categories | Tools, Views |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `globalview` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Toolbar

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| auto | `auto_refresh` | bool |  |  | Redraw when a fit or a link changes. Changes are coalesced and the layout only re-runs when the network's shape changed, so a running fit costs nothing here. Untick to refresh by hand. |
| all | `unlink_all` | bool |  |  | Unlink applies to EVERY parameter in every fit, not just the selection. |

### View

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show | `representation` | choice |  | choices: network, factor graph | Parameter network: every fit with the parameters it owns, and an arrow from each linked parameter to the one it follows. Factor graph: each dataset's likelihood (a square) over the variables it depends on, links resolved -- a parameter shared by two datasets is one variable joined to both, drawn gold, and a follower hangs off its master. |
| Layout | `graph_layout` | choice |  | choices: kamada_kawai, spring, shell, arf, spectral | Algorithm that places the nodes: kamada_kawai and spring keep linked parameters near each other, shell and spectral expose structure. |
| Node size | `node_size` | float |  | 4 … 40 (step 1) | Radius of a parameter node, in pixels; fits and factors are drawn larger. |
| Spread | `graph_scale` | float |  | 0.2 … 8 (step 0.1) | Spread the network beyond the panel (pan and zoom to read it): how a crowded graph is pulled apart without changing its layout. |
| Connect base | `connect_owners` | bool |  |  | Draw a line between every pair of owners -- every fit AND every registered parameter group (ndX, a calculator) -- so a plugin's working model sits with the fits it can be linked to. Visual only: it links nothing. |
| Include fixed | `include_fixed` | bool |  |  | Show parameters held fixed; they cannot be fitted but can still be linked. In the factor graph they are evidence: a grey node on the likelihood that reads them. |

### Parameters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Shade values | `shade_values` | bool |  |  | Colour Value and Error cells by their magnitude, each column over its own range. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `globalview.graph.build` | no | Build a parameter relationship graph from fit objects. |
| `globalview.parameters.list` | no | List all parameters across fits with their values, bounds, and link status. |
| `globalview.parameters.link` | no | Link two parameters by name across fits. |
| `globalview.parameters.unlink` | no | Unlink a parameter. |

## Theory and workflow

- **Workflow** — [Global analysis: linking parameters across fits](/guides/60_global_analysis.md)

## Source

- Plugin package: `chisurf/plugins/core/globalview/`
- Manifest: {src}`chisurf/plugins/core/globalview/manifest.json`
- UI spec: {src}`chisurf/plugins/core/globalview/gui/globalview.view.json`
