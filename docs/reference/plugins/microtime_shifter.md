(plugin-microtime_shifter)=
# Microtime Shifter

Apply global and per-channel micro-time shifts to TTTR files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `microtime_shifter` |
| Menu path | Tools → TTTR → **Microtime Shifter** |
| Categories | TTTR, Editor |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `microtime_shifter` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `microtime_shift.apply` | no | Apply micro-time shifts to TTTR files. |
| `microtime_shift.load_metadata` | no | Return routing channels and n_mt for a file. |
| `microtime_shift.identify` | no | Look up a file in the MMFDB object store. |
| `microtime_shift.contract.describe` | no | Return the Micro-time Shifter workflow contract. |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_microtime_shifter/`
- Manifest: `chisurf/plugins/tttr/tttr_microtime_shifter/manifest.json`
