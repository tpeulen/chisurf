---
type: Plugin Reference
title: ebFRET (binned traces)
description: Empirical-Bayes Gaussian hidden Markov model for binned single-molecule FRET time traces (ebFRET/vbFRET-style), with a state-count scan, per-state emission recovery, and Viterbi dwell/transition analysis. Complements the photon-by-photon H2MM plugin for TIRF-style intensity-vs-time data.
resource: chisurf/plugins/burst/burst_ebfret/
tags: [reference, plugins, burst-ebfret, spectroscopy, single-molecule]
anchor: plugin-burst_ebfret
generator: build_tools/docs/generate_plugin_docs.py
---

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

## Theory and workflow

- **Theory** — [ebFRET: variational-Bayes HMM of binned traces](/concepts/ebfret.md)
- **Workflow** — [Hidden Markov analysis of binned FRET traces (ebFRET)](/guides/20_ebfret_binned_hmm.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_ebfret/`
- Manifest: {src}`chisurf/plugins/burst/burst_ebfret/manifest.json`
