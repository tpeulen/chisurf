---
type: Concept
title: The flrCIF and MMFDB vocabulary
description: Generated reference of the categories and items ChiSurf persists, defined in the mmfdb extension dictionaries.
tags: [concepts, database, mmfdb]
anchor: concept-flrcif-vocabulary
---

(concept-flrcif-vocabulary)=
# The flrCIF and MMFDB vocabulary

Everything ChiSurf and ndX persist is expressed in the PDB-IHM FLR dictionary
(flrCIF) plus two MMFDB extension dictionaries, `mmfdb_flr_ext.dic` and
`mmfdb_workflow_ext.dic`. The dictionaries are the schema authority; this page
is generated from them by `build_tools/docs/generate_flrcif_vocabulary.py`.
A declared analysis feature names one of these items as its `term`.
The [MMFDB admin guide](../guides/102_mmfdb_admin.md) shows where these records are browsed
and curated.


## `_flr_analysis_feature`

Computed per-event observables of an analysis -- the feature vocabulary behind burst summaries (.bur columns), per-pixel and per-region MLE tables and related exports. Distinct from flr_fit_parameter, which holds *fitted model parameters*: an analysis feature is measured or derived per burst / pixel / region, not optimised. This category is the central drift point the general rule demands: an analysis declaration file (e.g. chisurf burst_features.yaml, result_columns.yaml) may only use terms defined here or in flr_fit_parameter, so a new feature is created HERE first and the declarations reference it. Where flrCIF/PDBx defines an equivalent item, prefer that definition; these are the terms it does not carry.

| Item | Type | Description |
|---|---|---|
| `_flr_analysis_feature.analysis_block` | text | Data set of a graph fit: the measured lifetimes of one dye in the listed solvents, e.g. 'Atto655 in D2O and H2O'. |
| `_flr_analysis_feature.analysis_graph` | code | Name of the declared graph a quantity was fitted in: one joint solve of several data sets that share titration slopes (a quenching analysis' stage declaration). |
| `_flr_analysis_feature.area` | int | Region area, pixels. |
| `_flr_analysis_feature.bimolecular_quenching_constant` | float | Bimolecular (collisional) quenching constant kq = K_SV / tau0 of a dye-quencher pair, in 1e9/(M s) = 1/(M ns). Negative values are recorded as measured; they are not quenching. |
| `_flr_analysis_feature.bimolecular_quenching_constant_sd` | float | Standard deviation of the bimolecular quenching constant kq, 1e9/(M s). |
| `_flr_analysis_feature.centroid_col` | float | Column coordinate of a region's centroid, pixels. |
| `_flr_analysis_feature.centroid_row` | float | Row coordinate of a region's centroid, pixels. |
| `_flr_analysis_feature.circularity` | float | 4*pi*area/perimeter^2 of a region; 1 for a disc. |
| `_flr_analysis_feature.confidence_sigma` | float | Significance of the event's photon excess over the locally measured background, in standard deviations (0 when the engine does not provide it). |
| `_flr_analysis_feature.count_rate_khz` | float | Selected photons per duration, kilohertz (-1.0 for an empty selection). |
| `_flr_analysis_feature.dark_fraction` | float | Fraction of a dye ensemble that is dark: quenched below the shortest measurable lifetime, or statically quenched, so it does not contribute to the measured lifetime. |
| `_flr_analysis_feature.day_to_day_error_abs` | float | Absolute part of the day-to-day error of a Stern-Volmer constant, 1/M: the scatter between days beyond each day's regression error, shared by all titrations of an analysis. |
| `_flr_analysis_feature.day_to_day_error_rel` | float | Relative part of the day-to-day error of a Stern-Volmer constant, as a fraction of K_SV, shared by all titrations of an analysis. |
| `_flr_analysis_feature.diffusion_time_mean` | float | Mean FCS diffusion time in milliseconds: the weighted mean of a diffusion-time distribution, or the fitted time in a single-component diffusion fit. Recorded separately for each channel pair. |
| `_flr_analysis_feature.diffusion_time_peak` | float | Peak FCS diffusion time in milliseconds: the time at the maximum of the reported diffusion-time distribution, or the fitted time in a single-component diffusion fit. Recorded separately for each channel pair. |
| `_flr_analysis_feature.duration_ms` | float | Time between the event's first and last selected photon, milliseconds (-1.0 for an empty selection). |
| `_flr_analysis_feature.eccentricity` | float | Eccentricity of the ellipse with the region's second moments; 0 for a disc. |
| `_flr_analysis_feature.estimate_note` | text | Note on a parameter estimate: not determined (the interval spans most of the range), at the edge of its range, other regions possible (another near-optimal search lies outside the interval), fixed, or derived from the residuals. |
| `_flr_analysis_feature.file_name` | line | Name of the measurement file the event's photons belong to. |
| `_flr_analysis_feature.first_photon` | int | Index of the event's first photon in the measurement's photon stream (per detector: first photon of that detector within the event; -1 when the detector saw none). |
| `_flr_analysis_feature.id` | int |  |
| `_flr_analysis_feature.inlier_flag` | boolean | True when the measurement entered the joint fit, i.e. it was not flagged as an outlier by the robust search. |
| `_flr_analysis_feature.intensity_max` | float | Maximum intensity of the region in the underlying intensity image, counts. |
| `_flr_analysis_feature.intensity_mean` | float | Mean intensity of the region in the underlying intensity image, counts. |
| `_flr_analysis_feature.interval_method` | code | How an interval was obtained: laplace (16 and 84 % of the Gaussian at the best fit) or profile (where the profile deviance reaches 1). |
| `_flr_analysis_feature.last_photon` | int | Index of the event's last photon, inclusive (-1 when the selection is empty). |
| `_flr_analysis_feature.leave_one_out_coverage` | float | Fraction of left-out measurements that lie inside their one-standard-deviation error bar of the prediction from the others (about 0.68 for honest error bars). |
| `_flr_analysis_feature.leave_one_out_z` | float | Leave-one-out deviation of a measurement in standard deviations: measured minus predicted value when the measurement is left out of the fit, divided by the combined error. |
| `_flr_analysis_feature.lifetime_error_total` | float | Measurement error and model error of a lifetime added in quadrature, ns: how far a measured point may lie from its prediction. |
| `_flr_analysis_feature.lifetime_point_count` | int | Number of lifetime measurements that contribute to a statistic or a fitted line. |
| `_flr_analysis_feature.lifetime_series_count` | int | Number of solvent series (one labelled site and state measured at several heavy-water fractions) that contribute to a statistic. |
| `_flr_analysis_feature.ligand_state` | code | Conformational or ligand-binding state of the labelled macromolecule a measurement was taken in, e.g. APO (ligand-free) or HOLO (ligand-bound). |
| `_flr_analysis_feature.log_posterior` | float | Natural logarithm of the (unnormalised) posterior density a fit or a search reached. |
| `_flr_analysis_feature.mean_macro_time_ms` | float | Midpoint of the first and last selected photon's macro times, milliseconds. A midpoint, not a photon-weighted mean -- inherited from the reference .bur format. |
| `_flr_analysis_feature.mean_micro_time_ns` | float | Mean TCSPC micro time of the selected photons, nanoseconds (-1.0 when empty or the micro-time resolution is unknown). |
| `_flr_analysis_feature.measured_lifetime` | float | Average fluorescence lifetime of a dye on a labelled site, ns, as measured (or read from the site's solvent line at a given solvent composition). |
| `_flr_analysis_feature.measured_lifetime_sd` | float | Measurement error (standard deviation) of a measured site lifetime, ns. |
| `_flr_analysis_feature.measurement_date` | int | Calendar day a measurement was taken, written as yyyymmdd (e.g. 20260826). Distinguishes repeated titrations or series of the same sample. |
| `_flr_analysis_feature.measurement_relative_scatter` | float | Relative error of one lifetime measurement around its solvent line, in percent of the lifetime: the site's own scatter mixed with the dye's typical scatter. |
| `_flr_analysis_feature.model_error` | float | Model error of a lifetime prediction, ns: the error added in quadrature to the measurement error so that the residuals are consistent with their errors. |
| `_flr_analysis_feature.n_photons` | int | Number of selected photons in the event (0 for an empty selection). |
| `_flr_analysis_feature.outlier_flag` | boolean | True when the measurement, left out of the fit, is predicted more than the outlier limit (in error bars) off. |
| `_flr_analysis_feature.outlier_sites` | text | Labelled sites flagged as outliers, space separated. |
| `_flr_analysis_feature.perimeter` | float | Region perimeter, pixels. |
| `_flr_analysis_feature.pixel_col` | int | Column index of a pixel in an image analysis. |
| `_flr_analysis_feature.pixel_number` | int | Flattened pixel index, row * line_length + column. |
| `_flr_analysis_feature.pixel_row` | int | Row (line) index of a pixel in an image analysis. |
| `_flr_analysis_feature.predicted_lifetime` | float | Average fluorescence lifetime of a dye on a labelled site predicted by a quenching model, ns. |
| `_flr_analysis_feature.predicted_lifetime_high` | float | Predicted lifetime plus its standard deviation, ns. |
| `_flr_analysis_feature.predicted_lifetime_low` | float | Predicted lifetime minus its standard deviation, ns. |
| `_flr_analysis_feature.predicted_lifetime_sd` | float | Standard deviation of a predicted site lifetime from the parameter uncertainty, ns. |
| `_flr_analysis_feature.profile_deviance` | float | Profile deviance of a parameter held at a value: twice the increase of the least-squares cost over its minimum when every other parameter is refitted; 1 bounds the 68 % interval. |
| `_flr_analysis_feature.region_label` | int | Integer label of a segmented region in a label image. |
| `_flr_analysis_feature.relative_scatter_leave_one_out` | float | Root-mean-square leave-one-out residual of single lifetime measurements around their solvent lines, as a fraction of the lifetime, on the scale of the pooled scatter. |
| `_flr_analysis_feature.relative_scatter_pooled` | float | Pooled residual scatter of single lifetime measurements around their solvent lines, as a fraction of the lifetime (residual sum of squares over the pooled degrees of freedom). |
| `_flr_analysis_feature.relative_scatter_robust` | float | Robust scatter of single lifetime measurements, as a fraction of the lifetime: 1.4826 times the median absolute leave-one-out residual, not moved by one bad series. |
| `_flr_analysis_feature.search_rank` | int | Rank of one optimiser search among all searches of a multistart fit, 1 for the best log posterior. |
| `_flr_analysis_feature.solidity` | float | Region area divided by its convex-hull area. |
| `_flr_analysis_feature.solvent_exposure` | float | Solvent exposure of a dye position: the fraction of probe points on a sphere around the dye centre (dye radius plus a water radius) that are not covered by atoms of the macromolecule (Shrake-Rupley). |
| `_flr_analysis_feature.solvent_isotope` | code | Isotopic form of the solvent a quantity refers to: H2O (normal water) or D2O (heavy water). Heavy water does not quench most dyes, so the pair separates water quenching from quenching by the macromolecule. |
| `_flr_analysis_feature.stern_volmer_constant` | float | Stern-Volmer constant K_SV of a dye-quencher pair, 1/M: the slope of tau0/tau - 1 (or F0/F - 1) against the quencher concentration. |
| `_flr_analysis_feature.stern_volmer_constant_sd` | float | Standard deviation of the Stern-Volmer constant K_SV, 1/M (the regression error of one line, or the posterior standard deviation when several days are combined). |
| `_flr_analysis_feature.stickiest_residue_group` | code | Residue group (aromatic, hydrophobic, basic, acidic, polar) with the smallest determined slow factor, i.e. the group a dye sticks to most. |
| `_flr_analysis_feature.titration_day_count` | int | Number of independent titration days (separate samples and stock solutions) that contribute to a quenching constant. |
| `_flr_analysis_feature.water_access` | float | Water access of a labelled site: (1/tau(H2O) - 1/tau(D2O)) divided by the free dye's water quenching rate. 1 means as exposed to water as the free dye, 0 fully shielded. |
| `_flr_analysis_feature.water_access_model` | float | Water access of a labelled site from a model: (1/tau_H2O - 1/tau_D2O) of the predicted lifetimes divided by the free dye's water quenching rate; 1 means as accessible as the free dye. |
| `_flr_analysis_feature.water_access_model_sd` | float | Standard deviation of the model water access, propagated from the fit's covariance. |
| `_flr_analysis_feature.water_access_sd` | float | Standard deviation of the water access of a labelled site. |
| `_flr_analysis_feature.water_quenching_rate` | float | Water quenching rate kq_w of a dye, 1/ns: the slope of the decay rate 1/tau against the fraction of normal water (H2O) in an H2O/D2O mixture. |
| `_flr_analysis_feature.water_quenching_rate_sd` | float | Standard deviation of the water quenching rate kq_w, 1/ns. |

## `_flr_fit_parameter`

Fit/model parameters, by registry key. This category holds the parameters a fitting application exposes in its parameter registry, exported to MMFDB under software-agnostic flrCIF identifiers. Each item corresponds to one registry entry; the item name is the registry key, not any program's spelling.

| Item | Type | Description |
|---|---|---|
| `_flr_fit_parameter.AtB` | float | Model parameter AtB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.BG` | float | Fit parameter BG. |
| `_flr_fit_parameter.BR` | float | Fit parameter BR. |
| `_flr_fit_parameter.BtA` | float | Model parameter BtA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.D` | float | Translational diffusion coefficient of the diffusing species (µm²/s). |
| `_flr_fit_parameter.E_FRET` | float | Apparent FRET efficiency parameter E_FRET (0e00..1). |
| `_flr_fit_parameter.N` | float | Fit parameter N. |
| `_flr_fit_parameter.N1` | float | Fit parameter N1. |
| `_flr_fit_parameter.N2` | float | Fit parameter N2. |
| `_flr_fit_parameter.N3` | float | Fit parameter N3. |
| `_flr_fit_parameter.QYA` | float | Fit parameter QYA. |
| `_flr_fit_parameter.QYD` | float | Fit parameter QYD. |
| `_flr_fit_parameter.R0` | float | Frster radius R0 of the donor-acceptor pair. |
| `_flr_fit_parameter.Veff` | float | Effective detection volume of the confocal/MDF spot (femtolitres). |
| `_flr_fit_parameter.aT` | float | Fit parameter aT. |
| `_flr_fit_parameter.alpha` | float | Fit parameter alpha. |
| `_flr_fit_parameter.b` | float | Fit parameter b. |
| `_flr_fit_parameter.ba` | float | Fit parameter ba. |
| `_flr_fit_parameter.bg` | float | Constant background level added to the time-resolved decay curve (counts per time channel). |
| `_flr_fit_parameter.bg0` | float | Fit parameter bg0. |
| `_flr_fit_parameter.bg1` | float | Fit parameter bg1. |
| `_flr_fit_parameter.brightness` | float | Background-corrected molecular brightness, mean count rate per particle (kilohertz). |
| `_flr_fit_parameter.bt` | float | Fit parameter bt. |
| `_flr_fit_parameter.conc` | float | Sample concentration derived from particle number and effective detection volume (nanomolar). |
| `_flr_fit_parameter.cont` | float | Model parameter cont used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.cpm` | float | Fit parameter cpm. |
| `_flr_fit_parameter.cpm_all` | float | Fit parameter cpm_all. |
| `_flr_fit_parameter.diam` | float | Known inter-focus separation for two-focus (dual-focus) FCS calibration (nanometres); 0 = single-focus. |
| `_flr_fit_parameter.dt` | float | Time bin width of the TCSPC histogram (time per channel). |
| `_flr_fit_parameter.dtMT[ns]` | float | Fit parameter dtMT[ns]. |
| `_flr_fit_parameter.dtTAC[ns]` | float | Fit parameter dtTAC[ns]. |
| `_flr_fit_parameter.eps1` | float | Fit parameter eps1. |
| `_flr_fit_parameter.eps2` | float | Fit parameter eps2. |
| `_flr_fit_parameter.eps3` | float | Fit parameter eps3. |
| `_flr_fit_parameter.fcs_C` | float | Dimensionless factor C used in the rotational correlation / anisotropy term. |
| `_flr_fit_parameter.fcs_N` | float | Average number of fluorescent particles in the observation volume. In standard FCS models the correlation amplitude scales roughly as 1/N. |
| `_flr_fit_parameter.fcs_N3` | float | Average number of fluorescent particles in the observation volume. In standard FCS models the correlation amplitude scales roughly as 1/N. |
| `_flr_fit_parameter.fcs_a` | float | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). |
| `_flr_fit_parameter.fcs_a1` | float | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). |
| `_flr_fit_parameter.fcs_a2` | float | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). |
| `_flr_fit_parameter.fcs_a21` | float | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). |
| `_flr_fit_parameter.fcs_a22` | float | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). |
| `_flr_fit_parameter.fcs_a31` | float | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). |
| `_flr_fit_parameter.fcs_aR` | float | Amplitude of a relaxation or anticorrelation term (dimensionless). |
| `_flr_fit_parameter.fcs_aR1` | float | Amplitude of a relaxation or anticorrelation term (dimensionless). |
| `_flr_fit_parameter.fcs_aR2` | float | Amplitude of a relaxation or anticorrelation term (dimensionless). |
| `_flr_fit_parameter.fcs_aRa` | float | Amplitude of a relaxation or anticorrelation term (dimensionless). |
| `_flr_fit_parameter.fcs_aab` | float | Amplitude of the photon antibunching term (very fast correlation component). |
| `_flr_fit_parameter.fcs_ab1` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_ab2` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_ab3` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_ab4` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_aba` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_aba1` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_aba2` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_aba3` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_aba4` | float | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). |
| `_flr_fit_parameter.fcs_abf` | float | Total amplitude factor for a group of anticorrelation components. |
| `_flr_fit_parameter.fcs_abt` | float | Time constant of an antibunching or anticorrelation component. |
| `_flr_fit_parameter.fcs_abt1` | float | Time constant of an individual antibunching / anticorrelation component. |
| `_flr_fit_parameter.fcs_abt2` | float | Time constant of an individual antibunching / anticorrelation component. |
| `_flr_fit_parameter.fcs_abt3` | float | Time constant of an individual antibunching / anticorrelation component. |
| `_flr_fit_parameter.fcs_abt4` | float | Time constant of an individual antibunching / anticorrelation component. |
| `_flr_fit_parameter.fcs_abt5` | float | Time constant of an individual antibunching / anticorrelation component. |
| `_flr_fit_parameter.fcs_af` | float | Overall amplitude factor for a set of anticorrelation components. |
| `_flr_fit_parameter.fcs_aroc` | float | Amplitude of the rotational correlation (anisotropy) contribution. |
| `_flr_fit_parameter.fcs_b` | float | Additive baseline/offset of the correlation function. |
| `_flr_fit_parameter.fcs_ba` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba1` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba11` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba12` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba2` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba21` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba22` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba3` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba31` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba32` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba4` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba5` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba6` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_ba7` | float | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. |
| `_flr_fit_parameter.fcs_bs2` | float | Stretching exponent for a stretched-exponential relaxation term. |
| `_flr_fit_parameter.fcs_bs21` | float | Stretching exponent for a stretched-exponential relaxation term. |
| `_flr_fit_parameter.fcs_bs22` | float | Stretching exponent for a stretched-exponential relaxation term. |
| `_flr_fit_parameter.fcs_bt` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt1` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt11` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt12` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt2` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt21` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt22` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt3` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt31` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt32` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt4` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt5` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt6` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_bt7` | float | Correlation/relaxation time constant of a dark or bunching state. |
| `_flr_fit_parameter.fcs_s` | float | Structure parameter s = z0 / w0 describing the axial-to-radial extent of the detection volume. |
| `_flr_fit_parameter.fcs_tR` | float | Relaxation or anticorrelation time constant of a kinetic component. |
| `_flr_fit_parameter.fcs_tR1` | float | Relaxation or anticorrelation time constant of a kinetic component. |
| `_flr_fit_parameter.fcs_tR2` | float | Relaxation or anticorrelation time constant of a kinetic component. |
| `_flr_fit_parameter.fcs_tR3` | float | Relaxation or anticorrelation time constant of a kinetic component. |
| `_flr_fit_parameter.fcs_tRa` | float | Relaxation or anticorrelation time constant of a kinetic component. |
| `_flr_fit_parameter.fcs_tab` | float | Correlation time of the photon antibunching term (fast time scale). |
| `_flr_fit_parameter.fcs_tb1` | float | Fit parameter fcs.tb1. |
| `_flr_fit_parameter.fcs_tb2` | float | Fit parameter fcs.tb2. |
| `_flr_fit_parameter.fcs_tb3` | float | Fit parameter fcs.tb3. |
| `_flr_fit_parameter.fcs_tb4` | float | Fit parameter fcs.tb4. |
| `_flr_fit_parameter.fcs_td` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td1` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td2` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td21` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td22` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td3` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td31` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_td32` | float | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). |
| `_flr_fit_parameter.fcs_trc1` | float | Rotational correlation time used in the anisotropy / rotational diffusion term. |
| `_flr_fit_parameter.fcs_trc2trc1` | float | Rotational correlation time used in the anisotropy / rotational diffusion term. |
| `_flr_fit_parameter.g` | float | Model parameter g used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.gG` | float | Fit parameter gG. |
| `_flr_fit_parameter.gR` | float | Fit parameter gR. |
| `_flr_fit_parameter.gamma` | float | Scatter fraction of the fit23-family MLE: fraction of the signal attributed to scattered light. |
| `_flr_fit_parameter.ics_alpha` | float | Anomalous diffusion exponent alpha in MSD(tau) = 4*D*tau^alpha. 1 is normal diffusion; below 1 is subdiffusion (crowding, transient binding), above 1 is directed transport. Releasing it turns an image-correlation fit into the anomalous/iMSD case. |
| `_flr_fit_parameter.ik` | float | Shape parameter of the synthetic IRF model. |
| `_flr_fit_parameter.irf_start` | float | Start index (or time) of the IRF region used for convolution. |
| `_flr_fit_parameter.irf_stop` | float | Stop index (or time) of the IRF region used for convolution. |
| `_flr_fit_parameter.iw` | float | Width parameter of the synthetic IRF model. |
| `_flr_fit_parameter.k2` | float | Orientation factor governing dipole-dipole coupling in FRET. |
| `_flr_fit_parameter.kQ` | float | Fit parameter kQ. |
| `_flr_fit_parameter.kQ_sd` | float | Standard deviation of the contact quenching rate kQ, 1/ns. |
| `_flr_fit_parameter.l` | float | Model parameter l used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.l1` | float | Model parameter l1 used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.l2` | float | Model parameter l2 used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.lam_em` | float | Emission wavelength used in the confocal detection-volume model (nanometres). |
| `_flr_fit_parameter.lam_ex` | float | Excitation wavelength used in the confocal detection-volume model (nanometres). |
| `_flr_fit_parameter.lb` | float | Lamp background level subtracted from the instrument response function. |
| `_flr_fit_parameter.line_dur` | float | Fit parameter line_dur. |
| `_flr_fit_parameter.lp` | float | Model parameter lp used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.mA` | float | Model parameter mA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.mB` | float | Model parameter mB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.mag` | float | Detection-path magnification used in the confocal detection-volume model. |
| `_flr_fit_parameter.n` | float | Fit parameter n. |
| `_flr_fit_parameter.n curves` | float | Fit parameter n curves. |
| `_flr_fit_parameter.n photons` | float | Fit parameter n photons. |
| `_flr_fit_parameter.n0` | float | Initial number of excited donor molecules used to scale the model decay to the experimental counts. |
| `_flr_fit_parameter.nPh_bg` | float | Output: estimated number of background photons in the TCSPC trace based on background level and measurement timing settings. |
| `_flr_fit_parameter.nPh_fl` | float | Output: estimated number of fluorescence photons (after background subtraction) in the TCSPC trace. |
| `_flr_fit_parameter.nPh_max` | float | Fit parameter nPh_max. |
| `_flr_fit_parameter.nPh_min` | float | Fit parameter nPh_min. |
| `_flr_fit_parameter.nTAC` | float | Fit parameter nTAC. |
| `_flr_fit_parameter.n_rh` | float | Fit parameter n_rh. |
| `_flr_fit_parameter.n_td` | float | Fit parameter n_td. |
| `_flr_fit_parameter.offset` | float | Fit parameter offset. |
| `_flr_fit_parameter.p2s_twoIstar` | int | fit23-family MLE setting: whether 2I* was computed on the parallel+2*perpendicular sum (1) or per channel (0); echoed per row in BIFL-style exports. |
| `_flr_fit_parameter.pinhole` | float | Confocal pinhole diameter, back-projected into the image plane (micrometres). |
| `_flr_fit_parameter.pureA` | float | Model parameter pureA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.pureB` | float | Model parameter pureB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.pxl_dur` | float | Fit parameter pxl_dur. |
| `_flr_fit_parameter.pxl_size` | float | Fit parameter pxl_size. |
| `_flr_fit_parameter.quench_contact_offset` | float | Offset added to the dye-quencher contact distances of the quenching model, angstroms. |
| `_flr_fit_parameter.quench_scale` | float | Common scale factor on a dye's contact quenching rates kQ of all quenching residue types (dimensionless). |
| `_flr_fit_parameter.r0` | float | Frster radius R0 of the donor-acceptor pair. |
| `_flr_fit_parameter.r_experimental` | float | Uncorrected experimental steady-state anisotropy from the raw parallel/perpendicular counts (rE of the BIFL export). |
| `_flr_fit_parameter.r_scatter` | float | Scatter-corrected steady-state anisotropy derived from a polarised MLE (rS of the BIFL export). |
| `_flr_fit_parameter.r_ss_i` | float | Intensity-domain steady-state anisotropy. For dual-channel data, ChiSurf background-corrects VV and VH (per-channel metadata when available), compensates objective mixing via l1/l2, and evaluates rS,I from channel sums using the ChiSurf convention r = (VV - VH) / (g*VV + 2*VH). For single-channel fallback, VM is reconstructed from the active anisotropy model before summation. |
| `_flr_fit_parameter.r_ss_l` | float | Lifetime-domain steady-state anisotropy derived from the model lifetime spectrum and rotational spectrum. This value is model-predicted (spectrum/integral domain) and does not depend on direct VV/VH channel integration. |
| `_flr_fit_parameter.rc_ele` | float | Model parameter rc_ele used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.reg` | float | Fit parameter reg. |
| `_flr_fit_parameter.rep` | float | Laser repetition rate of the excitation source. |
| `_flr_fit_parameter.rh_max` | float | Fit parameter rh_max. |
| `_flr_fit_parameter.rh_min` | float | Fit parameter rh_min. |
| `_flr_fit_parameter.rho` | float | Rotational correlation time fitted by the fit23-family MLE, nanoseconds. |
| `_flr_fit_parameter.rics_D` | float | Diffusion coefficient D in µm²/s. |
| `_flr_fit_parameter.rics_aT` | float | Triplet/blinking fraction a_T (0–1). |
| `_flr_fit_parameter.rics_frame_dur` | float | Frame time t_frame in ms. Converts a frame lag Delta into a lag time via tau = \|xi*t_pixel + psi*t_line + Delta*t_frame\|, so it scales every diffusion coefficient derived from frame lags (STICS/TICS/iMSD). |
| `_flr_fit_parameter.rics_line_dur` | float | Time between successive scanned lines in milliseconds. |
| `_flr_fit_parameter.rics_n` | float | Average number of fluorescent molecules in the observation volume N. RICS/ICS amplitude G(0) is proportional to 1/N. |
| `_flr_fit_parameter.rics_offset` | float | Additive offset of the correlation function. |
| `_flr_fit_parameter.rics_pxl_dur` | float | Pixel dwell time (line scan) in microseconds. |
| `_flr_fit_parameter.rics_pxl_size` | float | Pixel size in the sample plane in nanometers. |
| `_flr_fit_parameter.rics_tauT` | float | Triplet/blinking correlation time τ_T in milliseconds. |
| `_flr_fit_parameter.rics_w_r` | float | Radial waist of the detection PSF in µm. |
| `_flr_fit_parameter.rics_w_z` | float | Axial waist of the detection PSF in µm. |
| `_flr_fit_parameter.rotamer_weight` | float | Weight (0..1) of the side-chain rotamer ensemble of the quenching residues against their crystal positions. |
| `_flr_fit_parameter.s` | float | Fit parameter s. |
| `_flr_fit_parameter.sc` | float | Relative amplitude of a prompt scattering contribution that is added to the model decay. |
| `_flr_fit_parameter.shield_lifetime_increment` | float | Lifetime increment of a dye shielded from the solvent, ns: the unquenched lifetime is tau0 + increment x (1 - solvent exposure). |
| `_flr_fit_parameter.slow_factor_acidic` | float | Slow factor (0..1) of a dye near acidic residues (Asp, Glu). |
| `_flr_fit_parameter.slow_factor_aromatic` | float | Slow factor (0..1) of a dye near aromatic residues (Trp, Tyr, His): the factor by which the dye's mobility is reduced within the slow radius. Smaller is stickier. |
| `_flr_fit_parameter.slow_factor_basic` | float | Slow factor (0..1) of a dye near basic residues (Lys, Arg). |
| `_flr_fit_parameter.slow_factor_common` | float | Common stickiness (slow factor, 0..1) of a dye on a macromolecular surface: the prior centre of the per-group slow factors. Smaller is stickier. |
| `_flr_fit_parameter.slow_factor_hydrophobic` | float | Slow factor (0..1) of a dye near hydrophobic residues (Phe, Leu, Ile, Val, Met, Ala, Pro). |
| `_flr_fit_parameter.slow_factor_polar` | float | Slow factor (0..1) of a dye near polar residues (Ser, Thr, Asn, Gln, Gly, Cys). |
| `_flr_fit_parameter.slowf` | float | Model parameter slowf used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.soft_bifl_scatter` | int | fit23-family MLE setting: whether the scatter fraction was fitted softly (1) or held (0); echoed per row in BIFL-style exports. |
| `_flr_fit_parameter.start` | float | Start time (or channel) of the fit/convolution window. |
| `_flr_fit_parameter.static_quench_offset` | float | Offset of the contact distance of the static quenching channel, angstroms. |
| `_flr_fit_parameter.static_quench_strength` | float | Strength of the static (dark-complex) quenching channel of a dye-quencher contact (dimensionless). |
| `_flr_fit_parameter.stop` | float | Stop time (or channel) of the fit/convolution window. |
| `_flr_fit_parameter.t0` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tBg` | float | Measurement time of the background acquisition. |
| `_flr_fit_parameter.tDead` | float | Model parameter tDead used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.tMeas` | float | Measurement time of the main TCSPC experiment. |
| `_flr_fit_parameter.tau` | float | Fluorescence lifetime, the primary fitted lifetime of a burst- or pixel-wise MLE (fit23 family), nanoseconds. |
| `_flr_fit_parameter.tau0` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tauD` | float | Fit parameter tauD. |
| `_flr_fit_parameter.tauT` | float | Fit parameter tauT. |
| `_flr_fit_parameter.tcspc_Ddye` | float | Translational diffusion coefficient of the fluorescent dye. |
| `_flr_fit_parameter.tcspc_Nq` | float | Effective number or concentration of quenchers in the interaction volume. |
| `_flr_fit_parameter.tcspc_Rdye` | float | Characteristic interaction radius or distance parameter for the dye–quencher system. |
| `_flr_fit_parameter.tcspc_Vav` | float | Effective averaging volume used in the transient-quenching model. |
| `_flr_fit_parameter.tcspc_a` | float | Pre-exponential amplitude or population fraction of this decay component (dimensionless contribution to the overall time-resolved signal). |
| `_flr_fit_parameter.tcspc_a1` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_a2` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_a3` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_aD` | float | Fraction of donors subject to additional quenching or rate channels (dimensionless). |
| `_flr_fit_parameter.tcspc_aDA` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_aDAA` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_aDO` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_ad1` | float | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). |
| `_flr_fit_parameter.tcspc_af1A` | float | Pre-exponential amplitude or population fraction of this decay component (dimensionless contribution to the overall time-resolved signal). |
| `_flr_fit_parameter.tcspc_b` | float | Empirical coefficient of the sqrt(time) term in the transient-quenching decay model; controls deviations from a pure single-exponential decay. |
| `_flr_fit_parameter.tcspc_kQ` | float | Quenching rate constant added to the inverse lifetime (1/tau + kQ). |
| `_flr_fit_parameter.tcspc_kf1A` | float | Effective FRET or energy-transfer rate constant for this channel. |
| `_flr_fit_parameter.tcspc_kf1AA` | float | Effective FRET or energy-transfer rate constant for this channel. |
| `_flr_fit_parameter.tcspc_kf2A` | float | Effective FRET or energy-transfer rate constant for this channel. |
| `_flr_fit_parameter.tcspc_p0` | float | Overall normalization or intensity at time zero of the decay curve. |
| `_flr_fit_parameter.tcspc_tau0` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tcspc_tau1` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tcspc_tau2` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tcspc_tau3` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tcspc_td1` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tcspc_td2` | float | Fluorescence lifetime or characteristic decay time of this component. |
| `_flr_fit_parameter.tcspc_xD` | float | Fraction of donors subject to additional quenching or rate channels (dimensionless). |
| `_flr_fit_parameter.td_max` | float | Fit parameter td_max. |
| `_flr_fit_parameter.td_min` | float | Fit parameter td_min. |
| `_flr_fit_parameter.temp` | float | Fit parameter temp. |
| `_flr_fit_parameter.ts` | float | Additional temporal shift applied to align IRF and decay. |
| `_flr_fit_parameter.twoIstar` | float | 2I* goodness-of-fit of a photon-count MLE, twice the log-likelihood-ratio deviance per degree of freedom. |
| `_flr_fit_parameter.vh_bg_int` | float | Background-corrected summed VH intensity used by anisotropy diagnostics. Derived after channel/background extraction and channel-wise summation over the active trace. |
| `_flr_fit_parameter.vv_bg_int` | float | Background-corrected summed VV intensity used by anisotropy diagnostics. Derived after channel/background extraction and channel-wise summation over the active trace. |
| `_flr_fit_parameter.w` | float | Model parameter w used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.w0` | float | Fit parameter w0. |
| `_flr_fit_parameter.w_r` | float | Fit parameter w_r. |
| `_flr_fit_parameter.w_z` | float | Fit parameter w_z. |
| `_flr_fit_parameter.wem` | float | Emission-side Gauss-Lorentz collection-efficiency waist parameter of the Enderlein molecule-detection function (nanometres). |
| `_flr_fit_parameter.win_size` | float | Model parameter win-size used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.xA` | float | Model parameter xA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.xB` | float | Model parameter xB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. |
| `_flr_fit_parameter.xDOnly` | float | Fraction of donors subject to additional quenching or rate channels (dimensionless). |

## `_flr_fret_analysis`

| Item | Type | Description |
|---|---|---|
| `_flr_fret_analysis.details` | text | Free-text description of the analysis. |
| `_flr_fret_analysis.method` | text | The analysis method (for example PDA, or a screening algorithm), finer than the flrCIF analysis type. |
| `_flr_fret_analysis.sample_id` | text | The sample the analysis was run on. flrCIF reaches it only through the two sample-probe ids. |

## `_flr_fret_calibration_parameters`

| Item | Type | Description |
|---|---|---|
| `_flr_fret_calibration_parameters.phi_donor` | float | Fluorescence quantum yield of the donor. The IHM-FLR dictionary defines phi_acceptor but not its donor counterpart, although the detection-correction factor gamma is (gR*phi_acceptor)/(gG*phi_donor) and needs both. Stored so a calibration can be read back without the donor yield having to be remembered separately from the measurement it was determined with. |

## `_flr_fret_forster_radius`

ChiSurf extensions to the FLR_FRET_FORSTER_RADIUS category. These fields are used by ChiSurf but are not part of the standard flrCIF dictionary.

| Item | Type | Description |
|---|---|---|
| `_flr_fret_forster_radius.details` | text | Free-text provenance of the Forster radius (how it was measured or computed). |
| `_flr_fret_forster_radius.forster_radius` | float | The Forster radius of the probe pair, in angstroms. Upstream flrCIF declares no unit for this item, and the default here was 5.0 -- a nanometre value in a field every consumer reads as angstroms, where a Forster radius is 40-70. Declared and corrected to the same physical quantity, 50 angstroms. |
| `_flr_fret_forster_radius.id` |  |  |
| `_flr_fret_forster_radius.index_of_refraction` | float | Refractive index of the medium for FRET pair. Default is 1.4 for water. |
| `_flr_fret_forster_radius.kappa_squared` | float | Orientation factor kappa squared for FRET pair. Default is 2/3 (0.666667) for dynamic averaging. |
| `_flr_fret_forster_radius.sample_id` |  |  |

## `_flr_poly_probe_position`

ChiSurf schema bindings for the FLR_POLY_PROBE_POSITION category.

| Item | Type | Description |
|---|---|---|
| `_flr_poly_probe_position.asym_id` | code |  |
| `_flr_poly_probe_position.atom_id` | code |  |
| `_flr_poly_probe_position.auth_name` | line |  |
| `_flr_poly_probe_position.comp_id` |  |  |
| `_flr_poly_probe_position.details` | text | Free-text description of the labelled position. flrCIF gives the position list no description item. |
| `_flr_poly_probe_position.id` | int |  |
| `_flr_poly_probe_position.modification_flag` | ucode |  |
| `_flr_poly_probe_position.mutation_flag` | ucode |  |
| `_flr_poly_probe_position.seq_id` |  |  |

## `_flr_probe_descriptor`

ChiSurf schema bindings for probe descriptor columns stored in probes.

| Item | Type | Description |
|---|---|---|
| `_flr_probe_descriptor.chromophore_center_atom` | code |  |
| `_flr_probe_descriptor.chromophore_chem_descriptor_id` | int |  |
| `_flr_probe_descriptor.reactive_probe_chem_descriptor_id` | int |  |

## `_flr_probe_list`

ChiSurf schema bindings for fluorescence probe list fields stored in the local probes table.

| Item | Type | Description |
|---|---|---|
| `_flr_probe_list.chromophore_name` | line |  |
| `_flr_probe_list.details` | text | Free-text description of the probe. flrCIF gives the probe list no description item. |
| `_flr_probe_list.probe_id` | int |  |
| `_flr_probe_list.probe_link_type` | code |  |
| `_flr_probe_list.probe_origin` | code |  |
| `_flr_probe_list.reactive_probe_flag` | ucode |  |
| `_flr_probe_list.reactive_probe_name` | line |  |

## `_flr_sample`

ChiSurf schema bindings for the FLR_SAMPLE category.

| Item | Type | Description |
|---|---|---|
| `_flr_sample.id` |  |  |
| `_flr_sample.sample_description` |  |  |
| `_flr_sample.sample_type` | code |  |

## `_flr_sample_condition`

ChiSurf extensions to the FLR_SAMPLE_CONDITION category. These fields are used by ChiSurf but are not part of the standard flrCIF dictionary.

| Item | Type | Description |
|---|---|---|
| `_flr_sample_condition.id` |  |  |
| `_flr_sample_condition.ph` | float | pH value of the sample condition. |
| `_flr_sample_condition.temperature` | float | Temperature of the sample in Kelvin. |

## `_flr_sample_probe_details`

ChiSurf schema bindings for sample/probe association fields stored in flr_sample_probe.

| Item | Type | Description |
|---|---|---|
| `_flr_sample_probe_details.fluorophore_type` | code |  |
| `_flr_sample_probe_details.poly_probe_position_id` | int |  |
| `_flr_sample_probe_details.probe_id` | int |  |
| `_flr_sample_probe_details.sample_id` | code |  |
| `_flr_sample_probe_details.sample_probe_id` | int |  |

## `_ihm_chemical_component_descriptor`

| Item | Type | Description |
|---|---|---|
| `_ihm_chemical_component_descriptor.id` |  |  |
| `_ihm_chemical_component_descriptor.inchi` |  |  |
| `_ihm_chemical_component_descriptor.smiles` |  |  |

## `_ihm_external_files`

| Item | Type | Description |
|---|---|---|
| `_ihm_external_files.md5` | text | MD5 checksum of the external file content, so a reader can detect a changed or substituted file. |
| `_ihm_external_files.uuid` | text | Store-assigned identifier of the external file, stable across exports. |

## `_mmfdb_acl_entry`

Individual access control entries for fine-grained permissions.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_acl_entry.created_by_user_id` | code |  |
| `_mmfdb_acl_entry.effect` | code |  |
| `_mmfdb_acl_entry.entry_id` | int |  |
| `_mmfdb_acl_entry.object_id` | code |  |
| `_mmfdb_acl_entry.object_type` | code |  |
| `_mmfdb_acl_entry.permissions` | int |  |
| `_mmfdb_acl_entry.subject_id` | code |  |
| `_mmfdb_acl_entry.subject_type` | code |  |

## `_mmfdb_artifact`

Dataset artifact representing a raw measurement or processed result. Ownership and visibility are tracked via created_by_user_id and is_public for dataset-browser scoping.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_artifact.artifact_id` | code |  |
| `_mmfdb_artifact.artifact_kind` | code |  |
| `_mmfdb_artifact.author` | text | Who made the data this artifact holds, as they name themselves. Free text, because an author list is not a controlled vocabulary and a writer that has to normalise one will get it wrong or drop it. This is the upstream author of the DATA, not whoever ran the tool -- that is _mmfdb_operation.operator_user_id, and the two are routinely different: a converted rotamer library is somebody else's measurement in this package's format. |
| `_mmfdb_artifact.checksum` | code | Digest of the payload, lowercase hexadecimal, in the algorithm named by _mmfdb_artifact.checksum_algorithm. This is what makes an artifact held by reference, or embedded in a container, restorable with a guarantee rather than merely restorable. |
| `_mmfdb_artifact.checksum_algorithm` | code | Which digest _mmfdb_artifact.checksum holds. The object store addresses blobs by md5 and verifies them by sha256, so both occur. |
| `_mmfdb_artifact.citation` | text | Where the data was published: a DOI where one exists, otherwise enough of a reference to find it. |
| `_mmfdb_artifact.created_by_user_id` | code | User who created/registered this artifact. NULL for builtin/shared artifacts. Used for dataset-browser scoping (own vs public). |
| `_mmfdb_artifact.data_blob` | text |  |
| `_mmfdb_artifact.data_format` | code |  |
| `_mmfdb_artifact.data_json` | code |  |
| `_mmfdb_artifact.experiment_id` | code |  |
| `_mmfdb_artifact.file_path` | line | Path to the artifact when it is held by reference rather than copied into the object store. A container object names its member here, in the "<container>\|<member>" form the reader understands. |
| `_mmfdb_artifact.folder_path` | code |  |
| `_mmfdb_artifact.is_public` | int | GUI visibility flag. 1 = visible to all users; 0 = visible only to the owning user (created_by_user_id) or admins. |
| `_mmfdb_artifact.is_sidecar` | int | Whether this artifact is a file that only exists BESIDE another one and cannot be read alone. A Becker & Hickl `.spc` keeps half its header in a `.set` next to it: hand a reader the `.spc` on its own and it decodes with the wrong resolution and no error. The `.set` is therefore not a second measurement and not a derived result -- the two categories a container otherwise has -- and listing it as either misleads. It is a part of its primary, and the primary is named by _mmfdb_edge.source_node_id on the sidecar. A reader extracting the measurement must extract the sidecars with it; a reader enumerating what a container holds should not count them as measurements. 1 for a sidecar, 0 or absent otherwise. |
| `_mmfdb_artifact.license` | line | An SPDX license identifier, WHERE ONE EXISTS -- "GPL-3.0-only", "MIT". Deliberately not mandatory and deliberately not the only way to state terms. A great deal of scientific data is released under conditions that have no SPDX identifier at all -- "free for academic use" is the common one -- and coining a LicenseRef for it would state something the upstream did not. Use _mmfdb_artifact.terms for those, and expect to see one or the other rather than both. A writer that has neither should say so out of band rather than guess: an artifact whose terms are unknown is a different thing from one that is unrestricted, and the difference matters to whoever redistributes it. |
| `_mmfdb_artifact.metadata_json` | code |  |
| `_mmfdb_artifact.mime_type` | line | RFC 6838 media type of the payload. |
| `_mmfdb_artifact.object_uuid` | code |  |
| `_mmfdb_artifact.redistributed_via` | text | The intermediary the data reached this package through, when it did not come straight from its author. This exists because the licences differ along that chain and recording only the immediate source loses it. The worked case: the Dunbrack 2010 backbone-dependent rotamer library reaches this stack through FASPR, which is MIT, while the library itself is not -- an artifact naming only FASPR would understate its obligations, and one naming only Dunbrack would lose where the bytes were actually obtained. |
| `_mmfdb_artifact.row_count` | int | Rows or events in a tabular payload, recorded so that a listing can report the size of a table without decoding it. Advisory. |
| `_mmfdb_artifact.row_grain` | code | What one row of a tabular artifact IS. Two tables can only be joined once it is known what their rows count. A burst table and a dwell table are both "results of the same analysis" and are not the same shape: a dwell subdivides a burst, so a dwell table is finer, and a table of fused bursts is coarser than the bursts it fused. Formats that cannot state this force every result onto one grid, and the relations that do not fit that grid are then carried outside the format or lost. Stating the grain is what lets an artifact-to-artifact edge (see _mmfdb_edge.source_row_column) be resolved to rows. `spectrum` is one curve: a wavelength axis and the intensities paired with it, as `_mmfdb_spectrum` stores them. It is NOT `curve_point`, which is one point of one curve -- a table at `spectrum` grain has one row per (probe, spectrum_type) and carries arrays, which is both what the `spectra` table holds and, in a serialisation with arrays, about a tenth the size of the same data written a point per row. `label_site` is a position on a polymer that a label could be attached to -- an (asym_id, seq_id) pair, the same thing `_flr_poly_probe_position` addresses. It is not `species` and not `state`: those count what a molecule IS, and this counts a PLACE ON one. A table of label-site scores is finer than one row per residue whenever more than one quantity is scored at a position, which is the normal case -- so a reader joins it on (asym_id, seq_id, score_type) and not on row order. `spot` and `region` are not synonyms and the difference is not pedantry. A spot is a point-like detection -- a localisation, with a position and at most a width. A region is an arbitrary connected set of pixels that owns its own pixel list: a cell nucleus, a hand-drawn area, a watershed basin. A table of nuclei declared at `spot` grain is a false statement about its rows, of the same kind as calling a file of binned traces a photon stream, and it is false in the one field a reader consults to decide what may be joined to it. |
| `_mmfdb_artifact.size_bytes` | int | Size of the payload in octets. |
| `_mmfdb_artifact.source` | text | What this artifact was made FROM, when that is a thing outside this database -- an upstream file name, a database release, an accession. _mmfdb_edge.source_node_id says which artifact IN HERE it came from; this says what came in from outside, which no edge can point at. |
| `_mmfdb_artifact.storage_mode` | code | Where the bytes actually are. The column has existed since the table was first written by hand; declaring it here is what lets a reader resolve the term rather than guess at it. |
| `_mmfdb_artifact.terms` | text | The conditions of use in words, for data whose terms have no SPDX identifier -- "free for academic use", "no commercial redistribution". Carried verbatim. A summary of a licence is not a licence. |
| `_mmfdb_artifact.terms_url` | code | Where the terms actually live, so a reader can check them rather than trust this file's paraphrase. |
| `_mmfdb_artifact.url` | code |  |
| `_mmfdb_artifact.validation_message` | code |  |
| `_mmfdb_artifact.validation_status` | code |  |

## `_mmfdb_artifact_member`

File-group membership: lists the individual files that belong to a multi-file dataset artifact (e.g. a multi-channel TTTR run or a burst folder with co-located photon sources). Each member is content-addressed (dedup per file via mmfdb_object), and the group artifact carries one row per member.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_artifact_member.artifact_id` | code |  |
| `_mmfdb_artifact_member.filename` | line | Member filename within the group. |
| `_mmfdb_artifact_member.id` | int |  |
| `_mmfdb_artifact_member.object_uuid` | code |  |
| `_mmfdb_artifact_member.ordinal` | int |  |
| `_mmfdb_artifact_member.role` | line | Member role, e.g. ``primary``, ``sidecar``, ``channel``. |

## `_mmfdb_artifact_owner`

Many-to-many ownership of an artifact (dataset). A dataset can be co-owned by several users; each owner sees it under their "Mine" scope. Content dedup keeps one artifact while the owner set grows.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_artifact_owner.artifact_id` | code |  |
| `_mmfdb_artifact_owner.id` | int |  |
| `_mmfdb_artifact_owner.role` | line | Ownership role, e.g. ``owner`` (default) or ``contributor``. |
| `_mmfdb_artifact_owner.user_id` | code |  |

## `_mmfdb_audit_log`

Audit log for tracking changes to MMFDB objects.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_audit_log.action` | code |  |
| `_mmfdb_audit_log.details_json` | text |  |
| `_mmfdb_audit_log.log_id` | int |  |
| `_mmfdb_audit_log.operator_user_id` | code |  |
| `_mmfdb_audit_log.target_id` | code |  |
| `_mmfdb_audit_log.target_type` | code |  |

## `_mmfdb_auth_attempt`

Record of authentication attempts for security auditing.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_auth_attempt.attempt_id` | int |  |
| `_mmfdb_auth_attempt.client_host` | line |  |
| `_mmfdb_auth_attempt.reason` | text |  |
| `_mmfdb_auth_attempt.success` | int |  |
| `_mmfdb_auth_attempt.user_id` | code |  |

## `_mmfdb_branch`

Named branch/version in the MMFDB version graph.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_branch.branch_id` | int |  |
| `_mmfdb_branch.lifecycle_status` | code | Lifecycle status of a branch/version. |

## `_mmfdb_bundle_document`

A text document carried in the deposit (the methods report, the JSON manifest, and this dictionary), so the CIF is self-describing.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_bundle_document.content` | text |  |
| `_mmfdb_bundle_document.media_type` | line |  |
| `_mmfdb_bundle_document.name` | line |  |

## `_mmfdb_bundle_file`

A data file embedded in the deposit, base64-encoded, so the CIF is a single self-contained, reproducible archive. The original file is kept verbatim (never re-encoded); verify it against the recorded sha256.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_bundle_file.artifact_id` | line |  |
| `_mmfdb_bundle_file.content` | text | Base64 of the file's exact bytes, wrapped to fixed-width lines. |
| `_mmfdb_bundle_file.data_format` | line |  |
| `_mmfdb_bundle_file.encoding` | code |  |
| `_mmfdb_bundle_file.md5` | line |  |
| `_mmfdb_bundle_file.media_type` | line |  |
| `_mmfdb_bundle_file.name` | line |  |
| `_mmfdb_bundle_file.ordinal` | int |  |
| `_mmfdb_bundle_file.sha256` | line |  |
| `_mmfdb_bundle_file.size_bytes` | int |  |

## `_mmfdb_burst_column`

Data items describing a column in a burst-analysis artifact (.bur, .bg4, .br4, .bv4, .2c4, .td4). These are the input columns the ndx equation engine reads.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_burst_column.count_rate_khz` | float | Total burst count rate, N / Duration, in kHz. |
| `_mmfdb_burst_column.duration_green_ms` | float | Macro-time span of the green-detector photons within the burst. t_last(green) - t_first(green). Sentinel -1.0 when the burst has no green photons. This is the Tg in the ndx equation Tg-Tr(ms) = Duration(green) - Duration(red). It is a macro-time (burst) duration, NOT a TCSPC micro-time difference. |
| `_mmfdb_burst_column.duration_ms` | float | Macro-time span of the entire burst, t_last - t_first, in milliseconds. |
| `_mmfdb_burst_column.duration_red_ms` | float | Macro-time span of the red-detector photons within the burst. t_last(red) - t_first(red). Sentinel -1.0 when the burst has no red photons. This is the Tr in Tg-Tr(ms). |
| `_mmfdb_burst_column.f_aexc_aem` | int | Acceptor-excitation acceptor-emission integrated counts (ALEX). |
| `_mmfdb_burst_column.f_aexc_dem` | int | Acceptor-excitation donor-emission integrated counts (ALEX). |
| `_mmfdb_burst_column.f_dexc_aem` | int | Donor-excitation acceptor-emission integrated counts (ALEX). |
| `_mmfdb_burst_column.f_dexc_dem` | int | Donor-excitation donor-emission integrated counts (ALEX). |
| `_mmfdb_burst_column.first_photon` | int | Index of the first photon in the burst within the TTTR event stream. |
| `_mmfdb_burst_column.gamma_green` | float | Detection-efficiency correction factor gamma from the Fit2x fit. |
| `_mmfdb_burst_column.gamma_red` | float | Detection-efficiency correction factor gamma of the red-channel Fit2x fit. |
| `_mmfdb_burst_column.green_count_rate_khz` | float | Green-detector count rate within the burst. Primary input to the ndx Sg equation and all downstream intensity-FRET derivations. |
| `_mmfdb_burst_column.last_photon` | int | Index of the last photon in the burst (inclusive). |
| `_mmfdb_burst_column.mean_macro_time_green_ms` | float | Midpoint of green-detector photon macro-time span within burst. |
| `_mmfdb_burst_column.mean_macro_time_ms` | float | Midpoint of the burst's first and last photon macro times, (t_first + t_last) / 2, in ms. Despite the name this is a midpoint, not a photon-weighted mean. |
| `_mmfdb_burst_column.mean_macro_time_red_ms` | float | Midpoint of red-detector photon macro-time span within burst. |
| `_mmfdb_burst_column.mean_microtime_green_ns` | float | Mean TCSPC micro-time of the green-detector photons, converted to nanoseconds via micro_time_resolution. Sentinel -1.0 when no green photons or unknown resolution. |
| `_mmfdb_burst_column.mean_microtime_red_ns` | float | Mean TCSPC micro-time of the red-detector photons, in nanoseconds. Sentinel -1.0 when no red photons or unknown resolution. |
| `_mmfdb_burst_column.mle_fitted_green` | int | 1 if the Fit2x MLE fit converged for this burst on the green channel, 0 if it was skipped or failed. Failed fits write NaN in every numeric result column; this flag distinguishes "not attempted" from "attempted and produced a number". |
| `_mmfdb_burst_column.mle_fitted_red` | int | 1 if the Fit2x fit converged for red, 0 otherwise. |
| `_mmfdb_burst_column.n_photons` | int | Total photon count in the burst across all detectors. |
| `_mmfdb_burst_column.n_photons_green` | int | Photon count in the burst on the green-detector routing channels. |
| `_mmfdb_burst_column.n_photons_red` | int | Photon count in the burst on the red-detector routing channels. |
| `_mmfdb_burst_column.phasor_g` | float | Phasor coordinate g (real part, cosine transform) of a pixel's or a burst's decay. |
| `_mmfdb_burst_column.phasor_g_green` | float | Phasor coordinate g (real part, cosine transform) of the green channel of a pixel's or a burst's decay. |
| `_mmfdb_burst_column.phasor_g_red` | float | Phasor coordinate g (real part, cosine transform) of the red channel of a pixel's or a burst's decay. |
| `_mmfdb_burst_column.phasor_s` | float | Phasor coordinate s (imaginary part, sine transform) of a pixel's or a burst's decay. |
| `_mmfdb_burst_column.phasor_s_green` | float | Phasor coordinate s (imaginary part, sine transform) of the green channel of a pixel's or a burst's decay. |
| `_mmfdb_burst_column.phasor_s_red` | float | Phasor coordinate s (imaginary part, sine transform) of the red channel of a pixel's or a burst's decay. |
| `_mmfdb_burst_column.proximity_ratio` | float | Raw proximity ratio Nr / (Ng + Nr), uncorrected for background, leakage, or gamma. Distinct from the ndx-derived 'Proximity ratio' equation (which uses Sr and Sg). |
| `_mmfdb_burst_column.r0_green` | float | Fundamental anisotropy r0 from the Fit2x fit. |
| `_mmfdb_burst_column.r0_red` | float | Fundamental anisotropy r0 of the red-channel Fit2x fit. |
| `_mmfdb_burst_column.r_experimental_green` | float | Experimental steady-state anisotropy of the green channel from Fit2x. |
| `_mmfdb_burst_column.r_experimental_red` | float | Experimental steady-state anisotropy of the red channel from Fit2x. |
| `_mmfdb_burst_column.r_scatter_green` | float | Scatter-reference anisotropy for the green channel from Fit2x. |
| `_mmfdb_burst_column.r_scatter_red` | float | Scatter-reference anisotropy for the red channel from Fit2x. |
| `_mmfdb_burst_column.rda` | float | Dye-to-dye distance from Fit2x MLE fit. Input to ndx Rapp and kFRET. |
| `_mmfdb_burst_column.red_count_rate_khz` | float | Red-detector count rate within the burst. Primary input to the ndx Sr equation. |
| `_mmfdb_burst_column.rho_green` | float | Rotational correlation time rho from the Fit2x fit. |
| `_mmfdb_burst_column.rho_red` | float | Rotational correlation time rho of the red-channel Fit2x fit. |
| `_mmfdb_burst_column.s_delayed_yellow` | float | Red-detector rate in delayed micro-time window. Input to ndx Sy(PIE). |
| `_mmfdb_burst_column.s_prompt_green` | float | Green-detector rate in prompt micro-time window. Input to ndx Sg(PIE). |
| `_mmfdb_burst_column.s_prompt_red` | float | Red-detector rate in prompt micro-time window. Input to ndx Sr(PIE). |
| `_mmfdb_burst_column.tau` | float | Burst mean lifetime used as time base for ALEX rate equations. |
| `_mmfdb_burst_column.tau_green` | float | Fluorescence-weighted donor (green) lifetime from burst-wise Fit2x MLE. Primary lifetime input to ndx Var_tauD(A)), E_tau, and the FRET-line equations. |
| `_mmfdb_burst_column.tau_red` | float | Fluorescence-weighted acceptor (red) lifetime from burst-wise Fit2x MLE on the red detection channels: the red counterpart of Tau (green). |
| `_mmfdb_burst_column.td_mean` | float | Mean diffusion time from FCS/td4 companion analysis. |
| `_mmfdb_burst_column.two_istar_green` | float | Corrected intensity 2I* from the Fit2x fit -- the quality-of-fit likelihood ratio metric. |
| `_mmfdb_burst_column.two_istar_red` | float | Corrected intensity 2I* of the red-channel Fit2x fit -- the quality-of-fit likelihood ratio metric of Tau (red). |

## `_mmfdb_column`

What one column of a serialised table is. A column carries a name and a dtype, which is enough to read it and not enough to understand it: a burst duration is milliseconds, a lifetime is nanoseconds, and historically that was recorded only in the column name, when whoever wrote it remembered -- "Duration (ms)" and "Tau" sit in the same table. These are the attributes a column description carries so it is written down instead. Like the rest of this dictionary these describe a SERIALIZATION and are not database-backed: there is no mmfdb_column table.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_column.description` | text | Prose about the column, for a reader who has only the file. ############# ## CATEGORY: mmfdb_units ############# |
| `_mmfdb_column.item` | line | The mmCIF item this column corresponds to, when there is one, so a table can be projected onto the dictionary rather than matched by name. |
| `_mmfdb_column.name` | line | The column's name, and the key it is looked up by. |
| `_mmfdb_column.units` | code | The physical unit of the column's values. Spellings follow mmCIF's ITEM_UNITS_LIST wherever it has the unit, so "seconds", "nanoseconds", "hertz" and "counts" are the community's words -- 15 of the 28 here are already its own. Its 78 codes have an odd gap: it carries nanoseconds and femtoseconds but neither milliseconds nor picoseconds, and no concentration, rate multiple or count-of-photons. Those 13 are added here rather than invented at each call site. "dimensionless" is for a ratio that genuinely has no unit -- an efficiency, an anisotropy -- and is not the same as saying nothing, which means the unit is unknown. |

## `_mmfdb_constant`

Scalar calibration constants used by the ndx equation engine (gG/gR, alpha, beta, PhiA, PhiD, forster_radius, ...). Mirrors ndx mfd.constants.json.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_constant.Bg` | float | Green-channel background count rate. |
| `_mmfdb_constant.Br` | float | Red-channel background count rate. |
| `_mmfdb_constant.By` | float | Yellow (acceptor-excitation acceptor-emission) background. |
| `_mmfdb_constant.KB` | float | Boltzmann constant. |
| `_mmfdb_constant.PhiA` | float | Acceptor fluorescence quantum yield. |
| `_mmfdb_constant.PhiD` | float | Donor fluorescence quantum yield. |
| `_mmfdb_constant.T_K` | float | Sample temperature in Kelvin. |
| `_mmfdb_constant.alpha` | float | Donor-leakage (spectral crosstalk) coefficient. |
| `_mmfdb_constant.beta` | float | Direct acceptor excitation coefficient at donor wavelength. |
| `_mmfdb_constant.eta_Pa_s` | float | Solvent viscosity. |
| `_mmfdb_constant.f_rep` | float | Modulation (laser repetition) frequency the phasor coordinates are computed at. |
| `_mmfdb_constant.forster_radius` | float | Forster radius for the donor-acceptor pair. |
| `_mmfdb_constant.gG_gR` | float | Green-to-red detection-efficiency ratio (gamma-factor ratio). |
| `_mmfdb_constant.g_bg` | float | Phasor g of the background decay as measured (before the IRF correction). Uncorrelated background spread evenly over the period is at (0, 0). |
| `_mmfdb_constant.g_irf` | float | Phasor g of the instrument response (reference) of a pixel's or a burst's decay, at f_rep and harmonic; the measured phasor is divided by (g_irf + i s_irf). (1, 0) is an ideal instrument (no correction). |
| `_mmfdb_constant.g_irf_green` | float | Phasor g of the instrument response (reference) of the green detection channel, at f_rep and harmonic; the measured phasor is divided by (g_irf + i s_irf). (1, 0) is an ideal instrument (no correction). |
| `_mmfdb_constant.g_irf_red` | float | Phasor g of the instrument response (reference) of the red detection channel, at f_rep and harmonic; the measured phasor is divided by (g_irf + i s_irf). (1, 0) is an ideal instrument (no correction). |
| `_mmfdb_constant.harmonic` | float | Harmonic n of the phasor coordinates; the angular frequency is omega = 2*pi*f_rep*n. |
| `_mmfdb_constant.kappa2` | float | Dipole-orientation factor (default 2/3 for dynamic averaging). |
| `_mmfdb_constant.n_bg` | float | Background photons expected in one row (pixel or burst) of a pixel's or a burst's decay; the background fraction is n_bg / Number of Photons. 0 is no background correction. |
| `_mmfdb_constant.n_bg_green` | float | Background photons expected in one row (pixel or burst) of the green detection channel; the background fraction is n_bg / Number of Photons (green). 0 is no background correction. |
| `_mmfdb_constant.n_bg_red` | float | Background photons expected in one row (pixel or burst) of the red detection channel; the background fraction is n_bg / Number of Photons (red). 0 is no background correction. |
| `_mmfdb_constant.omega_r_um` | float | Radial beam waist (1/e^2) of the confocal volume. |
| `_mmfdb_constant.r` | float | Stoichiometry scaling factor (1/beta_Hellenkamp). |
| `_mmfdb_constant.s_bg` | float | Phasor s of the background decay as measured (before the IRF correction). Uncorrelated background spread evenly over the period is at (0, 0). |
| `_mmfdb_constant.s_irf` | float | Phasor s of the instrument response (reference) of a pixel's or a burst's decay, at f_rep and harmonic; together with g_irf it must not be (0, 0). |
| `_mmfdb_constant.s_irf_green` | float | Phasor s of the instrument response (reference) of the green detection channel, at f_rep and harmonic; together with g_irf it must not be (0, 0). |
| `_mmfdb_constant.s_irf_red` | float | Phasor s of the instrument response (reference) of the red detection channel, at f_rep and harmonic; together with g_irf it must not be (0, 0). |
| `_mmfdb_constant.tauD0` | float | Donor-only lifetime (lifetime in the absence of FRET). |

## `_mmfdb_container`

What a serialised container is, written into the container itself. A photon container (see the PTO.MFDB profile) carries results tagged with terms from this dictionary family. Four things can drift independently -- the container format, the profile that constrains it, the dictionary the terms come from, and the application that wrote it -- so a file that records only one of them cannot be diagnosed when it disagrees with a reader. These items are the stamp. Like the rest of this dictionary they describe a SERIALIZATION and are not database-backed: there is no mmfdb_container table, and this file is deliberately absent from MmcifDictionary.BUNDLED_DICTS so that schema reconciliation does not materialise one.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_container.dictionary_hash` | code | SHA-256 of that dictionary as loaded, lowercase hexadecimal. A version is what an author declares; this is what was actually used, and the two disagree exactly when someone edited a dictionary without bumping it. |
| `_mmfdb_container.dictionary_version` | code | ``_dictionary.version`` of the MMFDB extension dictionary whose terms the file is tagged with. |
| `_mmfdb_container.format` | code | The container format underneath the profile, e.g. ``pto``. |
| `_mmfdb_container.format_version` | code | Version of that container format. |
| `_mmfdb_container.profile` | line | Name of the profile the file conforms to, e.g. ``PTO.MFDB``. |
| `_mmfdb_container.profile_read_version` | int | Minimum profile version required to read the file correctly. A reader implementing less than this must refuse it rather than misread it. |
| `_mmfdb_container.profile_version` | code | Version of the profile that wrote the file. A reader accepts a higher one and skips what it does not know. |

## `_mmfdb_derived_column`

Output columns computed by the ndx equation engine from input columns and constants. Every equation output key in mfd.equations.yaml must appear here.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_derived_column.d_um2_s` | float | 250 * omega_r^2 / tauD. Diffusion coefficient. |
| `_mmfdb_derived_column.e_aa_pie` | float | ratioA(PIE) / r. Acceptor-side FRET efficiency. |
| `_mmfdb_derived_column.e_alex` | float | (1 + Fd/Fa(ALEX) * PhiA/PhiD)^(-1). |
| `_mmfdb_derived_column.e_pie` | float | (1 + Fd/Fa(PIE) * PhiA/PhiD)^(-1). PIE FRET efficiency. |
| `_mmfdb_derived_column.e_tau` | float | 1 - Tau(green) / tauD0. Lifetime-based FRET efficiency. |
| `_mmfdb_derived_column.f_bg` | float | n_bg / Number of Photons. Fraction of the photons of a pixel's or a burst's decay that are background. |
| `_mmfdb_derived_column.f_bg_green` | float | n_bg (green) / Number of Photons (green). Fraction of the photons of the green detection channel that are background. |
| `_mmfdb_derived_column.f_bg_red` | float | n_bg (red) / Number of Photons (red). Fraction of the photons of the red detection channel that are background. |
| `_mmfdb_derived_column.fd_fa` | float | (Fg/Fr) / (gG/gR). Donor-to-acceptor intensity ratio. |
| `_mmfdb_derived_column.fd_fa_alex` | float | (Fg/Fr(ALEX)) / (gG/gR). ALEX donor-to-acceptor ratio. |
| `_mmfdb_derived_column.fd_fa_pie` | float | (Fg/Fr(PIE)) / (gG/gR). PIE donor-to-acceptor ratio. |
| `_mmfdb_derived_column.fg` | float | Sg - Bg. Background-corrected green signal. |
| `_mmfdb_derived_column.fg_alex` | float | Sg(ALEX) - Bg. |
| `_mmfdb_derived_column.fg_fr` | float | Fg / Fr. |
| `_mmfdb_derived_column.fg_fr_alex` | float | Fg(ALEX) / Fr(ALEX). |
| `_mmfdb_derived_column.fg_fr_pie` | float | Fg(PIE) / Fr(PIE). |
| `_mmfdb_derived_column.fg_pie` | float | Sg(PIE) - Bg. |
| `_mmfdb_derived_column.fr` | float | Sr - Br - alpha*Sg. Corrected red signal. |
| `_mmfdb_derived_column.fr_alex` | float | Sr(ALEX) - Br - alpha*Sg(ALEX). |
| `_mmfdb_derived_column.fr_pie` | float | Sr(PIE) - Br - alpha*Sg(PIE). |
| `_mmfdb_derived_column.fret_efficiency` | float | (1 + Fd/Fa * PhiA/PhiD)^(-1). Intensity-based FRET efficiency. |
| `_mmfdb_derived_column.fy_alex` | float | Sy(ALEX) - By. |
| `_mmfdb_derived_column.fy_pie` | float | Sy(PIE) - By. |
| `_mmfdb_derived_column.inv_sensitivity` | float | 1 / (1 - E * (1 - gG/gR * PhiD/PhiA)). |
| `_mmfdb_derived_column.kfret` | float | (1/tauD0)*(3/2)*kappa^2*(R0/RDA)^6. FRET rate constant. |
| `_mmfdb_derived_column.one_minus_e_e` | float | (1 - E) * E. Static reference parabola in moment plot. |
| `_mmfdb_derived_column.one_minus_e_e_tau` | float | (1 - E) * E_tau. Moment-difference representation. |
| `_mmfdb_derived_column.phasor_g_corr` | float | Real part of ((g + i s) - f_bg (g_bg + i s_bg)) / ((1 - f_bg) (g_irf + i s_irf)). Phasor g of a pixel's or a burst's decay, background removed and referenced to the instrument response. |
| `_mmfdb_derived_column.phasor_g_corr_green` | float | Real part of ((g (green) + i s (green)) - f_bg (green) (g_bg + i s_bg)) / ((1 - f_bg (green)) (g_irf (green) + i s_irf (green))). Phasor g of the green detection channel, background removed and referenced to the instrument response. |
| `_mmfdb_derived_column.phasor_g_corr_red` | float | Real part of ((g (red) + i s (red)) - f_bg (red) (g_bg + i s_bg)) / ((1 - f_bg (red)) (g_irf (red) + i s_irf (red))). Phasor g of the red detection channel, background removed and referenced to the instrument response. |
| `_mmfdb_derived_column.phasor_s_corr` | float | Imaginary part of ((g + i s) - f_bg (g_bg + i s_bg)) / ((1 - f_bg) (g_irf + i s_irf)). Phasor s of a pixel's or a burst's decay, background removed and referenced to the instrument response. |
| `_mmfdb_derived_column.phasor_s_corr_green` | float | Imaginary part of ((g (green) + i s (green)) - f_bg (green) (g_bg + i s_bg)) / ((1 - f_bg (green)) (g_irf (green) + i s_irf (green))). Phasor s of the green detection channel, background removed and referenced to the instrument response. |
| `_mmfdb_derived_column.phasor_s_corr_red` | float | Imaginary part of ((g (red) + i s (red)) - f_bg (red) (g_bg + i s_bg)) / ((1 - f_bg (red)) (g_irf (red) + i s_irf (red))). Phasor s of the red detection channel, background removed and referenced to the instrument response. |
| `_mmfdb_derived_column.pr_alex` | float | Sr(ALEX) / (Sr(ALEX) + Sg(ALEX)). |
| `_mmfdb_derived_column.pr_pie` | float | Sr(PIE) / (Sr(PIE) + Sg(PIE)). PIE proximity ratio. |
| `_mmfdb_derived_column.proximity_ratio_derived` | float | Sr / (Sg + Sr). Corrected proximity ratio from ndx equations. |
| `_mmfdb_derived_column.r_fret` | float | R0 * (1/E - 1)^(1/6). Distance from FRET efficiency. |
| `_mmfdb_derived_column.r_fret_aa_pie` | float | R0 * (1/E_AA(PIE) - 1)^(1/6). |
| `_mmfdb_derived_column.r_fret_pie` | float | R0 * (1/E(PIE) - 1)^(1/6). PIE distance. |
| `_mmfdb_derived_column.rapp` | float | (3/2) / kappa^2 * RDA. Apparent distance. |
| `_mmfdb_derived_column.ratioA_pie` | float | Fr(PIE) / Fy(PIE). Acceptor ratio. |
| `_mmfdb_derived_column.rh_nm` | float | kB*T / (6*pi*eta*D). Hydrodynamic radius via Stokes-Einstein. |
| `_mmfdb_derived_column.sapp_alex_f` | float | Flux-based apparent stoichiometry from ALEX channels. |
| `_mmfdb_derived_column.sapp_alex_s` | float | Signal-based apparent stoichiometry from ALEX channels. |
| `_mmfdb_derived_column.sapp_pie_f` | float | Flux-based apparent stoichiometry from PIE channels. |
| `_mmfdb_derived_column.sapp_pie_s` | float | Signal-based apparent stoichiometry from PIE channels. |
| `_mmfdb_derived_column.sg` | float | Alias for Green Count Rate (KHz). ndx equation. |
| `_mmfdb_derived_column.sg_alex` | float | F_Dexc_Dem / Tau / 1e3. ALEX donor-excitation donor-emission rate. |
| `_mmfdb_derived_column.sg_pie` | float | Alias for S prompt green (kHz). PIE donor-excitation green signal. |
| `_mmfdb_derived_column.sg_sr` | float | Sg / Sr. |
| `_mmfdb_derived_column.sg_sr_alex` | float | Sg(ALEX) / Sr(ALEX). |
| `_mmfdb_derived_column.sg_sr_pie` | float | Sg(PIE) / Sr(PIE). |
| `_mmfdb_derived_column.sigma_e` | float | \|Var(E)\|^(1/2). Standard deviation of E. |
| `_mmfdb_derived_column.sr` | float | Alias for Red Count Rate (KHz). ndx equation. |
| `_mmfdb_derived_column.sr_alex` | float | F_Dexc_Aem / Tau / 1e3. |
| `_mmfdb_derived_column.sr_pie` | float | Alias for S prompt red (kHz). PIE donor-excitation red signal. |
| `_mmfdb_derived_column.stoich_alex` | float | Full ALEX stoichiometry from corrected fluxes. |
| `_mmfdb_derived_column.stoich_pie` | float | Full PIE stoichiometry ratio from corrected PIE fluxes. |
| `_mmfdb_derived_column.sx_alex` | float | F_Aexc_Dem / Tau / 1e3. |
| `_mmfdb_derived_column.sy_alex` | float | F_Aexc_Aem / Tau / 1e3. |
| `_mmfdb_derived_column.sy_pie` | float | Alias for S delayed yellow (kHz). PIE acceptor-excitation signal. |
| `_mmfdb_derived_column.tauDA_x` | float | (1 - E) * tauD(0). Species-weighted donor lifetime. |
| `_mmfdb_derived_column.tau_m` | float | sqrt(1/(g corr^2 + s corr^2) - 1) / omega. Apparent modulation lifetime. |
| `_mmfdb_derived_column.tau_m_green` | float | sqrt(1/(g corr (green)^2 + s corr (green)^2) - 1) / omega. Apparent modulation lifetime. |
| `_mmfdb_derived_column.tau_m_red` | float | sqrt(1/(g corr (red)^2 + s corr (red)^2) - 1) / omega. Apparent modulation lifetime. |
| `_mmfdb_derived_column.tau_phi` | float | s corr / (omega*g corr), omega = 2*pi*f_rep*harmonic. Apparent phase lifetime. |
| `_mmfdb_derived_column.tau_phi_green` | float | s corr (green) / (omega*g corr (green)), omega = 2*pi*f_rep*harmonic. Apparent phase lifetime. |
| `_mmfdb_derived_column.tau_phi_red` | float | s corr (red) / (omega*g corr (red)), omega = 2*pi*f_rep*harmonic. Apparent phase lifetime. |
| `_mmfdb_derived_column.td_` | float | Alias for td_mean. |
| `_mmfdb_derived_column.tg_tr_ms` | float | Duration(green) - Duration(red). Burst macro-time duration difference between green and red detectors. NOT a micro-time difference. |
| `_mmfdb_derived_column.total_rate` | float | Green Count Rate + Red Count Rate. |
| `_mmfdb_derived_column.total_rate_alex` | float | Sg(ALEX) + Sr(ALEX). |
| `_mmfdb_derived_column.var_e` | float | Var_tauD(A)) / tauD0^2. FRET-efficiency variance. |
| `_mmfdb_derived_column.var_tauDA` | float | Tau(green) * <tauD(A)>x - <tauD(A)>x^2. Lifetime variance. |

## `_mmfdb_edge`

Edges in the MMFDB provenance/knowledge graph.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_edge.checksum_snapshot_json` | code |  |
| `_mmfdb_edge.edge_id` | int |  |
| `_mmfdb_edge.metadata_json` | code |  |
| `_mmfdb_edge.operation_id` | code |  |
| `_mmfdb_edge.relationship_type` | code |  |
| `_mmfdb_edge.settings_hash` | code |  |
| `_mmfdb_edge.software_version` | code |  |
| `_mmfdb_edge.source_node_id` | code | What this edge points AT -- the artifact the derived one came from. The column has existed in the hand-written DDL since the table was first created; declaring it here is what lets a reader resolve it rather than guess. Leaving it undeclared had a concrete cost: a writer with nowhere to put the parent reference put it in `relationship_type` instead, so asking a file for the relationship between two artifacts returned an integer where a term was expected -- and the *relation* itself, the thing that says HOW the derived data relates to the primary, was never recorded at all. In a serialised container this is an object UID. In the database it is an artifact or operation id; `source_node_type` says which. |
| `_mmfdb_edge.source_node_type` | code |  |
| `_mmfdb_edge.source_row_column` | line | Column of the source table holding the key this edge joins on. An edge between two artifacts says the tables are related. It does not say which rows correspond, and a great deal of information has been lost historically by leaving that to positional alignment: two tables merged by counting rows agree only while both have the same rows in the same order, and disagree silently the moment one of them does not. Naming the key column makes the join declared data rather than a convention a reader has to already know. |
| `_mmfdb_edge.target_node_id` | code | What this edge points FROM -- the derived artifact. Implicit in a container, where an edge is a tag on the derived object and the target is therefore the object carrying the tag. Declared because the database stores edges as free-standing rows, where it is not implicit. |
| `_mmfdb_edge.target_node_type` | code |  |
| `_mmfdb_edge.target_row_column` | line | Column of the target table holding the key this edge joins on. See _mmfdb_edge.source_row_column. |
| `_mmfdb_edge.timestamp` | code |  |

## `_mmfdb_event_log`

Append-only log of interactive analysis operations. One row per recorded action. Durable record of a session's operation history; an interactive client's in-memory undo/redo history is a projection of these rows. The controlled vocabulary of action names — and their mapping to the coarse mmfdb_operation.operation_type — is declared here (the action_type enumeration plus its per-value detail), so the dictionary is the single source of truth for the operation vocabulary. Rows are never mutated in place.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_event_log.action_type` | line | Canonical action name (dotted form is authoritative). The detail column maps each action to the coarse mmfdb_operation.operation_type it emits ('.' = fine-grained action with no operation). |
| `_mmfdb_event_log.event_id` | code | Stable UUID identity of the event; equals the in-memory operation-history event id so the projection is identity-stable across save/restore. |
| `_mmfdb_event_log.event_timestamp` | datetime | The event's own ISO-8601 timestamp (distinct from the audit created_at). |
| `_mmfdb_event_log.history_version` | code |  |
| `_mmfdb_event_log.operation_id` | code | Links a coarse event to the semantic mmfdb_operation it produced (if any). |
| `_mmfdb_event_log.operation_type` | line | Coarse operation classification for this event, drawn from mmfdb_operation.operation_type; null for fine-grained actions. |
| `_mmfdb_event_log.payload_json` | text | JSON-encoded enriched action payload (opaque to the database). |
| `_mmfdb_event_log.project_id` | code | Project / session scope of the event; null for session-only events. |
| `_mmfdb_event_log.replayable` | boolean |  |
| `_mmfdb_event_log.seq` | int | Monotonic per-project ordinal giving the log's total order (clock-skew proof). |
| `_mmfdb_event_log.side_effect_class` | code |  |
| `_mmfdb_event_log.source_uid` | code |  |
| `_mmfdb_event_log.summary` | text |  |
| `_mmfdb_event_log.target_uid` | code |  |

## `_mmfdb_group`

User groups for access control and organization.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_group.created_by_user_id` | code |  |
| `_mmfdb_group.description` | text |  |
| `_mmfdb_group.display_name` | line |  |
| `_mmfdb_group.group_id` | code |  |
| `_mmfdb_group.is_builtin` | int |  |

## `_mmfdb_group_member`

Membership of users in groups.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_group_member.created_by_user_id` | code |  |
| `_mmfdb_group_member.group_id` | code |  |
| `_mmfdb_group_member.role` | code |  |
| `_mmfdb_group_member.user_id` | code |  |

## `_mmfdb_label_score`

A per-position score of how suitable a site is for attaching a fluorescent label. Label-site selection is a scored decision -- is this residue conserved, is it buried, does a tryptophan sit close enough to quench, would a cysteine here be one of several -- and each of those is a named quantity computed by a named method. They had nowhere to live: the tool that computes them writes them into the PDB B-factor column, a field that means "isotropic displacement parameter, in Angstrom squared" and is here carrying a dimensionless suitability score. A reader that believes the file is wrong; a reader that wants the score has to know the convention out of band; and WHICH score is in there is not written down at all, because one column can hold one at a time. One row is one score at one position. The position is given the way mmCIF gives a position -- asym_id and seq_id -- so a score joins to the structure and to _flr_poly_probe_position without a private convention. ABSENT MEANS NOT COMPUTED. Do not write a sentinel: the tool this was modelled on uses -1 for "excluded" and 0 for "no contribution" in the same column, so a consumer cannot tell an excluded residue from a genuinely zero score, and neither from a real value that happens to be zero. Use _mmfdb_label_score.status to say why a position has no value. For readers coming from Labelizer, whose parameters are named by two-letter file tags: cs -> conservation, se -> solvent_exposure, ss -> secondary_structure, ce -> charge_environment, tp -> tryptophan_proximity, cr -> cysteine_resemblance, me -> methionine_exclusion, FRET -> fret_sensitivity. Those tags are that program's private naming and are recorded here only so the correspondence is written down somewhere; they are not values of any item.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_label_score.artifact_id` | code | The artifact these scores belong to, so a table of them is provenance- tracked like any other result. |
| `_mmfdb_label_score.asym_id` | code | Chain the scored position is in, as mmCIF names a chain. |
| `_mmfdb_label_score.comp_id` | ucode | Residue type at that position, carried so a table of scores is readable without the structure beside it. |
| `_mmfdb_label_score.definition` | ucode | WHOSE definition of the score_type this value follows -- the program or published method that defines the number, not a code for it. Two programs may both report a "tryptophan proximity score" and not mean the same number: one may count tryptophans inside a radius and another weight them by distance, and the two are not comparable even though the score_type is. Recording the definition is what lets a reader pool the values that may be pooled and separate the ones that may not, without parsing settings whose keys differ per implementation. Read it with score_type, which already says what is being scored: the pair (`tryptophan_proximity`, `labelizer`) is "tryptophan proximity, as Labelizer defines it". The value here therefore names only the *source*, and does not repeat the quantity. A name here is a name, not an abbreviation. An implementation's internal tag for a score -- Labelizer calls its tryptophan-proximity parameter `tp` and its charge environment `ce` -- is private to that program and means nothing to a reader of this dictionary. If one program grows two incompatible definitions of the same score_type, add a second value that says so in words. Absent means the definition was not recorded -- never "the usual one". |
| `_mmfdb_label_score.label_score_id` | code |  |
| `_mmfdb_label_score.score_type` | ucode | WHAT is being scored. Deliberately coarse, because it is the join key: every tryptophan-proximity score is `tryptophan_proximity` whoever computed it and however, so they can be compared, pooled or plotted against each other without knowing the implementation. Which implementation produced a particular value is _mmfdb_label_score.definition, and the two answer different questions -- the same split as _mmfdb_operation.operation_type and .algorithm. |
| `_mmfdb_label_score.seq_id` | int | Sequence position scored. With asym_id this locates the residue, and is what joins a score to _flr_poly_probe_position -- so "which sites did we score, and which did we label" is one query rather than two files. |
| `_mmfdb_label_score.status` | ucode | Why a position has no value, when it has none. This exists so that "excluded on purpose" and "could not be computed" are different facts, which is exactly what an in-band sentinel destroys. |
| `_mmfdb_label_score.units` | ucode | An _mmfdb_units code. Most of these scores are `dimensionless`, which is a claim worth making explicitly rather than by omission -- a solvent exposure reported as an area is `angstroms` squared and a proximity as `angstroms`, and which one a definition uses is not guessable. |
| `_mmfdb_label_score.value` | float | The score. Absent when it was not computed -- see status. Never a sentinel: a magic -1 in a float column is indistinguishable from a measurement to everything except the code that wrote it. |

## `_mmfdb_object`

Content-addressed object store entry (MMFDB internal).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_object.content_md5` | code |  |
| `_mmfdb_object.content_sha256` | code |  |
| `_mmfdb_object.created_by_user_uuid` | code |  |
| `_mmfdb_object.metadata_json` | code |  |
| `_mmfdb_object.mime_type` | code |  |
| `_mmfdb_object.object_uuid` | code |  |
| `_mmfdb_object.original_filename` | code |  |
| `_mmfdb_object.refcount` | int |  |
| `_mmfdb_object.size_bytes` | int |  |
| `_mmfdb_object.storage_mode` | code |  |
| `_mmfdb_object.storage_path` | code |  |

## `_mmfdb_object_acl`

Access control list for objects. Each object has one ACL row.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_object_acl.inherits_from_id` | code |  |
| `_mmfdb_object_acl.inherits_from_type` | code |  |
| `_mmfdb_object_acl.mode` | int |  |
| `_mmfdb_object_acl.object_id` | code |  |
| `_mmfdb_object_acl.object_type` | code |  |
| `_mmfdb_object_acl.owner_group_id` | code |  |
| `_mmfdb_object_acl.owner_user_id` | code |  |

## `_mmfdb_operation`

A data-processing operation recorded for provenance tracking.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_operation.algorithm` | code | WHICH algorithm carried out this _mmfdb_operation.operation_type. `operation_type` says what was done and is deliberately coarse, because it is the join key: everything that produces a per-burst lifetime is `burst_lifetime_fitting`, so a reader can find them all without knowing how any of them worked. That coarseness is a problem for the reader who does care -- a maximum-likelihood lifetime, a phasor lifetime and a moment-derived lifetime are not the same estimator, do not have the same bias, and must not be pooled into one histogram. Recording the estimator is what lets them be told apart without parsing settings_json, whose keys differ per implementation and are not a controlled vocabulary. Two operations of the same type and different algorithm are different analyses, and a reader may keep both. Two of the same type AND the same algorithm differing only in settings are re-runs, distinguished by _mmfdb_operation.settings_hash. Absent means unrecorded, not "the usual one". A writer that knows its estimator says so; nothing infers one. |
| `_mmfdb_operation.command_line` | text | The command line that produced this operation, for operations run by an external tool (operation_type ``external_tool``). Stored verbatim as the invocation string so that the exact call is queryable rather than buried in free-form settings_json. Null for in-process operations. |
| `_mmfdb_operation.dictionary_hash` | code | SHA-256 of the bytes of mmfdb_flr_ext.dic in force when this operation was recorded, lowercase hexadecimal. A version is what an author declares; this is what was actually loaded, and the two disagree exactly when someone edited a dictionary without bumping it. |
| `_mmfdb_operation.dictionary_version` | code | The ``_dictionary.version`` of mmfdb_flr_ext.dic in force when this operation was recorded. An operation is tagged with controlled terms, and a term can be renamed or withdrawn by a later revision; without this the row cannot say which vocabulary it meant, and a reader has no way to tell drift from a typo. |
| `_mmfdb_operation.ended_at` | line | When it finished, ISO-8601 UTC. Null while it is still running. |
| `_mmfdb_operation.error_message` | text | Why it failed. A failed operation is still provenance: it records that something was attempted, which a missing row does not. |
| `_mmfdb_operation.exit_code` | int | Process exit status of an externally executed operation: 0 on success, non-zero on failure, negative on POSIX signal termination. Distinct from ``status``, which is the recorded provenance lifecycle state. Null for in-process operations. |
| `_mmfdb_operation.experiment_id` | code | The flr_experiment this operation belongs to, if any. |
| `_mmfdb_operation.metadata_json` | text | Anything else the caller attached, as JSON. |
| `_mmfdb_operation.operation_id` | code |  |
| `_mmfdb_operation.operation_type` | code |  |
| `_mmfdb_operation.operator_user_id` | code | Who ran it. |
| `_mmfdb_operation.protocol_id` | code |  |
| `_mmfdb_operation.protocol_version` | int |  |
| `_mmfdb_operation.runtime_environment_json` | text | Interpreter, platform and library versions at the time of the run. |
| `_mmfdb_operation.settings_hash` | code | Digest of the canonicalised settings, and therefore the identity of a run. Two operations of the same type with the same hash are the same computation, which is what lets a recomputation replace a result instead of accumulating beside it. |
| `_mmfdb_operation.settings_json` | text | The operation's parameters, as JSON. Typed parameters are also written as mmfdb_parameter rows; this is the verbatim bag, so a parameter with no declared schema is still recorded rather than dropped. |
| `_mmfdb_operation.setup_id` | code | The instrument setup in force, if any. |
| `_mmfdb_operation.software_module` | line | The module or subcommand within that program. |
| `_mmfdb_operation.software_package` | line | The program that performed the operation. Deliberately not defaulted to any one application: the provenance model is tool-agnostic, and a default attribution would quietly make it not so. |
| `_mmfdb_operation.software_version` | line | Its version, so a result can be traced to what produced it. |
| `_mmfdb_operation.started_at` | line | When the operation began, ISO-8601 UTC. |
| `_mmfdb_operation.status` | code |  |
| `_mmfdb_operation.traceback_summary` | text | An abbreviated traceback for a failed operation. |
| `_mmfdb_operation.validation_status` | code |  |

## `_mmfdb_operation_artifact`

Links an operation to its input/output artifacts.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_operation_artifact.artifact_id` | code |  |
| `_mmfdb_operation_artifact.checksum_snapshot` | code |  |
| `_mmfdb_operation_artifact.direction` | code |  |
| `_mmfdb_operation_artifact.id` | int |  |
| `_mmfdb_operation_artifact.metadata_json` | code |  |
| `_mmfdb_operation_artifact.operation_id` | code |  |
| `_mmfdb_operation_artifact.ordinal` | int |  |
| `_mmfdb_operation_artifact.role` | code |  |

## `_mmfdb_operation_parameter_def`

Typed parameter schema for an operation type — the data-side analog of a chinet node's typed ports. One row per (operation_type, name) declares the type, units, default, bounds, whether the parameter is required, and whether it is repeatable (role-indexed). Operation parameter rows in mmfdb_parameter are validated against this schema at registration.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_operation_parameter_def.def_id` | int |  |
| `_mmfdb_operation_parameter_def.default_value` | text |  |
| `_mmfdb_operation_parameter_def.description` | text |  |
| `_mmfdb_operation_parameter_def.lower_bound` | float |  |
| `_mmfdb_operation_parameter_def.name` | code |  |
| `_mmfdb_operation_parameter_def.operation_type` | code |  |
| `_mmfdb_operation_parameter_def.repeatable` | boolean |  |
| `_mmfdb_operation_parameter_def.required` | boolean |  |
| `_mmfdb_operation_parameter_def.role_domain` | code | Names the role domain for a repeatable parameter (e.g. detector_channel). |
| `_mmfdb_operation_parameter_def.units` | code |  |
| `_mmfdb_operation_parameter_def.upper_bound` | float |  |
| `_mmfdb_operation_parameter_def.value_type` | code |  |

## `_mmfdb_optical_property`

A scalar optical property of a probe: a quantum yield, a molar extinction coefficient, an absorption or emission maximum. These had nowhere to live. Nothing in the loaded dictionaries -- mmCIF std, PDBx, DDL, MA, IHM, IHM-FLR, or the MMFDB extensions -- declares an item for a fluorescence quantum yield or an extinction coefficient; the only near matches are `_em_detector.detective_quantum_efficiency`, which is a detector property, and the crystallographic `_refine.ls_extinction_*` family, which is about absorption in a crystal and not about a dye. So every program in this stack kept them in a private category of its own, and two files describing the same dye could not be compared. The shape is deliberately generic -- a name, a value and a unit -- because it mirrors the `optical_properties` table this database already has, and because the list of scalars worth recording about a dye is open. A property whose name is not in the enumeration below is a property nobody has agreed on yet; add it here rather than inventing a category. Spectra are NOT scalars and do not belong here: see _mmfdb_spectrum.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_optical_property.id` | int |  |
| `_mmfdb_optical_property.probe_id` | code | The probe this is a property of. Joins to `_flr_probe_list.probe_id`, so a dye described here and a dye described in flrCIF are the same dye. |
| `_mmfdb_optical_property.property_name` | ucode | WHICH scalar this is. DELIBERATELY NOT AN ENUMERATION. An `_item_enumeration` here is a closed set and generates a CHECK constraint, and the primary dataset in this stack would violate it: 19882 optical properties are stored under 76 distinct names written by importers that never agreed -- `qy` beside `q_fluor`, `ext_coeff` beside `molar_extinction`, `em_max` beside `Emission max`, some of it mojibake -- with `unit` NULL on every one. Filter and detector properties share the table with dye properties. Declaring a closed set would make a fresh database reject the data it exists to hold, which is a worse failure than an uncontrolled column. The CANONICAL names a writer should use, and what they mean: quantum_yield fluorescence quantum yield, dimensionless, 0-1 extinction_coefficient molar extinction at the absorption maximum excitation_maximum wavelength of the absorption maximum emission_maximum wavelength of the emission maximum fluorescence_lifetime the unquenched fluorescence lifetime anisotropy_fundamental the fundamental anisotropy r0, dimensionless steric_radius chromophore radius as a steric obstacle hydrodynamic_radius radius governing rotational diffusion A reader must expect others, and must not read a missing `unit` as dimensionless. Migrating the stored names onto the canonical ones is a separate, tracked job; it is not something a dictionary can assert. |
| `_mmfdb_optical_property.property_value` | float | The value. Absent when the property was not measured -- never zero: a quantum yield of 0 is a real and unusual claim about a dye. |
| `_mmfdb_optical_property.unit` | ucode | An _mmfdb_column.units term, plus the two an extinction coefficient needs. `dimensionless` for a quantum yield or an anisotropy is a positive claim and should be written rather than omitted. |

## `_mmfdb_parameter`

Named parameters associated with an operation.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_parameter.bounds_on` | int |  |
| `_mmfdb_parameter.confidence_interval_high` | float |  |
| `_mmfdb_parameter.confidence_interval_low` | float |  |
| `_mmfdb_parameter.expression` | code |  |
| `_mmfdb_parameter.initial_value` | float |  |
| `_mmfdb_parameter.lower_bound` | float |  |
| `_mmfdb_parameter.mapping_json` | code |  |
| `_mmfdb_parameter.metadata_json` | code |  |
| `_mmfdb_parameter.name` | code |  |
| `_mmfdb_parameter.operation_id` | code |  |
| `_mmfdb_parameter.parameter_id` | int |  |
| `_mmfdb_parameter.parameter_type` | code |  |
| `_mmfdb_parameter.parameter_uuid` | code |  |
| `_mmfdb_parameter.prior_json` | code |  |
| `_mmfdb_parameter.role` | code | Optional role/index distinguishing repeated parameter rows of the same name on one operation (the data-side analog of chinet's multiple ports), e.g. the detector channel for a per-channel shift. NULL/empty for scalar parameters (exactly one row per operation+name). |
| `_mmfdb_parameter.standard_error` | float |  |
| `_mmfdb_parameter.units` | code |  |
| `_mmfdb_parameter.upper_bound` | float |  |
| `_mmfdb_parameter.value` | float |  |

## `_mmfdb_pipeline`

A saveable, shareable workflow document (PRD-22): a named, versioned graph of transformer invocations. The graph structure lives in mmfdb_pipeline_node / mmfdb_pipeline_edge (structured, not a blob); ownership + visibility mirror the study/object pattern.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_pipeline.created_by_user_id` | code |  |
| `_mmfdb_pipeline.description` | text |  |
| `_mmfdb_pipeline.is_public` | int |  |
| `_mmfdb_pipeline.name` | code |  |
| `_mmfdb_pipeline.pipeline_id` | code |  |
| `_mmfdb_pipeline.version` | code |  |

## `_mmfdb_pipeline_edge`

A typed wire of a pipeline: source_node.source_port feeds target_node.target_port.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_pipeline_edge.edge_row_id` | int |  |
| `_mmfdb_pipeline_edge.pipeline_id` | code |  |
| `_mmfdb_pipeline_edge.source_node` | code |  |
| `_mmfdb_pipeline_edge.source_port` | code |  |
| `_mmfdb_pipeline_edge.target_node` | code |  |
| `_mmfdb_pipeline_edge.target_port` | code |  |

## `_mmfdb_pipeline_node`

One node of a pipeline: a transformer invocation binding an operation_type to bound parameters. parameters_json is the leaf parameter bag (schemaless per operation type, like an operation's metadata) — the graph structure itself is in the typed node/edge rows, not a blob.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_pipeline_node.node_name` | code |  |
| `_mmfdb_pipeline_node.node_row_id` | int |  |
| `_mmfdb_pipeline_node.operation_type` | code |  |
| `_mmfdb_pipeline_node.parameters_json` | text |  |
| `_mmfdb_pipeline_node.pipeline_id` | code |  |

## `_mmfdb_pipeline_run`

One execution of a pipeline. Groups the recorded operation chain (via mmfdb_pipeline_run_operation) so a run is queryable as a unit.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_pipeline_run.created_by_user_id` | code |  |
| `_mmfdb_pipeline_run.is_public` | int |  |
| `_mmfdb_pipeline_run.name` | code |  |
| `_mmfdb_pipeline_run.pipeline_id` | code |  |
| `_mmfdb_pipeline_run.pipeline_run_id` | code |  |
| `_mmfdb_pipeline_run.status` | code |  |

## `_mmfdb_pipeline_run_operation`

Links a pipeline run to the operations it produced, in execution order — the run-grouping over the recorded operation chain.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_pipeline_run_operation.operation_id` | code |  |
| `_mmfdb_pipeline_run_operation.ordinal` | int |  |
| `_mmfdb_pipeline_run_operation.pipeline_run_id` | code |  |
| `_mmfdb_pipeline_run_operation.row_id` | int |  |

## `_mmfdb_probe`

What kind of thing a probe is, and who makes it. Kept in the _mmfdb_ namespace rather than added to _flr_probe_list so a future IHM-FLR item of the same name cannot collide with it; the schema binding puts both on the existing `probes` table, so this adds columns, not a table. `_flr_probe_list.probe_origin` answers a different question -- how the probe got onto the molecule (intrinsic / extrinsic). A fluorescent protein is intrinsic and a spin label extrinsic, but neither fact tells you that one fluoresces and the other does not, which is what decides whether a Forster radius exists at all.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_probe.dipole_atoms` | text | The two atom names whose separation defines the transition dipole, stored as an array. Absent is a positive statement, not missing data: it means the probe is modelled as an isotropic emitter, which is what kappa^2 = 2/3 assumes. A consumer that silently substitutes the isotropic value for a probe whose dipole *was* recorded, and lost, gets a plausible orientation factor and no indication it was invented. |
| `_mmfdb_probe.negative_atoms` | text | Atom names carrying a formal negative charge, as an array. See _mmfdb_probe.positive_atoms. |
| `_mmfdb_probe.positive_atoms` | text | Atom names carrying a formal positive charge, as an array. A probe's net charge is not decoration: it decides whether the probe is attracted to or repelled from the surface it is tethered beside, and a sulfonated dye beside an acidic patch behaves unlike a neutral one. |
| `_mmfdb_probe.probe_id` | code | The probe this row describes; the _flr_probe_list.chromophore_name. |
| `_mmfdb_probe.probe_type` | ucode | What the probe is. Omitting it is read as `unspecified`, which is what a store written before this item existed means; `unspecified` is therefore also a value that can be written deliberately. |
| `_mmfdb_probe.vendor` | text | Who supplies it -- ATTO, Lumiprobe, AlexaFluor. Not an identifier: two vendors sell probes of the same name and one vendor renames its own. |

## `_mmfdb_protocol`

A named, versioned procedure (measurement / processing / analysis) that operations reference, so every recorded operation names the exact procedure + version it executed ("re-run protocol X v3"). Append-only by version: editing a protocol creates a new row (new protocol_id) with version = max+1 for that name; operations keep the version they ran. The parameter schema is the operation_type's declared schema (mmfdb_operation_parameter_def, PRD-11) — no forked parameter stack.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_protocol.category` | code |  |
| `_mmfdb_protocol.created_by_user_id` | code |  |
| `_mmfdb_protocol.description` | text |  |
| `_mmfdb_protocol.is_public` | int |  |
| `_mmfdb_protocol.name` | code | The protocol's stable name; shared across versions (UNIQUE with version, enforced by the repository). |
| `_mmfdb_protocol.operation_type` | code | The PRD-11 operation kind this protocol realizes; its declared parameter schema (mmfdb_operation_parameter_def) is the protocol's parameter schema. |
| `_mmfdb_protocol.protocol_id` | code |  |
| `_mmfdb_protocol.setup_id` | code |  |
| `_mmfdb_protocol.version` | int |  |

## `_mmfdb_provenance_artifact`

One data node in the provenance graph (a source, intermediate, or result).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_provenance_artifact.artifact_id` | line |  |
| `_mmfdb_provenance_artifact.artifact_kind` | line |  |
| `_mmfdb_provenance_artifact.checksum` | line |  |
| `_mmfdb_provenance_artifact.checksum_algorithm` | code |  |
| `_mmfdb_provenance_artifact.data_format` | line |  |
| `_mmfdb_provenance_artifact.ordinal` | int |  |
| `_mmfdb_provenance_artifact.row_grain` | line | What one row of a tabular artifact is (the _mmfdb_artifact.row_grain term), for example burst or bin. Absent for non-tabular artifacts. |

## `_mmfdb_provenance_edge`

A directed edge in the provenance graph (e.g. an output derived_from an input, or an artifact input_to an operation).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_provenance_edge.operation_id` | line | Operation that created the edge, when the edge was recorded as part of one. |
| `_mmfdb_provenance_edge.ordinal` | int |  |
| `_mmfdb_provenance_edge.relationship_type` | line |  |
| `_mmfdb_provenance_edge.role` | line | Role of the artifact in the operation, for an input_to or produced edge (for example source_file or fit_state). |
| `_mmfdb_provenance_edge.source_node_id` | line |  |
| `_mmfdb_provenance_edge.source_node_type` | code |  |
| `_mmfdb_provenance_edge.source_row_column` | line | Column of the source table that holds the join key, when source and target differ in row grain. |
| `_mmfdb_provenance_edge.target_node_id` | line |  |
| `_mmfdb_provenance_edge.target_node_type` | code |  |
| `_mmfdb_provenance_edge.target_row_column` | line | Column of the target table that the join key is matched to; equal to the source column when omitted. |

## `_mmfdb_provenance_operation`

One recorded operation node: the exact tool invocation that produced a result, with software, version, command line, and timing.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_provenance_operation.algorithm` | line | Algorithm term of the operation (the _mmfdb_operation.algorithm value), when the operation type alone does not name it. |
| `_mmfdb_provenance_operation.command_line` | text |  |
| `_mmfdb_provenance_operation.ended_at` | yyyy-mm-dd:hh:mm |  |
| `_mmfdb_provenance_operation.operation_id` | line |  |
| `_mmfdb_provenance_operation.operation_type` | line |  |
| `_mmfdb_provenance_operation.ordinal` | int |  |
| `_mmfdb_provenance_operation.parameters` | text | JSON object of the step parameters, recorded for exact re-run. |
| `_mmfdb_provenance_operation.settings_hash` | line | Hash of the complete settings of the operation. Two operations of one type with equal hashes ran with the same settings. |
| `_mmfdb_provenance_operation.settings_json` | text | The complete settings of the operation as one JSON object, verbatim. A partial record is not written: a reader reproduces the run from this item alone. |
| `_mmfdb_provenance_operation.software_package` | line |  |
| `_mmfdb_provenance_operation.software_version` | line |  |
| `_mmfdb_provenance_operation.started_at` | yyyy-mm-dd:hh:mm |  |
| `_mmfdb_provenance_operation.status` | code |  |

## `_mmfdb_provenance_parameter`

One named, typed parameter value of a recorded operation: a fitted or fixed model parameter with its uncertainty and bounds.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_provenance_parameter.bounds_on` | line | Whether the bounds apply to the value itself or to a transformed variable. |
| `_mmfdb_provenance_parameter.initial_value` | float | Value the parameter started from. |
| `_mmfdb_provenance_parameter.lower_bound` | float | Lower bound, in the units of the parameter. |
| `_mmfdb_provenance_parameter.name` | line | Parameter name as the model defines it. |
| `_mmfdb_provenance_parameter.operation_id` | line | Operation the parameter belongs to; matches _mmfdb_provenance_operation.operation_id. |
| `_mmfdb_provenance_parameter.ordinal` | int | Row number of the parameter in the file. |
| `_mmfdb_provenance_parameter.parameter_id` | line | Identifier of the parameter node, which an edge between two parameters (for example a link of one parameter to another) refers to. |
| `_mmfdb_provenance_parameter.parameter_type` | line | free, fixed or linked. |
| `_mmfdb_provenance_parameter.role` | line | Role of the parameter in the operation. |
| `_mmfdb_provenance_parameter.standard_error` | float | Standard error of the value, when estimated. |
| `_mmfdb_provenance_parameter.units` | line | Units of the value. |
| `_mmfdb_provenance_parameter.upper_bound` | float | Upper bound, in the units of the parameter. |
| `_mmfdb_provenance_parameter.value` | float | Value of the parameter. |

## `_mmfdb_reagent_lot`

A consumable lot — a fluorophore/buffer/optical-filter/kit with lot number and expiry — so a result can tie to exactly what was used. Linked to operations / setups / samples through mmfdb_reagent_usage (orthogonal; no columns added to those tables). A fluorophore lot may optionally reference a known probe.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_reagent_lot.catalog_no` | code |  |
| `_mmfdb_reagent_lot.concentration` | float |  |
| `_mmfdb_reagent_lot.concentration_units` | code |  |
| `_mmfdb_reagent_lot.created_by_user_id` | code |  |
| `_mmfdb_reagent_lot.details` | text |  |
| `_mmfdb_reagent_lot.expiry` | text |  |
| `_mmfdb_reagent_lot.kind` | code |  |
| `_mmfdb_reagent_lot.lot_id` | code |  |
| `_mmfdb_reagent_lot.lot_number` | code |  |
| `_mmfdb_reagent_lot.name` | code |  |
| `_mmfdb_reagent_lot.opened_at` | text |  |
| `_mmfdb_reagent_lot.probe_id` | code |  |
| `_mmfdb_reagent_lot.received_at` | text |  |
| `_mmfdb_reagent_lot.vendor` | code |  |

## `_mmfdb_reagent_usage`

Many-to-many link of a reagent lot to what used it — an operation (a measurement or processing step), a setup (e.g. an installed filter set), or a sample (e.g. a labeling dye lot). Orthogonal to those tables.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_reagent_usage.lot_id` | code | References mmfdb_reagent_lot.lot_id (a logical reference; the dictionary-generated lot_id code key is not emitted as a PRIMARY KEY, so no hard FK — the repository manages reagent-usage integrity, as for mmfdb_study_member.study_id). |
| `_mmfdb_reagent_usage.role` | code |  |
| `_mmfdb_reagent_usage.target_id` | code |  |
| `_mmfdb_reagent_usage.target_type` | code |  |
| `_mmfdb_reagent_usage.usage_row_id` | int |  |

## `_mmfdb_session`

User authentication sessions.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_session.client_host` | line |  |
| `_mmfdb_session.client_metadata_json` | text |  |
| `_mmfdb_session.client_name` | line |  |
| `_mmfdb_session.expires_at` | text |  |
| `_mmfdb_session.last_used_at` | text |  |
| `_mmfdb_session.revoked_at` | text |  |
| `_mmfdb_session.session_id` | code |  |
| `_mmfdb_session.token_hash` | line |  |
| `_mmfdb_session.user_id` | code |  |

## `_mmfdb_setup`

Structured reading/processing setup record for TTTR detector setups. Each named setup corresponds to one mmfdb_setup row addressed by the deterministic id from setup_id_for_name().

| Item | Type | Description |
|---|---|---|
| `_mmfdb_setup.created_by_user_id` | code | User who created this detector setup. NULL for builtin/shared setups. |
| `_mmfdb_setup.is_public` | int | GUI visibility flag. 1 (default) = visible to all users; 0 = visible only to the owning user (created_by_user_id). |
| `_mmfdb_setup.macro_time_resolution` | float |  |
| `_mmfdb_setup.make_fine` | int | Correlator make_fine flag for FCS channel setups. |
| `_mmfdb_setup.micro_time_binning` | int |  |
| `_mmfdb_setup.micro_time_resolution` | float |  |
| `_mmfdb_setup.n_bins` | int | Correlator number of bins for FCS channel setups. |
| `_mmfdb_setup.n_casc` | int | Correlator number of cascades for FCS channel setups. |
| `_mmfdb_setup.name` | line |  |
| `_mmfdb_setup.setup_id` | code |  |
| `_mmfdb_setup.version` | int |  |

## `_mmfdb_setup_calibration`

Append-only calibration snapshot for a detector channel within a reading/processing setup. Each row records the G-factor, l1, and l2 values that were current at a specific point in time, together with the method used to determine them and an optional reference to the MMFDB artifact that produced them. Rows are never updated or deleted; a new row is INSERTed each time the calibration values are set, preserving the full history.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_setup_calibration.calibrated_at` | datetime |  |
| `_mmfdb_setup_calibration.channel_name` | line |  |
| `_mmfdb_setup_calibration.created_by_user_id` | code | User who created this calibration snapshot. NULL for migrated defaults. |
| `_mmfdb_setup_calibration.g_factor` | float |  |
| `_mmfdb_setup_calibration.g_factor_calibration_id` | text | The MMFDB calibration artifact identifier for this G-factor. |
| `_mmfdb_setup_calibration.g_factor_channels` | text | JSON array of channel indices used for G-factor calculation. |
| `_mmfdb_setup_calibration.id` | int |  |
| `_mmfdb_setup_calibration.l1` | float | Leakage parameter l1 (donor leakage into acceptor channel). |
| `_mmfdb_setup_calibration.l2` | float | Leakage parameter l2 (acceptor leakage into donor channel). |
| `_mmfdb_setup_calibration.method` | line | Method used to determine the calibration values (e.g. manual, migrated, jordi_g_factor). |
| `_mmfdb_setup_calibration.setup_id` | code |  |

## `_mmfdb_setup_detector_channel`

Detector channel definition within a reading/processing setup. Each row defines one detector channel with its routing, micro-time windows, G-factor, and leakage parameters.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_setup_detector_channel.channels` | text | JSON array of TCSPC channel indices routed to this detector. |
| `_mmfdb_setup_detector_channel.g_factor` | float |  |
| `_mmfdb_setup_detector_channel.g_factor_calibration_id` | text | The MMFDB calibration artifact identifier for this G-factor. |
| `_mmfdb_setup_detector_channel.g_factor_channels` | text | JSON array of channel indices used for G-factor calculation. |
| `_mmfdb_setup_detector_channel.id` | int |  |
| `_mmfdb_setup_detector_channel.l1` | float | Leakage parameter l1 (donor leakage into acceptor channel). |
| `_mmfdb_setup_detector_channel.l2` | float | Leakage parameter l2 (acceptor leakage into donor channel). |
| `_mmfdb_setup_detector_channel.micro_time_ranges` | text | JSON array of [start, end] micro-time window pairs. |
| `_mmfdb_setup_detector_channel.name` | line |  |
| `_mmfdb_setup_detector_channel.setup_id` | code |  |

## `_mmfdb_setup_fcs_pair`

FCS channel correlation pair within an FCS channel setup. Each row defines one pair of detector channels to correlate, with optional kind/label (e.g. auto, cross).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_setup_fcs_pair.channel_a` | line | Name of the first detector channel in the correlation pair. |
| `_mmfdb_setup_fcs_pair.channel_b` | line | Name of the second detector channel in the correlation pair. |
| `_mmfdb_setup_fcs_pair.id` | int |  |
| `_mmfdb_setup_fcs_pair.kind` | line | Optional kind/label for the pair (e.g. auto, cross). |
| `_mmfdb_setup_fcs_pair.make_fine` | int | Correlator make_fine flag for this correlation pair (0/1). Overrides the setup-level default when set. |
| `_mmfdb_setup_fcs_pair.n_bins` | int | Correlator number of bins for this correlation pair. Overrides the setup-level default when set. |
| `_mmfdb_setup_fcs_pair.n_casc` | int | Correlator number of cascades for this correlation pair. Overrides the setup-level default when set. |
| `_mmfdb_setup_fcs_pair.name` | line |  |
| `_mmfdb_setup_fcs_pair.setup_id` | code |  |

## `_mmfdb_setup_pie_window`

PIE (Pulsed Interleaved Excitation) or micro-time window definition within a reading/processing setup. Each row defines one named window with its start and end micro-time bins.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_setup_pie_window.end` | int | End micro-time bin (inclusive). |
| `_mmfdb_setup_pie_window.id` | int |  |
| `_mmfdb_setup_pie_window.name` | line |  |
| `_mmfdb_setup_pie_window.setup_id` | code |  |
| `_mmfdb_setup_pie_window.start` | int | Start micro-time bin (inclusive). |

## `_mmfdb_spectrum`

An excitation or emission spectrum of a probe, as two arrays. Kept out of _mmfdb_optical_property because a spectrum is not a scalar and flattening it into name/value pairs would lose the pairing between a wavelength and its intensity. The only spectral categories anywhere in the loaded dictionaries are NMR ones (`_pdbx_nmr_spectral_*`), which describe a different measurement entirely. A spectral overlap -- and therefore a Forster radius -- is computed from the donor emission and the acceptor excitation, so these two are what make R0 derivable rather than supplied.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_spectrum.id` | int |  |
| `_mmfdb_spectrum.intensity_unit` | ucode | `normalized` is the common case and means the peak is 1; it does NOT mean the area is 1, and a spectral overlap integral has to renormalise. |
| `_mmfdb_spectrum.intensity_values` | text |  |
| `_mmfdb_spectrum.probe_id` | code |  |
| `_mmfdb_spectrum.spectrum_type` | ucode |  |
| `_mmfdb_spectrum.wavelength_unit` | ucode | `nm` rather than the `nanometres` of _mmfdb_column.units, because that is what the 2896 spectra already stored in this stack are labelled with and a dictionary that renamed them would invalidate every existing row to no benefit. The two spellings mean the same thing; a consumer converting between the column vocabulary and this one maps them. |
| `_mmfdb_spectrum.wavelengths` | text | The wavelength axis, paired elementwise with the intensities. Stored as an array; in a CIF serialisation the pairing is one row per point. |

## `_mmfdb_state_transition`

Lifecycle transition log (LIMS P1). One row per state change of a tracked entity (sample / artifact / operation): who moved it, when, from where to where, and why. The log is the source of truth; an entity's "current state" is the latest non-deleted transition's to_state (optionally cached on the entity). Allowed transitions are declared in mmfdb_state_transition_rule.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_state_transition.entity_id` | code |  |
| `_mmfdb_state_transition.entity_type` | code | The kind of entity whose state changed (e.g. sample, artifact, operation). |
| `_mmfdb_state_transition.from_state` | code | The prior state; null/empty for the initial transition into a lifecycle. |
| `_mmfdb_state_transition.operator_user_id` | code | The user who performed the transition (references flr_sample_users.user_id). ############################################ ## mmfdb_state_transition_rule (PRD-12) # ############################################ |
| `_mmfdb_state_transition.reason` | text |  |
| `_mmfdb_state_transition.to_state` | code |  |
| `_mmfdb_state_transition.transition_id` | int |  |

## `_mmfdb_state_transition_rule`

Allowed lifecycle transitions per entity_type. A transition_state() call is rejected unless a matching (entity_type, from_state, to_state) rule exists; a null from_state declares an allowed initial state. Seeded from the authored lifecycle definitions (data/state_lifecycle_defs.json).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_state_transition_rule.entity_type` | code |  |
| `_mmfdb_state_transition_rule.from_state` | code |  |
| `_mmfdb_state_transition_rule.rule_id` | int |  |
| `_mmfdb_state_transition_rule.to_state` | code |  |

## `_mmfdb_study`

A study/project: a named grouping of samples and datasets with ownership + visibility and configurable per-study metadata. Promotes the loose project_id string into a first-class entity (samples/artifacts join via mmfdb_study_member; custom fields live in mmfdb_study_key_value — the existing key-value pattern, not a new EAV stack).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_study.created_by_user_id` | code |  |
| `_mmfdb_study.description` | text |  |
| `_mmfdb_study.is_public` | int |  |
| `_mmfdb_study.name` | code |  |
| `_mmfdb_study.study_id` | code |  |

## `_mmfdb_study_key_value`

Configurable per-study metadata as key/value pairs (the existing key-value pattern; no new typed EAV stack). (study_id, key) is unique (repository).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_study_key_value.details` | text |  |
| `_mmfdb_study_key_value.key` | code |  |
| `_mmfdb_study_key_value.kv_id` | int |  |
| `_mmfdb_study_key_value.study_id` | code | References mmfdb_study.study_id (a logical reference; see mmfdb_study_member). |
| `_mmfdb_study_key_value.value` | text |  |

## `_mmfdb_study_member`

Many-to-many membership linking existing samples / artifacts into a study. member_type is 'sample' or 'artifact'; (study_id, member_type, member_id) is unique (enforced by the repository).

| Item | Type | Description |
|---|---|---|
| `_mmfdb_study_member.member_id` | code |  |
| `_mmfdb_study_member.member_row_id` | int |  |
| `_mmfdb_study_member.member_type` | code |  |
| `_mmfdb_study_member.role` | code |  |
| `_mmfdb_study_member.study_id` | code | References mmfdb_study.study_id (a logical reference; the dictionary-generated study_id is not emitted as a PRIMARY KEY, so no hard FK — the repository manages study membership integrity, as for mmfdb_operation.protocol_id). |

## `_mmfdb_units`

One row per unit: its code, how it is written for a person, and what it is in SI. mmCIF's ITEM_UNITS_LIST gives codes and prose and nothing else, so every consumer that wanted to *show* a unit invented its own abbreviation and every consumer that wanted to *convert* one invented its own factor. In ChiSurf alone that produced three in-band conventions for saying the same thing -- "Duration (ms)" in a burst table, "Name \| unit" in an expression column header, and bare dictionaries of factors in the DEER and FCS readers -- none of which agreed on spelling. This is the one table. A display layer reads `symbol`; a converter reads `si_factor` and `si_unit`; nothing parses a unit back out of a name. Serialization vocabulary, like the rest of this dictionary: no table is materialised for it.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_units.code` | code | The canonical code, as used by _mmfdb_column.units and _item_units.code. Follows ITEM_UNITS_LIST where that has the unit. |
| `_mmfdb_units.si_factor` | float | Multiply a value in this unit by this to get _mmfdb_units.si_unit. Absent for a unit that is not a scaled SI quantity. |
| `_mmfdb_units.si_unit` | code | The SI (or SI-derived) unit _mmfdb_units.si_factor converts to. |
| `_mmfdb_units.symbol` | line | How the unit is written for a person: "ns", "kHz", "ms". This is what an axis label or a table header shows, and having it here is what stops each display inventing its own. |

## `_mmfdb_vocabulary`

Vocabulary registry for extensible code fields used across MMFDB. Each row maps a field_name + value pair to a display name and description.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_vocabulary.description` | text |  |
| `_mmfdb_vocabulary.display_name` | line |  |
| `_mmfdb_vocabulary.field_name` | code |  |
| `_mmfdb_vocabulary.is_active` | int |  |
| `_mmfdb_vocabulary.is_builtin` | int |  |
| `_mmfdb_vocabulary.value` | ucode |  |

## `_mmfdb_workflow`

The declarative workflow that produced the deposit: its identity and the verbatim YAML definition, so the pipeline can be re-run. One row.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_workflow.definition` | text | The verbatim workflow YAML, embedded so the deposit is reproducible without any external file. |
| `_mmfdb_workflow.description` | text |  |
| `_mmfdb_workflow.name` | line |  |
| `_mmfdb_workflow.version` | int |  |

## `_mmfdb_workflow_step`

One declared step of the workflow: the tool it runs and how.

| Item | Type | Description |
|---|---|---|
| `_mmfdb_workflow_step.operation_type` | line |  |
| `_mmfdb_workflow_step.ordinal` | int |  |
| `_mmfdb_workflow_step.run` | text | The command-line template (for a cmd step) or the module:callable target (for a python step). |
| `_mmfdb_workflow_step.run_kind` | code |  |
| `_mmfdb_workflow_step.software_package` | line |  |
| `_mmfdb_workflow_step.software_version` | line |  |
| `_mmfdb_workflow_step.step_id` | line |  |

## `_struct_ref`

| Item | Type | Description |
|---|---|---|
| `_struct_ref.organism` | text | Source organism of the reference sequence. |
