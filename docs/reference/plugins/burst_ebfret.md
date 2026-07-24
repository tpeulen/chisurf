(plugin-burst_ebfret)=
# ebFRET (binned traces)

Empirical-Bayes Gaussian hidden Markov model for binned single-molecule FRET time traces (ebFRET/vbFRET-style), with a state-count scan, per-state emission recovery, and Viterbi dwell/transition analysis. Complements the photon-by-photon H2MM plugin for TIRF-style intensity-vs-time data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_ebfret` |
| Menu path | Spectroscopy → Single-Molecule → **ebFRET (binned traces)** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 0.1.0 |
| Surfaces | cli, services |
| State namespace | `burst_ebfret` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_ebfret.jobs.compute` | yes | Fit an empirical-Bayes Gaussian HMM over a set of binned FRET traces. |

## Source

- Plugin package: `chisurf/plugins/burst/burst_ebfret/`
- Manifest: `chisurf/plugins/burst/burst_ebfret/manifest.json`
