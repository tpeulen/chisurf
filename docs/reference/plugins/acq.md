---
type: Plugin Reference
title: Acquisition
description: 'Single-molecule fluorescence acquisition: stream photons from real TCSPC hardware or the built-in tttrlib Sim* photon simulator (confocal diffusion with FRET, anisotropy and photophysics).'
resource: chisurf/plugins/core/acq/
tags: [reference, plugins, acq, tools, views, acquisition]
anchor: plugin-acq
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-acq)=
# Acquisition

Single-molecule fluorescence acquisition: stream photons from real TCSPC hardware or the built-in tttrlib Sim* photon simulator (confocal diffusion with FRET, anisotropy and photophysics).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `acq` |
| Menu path | Tools → Views → **Acquisition** |
| Categories | Tools, Views, Acquisition |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `acq` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Device session

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Device type | `device_type` | choice |  | choices: SIMULATION, BH_SPC, PICOQUANT, BRICKMIC | Selection alone never loads, scans, or contacts a physical device. |
| Time limit (s) | `time_limit_s` | float |  | 0.0 … 36000.0 (step 1.0) | Wall-clock stop condition. Set zero to disable it; retain a positive photon limit. |
| Photon limit | `photon_limit` | int |  | 0 … 1000000000 (step 1) | Decoded-photon stop condition. Set zero only when a positive time limit is configured. |

### Routing and output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Routing channel 1 | `channel_0` | int |  | 0 … 4095 (step 1) | Device routing channel for pipeline decay window 1. |
| Routing channel 2 | `channel_1` | int |  | 0 … 4095 (step 1) | Device routing channel for pipeline decay window 2. |
| Routing channel 3 | `channel_2` | int |  | 0 … 4095 (step 1) | Device routing channel for pipeline decay window 3. |
| Routing channel 4 | `channel_3` | int |  | 0 … 4095 (step 1) | Device routing channel for pipeline decay window 4. |
| Output folder | `output_folder` | str |  |  | Optional path passed only to compatible simulation or BrickMic backends; this UI never claims every device writes raw files. |

### Simulator configuration

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Peak brightness | `brightness_khz` | float |  | 1.0 … 2000.0 (step 10.0) | Simulator brightness used to build encoded records; never a hardware detector setting. |
| Deterministic seed | `seed` | int |  | 0 … 2147483647 (step 1) | Simulator random seed for reproducible encoded records. |

### Result visibility

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Decay / intensity tab | `show_decay` | bool |  |  | Show the pipeline-derived decay and intensity tab. |
| Correlation / quality tab | `show_correlation` | bool |  |  | Show the pipeline-derived correlation, burst, and phasor tab. |
| Overview tab | `show_count_rate` | bool |  |  | Show decoded count, elapsed time, rate, and progress. |
| Macrotime tab | `show_macrotime` | bool |  |  | Show the bounded macrotime interval count from the pipeline. |
| MCS trace tab | `show_mcs` | bool |  |  | Show the pipeline MCS trace sample count. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `acq.simulation.run` | yes | Run the tttrlib Sim* photon simulator: Brownian diffusion of fluorophores through a confocal excitation focus, with N-state photophysics/FRET, rotational anisotropy and CW/pulsed emission, returning (or writing) the photon stream (macro-time window, routing channel, micro-time/TAC channel). Every parameter maps onto tttrlib's SimSystem / SimSpecies / SimGrid / SimIntegrator; this per-parameter help is the single source of truth shared by the GUI tooltips, the CLI, the Python API and this RPC method. Diffusion/rate/brightness units share one abstract MACRO-time unit (ChiSurf/BurstNet convention: milliseconds, so a rate of 1.0 = 1 kHz); the micro-time / TAC axis is a separate axis in nanoseconds. |

## Theory and workflow

- **Workflow** — [Live acquisition: watching a measurement while it happens](/guides/65_live_acquisition.md)

## Source

- Plugin package: `chisurf/plugins/core/acq/`
- Manifest: {src}`chisurf/plugins/core/acq/manifest.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/acq_emtk.view.json`
