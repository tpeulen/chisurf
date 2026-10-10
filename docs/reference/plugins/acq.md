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
| Surfaces | cli, emtk, services |
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
| Decay plot | `show_decay` | bool |  |  | Show the live decay plot tab. |
| Correlation plot | `show_correlation` | bool |  |  | Show the live correlation plot tab. |
| Count-rate plot | `show_count_rate` | bool |  |  | Show the live count-rate plot tab. |
| Macrotime plot | `show_macrotime` | bool |  |  | Show the live macrotime plot tab. |
| MCS plot | `show_mcs` | bool |  |  | Show the live MCS trace tab. |

### Decay

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Curve 0 | `decay_show0` | bool |  |  | Draw decay window 0. |
| Curve 1 | `decay_show1` | bool |  |  | Draw decay window 1. |
| Curve 2 | `decay_show2` | bool |  |  | Draw decay window 2. |
| Curve 3 | `decay_show3` | bool |  |  | Draw decay window 3. |
| Log Y scale | `decay_log_y` | bool |  |  | Logarithmic counts axis; empty bins are not drawn. |
| Update every (snapshots) | `decay_every` | int |  | 1 … 1000 (step 1) | Redraw this plot only on every N-th published snapshot (a snapshot is one data chunk batch); raise it to spare the CPU on fast streams. |

### Correlation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Curve 0 channel A | `corr_a0` | int |  | -1 … 4095 (step 1) | Routing channel of the first side; -1 means every photon. Applied when the acquisition starts. |
| channel B | `corr_b0` | int |  | -1 … 4095 (step 1) | Routing channel of the second side; equal to A gives the autocorrelation, -1 means every photon. |
| Curve 0 | `corr_show0` | bool |  |  | Compute and draw this correlation curve. |
| Curve 1 channel A | `corr_a1` | int |  | -1 … 4095 (step 1) | Routing channel of the first side; -1 means every photon. Applied when the acquisition starts. |
| channel B | `corr_b1` | int |  | -1 … 4095 (step 1) | Routing channel of the second side; equal to A gives the autocorrelation, -1 means every photon. |
| Curve 1 | `corr_show1` | bool |  |  | Compute and draw this correlation curve. |
| Curve 2 channel A | `corr_a2` | int |  | -1 … 4095 (step 1) | Routing channel of the first side; -1 means every photon. Applied when the acquisition starts. |
| channel B | `corr_b2` | int |  | -1 … 4095 (step 1) | Routing channel of the second side; equal to A gives the autocorrelation, -1 means every photon. |
| Curve 2 | `corr_show2` | bool |  |  | Compute and draw this correlation curve. |
| Curve 3 channel A | `corr_a3` | int |  | -1 … 4095 (step 1) | Routing channel of the first side; -1 means every photon. Applied when the acquisition starts. |
| channel B | `corr_b3` | int |  | -1 … 4095 (step 1) | Routing channel of the second side; equal to A gives the autocorrelation, -1 means every photon. |
| Curve 3 | `corr_show3` | bool |  |  | Compute and draw this correlation curve. |
| Log lag axis | `corr_log_x` | bool |  |  | Logarithmic lag axis (the correlator bins are logarithmic). |
| Update every (snapshots) | `corr_every` | int |  | 1 … 1000 (step 1) | Redraw this plot only on every N-th published snapshot (a snapshot is one data chunk batch); raise it to spare the CPU on fast streams. |

### Count rate

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Curve 0 channel | `rate_ch0` | int |  | -1 … 4095 (step 1) | Routing channel whose count rate is drawn; -1 draws the sum over all channels. |
| Curve 0 | `rate_show0` | bool |  |  | Draw count-rate curve 0. |
| Curve 1 channel | `rate_ch1` | int |  | -1 … 4095 (step 1) | Routing channel whose count rate is drawn; -1 draws the sum over all channels. |
| Curve 1 | `rate_show1` | bool |  |  | Draw count-rate curve 1. |
| Curve 2 channel | `rate_ch2` | int |  | -1 … 4095 (step 1) | Routing channel whose count rate is drawn; -1 draws the sum over all channels. |
| Curve 2 | `rate_show2` | bool |  |  | Draw count-rate curve 2. |
| Curve 3 channel | `rate_ch3` | int |  | -1 … 4095 (step 1) | Routing channel whose count rate is drawn; -1 draws the sum over all channels. |
| Curve 3 | `rate_show3` | bool |  |  | Draw count-rate curve 3. |
| All channels | `rate_all_show` | bool |  |  | Draw the sum over all windows. |
| Log Y scale | `rate_log_y` | bool |  |  | Logarithmic rate axis. |
| Rolling window | `rate_rolling` | bool |  |  | Show only the most recent points; off shows the whole retained history. |
| Window size (points) | `rate_window` | int |  | 10 … 10000 (step 1) | Number of most recent count-rate points kept in the rolling window. |
| Binning (points per bin) | `rate_binning` | int |  | 1 … 100 (step 1) | Average this many consecutive points into one; the bin count shown is the window size divided by this. |
| Update every (snapshots) | `rate_every` | int |  | 1 … 1000 (step 1) | Redraw this plot only on every N-th published snapshot (a snapshot is one data chunk batch); raise it to spare the CPU on fast streams. |

### MCS

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width (ms) | `mcs_bin_width_ms` | float |  | 0.1 … 100.0 (step 0.1) | Width of one MCS intensity bin. Applied when the acquisition starts. |
| Rollaround (s) | `mcs_rollaround_s` | float |  | 0.01 … 100.0 (step 0.1) | Length of the displayed MCS window; older bins are dropped, which bounds memory. Applied when the acquisition starts. |
| Update every (snapshots) | `mcs_every` | int |  | 1 … 100 (step 1) | Redraw this plot only on every N-th published snapshot (a snapshot is one data chunk batch); raise it to spare the CPU on fast streams. |
| Manual Y range | `mcs_manual_y` | bool |  |  | Fix the counts axis to the limits below instead of fitting the data. |
| Y min | `mcs_y_min` | float |  | -1000000.0 … 1000000.0 (step 1.0) | Lower counts limit used with Manual Y range. |
| Y max | `mcs_y_max` | float |  | -1000000.0 … 1000000.0 (step 1.0) | Upper counts limit used with Manual Y range. |

### Macrotime

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show macrotime plot | `macro_show` | bool |  |  | Draw the macrotime plot. |
| Plot type | `macro_type` | choice |  | choices: dt, absolute | dt plots the inter-photon time against time; absolute plots the photon time stamps against photon index. |
| Update every (snapshots) | `macro_every` | int |  | 1 … 1000 (step 1) | Redraw this plot only on every N-th published snapshot (a snapshot is one data chunk batch); raise it to spare the CPU on fast streams. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `acq.simulation.run` | yes | Run the tttrlib Sim* photon simulator: Brownian diffusion of fluorophores through a confocal excitation focus, with N-state photophysics/FRET, rotational anisotropy and CW/pulsed emission, returning (or writing) the photon stream (macro-time window, routing channel, micro-time/TAC channel). Every parameter maps onto tttrlib's SimSystem / SimSpecies / SimGrid / SimIntegrator; this per-parameter help is the single source of truth shared by the GUI tooltips, the CLI, the Python API and this RPC method. Diffusion/rate/brightness units share one abstract MACRO-time unit (ChiSurf/BurstNet convention: milliseconds, so a rate of 1.0 = 1 kHz); the micro-time / TAC axis is a separate axis in nanoseconds. |

## Theory and workflow

- **Theory** — [Streaming analysis: computing on photons that have not arrived yet](/concepts/live_streaming_analysis.md)
- **Workflow** — [Live acquisition: watching a measurement while it happens](/guides/65_live_acquisition.md)

## Source

- Plugin package: `chisurf/plugins/core/acq/`
- Manifest: {src}`chisurf/plugins/core/acq/manifest.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/acq_emtk.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/live_plots.view.json`
