(plugin-burst_mle_analysis)=
# Burst MLE

Maximum likelihood lifetime analysis for single-molecule burst data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_mle_analysis` |
| Menu path | Spectroscopy → Single-Molecule → **Burst MLE** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.1.0 |
| Surfaces | gui, services |
| State namespace | `burst_mle_analysis` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_mle.workflow.prepare` | no | Resolve MLE burst files and channel definitions from workflow context. |
| `burst_mle.contract.describe` | no | Return the Burst MLE workflow contract. |

## Source

- Plugin package: `chisurf/plugins/burst/burst_mle_analysis/`
- Manifest: `chisurf/plugins/burst/burst_mle_analysis/manifest.json`
