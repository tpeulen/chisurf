(plugin-traj_tools)=
# Traj Tools

Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_tools` |
| Menu path | Structure → Structure → **Traj Tools** |
| Categories | Structure, Tools |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_tools` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/traj/traj_tools/`
- Manifest: {src}`chisurf/plugins/traj/traj_tools/manifest.json`
