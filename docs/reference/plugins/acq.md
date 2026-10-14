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

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Simulation mode | `simulation_mode` | bool |  |  | Use simulated BH card detection; turn this off to request physical-card detection. |
| Maximum photons | `max_photons` | int |  | 1000 … 10000000 | Photons after which the acquisition stops, 1,000 to 10,000,000. Press Enter or click elsewhere to commit; Apply makes it the acquisition's stop limit. |
| Species | `species` | int |  | 1 … 999 | Which species' decay is being edited. Switching keeps each species' edits; OK writes them all back. |
| Decay pattern file | `pattern_path` | str |  |  | Measured or saved decay pattern (.npy or text) that replaces the lifetimes for this species; empty = use the lifetimes. |
| Gaussian FWHM (ns) | `irf_fwhm_ns` | float |  | 0.0 … 1000.0 | Full width at half maximum of the Gaussian instrument response shared by all species; 0 = no IRF convolution. |

### CFD

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| CFD Limit Low (mV) | `CFD_LIMIT_LOW` | float |  | -1000 … 1000 | CFD Limit Low (mV), -1000 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| CFD Limit High (mV) | `CFD_LIMIT_HIGH` | float |  | -1000 … 1000 | CFD Limit High (mV), -1000 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| CFD Zero Cross Level (mV) | `CFD_ZC_LEVEL` | float |  | -100 … 100 | CFD Zero Cross Level (mV), -100 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| CFD Holdoff (ns) | `CFD_HOLDOFF` | float |  | 0 … 100 | CFD Holdoff (ns), 0 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |

### Sync

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Sync Zero Cross Level (mV) | `SYNC_ZC_LEVEL` | float |  | -100 … 100 | Sync Zero Cross Level (mV), -100 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Sync Frequency Divider | `SYNC_FREQ_DIV` | int |  | 1 … 16 | Sync Frequency Divider, 1 to 16 (a whole number). Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Sync Holdoff (ns) | `SYNC_HOLDOFF` | float |  | 0 … 100 | Sync Holdoff (ns), 0 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Sync Threshold (mV) | `SYNC_THRESHOLD` | float |  | -1000 … 1000 | Sync Threshold (mV), -1000 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |

### TAC

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TAC Range (ns) | `TAC_RANGE` | float |  | 0 … 1000 | TAC Range (ns), 0 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| TAC Gain | `TAC_GAIN` | choice |  | choices: 1, 2, 4, 8 | TAC Gain: one of the supported hardware values. Apply writes this choice to the selected BH module. |
| TAC Offset (%) | `TAC_OFFSET` | float |  | 0 … 100 | TAC Offset (%), 0 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| TAC Limit Low (%) | `TAC_LIMIT_LOW` | float |  | 0 … 100 | TAC Limit Low (%), 0 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| TAC Limit High (%) | `TAC_LIMIT_HIGH` | float |  | 0 … 100 | TAC Limit High (%), 0 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| TAC Enable Hold (ns) | `TAC_ENABLE_HOLD` | float |  | 0 … 100 | TAC Enable Hold (ns), 0 to 100. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |

### Timing

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Collection Time (s) | `COLLECT_TIME` | float |  | 0.001 … 1000 | Collection Time (s), 0.001 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Display Time (s) | `DISPLAY_TIME` | float |  | 0.001 … 1000 | Display Time (s), 0.001 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Repeat Time (s) | `REPEAT_TIME` | float |  | 0.001 … 1000 | Repeat Time (s), 0.001 to 1000. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Stop on Time | `STOP_ON_TIME` | choice |  | choices: 0, 1 | Stop on Time: one of the supported hardware values. Apply writes this choice to the selected BH module. |
| Stop on Overflow | `STOP_ON_OVFL` | choice |  | choices: 0, 1 | Stop on Overflow: one of the supported hardware values. Apply writes this choice to the selected BH module. |
| Rate Count Time (s) | `RATE_COUNT_TIME` | float |  | 0.001 … 10 | Rate Count Time (s), 0.001 to 10. Press Enter or click elsewhere to commit; Apply writes it to the selected BH module. |
| Macro Time Clock | `MACRO_TIME_CLK` | choice |  | choices: 0, 1, 2, 3, 4, 5, 6, 7 | Macro Time Clock: one of the supported hardware values. Apply writes this choice to the selected BH module. |

### Mode

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `MODE` | choice |  | choices: 0, 1, 2, 3 | Mode: one of the supported hardware values. Apply writes this choice to the selected BH module. |
| Routing Mode | `ROUTING_MODE` | choice |  | choices: 0, 1, 2 | Routing Mode: one of the supported hardware values. Apply writes this choice to the selected BH module. |
| ADC Resolution | `ADC_RESOLUTION` | choice |  | choices: 6, 8, 10, 12, 14, 16 | ADC Resolution: one of the supported hardware values. Apply writes this choice to the selected BH module. |

### Hardware acquisition

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Start counter index | `start_ctr` | int |  | 0 … 31 (step 1) | Start counter index, 0 to 31. Press Enter or click elsewhere to commit; Apply writes it to the BrickMic backend. |
| End counter index | `end_ctr` | int |  | 0 … 31 (step 1) | End counter index, 0 to 31. Press Enter or click elsewhere to commit; Apply writes it to the BrickMic backend. |
| Acquisition rate (Hz) | `acquisition_rate` | int |  | 1000 … 5000000 (step 100000) | Acquisition rate (Hz), 1,000 to 5,000,000. Press Enter or click elsewhere to commit; Apply writes it to the BrickMic backend. |
| Buffer size / channel | `buffer_size` | int |  | 10000 … 20000000 (step 100000) | Buffer size / channel, 10,000 to 20,000,000. Press Enter or click elsewhere to commit; Apply writes it to the BrickMic backend. |

### SPC file output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Photons per .spc file | `N_ph_per_file` | int |  | 1000 … 1000000000 (step 10000) | Photons per .spc file, 1,000 to 1,000,000,000. Press Enter or click elsewhere to commit; Apply writes it to the BrickMic backend. |

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

### Acquisition

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `excitation_mode` | choice |  | choices: CW, Pulsed | Excitation mode: CW (continuous) or Pulsed (pulsed laser; enables the micro-time / TCSPC axis). |
| Photons | `n_ph_max` | int |  | 1 … 2000000000 | Stop once this many photons are generated (fixed-COUNT mode, default 1e6; a training chunk is often ~1e5). For a fixed measurement DURATION set 'Max windows' > 0 instead (Independent-molecule mode requires that). |
| Photons/file | `n_ph_per_file` | int |  | 1 … 2000000000 | Split the streamed SPC output into files of this many photons each. |
| Output folder | `output_path` | str |  |  | Folder where SPC/photon-stream files are written. |
| Diffusion seed | `seed_diffusion` | int |  | 0 … | RNG seed for diffusion, geometry and state transitions. Fix it for reproducible traces; change it for independent replicates. |
| Emission seed | `seed_emission` | int |  | 0 … | RNG seed for emission, channel choice and background (independent of the diffusion seed). |

### Sample & brightness

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Species | `n_species` | int |  | 1 … 999 | Number of molecular / photophysical states (default 1). Brightness q, diffusion D and the N×N rate matrices are all sized by this. Use ≥2 for FRET states, species mixtures, or blinking (a bright + a dark state). |

### Geometry

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Box XY | `box_xy` | float |  | 0.001 … 1000000.0 | Lateral half-extent of the ellipsoidal simulation box (µm, default 2). Must exceed the focus by a few diffusion lengths; larger = more dilute but slower. Prefer 'Active margin' (Performance) to auto-shrink around the focus instead of a tiny box. |
| Box Z | `box_z` | float |  | 0.001 … 1000000.0 | Axial half-extent of the box (µm, default 4), usually ~2× box_xy for a prolate confocal volume. |
| Focus w0 | `focus_w0` | float |  | 0.001 … 1000000.0 | Excitation Gaussian 1/e² radii [w0 (lateral), z0 (axial)] in µm (default [0.3, 2.0]). Confocal: w0 ~0.2–0.4, aspect z0/w0 ~3–6. Field I ∝ exp(-2((x²+y²)/w0² + z²/z0²)). |
| Focus z0 | `focus_z0` | float |  | 0.001 … 1000000.0 | Excitation Gaussian 1/e² radii [w0 (lateral), z0 (axial)] in µm (default [0.3, 2.0]). Confocal: w0 ~0.2–0.4, aspect z0/w0 ~3–6. Field I ∝ exp(-2((x²+y²)/w0² + z²/z0²)). |
| Step | `dt` | float |  | 1e-06 … 1000000.0 | Diffusion/integration window in the macro-time unit (ms ⇒ 0.001 = 1 µs; default 0.01). Sets the diffusion resolution — do NOT enlarge it for speed (it is sub-stepped internally, so it won't help; use the Performance knobs instead). |

### Microtime

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TAC channels | `n_tac_channels` | int |  | 1 … 1000000 | Number of micro-time (TCSPC/TAC) channels on the fluorescence-decay axis (default 4096; match the instrument, typically 1024–4096). N_tac × tac_dt should span one laser period. |
| TAC dt | `tac_dt` | float |  | 1e-06 … 1000000.0 | Micro-time channel width in NANOSECONDS (the TAC/TCSPC resolution; default ≈0.004 ns). Separate ns axis from the macro-time. |
| Laser period | `laser_period` | float |  | 1e-06 … 1000000.0 | Pulsed-excitation repetition period in NANOSECONDS (default 13.596 ≈ 73.5 MHz). Micro-times wrap modulo this. Only relevant in Pulsed mode. |

### Performance

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Coasting | `per_molecule_skip` | bool |  |  | Coasting: a molecule far from BOTH the focus and the box surface skips its per-window diffusion/emission and is caught up EXACTLY on wake. Large speedup for dilute samples and statistically exact (±0.1%) — safe to leave on for FCS/smFRET. No effect during a scan. |
| Two-step field lookup | `fast_grid_bbox` | bool |  |  | Reject far-from-focus field queries with a cheap 6-comparison bounding-box test before the trilinear interpolation. Drops the sub-threshold field tail — a small, statistically unbiased approximation. Safe to leave on; biggest help with large voxel grids. |
| Independent molecules | `independent_molecules` | bool |  |  | Simulate each molecule's WHOLE timeline independently (coasting far, fine-stepping near the focus) and merge the streams — embarrassingly parallel across molecules (combine with worker threads). REQUIRES 'Max windows' > 0 (fixed duration) and IGNORES N_ph_max. Big throughput win for dilute samples. |
| Analytic Gaussian focus | `analytic_excitation` | bool |  |  | Evaluate the excitation Gaussian analytically instead of sampling a voxel grid: zero construction cost and memory, and exact — but for a GAUSSIAN focus only. Leave OFF to use the general voxel grid, which supports any measured / ISM / aberrated PSF. Turn on only when the focus is a clean 3D Gaussian. |
| PSF / focus model | `psf_type` | choice |  | choices: gaussian3d, analytic_gaussian3d, gaussian_lorentzian, radial | Point-spread / molecule-detection function for the excitation focus. 'gaussian3d' = separable 3D Gaussian (waists [w0, z0]); 'analytic_gaussian3d' = same Gaussian evaluated grid-free (zero build cost, exact, Gaussian only — equivalent to 'Analytic Gaussian focus'); 'gaussian_lorentzian' = confocal MDF with a z-expanding waist w(z)²=w0²(1+(z/zR)²) (uses w0 and the Rayleigh range zR); 'radial' = a numeric/measured radially-symmetric PSF loaded from a file (see 'PSF file'). |
| Rayleigh range zR (µm) | `psf_zR` | float |  | 0.0 … 1000000.0 | Rayleigh range zR (µm) for the Gaussian-Lorentzian PSF: the axial distance over which the beam waist expands by √2 (w(z)²=w0²(1+(z/zR)²)). Confocal ~0.5–1.5 µm. Only used when PSF model = 'gaussian_lorentzian'. |
| PSF file (radial) | `psf_file` | str |  |  | Path to a numeric/measured radially-symmetric PSF sampled on the (r, z) half-plane: .npy (2D [nz, nr] array), .npz ('rz' + steps), or .mat (PyBroMo). Only used when PSF model = 'radial'. The PSF is filled into the voxel grid by bilinear interpolation at r=√(x²+y²). |
| PSF r step (µm) | `psf_r_step` | float |  | 0.0 … 1000000.0 | Radial (r) sample spacing of the numeric PSF file, in µm. Only used for PSF model = 'radial' when not supplied by the file itself (.npz). |
| PSF z step (µm) | `psf_z_step` | float |  | 0.0 … 1000000.0 | Axial (z) sample spacing of the numeric PSF file, in µm. Only used for PSF model = 'radial' when not supplied by the file itself (.npz). |
| Active margin (µm) | `active_margin` | float |  | 0.0 … 1000000.0 | Shrink the simulated box to the focus AABB + this margin (µm), holding concentration fixed, so molecules that never reach the focus are never simulated (open-volume only; default 0 = off, ~7× faster at ~2 µm). Exact for diffusion/FCS. WARNING for INTERNAL KINETICS: the margin must exceed √(2·D / k_min) so a molecule reaches its stationary bright/dark distribution BEFORE entering the focus — too small biases brightness (measured up to +6% for a fast ~2–3 kHz blinker at 1.5 µm). |
| Max windows | `max_windows` | int |  | 0 … 2000000000 | Fixed-DURATION stop: measurement duration = max_windows × dt (0 = unlimited, default 0). e.g. 10 min at dt = 1 µs ⇒ 6e8 windows. REQUIRED by Independent-molecule mode, which then ignores N_ph_max. |
| Coast safety | `coast_safety` | float |  | 1.0 … 1000000.0 | How conservative coasting is: a sleeper's per-step displacement std ≤ (distance-to-boundary) / coast_safety (default 3; 3–4 typical). Larger = safer but slower. Only used when Coasting is on. |
| Min coast windows | `min_coast_windows` | int |  | 1 … 1000000 | Never sleep a molecule for fewer than this many windows (default 8) — avoids coasting overhead on short gaps. Only used when Coasting is on. |
| Focus threshold | `focus_threshold` | float |  | 0.0 … 1000000.0 | Fraction of peak excitation that defines the effective-focus bounding box shared by Coasting, the two-step lookup and the Active margin (default 1e-3). Smaller ⇒ a larger, more conservative focus box. |

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
- UI spec: {src}`chisurf/plugins/core/acq/gui/bh_setup.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/brickmic_setup.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/live_plots.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/picoquant_setup.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/sim_decay_emtk.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/sim_setup_emtk.view.json`
