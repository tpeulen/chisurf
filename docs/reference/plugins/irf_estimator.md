---
type: Plugin Reference
title: IRF Estimation
description: Blind IRF estimation from fluorescence decay data using truncated exponential fitting and Richardson-Lucy deconvolution.
resource: chisurf/plugins/fluorescence_decay/irf_estimator/
tags: [reference, plugins, irf-estimator, spectroscopy, fluorescence-decay, decay]
anchor: plugin-irf_estimator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-irf_estimator)=
# IRF Estimation

Blind IRF estimation from fluorescence decay data using truncated exponential fitting and Richardson-Lucy deconvolution.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `irf_estimator` |
| Menu path | Spectroscopy → Decay → **IRF Estimation** |
| Categories | Spectroscopy, Fluorescence decay, Decay |
| Version | 2.0.0 |
| Surfaces | cli, emtk, services |
| State namespace | `irf_estimator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Time/Channel (ns) | `dt` | float |  | 0.001 … 10.0 (step 0.01) | Time per channel in nanoseconds, set from the data. Correct it when the file carries none: the time axis, lifetime and rate are rescaled, the IRF per channel is unchanged. |
| Source | `source` | choice |  | choices: `source_choices` | What the loaded decay is, and so how the IRF is taken from it. Blind: a fluorescence decay; its tail is fitted with a truncated exponential and deconvolved (Richardson-Lucy). Reference dye: a dye of one known lifetime (Rh110, Alexa647); its polarised exponential is deconvolved, the lifetime fitted to its tail, the rotation read from VV and VH. Scatter: water or Ludox; the prompt is the IRF after the floor (and a buffer). Non-burst (the photons outside the bursts): a Gaussian fitted to the scatter prompt's rising edge, leaving the fluorescent tail behind. Burst MLE takes its IRF from the same extraction. |
| VV \| VH halves | `vv_vh` | bool |  |  | The data holds two halves, VV then VH, each extracted on its own; a reference dye's rotation is read from them. Off: one curve (deconvolved with the plain exponential). |
| Lifetime (ns) | `reference_tau_ns` | float |  | 0.0 … 50.0 (step 0.01) | The reference dye's lifetime. 0: fitted to the tail of VV + 2 VH (the listed lifetime when that fails or is more than a factor two off). |
| Listed (ns) | `listed_tau_ns` | float |  | 0.0 … 50.0 (step 0.1) | The dye's lifetime as listed (reference_dyes.yaml: Rh110 4.0 ns, Alexa647 1.0 ns): the check on the fitted one. |
| ρ (ns) | `reference_rho_ns` | float |  | 0.0 … 20.0 (step 0.01) | The dye's rotational correlation time. 0: read from the data (the time at which the IRFs of VV and VH have one shape). Needs VV \| VH halves. |
| IRF model | `irf_model` | choice |  | choices: `irf_model_choices` | The pulse fitted to the prompt of the photons outside the bursts. Gaussian or Skewed Gaussian leave the fluorescent tail behind; Measured keeps the floor-free prompt as measured. |
| SG Window Length | `window_length` | int |  | 5 … 500 (step 2) | Savitzky-Golay filter window length (channels) used to find the decay maximum; the estimator makes it odd. |
| SG Poly Order | `polyorder` | int |  | 1 … 10 (step 1) | Polynomial order of the Savitzky-Golay filter. |
| RL Iterations | `rl_iterations` | int |  | 5 … 2000 (step 10) | Richardson-Lucy deconvolution iterations. More iterations sharpen the IRF and amplify noise: where you stop is the regularisation. Auto-update uses 50. |
| Regularization | `regularization` | int |  | 1 … 51 (step 2) | Median filter size for regularization (1 = no regularization). |
| Manual Background | `manual_background` | float |  | 0.0 … 100000.0 (step 1.0) | Background counts per channel subtracted before the estimate (0 = auto-estimate). Loading a file sets it to the median of the last 10 % of channels. |
| 📍  Use Range Selection | `use_range_selection` | bool |  |  | Use only a channel range for the estimate: drag the green region in the plot or type its first and last channel. |
| 🔄  Auto-Update IRF | `auto_update_enabled` | bool |  |  | Re-estimate the IRF (50 RL iterations) when a parameter, the background or the range changes, once an IRF exists. |
| First channel | `first_channel` | int |  | 0 … 100000 (step 1) | First channel of the estimation range (inclusive). |
| Last channel | `last_channel` | int |  | 0 … 100000 (step 1) | Last channel of the estimation range (inclusive). |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `irf_estimator.jobs.estimate` | yes | Run IRF estimation on loaded decay data. |
| `irf_estimator.data.load_decay` | no | Load a VV/VH format decay file. |
| `irf_estimator.data.load_dataset` | no | Load decay data from a ChiSurf dataset. |
| `irf_estimator.data.save_irf` | no | Save estimated IRF to a VV/VH file. |
| `irf_estimator.data.transfer_irf` | no | Transfer estimated IRF to ChiSurf as a dataset. |
| `irf_estimator.contract.describe` | no | Return the IRF Estimator workflow contract. |

## Theory and workflow

- **Theory** — [Extracting the instrument response](/concepts/irf_extraction.md), [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [IRF estimation](/guides/irf_estimation.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/irf_estimator/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/irf_estimator/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/irf_estimator/gui/irf_estimator_emtk.view.json`
