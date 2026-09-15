---
type: Plugin Reference
title: Intensity trace
description: 'Intensity Trace Analysis for Single-Molecule Data This plugin provides tools for analyzing fluorescence intensity time traces from single-molecule experiments. It enables researchers to extract dynamic information from photon counting data, particularly for studying conformational changes, molecular interactions, and reaction kinetics at the single-molecule level. Features: - Loading and displaying Time-Tagged Time-Resolved (TTTR) data as intensity traces - Histogram analysis of photon counts with customizable binning - Hidden Markov Model (HMM) analysis for state detection and classification - Bayesian Information Criterion (BIC) calculation for optimal state number determination - Dwell time analysis for extracting kinetic information and rate constants - FRET efficiency calculation and state-specific distribution analysis - Transition probability matrix visualization and analysis - Exponential fitting of dwell time distributions - Interactive visualization with adjustable parameters - Support for multi-channel data analysis (donor/acceptor channels) The plugin implements a comprehensive workflow for single-molecule state analysis: 1. Load TTTR data and convert to binned intensity traces 2. Visualize traces and photon count distributions 3. Apply HMM to identify discrete states in noisy data 4. Analyze state transitions and dwell times to extract kinetic information 5. For FRET data, calculate efficiency distributions for each state Ideal for analyzing single-molecule FRET, protein folding/unfolding, enzyme dynamics, ligand binding, blinking behavior, or any other dynamic processes that can be observed in fluorescence intensity traces. The HMM approach is particularly powerful for detecting states in noisy data with overlapping distributions.'
resource: chisurf/plugins/tttr/intensity_trace/
tags: [reference, plugins, intensity-trace, spectroscopy, single-molecule]
anchor: plugin-intensity_trace
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-intensity_trace)=
# Intensity trace

Intensity Trace Analysis for Single-Molecule Data  This plugin provides tools for analyzing fluorescence intensity time traces from  single-molecule experiments. It enables researchers to extract dynamic information  from photon counting data, particularly for studying conformational changes,  molecular interactions, and reaction kinetics at the single-molecule level.  Features: - Loading and displaying Time-Tagged Time-Resolved (TTTR) data as intensity traces - Histogram analysis of photon counts with customizable binning - Hidden Markov Model (HMM) analysis for state detection and classification - Bayesian Information Criterion (BIC) calculation for optimal state number determination - Dwell time analysis for extracting kinetic information and rate constants - FRET efficiency calculation and state-specific distribution analysis - Transition probability matrix visualization and analysis - Exponential fitting of dwell time distributions - Interactive visualization with adjustable parameters - Support for multi-channel data analysis (donor/acceptor channels)  The plugin implements a comprehensive workflow for single-molecule state analysis: 1. Load TTTR data and convert to binned intensity traces 2. Visualize traces and photon count distributions 3. Apply HMM to identify discrete states in noisy data 4. Analyze state transitions and dwell times to extract kinetic information 5. For FRET data, calculate efficiency distributions for each state  Ideal for analyzing single-molecule FRET, protein folding/unfolding, enzyme dynamics, ligand binding, blinking behavior, or any other dynamic processes that can be  observed in fluorescence intensity traces. The HMM approach is particularly powerful for detecting states in noisy data with overlapping distributions.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `intensity_trace` |
| Menu path | Spectroscopy → Single-Molecule → **Intensity trace** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/intensity_trace/`
- Manifest: {src}`chisurf/plugins/tttr/intensity_trace/manifest.json`
