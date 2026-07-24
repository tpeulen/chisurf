(plugin-maxent_decay)=
# MaxEnt MEM

Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `maxent_decay` |
| Menu path | Spectroscopy → Fluorescence decay → **MaxEnt MEM** |
| Categories | Spectroscopy, Fluorescence |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `maxent_decay` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `maxent_decay.jobs.run_lifetime_mem` | yes | Run MaxEnt lifetime MEM on arrays. |
| `maxent_decay.jobs.run_fret_mem` | yes | Run MaxEnt FRET distance MEM on arrays. |
| `maxent_decay.jobs.run_lcurve` | yes | Sweep regularization values and return L-curve data. |
| `maxent_decay.contract.describe` | no | Return the MaxEnt workflow contract. |

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/maxent_decay/`
- Manifest: `chisurf/plugins/fluorescence_decay/maxent_decay/manifest.json`
