(plugin-globalview)=
# Global View

Interactive network graph for visualizing and managing parameter relationships across fits in global analysis.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `globalview` |
| Menu path | Main → Tools → **Global View** |
| Categories | Main, Tools |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `globalview` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `globalview.graph.build` | no | Build a parameter relationship graph from fit objects. |
| `globalview.parameters.list` | no | List all parameters across fits with their values, bounds, and link status. |
| `globalview.parameters.link` | no | Link two parameters by name across fits. |
| `globalview.parameters.unlink` | no | Unlink a parameter. |

## Source

- Plugin package: `chisurf/plugins/core/globalview/`
- Manifest: `chisurf/plugins/core/globalview/manifest.json`
