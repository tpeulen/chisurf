(plugin-structure_tools)=
# Structure Tools

Unified structure toolbox: FPS JSON Editor, FRET Docking & Screening, Kappa2 Distribution, QuEst, HydroPro and Trajectory Tools.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `structure_tools` |
| Menu path | Structure → Structure → **Structure Tools** |
| Categories | Structure |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Molecular surfaces and solvent accessibility](/concepts/molecular_surfaces.md)
- **Workflow** — [Accessible-volume (AV) calculations](/guides/23_accessible_volume.md)

## Source

- Plugin package: `chisurf/plugins/modelling/structure_tools/`
- Manifest: {src}`chisurf/plugins/modelling/structure_tools/manifest.json`
