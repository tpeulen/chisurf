(plugin-vv_vh_g_factor)=
# VV/VH G-Factor Calculator

Calculate detector G-factors using tail-matching on VV/VH format files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `vv_vh_g_factor` |
| Menu path | Spectroscopy → Fluorescence decay → **VV/VH G-Factor Calculator** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `vv_vh_g_factor` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `vv_vh_g_factor.calculate` | no | Calculate G-factor based on tail matching for VV/VH decays. |
| `vv_vh_g_factor.perrin_steady_state` | no | Perrin steady-state anisotropy for a sphere. |
| `vv_vh_g_factor.solve_linked_l` | no | Solve for the linked l1=l2 mixing parameter. |
| `vv_vh_g_factor.archive_g_factor` | no | Register reference decay and archive G-factor calibration in MMFDB. |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/vv_vh_g_factor/`
- Manifest: {src}`chisurf/plugins/vv_vh_g_factor/manifest.json`
