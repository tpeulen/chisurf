(plugin-burst_irf_bg)=
# Burst IRF & Background

Extract a per-detector IRF and background rate from the non-burst photons of a single-molecule measurement, and feed them to the burst MLE lifetime fit.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_irf_bg` |
| Menu path | Spectroscopy → Single-Molecule → **Burst IRF & Background** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `burst_irf_bg` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  |  |
| Min photons/burst | `min_photons` | int |  | 2 … 100000 (step 5) | Burst-search minimum photons. Photons NOT in a burst are treated as background/scatter. |
| Photon window | `photon_window` | int |  | 2 … 10000 (step 1) | Sliding photon window used by the burst search to estimate the local count rate. |
| Time window (ms) | `time_window_ms` | float |  | 0.001 … 1000.0 (step 0.1) | Burst-search time window (ms). |
| Dark-count floor (quantile) | `baseline_quantile` | float |  | 0.0 … 0.9 (step 0.05) | Quantile of the non-burst micro-time histogram taken as the flat dark-count floor, subtracted before normalising the IRF. |
| Micro-time binning | `micro_time_binning` | int |  | 1 … 64 (step 1) | Micro-time coarsening for the MLE IRF/background patterns (match the burst-MLE binning). |

## Source

- Plugin package: `chisurf/plugins/burst/burst_irf_bg/`
- Manifest: {src}`chisurf/plugins/burst/burst_irf_bg/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_irf_bg/gui/irf_bg.view.json`
