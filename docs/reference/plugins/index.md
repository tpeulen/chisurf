---
type: Index
title: Plugin catalogue
description: Every discoverable ChiSurf plugin, grouped by its menu category, with a link to its reference page.
tags: [reference, plugins, catalogue]
generator: build_tools/docs/generate_plugin_docs.py
---

# Plugin catalogue

Every discoverable ChiSurf plugin, grouped by its menu category. Each page gives the plugin's identity, its editable parameters, and its JSON-RPC surface.

Of the **134 plugins**, **63** build their interface from declarative AutoForm specs and get a full per-parameter table on their page; the remainder use custom Qt widgets, so their controls are described in each plugin's guide while every named fit/model parameter is defined once in the **[parameter glossary](../parameters.md)**.

```{toctree}
:hidden:
:glob:

*
```

**134 plugins** across 29 categories.

## Analysis → Kinetics

| Plugin | Summary |
| --- | --- |
| [Hidden Markov model](hmm.md) | Gaussian hidden Markov model for binned time traces: fits states and transitions by Baum-Welch, decodes the state path, and reports emissions, dwell times, transition rates and an AIC/BIC state-count scan. The shared HMM seam of ChiSurf — the same analysis is reachable from the GUI, the CLI and over RPC, and other plugins call its Qt-free core instead of fitting their own. |

## Core

| Plugin | Summary |
| --- | --- |
| [Database Connector](database_connector.md) *(hidden)* | Core database connector services for source/user database resolution, migration, backup, reset, repository access, and FLR CIF import/export. |

## Help

| Plugin | Summary |
| --- | --- |
| [About ChiSurf](about.md) | ChiSurf About Plugin  This plugin provides information about ChiSurf, including version, developer, and contact information.  Features: - Display ChiSurf logo - Show version information - Display developer contact details |
| [Boarding Wizard](boarding.md) *(hidden)* | Startup onboarding wizard for first-run ChiSurf configuration. |
| [Documentation](help.md) | Documentation browser and help resource viewer for ChiSurf. |

## Imaging

| Plugin | Summary |
| --- | --- |
| [CLSM-Draw](clsm.md) *(hidden)* | Create CLSM-TTTR image representations, select pixels interactively, and export fluorescence-decay histograms. |
| [Colocalization](img_coloc.md) | Two-channel colocalization (Pearson, Manders, Costes, Li ICQ) on TIFF stacks and photon-stream images, with an interactive intensity scatter gate. |
| [Drift Correction](img_drift.md) | Measure and remove inter-frame sample drift in TIFF stacks and photon-stream images. Photon streams are corrected photon by photon, so lifetimes and correlations stay valid. |
| [FRC Resolution](img_frc.md) | Measure the resolution an image actually achieved by Fourier ring correlation — of a TIFF stack or a photon stream — and read it against the 1/7, ½-bit or 2σ criterion. |
| [Flow Maps](img_flow.md) | Map the velocity field of a sample from its own correlations — one arrow per tile, over the image. No model and no fit: the velocity is read off where a correlation peak is. Ships a simulated demo whose flow profile is known, so the arrows can be checked. |
| [IRF & BG](img_calibration.md) *(hidden)* | Per-detector IRF file and background (kHz) calibration; transferred to phasor and pixel-wise MLE. Optional (skippable) pipeline step. |
| [Intensity](img_pixel_intensity.md) *(hidden)* | Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference) that N&B / phasor / MLE enrich. |
| [Mean Micro-Time](img_pixel_micro_time.md) *(hidden)* | Per-pixel mean micro-time (arrival time) maps from TTTR imaging data. |
| [Number & Brightness](img_pixel_nb.md) *(hidden)* | Per-pixel Number (N) and Brightness (B) maps from TTTR imaging data. |
| [PSF Determination](psf_determination.md) *(hidden)* | 3D Gaussian PSF fitting and bead detection for confocal microscopy. |
| [Particle Tracking](img_tracking.md) | Single-particle tracking: detect diffraction-limited particles in every frame, link them into trajectories by exact assignment with gap closing, and fit the diffusion coefficient and anomalous exponent from the mean squared displacement. |
| [Phasor-FLIM](img_pixel_phasor.md) *(hidden)* | Per-pixel phasor (g, s) maps and phasor plot from TTTR imaging data. |
| [Spot Finder](spot_finder.md) *(hidden)* | Detect spots and regions in imaging data and persist them, with their pixels, into the measurement's container. |

## Imaging → Lifetime

| Plugin | Summary |
| --- | --- |
| [Pixel-wise MLE](img_pixel_mle.md) *(hidden)* | Pixel-wise MLE lifetime analysis for TTTR imaging data. |
| [Region MLE](region_mle.md) *(hidden)* | Region MLE lifetime analysis from TTTR imaging data (PTU). |

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
| [RICS-Precision](rics_precision.md) | Predict how precisely a raster scan (RICS) will measure a diffusion coefficient, and find the dwell time that measures it best — from the intended settings alone, before the microscope time is spent. |
| [Screenshot](screenshot.md) | Screenshot  A minimal plugin that captures a screenshot of the ChiSurf main window and copies it to the clipboard.  Behavior: - It captures the current main window and copies the image to the clipboard. - It displays a temporary message box confirming the action. |
| [Wizards](wizards.md) | Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view. |
| [ndX](ndxplorer.md) | Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data. |

## Microscopy

| Plugin | Summary |
| --- | --- |
| [PSF Calculator](psf_calculator.md) *(hidden)* | Compute and view a 3-D point-spread function: scalar, Airy or vectorial Richards-Wolf, with the input polarization at the objective pupil. |

## Setup

| Plugin | Summary |
| --- | --- |
| [Channel Definition](setup_channel_definition.md) *(hidden)* | Detector Channel and PIE-window definition wizard |
| [FCS Definitions](fcs_channel_preset.md) *(hidden)* | FCS channel definition plugin per detector setup |
| [Menu Switch](menu_switch.md) | Menu Switch  This plugin provides a simple toggle to switch between the traditional menu bar  and the modern ribbon interface in ChiSurf.  Features: - One-click switching between menu and ribbon interfaces - Automatic state detection and switching - Persistent preference saving - Seamless transition without requiring restart  The Menu Switch plugin allows users to easily toggle between the traditional menu bar interface and the modern ribbon interface based on their preference or workflow requirements. The current interface state is automatically saved and restored on application startup.  This plugin is particularly useful for users who want to quickly switch between interfaces for different tasks or for those who are evaluating which interface works best for their workflow. |
| [Models](model_manager.md) *(hidden)* | Model Manager for ChiSurf |
| [Plots](plot_settings.md) *(hidden)* | Configure plot appearance, colors, and rendering backend |
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
| [FCS](fcs_toolbox.md) | Unified **FCS** plugin — a meta tool hosting the FCS workflow behind a rail.  Merges the FCS *Correlator* workflow (detector → files → filter → correlate → merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, diffusion/volume calculator, fFCS filter calculator, correlation-channel presets) into a single left-navigation tool. Built on the reusable ``NavigationPanelTool`` shell. The ribbon execs this file with ``__name__ == "plugin"``. |
| [Image Tools](imaging_tools.md) | Unified imaging toolbox: Image Browser, Drift Correction, CLSM Draw, Molecule-wise MLE, Pixel-wise MLE, PSF Determination. |
| [Light Path Simulator](lightpath_simulator.md) | Optical light path simulator to calculate crosstalk and R0 overlap integrals. |
| [Spectra Downloader](spectra_downloader.md) | Download, browse and push optical-component spectra (fluorophores, filters, dichroics, detectors, light sources) |

## Spectroscopy → FRET

| Plugin | Summary |
| --- | --- |
| [Accurate FRET](accurate_fret.md) | Accurate FRET (Hellenkamp): automatic alpha/beta/gamma/delta from the burst populations, the optics prior of a saved light path and the static FRET line, with E-S and E-lifetime views. |
| [FRET Line Generator](fret_line.md) *(hidden)* | Compute static, dynamic, WLC, and mixture FRET lines for parameter ranges. Results are suitable for overlaying on smFRET 2D histograms in ndX. |

## Spectroscopy → Fluorescence Correlation Spectroscopy

| Plugin | Summary |
| --- | --- |
| [2D-FLCS](flc-2d.md) *(hidden)* | Two-dimensional fluorescence lifetime correlation spectroscopy (2D-FLCS): build 2D fluorescence-decay correlation maps from TTTR photon streams and resolve lifetime species and exchange dynamics. |
| [Burst-wise FCS](burst_fcs_correlator.md) *(hidden)* | Compute fluorescence correlation functions on a per-burst basis from Burst-ID (.bst) / BUR files. |
| [Correlator](fcs_correlator.md) *(hidden)* | FCS Correlator  This plugin provides a two-pane navigation-based correlator tool for computing and merging fluorescence correlation spectroscopy (FCS) data. Features include:  - Detector and PIE window definition - TTTR file selection with drag-and-drop - Optional photon/burst filtering - Multi-tau correlation with configurable parameters (bins, cascades, fine grid) - FCS curve merging and export  The tool replaces the legacy QWizard with a modern navigation panel layout (left step list, right view/display), built using the AutoForm declarative UI framework for the correlator settings panel.  The correlator workflow is no longer a standalone menu entry: it is hosted as the first section of the unified **FCS** tool (``fcs_toolbox``), which merges the correlator workflow with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, calculators). This module remains the reusable building block (``FcsCorrelatorTool`` + the correlator/filter/merger AutoForm panels) and is therefore hidden from the plugin menu. |
| [Diffusion/Volume Calculator](fcs_calculator.md) *(hidden)* | FCS confocal diffusion/volume calculator (tau, D, r_h, Veff, concentration). |
| [FCS Converter](fcs_convert.md) *(hidden)* | FCS conversion plugin.  Convert fluorescence correlation spectroscopy files between supported formats directly from the ChiSurf CLI. |
| [FCS Filter Calculator](fcs_filter_calculator.md) *(hidden)* | Compute filtered-FCS (fFCS) lifetime filters from microtime decay patterns. |
| [FCS Saturation](fcs_saturation.md) | FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5). |
| [FCS-Merger](fcs_merger.md) *(hidden)* | Merge / average multiple FCS correlation curves to improve signal-to-noise. |
| [Lifetime-FCS Simulator](fcs-lfcs-sim.md) *(hidden)* | Simulate diffusing species with distinct fluorescence lifetimes and optional interconversion, then recover them by lifetime-filtered (FLCS) correlation. |

## Spectroscopy → Fluorescence decay

| Plugin | Summary |
| --- | --- |
| [Anisotropy-Wizard](tr_anisotropy.md) *(hidden)* | Guided setup of a linked VV/VH global time-resolved anisotropy fit: load polarised decays, background-correct the IRFs, set instrument corrections and define lifetime/rotation spectra. |
| [Histogram-Microtime](microtime_histogram.md) *(hidden)* | Create and inspect TTTR microtime histograms. |
| [IRF Estimation](irf_estimator.md) *(hidden)* | Blind IRF estimation from fluorescence decay data using truncated exponential fitting and Richardson-Lucy deconvolution. |
| [Lazy Lifetime Analysis](lltf.md) *(hidden)* | Lazy Lifetime Analysis for TCSPC fluorescence decay data. |
| [MaxEnt MEM](maxent_decay.md) *(hidden)* | Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance). |
| [Synthetic Decay Generator](synthetic_decay.md) *(hidden)* | Generate synthetic TCSPC fluorescence-decay histograms from lifetimes/spectra (optional IRF convolution and Poisson shot noise) — the single canonical decay generator, exposed as API/CLI/RPC/GUI. |
| [VV/VH Anisotropy Decay](vv_vh_anisotropy.md) *(hidden)* | Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift. |
| [VV/VH G-Factor Calculator](vv_vh_g_factor.md) *(hidden)* | Calculate detector G-factors using tail-matching on VV/VH format files. |

## Spectroscopy → Single-Molecule

| Plugin | Summary |
| --- | --- |
| [2CDE](burst_2cde.md) *(hidden)* | FRET-2CDE / ALEX-2CDE per-burst dynamics feature (Tomov et al. 2012). |
| [ALEX Suite](alex_suite.md) | The classic ALEX-Suite workflow, as a linear ChiSurf pipeline: files, µs-ALEX alternation, burst search, background, accurate FRET, E-S. Plus the titration/stack-plot analysis and the ALEX-Suite CSV export. Writes the same .pto container and burst companions as the PIE burst workflow. |
| [BVA](burst_bva.md) *(hidden)* | Burst Variance Analysis for single-molecule FRET experiments. |
| [Burst Background Estimation](burst_background.md) *(hidden)* | Estimate detector background rates from TTTR burst data. |
| [Burst Browser](burst_browser.md) *(hidden)* | Inspect burstwise analysis tables and plots. |
| [Burst Fusion](burst_fusion.md) *(hidden)* | Fuse bursts the same molecule produced, using the recurrence same-molecule probability, into a new burst folder. |
| [Burst IRF & Background](burst_irf_bg.md) *(hidden)* | Extract a per-detector IRF and background rate from the non-burst photons of a single-molecule measurement, and feed them to the burst MLE lifetime fit. |
| [Burst MLE](burst_mle_analysis.md) *(hidden)* | Maximum likelihood lifetime analysis for single-molecule burst data. |
| [Burst Selection](burst_selection.md) *(hidden)* | Burst selection and FRET analysis for single-molecule fluorescence data. |
| [H2MM](burst_h2mm.md) *(hidden)* | Photon-by-photon Hidden Markov Model (H2MM) analysis of single-molecule FRET burst data, with BIC/ICL state selection and Viterbi dwell/transition analysis. |
| [Intensity trace](intensity_trace.md) | Intensity Trace Analysis for Single-Molecule Data  This plugin provides tools for analyzing fluorescence intensity time traces from  single-molecule experiments. It enables researchers to extract dynamic information  from photon counting data, particularly for studying conformational changes,  molecular interactions, and reaction kinetics at the single-molecule level.  Features: - Loading and displaying Time-Tagged Time-Resolved (TTTR) data as intensity traces - Histogram analysis of photon counts with customizable binning - Hidden Markov Model (HMM) analysis for state detection and classification - Bayesian Information Criterion (BIC) calculation for optimal state number determination - Dwell time analysis for extracting kinetic information and rate constants - FRET efficiency calculation and state-specific distribution analysis - Transition probability matrix visualization and analysis - Exponential fitting of dwell time distributions - Interactive visualization with adjustable parameters - Support for multi-channel data analysis (donor/acceptor channels)  The plugin implements a comprehensive workflow for single-molecule state analysis: 1. Load TTTR data and convert to binned intensity traces 2. Visualize traces and photon count distributions 3. Apply HMM to identify discrete states in noisy data 4. Analyze state transitions and dwell times to extract kinetic information 5. For FRET data, calculate efficiency distributions for each state  Ideal for analyzing single-molecule FRET, protein folding/unfolding, enzyme dynamics, ligand binding, blinking behavior, or any other dynamic processes that can be  observed in fluorescence intensity traces. The HMM approach is particularly powerful for detecting states in noisy data with overlapping distributions. |
| [PCH](pch.md) | Photon Counting Histogram (PCH) analysis for single-molecule fluorescence data. Compute PCH histograms from TTTR files and fit multi-species models to extract molecular brightness and occupancy. |
| [Photon-by-photon kinetics](burst_gs.md) | Gopich-Szabo photon-by-photon maximum likelihood: continuous-time rate constants and per-state FRET efficiencies fitted directly to photon arrival times and colours, for two- and three-colour data, with a transition-time scan and an H2MM cross-check. |
| [Trace Browser](trace_browser.md) | Browse PTU/TTTR intensity traces from a folder, rate and annotate files, preview traces, and export selected traces. |
| [ebFRET (binned traces)](burst_ebfret.md) *(hidden)* | Empirical-Bayes Gaussian hidden Markov model for binned single-molecule FRET time traces (ebFRET/vbFRET-style), with a state-count scan, per-state emission recovery, and Viterbi dwell/transition analysis. Complements the photon-by-photon H2MM plugin for TIRF-style intensity-vs-time data. |

## Structure → Computation

| Plugin | Summary |
| --- | --- |
| [HydroPro](hydropro.md) *(hidden)* | Graphical front-end to the HYDROPRO / HYDRO++ suite for computing hydrodynamic properties (e.g. translational diffusion coefficient) from atomic or bead-model structures. |
| [Protein Monte Carlo](proteinmc.md) *(hidden)* | Protein Monte Carlo CLI plugin.  Expose the ProteinMC cmd tool via the unified ChiSurf CLI. |
| [QuEst](quenching_estimator.md) *(hidden)* | Structure-based simulation of dynamic PET quenching and FRET for dyes tethered to proteins by flexible linkers. The science lives in the `quest` package; this plugin is the ChiSurf-side shell. |

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

## TTTR

| Plugin | Summary |
| --- | --- |
| [Correlate](tttr_correlate.md) | TTTR Correlate  This plugin provides a graphical interface for calculating correlation functions from Time-Tagged Time-Resolved (TTTR) data.  Features: - Support for various correlation types (auto, cross) - Configurable correlation parameters - Interactive visualization of correlation curves - Export of correlation results  The correlator is essential for analyzing dynamic processes in fluorescence correlation spectroscopy (FCS) and related techniques. |
| [Generate Decay](tttr_histogram.md) | TTTR Histogram (Generate Decay)  This plugin provides a graphical interface for generating fluorescence decay histograms from Time-Tagged Time-Resolved (TTTR) data.  Features: - Configurable histogram parameters (binning, time range) - Channel selection for multi-channel TTTR data - Interactive visualization of decay curves - Export of histogram data for further analysis  The histogram generator is useful for time-resolved fluorescence spectroscopy and lifetime analysis. |
| [PTO Inspector](pto_inspector.md) *(hidden)* | Inspect a .pto photon container: every object in it, the provenance graph that says how each came to be, the payload as a table or a curve, and the settings that are the recipe. Double-click a step to open the tool that performs it. |
| [⇄ .pto](tttr_to_pto.md) *(hidden)* | Convert between a vendor photon file (.ptu, .spc, .ht3, ...) and ChiSurf's own .pto container, in either direction. Drop a vendor file to pack it into a .pto beside it; drop a .pto to unpack the vendor file(s) it embeds back out. Whichever direction, the dropped file is kept and the result is verified byte-for-byte before anything is ever deleted. Packing is also offered as a one-time nag wherever a plugin drops a vendor file to load it as the working measurement. |

## TTTR → Editor

| Plugin | Summary |
| --- | --- |
| [Split/Convert](tttr_splitter.md) *(hidden)* | TTTR Split / Convert plugin.  This plugin provides functionality for splitting large TTTR (Time-Tagged Time-Resolved) files, particularly those in the PicoQuant PTU format, into smaller segments. This is useful for:  1. Breaking down large datasets into manageable chunks 2. Extracting specific time segments from long measurements 3. Creating subsets of data for parallel processing 4. Reducing memory requirements for analysis  The plugin features: - Support for various TTTR file formats - Configurable splitting parameters (photons per file, time segments) - Options for micro-time binning to reduce file size - Ability to reset macro-times in the output files - Selection of output container formats (file format conversion)  This tool is particularly valuable for handling large datasets from long-duration single-molecule or imaging experiments, making them more manageable for subsequent analysis. |
| [TTTR Header editor](tttr_header_edit.md) *(hidden)* | TTTR Header Editor plugin.  This plugin provides a tool for viewing and editing header tags of any time-tagged time-resolved (TTTR) file that :mod:`tttrlib` can read — PicoQuant PTU and HT3, Becker&Hickl SPC, and Photon-HDF5. ``tttrlib`` normalises every container into the same tag list, so the editor is format-agnostic on read. It allows users to: 1. Open and inspect any supported TTTR file (auto-detected container) 2. View all header tags and their values in a tabular format 3. Edit existing tag values 4. Add new custom tags to the header 5. Remove unwanted tags 6. Save the edited header to a new PTU file  The plugin features an intuitive table-based interface that displays tag names, types, values, and indices. Users can modify any field and see the changes in real-time. A JSON view is also available to see the complete header structure.  This tool is particularly useful for: - Correcting metadata in experimental TTTR files - Adding missing information to headers - Preparing files for specialized analysis - Troubleshooting issues with file metadata - Educational purposes to understand TTTR file structure  The photon events of the source file are copied verbatim into the saved file. Output is always a PTU container, because it is the only ``tttrlib`` container that persists arbitrary edited header tags without loss. |

## Tools

| Plugin | Summary |
| --- | --- |
| [AI Settings](ai_settings.md) *(hidden)* | AI Settings plugin for configuring API providers and backends. |
| [File tools](filetools.md) | Everything that acts on a file rather than on the physics inside it: TTTR split/convert, packing and unpacking a .pto container, reading one back, time-window BIDs, BID→Analysis, and the TTTR header editor. |
| [MMFDB Admin](mmfdb_admin.md) | Manage the Multiparametric Fluorescence Database (MMFDB): samples, experiments, setups, raw/processed data, provenance, and project archives. |
| [Open Project](project_browser.md) | Browse, save, restore, export, and import Chisurf projects using the MMFDB database with version control. |
| [TTTR Tools](tttr_toolbox.md) | Unified TTTR toolbox: ALEX Creator, Micro-time Shifter, TTTR Header Editor and Split/Convert. |

## Tools → Burst

| Plugin | Summary |
| --- | --- |
| [MFD Prepare](mfd_prepare.md) *(hidden)* | Prepare a burst folder for multiparameter-fluorescence (MFD) analysis: resolve photon sources, verify channel counts, compute mean micro times, and inspect the preparation report. |

## Tools → Converter

| Plugin | Summary |
| --- | --- |
| [ALEX Creator](ptu_alex_creator.md) *(hidden)* | Convert ALEX macro-time modulation into micro-time (single, batch or merged), for PIE-style analysis of .sm and other TTTR files. |
| [BID→Analysis](bid_to_analysis.md) *(hidden)* | BID → Analysis Converter  This plugin reads burst ID (BID) files containing start/stop photon indices and generates a burstwise analysis folder next to the corresponding TTTR data.  Workflow per BID file: - Infer the TTTR file from the BID file name (same stem, common TTTR extensions) - Load TTTR via tttrlib - Compute burst summary using cs.core.fio.fluorescence.burst.generate_burst_dataframe - Write a BUR file to analysis/bi4_bur/<stem>.bur - Update/create analysis/Info/*.mti with total measurement time  The plugin exposes a simple GUI file dialog when launched from the Plugins menu. It can also be called programmatically via convert_bid_file(pathlike). |
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
| [Imaging Common](imaging_common.md) *(hidden)* | Shared base classes for the per-pixel imaging tools: the common tool shell, the image/frame plumbing and the MMFDB bridge they all reuse. |
| [Mle Common](mle_common.md) *(hidden)* | Shared maximum-likelihood machinery for the spot/region/pixel MLE tools: the estimator contract, the fitting base class and its tool shell. |
| [Ninja Adventure](ninja_adventure.md) *(hidden)* | The CC0 Ninja Adventure reference map, playable on the chigame engine: explore the village, break the crates, cross the teleporter, fight the swamp samurai. |

## {{ cookiecutter.plugin_category }}

| Plugin | Summary |
| --- | --- |
| [{{ cookiecutter.plugin_display_name }}]({{ cookiecutter.plugin_name }}.md) | {{ cookiecutter.plugin_description }} |
