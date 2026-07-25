# Guides — how to do it in ChiSurf

```{toctree}
:hidden:
:glob:

*
```

Step-by-step guides for the fluorescence analyses in ChiSurf. Each guide shows
**how to run the analysis in the actual user interface** and links to the
matching {doc}`concept </concepts/index>` page for the underlying theory. Figures
are real output — matplotlib plots produced by [`make_figures.py`](make_figures.py)
from synthetic data using the very functions the guide describes, and GUI
screenshots grabbed from the real widgets by
[`make_screenshots.py`](make_screenshots.py) under an offscreen Qt platform.

Related how-to pages: [FRET calibration](fret_calibration.md),
[IRF estimation](irf_estimation.md), and [photon-by-photon HMM (H2MM)](h2mm.md).

| # | Tutorial | ChiSurf entry point |
|---|----------|---------------------|
| 1 | [FRET-2CDE / ALEX-2CDE burst dynamics](01_fret_2cde.md) | `tttrlib.TwoCDE`, `burst_2cde` plugin |
| 2 | [Recurrence analysis (RASP)](02_recurrence_rasp.md) | `core.fluorescence.burst.recurrence` |
| 3 | [Polymer inter-dye distance distributions](03_polymer_distance_distributions.md) | `rdf.saw_nu`, `rdf.ising_chain` |
| 4 | [FIDA — photon-counting histograms](04_fida_pch.md) | `core.models.pch.fida` |
| 5 | [Enderlein MDF & two-focus FCS](05_enderlein_mdf_two_focus_fcs.md) | `core.fluorescence.fcs.enderlein` |
| 6 | [ns-FCS second-order correlation](06_nsfcs_second_order.md) | `core.fluorescence.fcs.correlate.second_order_correlation` |
| 7 | [RCM detection calibration](07_rcm_calibration.md) | `core.fluorescence.fret.calibration.rcm_from_dye_solutions` |
| 8 | [Burst Variance Analysis (BVA)](08_burst_variance_analysis.md) | `tttrlib.BVA`, `burst_bva` plugin |
| 9 | [Diffusion FCS](09_diffusion_fcs.md) | FCS models + `fcs_correlator` plugin |
| 10 | [Lifetime & anisotropy decay fitting](10_lifetime_anisotropy_fitting.md) | `core.fluorescence.tcspc`, TCSPC models |
| 11 | [Photon Distribution Analysis (PDA)](11_pda.md) | `tttrlib.Pda`, `core.models.pda` |
| 12 | [Handling TTTR files (& Photon-HDF5)](12_handling_tttr_files.md) | `tttrlib.TTTR`, `plugins/tttr` |
| 13 | [Photon burst identification](13_burst_identification.md) | `TTTR.burst_search`, `burst_selection` |
| 14 | [Multi-parameter E–S & correction factors](14_multiparameter_es.md) | `burst/es.py`, `fret/calibration.py` |
| 15 | [Background rates](15_background_rates.md) | `burst/background.py`, `burst_background` |
| 16 | [FRET-FCS](16_fret_fcs.md) | FRET-FCCS models + correlator |
| 17 | [Filtered FCS (fFCS / 2D-FLCS)](17_filtered_fcs.md) | `fcs/filtered.py`, `flc_2d` |
| 18 | [TTTR simulation of diffusing particles](18_tttr_simulation.md) | `tttrlib.SimEngine` |
| 19 | [Photon-by-photon HMM (H2MM)](19_h2mm_hidden_markov.md) | `burst_h2mm`, `tttrlib.H2MM` |
| 20 | [HMM of binned traces (ebFRET)](20_ebfret_binned_hmm.md) | `burst_ebfret` |
| 21 | [Lifetime from photon bursts (MLE)](21_lifetime_from_bursts.md) | `core.fluorescence.mle`, `burst_mle_analysis` |
| 22 | [Binned photon traces (MCS)](22_binned_photon_traces.md) | `trace_browser`, TTTR binning |
| 23 | [Accessible-volume (AV) calculations](23_accessible_volume.md) | `core.structure.av`, `fps_json_editor` |
| 24 | [Confocal scan images (CLSM)](24_scan_images.md) | `tttrlib.CLSMImage`, `plugins/microscopy` |
| 25 | [RCM from FRET-labelled samples (PIE/ALEX)](25_rcm_from_fret_samples.md) | `fret/calibration.py`, `burst/es.py` |
| 26 | [2-D peak fitting](26_2d_peak_fitting.md) | `burst_selection` GMM features |
| | **End-to-end workflows** | |
| 27 | [Complete µs-ALEX smFRET workflow](27_alex_smfret_workflow.md) | `BurstWorkflow` facade |
| 28 | [Selecting & comparing FRET populations](28_selecting_fret_populations.md) | `Bursts.table`, `burst_selection` |
| 29 | [FRET-efficiency histogram fitting](29_fret_histogram_fitting.md) | Gaussian mixture on `E` |
| 30 | [H2MM: complete workflow & results](30_h2mm_workflow_results.md) | `burst_h2mm.core.analysis` |
| 31 | [H2MM: simulating & validating](31_h2mm_simulation_validation.md) | `BurstWorkflow.simulate`, `burst_h2mm` |
| 32 | [ns-ALEX / PIE: FRET + stoichiometry + lifetime](32_nsalex_lifetime.md) | burst nanotimes, E–τ plot |
| 33 | [Working with timestamps and bursts](33_timestamps_and_bursts.md) | `tttrlib.TTTR`, burst index ranges |
| 34 | [Exporting burst data](34_exporting_burst_data.md) | burst tables, `burst_h2mm` export, `bid_to_analysis` |
| 35 | [Combining measurements / repeats](35_combining_repeats.md) | `BurstWorkflow.register_all` |
| 36 | [Multispot (8-spot) smFRET](36_multispot.md) | per-channel burst analysis |
| 37 | [TAC linearization: microtime LUTs](37_tttr_microtime_lut.md) | `tttr_lut_tools` plugin, `staging.open_tttr` |
| 38 | [Two-channel colocalization](38_colocalization.md) | `img_coloc` plugin, `imaging.colocalization` |
| 41 | [Accurate FRET: automatic correction factors](41_accurate_fret.md) | `accurate_fret` plugin, `fret.accurate`, `fret.lines` |
| 39 | [Parameter uncertainty: priors, sampling, convergence](39_parameter_uncertainty.md) | `fitting.priors`, `fitting.sample`, `fitting.diagnostics` |

## Running

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
