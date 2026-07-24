(plugin-burst_h2mm)=
# H2MM

Photon-by-photon Hidden Markov Model (H2MM) analysis of single-molecule FRET burst data, with BIC/ICL state selection and Viterbi dwell/transition analysis.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_h2mm` |
| Menu path | Spectroscopy → Single-Molecule → **H2MM** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_h2mm` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_h2mm.jobs.compute` | yes | Fit photon-by-photon HMM (H2MM) models over burst data. |
| `burst_h2mm.workflow.prepare` | no | Resolve H2MM settings and folders from a burst workflow context. |
| `burst_h2mm.contract.describe` | no | Return the H2MM workflow contract. |

## Source

- Plugin package: `chisurf/plugins/burst/burst_h2mm/`
- Manifest: `chisurf/plugins/burst/burst_h2mm/manifest.json`
