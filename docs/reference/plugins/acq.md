---
type: Plugin Reference
title: Acquisition
description: 'Single-molecule fluorescence acquisition: stream photons from real TCSPC hardware or the built-in tttrlib Sim* photon simulator (confocal diffusion with FRET, anisotropy and photophysics).'
resource: chisurf/plugins/core/acq/
tags: [reference, plugins, acq, main, tools, acquisition]
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
| Menu path | Main → Tools → **Acquisition** |
| Categories | Main, Tools, Acquisition |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `acq` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `acq.simulation.run` | yes | Run the tttrlib Sim* photon simulator: Brownian diffusion of fluorophores through a confocal excitation focus, with N-state photophysics/FRET, rotational anisotropy and CW/pulsed emission, returning (or writing) the photon stream (macro-time window, routing channel, micro-time/TAC channel). Every parameter maps onto tttrlib's SimSystem / SimSpecies / SimGrid / SimIntegrator; this per-parameter help is the single source of truth shared by the GUI tooltips, the CLI, the Python API and this RPC method. Diffusion/rate/brightness units share one abstract MACRO-time unit (ChiSurf/BurstNet convention: milliseconds, so a rate of 1.0 = 1 kHz); the micro-time / TAC axis is a separate axis in nanoseconds. |

## Source

- Plugin package: `chisurf/plugins/core/acq/`
- Manifest: {src}`chisurf/plugins/core/acq/manifest.json`
