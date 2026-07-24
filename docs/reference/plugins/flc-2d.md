(plugin-flc-2d)=
# 2D-FLCS

Two-dimensional fluorescence lifetime correlation spectroscopy (2D-FLCS): build 2D fluorescence-decay correlation maps from TTTR photon streams and resolve lifetime species and exchange dynamics.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `flc-2d` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **2D-FLCS** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `flc_2d` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### 2D-FDC

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| lag | `dT_ms` | float |  | 0.0 … 1000000.0 (step 0.1) | Macro-time lag dT at which the 2D fluorescence-decay correlation is built. Pick a value within the dynamics timescale to see lifetime cross-peaks. |
| win | `ddT_ms` | float |  | 0.0 … 1000000.0 (step 0.1) | Half-width of the macro-time lag window (ddT). Wider = more photon pairs but coarser lag resolution. |
| tmin | `tmin_ns` | float |  | 0.0 … 1000.0 | Lower micro-time gate (ns) for the decay axis. |
| tmax | `tmax_ns` | float |  | 0.0 … 1000.0 | Upper micro-time gate (ns) for the decay axis. |
| bins | `max_bins` | int |  | 16 … 256 | Block-rebin the 2D-FDC down to this many bins before inversion (speed vs resolution). |

### Lifetime inversion

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| method | `fit_mode` | choice |  | choices: tikhonov, nnls, mem | Inverse-Laplace solver: Tikhonov (closed-form, fastest), NNLS (strict non-negativity, default), or maximum-entropy (faithful, slower). |
| grid | `n_components` | int |  | 4 … 80 | Number of log-spaced trial lifetimes in the inversion basis. |
| τmin | `tau_min_ns` | float |  | 0.01 … 100.0 (step 0.1) | Smallest trial lifetime (ns). |
| τmax | `tau_max_ns` | float |  | 0.1 … 1000.0 (step 0.5) | Largest trial lifetime (ns). |
| log λ | `log10_reg` | float |  | -12.0 … 6.0 (step 0.5) | Regularisation as log10(reg); 0 selects it automatically by L-curve. |

### IRF

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| source | `irf_mode` | choice |  | choices: synthetic, detect, file, none | How the IRF used for lifetime deconvolution is obtained. Synthetic = Gaussian pulse; Detect = place a synthetic pulse at the decay's prompt rise; File = IRF opened via 📈 Open IRF; None = tail-fit without an IRF. |
| center | `irf_center_ns` | float |  | 0.0 … 100.0 (step 0.05) | Centre (prompt position) of the synthetic IRF in ns. Ignored for Detect/File/None. |
| FWHM | `irf_fwhm_ns` | float |  | 0.001 … 10.0 (step 0.02) | Full width at half maximum of the synthetic IRF (ns). |
| skew | `irf_shape` | float |  | -2.0 … 2.0 (step 0.1) | Skewness of the synthetic IRF pulse (0 = symmetric Gaussian). |
| rise | `irf_rise_scan` | bool |  |  | When running the 1D-MEM, scan the IRF rise position and average the distributions around the optimum (port of TK_MyMain_Search_RiseIRF_1DMEM); reduces the IRF-timing systematic. |

### Dynamics

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| corr | `compute_dynamics` | bool |  |  | After resolving the lifetimes, compute the species-resolved (lifetime-filtered) correlation and fit the interconversion relaxation time + rate matrix. |
| cascades | `n_casc` | int |  | 1 … 40 | Multi-tau cascades for the filtered correlation. |

### Kinetics (advanced)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| gMEM | `run_global_mem` | bool |  |  | Build 2D-FDCs at several lags and jointly invert them with one shared lifetime distribution (global multi-lag 2D-MEM). Advanced; state separation is ill-conditioned for equal-brightness data. |
| lags | `n_lags` | int |  | 2 … 24 | Number of macro-time lags for the global multi-lag MEM / kinetics scan. |

### 1D-MEM + Gaussian

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| run | `run_1d_mem` | bool |  |  | Also build the 1D-FDC (zero-lag decay coincidence) and fit it with the explicit maximum-entropy method ported from the MATLAB toolbox, then decompose the distribution into Gaussian lifetime components. |
| λ | `mem_reg` | float |  | 0.1 … 100000.0 (step 5.0) | Initial MEM regulator (RegulatorConst). Larger = smoother; the schedule relaxes it over outer iterations. |
| prior | `mem_mi_type` | choice |  | choices: 0, 1, 2, 3 | Entropy prior model (mi) ported from TK_mi_ModelFunction: 0 flat (resolution-weighted), 1 self (current dist.), 2 blend, 3 Gaussian. |
| peaks | `gaussian_components` | int |  | 1 … 6 | Number of Gaussian lifetime components to fit to the MEM distribution. |

### Simulator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| τ₁ | `sim_tau1_ns` | float |  | 0.01 … 100.0 (step 0.1) | Fluorescence lifetime of state 1 (ns). |
| τ₂ | `sim_tau2_ns` | float |  | 0.01 … 100.0 (step 0.1) | Fluorescence lifetime of state 2 (ns). |
| k₁₂ | `sim_k12` | float |  | 0.0 … 1000000.0 (step 1.0) | Transition rate state 1 → 2 (1/s). |
| k₂₁ | `sim_k21` | float |  | 0.0 … 1000000.0 (step 1.0) | Transition rate state 2 → 1 (1/s). |
| cps | `sim_intensity_cps` | float |  | 1.0 … 100000000.0 (step 1000.0) | Per-state brightness in counts per second (equal for both states). |
| time | `sim_time_s` | float |  | 0.1 … 100000.0 (step 10.0) | Acquisition time to simulate (s). Use the Sim button to generate and load the stream. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `flc2d.load_tttr` | yes | Load TTTR metadata and optionally photon arrays. |
| `flc2d.correlate` | yes | Build a 2D-FDC matrix from TTTR macro/micro times. |
| `flc2d.fit` | yes | Fit a 2D-FDC matrix to lifetime species. |
| `flc2d.lifetime_spectrum` | yes | Resolve a 1D lifetime spectrum from microtimes. |
| `flc2d.lifetime_lcurve` | yes | Compute 1D lifetime inversion L-curve diagnostics. |
| `flc2d.contract.describe` | no | Describe the 2D-FLCS RPC namespace. |

## Source

- Plugin package: `chisurf/plugins/fcs/flc_2d/`
- Manifest: `chisurf/plugins/fcs/flc_2d/manifest.json`
- UI spec: `chisurf/plugins/fcs/flc_2d/gui/flc_2d.view.json`
