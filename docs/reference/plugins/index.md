---
type: Index
title: Plugin catalogue
description: Every discoverable ChiSurf plugin, grouped by its menu category, with a link to its reference page.
tags: [reference, plugins, catalogue]
generator: build_tools/docs/generate_plugin_docs.py
---

# Plugin catalogue

Every discoverable ChiSurf plugin, grouped by its menu category. Each page gives the plugin's identity, its editable parameters, and its JSON-RPC surface.

Of the **127 plugins**, **91** build their interface from declarative AutoForm specs and get a full per-parameter table on their page; the controls of the others are described in each plugin's guide, and every named fit/model parameter is defined once in the **[parameter glossary](../parameters.md)**.

```{toctree}
:hidden:
:glob:

*
```

**127 plugins** across 28 categories.

## Core

| Plugin | Summary |
| --- | --- |
| [Database Connector](database_connector.md) *(hidden)* | Core database connector services for source/user database resolution, migration, backup, reset, repository access, and FLR CIF import/export. |

## File → Data

| Plugin | Summary |
| --- | --- |
| [BID→Analysis](bid_to_analysis.md) | Turn burst-ID files (first/last photon index per burst) into burst tables of the matching TTTR measurement: a bursts table in its .pto, or a legacy .bur + .mti, SL5 mask or HDF5 table. Scriptable as convert_bid_file(path). |
| [Burstwise→PTO](burstwise_import.md) | Convert legacy burstwise analysis folders (bi4_bur/bg4/br4/BIDs/Info/.mti) to PTO.MFDB containers. |
| [MFD Prepare](mfd_prepare.md) | Prepare a burst folder for multiparameter-fluorescence (MFD) analysis: resolve photon sources, verify channel counts, compute mean micro times, and inspect the preparation report. |
| [PTO Inspector](pto_inspector.md) | Inspect a .pto photon container: every object in it, the provenance graph that says how each came to be, the payload as a table or a curve, and the settings that are the recipe. Double-click a step to open the tool that performs it. |
| [Split/Convert](tttr_splitter.md) | Split a TTTR file into files of a fixed photon count, convert it to another container format, or bin its micro-times; one file or a batch. |
| [TTTR Header editor](tttr_header_edit.md) | View and edit the header tags of any TTTR file tttrlib reads (PTU, HT3, SPC, Photon-HDF5): change, add or remove tags and save the photons unchanged into a new PTU file, the only container that keeps arbitrary tags. |
| [TTTR→Time-Window BIDs](tttr_time_windows.md) | Split TTTR files into fixed-duration time-window BID (.bst) files. |
| [Zenodo deposit](zenodo_deposit.md) | Review a deposition record item by item -- every measurement folder, calibration folder and metadata file, with where it came from and why it is flagged -- then upload it as a Zenodo draft and check the draft against the local package. Nothing is uploaded until every item is approved at its current content; publishing needs its own approval of the exact package. |
| [⇄ .pto](tttr_to_pto.md) | Convert between a vendor photon file (.ptu, .spc, .ht3, ...) and ChiSurf's own .pto container, in either direction. Drop a vendor file to pack it into a .pto beside it; drop a .pto to unpack the vendor file(s) it embeds back out. Whichever direction, the dropped file is kept and the result is verified byte-for-byte before anything is ever deleted. Packing is also offered as a one-time nag wherever a plugin drops a vendor file to load it as the working measurement. |

## Help

| Plugin | Summary |
| --- | --- |
| [About ChiSurf](about.md) | ChiSurf's logo, version, developer and contact details. |
| [Boarding Wizard](boarding.md) *(hidden)* | Startup onboarding wizard for first-run ChiSurf configuration. |
| [Documentation](help.md) | Documentation browser and help resource viewer for ChiSurf. |

## Main → Tools

| Plugin | Summary |
| --- | --- |
| [Batch-Analysis](batch_analysis.md) *(hidden)* | Apply one pre-optimised template fit to many datasets or files in one pass and export the consolidated results (CSV, DOCX report, per-run ZIP). |
| [F-Test](f_test.md) *(hidden)* | F-test calculator: compare two nested model fits (confidence &lt;-> chi2 threshold) and compute the chi2-max upper limit of a single fit at a confidence level. Declarative AutoForm view; values load from open fits. |
| [FRET-Calculator](fret_calculator.md) *(hidden)* | Combined heteroFRET and homoFRET parameter calculator. |
| [Phasor-Calculator](phasor_calculator.md) *(hidden)* | Interactive phasor plot: universal semicircle with reference-lifetime grid/ticks, a FRET trajectory and a two-component mixing line. |
| [RICS-Precision](rics_precision.md) *(hidden)* | Predict how precisely a raster scan (RICS) will measure a diffusion coefficient, and find the dwell time that measures it best — from the intended settings alone, before the microscope time is spent. |

## Microscopy

| Plugin | Summary |
| --- | --- |
| [PSF Calculator](psf_calculator.md) *(hidden)* | Compute and view a 3-D point-spread function: scalar, Airy or vectorial Richards-Wolf, with the input polarization at the objective pupil. |

## Setup

| Plugin | Summary |
| --- | --- |
| [Channel Definition](setup_channel_definition.md) *(hidden)* | Detector Channel and PIE-window definition wizard |
| [FCS Definitions](fcs_channel_preset.md) *(hidden)* | Define which detector channels are correlated with which, per detector setup. |
| [Menu Switch](menu_switch.md) | Switches the open ChiSurf main window between the traditional menu bar and the ribbon, without a restart. The choice is saved and restored at the next start. Menu Switch opens no window of its own. |
| [Models](model_manager.md) *(hidden)* | List the registered fitting models and switch models off so they leave the model drop-down. |
| [Plots](plot_settings.md) *(hidden)* | How fit plots look: curve colours and width, fit-range band, global fits, axes and grid, with a live preview |
| [Plugins](plugin_manager.md) *(hidden)* | List the installed plugins: switch them off, pin them to the toolbar, rename their menu entry, set their icon and whether their window remembers its state. |
| [Settings](setup.md) | The Settings window: one searchable list of every settings panel (ChiSurf settings, acquisition, styles, plots, models, users, plugins, updates, detector setup, ...). |
| [Styles](style_manager.md) *(hidden)* | Edit ChiSurf's emtk style sheets (.css files in the settings directory) and apply one to the running window. |
| [Switch User](switch_user.md) | Switch the active MMFDB user for this ChiSurf session. |
| [Updates & Packages](updater.md) *(hidden)* | Update checker/installer and conda package manager. Surfaced as panels inside the unified Settings dialog. |
| [User Editor](user_editor.md) *(hidden)* | Manage the users registered in the MMFDB: create, edit and remove accounts. |

## Spectroscopy → Correlation

| Plugin | Summary |
| --- | --- |
| [2D-FLCS](flc-2d.md) | Two-dimensional fluorescence lifetime correlation spectroscopy (2D-FLCS): build 2D fluorescence-decay correlation maps from TTTR photon streams and resolve lifetime species and exchange dynamics. |
| [Burst-wise FCS](burst_fcs_correlator.md) | Compute fluorescence correlation functions on a per-burst basis from Burst-ID (.bst) / BUR files. |
| [Diffusion/Volume Calculator](fcs_calculator.md) | FCS confocal diffusion/volume calculator (tau, D, r_h, Veff, concentration). |
| [FCS](fcs_correlator.md) | The FCS workflow: multi-tau correlation of TTTR photon streams in five steps -- channel definitions (detectors and PIE windows), files, optional photon/burst filter, correlation, and screening and merging of the curves. Filter Calc... hands the files to the fFCS Filter Calculator. |
| [FCS Converter](fcs_convert.md) *(hidden)* | Convert correlation-curve files between the supported FCS formats from the command line (csc). |
| [FCS Filter Calculator](fcs_filter_calculator.md) | Compute filtered-FCS (fFCS) lifetime filters from microtime decay patterns. |
| [FCS Saturation](fcs_saturation.md) *(hidden)* | FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5). |
| [FCS-Merger](fcs_merger.md) *(hidden)* | Merge / average multiple FCS correlation curves to improve signal-to-noise. |
| [Lifetime-FCS Simulator](fcs-lfcs-sim.md) | Simulate diffusing species with distinct fluorescence lifetimes and optional interconversion, then recover them by lifetime-filtered (FLCS) correlation. |
| [PCH](pch.md) | Photon Counting Histogram (PCH) analysis for single-molecule fluorescence data. Compute PCH histograms from TTTR files and fit multi-species models to extract molecular brightness and occupancy. |

## Spectroscopy → Decay

| Plugin | Summary |
| --- | --- |
| [Anisotropy-Wizard](tr_anisotropy.md) *(hidden)* | Guided setup of a linked VV/VH global time-resolved anisotropy fit: load polarised decays, background-correct the IRFs, set instrument corrections and define lifetime/rotation spectra. |
| [Histogram-Microtime](microtime_histogram.md) | Create and inspect TTTR microtime histograms. |
| [IRF Estimation](irf_estimator.md) | Blind IRF estimation from fluorescence decay data using truncated exponential fitting and Richardson-Lucy deconvolution. |
| [Lazy Lifetime Analysis](lltf.md) | Lazy Lifetime Analysis for TCSPC fluorescence decay data. |
| [MaxEnt MEM](maxent_decay.md) | Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance). |
| [Synthetic Decay Generator](synthetic_decay.md) | Generate synthetic TCSPC fluorescence-decay histograms from lifetimes or lifetime spectra, with optional IRF convolution and Poisson shot noise; the same generator is available from the Python API, the CLI and RPC. |
| [VV/VH Anisotropy Decay](vv_vh_anisotropy.md) | Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift. |
| [VV/VH G-Factor Calculator](vv_vh_g_factor.md) | Calculate detector G-factors using tail-matching on VV/VH format files. |

## Spectroscopy → FRET

| Plugin | Summary |
| --- | --- |
| [Accurate FRET](accurate_fret.md) *(hidden)* | Accurate FRET (Hellenkamp): automatic alpha/beta/gamma/delta from the burst populations, the optics prior of a saved light path and the static FRET line, with E-S and E-lifetime views. |
| [FRET Line Generator](fret_line.md) *(hidden)* | Compute static, dynamic, WLC, and mixture FRET lines for parameter ranges. Results are suitable for overlaying on smFRET 2D histograms in ndX. |

## Spectroscopy → Imaging

| Plugin | Summary |
| --- | --- |
| [CLSM-Draw](clsm.md) *(hidden)* | Create CLSM-TTTR image representations, select pixels interactively, and export fluorescence-decay histograms. |
| [Colocalization](img_coloc.md) *(hidden)* | Two-channel colocalization (Pearson, Manders, Costes, Li ICQ) on TIFF stacks and photon-stream images, with an interactive intensity scatter gate. |
| [Drift Correction](img_drift.md) *(hidden)* | Measure and remove inter-frame sample drift in TIFF stacks and photon-stream images. Photon streams are corrected photon by photon, so lifetimes and correlations stay valid. |
| [FRC Resolution](img_frc.md) *(hidden)* | Measure the resolution an image actually achieved by Fourier ring correlation — of a TIFF stack or a photon stream — and read it against the 1/7, ½-bit or 2σ criterion. |
| [Flow Maps](img_flow.md) *(hidden)* | Map the velocity field of a sample from its own correlations — one arrow per tile, over the image. No model and no fit: the velocity is read off where a correlation peak is. Ships a simulated demo whose flow profile is known, so the arrows can be checked. |
| [IRF & BG](img_calibration.md) *(hidden)* | Per-detector IRF file and background (kHz) calibration; transferred to phasor and pixel-wise MLE. Optional (skippable) pipeline step. |
| [Image Tools](imaging_tools.md) | Unified imaging toolbox: Image Browser, Drift Correction, FRC Resolution, Flow Maps, Particle Tracking, Colocalization, the per-pixel maps, CLSM Draw, Region MLE, PSF Determination, CLSM Generator. |
| [Intensity](img_pixel_intensity.md) *(hidden)* | Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference) that N&B / phasor / MLE enrich. |
| [Mean Micro-Time](img_pixel_micro_time.md) *(hidden)* | Per-pixel mean micro-time (arrival time) maps from TTTR imaging data. |
| [Number & Brightness](img_pixel_nb.md) *(hidden)* | Per-pixel Number & Brightness from TTTR imaging stacks: apparent B and N, molecular brightness and number, cross N&B, analog-detector calibration, bleaching detrending, and gating a brightness population back onto the image. |
| [PSF Determination](psf_determination.md) *(hidden)* | 3D Gaussian PSF fitting and bead detection for confocal microscopy. |
| [Particle Tracking](img_tracking.md) *(hidden)* | Single-particle tracking: detect diffraction-limited particles in every frame, link them into trajectories by exact assignment with gap closing, and fit the diffusion coefficient and anomalous exponent from the mean squared displacement. |
| [Phasor-FLIM](img_pixel_phasor.md) *(hidden)* | Per-pixel phasor (g, s) maps and phasor plot from TTTR imaging data. |
| [Spot Finder](spot_finder.md) *(hidden)* | Detect spots and regions in imaging data and persist them, with their pixels, into the measurement's container. |

## Spectroscopy → Imaging → Lifetime

| Plugin | Summary |
| --- | --- |
| [Pixel-wise MLE](img_pixel_mle.md) *(hidden)* | Pixel-wise MLE lifetime analysis for TTTR imaging data. |
| [Region MLE](region_mle.md) *(hidden)* | Region MLE lifetime analysis from TTTR imaging data (PTU). |

## Spectroscopy → Imaging → Simulate

| Plugin | Summary |
| --- | --- |
| [CLSM Generator](clsm_generator.md) *(hidden)* | Generate a synthetic CLSM photon image from an intensity image + per-detector lifetime map(s). |

## Spectroscopy → Imaging → Tools

| Plugin | Summary |
| --- | --- |
| [Image Browser](tttr_image_browser.md) *(hidden)* | Browse TTTR files in a folder and preview intensity images for all DetectorWizard-defined detector windows. |

## Spectroscopy → Kinetics

| Plugin | Summary |
| --- | --- |
| [Hidden Markov model](hmm.md) | Gaussian hidden Markov model for binned time traces: fits states and transitions by Baum-Welch, decodes the state path, and reports emissions, dwell times, transition rates and an AIC/BIC state-count scan. The shared HMM seam of ChiSurf — the same analysis is reachable from the GUI, the CLI and over RPC, and other plugins call its Qt-free core instead of fitting their own. |

## Spectroscopy → Single-Molecule

| Plugin | Summary |
| --- | --- |
| [2CDE](burst_2cde.md) *(hidden)* | FRET-2CDE / ALEX-2CDE per-burst dynamics feature (Tomov et al. 2012). |
| [ALEX Suite](alex_suite.md) | The classic ALEX-Suite workflow, as a linear ChiSurf pipeline: files, µs-ALEX alternation, burst search, background, accurate FRET, E-S. Plus the titration/stack-plot analysis and the ALEX-Suite CSV export. Writes the same .pto container and burst companions as the PIE burst workflow. |
| [BVA](burst_bva.md) *(hidden)* | Burst Variance Analysis for single-molecule FRET experiments. |
| [Burst Analysis](burst_analysis.md) | Integrated burst workflow with burst selection, BVA, burst MLE, burst browser, and background estimation. |
| [Burst Background Estimation](burst_background.md) *(hidden)* | Estimate detector background rates from TTTR burst data. |
| [Burst Browser](burst_browser.md) *(hidden)* | Inspect burstwise analysis tables and plots. |
| [Burst Fusion](burst_fusion.md) *(hidden)* | Fuse bursts the same molecule produced, using the recurrence same-molecule probability, into a new burst folder. |
| [Burst IRF & Background](burst_irf_bg.md) *(hidden)* | Extract a per-detector IRF and background rate from the non-burst photons of a single-molecule measurement, and feed them to the burst MLE lifetime fit. |
| [Burst MLE](burst_mle_analysis.md) *(hidden)* | Maximum likelihood lifetime analysis for single-molecule burst data. |
| [Burst Selection](burst_selection.md) *(hidden)* | Burst selection and FRET analysis for single-molecule fluorescence data. |
| [H2MM](burst_h2mm.md) *(hidden)* | Photon-by-photon Hidden Markov Model (H2MM) analysis of single-molecule FRET burst data, with BIC/ICL state selection and Viterbi dwell/transition analysis. |
| [Intensity trace](intensity_trace.md) | Bin a TTTR photon stream into intensity traces per detector, histogram the counts per bin, and find discrete states with a hidden Markov model, with dwell-time histograms of each state. |
| [Photon-by-photon kinetics](burst_gs.md) *(hidden)* | Gopich-Szabo photon-by-photon maximum likelihood: continuous-time rate constants and per-state FRET efficiencies fitted directly to photon arrival times and colours, for two- and three-colour data, with a transition-time scan and an H2MM cross-check. |
| [Trace Browser](trace_browser.md) | Browse PTU/TTTR intensity traces from a folder, rate and annotate files, preview traces, and export selected traces. |
| [ebFRET](burst_ebfret.md) | ebFRET, ported from its MATLAB GUI: empirical-Bayes hidden Markov analysis of binned donor/acceptor smFRET time series. The same window -- time series with the Viterbi path, the ensemble histograms and parameter distributions, series/crop/state controls -- the same menus (load/save session, raw/SF-Tracer/SMD import, photobleaching and outlier removal, priors, summary/trace/SMD export) and the same analysis loop, run on the backend. Ships a simulated four-state demo. |

## Structure → Computation

| Plugin | Summary |
| --- | --- |
| [HydroPro](hydropro.md) | Graphical front-end to the HYDROPRO / HYDRO++ suite for computing hydrodynamic properties (e.g. translational diffusion coefficient) from atomic or bead-model structures. |
| [Protein Monte Carlo](proteinmc.md) *(hidden)* | Command-line Protein Monte Carlo: torsion-angle sampling of a structure under FRET distance restraints, written as an RMF trajectory. |
| [QuEst](quenching_estimator.md) | Structure-based simulation of dynamic PET quenching and FRET for dyes tethered to proteins by flexible linkers: accessible volume, Brownian dynamics and photon Monte-Carlo on IMP.bff. |

## Structure → FRET

| Plugin | Summary |
| --- | --- |
| [Docking & Screening](fret_docking.md) | FRET-restrained rigid-body docking, refinement, structure-library screening and error estimation using IMP + IMP.bff accessible volumes (a thin shim around IMP.pmi). |
| [FPS JSON Editor](fps_json_editor.md) | Edit fps.json labelling plans in ChiMOL's labelling editor (positions, distances, FlexFit, accessible volumes); validate payloads and fetch PDB structures headlessly. |
| [Kappa2 Distribution](kappa2_dist.md) *(hidden)* | Calculate and visualise the k² orientation-factor distribution for FRET using WIC, DWT, or isotropic models. |

## Structure → Modelling

| Plugin | Summary |
| --- | --- |
| [ChiMOL](chimol.md) | Molecular structure viewer and protein analysis plugin for ChiSurf. |

## Structure → Trajectory

| Plugin | Summary |
| --- | --- |
| [Align](traj_align.md) | Align molecular dynamics trajectories to a reference frame or structure. |
| [Convert](traj_convert.md) | Convert molecular dynamics trajectory files between supported formats. |
| [Energy Calculator](traj_energy_calculator.md) | Calculate potential energy components for structures and trajectories. |
| [FRET](traj_fret.md) | Calculate FRET observables from molecular dynamics trajectories. |
| [Join](traj_join.md) | Join or stack molecular dynamics trajectories. |
| [Remove Clashed](traj_remove_clashes.md) | Remove frames containing steric clashes from trajectories. |
| [Rotate/Translate](traj_rotate_translate.md) | Apply rigid-body rotation and translation to trajectories. |
| [Save Topol](traj_save_topology.md) | Save topology or first-frame structure files from trajectories. |

## Tools

| Plugin | Summary |
| --- | --- |
| [AI Settings](ai_settings.md) *(hidden)* | AI Settings plugin for configuring API providers and backends. |
| [Open Project](project_browser.md) *(hidden)* | Browse, save, restore, export, and import ChiSurf projects using the MMFDB database with version control. |

## Tools → Calculators

| Plugin | Summary |
| --- | --- |
| [Calculators](calculators.md) | Hub that groups ChiSurf's FRET-line, FRET/homoFRET, FCS and phasor-plot calculators and embeds the selected one in a two-panel view. |
| [Light Path Simulator](lightpath_simulator.md) | Optical light path simulator to calculate crosstalk and R0 overlap integrals. |
| [Spectra Downloader](spectra_downloader.md) | Download, browse and push optical-component spectra (fluorophores, filters, dichroics, detectors, light sources) |
| [Wizards](wizards.md) | Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view. |

## Tools → Miscellaneous

| Plugin | Summary |
| --- | --- |
| [Plugin-Check](plugin_check.md) *(hidden)* | Tests all ChiSurf plugins for startup errors and reports successes, failures, and skipped checks. |

## Tools → Miscellaneous → Games

| Plugin | Summary |
| --- | --- |
| [Breakout](breakout.md) *(hidden)* | Classic Breakout game with progressive difficulty, multiple brick types, mouse/keyboard control, and particle effects; contained in the Games hub. |
| [Minesweeper](minesweeper.md) *(hidden)* | A Minesweeper game with selectable playfield size and mine count, contained in the Games hub. |
| [Number Quest](number_quest.md) *(hidden)* | A small number-guessing game contained in the Games hub. |
| [Pong](pong.md) *(hidden)* | Classic Pong game with CPU opponent, score tracking, and particle effects; contained in the Games hub. |
| [Tetris](tetris.md) *(hidden)* | Spectral Tetris with line clearing, score tracking, pause and restart; contained in the Games hub. |

## Tools → Photon data

| Plugin | Summary |
| --- | --- |
| [ALEX Creator](ptu_alex_creator.md) | Convert ALEX macro-time modulation into micro-time (single, batch or merged), for PIE-style analysis of .sm and other TTTR files. |
| [Audifier](tttr_audifier.md) | Convert TTTR photon streams to audio, with a live micro-time / lifetime waterfall preview. |
| [Count Rate Analysis](tttr_count_rate_analysis.md) | Count rates per detector channel across many TTTR files, with mean/std and a per-file plot. |
| [Microtime Shifter](microtime_shifter.md) | Apply global and per-channel micro-time shifts to TTTR files. |
| [Photon Table](photon_table.md) | Inspect the photons of a TTTR file in a table: routing channel, micro-time and macro-time, one row per photon, with navigation and a channel filter. |

## Tools → System

| Plugin | Summary |
| --- | --- |
| [Code Editor](code_editor.md) | Shared multi-document code/text editor with project navigation, symbols, diagnostics, and optional Python LSP integration. |
| [Games](games.md) | A collection of built-in games: Number Quest, Minesweeper, Tetris, Pong, and Breakout. |
| [MMFDB Admin](mmfdb_admin.md) | Manage the Multiparametric Fluorescence Database (MMFDB): samples, experiments, setups, raw/processed data, provenance, and project archives. |
| [Python Terminal](python_terminal.md) | ChiSurf's built-in Python console as a terminal pane: tmux-style tabs, splits and floating windows around the console engine. |
| [Terminal](terminal.md) | Terminal panes like tmux: tabs, splits and floating windows of real PTY sessions. |

## Tools → TTTR

| Plugin | Summary |
| --- | --- |
| [LUT Tools](tttr_lut_tools.md) *(hidden)* | Compute TTTR microtime LUTs and create channel LUT settings in one dockable workspace. |

## Tools → Views

| Plugin | Summary |
| --- | --- |
| [Acquisition](acq.md) | Single-molecule fluorescence acquisition: stream photons from real TCSPC hardware or the built-in tttrlib Sim* photon simulator (confocal diffusion with FRET, anisotropy and photophysics). |
| [Global View](globalview.md) | Interactive network graph for visualizing and managing parameter relationships across fits in global analysis. |
| [ndX](ndxplorer.md) | Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data. |

## Uncategorized

| Plugin | Summary |
| --- | --- |
| [Imaging Common](imaging_common.md) *(hidden)* | Shared base classes for the per-pixel imaging tools: the common tool shell, the image/frame plumbing and the MMFDB bridge they all reuse. |
| [Mle Common](mle_common.md) *(hidden)* | Shared maximum-likelihood machinery for the spot/region/pixel MLE tools: the estimator contract, the fitting base class and its tool shell. |
