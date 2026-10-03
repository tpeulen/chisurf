---
type: Plugin Reference
title: H2MM
description: Photon-by-photon Hidden Markov Model (H2MM) analysis of single-molecule FRET burst data, with BIC/ICL state selection and Viterbi dwell/transition analysis.
resource: chisurf/plugins/burst/burst_h2mm/
tags: [reference, plugins, burst-h2mm, spectroscopy, single-molecule]
anchor: plugin-burst_h2mm
generator: build_tools/docs/generate_plugin_docs.py
---

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
| Surfaces | cli, emtk, gui, services |
| State namespace | `burst_h2mm` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Data

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Burst folder | `data_folder` | directory |  |  | Folder with the burst (.bur) tables of a finished burst analysis; the photons they name are read from beside them. |
| Donor detector | `donor` | choice |  | choices: `detector_names` | Detector of the donor photons (stream 0): apparent FRET E = A/(A+D). Define detectors in the Detector setup window. |
| Acceptor detector | `acceptor` | choice |  | choices: `detector_names` | Detector of the acceptor photons (stream 1). Swapping donor and acceptor still converges and looks plausible: check the assignment. |
| Aex detector | `aex` | choice |  | choices: `aex_options` | Optional third stream (usALEX / PIE): acceptor photons under acceptor excitation. Gives every state a stoichiometry. |

### Model selection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Min states | `min_states` | int |  | 1 … 8 | Smallest number of states tried. |
| Max states | `max_states` | int |  | 1 … 8 | Largest number of states tried. |
| Criterion | `criterion` | choice |  | choices: bic, icl | Information criterion that picks the state count: BIC, or ICL which also penalises overlapping states. |
| Scan patience | `patience` | int |  | -1 … 8 | Stop the state-count scan once the criterion has risen this many times (about 1.6 times faster); -1 fits every state count. |

### Optimisation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Engine | `engine` | choice |  | choices: em-float32, em, neural | Compute engine: fast float32 EM (default), exact float64 EM, or the neural surrogate (fastest, approximate). |
| Restarts | `restarts` | int |  | 1 … 20 | Random initialisations per state count; the best log-likelihood wins. |
| Seed | `seed` | int |  | 0 … 2147483646 | Seed of the restarts: the same seed refits to the same answer. |
| Max iterations | `max_iter` | int |  | 10 … 5000 | Maximum EM iterations per fit. |
| Min photons / burst | `min_photons` | int |  | 2 … 1000 | Bursts with fewer stream photons are left out. |
| Macro-time scale | `time_scale` | int |  | 1 … 100000 | Integer down-scaling of macro times (coarser base unit); raise it when the fit is slow. |
| Nanotime divisors | `divisors` | int |  | 1 … 8 | Split each stream into this many micro-time bins so states of equal E but different lifetime separate; 1 is off. |

### Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Photon table HDF5 | `photon_hdf5` | bool |  |  | Write h2mm_photons.h5: compact and fast to reload. |
| Photon table CSV | `photon_csv` | bool |  |  | Write h2mm_photons.csv: what every other tool can open. |
| Decoder | `decoder` | choice |  | choices: viterbi, jitter, ffbs | How one state is assigned per photon: Viterbi (most likely path), jitter (draw per photon) or ffbs (draw whole paths). |
| Decoder seed | `decoder_seed` | int |  | 0 … 2147483646 | Seed of the sampling decoders. |
| Write state photons | `write_state_tttr` | bool |  |  | Write the decoded assignment back beside each source measurement. |
| State photons as PTU | `state_tttr_ptu` | bool |  |  | A PTU whose routing channels encode (stream, state). |
| State photons sidecar | `state_tttr_sidecar` | bool |  |  | A msgpack sidecar; the source file is left untouched. |

### Burst

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Burst | `nav_burst` | int |  | 0 … 10000000 | Index into the bursts listed for the state-path plot (all bursts, or only those with a decoded transition). |
| Dynamic bursts only | `dynamic_only` | bool |  |  | List only bursts with at least one decoded transition. |

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
- UI spec: {src}`chisurf/plugins/burst/burst_h2mm/gui/h2mm.view.json`
