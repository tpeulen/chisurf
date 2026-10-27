---
type: Plugin Reference
title: Acquisition
description: 'Record single-molecule measurements with pulsed interleaved excitation and watch the E–S histogram build up live: bursts are searched, counted into DD/DA/AA and placed in E and S while the photons arrive, written to a PTU, and the run lands in the project (photons dataset with its burst run). Sources: the built-in tttrlib photon simulator (PIE smFRET with known E/S), replay of a workspace photon stream, and TCSPC hardware through the phacq library (native drivers for PicoQuant MultiHarp/PicoHarp 330/HydraHarp 500, Becker & Hickl SPC cards and the PicoQuant Sepia II laser; no vendor libraries).'
resource: chisurf/plugins/core/acq/
tags: [reference, plugins, acq, tools, views, acquisition]
anchor: plugin-acq
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-acq)=
# Acquisition

Record single-molecule measurements with pulsed interleaved excitation and watch the E–S histogram build up live: bursts are searched, counted into DD/DA/AA and placed in E and S while the photons arrive, written to a PTU, and the run lands in the project (photons dataset with its burst run). Sources: the built-in tttrlib photon simulator (PIE smFRET with known E/S), replay of a workspace photon stream, and TCSPC hardware through the phacq library (native drivers for PicoQuant MultiHarp/PicoHarp 330/HydraHarp 500, Becker & Hickl SPC cards and the PicoQuant Sepia II laser; no vendor libraries).

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

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| From | `settings_address` | choice |  | choices: `settings_options` | A settings file (⚙) or a measurement (⏱) of the workspace. Settings files enter ChiSurf through the drop, like every input. |

### Source

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `mode` | choice |  | choices: `mode_options` | Point: a single-molecule measurement at one spot -- bursts, E-S and the running trace. FCS: a point measurement for fluorescence correlation -- the correlation curve builds up live. Image: a scan -- the image builds up line by line from the scanner's markers, with fast-FLIM maps. |
| Source | `source_kind` | choice |  | choices: `source_options` | Where the photons come from: the simulator (a MultiHarp measuring a PIE smFRET sample with a known answer — its records go through the same device path as a real measurement), a photon stream from the Datasets workspace played back at measurement speed, or a PicoQuant device connected over USB. |
| Seed | `sim_seed` | int |  | 0 … 2147483647 (step 1) | Seeds diffusion and emission, so a run is reproducible. |
| Photon stream | `replay_address` | choice |  | choices: `photon_options` | A photons dataset of the Datasets workspace, played back at measurement speed. Drop the file on the ChiSurf window to add it. |
| Speed | `speed` | float |  | 0.1 … 100.0 (step 1.0) | How fast simulated or replayed photons arrive: 1 is the pace of the real measurement, 10 ten times faster. |

### Simulated molecules

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Excitation | `sim_scheme` | choice |  | choices: `scheme_options` | How the simulated sample is excited: PIE (a green and a red pulse per period, so stoichiometry is measured) or two colour (the green laser only). |
| Population 1: E | `sim_e_low` | float |  | 0.0 … 1.0 (step 0.05) | FRET efficiency of the first simulated population. Each molecule carries donor and acceptor; its photons are split into donor and acceptor channel by this E. |
| Population 2: E | `sim_e_high` | float |  | 0.0 … 1.0 (step 0.05) | FRET efficiency of the second simulated population. |
| Stoichiometry S | `sim_s` | float |  | 0.1 … 0.9 (step 0.05) | Stoichiometry of both populations: the share of donor-excited photons in all photons of a molecule (0.5 = equally bright under both lasers). |
| Concentration | `sim_concentration` | float |  | 0.1 … 20.0 (step 0.5) | Molecules of each population in the simulation box. Higher means more bursts per second, and more coincident molecules. |

### Simulated FCS sample

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Molecules in focus N | `fcs_n` | float |  | 0.05 … 200.0 (step 0.5) | Mean number of molecules in the focal volume (the inverse amplitude of the correlation curve). |
| D (µm²/s) | `fcs_d_um2_per_s` | float |  | 1.0 … 1000.0 (step 10.0) | Diffusion coefficient of the dye; with the simulated focus it sets the diffusion time. |
| Brightness (kHz) | `fcs_brightness_khz` | float |  | 1.0 … 2000.0 (step 10.0) | Photons per millisecond of one molecule at the focus centre. |

### Sample & instrument realism

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Preset | `realism_preset` | choice |  | choices: `realism_options` | Realistic: what a confocal smFRET measurement shows (donor-/acceptor-only molecules, bleaching, blinking, crosstalk, background, IRF, dead time). Ideal: everything off — the clean stream for teaching and exact tests. Editing a value makes it Custom. |
| Donor-only | `real_donor_only_fraction` | float |  | 0 … 1 (step 0.05) | Fraction of molecules without an active acceptor: an island at stoichiometry ≈ 1 and E ≈ 0. |
| Acceptor-only | `real_acceptor_only_fraction` | float |  | 0 … 1 (step 0.05) | Fraction of molecules without a donor: an island at stoichiometry ≈ 0. |
| Aggregates | `real_aggregate_fraction` | float |  | 0 … 0.1 (step 0.002) | Fraction of bright, slowly diffusing particles: rare bright spikes and long bursts. |
| Brightness spread | `real_brightness_cv` | float |  | 0 … 1 (step 0.05) | Molecule-to-molecule brightness spread (coefficient of variation): broadens burst sizes and the clusters. |
| Diffusion (µm²/s) | `real_diffusion_um2_per_s` | float |  | 1 … 1000 (step 10) | Translational diffusion coefficient; with the focus it sets the burst duration (80 µm²/s ≈ a 30 kDa protein). |
| γ | `real_gamma` | float |  | 0.1 … 5 (step 0.05) | Detection-efficiency × quantum-yield ratio of acceptor to donor. γ ≠ 1 shifts raw E; the corrected E uses it. |
| α (leakage) | `real_alpha` | float |  | 0 … 0.5 (step 0.01) | Donor emission leaking into the acceptor channel: raises raw E, most visibly for donor-only molecules. |
| δ (direct exc.) | `real_delta` | float |  | 0 … 0.5 (step 0.01) | Direct excitation of the acceptor by the donor laser (relative to its own laser): raises raw E. |
| Donor lifetime (ns) | `real_tau_donor_ns` | float |  | 0.5 … 10 (step 0.1) | Donor lifetime without FRET; a FRET population decays with τ_D (1 − E). |
| Acceptor lifetime (ns) | `real_tau_acceptor_ns` | float |  | 0.5 … 10 (step 0.1) | Acceptor lifetime: decay of the directly excited acceptor and the delay of sensitised emission. |
| IRF FWHM (ns) | `real_irf_fwhm_ns` | float |  | 0 … 2 (step 0.05) | Instrument response width, with a small exponential tail and per-detector timing jitter. |
| Background donor (kHz) | `real_background_donor_khz` | float |  | 0 … 20 (step 0.1) | Uncorrelated background of the donor detector (dark counts, ambient light), flat in micro time. |
| Background acceptor (kHz) | `real_background_acceptor_khz` | float |  | 0 … 20 (step 0.1) | Uncorrelated background of the acceptor detector. |
| Scatter (kHz) | `real_scatter_donor_khz` | float |  | 0 … 20 (step 0.1) | Scattered and Raman light of the donor laser in the donor detector: prompt window, instrument response only. |
| Afterpulsing | `real_afterpulse_probability` | float |  | 0 … 0.1 (step 0.001) | Probability that a detection repeats on the same detector shortly after (detector afterpulsing). |
| Dead time (ns) | `real_dead_time_ns` | float |  | 0 … 500 (step 5) | Detector dead time: a photon arriving within it after another is lost (count-rate saturation). |
| Acceptor bleaching (/ms) | `real_acceptor_bleach_per_ms` | float |  | 0 … 5 (step 0.01) | Acceptor photobleaching rate at the focus centre: bursts end as donor only — tails towards high S and low E. |
| Donor bleaching (/ms) | `real_donor_bleach_per_ms` | float |  | 0 … 5 (step 0.01) | Donor photobleaching rate at the focus centre: bursts end as acceptor only — tails towards low S. |
| Acceptor blinking (/ms) | `real_acceptor_blink_per_ms` | float |  | 0 … 20 (step 0.05) | Rate into the acceptor's dark state (it returns after ~0.2 ms): FRET drops for a while within a burst. |
| Drift (per min) | `real_drift_per_minute` | float |  | -0.5 … 0.5 (step 0.01) | Slow relative intensity change per minute (focus, laser power, evaporation). |

### TCSPC device

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Device | `device_index` | choice |  | choices: `device_options` | The PicoQuant devices connected over USB (driven through CMC's pqusb, without PicoQuant's libraries). Connect opens and initialises it in T3 mode. |
| Sync divider | `sync_div` | int |  | 1 … 16 (step 1) | Divides the laser's sync pulses. Keep 1 for PIE: the micro-time must span one full laser period, both pulses. |
| Sync level (mV) | `sync_level_mv` | int |  | -1200 … 1200 (step 10) | Trigger level of the sync input. |
| Sync edge | `sync_edge` | choice |  | choices: 0, 1 | Which edge of the sync signal triggers. |
| Sync offset (ps) | `sync_offset_ps` | int |  | -99999 … 99999 (step 100) | Shifts all micro-times; use it to place the prompt pulse at the start of the period. |
| Input level (mV) | `input_level_mv` | int |  | -1200 … 1200 (step 10) | Trigger level of the detector inputs (all inputs). |
| Input edge | `input_edge` | choice |  | choices: 0, 1 | Which edge of the detector pulses triggers (all inputs). |
| Donor input offset (ps) | `donor_offset_ps` | int |  | -99999 … 99999 (step 100) | Delay of the donor detector's input (the first donor channel of the setup), to align it with the acceptor's. |
| Acceptor input offset (ps) | `acceptor_offset_ps` | int |  | -99999 … 99999 (step 100) | Delay of the acceptor detector's input (the first acceptor channel of the setup). |
| Binning | `binning` | int |  | 0 … 24 (step 1) | T3 micro-time bin width = base resolution x 2^binning. |
| Offset (ns) | `offset_ns` | int |  | 0 … 100000000 (step 1) | T3 offset of the micro-time window (ns). |

### Laser

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Laser | `laser_kind` | choice |  | choices: `laser_options` | Auto uses the Sepia II driver when its library is installed, else the simulated laser. Why Sepia II is not available is shown on the status line. |

### Program

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Divider | `laser_divider` | int |  | 1 … 65535 (step 1) | The oscillator's base frequency is divided by this to give the pulse rate the sequencer distributes. |

### Experiment setup

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Instrument setup | `setup_address` | choice |  | choices: `setup_options` | Which detector is donor and which acceptor, and the excitation windows: a setup row of the Datasets workspace (drop a detector setup JSON on the window), or the default for the measurement type — routing channel 0 donor, 1 acceptor; PIE splits the laser period into prompt and delay halves. A setup with gamma, beta, alpha and delta gives corrected FRET efficiency and stoichiometry. |
| Measurement type | `preset` | choice |  | choices: `preset_options` | How the setup is read: single colour, two colour, PIE, µs-ALEX, MFD or three-colour PIE. 'From the setup' takes the type the setup describes. The type decides the quantities (proximity ratio, stoichiometry, anisotropy), the live histograms and which quality checks apply. |
| Alternation period (µs) | `alex_period_us` | float |  | 1.0 … 10000.0 (step 10.0) | µs-ALEX only: the laser alternation period; the first half excites the donor, the second the acceptor. |
| Minimum photons | `min_photons` | int |  | 5 … 10000 (step 5) | A burst needs at least this many photons (L). |
| Window photons | `window_photons` | int |  | 2 … 1000 (step 1) | The sliding window: this many consecutive photons (m) ... |
| Window time (ms) | `window_time_ms` | float |  | 0.01 … 100.0 (step 0.05) | ... arriving within this time (T) belong to a burst. The same criterion as Burst Selection's sliding-window search, so the run can be re-analysed offline with identical bursts. |

### Running trace

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Span (s) | `trace_window_s` | float |  | 0.01 … 600.0 (step 0.5) | How many seconds the running trace shows: the most recent ones, scrolling. Default 1 s. |
| Bin (ms) | `trace_bin_ms` | float |  | 0.01 … 1000.0 (step 0.5) | Bin width of the running trace. Default 1 ms (bursts last a few ms). |

### Raster

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pixels x | `scan_pixels_x` | int |  | 1 … 4096 (step 8) | Pixels per line. |
| Pixels y | `scan_pixels_y` | int |  | 1 … 4096 (step 8) | Lines per frame. |
| Width (µm) | `scan_area_x_um` | float |  | 0.01 … 1000.0 (step 1.0) | The scanned width; a pixel is width / pixels wide. |
| Height (µm) | `scan_area_y_um` | float |  | 0.01 … 1000.0 (step 1.0) | The scanned height. |
| Dwell (ms) | `scan_dwell_ms` | float |  | 0.001 … 100.0 (step 0.01) | Time on one pixel. A line takes pixels x dwell; the line rate follows. |
| Frames | `scan_frames` | int |  | 1 … 10000 (step 1) | Frames per plane; their photons add up in the live image. |
| Bidirectional | `scan_bidirectional` | bool |  |  | Odd lines are scanned right to left (faster; needs a well-aligned scanner). |
| Z planes | `scan_z_planes` | int |  | 1 … 1000 (step 1) | Planes of a z stack (1: one plane). |
| Z step (µm) | `scan_z_step_um` | float |  | 0.01 … 100.0 (step 0.1) | Distance between the planes of a z stack. |

### Simulated sample

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Beads | `img_beads` | int |  | 0 … 500 (step 1) | Bright beads on the dim outline of a cell; half of them with each lifetime. |
| τ₁ (ns) | `img_tau_1_ns` | float |  | 0.05 … 20.0 (step 0.1) | Lifetime of the first bead kind (mostly on detector 0). |
| τ₂ (ns) | `img_tau_2_ns` | float |  | 0.05 … 20.0 (step 0.1) | Lifetime of the second bead kind (mostly on detector 1). |
| Brightness | `img_brightness` | float |  | 0.1 … 10000.0 (step 5.0) | Photon rate of one emitter at the focus centre (a bead is a few emitters). Too bright piles up: watch the Pile-up light. |

### Run

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Duration (s) | `duration_s` | float |  | 0.0 … 86400.0 (step 10.0) | Stop after this much measurement time; 0 measures until you press Stop. |
| Name | `run_name` | str |  |  | The recording's name: its file in the project's recordings folder and its row in Datasets. |
| Store photons | `recording_store` | choice |  | choices: `store_options` | Embed (default): the photons are stored inside the project's .cs.pto when the run stops, so the project carries its data. Link: the project records the file's path and checksum only. Written beside the project while measuring, so a crash leaves the photons on disk. |

### Histogram

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Histogram | `plot_choice` | choice |  | choices: `plot_options` | Which of the measurement type's histograms to show: E–S (with its marginals) for PIE and ALEX, the proximity ratio for two colour, anisotropy and proximity ratio for MFD, burst size and duration for a single colour. |

### Image

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Map | `image_map` | choice |  | choices: `image_map_options` | Which map: intensity (all detectors), mean arrival time (fast FLIM), a single detector, or a micro-time window (PIE). |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Species | `species` | int |  | 1 … 999 | Which species' decay is being edited. Switching keeps each species' edits; OK writes them all back. |
| Decay pattern file | `pattern_path` | str |  |  | Measured or saved decay pattern (.npy or text) that replaces the lifetimes for this species; empty = use the lifetimes. |
| Gaussian FWHM (ns) | `irf_fwhm_ns` | float |  | 0.0 … 1000.0 | Full width at half maximum of the Gaussian instrument response shared by all species; 0 = no IRF convolution. |

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
- **Workflow** — [TTTR simulation of diffusing particles](/guides/18_tttr_simulation.md), [Live acquisition: watching a measurement while it happens](/guides/65_live_acquisition.md)

## Source

- Plugin package: `chisurf/plugins/core/acq/`
- Manifest: {src}`chisurf/plugins/core/acq/manifest.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/live_plots.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/record.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/sim_decay_emtk.view.json`
- UI spec: {src}`chisurf/plugins/core/acq/gui/sim_setup_emtk.view.json`
