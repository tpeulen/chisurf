Fitting interface & worked examples
===================================

This section teaches ChiSurf's **fitting interface** — importing data, creating a
fit, the analysis dock, parameters and linking, global fits, nuisances, and plots
— and walks through complete **worked examples** (a full FCS fit with detection-
volume calibration, and a joint anisotropy analysis) using real screenshots of the
application.

It complements the two other layers: the :doc:`Concepts </concepts/index>` explain
the *theory* (e.g. :ref:`FCS <concept-fcs-correlation>`,
:ref:`TCSPC lifetimes <concept-tcspc-lifetime>`,
:ref:`anisotropy <concept-anisotropy>`,
:ref:`filtered FCS <concept-filtered-fcs>`), and the
:doc:`Guides </guides/index>` cover specific single-molecule analyses.

.. toctree::
   :maxdepth: 1
   :caption: The fitting interface

   Introduction <introduction>
   Overview <overview>
   Data import <data_import>
   Fit models <fit_models>
   Creating fits <creating_fits>
   Analysis dock <analysis_dock>
   Parameters <parameters>
   Fit interface <fit_interface>
   Model scores <model_scores>
   Model scoring range <model_scoring_range>
   Parameter optimization <parameter_optimization>
   Parameter sampling <parameter_sampling>
   Multiple document interface <multiple_document_interface>
   Fit plots <fit_plots>
   Parameter scan <parameter_scan>
   Nuisances <nuisances>
   Equation parsing <equation_parsing>

.. toctree::
   :maxdepth: 1
   :caption: Fluorescence decay models

   Fluorescence lifetime <fluorescence_lifetime>
   FRET lines <fret_lines>
   Discrete FRET rate constants <discrete_fret_rate_constants>
   Partial donor-donor energy migration <partial_donordonor_energy_migration>
   Worm-like chain <wormlike_chain>
   Reference curves <reference_curves>
   F-Calculator <fcalculator>

.. toctree::
   :maxdepth: 1
   :caption: Anisotropy wizard

   Anisotropy wizard <anisotropy_wizard>

.. toctree::
   :maxdepth: 1
   :caption: Correlator plugin

   Correlator: overview <overview_2>
   Loading & plotting data <loading__plotting_data>
   Photon filter <photon_filter>
   Correlator <correlator>
   Correlation merging <correlation_merging>

.. toctree::
   :maxdepth: 1
   :caption: Parameter dependency graphs

   Global view: overview <overview_3>
   Changing visualizations <changing_visualizations>
   Saving and loading networks <saving_and_loading_networks>
   Linking parameters <linking_parameters>

.. toctree::
   :maxdepth: 1
   :caption: Worked example — calibrating an FCS setup

   Computing FCS curves <computing_fluorescence_correlation_spectroscopy_curves>
   Data format <data_format>
   Test data: calibration <provided_test_data__calibration>
   Test data: live-cell experiments <provided_test_data__live_cell_experiments>
   Test data: simulation <provided_test_data__simulation>
   Determination of background / dark count rate <determination_of_background___dark_count_rate>
   Calibration of detection volume – green excitation <calibration_of_detection_volume__green_excitation>
   Fit of the green-excitation FCS curve <fit_of_a_fcs_curve>
   Calculation of confocal volume <calculation_of_confocal_volume>
   Estimation of the fluorophore concentration <estimation_of_the_fluorophore_concentration>
   Calibration of detection volume – red excitation <calibration_of_detection_volume__red_excitation>
   Fit of the red-excitation FCS curve <fit_of_fcs_curve>
   Calculation of the red detection volume <calculations>
   Correction factors for spectral crosstalk & direct acceptor excitation <correction_factors_for_spectral_crosstalk__direct_acceptor_excitation>
   Spectral crosstalk of green fluorescence into red detection channel <spectral_crosstalk_of_green_fluorescence_into_red_detection_channel>
   Determination of direct excitation of red fluorophore by green excitation <determination_of_direct_excitation_of_red_fluorophore_by_green_excitation>
   Determination of molecular brightness <determination_of_molecular_brightness>
   Determination of overlap of green & red detection volume <determination_of_overlap_of_green__red_detection_volume>
   Global fit of FCS curves <global_fit_of_fcs_curves>
   Calculation of the overlap volume and co-diffusion amplitude <calculations_2>

.. toctree::
   :maxdepth: 1
   :caption: Worked example — live-cell FCS & FCCS

   Analysis of live cell experiments <analysis_of_live_cell_experiments>
   Adding the membrane-diffusion models <adding_the_membranediffusion_models>
   Fit of autocorrelation curves <fit_of_autocorrelation_curves>
   Crosstalk-induced correlations <crosstalkinduced_correlations>
   Fit of auto- and cross-correlation curves <fit_of_auto_and_crosscorrelation_curves>
   Calculation of co-diffusing molecules <calculation_of_codiffusing_molecules>

.. toctree::
   :maxdepth: 1
   :caption: Worked example — simulated FCS data

   Simulation details <simulation_details>
   Global fit of auto- and cross-correlation curves <global_fit_of_auto_and_crosscorrelation_curves>
   Influence of FRET efficiency <influence_of_fret_efficiency>
   Influence of triplet blinking <influence_of_triplet_blinking>
   Species-filtered FCS to recover dynamics <speciesfiltered_fcs_to_recover_dynamics>

.. toctree::
   :maxdepth: 1
   :caption: Worked example — anisotropy (g-factor & depolarization)

   Determination of g-factor and depolarization factors <determination_of_gfactor_and_depolarization_factors_using_chisurf>
   Data input and file format <data_input_and_file_format>
   Loading the data: defining the reading parameter <loading_the_data_defining_the_reading_parameter>
   Two single files <two_single_files>
   VV/VH format <vv_vh_format>
   Loading the Alexa488 data into the anisotropy plugin <loading_the_alexa488_data_into_the_anisotropy_plugin>
   Step 1: approximating g-factor with a small fluorophore <step_1_approximating_gfactor_with_small_fluorophore>
   Step 2: joint analysis to determine g-factor, ls and lp <step_2_joint_analysis_to_determine_gfactor_ls_and_lp>
   Loading and setting up the eGFP data set <loading_and_setting_up_the_egfp_data_set>
   Setting up the joint global fit of A488 & eGFP <setting_up_the_joint_global_fit_of_a488__egfp>
   Saving & exporting the results <saving__exporting_the_results>
   Re-using the parameters to analyse the actual samples <reusing_the_parameter_to_analyse_the_actual_samples>

.. toctree::
   :maxdepth: 1
   :caption: References

   References <references>
