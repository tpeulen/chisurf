---
type: Index
title: Guides — how to do it in ChiSurf
description: Step-by-step guides for the fluorescence analyses in ChiSurf.
tags: [guides, index]
---

# Guides — how to do it in ChiSurf

Step-by-step guides for the fluorescence analyses in ChiSurf. Each guide shows
**how to run the analysis in the actual user interface** and links to the
matching {doc}`concept </concepts/index>` page for the underlying theory. Figures
are real output — matplotlib plots produced by [`make_figures.py`](make_figures.py)
from synthetic data using the very functions the guide describes, and GUI
screenshots grabbed from the real widgets by
[`make_screenshots.py`](make_screenshots.py) under an offscreen Qt platform.

The guides are grouped by what you are trying to measure. If you are starting
from a raw photon file, begin with *Photon data and the burst pipeline*; if you
already have a burst list or a decay, jump straight to the analysis you need.

## Photon data and the burst pipeline

```{toctree}
:maxdepth: 1

65_live_acquisition
12_handling_tttr_files
33_timestamps_and_bursts
13_burst_identification
15_background_rates
22_binned_photon_traces
37_tttr_microtime_lut
34_exporting_burst_data
35_combining_repeats
53_reusing_results
63_pto_inspector
```

## smFRET: efficiency, stoichiometry and corrections

```{toctree}
:maxdepth: 1

14_multiparameter_es
41_accurate_fret
61_kappa2_distribution
fret_calibration
07_rcm_calibration
25_rcm_from_fret_samples
27_alex_smfret_workflow
66_alex_suite
28_selecting_fret_populations
29_fret_histogram_fitting
36_multispot
```

## Dynamics: distributions, kinetics and hidden states

```{toctree}
:maxdepth: 1

01_fret_2cde
08_burst_variance_analysis
02_recurrence_rasp
19_h2mm_hidden_markov
h2mm
30_h2mm_workflow_results
31_h2mm_simulation_validation
20_ebfret_binned_hmm
54_hidden_markov_models
49_photon_by_photon_kinetics
11_pda2c
42_pda3c
57_mfd_fitting
58_burst_fusion
```

## Fluorescence decays and anisotropy

```{toctree}
:maxdepth: 1

10_lifetime_anisotropy_fitting
irf_estimation
21_lifetime_from_bursts
32_nsalex_lifetime
```

## Correlation spectroscopy

```{toctree}
:maxdepth: 1

09_diffusion_fcs
16_fret_fcs
17_filtered_fcs
05_enderlein_mdf_two_focus_fcs
06_nsfcs_second_order
56_fcs_saturation
04_fida_pch
```

## Imaging and microscopy

```{toctree}
:maxdepth: 1

24_scan_images
48_regions
38_colocalization
67_number_and_brightness
43_drift_correction
50_particle_tracking
51_frc_resolution
45_scan_precision
55_pair_correlation
```

## Structure and modelling

```{toctree}
:maxdepth: 1

23_accessible_volume
03_polymer_distance_distributions
44_molecular_viewer
```

## Exploration, simulation and automation

```{toctree}
:maxdepth: 1

46_ndxplorer
47_ndxplorer_bridges
52_send_bursts_to_analysis
26_2d_peak_fitting
18_tttr_simulation
39_parameter_uncertainty
62_maxent_decay
60_global_analysis
40_ai_assistant
70_ask_the_documentation
71_lumis_quest
59_console
64_notebooks
```

## Where each guide starts in ChiSurf

| Tutorial | ChiSurf entry point |
|----------|---------------------|
| [FRET-2CDE / ALEX-2CDE burst dynamics](01_fret_2cde.md) | `tttrlib.TwoCDE`, `burst_2cde` plugin |
| [Recurrence analysis (RASP)](02_recurrence_rasp.md) | `core.fluorescence.burst.recurrence` |
| [Polymer inter-dye distance distributions](03_polymer_distance_distributions.md) | `rdf.saw_nu`, `rdf.ising_chain` |
| [FIDA — photon-counting histograms](04_fida_pch.md) | `core.models.pch.fida` |
| [Enderlein MDF & two-focus FCS](05_enderlein_mdf_two_focus_fcs.md) | `core.fluorescence.fcs.enderlein` |
| [ns-FCS second-order correlation](06_nsfcs_second_order.md) | `core.fluorescence.fcs.correlate.second_order_correlation` |
| [RCM detection calibration](07_rcm_calibration.md) | `core.fluorescence.fret.calibration.rcm_from_dye_solutions` |
| [Burst Variance Analysis (BVA)](08_burst_variance_analysis.md) | `tttrlib.BVA`, `burst_bva` plugin |
| [Diffusion FCS](09_diffusion_fcs.md) | FCS models + `fcs_correlator` plugin |
| [Lifetime & anisotropy decay fitting](10_lifetime_anisotropy_fitting.md) | `core.fluorescence.tcspc`, TCSPC models |
| [Two-colour PDA (PDA2c)](11_pda2c.md) | `tttrlib.Pda`, `core.models.pda2c` |
| [Live acquisition](65_live_acquisition.md) | `core/acq` plugin, `acq.pipeline`, `tttrlib` streaming consumers |
| [Handling TTTR files (& Photon-HDF5)](12_handling_tttr_files.md) | `tttrlib.TTTR`, `plugins/tttr` |
| [Photon burst identification](13_burst_identification.md) | `TTTR.burst_search`, `burst_selection` |
| [Multi-parameter E–S & correction factors](14_multiparameter_es.md) | `burst/es.py`, `fret/calibration.py` |
| [Background rates](15_background_rates.md) | `burst/background.py`, `burst_background` |
| [FRET-FCS](16_fret_fcs.md) | FRET-FCCS models + correlator |
| [Filtered FCS (fFCS / 2D-FLCS)](17_filtered_fcs.md) | `fcs/filtered.py`, `flc_2d` |
| [TTTR simulation of diffusing particles](18_tttr_simulation.md) | `tttrlib.SimEngine` |
| [Photon-by-photon HMM (H2MM)](19_h2mm_hidden_markov.md) | `burst_h2mm`, `tttrlib.H2MM` |
| [HMM of binned traces (ebFRET)](20_ebfret_binned_hmm.md) | `burst_ebfret` |
| [Lifetime from photon bursts (MLE)](21_lifetime_from_bursts.md) | `core.fluorescence.mle`, `burst_mle_analysis` |
| [Binned photon traces (MCS)](22_binned_photon_traces.md) | `trace_browser`, TTTR binning |
| [Accessible-volume (AV) calculations](23_accessible_volume.md) | `core.structure.av`, `fps_json_editor` |
| [Confocal scan images (CLSM)](24_scan_images.md) | `tttrlib.CLSMImage`, `plugins/microscopy` |
| [RCM from FRET-labelled samples (PIE/ALEX)](25_rcm_from_fret_samples.md) | `fret/calibration.py`, `burst/es.py` |
| [2-D peak fitting](26_2d_peak_fitting.md) | `burst_selection` GMM features |
| [Complete µs-ALEX smFRET workflow](27_alex_smfret_workflow.md) | `BurstWorkflow` facade |
| [Selecting & comparing FRET populations](28_selecting_fret_populations.md) | `Bursts.table`, `burst_selection` |
| [FRET-efficiency histogram fitting](29_fret_histogram_fitting.md) | Gaussian mixture on `E` |
| [H2MM: complete workflow & results](30_h2mm_workflow_results.md) | `burst_h2mm.core.analysis` |
| [H2MM: simulating & validating](31_h2mm_simulation_validation.md) | `BurstWorkflow.simulate`, `burst_h2mm` |
| [ns-ALEX / PIE: FRET + stoichiometry + lifetime](32_nsalex_lifetime.md) | burst nanotimes, E–τ plot |
| [Working with timestamps and bursts](33_timestamps_and_bursts.md) | `tttrlib.TTTR`, burst index ranges |
| [Exporting burst data](34_exporting_burst_data.md) | burst tables, `burst_h2mm` export, `bid_to_analysis` |
| [Combining measurements / repeats](35_combining_repeats.md) | `BurstWorkflow.register_all` |
| [Multispot (8-spot) smFRET](36_multispot.md) | per-channel burst analysis |
| [TAC linearization: microtime LUTs](37_tttr_microtime_lut.md) | `tttr_lut_tools` plugin, `staging.open_tttr` |
| [Two-channel colocalization](38_colocalization.md) | `img_coloc` plugin, `imaging.colocalization` |
| [Number & Brightness](67_number_and_brightness.md) | `img_pixel_nb` plugin, `imaging.number_brightness` |
| [Parameter uncertainty: priors, sampling, convergence](39_parameter_uncertainty.md) | `fitting.priors`, `fitting.sample`, `fitting.diagnostics`, `fitting.reweight`, `fitting.graphview` |
| [The AI assistant: operating ChiSurf in plain language](40_ai_assistant.md) | `chisurf.core.agent`, agent skills |
| [Asking the documentation](70_ask_the_documentation.md) | Help browser **Ask** panel, `csc help ask`, `help.docs.ask` |
| [Accurate FRET: automatic correction factors](41_accurate_fret.md) | `accurate_fret` plugin, `fret.accurate`, `fret.lines` |
| [κ² distributions: how much is the orientation assumption costing?](61_kappa2_distribution.md) | `kappa2_dist` plugin, `fluorescence.anisotropy.kappa2` |
| [Three-colour PDA (PDA3c)](42_pda3c.md) | `core.models.pda3c`, `core.fluorescence.pda3c`, `core.fluorescence.kinetics` |
| [Drift correction](43_drift_correction.md) | `img_drift` plugin, `imaging.drift` |
| [The molecular viewer (ChiMOL)](44_molecular_viewer.md) | `chimol` plugin, PyMOL-compatible commands, `get_area` |
| [Planning a scan: which dwell time measures D best?](45_scan_precision.md) | `rics_precision` calculator, `experiments.ics.precision` |
| [Exploring & fitting multidimensional data (ndX)](46_ndxplorer.md) | `ndxplorer`, `ndxplorer.analysis.curve_fit`, `chisurf.core.support.expressions` |
| [From a selection to a fit: the ndX bridges](47_ndxplorer_bridges.md) | `ndxplorer.analysis.burst_bridge`, `pda.from_bursts`, `burst_fcs.*`, `burst_mle.*` |
| [Regions: selecting pixels, measuring what you selected](48_regions.md) | `chisurf.core.roi`, `regionprops`, `region_mle --roi` |
| [Photon-by-photon kinetics: rates without binning](49_photon_by_photon_kinetics.md) | `burst_gs` plugin, `core.fluorescence.burst.gopich_szabo` |
| [Particle tracking: from spots to a diffusion coefficient](50_particle_tracking.md) | `img_tracking` plugin, `imaging.tracking` |
| [Image resolution: measuring it from the image itself](51_frc_resolution.md) | `img_frc` plugin, `imaging.frc` |
| [Sending a gated burst population to FCS, TCSPC, PDA or PCH](52_send_bursts_to_analysis.md) | ndX bridge, `*.from_bursts` services |
| [Reusing results: when a step recomputes](53_reusing_results.md) | `chisurf.core.runtime.analysis_cache`, burst workflow steps |
| [Inspecting a container: what is in a .pto](63_pto_inspector.md) | `pto_inspector` plugin, `core.fio.pto`, `core.plugin.operations`, `csg_pto_inspect` |
| [Hidden Markov models of binned traces](54_hidden_markov_models.md) | `hmm` plugin, `chisurf.core.math.hmm`, `csc hmm` |
| [Pair correlation and flow maps: where molecules go](55_pair_correlation.md) | `experiments.ics.pair_correlation`, `experiments.ics.flow_map` |
| [FCS saturation and focal-volume expansion](56_fcs_saturation.md) | `fcs_saturation` calculator, `FCS (kinetics)` model, `chisurf.core.fluorescence.fcs.saturation` |
| [Fitting an MFD burst histogram](57_mfd_fitting.md) | `MFD` experiment, `MFD 2D` model, `chisurf.core.fluorescence.mfd` |
| [Fusing bursts the same molecule produced](58_burst_fusion.md) | `burst_fusion` plugin, `core.fluorescence.burst.fusion`, `csc fusion` |
| [Global analysis: linking parameters across fits](60_global_analysis.md) | `fitting.fit.link_parameter`, `core.models.global_model`, `globalview` plugin |
| [Maximum-entropy decay analysis](62_maxent_decay.md) | `maxent_decay` plugin, `tcspc_maxent_*` descriptions, `math.regularization` |
| [Driving ChiSurf from its console](59_console.md) | `chisurf.gui.chinsole`, `chisurf.core.console`, `cs.fits`, `%run -i` |
| [Notebooks that run inside ChiSurf](64_notebooks.md) | Code Editor `.ipynb` tabs, `code_editor.notebook_editor`, `core.console.shell` |
| [Accurate FRET: calibration](fret_calibration.md) | `accurate_fret` plugin, `fret.calibration` |
| [IRF estimation](irf_estimation.md) | `irf_estimation`, TCSPC nuisances |
| [Photon-by-photon HMM (H2MM)](h2mm.md) | `burst_h2mm` plugin |

## Regenerating the figures

```bash
pixi run -e docs python docs/guides/make_figures.py   # regenerate all figures
```

GUI screenshots (e.g. tutorial 37) are regenerated separately from the real
widgets under an offscreen Qt platform (needs the full GUI environment):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python docs/guides/make_screenshots.py
```

or, outside pixi, with the project on the path:

```bash
PYTHONPATH=. python docs/guides/make_figures.py
```

All lengths in the polymer tutorials are in Ångström, FCS lag times in seconds
(displayed in ms), and diffusion coefficients in µm²/s.
