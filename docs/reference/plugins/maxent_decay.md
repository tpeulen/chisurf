---
type: Plugin Reference
title: MaxEnt MEM
description: Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance).
resource: chisurf/plugins/fluorescence_decay/maxent_decay/
tags: [reference, plugins, maxent-decay, spectroscopy, fluorescence-decay]
anchor: plugin-maxent_decay
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-maxent_decay)=
# MaxEnt MEM

Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `maxent_decay` |
| Menu path | Spectroscopy → Fluorescence decay → **MaxEnt MEM** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `maxent_decay` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### MEM settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `mode` | choice |  | choices: lifetime, fret | Invert a lifetime spectrum or a FRET-distance distribution (the FRET mode needs a donor-only spectrum). |
| nu (reg) | `nu` | float |  | 1e-08 … 1.0 (step 0.001) | Entropy regularization weight: small values fit the noise, large ones smooth the distribution. |
| MEM iterations | `max_iter` | int |  | 1 … 100000 (step 10) | Maximum iterations of the compiled MEM solver. |

### Lifetime grid

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| tau min (ns) | `tau_min` | float |  | 0.001 … 1000.0 (step 0.01) | Smallest lifetime of the grid (set from the IRF width when data is taken from a fit). |
| tau max (ns) | `tau_max` | float |  | 0.001 … 1000.0 (step 0.1) | Largest lifetime of the grid. |
| tau points | `tau_bins` | int |  | 2 … 10000 (step 1) | Number of grid points. |

### Distance grid

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| tau0 (ns) | `tau0` | float |  | 0.01 … 100.0 (step 0.1) | Unquenched donor reference lifetime. |
| R0 (A) | `R0` | float |  | 10.0 … 100.0 (step 1.0) | Foerster radius used to convert FRET rates to distances. |
| R/R0 min | `r_min_frac` | float |  | 0.001 … 10.0 (step 0.05) | Lower distance boundary relative to R0. |
| R/R0 max | `r_max_frac` | float |  | 0.001 … 10.0 (step 0.05) | Upper distance boundary relative to R0. |
| R points | `r_bins` | int |  | 2 … 10000 (step 1) | Number of distance grid points. |
| donor-only fraction | `x_donly` | float |  | 0.0 … 1.0 (step 0.05) | Fraction of unquenched donor in the sample. |
| fix donor-only fraction | `fix_x_donly` | bool |  |  | Keep the donor-only fraction at its value during nuisance optimization. |

### Periodic convolution

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Periodic convolution | `use_periodic` | bool |  |  | Include repeated excitation pulses instead of a single-shot decay. |
| Period (ns) | `period` | float |  | 0.1 … 1000.0 (step 1.0) | Pulse separation used with periodic convolution (initialised from the decay window). |

### Instrument

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| timeshift (ch) | `timeshift` | float |  | -100.0 … 100.0 (step 0.01) | Response shift in histogram channels. |
| background (cts) | `background` | float |  | 0.0 … 1000000000.0 (step 1.0) | Constant decay background. |
| IRF background (cts) | `irf_background` | float |  | 0.0 … 1000000000.0 (step 1.0) | Response baseline; zero selects the automatic baseline estimate. |
| lamp scatter | `lamp_scatter` | float |  | 0.0 … 1000.0 (step 0.001) | Fixed amplitude of scattered excitation light. |

### Nuisance optimization

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Fit nuisance (ts/bg/IRF BG) | `optimize_nuisance` | bool |  |  | Let the solver fit the timeshift, background and IRF background whose fix switches are off. |
| fix timeshift | `fix_timeshift` | bool |  |  | Hold the timeshift at its value during nuisance optimization. |
| fix background | `fix_background` | bool |  |  | Hold the background at its value during nuisance optimization. |
| fix IRF background | `fix_irf_background` | bool |  |  | Hold the IRF background at its value during nuisance optimization. |

### L-curve

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| decades below nu | `lcurve_left` | float |  | 0.0 … 6.0 (step 0.5) | Decades below the current nu scanned by the L-curve. |
| decades above nu | `lcurve_right` | float |  | 0.0 … 6.0 (step 0.5) | Decades above the current nu scanned by the L-curve. |

### Sampling

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Q-MCMC steps | `sample_steps` | int |  | 10 … 1000000 (step 100) | Total ensemble steps. |
| Q-MCMC thinning | `sample_thin` | int |  | 1 … 1000 (step 1) | Keep every n-th step. |
| Walkers (0=auto) | `sample_walkers` | int |  | 0 … 1000000 (step 1) | Number of walkers; zero uses the sampler default. |
| Chunk size (substeps) | `sample_substeps` | int |  | 1 … 1000000 (step 10) | Steps per progress update and saved chunk. |
| CPUs (0=auto) | `sample_nprocs` | int |  | 0 … 64 (step 1) | Worker processes; zero selects a platform default. |
| Vectorized sampling | `sample_vectorized` | bool |  |  | Evaluate ensemble log probabilities in vectorized batches. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `maxent_decay.jobs.run_lifetime_mem` | yes | Run MaxEnt lifetime MEM on arrays. |
| `maxent_decay.jobs.run_fret_mem` | yes | Run MaxEnt FRET distance MEM on arrays. |
| `maxent_decay.jobs.run_lcurve` | yes | Sweep regularization values and return L-curve data. |
| `maxent_decay.contract.describe` | no | Return the MaxEnt workflow contract. |

## Theory and workflow

- **Theory** — [Lifetime distributions and maximum entropy](/concepts/maximum_entropy.md), [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [Maximum-entropy decay analysis](/guides/62_maxent_decay.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/maxent_decay/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/maxent_decay/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/maxent_decay/gui/maxent_emtk.view.json`
