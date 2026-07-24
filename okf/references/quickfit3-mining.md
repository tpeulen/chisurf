---
type: Reference
title: QuickFit3 mining — algorithms & models for chisurf
description: Survey of 80+ QuickFit3 plugins for portable algorithms, models, and UI patterns; ranked by value/effort against chisurf's coverage. Reuses formulas as documented prior art per fcs-pam-port.md pattern.
tags: [reference, fcs, imaging, algorithms, roadmap]
timestamp: '2026-07-24T00:00:00Z'
---

# QuickFit3 mining — algorithms & models for chisurf

QuickFit3 (Krieger & Langowski, DKFZ B040; GPL3/LGPL2.1) is a Qt/C++ project-manager-plus-plugins application for FCS, imaging-FCS, and biophysics data evaluation. ChiSurf maintains a full local checkout at `junk/quickfit3/`. This document mines its ~80 plugins for algorithms, models, and workflows that chisurf does not yet have, following the **[fcs-pam-port.md](fcs-pam-port.md)** precedent: formulas and algorithms are documented prior art, reimplemented independently in chisurf's Python/PyQt5 codebase, never verbatim code copies. Licensing: GPL3/LGPL2.1 reuse is formula/algorithm only, with proper attribution to QuickFit3 help docs and plugin source.

## Path index

Every surveyed QuickFit3 plugin directory, mapped to topic, chisurf equivalent (if any), and verdict:

| QuickFit3 Path | Topic | ChiSurf Equivalent | Verdict | Value |
|---|---|---|---|---|
| `plugins/fcsfit` | FCS model library | `chisurf/core/models/fcs/` | Partial-gap (gaps: afterpulsing, stretch-factor, cross-section, flow+photophysics) | 3 |
| `plugins/fccsfit` | FCCS model library | `chisurf/core/models/fcs/` + `plugins/burst/*` | Partial-gap (missing: forward-watching, spatial/temporal separation variants) | 3 |
| `plugins/fitfunction_general` | Generic math functions | scipy, numpy | Already-covered | 1 |
| `plugins/fitfunction_fcsdistribution` | Distribution-based FCS | `chisurf/plugins/fcs/flc_2d/` | Low-priority (deprecated in QF3; discrete components preferred) | 2 |
| `plugins/fitfunction_2ffcs` | Two-focus FCS models | `okf/references/two-focus-fcs.md` | Partial-gap (documented but NOT implemented; 4 models) | 4 |
| `plugins/fitfunction_dls` | Dynamic light scattering | — | Clear-gap (no DLS support in chisurf) | 3 |
| `plugins/fitfunction_tirfcs` | TIRF-FCS models (evanescent) | — | **CLEAR-GAP** (20+ models; surface confinement, 2D pixel model) | **5** |
| `plugins/fitfunction_spimfcs` | SPIM-FCS models (thin-sheet) | — | **CLEAR-GAP** (50+ models; sheet geometry, split factor, pixelated camera) | **5** |
| `plugins/fitfunctions_lightsheet` | Lightsheet PSF helpers | — | Low-priority (supporting functions; lightsheet out-of-scope) | 2 |
| `plugins/fitalgorithm_fit_gsl` | GSL fit algorithms (BFGS, simplex) | `chisurf/core/fitting/` | Partial-gap (lacks derivative-free simplex fallback, multi-algorithm choice) | 3 |
| `plugins/fitalgorithm_fit_lmfit` | LMFit (Levenberg-Marquardt) | `chisurf/core/fitting/` | Redundant with existing MINPACK leastsq | 1 |
| `plugins/fitalgorithm_fit_nlopt` | NLOpt (global optimization) | — | **CLEAR-GAP** (DIRECT, StoGO, MLSL, ISRES for multi-modal landscapes) | **4** |
| `plugins/fitalgorithm_levmar` | Levmar (LM with native bounds) | `chisurf/core/fitting/` | Partial-gap (cleaner covariance pipeline; redundant capability) | 2 |
| `plugins/fitalgorithm_simanneal` | Simulated annealing (global, adaptive per-param step) | — | **CLEAR-GAP** (adaptive velocity vector for each parameter independently) | **4** |
| `plugins/curve_fit` | Fit evaluation & UI dispatch | `chisurf/core/fitting/` | Already-covered (UI integration) | 1 |
| `plugins/imagingfcs` | Spatial ACF/CCF from image series | — | **CLEAR-GAP** (no pixel-lag spatial correlator; bleach/background correction missing) | **5** |
| `plugins/imfcsfit` | Imaging FCS model fitting | — | **CLEAR-GAP** (blocked by imaging ACF; spatial D, F, τ_D extraction) | **4** |
| `plugins/imfccsfit` | Imaging FCCS (cross-correlation) | — | **CLEAR-GAP** (spatial FCCS + crosstalk matrix + intensity balance) | **4** |
| `plugins/numberandbrightness` | Number & Brightness (N&B) analysis | `chisurf/plugins/microscopy/img_pixel_nb/` | Partial-gap (~95% covered; missing: background UI, EMCCD gain visibility, histogram overlays) | 2 |
| `plugins/imagestack` | 3D image stack viewer | AutoForm `image` section | Partial-gap (~70% covered; missing: true volumetric rendering, orthogonal planes) | 2 |
| `plugins/photoncounts` | Single-photon counting histograms | `chisurf/plugins/microscopy/img_pixel_intensity/` | Partial-gap (~80% covered; missing: photon-by-photon stats, dead-time, drift QC) | 2 |
| `plugins/qfevalbeadscanpsf` | PSF fitting from bead scans | `chisurf/plugins/microscopy/psf_determination/` | Partial-gap (basic PSF covered; missing: 1D slice-by-slice analysis, beam-width profiling) | 2.5 |
| `plugins/qfevalcameracalibration` | Camera gain, offset, QE correction | — | **CLEAR-GAP** (per-pixel gain maps, noise-weighted thresholding, excess-noise modeling) | **4** |
| `plugins/qfevalcolocalization` | Colocalization (Pearson PCC, Manders MOC) | — | **CLEAR-GAP** (no correlation metrics, scatter-plot UI, automatic thresholding) | **4** |
| `plugins/qfe_alexeval` | ALEX burst analysis, S-vs-E 2D | `chisurf/plugins/burst/*` | Partial-gap (has BVA; missing: S-vs-E 2D density, GMM mixture fitting, explicit stoichiometry UI) | **4** |
| `plugins/qfe_fcssimulator` | FCS correlation-curve simulator (external diffusion4) | `chisurf/plugins/fcs/fcs_lfcs_sim/` | Different paradigm (correlation vs. single-photon stochastic); skip | 2 |
| `plugins/qfe_alexcontrol` | ALEX hardware control (NI DAQmx) | — | **EXCLUDED** (hardware-dependent; chisurf is software-only) | — |
| `plugins/alv_autocorrelator5000` | ALV correlator import (hardware correlator) | tttrlib | Superseded by tttrlib | 1 |
| `plugins/tcspcimporter` | Generic TCSPC importer + correlator | tttrlib | Superseded by tttrlib | 1 |
| `plugins/picoquantimporters` | PicoQuant PTU/PT3/T3R import | tttrlib | Superseded by tttrlib | 1 |
| `plugins/bhimporters` | Becker & Hickl .sdt/.spc/.set import | tttrlib | Superseded by tttrlib | 1 |
| `plugins/importers_simpletcspcimporter` | Text/CSV TCSPC import | chisurf staging | Superseded by tttrlib | 1 |
| `plugins/qfqtimageimporter` | Qt image format import | tttrlib, PIL | Superseded by tttrlib/PIL | 1 |
| `plugins/rdrsettings` | Settings .ini viewer | — | N/A (diagnostic tool) | 1 |
| `plugins/qfe_plotterexportercairo` | Cairo/PDF/EPS/PS/SVG export | — | **CLEAR-GAP** (no publication-quality vector export; paint-device adapter pattern instructive) | **4** |
| `plugins/qfe_plotterexporterlatex` | LaTeX/TikZ/PGF export | — | **CLEAR-GAP** (no LaTeX vector export; enables reproducible paper figures) | **4** |
| `plugins/qfe_dataexportbasics` | CSV/SYLK/MATLAB export | pandas, scipy.io | Partial-gap (CSV via pandas; missing: MATLAB .mat, value-error pair export) | 2 |
| `plugins/qfe_dataexportbasics_xlsx` | Excel XLSX export | openpyxl | Clear-gap (missing: role-based export, median-quantile pairs) | 2 |
| `plugins/qfe_spectraviewer` | Spectral optical viewer (FRET/spillover) | `chisurf/plugins/spectra_downloader` | **CLEAR-GAP** (database only; missing: spillover matrix UI, FRET predictor, optical overlap visualization) | **4** |
| `plugins/qfe_calculator` | General-purpose calculator | `chisurf/plugins/calculator` | Partial-gap (domain-specific only; missing: general math expression UI) | 3 |
| `plugins/qfe_resultstools` | Post-fit result combiner | — | Low-priority (domain-specific workflow) | 2 |
| `plugins/qfe_gslmathparserextensions` | GSL math functions | scipy.special | Low-priority (scipy sufficient) | 2 |
| `plugins/qfe_helpeditor` | Online help editor | Sphinx/Markdown docs | N/A (chisurf uses Sphinx) | — |
| `plugins/spim_lightsheet_eval` | Lightsheet microscopy analysis | — | N/A (specialized microscopy, out-of-scope) | — |
| `plugins/table` | Spreadsheet + plotting + formula UI | AutoForm `table` section | Partial-gap (missing: formula editor, histogram dialog, curve-fit UI, 17+ graph types) | **4** |
| `lib/qfmathtools.h` | Robust statistics (median, MAD, quantiles) | scipy.stats, hand-rolled | **CLEAR-GAP** (masked-aware median/MAD/quantiles, template specialization) | **4** |
| `lib/qfmathtools.h` | Error propagation (arithmetic, trig functions) | Scattered across modules | Clear-gap (no centralized error propagation) | 3 |
| `lib/qfweightingtools.h` | Weighting scheme selector (running stddev, poly) | `chisurf/core/fitting/` | Partial-gap (missing: predefined weighting combobox, running-stddev options) | 2 |
| `lib/qffitfunction*.h` | Fit function base classes | `chisurf/core/models/base.py` | Already-covered (API patterns align) | 1 |
| `lib/qffitalgorithm*.h` | Fit algorithm base classes | `chisurf/core/fitting/` | Already-covered | 1 |
| `libqf3widgets/qfenhancedtableview.h` | Enhanced table view (multi-sort, copy, export) | `chisurf/plugins/filtered_table.py` | **CLEAR-GAP** (missing: Excel export with value-error columns, role-based export, MATLAB format) | **4** |
| `lib/datatools.h` | CSV/MATLAB/binary data I/O | pandas, scipy.io | Partial-gap (CSV via pandas; missing: MATLAB interop, compact binary formats) | 2 |
| `extlibsb040/processing_chain/we_correlator.h` | Multi-tau correlator core (hardware pipeline) | tttrlib `Correlator` | **CLEAR-GAP** (reference for future performance optimization; proven multi-tau lag binning) | **5** |
| `lib/qfhistogramservice.h` | Histogram visualization service | pyqtgraph plots | Partial-gap (no centralized histogram registry/service) | 2 |
| `lib/qfparametercorrelationservice.h` | Parameter correlation heatmap | Fit toolbox | N/A (niche diagnostic tool) | 2 |
| `libqf3widgets/qfdoublerangeedit.h` | Range slider, elided labels | AutoForm spinboxes | Partial-gap (missing: range-slider variant) | 2 |
| `libqf3widgets/qffitfunctionselectdialog.h` | Fit function selection combobox | model_editor seam | Already-covered | 1 |

## Candidates worth porting — ranked by value/effort

### Tier 1: HIGHEST PRIORITY (value 5/5, clear gaps in core science)

1. **TIRF-FCS models** (`fitfunction_tirfcs`)
   - **What**: 20+ FCS models for total-internal-reflection fluorescence (evanescent wave). Surface confinement, 2D pixelated camera detection, anomalous + TIRF hybrid, flow under evanescent field.
   - **Key formulas**: `plugins/fitfunction_tirfcs/qffitfunctionstirfcsdiffe2.h` lines 45–127 (erf integral for pixel boundaries, surface-projected PSF)
   - **Where to land**: New models in `chisurf/core/models/fcs/models.yaml` + coded `tirfcs.py` (2D PSF requires integration)
   - **Effort**: 2–3 PRD cycles (models ported; new PSF convolution kernel)
   - **Why**: TIRF is a standard technique for membrane biology; high-value for live-cell FRET

2. **SPIM-FCS models** (`fitfunction_spimfcs`)
   - **What**: 50+ FCS models for Selective Plane Illumination Microscopy (thin-sheet geometry). Sheet width/position effects, 3D diffusion under confinement, multi-geometry variants (xy/xz separation), pixelated camera.
   - **Key formulas**: `plugins/fitfunction_spimfcs/qffitfunctionsspimfcsdiffe2.cpp` lines 75–129 (sheet convolution, split factor `fac_z`, effective volume factorization)
   - **Where to land**: New models in `chisurf/core/models/fcs/models.yaml` + `spimfcs.py` (sheet PSF kernel)
   - **Effort**: 3–4 PRD cycles (large model suite; sheet geometry adds complexity)
   - **Why**: SPIM is increasingly common for 3D tissue imaging; enables volumetric FCS

3. **Imaging FCS spatial correlator** (`imagingfcs`)
   - **What**: Pixel-lag autocorrelation/cross-correlation from time-series image stacks. Multi-tau binning (Schätzel et al. 1995) on spatial lag instead of temporal lag; bleach correction (exponential + polynomial variants); background removal; ROI/mask selection.
   - **Key algorithm files**: 
     - `plugins/imagingfcs/qfrdrimagingfcscorrelationjobthread.h` lines 44–65 (correlator types, bleach/background enums)
     - `extlibsb040/processing_chain/we_correlator.h` (multi-tau core)
   - **Where to land**: New `chisurf/plugins/fcs/imaging_fcs_correlator/` RPC backend + AutoForm GUI
   - **Effort**: 2 PRD cycles (correlator is ~400 lines; bleach pipeline + ROI UI ~600 lines)
   - **Why**: Enables spatial-dynamics science (diffusion, Turing patterns, etc.); high impact for imaging-FCS users

4. **Multi-tau correlator reference implementation** (`lib/we_correlator.h`)
   - **What**: Fast, proven multi-tau lag-binning algorithm for FCS autocorrelation. Schätzel et al. 1995 parameter tuning (P, M, S, K); real-time correlator pipeline.
   - **Key file**: `extlibsb040/StatisticsTools/multitau-correlator.h` (template class)
   - **Where to land**: Reference for tttrlib optimizations; consider Numba/Cython port for `chisurf/core/fluorescence/fcs/correlate.py` if profiling shows bottleneck
   - **Effort**: 1–2 PRD cycles (profiling + optimization only if needed)
   - **Why**: Foundation for real-time FCS; future embedded device support

### Tier 2: HIGH-VALUE FOLLOW-UPS (value 4/5, enabling gaps)

5. **NLOpt global optimization** (`fitalgorithm_fit_nlopt`)
   - **What**: Wrapper for libnlopt (8+ algorithms): DIRECT, DIRECT-L, DIRECT-L-RAND (global divide-and-conquer), CRS2_LM, StoGO, ISRES (evolution strategy), ESCH, MLSL (multi-level single-linkage with embedded local solver). Box constraints native, adaptive damping.
   - **Key file**: `plugins/fitalgorithm_fit_nlopt/qffitalgorithmnlopt{base,algorithms}.*`
   - **Where to land**: New `chisurf/core/fitting/nlopt_wrapper.py` (ctypes or cython binding to libnlopt)
   - **Effort**: 2–3 weeks (C extension + scipy compatibility layer)
   - **Why**: Solves multi-modal fitting (multi-component kinetics, FRET networks); recovery from poor initializations

6. **Simulated annealing** (`fitalgorithm_simanneal`)
   - **What**: Stochastic global minimizer (Corana et al. 1987) with **adaptive per-parameter velocity** (unique feature). Metropolis-Hastings acceptance, adaptive cooling, per-parameter tuning (NS, NT, RT, C).
   - **Key file**: `plugins/fitalgorithm_simanneal/fitalgorithm_simanneal.cpp`
   - **Where to land**: Pure Python port to `chisurf/core/fitting/simanneal.py` (~400 lines)
   - **Effort**: 1–2 weeks (straightforward Python port)
   - **Why**: Excellent fallback after LM plateau; per-parameter adaptive step is novel

7. **Imaging FCCS + crosstalk** (`imfccsfit`)
   - **What**: Cross-correlation fitting for spatial FCCS (multi-color). Crosstalk/spectral-bleed-through correction, dual-channel intensity balance, relative CCF normalization.
   - **Key file**: `plugins/imfccsfit/qfimfccsfitevaluation*.h` (crosstalk dialog, relative CCF)
   - **Where to land**: Extend imaging FCS plugin (Tier 1 #3) + add crosstalk matrix solver
   - **Effort**: 2 PRD cycles (reuse imaging ACF + add crosstalk solver)
   - **Why**: Enables multi-color live-cell FRET dynamics

8. **Imaging FCS model fitting** (`imfcsfit`)
   - **What**: Model fitting to spatial ACF curves; extracts D, F, τ_D, binding parameters for imaging FCS.
   - **Key file**: `plugins/imfcsfit/qfimfcsfitevaluation.h`
   - **Where to land**: Reuse `chisurf/core/models/fcs/` + adapt for spatial lag instead of time lag
   - **Effort**: 1 PRD cycle (~70% framework reuse)
   - **Why**: Completes imaging-FCS analysis loop (ACF → parameters)

9. **S-vs-E 2D analysis (ALEX)** (`qfe_alexeval`)
   - **What**: 2D stoichiometry-vs-FRET-efficiency histograms with density contours and GMM/EM mixture fitting. Explicit crosstalk/direct-excitation/duty-cycle corrections; background subtraction per excitation period.
   - **Key formulas**: `plugins/qfe_alexeval/analysis.cpp` lines 29–138 (FRET corrections with gamma factor, stoichiometry both photon-count and intensity variants)
   - **Where to land**: Extend `chisurf/plugins/burst/burst_analysis/` + add 2D histogram UI, GMM fitting
   - **Effort**: 2 weeks (stoichiometry math ~100 lines; 2D contour/GMM UI ~500 lines)
   - **Why**: Identifies population substructure (incomplete labeling, conformational states)

10. **Camera calibration** (`qfevalcameracalibration`)
    - **What**: Per-pixel gain, offset, QE mapping; noise characterization (read noise + shot-noise profile); excess-noise modeling (EMCCD).
    - **Key file**: `plugins/qfevalcameracalibration/qfevalcameracalibration_item.cpp` lines 85–210
    - **Where to land**: New `chisurf/plugins/microscopy/camera_calibration/` RPC service + AutoForm UI
    - **Effort**: 1 week (algorithm is simple aggregation; no fitting)
    - **Why**: Essential for quantitative microscopy; enables downstream intensity corrections

11. **Colocalization metrics** (`qfevalcolocalization`)
    - **What**: Pearson correlation coefficient (PCC), Manders overlap coefficient (MOC); automatic background subtraction (5% quantile); interactive ROI selection via scatter plot.
    - **Key formulas**: `plugins/qfevalcolocalization/qfevalcolocalization_item.cpp` (PCC, MOC equations)
    - **Where to land**: New `chisurf/plugins/microscopy/colocalization/` plugin (backend RPC + AutoForm UI)
    - **Effort**: 1 week (algorithms ~50 lines; UI ~300 lines)
    - **Why**: Standard for multi-color validation; high utility for multi-channel workflows

12. **Robust statistics library** (`lib/qfmathtools.h`)
    - **What**: Median, Median Absolute Deviation (MAD), normalized MAD (NMAD), quantiles (25th/75th), masked variants (NaN handling), template specialization.
    - **Key functions**: `qfstatisticsMedian()`, `qfstatisticsMAD()`, `qfstatisticsQuantile()`
    - **Where to land**: New `chisurf/core/math/robust_stats.py` (NumPy/Numba port)
    - **Effort**: 2–3 days (straightforward translation)
    - **Why**: Standard for outlier-resistant analysis; reusable across plugins (fitting, histogram, drift detection)

13. **Cairo/LaTeX vector export** (`qfe_plotterexporter*`)
    - **What**: Publication-quality export to PDF, EPS, PS, SVG, TikZ/PGF via paint-device adapter pattern (pluggable backends). Exact font/color preservation.
    - **Key architecture**: `plugins/qfe_plotter*/jkqtcairoengineadapter.{h,cpp}`, `jkqtplatexengineadapter.{h,cpp}` (paint-device pattern)
    - **Where to land**: Extend pyqtgraph plotter (or use Matplotlib backends which already support Cairo/LaTeX)
    - **Effort**: 2 weeks (Matplotlib already has backends; wire into pyqtgraph)
    - **Why**: Reproducible paper figures; high user expectation (Academia loves LaTeX)

14. **Enhanced table export** (`libqf3widgets/qfenhancedtableview.h`)
    - **What**: Multi-column sort, filtering, copy-to-clipboard with format preservation; role-based export (EditRole, ErrorRole, MedianRole, QuantileRole); HTML/Excel/MATLAB/CSV output with value-error pairs.
    - **Key methods**: `toHtml()`, `copySelectionToExcel()`, `copySelectionAsValueErrorToExcel()`, `print()`
    - **Where to land**: Extend `chisurf/plugins/filtered_table.py` (add role-aware export methods)
    - **Effort**: 1–2 weeks (mostly DataFrame operations via pandas/openpyxl)
    - **Why**: Productivity multiplier; users demand error-column export

15. **Spectra viewer** (`qfe_spectraviewer`)
    - **What**: Interactive spectral database UI with spillover matrix calculator, FRET efficiency predictor, detector config editor, wavelength-driven optical overlap visualization. 9 sub-components (fluorophore/filter/detector/light-source editors).
    - **Key file**: `plugins/qfe_spectraviewer/` (9 dialogs, spectrum aggregation)
    - **Where to land**: Extend `chisurf/plugins/spectra_downloader/` (add UI panels, FRET/spillover calculator)
    - **Effort**: 3–4 weeks (9 components; cross-linked dialogs)
    - **Why**: Enables optical design workflows; interactive planning (what dyes/filters for this experiment?)

16. **Table with formula editor** (`plugins/table`)
    - **What**: Spreadsheet-like table with formula-driven columns, histogram dialog, curve-fit UI, 17+ graph types, inline expressions.
    - **Key file**: `plugins/table/qfrdrtable.h/cpp` (~3500 lines)
    - **Where to land**: Extend AutoForm `table` section (add formula parser, graph types)
    - **Effort**: 3–4 weeks (sympy backend for math parser; graph variants)
    - **Why**: Data exploration; power-user feature

### Tier 3: MEDIUM-VALUE REFINEMENTS (value 3/5, optional enhancements)

17. **Error propagation utility** (`lib/qfmathtools.h`)
    - **What**: Closed-form derivatives for error calc (division, power, sqrt, trig). $f = a·b \to Δf = \sqrt{(Δa·b)² + (Δb·a)²}$
    - **Where to land**: `chisurf/core/math/error_propagation.py`
    - **Effort**: 1 week
    - **Why**: Useful for parameter-editor tooltips, report generation

18. **Derivative-free simplex fallback** (`fitalgorithm_fit_gsl`)
    - **What**: Nelder-Mead simplex for models where Jacobian unavailable/noisy.
    - **Where to land**: Add to `chisurf/core/fitting/` as fallback after LM failure
    - **Effort**: 1 week (scipy.optimize already has this; just wire it in)
    - **Why**: Robustness for edge cases

### Tier 4: LOWER-PRIORITY GAPS (value 1–2, either already covered or niche)

- **DLS (Dynamic Light Scattering)** models (3/5) — TCSPC-centric; lower-priority
- **Two-focus FCS models** (4/5) — Documented in `okf/references/two-focus-fcs.md` but NOT implemented; blocked by higher-priority model suites
- **Distribution-based FCS** (2/5) — Deprecated in QuickFit3; discrete-component fits preferred
- **Import/correlators** (1/5 each) — Fully superseded by tttrlib
- **Excel/MATLAB/CSV export** (2/5) — scipy.io + openpyxl + pandas sufficient
- **General-purpose calculator** (3/5) — Niche; `chisurf/plugins/calculator` covers domain-specific needs
- **Histogram service interface** (2/5) — Chisurf's modular design already decoupled
- **Weighting combobox** (2/5) — Low-effort UI polish; defer to iteration cycle
- **Parameter correlation heatmap** (2/5) — Niche diagnostic tool
- **N&B UI polish** (2/5) — Core math 95% done; missing background-picker UX

## Already-covered (do not re-investigate)

- GSL/LMFit fit algorithms (redundant with MINPACK `leastsqbound`)
- MaxEnt (Skilling-Gull entropy identical to `flc_2d`; QuickFit3's fixed-point iteration is inferior to chisurf's L-BFGS-B)
- Basic FCS model library (13 models ported from PAM, A/B-verified in `test/fitting/test_fcs_pam_ab.py`)
- FLCS lifetime filters (core weighted-pseudo-inverse math already ported; channel-aware filtering done)
- Fit function/algorithm base classes (chisurf's `core/models/base.py` and `core/fitting/` already have equivalent architecture)
- Number & Brightness core math (95% implemented in `chisurf/plugins/microscopy/img_pixel_nb/`)
- Image stack 3D viewer (AutoForm `image` section supports 3D stacks + click-pick + markers + ROI)
- PSF 3D Gaussian fitting (basic bead-scan + 3D fit already in `plugins/microscopy/psf_determination/`)
- TTTR data import (tttrlib fully supersedes all QuickFit3 importers)

## Excluded (hardware-dependent, out-of-scope)

ChiSurf is a data-analysis package, not instrument control. The following QuickFit3 plugins are excluded:

- `b040_ffmcontrol` — Laser control (NI-DAQmx firmware)
- `cam_*` (Andor, RadHard, server, testcamera) — EMCCD/CMOS camera drivers
- `lights_*` (Cobolt laser, PCCS LED) — Laser/LED control
- `meas_*` (B040 resheater, SPAD measurement) — Temperature/detector control
- `multicontrol_stage` — Motorized stage control
- `servo_*`, `shutter_*` (Arduino servos, relais shutters) — Mechanical control
- `spimb040` — SPIM microscope hardware stack (companion to SPIM-FCS, but requires hardware)
- `stage_*` (PI, Pololu) — Stage drivers
- `qfe_acquisitiontest`, `qfe_nidaqmxreader` — Acquisition/DAQmx only

**Rationale**: These are instrument-specific and do not port to chisurf's software-only architecture. New hardware integrations (if needed) follow chisurf's RPC service pattern, not monolithic plugins.

## Pointers

- **FCS models & formulas**: [fcs-pam-port.md](fcs-pam-port.md) (PAM reference port, A/B-verified; related work)
- **Two-focus FCS status**: [two-focus-fcs.md](two-focus-fcs.md) (Dertinger MDF gaps, Gaussian form ported)
- **FCS & FLCS infrastructure**: `chisurf/core/models/fcs/`, `chisurf/core/fluorescence/fcs/`
- **Imaging/microscopy plugins**: `chisurf/plugins/microscopy/{sm_image_mle,imaging_common,imaging_tools}`, `chisurf/plugins/fcs/fcs_lfcs_sim`, `chisurf/plugins/burst/*`
- **Fitting engine**: `chisurf/core/fitting/`, `chisurf/core/math/optimization/`
- **AutoForm framework**: PRD-40 (data-driven UI), `chisurf/gui/autoform/`, `chisurf/core/dataspec/`
- **Imaging PRDs**: PRD-49 (Imaging FLIM, done), PRD-52 (Phasor-FLIM, phase 3)
- **Burst & ALEX**: [fretica-gap-features-resume.md](../log.md) (2CDE, BVA, pending features)

## Implementation roadmap sketch

**Phase 1 (High-impact, foundational):**
1. Imaging FCS spatial correlator (bleach/background + multi-tau) — **New PRD-xx "Imaging FCS Correlation"**
2. Global optimization (NLopt + SA) — **Extend PRD-xx "Fit Algorithms"**
3. Camera calibration (gain/QE) + colocalization (PCC/MOC) — **Two small plugins, 1 week each**

**Phase 2 (FCS model suite):**
4. TIRF-FCS models (20+ with evanescent PSF)
5. SPIM-FCS models (50+ with sheet geometry)

**Phase 3 (Multi-color workflows):**
6. S-vs-E 2D analysis (ALEX GMM fitting)
7. Imaging FCCS + crosstalk

**Phase 4 (Polish & tools):**
8. Robust statistics, error propagation, enhanced table export, Cairo/LaTeX export, spectra viewer

This roadmap prioritizes scientific impact (imaging-FCS opens new microscopy paradigms) over breadth. Parallel work on PRD-40 (AutoForm) can absorb N&B UI and table enhancements.
