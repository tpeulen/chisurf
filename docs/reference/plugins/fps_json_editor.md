(plugin-fps_json_editor)=
# FPS JSON Editor

Edit fps.json files for FRET accessible-volume modeling and fetch reference PDB structures by RCSB ID.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fps_json_editor` |
| Menu path | Structure → FRET → **FPS JSON Editor** |
| Categories | Structure, FRET |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `fps_json_editor` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fps_json_editor.pdb.fetch` | no | Download a PDB file from RCSB by four-character PDB ID. |
| `fps_json_editor.contract.describe` | no | Return the FPS JSON Editor workflow contract. |
| `fps_json_editor.payload.validate` | no | Validate an fps.json payload and return errors, warnings, and a summary. |
| `fps_json_editor.payload.summarize` | no | Summarize positions, distances, score sets, and unresolved references. |
| `fps_json_editor.payload.normalize` | no | Normalize an fps.json payload through the core data model. |
| `fps_json_editor.av.mrc.save` | no | Save AV points as an IMP-backed MRC density map. |

## Source

- Plugin package: `chisurf/plugins/modelling/fps_json_editor/`
- Manifest: `chisurf/plugins/modelling/fps_json_editor/manifest.json`
