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

*909 blocks, 231 Python, 0 executed.*

| # | Language | Section | Lines | Verified | Page |
| --- | --- | --- | --- | --- | --- |
| 1 | `text` | Installation and environment | 3 | — | [docs/getting_started/index.md](/getting_started/index.md) |
| 2 | `text` | Installation and environment | 4 | — | [docs/getting_started/index.md](/getting_started/index.md) |
| 3 | `text` | Colours tell the kind of task | 5 | — | [docs/getting_started/index.md](/getting_started/index.md) |
| 4 | `text` | Fonts | 4 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 5 | `text` | Fonts | 4 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 6 | `yaml` | Without the window | 6 | — | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 7 | `python` | Without the window | 3 | compiled | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 8 | `text` | What happens before emission | 7 | — | [docs/fundamentals/absorption_and_emission.md](/fundamentals/absorption_and_emission.md) |
| 9 | `text` | Mechanism | 8 | — | [docs/fundamentals/energy_transfer.md](/fundamentals/energy_transfer.md) |
| 10 | `text` | The excited state | 6 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 11 | `text` | Orientation and transfer | 4 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 12 | `text` | Probe and environment | 4 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 13 | `text` | Measuring photons | 5 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 14 | `text` | Reference | 3 | — | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 15 | `text` | Multi-exponential decays | 7 | — | [docs/fundamentals/lifetime_and_quantum_yield.md](/fundamentals/lifetime_and_quantum_yield.md) |
| 16 | `text` | Rotational diffusion | 7 | — | [docs/fundamentals/polarization_and_rotation.md](/fundamentals/polarization_and_rotation.md) |
| 17 | `text` | Collisional quenching and Stern–Volmer | 8 | — | [docs/fundamentals/quenching_and_photophysics.md](/fundamentals/quenching_and_photophysics.md) |
| 18 | `text` | Upward curvature: the sphere of action | 11 | — | [docs/fundamentals/quenching_and_photophysics.md](/fundamentals/quenching_and_photophysics.md) |
| 19 | `text` | Species mixtures | 12 | — | [docs/fundamentals/quenching_and_photophysics.md](/fundamentals/quenching_and_photophysics.md) |
| 20 | `text` | The rate is not constant in time | 10 | — | [docs/fundamentals/quenching_mechanisms.md](/fundamentals/quenching_mechanisms.md) |
| 21 | `text` | Nucleobase-specific quenching | 14 | — | [docs/fundamentals/quenching_mechanisms.md](/fundamentals/quenching_mechanisms.md) |
| 22 | `text` | The three decay laws | 9 | — | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 23 | `python` | Using it headlessly | 12 | compiled | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 24 | `text` | Three AV-to-distance measures | 4 | — | [docs/concepts/accessible_volume.md](/concepts/accessible_volume.md) |
| 25 | `text` | 3. The donor lifetime and the static FRET line | 7 | — | [docs/concepts/accurate_fret.md](/concepts/accurate_fret.md) |
| 26 | `text` | The rotational-correlation-time decay | 4 | — | [docs/concepts/anisotropy.md](/concepts/anisotropy.md) |
| 27 | `text` | The shot-noise floor: a static molecule's expected scatter | 4 | — | [docs/concepts/bva.md](/concepts/bva.md) |
| 28 | `text` | Relevance: the objective costs what moved | 6 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 29 | `text` | What treewidth means | 4 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 30 | `python` | Reading the structure report | 4 | compiled | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 31 | `text` | Reading the structure report | 13 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 32 | `text` | Reading the structure report | 5 | — | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 33 | `text` | The anatomy of a correlation curve | 4 | — | [docs/concepts/fcs_correlation.md](/concepts/fcs_correlation.md) |
| 34 | `text` | Excitation rate | 4 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 35 | `text` | From the scheme to G(τ) | 1 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 36 | `text` | From the scheme to G(τ) | 1 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 37 | `text` | Reading the radial profile | 1 | — | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 38 | `python` | Determining a scheme: fit the power series, not one curve | 10 | compiled | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 39 | `yaml` | What ChiSurf uses, and how to change it | 4 | — | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 40 | `python` | Per-fit override | 2 | compiled | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 41 | `text` | Which threshold? | 4 | — | [docs/concepts/frc_resolution.md](/concepts/frc_resolution.md) |
| 42 | `text` | Transfer rate and efficiency | 4 | — | [docs/concepts/fret.md](/concepts/fret.md) |
| 43 | `text` | Worked numbers | 6 | — | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 44 | `text` | The universal semicircle | 4 | — | [docs/concepts/imaging_flim_phasor.md](/concepts/imaging_flim_phasor.md) |
| 45 | `text` | Core methods | 11 | — | [docs/concepts/index.md](/concepts/index.md) |
| 46 | `text` | Fitting and inference | 7 | — | [docs/concepts/index.md](/concepts/index.md) |
| 47 | `text` | Correlation methods | 9 | — | [docs/concepts/index.md](/concepts/index.md) |
| 48 | `text` | Single-molecule FRET (bursts) | 12 | — | [docs/concepts/index.md](/concepts/index.md) |
| 49 | `text` | Dynamics (hidden Markov) | 7 | — | [docs/concepts/index.md](/concepts/index.md) |
| 50 | `text` | Imaging and resolution | 11 | — | [docs/concepts/index.md](/concepts/index.md) |
| 51 | `text` | Exploration & selection | 5 | — | [docs/concepts/index.md](/concepts/index.md) |
| 52 | `text` | Data and provenance | 9 | — | [docs/concepts/index.md](/concepts/index.md) |
| 53 | `text` | Structure | 9 | — | [docs/concepts/index.md](/concepts/index.md) |
| 54 | `text` | Simulation | 4 | — | [docs/concepts/index.md](/concepts/index.md) |
| 55 | `text` | Recreational tools | 3 | — | [docs/concepts/index.md](/concepts/index.md) |
| 56 | `text` | Application information | 6 | — | [docs/concepts/index.md](/concepts/index.md) |
| 57 | `text` | Which average applies | 9 | — | [docs/concepts/kappa2_orientation.md](/concepts/kappa2_orientation.md) |
| 58 | `text` | Entropy as the criterion | 10 | — | [docs/concepts/maximum_entropy.md](/concepts/maximum_entropy.md) |
| 59 | `text` | Photons do not sample a burst uniformly in time | 1 | — | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 60 | `text` | Doing it in ChiSurf | 7 | — | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 61 | `text` | Doing it in ChiSurf | 3 | — | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 62 | `python` | Doing it in ChiSurf | 9 | compiled | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 63 | `text` | Three properties nothing else has | 6 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 64 | `text` | STICS: track where the peak sits | 5 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 65 | `text` | What limits the arrows | 5 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 66 | `python` | Finding the minimum before describing it | 3 | compiled | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 67 | `python` | One way to ask | 11 | compiled | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 68 | `text` | Why the histogram carries brightness | 4 | — | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 69 | `python` | What ChiSurf writes, and what it only reads | 4 | compiled | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 70 | `python` | Where did this number come from | 4 | compiled | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 71 | `text` | Where did this number come from | 14 | — | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 72 | `text` | Average lifetimes and fractions | 4 | — | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 73 | `text` | Average lifetimes and fractions | 6 | — | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 74 | `text` | In ChiSurf | 6 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 75 | `python` | In ChiSurf | 10 | compiled | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 76 | `text` | In ChiSurf | 11 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 77 | `python` | In ChiSurf | 4 | compiled | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 78 | `text` | Result | 4 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 79 | `text` | In the GUI: the same-molecule probability | 8 | — | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 80 | `python` | Headless | 10 | compiled | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 81 | `python` | Headless | 3 | compiled | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 82 | `text` | Result | 4 | — | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 83 | `python` | In ChiSurf | 13 | compiled | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 84 | `text` | In ChiSurf | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 85 | `text` | In ChiSurf | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 86 | `text` | Result | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 87 | `text` | The PCH tool (classical PCH, not FIDA) | 6 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 88 | `text` | FIDA in the PCH experiment | 7 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 89 | `python` | Headless | 10 | compiled | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 90 | `text` | Result | 4 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 91 | `text` | In the GUI: the FCS model | 9 | — | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 92 | `python` | Headless | 8 | compiled | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 93 | `text` | Result | 4 | — | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 94 | `python` | In ChiSurf | 9 | compiled | [docs/guides/06_nsfcs_second_order.md](/guides/06_nsfcs_second_order.md) |
| 95 | `text` | Result | 4 | — | [docs/guides/06_nsfcs_second_order.md](/guides/06_nsfcs_second_order.md) |
| 96 | `python` | In ChiSurf | 12 | compiled | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 97 | `text` | In ChiSurf | 4 | — | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 98 | `text` | Result | 4 | — | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 99 | `text` | In ChiSurf | 11 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 100 | `text` | In ChiSurf | 6 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 101 | `python` | Headless | 17 | compiled | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 102 | `text` | Result | 4 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 103 | `text` | In ChiSurf | 10 | — | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 104 | `python` | Headless / scripting | 8 | compiled | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 105 | `text` | Result | 5 | — | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 106 | `text` | 1. Load a file | 7 | — | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 107 | `python` | 5. Excitation regions and multiple lasers | 11 | compiled | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 108 | `bash` | Command line and Python | 2 | — | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 109 | `python` | Command line and Python | 3 | compiled | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 110 | `text` | One window for the TTTR file tools (TTTR Tools) | 6 | — | [docs/guides/101_tttr_toolbox.md](/guides/101_tttr_toolbox.md) |
| 111 | `text` | Using the window | 7 | — | [docs/guides/101_tttr_toolbox.md](/guides/101_tttr_toolbox.md) |
| 112 | `text` | Using the window | 7 | — | [docs/guides/101_tttr_toolbox.md](/guides/101_tttr_toolbox.md) |
| 113 | `python` | Using the window | 16 | compiled | [docs/guides/101_tttr_toolbox.md](/guides/101_tttr_toolbox.md) |
| 114 | `bash` | Administering the measurement database: MMFDB Admin | 2 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 115 | `text` | Administering the measurement database: MMFDB Admin | 5 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 116 | `text` | 7. Demo data | 6 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 117 | `python` | Headless and Python | 7 | compiled | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 118 | `text` | Application details for a support request | 4 | — | [docs/guides/103_application_identity.md](/guides/103_application_identity.md) |
| 119 | `python` | Application details for a support request | 5 | compiled | [docs/guides/103_application_identity.md](/guides/103_application_identity.md) |
| 120 | `text` | Light path simulator: crosstalk and R0 of an optical setup | 8 | — | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 121 | `bash` | 5. Headless | 6 | — | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 122 | `python` | 5. Headless | 9 | compiled | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 123 | `bash` | 2. Run it | 1 | — | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 124 | `python` | 3. Python | 13 | compiled | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 125 | `text` | 4. Read the result | 6 | — | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 126 | `text` | 1. HeteroFRET | 5 | — | [docs/guides/107_fret_calculator.md](/guides/107_fret_calculator.md) |
| 127 | `python` | 3. Python | 8 | compiled | [docs/guides/107_fret_calculator.md](/guides/107_fret_calculator.md) |
| 128 | `text` | 1. Open a file | 6 | — | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 129 | `python` | 4. Python | 8 | compiled | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 130 | `python` | 4. Python | 4 | compiled | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 131 | `text` | In ChiSurf | 9 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 132 | `python` | In ChiSurf | 14 | compiled | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 133 | `text` | Result | 4 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 134 | `text` | VV/VH Anisotropy Decay (deprecated) | 4 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 135 | `python` | In ChiSurf | 10 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 136 | `text` | Fitting in the GUI | 8 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 137 | `python` | Reading bursts | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 138 | `python` | Fitting a kinetic scheme | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 139 | `python` | Diagnostics | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 140 | `python` | Measuring an exchange rate: several time bins, one rate | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 141 | `text` | Result | 4 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 142 | `python` | One measurement, one file | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 143 | `text` | Converting on drop | 7 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 144 | `python` | Converting on drop | 4 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 145 | `python` | In ChiSurf | 17 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 146 | `python` | In ChiSurf | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 147 | `text` | Result | 4 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 148 | `text` | Open the tool | 7 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 149 | `text` | Open the tool | 10 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 150 | `text` | Open the tool | 5 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 151 | `python` | Headless | 5 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 152 | `python` | Headless | 6 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 153 | `text` | Result | 4 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 154 | `text` | In the GUI: Accurate FRET | 10 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 155 | `python` | Headless | 8 | compiled | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 156 | `text` | Result | 4 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 157 | `text` | In ChiSurf | 8 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 158 | `text` | In ChiSurf | 6 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 159 | `python` | In ChiSurf | 8 | compiled | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 160 | `text` | Result | 4 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 161 | `python` | In ChiSurf | 23 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 162 | `text` | Burst-wise FCS | 8 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 163 | `text` | Burst-wise FCS | 6 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 164 | `python` | Burst-wise FCS | 12 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 165 | `text` | Result | 4 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 166 | `python` | In ChiSurf | 6 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 167 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 168 | `text` | The Filter Calculator | 6 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 169 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 170 | `python` | 2D-FLCS on many molecules, with error bars | 10 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 171 | `bash` | 2D-FLCS on many molecules, with error bars | 2 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 172 | `python` | 2D-FLCS on many molecules, with error bars | 4 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 173 | `text` | Instrument parameters | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 174 | `text` | Result | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 175 | `python` | In ChiSurf | 9 | compiled | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 176 | `text` | The lifetime-FCS simulator | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 177 | `text` | Setting up species and kinetics in the GUI | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 178 | `text` | Result | 4 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 179 | `python` | In ChiSurf | 8 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 180 | `bash` | In ChiSurf | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 181 | `text` | The H2MM tool | 11 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 182 | `python` | Choosing a decoder | 4 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 183 | `bash` | Writing the states back into the photons | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 184 | `text` | Per-state decays | 8 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 185 | `text` | Result | 4 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 186 | `text` | The ebFRET window | 8 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 187 | `python` | Headless | 10 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 188 | `python` | Headless | 4 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 189 | `text` | Result | 6 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 190 | `text` | Extracting patterns from non-burst photons | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 191 | `python` | Extracting patterns from non-burst photons | 16 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 192 | `python` | In ChiSurf | 14 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 193 | `python` | Measured IRF and background, Opt, Save fit | 11 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 194 | `text` | Measured IRF and background, Opt, Save fit | 8 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 195 | `text` | Measured IRF and background, Opt, Save fit | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 196 | `text` | Measured IRF and background, Opt, Save fit | 7 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 197 | `text` | Result | 9 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 198 | `text` | The lifetime of a state, not of a burst | 5 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 199 | `python` | In ChiSurf | 12 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 200 | `text` | Trace Browser | 9 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 201 | `text` | Trace Browser | 6 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 202 | `python` | Trace Browser | 3 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 203 | `text` | Result | 4 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 204 | `python` | In ChiSurf | 13 | compiled | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 205 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 8 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 206 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 207 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 5 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 208 | `text` | Result | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 209 | `python` | In ChiSurf | 8 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 210 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 211 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 212 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 213 | `python` | Selecting pixels | 5 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 214 | `text` | Result | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 215 | `text` | The Intensity tool | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 216 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 217 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 218 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 219 | `python` | In ChiSurf | 10 | compiled | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 220 | `text` | In the Accurate FRET tool | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 221 | `text` | In the Accurate FRET tool | 6 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 222 | `text` | Result | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 223 | `text` | In ChiSurf | 8 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 224 | `python` | In ChiSurf | 9 | compiled | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 225 | `text` | Result | 7 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 226 | `text` | In ChiSurf | 7 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 227 | `text` | In ChiSurf | 8 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 228 | `python` | In ChiSurf | 9 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 229 | `text` | In ChiSurf | 12 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 230 | `python` | In ChiSurf | 17 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 231 | `text` | Result | 4 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 232 | `text` | In ChiSurf | 10 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 233 | `text` | In ChiSurf | 5 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 234 | `python` | In ChiSurf | 14 | compiled | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 235 | `text` | Result | 4 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 236 | `text` | In ChiSurf | 8 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 237 | `python` | In ChiSurf | 14 | compiled | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 238 | `text` | Result | 4 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 239 | `python` | The steps | 20 | compiled | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 240 | `text` | Exploring the dwells | 10 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 241 | `text` | Exploring the dwells | 4 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 242 | `python` | In ChiSurf | 8 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 243 | `python` | In ChiSurf | 17 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 244 | `text` | In ChiSurf | 10 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 245 | `text` | Result | 4 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 246 | `python` | In ChiSurf | 23 | compiled | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 247 | `text` | In ChiSurf | 9 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 248 | `text` | Result | 5 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 249 | `python` | In ChiSurf | 17 | compiled | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 250 | `text` | In ChiSurf | 11 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 251 | `text` | Result | 7 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 252 | `python` | In ChiSurf | 20 | compiled | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 253 | `text` | Result | 14 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 254 | `text` | In ChiSurf | 9 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 255 | `python` | In ChiSurf | 13 | compiled | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 256 | `text` | Result | 4 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 257 | `python` | In ChiSurf | 10 | compiled | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 258 | `text` | Result | 4 | — | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 259 | `text` | Compute a LUT per channel and add it to the setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 260 | `text` | It lands in the detector setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 261 | `bash` | Headless (CLI / API) | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 262 | `python` | Headless (CLI / API) | 6 | compiled | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 263 | `text` | 2. Concepts | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 264 | `text` | 5. Read the results | 6 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 265 | `text` | 9. Punctate signal? Count objects instead | 5 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 266 | `text` | 9. Punctate signal? Count objects instead | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 267 | `text` | 10. Gate a population in the scatter | 7 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 268 | `bash` | Headless / CLI | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 269 | `python` | Python API | 12 | compiled | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 270 | `python` | 1. Fit something | 20 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 271 | `python` | 2. Attach a prior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 272 | `python` | 3. Sample the posterior | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 273 | `python` | 3. Sample the posterior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 274 | `python` | 4. Read the diagnostics before the answer | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 275 | `text` | 4. Read the diagnostics before the answer | 3 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 276 | `python` | 4. Read the diagnostics before the answer | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 277 | `python` | 6. Global fits | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 278 | `python` | 6. Global fits | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 279 | `python` | 7. Linked global fits: use `collapsed` | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 280 | `python` | 8. Inspecting the structure of a global fit | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 281 | `text` | 8. Inspecting the structure of a global fit | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 282 | `text` | The Dependence tab, and why it is not the correlation tab | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 283 | `text` | The Dependence tab, and why it is not the correlation tab | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 284 | `python` | The Dependence tab, and why it is not the correlation tab | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 285 | `python` | 9. Reusing a chain under a different prior | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 286 | `text` | 10. Opening the chains in nDXplorer | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 287 | `python` | 10. Opening the chains in nDXplorer | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 288 | `python` | 11. Looking at the posterior instead of reading about it | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 289 | `text` | 11. Looking at the posterior instead of reading about it | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 290 | `python` | 11. Looking at the posterior instead of reading about it | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 291 | `text` | 12. In the GUI | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 292 | `python` | 12. In the GUI | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 293 | `python` | 13. Asking directly, without picking an estimator first | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 294 | `python` | 14. From a script, a macro or the server | 14 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 295 | `text` | 15. Error bars on the quantities you publish | 7 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 296 | `python` | 15. Error bars on the quantities you publish | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 297 | `python` | 15. Error bars on the quantities you publish | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 298 | `text` | Using it in the GUI | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 299 | `bash` | Using it from a terminal | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 300 | `yaml` | Skills: how it knows *how* | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 301 | `markdown` | Writing your own | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 302 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 303 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 304 | `text` | 3. Pick the dyes (and the setup) | 5 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 305 | `python` | 3. Pick the dyes (and the setup) | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 306 | `text` | 6. Calibrate | 15 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 307 | `text` | 7. Read the plots | 7 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 308 | `text` | 7. Read the plots | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 309 | `python` | Keeping a calibration | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 310 | `bash` | Trying it without data (and checking it works) | 1 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 311 | `python` | Trying it without data (and checking it works) | 10 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 312 | `bash` | Head-less | 9 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 313 | `python` | From Python | 21 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 314 | `python` | In the Global View | 7 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 315 | `python` | In the Global View | 6 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 316 | `python` | A worked run against known truth | 25 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 317 | `text` | Fitting a kinetic scheme | 6 | — | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 318 | `python` | Fitting a kinetic scheme | 11 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 319 | `python` | Uncertainties | 5 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 320 | `text` | Measure | 8 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 321 | `text` | Read the result | 5 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 322 | `text` | Read the result | 6 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 323 | `bash` | Headless | 2 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 324 | `text` | Headless | 7 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 325 | `python` | Python | 8 | compiled | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 326 | `text` | The window | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 327 | `text` | Loading and looking | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 328 | `text` | Loading and looking | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 329 | `text` | Integrative (bead) models | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 330 | `text` | Integrative (bead) models | 8 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 331 | `text` | Integrative (bead) models | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 332 | `text` | RMF models from IMP | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 333 | `text` | Whether the camera follows the frame | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 334 | `text` | Whether the camera follows the frame | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 335 | `text` | Choosing a resolution | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 336 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 337 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 338 | `text` | Simulating a map, and fitting a model into one | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 339 | `text` | Simulating a map, and fitting a model into one | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 340 | `text` | The Map panel | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 341 | `text` | Playing a trajectory | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 342 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 343 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 344 | `text` | Crystal symmetry | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 345 | `text` | Making it look good | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 346 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 347 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 348 | `text` | Seeing through a surface | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 349 | `text` | How finely the surface is built | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 350 | `text` | A picture behind the scene, so transparency reads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 351 | `text` | A picture behind the scene, so transparency reads | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 352 | `text` | Clipping, and how to get out of it | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 353 | `text` | Every setting, in the view it changes | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 354 | `text` | How big the chrome draws | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 355 | `text` | Tuning a metaball | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 356 | `text` | Tidying and shielding | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 357 | `text` | Adding hydrogens | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 358 | `text` | Saving a session | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 359 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 360 | `text` | Organising the panel | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 361 | `text` | Organising the panel | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 362 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 363 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 364 | `text` | Organising the panel | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 365 | `text` | Selecting | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 366 | `text` | How far a click spreads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 367 | `text` | Drawing | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 368 | `text` | Drawing | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 369 | `text` | Measuring | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 370 | `text` | Measuring | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 371 | `text` | Measuring by clicking | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 372 | `text` | Polar contacts | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 373 | `text` | Polar contacts | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 374 | `text` | Hydrogen-bond networks | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 375 | `text` | Where two chains touch | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 376 | `text` | Salt bridges, halogen bonds and pi interactions | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 377 | `text` | Clashes | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 378 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 379 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 380 | `text` | The mutagenesis wizard | 15 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 381 | `text` | The mutagenesis wizard | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 382 | `text` | Bonds | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 383 | `text` | Superposing structures | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 384 | `text` | Superposing structures | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 385 | `text` | Superposing structures | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 386 | `text` | Presets — one command to a figure | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 387 | `text` | Side chains that grow out of the ribbon | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 388 | `text` | Colouring by a computed quantity | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 389 | `text` | Colouring by a computed quantity | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 390 | `text` | Showing a quantity as thickness | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 391 | `text` | Showing a quantity as thickness | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 392 | `text` | Getting data in and out | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 393 | `text` | Getting data in and out | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 394 | `text` | Getting data in and out | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 395 | `text` | Exporting the scene as a 3-D model | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 396 | `text` | Images | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 397 | `python` | Headless and scripted use | 17 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 398 | `python` | Headless and scripted use | 11 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 399 | `text` | Open the tool | 8 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 400 | `bash` | Headless | 4 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 401 | `bash` | Launching | 5 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 402 | `python` | ndX in ChiSurf | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 403 | `python` | Lines pushed from another tool | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 404 | `text` | Lines pushed from another tool | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 405 | `text` | Phasor plots are overlays | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 406 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 407 | `text` | Referencing the phasor to the instrument and removing background | 2 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 408 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 409 | `python` | Fitting a constant: moving the data onto the curve | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 410 | `python` | Fitting a constant: moving the data onto the curve | 14 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 411 | `python` | Curves that trace a line rather than evaluate one | 10 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 412 | `python` | Worked example: two smFRET populations and the static FRET line | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 413 | `python` | Worked example: two smFRET populations and the static FRET line | 4 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 414 | `text` | Worked example: two smFRET populations and the static FRET line | 10 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 415 | `text` | Fit 2-D Gaussians to the populations on the map | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 416 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 417 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 418 | `text` | Find the informative projections | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 419 | `python` | Find the informative projections | 9 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 420 | `text` | Session state in the measurement | 3 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 421 | `text` | The workflow | 8 | — | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 422 | `python` | The workflow | 31 | compiled | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 423 | `text` | The region editor | 7 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 424 | `text` | The region editor | 8 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 425 | `text` | The single-molecule imaging workflow | 9 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 426 | `python` | The single-molecule imaging workflow | 2 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 427 | `bash` | Headless | 2 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 428 | `text` | Headless | 4 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 429 | `python` | Python | 28 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 430 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 431 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 432 | `text` | Region MLE: the demo's fit assumptions | 5 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 433 | `text` | Open the tool | 10 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 434 | `text` | Open the tool | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 435 | `text` | The transition-time scan | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 436 | `bash` | Headless | 4 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 437 | `bash` | Headless | 2 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 438 | `text` | Open the tool | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 439 | `text` | 2. Link | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 440 | `bash` | Headless | 4 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 441 | `bash` | Headless | 2 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 442 | `text` | Open the tool | 7 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 443 | `bash` | Headless | 3 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 444 | `text` | Doing it | 7 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 445 | `json` | Advertising another analysis | 13 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 446 | `python` | Headless | 10 | compiled | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 447 | `text` | What counts as a change | 1 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 448 | `text` | What counts as a change | 9 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 449 | `json` | The stamp files | 16 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 450 | `python` | Forcing a recomputation | 3 | compiled | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 451 | `text` | Open the tool | 10 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 452 | `text` | Load a trace | 4 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 453 | `text` | Choose the number of states | 5 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 454 | `text` | Read the result | 7 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 455 | `bash` | Headless | 2 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 456 | `python` | Headless | 26 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 457 | `python` | Headless | 2 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 458 | `text` | The tool | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 459 | `bash` | The tool | 2 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 460 | `python` | The tool | 3 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 461 | `python` | The cheap reading: a pCF curve from a carpet you already have | 12 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 462 | `python` | The real thing: position-resolved pCF | 14 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 463 | `text` | The real thing: position-resolved pCF | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 464 | `python` | A line scan | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 465 | `python` | The arrows: a velocity field | 7 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 466 | `text` | The arrows: a velocity field | 6 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 467 | `python` | The arrows: a velocity field | 6 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 468 | `python` | The second route, for a cross-check | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 469 | `bash` | Regenerating the figures | 1 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 470 | `text` | 4. Read the four outputs | 9 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 471 | `json` | 5. Build your own scheme | 10 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 472 | `bash` | 6. Headless | 8 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 473 | `python` | 7. From the Python API | 12 | compiled | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 474 | `text` | 1. Load the folder | 4 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 475 | `text` | 2. Fit the static model first | 9 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 476 | `text` | 2. Fit the static model first | 7 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 477 | `python` | 5. Headless | 13 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 478 | `python` | 5. Headless | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 479 | `python` | 6. Try it on data whose answer you know | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 480 | `text` | 1. Open the step | 6 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 481 | `text` | 2. Look at the curve before choosing a threshold | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 482 | `text` | 5. Write the fused folder | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 483 | `text` | 5. Write the fused folder | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 484 | `text` | 5. Write the fused folder | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 485 | `bash` | Headless | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 486 | `python` | Headless | 8 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 487 | `python` | Headless | 6 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 488 | `python` | The first thing to know | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 489 | `text` | The first thing to know | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 490 | `python` | Reading a fit | 2 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 491 | `python` | Reading a fit | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 492 | `text` | Reading a fit | 6 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 493 | `text` | Turning what you did into a script | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 494 | `python` | Plotting | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 495 | `text` | Plotting | 6 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 496 | `text` | 2. Open the parameter network | 10 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 497 | `text` | 3. Link the shared parameter | 4 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 498 | `text` | 4. Check that the link took effect | 7 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 499 | `python` | Headless: linking two fits | 25 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 500 | `text` | Headless: linking two fits | 2 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 501 | `python` | Headless: linking two fits | 2 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 502 | `python` | Headless: the joint fit | 9 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 503 | `text` | Headless: the joint fit | 1 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 504 | `text` | Step 2 — use your own dyes | 9 | — | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 505 | `python` | Headless | 8 | compiled | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 506 | `text` | Maximum-entropy decay analysis | 4 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 507 | `text` | Maximum-entropy decay analysis | 5 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 508 | `text` | Step 2 — run once, and distrust the answer | 16 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 509 | `python` | Headless | 10 | compiled | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 510 | `text` | How it got there | 11 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 511 | `text` | The settings are the recipe | 13 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 512 | `json` | Opening the tool that made a result | 5 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 513 | `python` | Verifying | 4 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 514 | `bash` | Headless | 7 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 515 | `python` | Headless | 11 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 516 | `python` | Plots | 7 | compiled | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 517 | `text` | The kernel terminal | 4 | — | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 518 | `text` | The Acquisition fit window | 7 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 519 | `python` | The Acquisition fit window | 4 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 520 | `python` | Without a GUI | 25 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 521 | `python` | Without a GUI | 10 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 522 | `text` | The simple workflow | 6 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 523 | `text` | 3 — Alternation, measured rather than typed | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 524 | `text` | Titration | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 525 | `bash` | Headless | 4 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 526 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 527 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 528 | `bash` | Headless | 1 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 529 | `python` | Headless | 9 | compiled | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 530 | `text` | Asking | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 531 | `bash` | From the command line | 1 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 532 | `text` | From the command line | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 533 | `python` | From Python | 6 | compiled | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 534 | `text` | Open the tool | 8 | — | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 535 | `python` | Headless | 12 | compiled | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 536 | `text` | Generate a decay | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 537 | `text` | Correlate | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 538 | `python` | Headless | 28 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 539 | `python` | Headless | 12 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 540 | `text` | Open the tool | 9 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 541 | `text` | Open a tool | 6 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 542 | `text` | The tools | 4 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 543 | `python` | Headless | 27 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 544 | `python` | Headless | 7 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 545 | `bash` | Headless | 1 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 546 | `bash` | Open the tool | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 547 | `text` | 1. Channel Definitions | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 548 | `text` | 2. Files & Steps | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 549 | `text` | 3. Photon / Burst Filter | 8 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 550 | `text` | 4. Correlator | 8 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 551 | `text` | 5. FCS Merger | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 552 | `text` | 5. FCS Merger | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 553 | `bash` | Converting correlation files | 2 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 554 | `python` | Headless | 29 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 555 | `python` | Headless | 6 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 556 | `python` | Headless | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 557 | `text` | Open the tools | 4 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 558 | `text` | Settings | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 559 | `text` | Settings | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 560 | `text` | Reading the output | 5 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 561 | `text` | Synthetic Decay Generator | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 562 | `text` | Synthetic Decay Generator | 7 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 563 | `text` | Synthetic Decay Generator | 5 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 564 | `bash` | Headless | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 565 | `python` | Headless | 22 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 566 | `text` | Open the tool | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 567 | `text` | Set it up | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 568 | `python` | Headless | 13 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 569 | `python` | Headless | 19 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 570 | `text` | Open the tool | 8 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 571 | `text` | 2. Loaded data (optional) | 5 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 572 | `text` | 4. Run | 7 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 573 | `python` | Headless | 23 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 574 | `bash` | Headless | 3 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 575 | `python` | Headless | 27 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 576 | `text` | HydroPro: diffusion coefficients from a structure | 5 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 577 | `text` | Open the tool | 7 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 578 | `text` | Run and read the result | 6 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 579 | `python` | Headless | 10 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 580 | `text` | Headless | 18 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 581 | `python` | Headless | 3 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 582 | `text` | Open the tool | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 583 | `bash` | Headless | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 584 | `python` | Headless | 7 | compiled | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 585 | `text` | Align | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 586 | `text` | Convert | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 587 | `text` | Remove Clashed | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 588 | `text` | Energy Calc | 6 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 589 | `text` | FRET | 6 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 590 | `bash` | FRET | 2 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 591 | `python` | Headless | 33 | compiled | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 592 | `text` | Open the tool | 8 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 593 | `text` | Start with your dye pair | 5 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 594 | `python` | Start with your dye pair | 11 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 595 | `text` | Read the result | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 596 | `text` | Where the lines go next | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 597 | `bash` | Headless | 3 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 598 | `json` | Headless | 9 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 599 | `python` | Headless | 16 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 600 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 601 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 602 | `bash` | 3. Push to the MMFDB | 2 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 603 | `text` | 4. Compute R₀ | 7 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 604 | `python` | 4. Compute R₀ | 8 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 605 | `python` | 6. Headless | 28 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 606 | `bash` | 6. Headless | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 607 | `text` | Narrow windows | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 608 | `text` | 1. Open the tool | 9 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 609 | `text` | 3. A real image | 5 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 610 | `text` | 3. A real image | 6 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 611 | `bash` | 6. Headless | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 612 | `python` | 6. Headless | 10 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 613 | `python` | 6. Headless | 5 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 614 | `text` | Window and bright pixels | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 615 | `text` | 1. Where it is | 6 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 616 | `bash` | 4. Headless | 4 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 617 | `python` | 4. Headless | 17 | compiled | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 618 | `text` | See also | 7 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 619 | `text` | 1. Open the tool | 8 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 620 | `text` | 2. The detector setup | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 621 | `text` | 4. Look at the image | 5 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 622 | `bash` | 7. From the command line and Python | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 623 | `python` | 7. From the command line and Python | 9 | compiled | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 624 | `text` | 1. The page | 7 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 625 | `text` | 2. Typing into a table | 4 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 626 | `python` | 4. From Python | 6 | compiled | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 627 | `text` | 5. Edit the complete working definition | 5 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 628 | `text` | 6. Independent reference calibration | 8 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 629 | `text` | 6. Independent reference calibration | 6 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 630 | `text` | 1. Docking and screening | 4 | — | [docs/guides/88_fret_docking.md](/guides/88_fret_docking.md) |
| 631 | `text` | 1. Open the tool | 9 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 632 | `bash` | Headless | 2 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 633 | `python` | Headless | 5 | compiled | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 634 | `bash` | 1. Open the tool | 1 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 635 | `text` | 1. Open the tool | 9 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 636 | `text` | 3. Detector, channels and gates | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 637 | `python` | Headless | 11 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 638 | `python` | Headless | 13 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 639 | `text` | Timing when comparing earlier results | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 640 | `text` | 1. Open the tool | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 641 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 642 | `text` | 5. Package Manager | 4 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 643 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 644 | `python` | Headless / Python | 2 | compiled | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 645 | `bash` | 1. Open the tool and load the fast reference | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 646 | `text` | 1. Open the tool and load the fast reference | 7 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 647 | `text` | 4. Batch, export, archive | 6 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 648 | `python` | Headless and Python | 9 | compiled | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 649 | `bash` | Headless and Python | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 650 | `text` | 1. Open the tool and load a trace | 8 | — | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 651 | `python` | 4. Save and reuse | 7 | compiled | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 652 | `text` | 1. Open the tool and load a stack | 5 | — | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 653 | `python` | Headless and Python | 4 | compiled | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 654 | `text` | Audifier: photon streams as sound and as a waterfall | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 655 | `text` | Layout and saved preferences | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 656 | `text` | 1. The window | 5 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 657 | `text` | Help, Restart and Guide | 7 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 658 | `python` | 4. Python | 8 | compiled | [docs/guides/95_games.md](/guides/95_games.md) |
| 659 | `text` | 1. Open the tool | 6 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 660 | `text` | 4. Read a failure | 5 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 661 | `bash` | From the command line and from Python | 1 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 662 | `python` | From the command line and from Python | 8 | compiled | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 663 | `text` | 1. The window | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 664 | `text` | 2. The destinations | 4 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 665 | `text` | 2. The destinations | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 666 | `text` | CLSM Generator: a scan whose answer is known | 4 | — | [docs/guides/98_clsm_generator.md](/guides/98_clsm_generator.md) |
| 667 | `text` | The imaging workflow in one window (Imaging Tools) | 5 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 668 | `text` | 1. Open the hub | 7 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 669 | `text` | 1. Choose the photons and the detector | 6 | — | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 670 | `python` | The correction | 6 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 671 | `text` | Where the factors come from | 10 | — | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 672 | `python` | 1. Light-path prior → data-optimized posterior | 10 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 673 | `python` | 2. Reference samples (donor-only, acceptor-only) | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 674 | `python` | 3. The donor lifetime and the static FRET line | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 675 | `python` | All three at once | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 676 | `python` | The general case: crosstalk matrices | 13 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 677 | `python` | Naive vs. stable un-mixing | 2 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 678 | `python` | Preserving photon-counting statistics (integer "photon shuffling") | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 679 | `python` | ndxplorer: stable / shuffle un-mixing | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 680 | `python` | Per-pixel / FLIM imaging | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 681 | `python` | Scalar multi-chromophore path | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 682 | `python` | Global analysis and ndxplorer | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 683 | `python` | Global analysis and ndxplorer | 3 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 684 | `text` | Inputs and outputs | 13 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 685 | `text` | GUI | 6 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 686 | `bash` | CLI | 5 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 687 | `python` | Python API | 7 | compiled | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 688 | `text` | Projects and session lifecycle | 3 | — | [docs/guides/index.md](/guides/index.md) |
| 689 | `text` | Photon data and the burst pipeline | 23 | — | [docs/guides/index.md](/guides/index.md) |
| 690 | `text` | smFRET: efficiency, stoichiometry and corrections | 17 | — | [docs/guides/index.md](/guides/index.md) |
| 691 | `text` | Dynamics: distributions, kinetics and hidden states | 18 | — | [docs/guides/index.md](/guides/index.md) |
| 692 | `text` | Fluorescence decays and anisotropy | 8 | — | [docs/guides/index.md](/guides/index.md) |
| 693 | `text` | Correlation spectroscopy | 10 | — | [docs/guides/index.md](/guides/index.md) |
| 694 | `text` | Imaging and microscopy | 19 | — | [docs/guides/index.md](/guides/index.md) |
| 695 | `text` | Structure and modelling | 10 | — | [docs/guides/index.md](/guides/index.md) |
| 696 | `text` | Exploration, simulation and automation | 15 | — | [docs/guides/index.md](/guides/index.md) |
| 697 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 698 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 699 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 700 | `text` | Application and settings | 8 | — | [docs/guides/index.md](/guides/index.md) |
| 701 | `text` | Algorithm Pipeline | 12 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 702 | `text` | In the window | 6 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 703 | `python` | Basic Usage | 11 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 704 | `python` | Step-by-Step Usage | 24 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 705 | `python` | Multi-Channel Data | 7 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 706 | `python` | Visualization | 9 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 707 | `python` | Constructor | 1 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 708 | `text` | Richardson-Lucy Algorithm | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 709 | `bash` | Testing | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 710 | `text` | Saving and reopening projects | 5 | — | [docs/guides/saving_projects.md](/guides/saving_projects.md) |
| 711 | `text` | Adding the membrane-diffusion models | 10 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 712 | `text` | Adding the membrane-diffusion models | 4 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 713 | `text` | Analysis dock | 1 | — | [docs/manual/analysis_dock.md](/manual/analysis_dock.md) |
| 714 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 715 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 716 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 717 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 718 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 719 | `text` | Calculation of co-diffusing molecules | 1 | — | [docs/manual/calculation_of_codiffusing_molecules.md](/manual/calculation_of_codiffusing_molecules.md) |
| 720 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 721 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 722 | `text` | Calculation of the overlap volume and co-diffusion amplitude | 1 | — | [docs/manual/calculations_2.md](/manual/calculations_2.md) |
| 723 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 724 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 725 | `text` | Correction factors for spectral crosstalk & direct acceptor excitation | 1 | — | [docs/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md](/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md) |
| 726 | `text` | Correlation merging | 1 | — | [docs/manual/correlation_merging.md](/manual/correlation_merging.md) |
| 727 | `text` | Correlator | 1 | — | [docs/manual/correlator.md](/manual/correlator.md) |
| 728 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 729 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 730 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 731 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 732 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 733 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 734 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 735 | `text` | Data import | 2 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 736 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 737 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 738 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 739 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 740 | `text` | Data import | 3 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 741 | `text` | Data input and file format | 12 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 742 | `text` | Data input and file format | 5 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 743 | `shell` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 744 | `text` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 745 | `text` | Determination of g-factor and depolarization factors using ChiSurf | 1 | — | [docs/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md](/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md) |
| 746 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 747 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 748 | `text` | Discrete FRET rate constants | 2 | — | [docs/manual/discrete_fret_rate_constants.md](/manual/discrete_fret_rate_constants.md) |
| 749 | `text` | Equation parsing | 1 | — | [docs/manual/equation_parsing.md](/manual/equation_parsing.md) |
| 750 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 751 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 752 | `text` | F-Calculator | 1 | — | [docs/manual/fcalculator.md](/manual/fcalculator.md) |
| 753 | `text` | Fit interface | 1 | — | [docs/manual/fit_interface.md](/manual/fit_interface.md) |
| 754 | `text` | Fit models | 3 | — | [docs/manual/fit_models.md](/manual/fit_models.md) |
| 755 | `text` | Fit of the green-excitation FCS curve | 4 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 756 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 757 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 758 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 759 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 760 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 761 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 762 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 763 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 764 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 765 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 766 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 767 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 768 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 769 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 770 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 771 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 772 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 773 | `text` | Fit of auto- and cross-correlation curves | 1 | — | [docs/manual/fit_of_auto_and_crosscorrelation_curves.md](/manual/fit_of_auto_and_crosscorrelation_curves.md) |
| 774 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 775 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 776 | `text` | Fit of the red-excitation FCS curve | 1 | — | [docs/manual/fit_of_fcs_curve.md](/manual/fit_of_fcs_curve.md) |
| 777 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 778 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 779 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 780 | `text` | Fluorescence Lifetime | 5 | — | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 781 | `text` | Static FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 782 | `text` | Dynamic FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 783 | `text` | Visualizing FRET Lines | 14 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 784 | `text` | Visualizing FRET Lines | 21 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 785 | `text` | Example: Complete Analysis Workflow | 71 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 786 | `text` | Troubleshooting | 3 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 787 | `text` | Example Script | 2 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 788 | `text` | Global fit of auto- and cross-correlation curves | 1 | — | [docs/manual/global_fit_of_auto_and_crosscorrelation_curves.md](/manual/global_fit_of_auto_and_crosscorrelation_curves.md) |
| 789 | `text` | Global fit of FCS curves | 1 | — | [docs/manual/global_fit_of_fcs_curves.md](/manual/global_fit_of_fcs_curves.md) |
| 790 | `text` | Fitting interface & worked examples | 20 | — | [docs/manual/index.md](/manual/index.md) |
| 791 | `text` | Fitting interface & worked examples | 10 | — | [docs/manual/index.md](/manual/index.md) |
| 792 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 793 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 794 | `text` | Fitting interface & worked examples | 7 | — | [docs/manual/index.md](/manual/index.md) |
| 795 | `text` | Fitting interface & worked examples | 23 | — | [docs/manual/index.md](/manual/index.md) |
| 796 | `text` | Fitting interface & worked examples | 9 | — | [docs/manual/index.md](/manual/index.md) |
| 797 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 798 | `text` | Fitting interface & worked examples | 15 | — | [docs/manual/index.md](/manual/index.md) |
| 799 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 800 | `text` | Influence of FRET efficiency | 1 | — | [docs/manual/influence_of_fret_efficiency.md](/manual/influence_of_fret_efficiency.md) |
| 801 | `text` | Influence of triplet blinking | 1 | — | [docs/manual/influence_of_triplet_blinking.md](/manual/influence_of_triplet_blinking.md) |
| 802 | `text` | Introduction | 6 | — | [docs/manual/introduction.md](/manual/introduction.md) |
| 803 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 804 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 805 | `text` | Loading & plotting data | 1 | — | [docs/manual/loading__plotting_data.md](/manual/loading__plotting_data.md) |
| 806 | `text` | Loading and setting up the eGFP data set | 1 | — | [docs/manual/loading_and_setting_up_the_egfp_data_set.md](/manual/loading_and_setting_up_the_egfp_data_set.md) |
| 807 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 808 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 809 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 810 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 811 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 812 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 813 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 814 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 815 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 816 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 817 | `text` | Model scores | 2 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 818 | `text` | Model scores | 3 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 819 | `text` | Model scores | 1 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 820 | `text` | Model scoring range | 1 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 821 | `text` | Model scoring range | 2 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 822 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 823 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 824 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 825 | `text` | Arranging the windows | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 826 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 827 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 828 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 829 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 830 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 831 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 832 | `text` | Correlator: overview | 1 | — | [docs/manual/overview_2.md](/manual/overview_2.md) |
| 833 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 834 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 835 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 836 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 837 | `text` | Parameter optimization | 1 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 838 | `text` | Settings | 25 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 839 | `text` | Parameter sampling | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 840 | `text` | Parameter sampling | 1 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 841 | `text` | From the shell | 2 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 842 | `text` | From the shell | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 843 | `text` | Parameter scan | 1 | — | [docs/manual/parameter_scan.md](/manual/parameter_scan.md) |
| 844 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 845 | `text` | Parameters | 8 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 846 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 847 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 848 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 849 | `text` | Parameters | 3 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 850 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 851 | `text` | Partial donor-donor energy migration | 3 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 852 | `text` | Parameters | 5 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 853 | `text` | Reference curves | 1 | — | [docs/manual/reference_curves.md](/manual/reference_curves.md) |
| 854 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 855 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 856 | `text` | Saving & exporting the results | 8 | — | [docs/manual/saving__exporting_the_results.md](/manual/saving__exporting_the_results.md) |
| 857 | `xml` | Saving and loading networks | 14 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 858 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 859 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 860 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 861 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 862 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 863 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 864 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 865 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 866 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 867 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 868 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 869 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 870 | `text` | Step 1: Approximating g-factor with small fluorophore | 1 | — | [docs/manual/step_1_approximating_gfactor_with_small_fluorophore.md](/manual/step_1_approximating_gfactor_with_small_fluorophore.md) |
| 871 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 872 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 873 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 874 | `text` | Two single files | 1 | — | [docs/manual/two_single_files.md](/manual/two_single_files.md) |
| 875 | `text` | VV/VH format | 1 | — | [docs/manual/vv_vh_format.md](/manual/vv_vh_format.md) |
| 876 | `text` | Worm-like chain | 4 | — | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 877 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 878 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 879 | `text` | Usage | 7 | — | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 880 | `python` | Correlation section | 5 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 881 | `python` | Correlation section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 882 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 883 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 884 | `text` | Intensity trace section | 6 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 885 | `python` | Correlation arrays | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 886 | `python` | Intensity arrays | 9 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 887 | `text` | ALV-7004/USB `.asc` (openASC_ALV_7004) | 7 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 888 | `text` | File formats | 4 | — | [docs/reference/file_formats/index.md](/reference/file_formats/index.md) |
| 889 | `python` | Single-file structure reader | 6 | compiled | [docs/reference/file_formats/structure_files.md](/reference/file_formats/structure_files.md) |
| 890 | `python` | Workflow | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 891 | `python` | Becker-SDT | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 892 | `python` | Preview and Add | 7 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 893 | `text` | Reference | 12 | — | [docs/reference/index.md](/reference/index.md) |
| 894 | `bash` | Local (primitive) | 10 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 895 | `bash` | MMFDB round trip | 12 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 896 | `bash` | Local (primitive) | 4 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 897 | `bash` | Local (primitive) | 3 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 898 | `bash` | MMFDB round trip | 6 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 899 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 900 | `python` | From a script | 9 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 901 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 902 | `python` | Saving a single parameter | 7 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 903 | `text` | Plugin catalogue | 4 | — | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 904 | `yaml` | 3. `settings_colors.yaml` (global color palette) | 3 | — | [docs/reference/settings.md](/reference/settings.md) |
| 905 | `json` | 4.2 Schema | 32 | — | [docs/reference/settings.md](/reference/settings.md) |
| 906 | `python` | User-Defined Models in ChiSurf | 2 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 907 | `python` | 1.1 Write the model | 21 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 908 | `yaml` | 1.3 List it in `experiment_configs.yaml` | 4 | — | [docs/reference/user_models.md](/reference/user_models.md) |
| 909 | `python` | 3. Turning a plain function into a model | 7 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
