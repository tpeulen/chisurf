---
type: Plugin Reference
title: Correlator
description: 'This plugin provides a two-pane navigation-based correlator tool for computing and merging fluorescence correlation spectroscopy (FCS) data. Features include:'
resource: chisurf/plugins/fcs/fcs_correlator/
tags: [reference, plugins, fcs-correlator]
anchor: plugin-fcs_correlator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_correlator)=
# Correlator

This plugin provides a two-pane navigation-based correlator tool for computing and merging fluorescence correlation spectroscopy (FCS) data. Features include:

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_correlator` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **Correlator** |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Correlation Channels

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Ch A | `channel_a` | str |  |  | Comma or space-separated detector routing channels for channel A. |
| Ch B | `channel_b` | str |  |  | Comma or space-separated detector routing channels for channel B. |
| µt A | `microtime_range_a` | str |  |  | Semicolon-separated microtime ranges for channel A: start-end;start-end. |
| µt B | `microtime_range_b` | str |  |  | Semicolon-separated microtime ranges for channel B: start-end;start-end. |

### Correlation Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bins | `n_bins` | int |  | 1 … 65535 | Number of linear correlation bins per cascade. |
| Cascades | `n_casc` | int |  | 1 … 64 | Number of multi-tau cascades. |
| Splits | `n_splits` | int |  | 1 … 128 | Number of chunks to split data into for block averaging. |
| Fine | `make_fine` | bool |  |  | Use the micro-time-resolved correlation grid. |
| µt bin | `microtime_binning` | choice |  | choices: 1, 2, 4, 8, 16 | Micro-time binning factor for fine correlation. |

### Channel selection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Channels | `channel_numbers` | str |  |  | Detector routing channels to keep (comma/space separated; empty = all). |
| µt range | `microtime_range` | str |  |  | Micro-time range(s) to keep, e.g. 0-2048;2048-4095. |

### Macro time interval

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| min dMT (ms) | `min_dmt` | float |  | 0.0 … 100000.0 | Lower inter-photon-time threshold. |
| use min | `use_min` | bool |  |  | Apply the lower dMT threshold. |
| max dMT (ms) | `max_dmt` | float |  | 0.0 … 100000.0 | Upper inter-photon-time threshold; also the burst/count-rate time window. |
| use max | `use_max` | bool |  |  | Apply the upper dMT threshold. |

### Filter

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `filter_mode` | choice |  | choices: burst, count_rate, bocpd, kalman, cusum | burst / count-rate thresholding, or change-point burst detection (BOCPD / Kalman / CUSUM). |
| enable | `filter_enabled` | bool |  |  | Apply the burst/count-rate filter (channel/µt/dMT selections always apply). |
| Min photons | `min_ph` | int |  | 1 … 100000 | Minimum photons per burst (burst) / max photons in window (count-rate). |
| Photon window | `cr_tw` | int |  | 1 … 100000 | Number of photons over which the local count rate is computed (burst mode). |
| invert | `invert` | bool |  |  | Invert the selection (keep the rejected photons). |

### Change-point parameters (BOCPD / Kalman / CUSUM)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Trace bin (ms) | `trace_bin_width` | float |  | 0.001 … 10000.0 | Bin width for the binned-intensity trace used by BOCPD/Kalman. |
| Fill gaps | `use_gap_fill` | bool |  |  | Merge selected segments separated by up to 'Max gap' photons. |
| Max gap | `max_gap` | int |  | 0 … 100000 | Maximum gap (photons) bridged when filling gaps. |
| BOCPD prior count | `bocpd_prior_count` | float |  | 0.0 … 100000.0 | Prior photon count for the BOCPD Gamma prior. |
| BOCPD prior dur | `bocpd_prior_duration` | float |  | 0.0 … 100000.0 | Time window assumed for the BOCPD prior count. |
| BOCPD cp prob | `bocpd_changepoint_prob` | float |  | 0.0 … 1.0 | Probability of a burst start in any bin (BOCPD). |
| Kalman Q | `kalman_q` | float |  | 0.0 … 100000.0 | Process-noise parameter (Kalman). |
| Kalman R scale | `kalman_r_scale` | float |  | 0.0 … 100000.0 | Measurement-noise scaling (Kalman). |
| Kalman z-thresh | `kalman_z_thresh` | float |  | 0.0 … 100000.0 | Burst-detection threshold (Kalman). |
| Kalman min len | `kalman_min_len` | int |  | 1 … 100000 | Minimum burst length in bins (Kalman). |
| Kalman merge gap | `kalman_merge_gap` | int |  | 0 … 100000 | Maximum gap between bursts to merge (Kalman). |
| CUSUM bg rate | `cusum_bg_rate` | float |  | 0.0 … 1000000.0 | Background rate (CUSUM). |
| CUSUM s/b ratio | `cusum_sb_ratio` | float |  | 0.0 … 100000.0 | Signal-to-background ratio (CUSUM). |
| CUSUM alpha | `cusum_alpha` | float |  | 0.0 … 1.0 | False-alarm probability (CUSUM). |
| CUSUM beta | `cusum_beta` | float |  | 0.0 … 100000.0 | Missed-detection parameter (CUSUM). |

### Plot settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| MCS bin (ms) | `mcs_bin_width` | float |  | 0.001 … 10000.0 | Bin width of the count-rate trace. |
| Range lo | `range_lo` | int |  | 0 … 1000000000 | First photon index shown in the dT plot. |
| Range hi | `range_hi` | int |  | 0 … 1000000000 | Last photon index shown in the dT plot (0 = all). |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Folder | `folder_path` | str |  |  | Folder containing .cor or .json.gz correlation chunk files. |

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [Diffusion FCS](/guides/09_diffusion_fcs.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_correlator/`
- UI spec: {src}`chisurf/plugins/fcs/fcs_correlator/correlator.view.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_correlator/filter.view.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_correlator/merger.view.json`
