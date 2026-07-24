(plugin-irf_estimator)=
# IRF Estimation

Blind IRF estimation from fluorescence decay data using truncated exponential fitting and Richardson-Lucy deconvolution.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `irf_estimator` |
| Menu path | Spectroscopy → Fluorescence decay → **IRF Estimation** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `irf_estimator` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `irf_estimator.jobs.estimate` | yes | Run IRF estimation on loaded decay data. |
| `irf_estimator.data.load_decay` | no | Load a VV/VH format decay file. |
| `irf_estimator.data.load_dataset` | no | Load decay data from a ChiSurf dataset. |
| `irf_estimator.data.save_irf` | no | Save estimated IRF to a VV/VH file. |
| `irf_estimator.data.transfer_irf` | no | Transfer estimated IRF to ChiSurf as a dataset. |
| `irf_estimator.contract.describe` | no | Return the IRF Estimator workflow contract. |

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/irf_estimator/`
- Manifest: `chisurf/plugins/fluorescence_decay/irf_estimator/manifest.json`
