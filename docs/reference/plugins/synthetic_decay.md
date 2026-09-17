---
type: Plugin Reference
title: Synthetic Decay Generator
description: Generate synthetic TCSPC fluorescence-decay histograms from lifetimes/spectra (optional IRF convolution and Poisson shot noise) — the single canonical decay generator, exposed as API/CLI/RPC/GUI.
resource: chisurf/plugins/fluorescence_decay/synthetic_decay/
tags: [reference, plugins, synthetic-decay, spectroscopy, fluorescence-decay]
anchor: plugin-synthetic_decay
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-synthetic_decay)=
# Synthetic Decay Generator

Generate synthetic TCSPC fluorescence-decay histograms from lifetimes/spectra (optional IRF convolution and Poisson shot noise) — the single canonical decay generator, exposed as API/CLI/RPC/GUI.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `synthetic_decay` |
| Menu path | Spectroscopy → Fluorescence decay → **Synthetic Decay Generator** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `synthetic_decay` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Histogram

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bins | `n_bins` | int |  | 2 … 65535 | Number of micro-time (TAC) bins in the decay histogram. |
| Δt | `bin_width` | float |  | 0.0001 … 100.0 | Micro-time bin width in nanoseconds. |
| Start | `start_bin` | int |  | 0 … 65535 | Bin index where the ideal decay begins (prompt offset). |

### IRF & noise

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| IRF | `irf_path` | file |  |  | Optional instrument response function file (text or .npy) to convolve with the decay. Empty = ideal decay. |
| Noise | `shot_noise` | bool |  |  | Poisson-sample a finite-count observation (uses Photons + Seed). Off = normalized ideal pattern. |
| Photons | `photon_count` | float |  | 1.0 … 1000000000.0 | Total photon count for the Poisson observation. |
| Seed | `seed` | int |  | 0 … 2147483647 | Random seed for the shot-noise realization (reproducible). |

### Anisotropy

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `polarization` | choice |  | choices: vm, vv/vh | Detection mode. VM: magic angle — the decay carries no anisotropy. VV/VH: parallel and perpendicular channels generated with the rotation spectrum below; both share one photon budget when Noise is on. |

### VV/VH detection corrections

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| g | `g_factor` | float |  | 0.001 … 100.0 | Parallel/perpendicular detection sensitivity ratio G. The perpendicular channel records 1/G of what an equally sensitive one would. |
| l1 | `l1` | float |  | -10.0 … 10.0 | Polarization mixing factor of the parallel (VV) channel. |
| l2 | `l2` | float |  | -10.0 … 10.0 | Polarization mixing factor of the perpendicular (VH) channel. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `synthetic_decay.compute` | no | Generate a decay from lifetimes/amplitudes (+ optional IRF, shot noise). |
| `synthetic_decay.compute_component` | no | Generate a decay from a component definition (lifetime / spectrum / gaussian-lifetime / gaussian-distance). |
| `synthetic_decay.compute_aniso` | no | Generate a polarized VV/VH channel pair plus the anisotropy decay r(t) (g-factor, l1, l2 corrections; per-channel shot noise). |
| `synthetic_decay.compute_rt` | no | Ideal anisotropy r(t) from rotation rows on the decay time axis. |

## Theory and workflow

- **Theory** — [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/synthetic_decay/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/synthetic_decay/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/synthetic_decay/gui/synthetic_decay.view.json`
