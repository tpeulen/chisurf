---
type: Plugin Reference
title: Photon-by-photon kinetics
description: 'Gopich-Szabo photon-by-photon maximum likelihood: continuous-time rate constants and per-state FRET efficiencies fitted directly to photon arrival times and colours, for two- and three-colour data, with a transition-time scan and an H2MM cross-check.'
resource: chisurf/plugins/burst/burst_gs/
tags: [reference, plugins, burst-gs, spectroscopy, single-molecule, fret]
anchor: plugin-burst_gs
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_gs)=
# Photon-by-photon kinetics

Gopich-Szabo photon-by-photon maximum likelihood: continuous-time rate constants and per-state FRET efficiencies fitted directly to photon arrival times and colours, for two- and three-colour data, with a transition-time scan and an H2MM cross-check.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_gs` |
| Menu path | Spectroscopy → Single-Molecule → **Photon-by-photon kinetics** |
| Categories | Spectroscopy, Single-Molecule, FRET |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_gs` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Photons

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| bur_files | `bur_files` | path_list |  |  |  |
| TTTR folder | `data_dir` | directory |  |  | Folder the raw TTTR files named in the burst table resolve against. Left empty, the burst table's own folder is used. |
| Container | `file_type` | choice |  | choices: `file_type_options` | TTTR container type of the raw files, or Auto to detect it. |
| Donor channels | `donor_channels` | str |  |  | Routing channels counted as donor photons, comma separated. This is colour 0. |
| Acceptor channels | `acceptor_channels` | str |  |  | Routing channels counted as acceptor photons, comma separated. This is colour 1. Photons in neither list — acceptor-excitation photons, for instance — are dropped. |
| Macro-time tick [ns] | `macro_time_resolution_ns` | float |  | 0.0 … 1000000.0 | Seconds per macro-time tick, in nanoseconds. Zero reads it from the file header. Every fitted rate is proportional to this, so a wrong value rescales the whole answer silently. |
| Min photons/burst | `min_photons` | int |  | 2 … 10000 | Bursts with fewer photons are dropped. A burst too short to show a spread of interphoton gaps contributes nothing to the kinetics and only costs time. |
| Max bursts | `max_bursts` | int |  | 0 … 1000000 | Keep at most this many bursts; 0 uses all of them. Lower it for a quick first look. |

### Simulate instead

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Simulate | `use_simulation` | bool |  |  | Fit simulated photons instead of the loaded files. |
| k(1→2) [1/s] | `sim_k_forward` | float |  | 0.1 … 10000000.0 | True forward rate of the simulated molecule. |
| k(2→1) [1/s] | `sim_k_backward` | float |  | 0.1 … 10000000.0 | True backward rate. |
| E state 1 | `sim_e1` | float |  | 0.0 … 1.0 | True FRET efficiency of state 1. |
| E state 2 | `sim_e2` | float |  | 0.0 … 1.0 | True FRET efficiency of state 2. States closer together than the shot noise cannot be separated however many photons you collect. |
| Photon rate [kHz] | `sim_photon_rate_khz` | float |  | 0.1 … 100000.0 | Detected photons per second within a burst. This sets the fastest exchange that can be resolved at all: nothing faster than the interphoton time is visible. |
| Bursts | `sim_n_bursts` | int |  | 1 … 100000 | Number of simulated bursts. |
| Photons/burst | `sim_photons_per_burst` | int |  | 5 … 100000 | Photons in each simulated burst. |
| Seed | `sim_seed` | int |  | 0 … 1000000 | Random seed, so a simulation can be reproduced. |

### Model

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| States | `n_states` | int |  | 2 … 5 | Number of kinetic states. Add one only when the BIC clearly falls: every extra state costs n more rates and always fits a little better. |
| Initial rate [1/s] | `initial_rate` | float |  | 0.1 … 10000000.0 | Starting value for every rate. Rates are optimised in log space, so this only needs to be the right order of magnitude. |
| Fix efficiencies | `fix_efficiencies` | bool |  |  | Hold the per-state efficiencies at their starting values and fit only the rates. Worth doing when the efficiencies are known from a static measurement: rates and efficiencies are the most strongly correlated pair in this problem. |
| Optimiser | `method` | choice |  | choices: `method_options` | Nelder-Mead is derivative-free and robust; L-BFGS-B is faster but leans on finite differences of a likelihood that is only piecewise smooth. |
| Max iterations | `max_iterations` | int |  | 50 … 100000 | Optimiser iteration cap. |

### Extras

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Scan transition time | `scan_transition_time` | bool |  |  | After fitting, insert an explicit intermediate the molecule must cross and scan how long it takes. Two states only. Usually this returns an upper bound rather than a measurement, which is itself the useful answer. |
| Scan points | `transit_points` | int |  | 5 … 200 | Points in the transition-time scan, spread logarithmically from 1 µs to 1 ms. |
| Decode state path | `decode_states` | bool |  |  | Compute the most likely state of every photon (Viterbi). An illustration of the fitted model, not a measurement: it draws a definite path even where the photons support none. |
| Cross-check with H2MM | `cross_check_h2mm` | bool |  |  | Fit the same photons with the discrete-time H2MM engine and compare. The two share no code and parameterise time differently, so agreement is real evidence — and disagreement is worth chasing before you believe either. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_gs.jobs.fit` | yes | Fit a continuous-time kinetic scheme to coloured photons. |
| `burst_gs.jobs.log_likelihood` | no | Evaluate the Gopich-Szabo log-likelihood of a given scheme. |
| `burst_gs.jobs.transition_time_scan` | yes | Scan the log-likelihood against the duration of a transition. |

## Theory and workflow

- **Theory** — [Photon-by-photon kinetics (Gopich–Szabo)](/concepts/photon_by_photon_kinetics.md)
- **Workflow** — [Photon-by-photon kinetics: rates without binning](/guides/49_photon_by_photon_kinetics.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_gs/`
- Manifest: {src}`chisurf/plugins/burst/burst_gs/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_gs/gui/burst_gs.view.json`
