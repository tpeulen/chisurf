(plugin-burst_fcs_correlator)=
# Burst-wise FCS

Compute fluorescence correlation functions on a per-burst basis from Burst-ID (.bst) / BUR files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_fcs_correlator` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **Burst-wise FCS** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_fcs_correlator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Correlator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| FCS bins (B) | `n_bins` | int |  | 1 … 65535 | Number of linear correlation bins per cascade. |
| cascades | `n_casc` | int |  | 1 … 64 | Number of multi-tau cascades (n_casc). |
| Fine grid | `make_fine` | bool |  |  | Use the fine (micro-time-resolved) correlation grid. |
| Padding ±[ms] | `padding_ms` | float |  | 0.0 … 1000000.0 (step 0.1) | Photon time padding added around each burst before correlation. |

### Fitting

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `fit_mode` | choice |  | choices: none, simple, maxent | Per-curve fit: none, single-component diffusion, or MaxEnt distribution. |
| MaxEnt reg (log10) | `maxent_log10_reg` | float |  | -12.0 … 6.0 (step 0.5) | MaxEnt regularisation strength as log10(reg). |
| τ_D min [ms] | `maxent_td_min` | float |  | 0.0 … 1000000.0 | Lower diffusion-time bound for the MaxEnt grid (0 = auto). |
| τ_D max [ms] | `maxent_td_max` | float |  | 0.0 … 1000000000.0 | Upper diffusion-time bound for the MaxEnt grid (0 = auto). |
| t_min [ms] | `tmin_fit` | float |  | 0.0 … 1000000000.0 | Lower correlation-time bound of the fit window (0 = full). |
| t_max [ms] | `tmax_fit` | float |  | 0.0 … 1000000000.0 | Upper correlation-time bound of the fit window (0 = full). |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_fcs.parse_bst` | no | Parse a Burst-ID .bst file into TTTR path + burst ranges. |
| `burst_fcs.parse_bur` | no | Parse a BUR file into TTTR path + burst ranges. |
| `burst_fcs.fit_curve` | no | Fit a correlation curve (simple/MaxEnt) per settings. |
| `burst_fcs.fit_diffusion` | no | MaxEnt diffusion-time summary of a correlation curve. |
| `burst_fcs.fit_simple` | no | Single-component diffusion-time fit of a correlation curve. |
| `burst_fcs.correlate_file` | yes | Correlate every burst x pair for one TTTR file. |

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [FRET-FCS](/guides/16_fret_fcs.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_fcs_correlator/`
- Manifest: {src}`chisurf/plugins/burst/burst_fcs_correlator/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_fcs_correlator/gui/burst_fcs.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_fcs_correlator/gui/burst_fcs_plots.view.json`
