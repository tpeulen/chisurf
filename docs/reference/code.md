---
type: Reference
title: Code index
description: Every code block in the documentation, with its language and whether it is verified.
tags: [reference, code, index]
anchor: code-index
generator: build_tools/docs/make_registers.py
---

(code-index)=
# Code index

Every code block in the documentation. **Python blocks are verified**:
each is compiled by `test_doc_code.py`, so a snippet that cannot even be
parsed fails the suite, and a block marked ```` ```python run ```` is
additionally executed. A block that must not be run — one that deletes
files, needs a measurement, or shows a fragment — simply omits the
marker and is still compiled.

*926 blocks, 234 Python, 0 executed.*

| # | Language | Section | Lines | Verified | Page |
| --- | --- | --- | --- | --- | --- |
| 1 | `text` | Installation and environment | 3 | — | [docs/getting_started/index.md](/getting_started/index.md) |
| 2 | `text` | Installation and environment | 4 | — | [docs/getting_started/index.md](/getting_started/index.md) |
| 3 | `text` | Colours tell the kind of task | 5 | — | [docs/getting_started/index.md](/getting_started/index.md) |
| 4 | `text` | Theme | 3 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 5 | `text` | Fonts | 4 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 6 | `text` | Fonts | 4 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 7 | `yaml` | Without the window | 6 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 8 | `python` | Without the window | 3 | compiled | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 9 | `text` | What happens before emission | 7 | — | [docs/fundamentals/absorption_and_emission.md](/fundamentals/absorption_and_emission.md) |
| 10 | `text` | Mechanism | 8 | — | [docs/fundamentals/energy_transfer.md](/fundamentals/energy_transfer.md) |
| 11 | `text` | The excited state | 6 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 12 | `text` | Orientation and transfer | 4 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 13 | `text` | Probe and environment | 4 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 14 | `text` | Measuring photons | 5 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 15 | `text` | Reference | 3 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 16 | `text` | Multi-exponential decays | 7 | — | [docs/fundamentals/lifetime_and_quantum_yield.md](/fundamentals/lifetime_and_quantum_yield.md) |
| 17 | `text` | Rotational diffusion | 7 | — | [docs/fundamentals/polarization_and_rotation.md](/fundamentals/polarization_and_rotation.md) |
| 18 | `text` | Collisional quenching and Stern–Volmer | 8 | — | [docs/fundamentals/quenching_and_photophysics.md](/fundamentals/quenching_and_photophysics.md) |
| 19 | `text` | Upward curvature: the sphere of action | 11 | — | [docs/fundamentals/quenching_and_photophysics.md](/fundamentals/quenching_and_photophysics.md) |
| 20 | `text` | Species mixtures | 12 | — | [docs/fundamentals/quenching_and_photophysics.md](/fundamentals/quenching_and_photophysics.md) |
| 21 | `text` | The rate is not constant in time | 10 | — | [docs/fundamentals/quenching_mechanisms.md](/fundamentals/quenching_mechanisms.md) |
| 22 | `text` | Nucleobase-specific quenching | 14 | — | [docs/fundamentals/quenching_mechanisms.md](/fundamentals/quenching_mechanisms.md) |
| 23 | `text` | The three decay laws | 9 | — | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 24 | `python` | Using it headlessly | 12 | compiled | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 25 | `text` | Three AV-to-distance measures | 4 | — | [docs/concepts/accessible_volume.md](/concepts/accessible_volume.md) |
| 26 | `text` | 3. The donor lifetime and the static FRET line | 7 | — | [docs/concepts/accurate_fret.md](/concepts/accurate_fret.md) |
| 27 | `text` | The rotational-correlation-time decay | 4 | — | [docs/concepts/anisotropy.md](/concepts/anisotropy.md) |
| 28 | `text` | The shot-noise floor: a static molecule's expected scatter | 4 | — | [docs/concepts/bva.md](/concepts/bva.md) |
| 29 | `text` | Relevance: the objective costs what moved | 6 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 30 | `text` | What treewidth means | 4 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 31 | `python` | Reading the structure report | 4 | compiled | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 32 | `text` | Reading the structure report | 13 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 33 | `text` | Reading the structure report | 5 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 34 | `text` | The anatomy of a correlation curve | 4 | — | [docs/concepts/fcs_correlation.md](/concepts/fcs_correlation.md) |
| 35 | `text` | Excitation rate | 4 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 36 | `text` | From the scheme to G(τ) | 1 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 37 | `text` | From the scheme to G(τ) | 1 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 38 | `text` | Reading the radial profile | 1 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 39 | `python` | Determining a scheme: fit the power series, not one curve | 10 | compiled | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 40 | `yaml` | What ChiSurf uses, and how to change it | 4 | — | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 41 | `python` | Per-fit override | 2 | compiled | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 42 | `text` | Which threshold? | 4 | — | [docs/concepts/frc_resolution.md](/concepts/frc_resolution.md) |
| 43 | `text` | Transfer rate and efficiency | 4 | — | [docs/concepts/fret.md](/concepts/fret.md) |
| 44 | `text` | Worked numbers | 6 | — | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 45 | `text` | The universal semicircle | 4 | — | [docs/concepts/imaging_flim_phasor.md](/concepts/imaging_flim_phasor.md) |
| 46 | `text` | Core methods | 11 | — | [docs/concepts/index.md](/concepts/index.md) |
| 47 | `text` | Fitting and inference | 7 | — | [docs/concepts/index.md](/concepts/index.md) |
| 48 | `text` | Correlation methods | 9 | — | [docs/concepts/index.md](/concepts/index.md) |
| 49 | `text` | Single-molecule FRET (bursts) | 12 | — | [docs/concepts/index.md](/concepts/index.md) |
| 50 | `text` | Dynamics (hidden Markov) | 7 | — | [docs/concepts/index.md](/concepts/index.md) |
| 51 | `text` | Imaging and resolution | 11 | — | [docs/concepts/index.md](/concepts/index.md) |
| 52 | `text` | Exploration & selection | 5 | — | [docs/concepts/index.md](/concepts/index.md) |
| 53 | `text` | Data and provenance | 10 | — | [docs/concepts/index.md](/concepts/index.md) |
| 54 | `text` | Structure | 10 | — | [docs/concepts/index.md](/concepts/index.md) |
| 55 | `text` | Simulation | 4 | — | [docs/concepts/index.md](/concepts/index.md) |
| 56 | `text` | Recreational tools | 3 | — | [docs/concepts/index.md](/concepts/index.md) |
| 57 | `text` | Application information | 7 | — | [docs/concepts/index.md](/concepts/index.md) |
| 58 | `text` | Which average applies | 9 | — | [docs/concepts/kappa2_orientation.md](/concepts/kappa2_orientation.md) |
| 59 | `text` | Entropy as the criterion | 10 | — | [docs/concepts/maximum_entropy.md](/concepts/maximum_entropy.md) |
| 60 | `text` | Photons do not sample a burst uniformly in time | 1 | — | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 61 | `text` | Doing it in ChiSurf | 7 | — | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 62 | `text` | Doing it in ChiSurf | 3 | — | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 63 | `python` | Doing it in ChiSurf | 9 | compiled | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 64 | `text` | Three properties nothing else has | 6 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 65 | `text` | STICS: track where the peak sits | 5 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 66 | `text` | What limits the arrows | 5 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 67 | `python` | Finding the minimum before describing it | 3 | compiled | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 68 | `python` | One way to ask | 11 | compiled | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 69 | `text` | Why the histogram carries brightness | 4 | — | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 70 | `python` | What ChiSurf writes, and what it only reads | 4 | compiled | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 71 | `python` | Where did this number come from | 4 | compiled | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 72 | `text` | Where did this number come from | 14 | — | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 73 | `text` | Average lifetimes and fractions | 4 | — | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 74 | `text` | Average lifetimes and fractions | 6 | — | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 75 | `text` | In ChiSurf | 6 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 76 | `python` | In ChiSurf | 10 | compiled | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 77 | `text` | In ChiSurf | 11 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 78 | `python` | In ChiSurf | 4 | compiled | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 79 | `text` | Result | 4 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 80 | `text` | In the GUI: the same-molecule probability | 8 | — | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 81 | `python` | Headless | 10 | compiled | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 82 | `python` | Headless | 3 | compiled | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 83 | `text` | Result | 4 | — | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 84 | `python` | In ChiSurf | 13 | compiled | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 85 | `text` | In ChiSurf | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 86 | `text` | In ChiSurf | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 87 | `text` | Result | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 88 | `text` | The PCH tool (classical PCH, not FIDA) | 6 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 89 | `text` | FIDA in the PCH experiment | 7 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 90 | `python` | Headless | 15 | compiled | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 91 | `text` | Result | 4 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 92 | `text` | In the GUI: the FCS model | 9 | — | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 93 | `python` | Headless | 8 | compiled | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 94 | `text` | Result | 4 | — | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 95 | `python` | In ChiSurf | 9 | compiled | [docs/guides/06_nsfcs_second_order.md](/guides/06_nsfcs_second_order.md) |
| 96 | `text` | Result | 4 | — | [docs/guides/06_nsfcs_second_order.md](/guides/06_nsfcs_second_order.md) |
| 97 | `python` | In ChiSurf | 12 | compiled | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 98 | `text` | In ChiSurf | 4 | — | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 99 | `text` | Result | 4 | — | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 100 | `text` | In ChiSurf | 11 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 101 | `text` | In ChiSurf | 6 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 102 | `python` | Headless | 17 | compiled | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 103 | `text` | Result | 4 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 104 | `text` | In ChiSurf | 10 | — | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 105 | `python` | Headless / scripting | 8 | compiled | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 106 | `text` | Result | 5 | — | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 107 | `text` | 1. Load a file | 7 | — | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 108 | `python` | 5. Excitation regions and multiple lasers | 11 | compiled | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 109 | `bash` | Command line and Python | 2 | — | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 110 | `python` | Command line and Python | 3 | compiled | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 111 | `text` | The photon-data tools and count rates (Tools › Photon data) | 5 | — | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 112 | `text` | Count rates over many files | 5 | — | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 113 | `bash` | Count rates over many files | 2 | — | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 114 | `python` | Count rates over many files | 11 | compiled | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 115 | `bash` | Administering the measurement database: MMFDB Admin | 2 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 116 | `text` | Administering the measurement database: MMFDB Admin | 5 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 117 | `text` | 7. Demo data | 6 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 118 | `python` | Headless and Python | 7 | compiled | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 119 | `text` | Application details for a support request | 4 | — | [docs/guides/103_application_identity.md](/guides/103_application_identity.md) |
| 120 | `python` | Application details for a support request | 5 | compiled | [docs/guides/103_application_identity.md](/guides/103_application_identity.md) |
| 121 | `text` | Light path simulator: crosstalk and R0 of an optical setup | 8 | — | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 122 | `bash` | 5. Headless | 6 | — | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 123 | `python` | 5. Headless | 9 | compiled | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 124 | `bash` | 2. Run it | 1 | — | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 125 | `python` | 3. Python | 13 | compiled | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 126 | `text` | 4. Read the result | 6 | — | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 127 | `text` | 1. HeteroFRET | 5 | — | [docs/guides/107_fret_calculator.md](/guides/107_fret_calculator.md) |
| 128 | `python` | 3. Python | 8 | compiled | [docs/guides/107_fret_calculator.md](/guides/107_fret_calculator.md) |
| 129 | `text` | 1. Open a file | 6 | — | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 130 | `python` | 4. Python | 8 | compiled | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 131 | `python` | 4. Python | 4 | compiled | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 132 | `text` | 0. Make the record | 5 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 133 | `text` | 1. Pick a record and review it | 5 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 134 | `text` | 2. Build and upload | 5 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 135 | `bash` | Terminal | 9 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 136 | `python` | Python | 13 | compiled | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 137 | `text` | In ChiSurf | 9 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 138 | `python` | In ChiSurf | 14 | compiled | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 139 | `text` | Result | 4 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 140 | `text` | VV/VH Anisotropy Decay (deprecated) | 4 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 141 | `text` | Terminal panes: shells and Python side by side | 6 | — | [docs/guides/110_terminal.md](/guides/110_terminal.md) |
| 142 | `text` | 3. Split | 5 | — | [docs/guides/110_terminal.md](/guides/110_terminal.md) |
| 143 | `python` | In ChiSurf | 10 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 144 | `text` | Fitting in the GUI | 8 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 145 | `python` | Reading bursts | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 146 | `python` | Fitting a kinetic scheme | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 147 | `python` | Diagnostics | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 148 | `python` | Measuring an exchange rate: several time bins, one rate | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 149 | `text` | Result | 4 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 150 | `python` | One measurement, one file | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 151 | `text` | Converting on drop | 7 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 152 | `python` | Converting on drop | 4 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 153 | `python` | In ChiSurf | 17 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 154 | `python` | In ChiSurf | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 155 | `text` | Result | 4 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 156 | `text` | Open the tool | 7 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 157 | `text` | Open the tool | 10 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 158 | `text` | Open the tool | 5 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 159 | `python` | Headless | 5 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 160 | `python` | Headless | 6 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 161 | `text` | Result | 4 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 162 | `text` | In the GUI: Accurate FRET | 10 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 163 | `python` | Headless | 8 | compiled | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 164 | `text` | Result | 4 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 165 | `text` | In ChiSurf | 8 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 166 | `text` | In ChiSurf | 6 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 167 | `python` | In ChiSurf | 8 | compiled | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 168 | `text` | Result | 4 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 169 | `python` | In ChiSurf | 23 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 170 | `text` | Burst-wise FCS | 6 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 171 | `text` | Burst-wise FCS | 6 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 172 | `python` | Burst-wise FCS | 12 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 173 | `text` | Result | 4 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 174 | `python` | In ChiSurf | 6 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 175 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 176 | `text` | The Filter Calculator | 6 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 177 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 178 | `python` | 2D-FLCS on many molecules, with error bars | 10 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 179 | `bash` | 2D-FLCS on many molecules, with error bars | 2 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 180 | `python` | 2D-FLCS on many molecules, with error bars | 4 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 181 | `text` | Instrument parameters | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 182 | `text` | Result | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 183 | `python` | In ChiSurf | 9 | compiled | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 184 | `text` | The lifetime-FCS simulator | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 185 | `text` | Setting up species and kinetics in the GUI | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 186 | `text` | Result | 4 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 187 | `python` | In ChiSurf | 8 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 188 | `bash` | In ChiSurf | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 189 | `text` | The H2MM tool | 11 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 190 | `python` | Choosing a decoder | 4 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 191 | `bash` | Writing the states back into the photons | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 192 | `text` | Per-state decays | 8 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 193 | `text` | Result | 4 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 194 | `text` | The ebFRET window | 8 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 195 | `python` | Headless | 10 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 196 | `python` | Headless | 4 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 197 | `text` | Result | 6 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 198 | `text` | Extracting patterns from non-burst photons | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 199 | `python` | Extracting patterns from non-burst photons | 16 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 200 | `python` | In ChiSurf | 14 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 201 | `python` | Measured IRF and background, Opt, Save fit | 11 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 202 | `text` | Measured IRF and background, Opt, Save fit | 8 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 203 | `text` | Measured IRF and background, Opt, Save fit | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 204 | `text` | Measured IRF and background, Opt, Save fit | 7 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 205 | `text` | Result | 9 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 206 | `text` | The lifetime of a state, not of a burst | 5 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 207 | `python` | In ChiSurf | 12 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 208 | `text` | Trace Browser | 9 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 209 | `text` | Trace Browser | 6 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 210 | `python` | Trace Browser | 3 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 211 | `text` | Result | 4 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 212 | `python` | In ChiSurf | 13 | compiled | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 213 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 8 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 214 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 215 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 5 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 216 | `text` | Result | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 217 | `python` | In ChiSurf | 8 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 218 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 219 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 220 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 221 | `python` | Selecting pixels | 5 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 222 | `text` | Result | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 223 | `text` | The Intensity tool | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 224 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 225 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 226 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 227 | `python` | In ChiSurf | 10 | compiled | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 228 | `text` | In the Accurate FRET tool | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 229 | `text` | In the Accurate FRET tool | 7 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 230 | `text` | Result | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 231 | `text` | In ChiSurf | 8 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 232 | `python` | In ChiSurf | 9 | compiled | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 233 | `text` | Result | 7 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 234 | `text` | In ChiSurf | 7 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 235 | `text` | In ChiSurf | 8 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 236 | `python` | In ChiSurf | 9 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 237 | `text` | In ChiSurf | 12 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 238 | `python` | In ChiSurf | 17 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 239 | `text` | Result | 4 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 240 | `text` | In ChiSurf | 10 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 241 | `text` | In ChiSurf | 5 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 242 | `python` | In ChiSurf | 14 | compiled | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 243 | `text` | Result | 4 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 244 | `text` | In ChiSurf | 8 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 245 | `python` | In ChiSurf | 14 | compiled | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 246 | `text` | Result | 4 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 247 | `python` | The steps | 20 | compiled | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 248 | `text` | Exploring the dwells | 10 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 249 | `text` | Exploring the dwells | 4 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 250 | `python` | In ChiSurf | 8 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 251 | `python` | In ChiSurf | 17 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 252 | `text` | In ChiSurf | 10 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 253 | `text` | Result | 4 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 254 | `python` | In ChiSurf | 23 | compiled | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 255 | `text` | In ChiSurf | 9 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 256 | `text` | Result | 5 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 257 | `python` | In ChiSurf | 17 | compiled | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 258 | `text` | In ChiSurf | 11 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 259 | `text` | Result | 7 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 260 | `python` | In ChiSurf | 20 | compiled | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 261 | `text` | Result | 14 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 262 | `text` | In ChiSurf | 9 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 263 | `python` | In ChiSurf | 13 | compiled | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 264 | `text` | Result | 4 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 265 | `python` | In ChiSurf | 10 | compiled | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 266 | `text` | Result | 4 | — | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 267 | `text` | Compute a LUT per channel and add it to the setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 268 | `text` | It lands in the detector setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 269 | `bash` | Headless (CLI / API) | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 270 | `python` | Headless (CLI / API) | 6 | compiled | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 271 | `text` | 2. Concepts | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 272 | `text` | 5. Read the results | 5 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 273 | `text` | 9. Punctate signal? Count objects instead | 5 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 274 | `text` | 9. Punctate signal? Count objects instead | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 275 | `text` | 10. Gate a population in the scatter | 6 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 276 | `bash` | Headless / CLI | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 277 | `python` | Python API | 12 | compiled | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 278 | `python` | 1. Fit something | 20 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 279 | `python` | 2. Attach a prior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 280 | `python` | 3. Sample the posterior | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 281 | `python` | 3. Sample the posterior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 282 | `python` | 4. Read the diagnostics before the answer | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 283 | `text` | 4. Read the diagnostics before the answer | 3 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 284 | `python` | 4. Read the diagnostics before the answer | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 285 | `python` | 6. Global fits | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 286 | `python` | 6. Global fits | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 287 | `python` | 7. Linked global fits: use `collapsed` | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 288 | `python` | 8. Inspecting the structure of a global fit | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 289 | `text` | 8. Inspecting the structure of a global fit | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 290 | `text` | The Dependence tab, and why it is not the correlation tab | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 291 | `text` | The Dependence tab, and why it is not the correlation tab | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 292 | `python` | The Dependence tab, and why it is not the correlation tab | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 293 | `python` | 9. Reusing a chain under a different prior | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 294 | `text` | 10. Opening the chains in nDXplorer | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 295 | `python` | 10. Opening the chains in nDXplorer | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 296 | `python` | 11. Looking at the posterior instead of reading about it | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 297 | `text` | 11. Looking at the posterior instead of reading about it | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 298 | `python` | 11. Looking at the posterior instead of reading about it | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 299 | `text` | 12. In the GUI | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 300 | `python` | 12. In the GUI | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 301 | `python` | 13. Asking directly, without picking an estimator first | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 302 | `python` | 14. From a script, a macro or the server | 14 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 303 | `text` | 15. Error bars on the quantities you publish | 7 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 304 | `python` | 15. Error bars on the quantities you publish | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 305 | `python` | 15. Error bars on the quantities you publish | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 306 | `text` | Using it in the GUI | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 307 | `bash` | Using it from a terminal | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 308 | `yaml` | Skills: how it knows *how* | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 309 | `markdown` | Writing your own | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 310 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 311 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 312 | `text` | 3. Pick the dyes (and the setup) | 5 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 313 | `python` | 3. Pick the dyes (and the setup) | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 314 | `text` | 6. Calibrate | 15 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 315 | `text` | 7. Read the plots | 7 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 316 | `text` | 7. Read the plots | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 317 | `python` | Keeping a calibration | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 318 | `bash` | Trying it without data (and checking it works) | 1 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 319 | `python` | Trying it without data (and checking it works) | 10 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 320 | `bash` | Head-less | 9 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 321 | `python` | From Python | 21 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 322 | `python` | In the Global View | 7 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 323 | `python` | In the Global View | 6 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 324 | `python` | A worked run against known truth | 25 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 325 | `text` | Fitting a kinetic scheme | 6 | — | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 326 | `python` | Fitting a kinetic scheme | 11 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 327 | `python` | Uncertainties | 5 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 328 | `text` | Measure | 7 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 329 | `text` | Read the result | 5 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 330 | `text` | Read the result | 6 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 331 | `bash` | Headless | 2 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 332 | `text` | Headless | 7 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 333 | `python` | Python | 8 | compiled | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 334 | `text` | Loading and looking | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 335 | `text` | Loading and looking | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 336 | `text` | Integrative (bead) models | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 337 | `text` | Integrative (bead) models | 8 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 338 | `text` | Integrative (bead) models | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 339 | `text` | RMF models from IMP | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 340 | `text` | Whether the camera follows the frame | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 341 | `text` | Whether the camera follows the frame | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 342 | `text` | Choosing a resolution | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 343 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 344 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 345 | `text` | Simulating a map, and fitting a model into one | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 346 | `text` | Simulating a map, and fitting a model into one | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 347 | `text` | The Map panel | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 348 | `text` | Playing a trajectory | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 349 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 350 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 351 | `text` | Crystal symmetry | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 352 | `text` | Trying it out: the Demo menu | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 353 | `text` | Making it look good | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 354 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 355 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 356 | `text` | Seeing through a surface | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 357 | `text` | How finely the surface is built | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 358 | `text` | A picture behind the scene, so transparency reads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 359 | `text` | A picture behind the scene, so transparency reads | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 360 | `text` | Clipping, and how to get out of it | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 361 | `text` | Every setting, in the view it changes | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 362 | `text` | How big the chrome draws | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 363 | `text` | Tuning a metaball | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 364 | `text` | Tidying and shielding | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 365 | `text` | Adding hydrogens | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 366 | `text` | Saving a session | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 367 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 368 | `text` | Organising the panel | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 369 | `text` | Organising the panel | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 370 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 371 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 372 | `text` | Organising the panel | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 373 | `text` | Selecting | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 374 | `text` | How far a click spreads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 375 | `text` | Drawing | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 376 | `text` | Drawing | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 377 | `text` | Measuring | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 378 | `text` | Measuring | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 379 | `text` | Measuring by clicking | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 380 | `text` | Polar contacts | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 381 | `text` | Polar contacts | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 382 | `text` | Hydrogen-bond networks | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 383 | `text` | Where two chains touch | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 384 | `text` | Salt bridges, halogen bonds and pi interactions | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 385 | `text` | Clashes | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 386 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 387 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 388 | `text` | The mutagenesis wizard | 15 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 389 | `text` | The mutagenesis wizard | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 390 | `text` | Bonds | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 391 | `text` | Superposing structures | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 392 | `text` | Superposing structures | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 393 | `text` | Superposing structures | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 394 | `text` | Presets — one command to a figure | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 395 | `text` | Side chains that grow out of the ribbon | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 396 | `text` | Colouring by a computed quantity | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 397 | `text` | Colouring by a computed quantity | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 398 | `text` | Showing a quantity as thickness | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 399 | `text` | Showing a quantity as thickness | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 400 | `text` | Getting data in and out | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 401 | `text` | Getting data in and out | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 402 | `text` | Getting data in and out | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 403 | `text` | Exporting the scene as a 3-D model | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 404 | `text` | Images | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 405 | `python` | Headless and scripted use | 17 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 406 | `python` | Headless and scripted use | 22 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 407 | `text` | Open the tool | 8 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 408 | `bash` | Headless | 4 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 409 | `bash` | Launching | 5 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 410 | `python` | ndX in ChiSurf | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 411 | `python` | Lines pushed from another tool | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 412 | `text` | Lines pushed from another tool | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 413 | `text` | Phasor plots are overlays | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 414 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 415 | `text` | Referencing the phasor to the instrument and removing background | 2 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 416 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 417 | `python` | Fitting a constant: moving the data onto the curve | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 418 | `python` | Fitting a constant: moving the data onto the curve | 14 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 419 | `python` | Curves that trace a line rather than evaluate one | 10 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 420 | `python` | Worked example: two smFRET populations and the static FRET line | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 421 | `python` | Worked example: two smFRET populations and the static FRET line | 4 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 422 | `text` | Worked example: two smFRET populations and the static FRET line | 10 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 423 | `text` | Fit 2-D Gaussians to the populations on the map | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 424 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 425 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 426 | `text` | Find the informative projections | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 427 | `python` | Find the informative projections | 9 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 428 | `text` | Session state in the measurement | 3 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 429 | `text` | The workflow | 8 | — | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 430 | `python` | The workflow | 31 | compiled | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 431 | `text` | The region editor | 7 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 432 | `text` | The region editor | 8 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 433 | `text` | The single-molecule imaging workflow | 9 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 434 | `python` | The single-molecule imaging workflow | 2 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 435 | `bash` | Headless | 2 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 436 | `text` | Headless | 4 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 437 | `python` | Python | 28 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 438 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 439 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 440 | `text` | Region MLE: the demo's fit assumptions | 5 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 441 | `text` | Open the tool | 10 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 442 | `text` | Open the tool | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 443 | `text` | The transition-time scan | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 444 | `bash` | Headless | 4 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 445 | `bash` | Headless | 2 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 446 | `text` | Open the tool | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 447 | `text` | 2. Link | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 448 | `bash` | Headless | 4 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 449 | `bash` | Headless | 2 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 450 | `text` | Open the tool | 7 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 451 | `bash` | Headless | 3 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 452 | `text` | Doing it | 7 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 453 | `json` | Advertising another analysis | 13 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 454 | `python` | Headless | 10 | compiled | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 455 | `text` | What counts as a change | 1 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 456 | `text` | What counts as a change | 9 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 457 | `json` | The stamp files | 16 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 458 | `python` | Forcing a recomputation | 3 | compiled | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 459 | `text` | Open the tool | 10 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 460 | `text` | Load a trace | 4 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 461 | `text` | Choose the number of states | 5 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 462 | `text` | Read the result | 7 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 463 | `bash` | Headless | 2 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 464 | `python` | Headless | 26 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 465 | `python` | Headless | 2 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 466 | `text` | The tool | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 467 | `bash` | The tool | 2 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 468 | `python` | The tool | 3 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 469 | `python` | The cheap reading: a pCF curve from a carpet you already have | 12 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 470 | `python` | The real thing: position-resolved pCF | 14 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 471 | `text` | The real thing: position-resolved pCF | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 472 | `python` | A line scan | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 473 | `python` | The arrows: a velocity field | 7 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 474 | `text` | The arrows: a velocity field | 6 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 475 | `python` | The arrows: a velocity field | 6 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 476 | `python` | The second route, for a cross-check | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 477 | `bash` | Regenerating the figures | 1 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 478 | `text` | 4. Read the four outputs | 9 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 479 | `json` | 5. Build your own scheme | 10 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 480 | `bash` | 6. Headless | 8 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 481 | `python` | 7. From the Python API | 12 | compiled | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 482 | `text` | 1. Load the folder | 4 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 483 | `text` | 2. Fit the static model first | 9 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 484 | `text` | 2. Fit the static model first | 7 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 485 | `python` | 5. Headless | 13 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 486 | `python` | 5. Headless | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 487 | `python` | 6. Try it on data whose answer you know | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 488 | `text` | 1. Open the step | 6 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 489 | `text` | 2. Look at the curve before choosing a threshold | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 490 | `text` | 5. Write the fused folder | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 491 | `text` | 5. Write the fused folder | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 492 | `text` | 5. Write the fused folder | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 493 | `bash` | Headless | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 494 | `python` | Headless | 8 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 495 | `python` | Headless | 6 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 496 | `text` | Driving ChiSurf from its console | 5 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 497 | `python` | The first thing to know | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 498 | `text` | The first thing to know | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 499 | `python` | Reading a fit | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 500 | `python` | Reading a fit | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 501 | `text` | Reading a fit | 5 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 502 | `text` | Turning what you did into a script | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 503 | `text` | Long commands and Ctrl+C | 3 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 504 | `python` | Plotting | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 505 | `text` | Plotting | 6 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 506 | `text` | 2. Open the parameter network | 10 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 507 | `text` | 3. Link the shared parameter | 4 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 508 | `text` | 4. Check that the link took effect | 7 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 509 | `python` | Headless: linking two fits | 25 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 510 | `text` | Headless: linking two fits | 2 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 511 | `python` | Headless: linking two fits | 2 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 512 | `python` | Headless: the joint fit | 9 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 513 | `text` | Headless: the joint fit | 1 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 514 | `text` | Step 2 — use your own dyes | 9 | — | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 515 | `python` | Headless | 8 | compiled | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 516 | `text` | Maximum-entropy decay analysis | 4 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 517 | `text` | Maximum-entropy decay analysis | 5 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 518 | `text` | Step 2 — run once, and distrust the answer | 16 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 519 | `python` | Headless | 10 | compiled | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 520 | `text` | How it got there | 11 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 521 | `text` | The settings are the recipe | 13 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 522 | `json` | Opening the tool that made a result | 5 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 523 | `python` | Verifying | 4 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 524 | `bash` | Headless | 7 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 525 | `python` | Headless | 11 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 526 | `python` | Plots | 7 | compiled | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 527 | `text` | The kernel terminal | 4 | — | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 528 | `text` | The Acquisition fit window | 7 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 529 | `python` | The Acquisition fit window | 4 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 530 | `python` | Without a GUI | 25 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 531 | `python` | Without a GUI | 10 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 532 | `text` | The simple workflow | 6 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 533 | `text` | 3 — Alternation, measured rather than typed | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 534 | `text` | Titration | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 535 | `bash` | Headless | 4 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 536 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 537 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 538 | `bash` | Headless | 1 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 539 | `python` | Headless | 9 | compiled | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 540 | `text` | Asking | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 541 | `bash` | From the command line | 1 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 542 | `text` | From the command line | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 543 | `python` | From Python | 6 | compiled | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 544 | `text` | Open the tool | 8 | — | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 545 | `python` | Headless | 12 | compiled | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 546 | `text` | Generate a decay | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 547 | `text` | Correlate | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 548 | `python` | Headless | 28 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 549 | `python` | Headless | 12 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 550 | `text` | Open the tool | 9 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 551 | `text` | Open a tool | 6 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 552 | `text` | The tools | 4 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 553 | `python` | Headless | 27 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 554 | `python` | Headless | 7 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 555 | `bash` | Headless | 1 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 556 | `bash` | Open the tool | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 557 | `text` | 1. Channel Definitions | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 558 | `text` | 2. Files & Steps | 4 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 559 | `text` | Time regions | 4 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 560 | `text` | 3. Photon / Burst Filter | 8 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 561 | `text` | 4. Correlator | 8 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 562 | `text` | 5. FCS Merger | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 563 | `bash` | The settings file beside every `.cor` | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 564 | `python` | The settings file beside every `.cor` | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 565 | `text` | The settings file beside every `.cor` | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 566 | `bash` | Converting correlation files | 2 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 567 | `python` | Headless | 29 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 568 | `python` | Headless | 6 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 569 | `python` | Headless | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 570 | `text` | Open the tools | 4 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 571 | `text` | Settings | 8 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 572 | `text` | Settings | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 573 | `text` | Reading the output | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 574 | `text` | VV/VH: lifetimes and rotations together | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 575 | `text` | VV/VH: lifetimes and rotations together | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 576 | `bash` | VV/VH: lifetimes and rotations together | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 577 | `python` | VV/VH: lifetimes and rotations together | 5 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 578 | `text` | Synthetic Decay Generator | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 579 | `text` | Synthetic Decay Generator | 7 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 580 | `text` | Synthetic Decay Generator | 5 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 581 | `bash` | Headless | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 582 | `python` | Headless | 22 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 583 | `text` | Open the tool | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 584 | `text` | Set it up | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 585 | `python` | Headless | 13 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 586 | `python` | Headless | 19 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 587 | `text` | Open the tool | 8 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 588 | `text` | 2. Loaded data (optional) | 5 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 589 | `text` | 4. Run | 7 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 590 | `python` | Headless | 23 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 591 | `bash` | Headless | 3 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 592 | `python` | Headless | 27 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 593 | `text` | HydroPro: diffusion coefficients from a structure | 5 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 594 | `text` | Open the tool | 7 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 595 | `text` | Run and read the result | 6 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 596 | `python` | Headless | 10 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 597 | `text` | Headless | 18 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 598 | `python` | Headless | 3 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 599 | `text` | Open the tool | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 600 | `bash` | Headless | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 601 | `python` | Headless | 7 | compiled | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 602 | `text` | Align | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 603 | `text` | Convert | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 604 | `text` | Remove Clashed | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 605 | `text` | Energy Calc | 6 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 606 | `text` | FRET | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 607 | `bash` | FRET | 2 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 608 | `python` | Headless | 33 | compiled | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 609 | `text` | Open the tool | 8 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 610 | `text` | Start with your dye pair | 5 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 611 | `python` | Start with your dye pair | 11 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 612 | `text` | Read the result | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 613 | `text` | Where the lines go next | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 614 | `bash` | Headless | 3 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 615 | `json` | Headless | 9 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 616 | `python` | Headless | 16 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 617 | `text` | 1. Open the Spectra Downloader | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 618 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 619 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 620 | `bash` | 3. Push to the MMFDB | 2 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 621 | `text` | 4. Compute R₀ | 7 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 622 | `python` | 4. Compute R₀ | 8 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 623 | `python` | 6. Headless | 28 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 624 | `bash` | 6. Headless | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 625 | `text` | Native window and stacked Browse content | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 626 | `text` | 1. Open the tool | 9 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 627 | `text` | 3. A real image | 5 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 628 | `text` | 3. A real image | 6 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 629 | `bash` | 6. Headless | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 630 | `python` | 6. Headless | 10 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 631 | `python` | 6. Headless | 5 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 632 | `text` | Window and bright pixels | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 633 | `text` | 1. Where it is | 6 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 634 | `bash` | 4. Headless | 5 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 635 | `python` | 4. Headless | 17 | compiled | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 636 | `text` | See also | 7 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 637 | `text` | 1. Open the tool | 8 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 638 | `text` | 2. The detector setup | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 639 | `text` | 4. Look at the image | 5 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 640 | `bash` | 7. From the command line and Python | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 641 | `python` | 7. From the command line and Python | 9 | compiled | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 642 | `text` | 1. The page | 7 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 643 | `text` | 2. Typing into a table | 4 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 644 | `python` | 4. From Python | 6 | compiled | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 645 | `text` | 5. Edit the complete working definition | 5 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 646 | `text` | 6. Independent reference calibration | 8 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 647 | `text` | 6. Independent reference calibration | 6 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 648 | `text` | 1. Docking and screening | 4 | — | [docs/guides/88_fret_docking.md](/guides/88_fret_docking.md) |
| 649 | `text` | 1. Open the tool | 9 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 650 | `bash` | Headless | 2 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 651 | `python` | Headless | 5 | compiled | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 652 | `bash` | 1. Open the tool | 1 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 653 | `text` | 1. Open the tool | 9 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 654 | `text` | 3. Detector, channels and gates | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 655 | `python` | Headless | 11 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 656 | `python` | Headless | 13 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 657 | `text` | Timing when comparing earlier results | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 658 | `text` | 1. Open the tool | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 659 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 660 | `text` | 5. Package Manager | 4 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 661 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 662 | `python` | Headless / Python | 2 | compiled | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 663 | `bash` | 1. Open the tool and load the fast reference | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 664 | `text` | 1. Open the tool and load the fast reference | 7 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 665 | `text` | 5. Batch, export, archive | 6 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 666 | `python` | Headless and Python | 9 | compiled | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 667 | `bash` | Headless and Python | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 668 | `text` | 1. Open the tool and load a trace | 8 | — | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 669 | `python` | 4. Save and reuse | 7 | compiled | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 670 | `text` | 1. Open the tool and load a stack | 5 | — | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 671 | `python` | Headless and Python | 4 | compiled | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 672 | `text` | Audifier: photon streams as sound and as a waterfall | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 673 | `text` | Layout and saved preferences | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 674 | `text` | 1. The window | 4 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 675 | `text` | 1. The window | 4 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 676 | `text` | Help, Restart and Guide | 7 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 677 | `python` | 4. Native Python entrypoint | 8 | compiled | [docs/guides/95_games.md](/guides/95_games.md) |
| 678 | `text` | 1. Open the tool | 6 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 679 | `text` | 4. Read a failure | 5 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 680 | `bash` | From the command line and from Python | 1 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 681 | `python` | From the command line and from Python | 8 | compiled | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 682 | `text` | 1. The window | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 683 | `text` | 2. The destinations | 4 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 684 | `text` | 2. The destinations | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 685 | `text` | CLSM Generator: a scan whose answer is known | 4 | — | [docs/guides/98_clsm_generator.md](/guides/98_clsm_generator.md) |
| 686 | `text` | The imaging pipeline in one window (Image Tools) | 6 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 687 | `text` | 1. Open the window | 7 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 688 | `text` | 1. Choose the photons and the detector | 6 | — | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 689 | `python` | The correction | 6 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 690 | `text` | Where the factors come from | 10 | — | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 691 | `python` | 1. Light-path prior → data-optimized posterior | 10 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 692 | `python` | 2. Reference samples (donor-only, acceptor-only) | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 693 | `python` | 3. The donor lifetime and the static FRET line | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 694 | `python` | All three at once | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 695 | `python` | The general case: crosstalk matrices | 13 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 696 | `python` | Naive vs. stable un-mixing | 2 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 697 | `python` | Preserving photon-counting statistics (integer "photon shuffling") | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 698 | `python` | ndxplorer: stable / shuffle un-mixing | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 699 | `python` | Per-pixel / FLIM imaging | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 700 | `python` | Scalar multi-chromophore path | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 701 | `python` | Global analysis and ndxplorer | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 702 | `python` | Global analysis and ndxplorer | 3 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 703 | `text` | Inputs and outputs | 13 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 704 | `text` | GUI | 6 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 705 | `bash` | CLI | 5 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 706 | `python` | Python API | 7 | compiled | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 707 | `text` | Projects and session lifecycle | 3 | — | [docs/guides/index.md](/guides/index.md) |
| 708 | `text` | Photon data and the burst pipeline | 23 | — | [docs/guides/index.md](/guides/index.md) |
| 709 | `text` | smFRET: efficiency, stoichiometry and corrections | 17 | — | [docs/guides/index.md](/guides/index.md) |
| 710 | `text` | Dynamics: distributions, kinetics and hidden states | 17 | — | [docs/guides/index.md](/guides/index.md) |
| 711 | `text` | Fluorescence decays and anisotropy | 7 | — | [docs/guides/index.md](/guides/index.md) |
| 712 | `text` | Correlation spectroscopy | 10 | — | [docs/guides/index.md](/guides/index.md) |
| 713 | `text` | Imaging and microscopy | 27 | — | [docs/guides/index.md](/guides/index.md) |
| 714 | `text` | Structure and modelling | 9 | — | [docs/guides/index.md](/guides/index.md) |
| 715 | `text` | Exploration, simulation and automation | 16 | — | [docs/guides/index.md](/guides/index.md) |
| 716 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 717 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 718 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 719 | `text` | Application information | 4 | — | [docs/guides/index.md](/guides/index.md) |
| 720 | `text` | Algorithm Pipeline | 12 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 721 | `text` | In the window | 6 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 722 | `python` | Basic Usage | 11 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 723 | `python` | Step-by-Step Usage | 24 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 724 | `python` | Multi-Channel Data | 7 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 725 | `python` | Visualization | 9 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 726 | `python` | Constructor | 1 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 727 | `text` | Richardson-Lucy Algorithm | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 728 | `bash` | Testing | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 729 | `text` | Saving and reopening projects | 6 | — | [docs/guides/saving_projects.md](/guides/saving_projects.md) |
| 730 | `text` | Adding the membrane-diffusion models | 10 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 731 | `text` | Adding the membrane-diffusion models | 4 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 732 | `text` | Analysis dock | 1 | — | [docs/manual/analysis_dock.md](/manual/analysis_dock.md) |
| 733 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 734 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 735 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 736 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 737 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 738 | `text` | Calculation of co-diffusing molecules | 1 | — | [docs/manual/calculation_of_codiffusing_molecules.md](/manual/calculation_of_codiffusing_molecules.md) |
| 739 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 740 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 741 | `text` | Calculation of the overlap volume and co-diffusion amplitude | 1 | — | [docs/manual/calculations_2.md](/manual/calculations_2.md) |
| 742 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 743 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 744 | `text` | Correction factors for spectral crosstalk & direct acceptor excitation | 1 | — | [docs/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md](/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md) |
| 745 | `text` | Correlation merging | 1 | — | [docs/manual/correlation_merging.md](/manual/correlation_merging.md) |
| 746 | `text` | Correlator | 1 | — | [docs/manual/correlator.md](/manual/correlator.md) |
| 747 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 748 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 749 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 750 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 751 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 752 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 753 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 754 | `text` | Data import | 2 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 755 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 756 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 757 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 758 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 759 | `text` | Data import | 3 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 760 | `text` | Data input and file format | 12 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 761 | `text` | Data input and file format | 5 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 762 | `shell` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 763 | `text` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 764 | `text` | Determination of g-factor and depolarization factors using ChiSurf | 1 | — | [docs/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md](/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md) |
| 765 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 766 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 767 | `text` | Discrete FRET rate constants | 2 | — | [docs/manual/discrete_fret_rate_constants.md](/manual/discrete_fret_rate_constants.md) |
| 768 | `text` | Equation parsing | 1 | — | [docs/manual/equation_parsing.md](/manual/equation_parsing.md) |
| 769 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 770 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 771 | `text` | F-Calculator | 1 | — | [docs/manual/fcalculator.md](/manual/fcalculator.md) |
| 772 | `text` | Fit interface | 1 | — | [docs/manual/fit_interface.md](/manual/fit_interface.md) |
| 773 | `text` | Fit models | 3 | — | [docs/manual/fit_models.md](/manual/fit_models.md) |
| 774 | `text` | Fit of the green-excitation FCS curve | 4 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 775 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 776 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 777 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 778 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 779 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 780 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 781 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 782 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 783 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 784 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 785 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 786 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 787 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 788 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 789 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 790 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 791 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 792 | `text` | Fit of auto- and cross-correlation curves | 1 | — | [docs/manual/fit_of_auto_and_crosscorrelation_curves.md](/manual/fit_of_auto_and_crosscorrelation_curves.md) |
| 793 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 794 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 795 | `text` | Fit of the red-excitation FCS curve | 1 | — | [docs/manual/fit_of_fcs_curve.md](/manual/fit_of_fcs_curve.md) |
| 796 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 797 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 798 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 799 | `text` | Fluorescence Lifetime | 5 | — | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 800 | `text` | Static FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 801 | `text` | Dynamic FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 802 | `text` | Visualizing FRET Lines | 14 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 803 | `text` | Visualizing FRET Lines | 21 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 804 | `text` | Example: Complete Analysis Workflow | 71 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 805 | `text` | Troubleshooting | 3 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 806 | `text` | Example Script | 2 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 807 | `text` | Global fit of auto- and cross-correlation curves | 1 | — | [docs/manual/global_fit_of_auto_and_crosscorrelation_curves.md](/manual/global_fit_of_auto_and_crosscorrelation_curves.md) |
| 808 | `text` | Global fit of FCS curves | 1 | — | [docs/manual/global_fit_of_fcs_curves.md](/manual/global_fit_of_fcs_curves.md) |
| 809 | `text` | Fitting interface & worked examples | 20 | — | [docs/manual/index.md](/manual/index.md) |
| 810 | `text` | Fitting interface & worked examples | 10 | — | [docs/manual/index.md](/manual/index.md) |
| 811 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 812 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 813 | `text` | Fitting interface & worked examples | 7 | — | [docs/manual/index.md](/manual/index.md) |
| 814 | `text` | Fitting interface & worked examples | 23 | — | [docs/manual/index.md](/manual/index.md) |
| 815 | `text` | Fitting interface & worked examples | 9 | — | [docs/manual/index.md](/manual/index.md) |
| 816 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 817 | `text` | Fitting interface & worked examples | 15 | — | [docs/manual/index.md](/manual/index.md) |
| 818 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 819 | `text` | Influence of FRET efficiency | 1 | — | [docs/manual/influence_of_fret_efficiency.md](/manual/influence_of_fret_efficiency.md) |
| 820 | `text` | Influence of triplet blinking | 1 | — | [docs/manual/influence_of_triplet_blinking.md](/manual/influence_of_triplet_blinking.md) |
| 821 | `text` | Introduction | 6 | — | [docs/manual/introduction.md](/manual/introduction.md) |
| 822 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 823 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 824 | `text` | Loading & plotting data | 1 | — | [docs/manual/loading__plotting_data.md](/manual/loading__plotting_data.md) |
| 825 | `text` | Loading and setting up the eGFP data set | 1 | — | [docs/manual/loading_and_setting_up_the_egfp_data_set.md](/manual/loading_and_setting_up_the_egfp_data_set.md) |
| 826 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 827 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 828 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 829 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 830 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 831 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 832 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 833 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 834 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 835 | `text` | Model scores | 2 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 836 | `text` | Model scores | 3 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 837 | `text` | Model scores | 1 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 838 | `text` | Model scoring range | 1 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 839 | `text` | Model scoring range | 2 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 840 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 841 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 842 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 843 | `text` | Arranging the windows | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 844 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 845 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 846 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 847 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 848 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 849 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 850 | `text` | Correlator: overview | 1 | — | [docs/manual/overview_2.md](/manual/overview_2.md) |
| 851 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 852 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 853 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 854 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 855 | `text` | Parameter optimization | 1 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 856 | `text` | Settings | 25 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 857 | `text` | Parameter sampling | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 858 | `text` | Parameter sampling | 1 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 859 | `text` | From the shell | 2 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 860 | `text` | From the shell | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 861 | `text` | Parameter scan | 1 | — | [docs/manual/parameter_scan.md](/manual/parameter_scan.md) |
| 862 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 863 | `text` | Parameters | 8 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 864 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 865 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 866 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 867 | `text` | Parameters | 3 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 868 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 869 | `text` | Partial donor-donor energy migration | 3 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 870 | `text` | Parameters | 5 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 871 | `text` | Reference curves | 1 | — | [docs/manual/reference_curves.md](/manual/reference_curves.md) |
| 872 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 873 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 874 | `text` | Saving & exporting the results | 8 | — | [docs/manual/saving__exporting_the_results.md](/manual/saving__exporting_the_results.md) |
| 875 | `xml` | Saving and loading networks | 14 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 876 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 877 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 878 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 879 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 880 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 881 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 882 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 883 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 884 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 885 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 886 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 887 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 888 | `text` | Step 1: Approximating g-factor with small fluorophore | 1 | — | [docs/manual/step_1_approximating_gfactor_with_small_fluorophore.md](/manual/step_1_approximating_gfactor_with_small_fluorophore.md) |
| 889 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 890 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 891 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 892 | `text` | Two single files | 1 | — | [docs/manual/two_single_files.md](/manual/two_single_files.md) |
| 893 | `text` | VV/VH format | 1 | — | [docs/manual/vv_vh_format.md](/manual/vv_vh_format.md) |
| 894 | `text` | Worm-like chain | 4 | — | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 895 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 896 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 897 | `text` | Usage | 7 | — | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 898 | `python` | Correlation section | 5 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 899 | `python` | Correlation section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 900 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 901 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 902 | `text` | Intensity trace section | 6 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 903 | `python` | Correlation arrays | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 904 | `python` | Intensity arrays | 9 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 905 | `text` | ALV-7004/USB `.asc` (openASC_ALV_7004) | 7 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 906 | `text` | File formats | 4 | — | [docs/reference/file_formats/index.md](/reference/file_formats/index.md) |
| 907 | `python` | Single-file structure reader | 6 | compiled | [docs/reference/file_formats/structure_files.md](/reference/file_formats/structure_files.md) |
| 908 | `python` | Workflow | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 909 | `python` | Becker-SDT | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 910 | `python` | Preview and Add | 7 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 911 | `text` | Reference | 12 | — | [docs/reference/index.md](/reference/index.md) |
| 912 | `bash` | Local (primitive) | 10 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 913 | `bash` | MMFDB round trip | 13 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 914 | `bash` | Local (primitive) | 4 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 915 | `bash` | Local (primitive) | 3 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 916 | `bash` | MMFDB round trip | 7 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 917 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 918 | `python` | From a script | 9 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 919 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 920 | `python` | Saving a single parameter | 7 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 921 | `text` | Plugin catalogue | 4 | — | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 922 | `yaml` | 3. `settings_colors.yaml` (global color palette) | 3 | — | [docs/reference/settings.md](/reference/settings.md) |
| 923 | `python` | User-Defined Models in ChiSurf | 2 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 924 | `python` | 1.1 Write the model | 21 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 925 | `yaml` | 1.3 List it in `experiment_configs.yaml` | 3 | — | [docs/reference/user_models.md](/reference/user_models.md) |
| 926 | `python` | 3. Turning a plain function into a model | 7 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
