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

## Theory and workflow

- **Theory** — [Photon-by-photon HMM (H2MM)](/concepts/h2mm.md)
- **Workflow** — [Photon-by-photon hidden Markov models (H2MM)](/guides/19_h2mm_hidden_markov.md), [H2MM: complete workflow and results](/guides/30_h2mm_workflow_results.md), [H2MM: simulating and validating](/guides/31_h2mm_simulation_validation.md), [Exporting burst data](/guides/34_exporting_burst_data.md), [Photon-by-photon HMM (H2MM)](/guides/h2mm.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_h2mm/`
- Manifest: {src}`chisurf/plugins/burst/burst_h2mm/manifest.json`
