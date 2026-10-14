---
type: Plugin Reference
title: Lazy Lifetime Analysis
description: Lazy Lifetime Analysis for TCSPC fluorescence decay data.
resource: chisurf/plugins/fluorescence_decay/lltf/
tags: [reference, plugins, lltf, spectroscopy, fluorescence-decay, decay]
anchor: plugin-lltf
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-lltf)=
# Lazy Lifetime Analysis

Lazy Lifetime Analysis for TCSPC fluorescence decay data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lltf` |
| Menu path | Spectroscopy → Decay → **Lazy Lifetime Analysis** |
| Categories | Spectroscopy, Fluorescence decay, Decay |
| Version | 1.0.0 |
| Surfaces | cli, emtk |
| State namespace | `lltf` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Input Files

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Data | `mode` | choice |  | choices: Magic angle, VV/VH | Magic angle: one decay. VV/VH: a polarization-resolved pair fitted jointly — shared lifetimes, an anisotropy decay r(t) and the G/l1/l2 calibration. The decay file is then a stacked VV/VH file (one column), a three-column file (time, VV, VH), or the VV channel with a separate VH file. |

### Fitting Options

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Number of Lifetimes | `n_lifetimes` | int |  | 1 … 6 (step 1) | Exponential components of the fit. Used when Find Optimal is off; it then also switches the configuration file's own find_optimal off. |
| Noise Model | `noise_model` | choice |  | choices: poisson, neyman | Objective of the fit. poisson (default): the Poisson deviance 2I*, unbiased; the decay must be raw photon counts. neyman: χ² weighted by the data, for curves that are not counts, but biased at low counts (3.0 + 4.5 ns comes back near 2.4 + 4.1 ns). Overrides the configuration's noise_model. |
| Find Optimal | `find_optimal` | bool |  |  | Find the optimal number of lifetimes: fit 1 … Max Lifetimes components and pick a count by the probability test. Read the χ²ᵣ sequence (Analysis Output, or optimal_fitting in the JSON) rather than taking the count as a verdict. |
| Max Lifetimes to Try | `max_lifetimes` | int |  | 2 … 6 (step 1) | Largest component count the search fits. |
| Probability Threshold | `prob_threshold` | float |  | 0.0 … 1.0 (step 0.01) | Probability a further component must reach to be kept: the F distribution's CDF of the extra-sum-of-squares F statistic of the χ² drop against the added parameters. |
| Verbose Output | `verbose` | bool |  |  | Print the fitter's progress and diagnostics in Analysis Output. |

### Anisotropy (VV/VH)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Rotations | `n_rotations` | int |  | 1 … 3 (step 1) | Rotational correlation times in r(t) = Σ b_j exp(−t/ρ_j); the lifetimes are counted separately (Number of Lifetimes / Find Optimal). |
| Residual anisotropy r∞ | `fit_r_inf` | bool |  |  | Add an anisotropy that does not decay (hindered rotation); r0 is then Σ b_j + r∞. |
| Override calibration | `override_calibration` | bool |  |  | Off: G, l1 and l2 come from the data (a vv_vh footer, the TTTR reader's anisotropy panel), else from the configuration's polarization_parameter; after a fit the greyed fields show the values used. On: the three values below are used. |
| G-factor | `g_factor` | float |  | 0.01 … 10.0 (step 0.01) | G = S∥/S⊥, the parallel/perpendicular detection sensitivity ratio; it divides the VH channel. The VV/VH G-Factor Calculator measures it. |
| l1 | `l1` | float |  | 0.0 … 0.3 (step 0.001) | Schaffer polarization mixing of the VV channel (high-aperture objective); 0 for an ideal polarizer. |
| l2 | `l2` | float |  | 0.0 … 0.3 (step 0.001) | Schaffer polarization mixing of the VH channel; 0 for an ideal polarizer. |

## Theory and workflow

- **Theory** — [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [The decay tools, Lazy Lifetime Analysis and synthetic decays](/guides/76_decay_analysis_tools.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/lltf/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/lltf/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/lltf/gui/lltf.view.json`
