# Plugin catalogue

Every discoverable ChiSurf plugin, grouped by its menu category. Each page gives the plugin's identity, its editable parameters, and its JSON-RPC surface.

Of the **100 plugins**, **42** build their interface from declarative AutoForm specs and get a full per-parameter table on their page; the remainder use custom Qt widgets, so their controls are described in each plugin's guide while every named fit/model parameter is defined once in the **[parameter glossary](../parameters.md)**.

```{toctree}
:hidden:
:glob:

*
```

**100 plugins** across 25 categories.

## Core

| Plugin | Summary |
| --- | --- |
| [Database Connector](database_connector.md) | Core database connector services for source/user database resolution, migration, backup, reset, repository access, and FLR CIF import/export. |

## Help

| Plugin | Summary |
| --- | --- |
| [Boarding Wizard](boarding.md) *(hidden)* | Startup onboarding wizard for first-run ChiSurf configuration. |
| [Documentation](help.md) | Documentation browser and help resource viewer for ChiSurf. |

## Imaging

| Plugin | Summary |
| --- | --- |
| [CLSM-Draw](clsm.md) *(hidden)* | Create CLSM-TTTR image representations, select pixels interactively, and export fluorescence-decay histograms. |
| [Colocalization](img_coloc.md) | Two-channel colocalization (Pearson, Manders, Costes, Li ICQ) on TIFF stacks and photon-stream images, with an interactive intensity scatter gate. |
| [IRF & BG](img_calibration.md) *(hidden)* | Per-detector IRF file and background (kHz) calibration; transferred to phasor and pixel-wise MLE. Optional (skippable) pipeline step. |
| [Intensity](img_pixel_intensity.md) *(hidden)* | Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference) that N&B / phasor / MLE enrich. |
| [Mean Micro-Time](img_pixel_micro_time.md) *(hidden)* | Per-pixel mean micro-time (arrival time) maps from TTTR imaging data. |
| [Number & Brightness](img_pixel_nb.md) *(hidden)* | Per-pixel Number (N) and Brightness (B) maps from TTTR imaging data. |
| [PSF Determination](psf_determination.md) *(hidden)* | 3D Gaussian PSF fitting and bead detection for confocal microscopy. |
| [Phasor-FLIM](img_pixel_phasor.md) *(hidden)* | Per-pixel phasor (g, s) maps and phasor plot from TTTR imaging data. |

## Imaging → Lifetime

| Plugin | Summary |
| --- | --- |
| [Molecule-wise MLE](sm_image_mle.md) *(hidden)* | Molecule-wise MLE lifetime analysis from TTTR imaging data (PTU). |
| [Pixel-wise MLE](img_pixel_mle.md) *(hidden)* | Pixel-wise MLE lifetime analysis for TTTR imaging data. |

## Imaging → Simulate

| Plugin | Summary |
| --- | --- |
| [CLSM Generator](clsm_generator.md) *(hidden)* | Generate a synthetic CLSM photon image from an intensity image + per-detector lifetime map(s). |

## Imaging → Tools

| Plugin | Summary |
| --- | --- |
| [Image Browser](tttr_image_browser.md) *(hidden)* | Browse TTTR files in a folder and preview intensity images for all DetectorWizard-defined detector windows. |

## Main → Tools

| Plugin | Summary |
| --- | --- |
| [Acquisition](acq.md) | Single-molecule fluorescence acquisition: stream photons from real TCSPC hardware or the built-in tttrlib Sim* photon simulator (confocal diffusion with FRET, anisotropy and photophysics). |
| [Batch-Analysis](batch_analysis.md) *(hidden)* | Apply one pre-optimised template fit to many datasets or files in one pass and export the consolidated results (CSV, DOCX report, per-run ZIP). |
| [Calculators](calculators.md) | Hub that groups ChiSurf's FRET-line, FRET/homoFRET, FCS and phasor-plot calculators and embeds the selected one in a two-panel view. |
| [F-Test](f_test.md) *(hidden)* | F-test calculator: compare two nested model fits (confidence <-> chi2 threshold) and compute the chi2-max upper limit of a single fit at a confidence level. Declarative AutoForm view; values load from open fits. |
| [FRET-Calculator](fret_calculator.md) *(hidden)* | Combined heteroFRET and homoFRET parameter calculator. |
| [Global View](globalview.md) | Interactive network graph for visualizing and managing parameter relationships across fits in global analysis. |
| [Phasor-Calculator](phasor_calculator.md) *(hidden)* | Interactive phasor plot: universal semicircle with reference-lifetime grid/ticks, a FRET trajectory and a two-component mixing line. Declarative AutoForm view. |
| [Wizards](wizards.md) | Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view. |
| [ndXplorer](ndxplorer.md) | Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data. |

## Setup

| Plugin | Summary |
| --- | --- |
| [Channel Definition](setup_channel_definition.md) *(hidden)* | Detector Channel and PIE-window definition wizard |
| [FCS Definitions](fcs_channel_preset.md) *(hidden)* | FCS channel definition plugin per detector setup |
| [Models](model_manager.md) *(hidden)* | Model Manager for ChiSurf |
| [Plugins](plugin_manager.md) *(hidden)* | Plugin Manager for ChiSurf |
| [Settings](setup.md) | Unified Settings for ChiSurf |
| [Styles](style_manager.md) *(hidden)* | Style Manager Plugin for ChiSurf |
| [Switch User](switch_user.md) | Switch the active MMFDB user for this ChiSurf session. |
| [Updates & Packages](updater.md) *(hidden)* | Update checker/installer and conda package manager. Surfaced as panels inside the unified Settings dialog. |
| [User Editor](user_editor.md) *(hidden)* | User editor plugin for Chisurf to manage users registered in the MMFDB. |

## Spectroscopy

| Plugin | Summary |
| --- | --- |
| [Burst Analysis](burst_analysis.md) | Integrated burst workflow with burst selection, BVA, burst MLE, burst browser, and background estimation. |
| [Decay Analysis](lifetime_analysis.md) | Integrated fluorescence lifetime analysis tools with IRF estimation, MaxEnt MEM, Lazy Lifetime Analysis, microtime histograms, and VV/VH G-factor calibration. |
| [Image Tools](imaging_tools.md) | Unified imaging toolbox: Image Browser, CLSM Draw, Molecule-wise MLE, Pixel-wise MLE, PSF Determination. |
| [Light Path Simulator](lightpath_simulator.md) | Optical light path simulator to calculate crosstalk and R0 overlap integrals. |

## Spectroscopy → FRET

| Plugin | Summary |
| --- | --- |
| [Accurate FRET](accurate_fret.md) | Accurate FRET (Hellenkamp): automatic alpha/beta/gamma/delta from the burst populations, the optics prior of a saved light path and the static FRET line, with E-S and E-lifetime views. |
| [FRET Line Generator](fret_line.md) *(hidden)* | Compute static, dynamic, WLC, and mixture FRET lines for parameter ranges. Results are suitable for overlaying on smFRET 2D histograms in ndxplorer. |

## Spectroscopy → Fluorescence Correlation Spectroscopy

| Plugin | Summary |
| --- | --- |
| [2D-FLCS](flc-2d.md) *(hidden)* | Two-dimensional fluorescence lifetime correlation spectroscopy (2D-FLCS): build 2D fluorescence-decay correlation maps from TTTR photon streams and resolve lifetime species and exchange dynamics. |
| [Burst-wise FCS](burst_fcs_correlator.md) *(hidden)* | Compute fluorescence correlation functions on a per-burst basis from Burst-ID (.bst) / BUR files. |
| [Diffusion/Volume Calculator](fcs_calculator.md) *(hidden)* | FCS confocal diffusion/volume calculator (tau, D, r_h, Veff, concentration). |
| [FCS Filter Calculator](fcs_filter_calculator.md) *(hidden)* | Compute filtered-FCS (fFCS) lifetime filters from microtime decay patterns. |
| [FCS-Merger](fcs_merger.md) *(hidden)* | Merge / average multiple FCS correlation curves to improve signal-to-noise. |
| [Lifetime-FCS Simulator](fcs-lfcs-sim.md) *(hidden)* | Simulate diffusing species with distinct fluorescence lifetimes and optional interconversion, then recover them by lifetime-filtered (FLCS) correlation. |

## Spectroscopy → Fluorescence Decay

| Plugin | Summary |
| --- | --- |
| [Synthetic Decay Generator](synthetic_decay.md) *(hidden)* | Generate synthetic TCSPC fluorescence-decay histograms from lifetimes/spectra (optional IRF convolution and Poisson shot noise) — the single canonical decay generator, exposed as API/CLI/RPC/GUI. |

## Spectroscopy → Fluorescence decay

| Plugin | Summary |
| --- | --- |
| [Anisotropy-Wizard](tr_anisotropy.md) *(hidden)* | Guided setup of a linked VV/VH global time-resolved anisotropy fit: load polarised decays, background-correct the IRFs, set instrument corrections and define lifetime/rotation spectra. |
| [Histogram-Microtime](microtime_histogram.md) *(hidden)* | Create and inspect TTTR microtime histograms. |
| [IRF Estimation](irf_estimator.md) *(hidden)* | Blind IRF estimation from fluorescence decay data using truncated exponential fitting and Richardson-Lucy deconvolution. |
| [Lazy Lifetime Analysis](lltf.md) *(hidden)* | Lazy Lifetime Analysis for TCSPC fluorescence decay data. |
| [MaxEnt MEM](maxent_decay.md) *(hidden)* | Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance). |
| [VV/VH G-Factor Calculator](vv_vh_g_factor.md) *(hidden)* | Calculate detector G-factors using tail-matching on VV/VH format files. |

## Spectroscopy → Single-Molecule

| Plugin | Summary |
| --- | --- |
| [2CDE](burst_2cde.md) *(hidden)* | FRET-2CDE / ALEX-2CDE per-burst dynamics feature (Tomov et al. 2012). |
| [BVA](burst_bva.md) *(hidden)* | Burst Variance Analysis for single-molecule FRET experiments. |
| [Burst Background Estimation](burst_background.md) *(hidden)* | Estimate detector background rates from TTTR burst data. |
| [Burst Browser](burst_browser.md) *(hidden)* | Inspect burstwise analysis tables and plots. |
| [Burst IRF & Background](burst_irf_bg.md) *(hidden)* | Extract a per-detector IRF and background rate from the non-burst photons of a single-molecule measurement, and feed them to the burst MLE lifetime fit. |
| [Burst MLE](burst_mle_analysis.md) *(hidden)* | Maximum likelihood lifetime analysis for single-molecule burst data. |
| [Burst Selection](burst_selection.md) *(hidden)* | Burst selection and FRET analysis for single-molecule fluorescence data. |
| [H2MM](burst_h2mm.md) *(hidden)* | Photon-by-photon Hidden Markov Model (H2MM) analysis of single-molecule FRET burst data, with BIC/ICL state selection and Viterbi dwell/transition analysis. |
| [PCH](pch.md) | Photon Counting Histogram (PCH) analysis for single-molecule fluorescence data. Compute PCH histograms from TTTR files and fit multi-species models to extract molecular brightness and occupancy. |
| [Trace Browser](trace_browser.md) | Browse PTU/TTTR intensity traces from a folder, rate and annotate files, preview traces, and export selected traces. |
| [ebFRET (binned traces)](burst_ebfret.md) *(hidden)* | Empirical-Bayes Gaussian hidden Markov model for binned single-molecule FRET time traces (ebFRET/vbFRET-style), with a state-count scan, per-state emission recovery, and Viterbi dwell/transition analysis. Complements the photon-by-photon H2MM plugin for TIRF-style intensity-vs-time data. |

## Structure → Computation

| Plugin | Summary |
| --- | --- |
| [HydroPro](hydropro.md) *(hidden)* | Graphical front-end to the HYDROPRO / HYDRO++ suite for computing hydrodynamic properties (e.g. translational diffusion coefficient) from atomic or bead-model structures. |

## Structure → FRET

| Plugin | Summary |
| --- | --- |
| [Docking & Screening](fret_docking.md) *(hidden)* | FRET-restrained rigid-body docking, refinement, structure-library screening and error estimation using IMP + IMP.bff accessible volumes (a thin shim around IMP.pmi). |
| [FPS JSON Editor](fps_json_editor.md) *(hidden)* | Edit fps.json files for FRET accessible-volume modeling and fetch reference PDB structures by RCSB ID. |
| [Kappa2 Distribution](kappa2_dist.md) *(hidden)* | Calculate and visualise the k² orientation-factor distribution for FRET using WIC, DWT, or isotropic models. |

## Structure → Structure

| Plugin | Summary |
| --- | --- |
| [ChiMOL](chimol.md) | Molecular structure viewer and protein analysis plugin for ChiSurf. |
| [Structure Tools](structure_tools.md) | Unified structure toolbox: FPS JSON Editor, FRET Docking & Screening, Kappa2 Distribution, QuEst, HydroPro and Trajectory Tools. |
| [Traj Tools](traj_tools.md) *(hidden)* | Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools. |

## Structure → Trajectory

| Plugin | Summary |
| --- | --- |
| [Align](traj_align.md) *(hidden)* | Align molecular dynamics trajectories to a reference frame or structure. |
| [Convert](traj_convert.md) *(hidden)* | Convert molecular dynamics trajectory files between supported formats. |
| [Energy Calculator](traj_energy_calculator.md) *(hidden)* | Calculate potential energy components for structures and trajectories. |
| [FRET](traj_fret.md) *(hidden)* | Calculate FRET observables from molecular dynamics trajectories. |
| [Join](traj_join.md) *(hidden)* | Join or stack molecular dynamics trajectories. |
| [Remove Clashed](traj_remove_clashes.md) *(hidden)* | Remove frames containing steric clashes from trajectories. |
| [Rotate/Translate](traj_rotate_translate.md) *(hidden)* | Apply rigid-body rotation and translation to trajectories. |
| [Save Topol](traj_save_topology.md) *(hidden)* | Save topology or first-frame structure files from trajectories. |
| [Trajectory Energy](traj_energy.md) *(hidden)* | Calculate and analyze trajectory energy time series. |

## Tools

| Plugin | Summary |
| --- | --- |
| [AI Settings](ai_settings.md) *(hidden)* | AI Settings plugin for configuring API providers and backends. |
| [Converter](converter.md) | Unified converter hub: TTTR Split/Convert, TTTR→Time-Window BIDs and BID→Analysis. |
| [MMFDB Admin](mmfdb_admin.md) | Manage the Multiparametric Fluorescence Database (MMFDB): samples, experiments, setups, raw/processed data, provenance, and project archives. |
| [Open Project](project_browser.md) | Browse, save, restore, export, and import Chisurf projects using the MMFDB database with version control. |
| [TTTR Tools](tttr_toolbox.md) | Unified TTTR toolbox: ALEX Creator, Micro-time Shifter, TTTR Header Editor and Split/Convert. |

## Tools → Converter

| Plugin | Summary |
| --- | --- |
| [ALEX Creator](ptu_alex_creator.md) *(hidden)* | Convert ALEX macro-time modulation into micro-time (single, batch or merged), for PIE-style analysis of .sm and other TTTR files. |
| [TTTR→Time-Window BIDs](tttr_time_windows.md) *(hidden)* | Split TTTR files into fixed-duration time-window BID (.bst) files. |

## Tools → Miscellaneous

| Plugin | Summary |
| --- | --- |
| [Code Editor](code_editor.md) | Shared multi-document code/text editor with project navigation, symbols, diagnostics, and optional Python LSP integration. |
| [Games](games.md) | A collection of built-in games: Number Quest, Minesweeper, Tetris, Pong, and Breakout. |
| [Plugin-Check](plugin_check.md) *(hidden)* | Tests all ChiSurf plugins for startup errors and reports successes, failures, and skipped checks. |

## Tools → Miscellaneous → Games

| Plugin | Summary |
| --- | --- |
| [Breakout](breakout.md) *(hidden)* | Classic Breakout game with progressive difficulty, multiple brick types, mouse/keyboard control, and particle effects; contained in the Games hub. |
| [Minesweeper](minesweeper.md) *(hidden)* | A Minesweeper game with selectable playfield size and mine count, contained in the Games hub. |
| [Number Quest](number_quest.md) *(hidden)* | A small number-guessing game contained in the Games hub. |
| [Pong](pong.md) *(hidden)* | Classic Pong game with CPU opponent, score tracking, and particle effects; contained in the Games hub. |
| [Tetris](tetris.md) *(hidden)* | Classic Tetris game with line clearing, score tracking, and next-piece preview; contained in the Games hub. |

## Tools → TTTR

| Plugin | Summary |
| --- | --- |
| [Audifier](tttr_audifier.md) *(hidden)* | Convert TTTR photon streams to audio, with a live micro-time / lifetime waterfall preview. |
| [Count Rate Analysis](tttr_count_rate_analysis.md) *(hidden)* | Count rates per detector channel across many TTTR files, with mean/std and a per-file plot. |
| [LUT Tools](tttr_lut_tools.md) *(hidden)* | Compute TTTR microtime LUTs and create channel LUT settings in one dockable workspace. |
| [Microtime Shifter](microtime_shifter.md) *(hidden)* | Apply global and per-channel micro-time shifts to TTTR files. |

## Uncategorized

| Plugin | Summary |
| --- | --- |
| [Spectra Downloader](spectra_downloader.md) | Download, browse and push optical-component spectra (fluorophores, filters, dichroics, detectors, light sources) |

## {{ cookiecutter.plugin_category }}

| Plugin | Summary |
| --- | --- |
| [{{ cookiecutter.plugin_display_name }}]({{ cookiecutter.plugin_name }}.md) | {{ cookiecutter.plugin_description }} |
