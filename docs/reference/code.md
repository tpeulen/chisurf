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

*957 blocks, 241 Python, 0 executed.*

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
| 49 | `text` | Single-molecule FRET (bursts) | 13 | — | [docs/concepts/index.md](/concepts/index.md) |
| 50 | `text` | Dynamics (hidden Markov) | 7 | — | [docs/concepts/index.md](/concepts/index.md) |
| 51 | `text` | Imaging and resolution | 11 | — | [docs/concepts/index.md](/concepts/index.md) |
| 52 | `text` | Exploration & selection | 5 | — | [docs/concepts/index.md](/concepts/index.md) |
| 53 | `text` | Data and provenance | 12 | — | [docs/concepts/index.md](/concepts/index.md) |
| 54 | `text` | Structure | 10 | — | [docs/concepts/index.md](/concepts/index.md) |
| 55 | `text` | Simulation | 4 | — | [docs/concepts/index.md](/concepts/index.md) |
| 56 | `text` | Recreational tools | 3 | — | [docs/concepts/index.md](/concepts/index.md) |
| 57 | `text` | Application information | 8 | — | [docs/concepts/index.md](/concepts/index.md) |
| 58 | `text` | Which average applies | 9 | — | [docs/concepts/kappa2_orientation.md](/concepts/kappa2_orientation.md) |
| 59 | `text` | The burst folder | 5 | — | [docs/concepts/legacy_export.md](/concepts/legacy_export.md) |
| 60 | `text` | Entropy as the criterion | 10 | — | [docs/concepts/maximum_entropy.md](/concepts/maximum_entropy.md) |
| 61 | `json` | File format | 6 | — | [docs/concepts/metadata_editor.md](/concepts/metadata_editor.md) |
| 62 | `text` | Photons do not sample a burst uniformly in time | 1 | — | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 63 | `text` | Doing it in ChiSurf | 7 | — | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 64 | `text` | Doing it in ChiSurf | 3 | — | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 65 | `python` | Doing it in ChiSurf | 9 | compiled | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 66 | `text` | Three properties nothing else has | 6 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 67 | `text` | STICS: track where the peak sits | 5 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 68 | `text` | What limits the arrows | 5 | — | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 69 | `python` | Finding the minimum before describing it | 3 | compiled | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 70 | `python` | One way to ask | 11 | compiled | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 71 | `text` | Why the histogram carries brightness | 4 | — | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 72 | `python` | What ChiSurf writes, and what it only reads | 4 | compiled | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 73 | `python` | Where did this number come from | 4 | compiled | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 74 | `text` | Where did this number come from | 14 | — | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 75 | `text` | Average lifetimes and fractions | 4 | — | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 76 | `text` | Average lifetimes and fractions | 6 | — | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 77 | `text` | In ChiSurf | 6 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 78 | `python` | In ChiSurf | 10 | compiled | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 79 | `text` | In ChiSurf | 11 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 80 | `python` | In ChiSurf | 4 | compiled | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 81 | `text` | Result | 4 | — | [docs/guides/01_fret_2cde.md](/guides/01_fret_2cde.md) |
| 82 | `text` | In the GUI: the same-molecule probability | 8 | — | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 83 | `python` | Headless | 10 | compiled | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 84 | `python` | Headless | 3 | compiled | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 85 | `text` | Result | 4 | — | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 86 | `python` | In ChiSurf | 13 | compiled | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 87 | `text` | In ChiSurf | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 88 | `text` | In ChiSurf | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 89 | `text` | Result | 4 | — | [docs/guides/03_polymer_distance_distributions.md](/guides/03_polymer_distance_distributions.md) |
| 90 | `text` | The PCH tool (classical PCH, not FIDA) | 6 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 91 | `text` | FIDA in the PCH experiment | 7 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 92 | `python` | Headless | 15 | compiled | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 93 | `text` | Result | 4 | — | [docs/guides/04_fida_pch.md](/guides/04_fida_pch.md) |
| 94 | `text` | In the GUI: the FCS model | 9 | — | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 95 | `python` | Headless | 8 | compiled | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 96 | `text` | Result | 4 | — | [docs/guides/05_enderlein_mdf_two_focus_fcs.md](/guides/05_enderlein_mdf_two_focus_fcs.md) |
| 97 | `python` | In ChiSurf | 9 | compiled | [docs/guides/06_nsfcs_second_order.md](/guides/06_nsfcs_second_order.md) |
| 98 | `text` | Result | 4 | — | [docs/guides/06_nsfcs_second_order.md](/guides/06_nsfcs_second_order.md) |
| 99 | `python` | In ChiSurf | 12 | compiled | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 100 | `text` | In ChiSurf | 4 | — | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 101 | `text` | Result | 4 | — | [docs/guides/07_rcm_calibration.md](/guides/07_rcm_calibration.md) |
| 102 | `text` | In ChiSurf | 11 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 103 | `text` | In ChiSurf | 6 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 104 | `python` | Headless | 17 | compiled | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 105 | `text` | Result | 4 | — | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 106 | `text` | In ChiSurf | 10 | — | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 107 | `python` | Headless / scripting | 8 | compiled | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 108 | `text` | Result | 5 | — | [docs/guides/09_diffusion_fcs.md](/guides/09_diffusion_fcs.md) |
| 109 | `text` | 1. Load a file | 7 | — | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 110 | `python` | 5. Excitation regions and multiple lasers | 11 | compiled | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 111 | `bash` | Command line and Python | 2 | — | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 112 | `python` | Command line and Python | 3 | compiled | [docs/guides/100_alex_creator.md](/guides/100_alex_creator.md) |
| 113 | `text` | The photon-data tools and count rates (Tools › Photon data) | 5 | — | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 114 | `text` | Count rates over many files | 5 | — | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 115 | `bash` | Count rates over many files | 2 | — | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 116 | `python` | Count rates over many files | 11 | compiled | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 117 | `bash` | Administering the measurement database: MMFDB Admin | 2 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 118 | `text` | Administering the measurement database: MMFDB Admin | 5 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 119 | `text` | 7. Demo data | 6 | — | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 120 | `python` | Headless and Python | 7 | compiled | [docs/guides/102_mmfdb_admin.md](/guides/102_mmfdb_admin.md) |
| 121 | `text` | Application details for a support request | 4 | — | [docs/guides/103_application_identity.md](/guides/103_application_identity.md) |
| 122 | `python` | Application details for a support request | 5 | compiled | [docs/guides/103_application_identity.md](/guides/103_application_identity.md) |
| 123 | `text` | Light path simulator: crosstalk and R0 of an optical setup | 8 | — | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 124 | `bash` | 5. Headless | 6 | — | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 125 | `python` | 5. Headless | 9 | compiled | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 126 | `bash` | 2. Run it | 1 | — | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 127 | `python` | 3. Python | 13 | compiled | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 128 | `text` | 4. Read the result | 6 | — | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 129 | `text` | 1. HeteroFRET | 5 | — | [docs/guides/107_fret_calculator.md](/guides/107_fret_calculator.md) |
| 130 | `python` | 3. Python | 8 | compiled | [docs/guides/107_fret_calculator.md](/guides/107_fret_calculator.md) |
| 131 | `text` | 1. Open a file | 6 | — | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 132 | `python` | 4. Python | 8 | compiled | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 133 | `python` | 4. Python | 4 | compiled | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 134 | `text` | 0. Make the record | 5 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 135 | `text` | 1. Pick a record and review it | 4 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 136 | `text` | 2. Build and upload | 5 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 137 | `bash` | Terminal | 9 | — | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 138 | `python` | Python | 13 | compiled | [docs/guides/109_zenodo_deposit.md](/guides/109_zenodo_deposit.md) |
| 139 | `text` | In ChiSurf | 9 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 140 | `python` | In ChiSurf | 14 | compiled | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 141 | `text` | Result | 4 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 142 | `text` | VV/VH Anisotropy Decay (deprecated) | 4 | — | [docs/guides/10_lifetime_anisotropy_fitting.md](/guides/10_lifetime_anisotropy_fitting.md) |
| 143 | `text` | Terminal panes: shells and Python side by side | 6 | — | [docs/guides/110_terminal.md](/guides/110_terminal.md) |
| 144 | `text` | 3. Split | 5 | — | [docs/guides/110_terminal.md](/guides/110_terminal.md) |
| 145 | `text` | 1. Load the data | 6 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 146 | `text` | 3. Run | 5 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 147 | `text` | 3. Run | 5 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 148 | `text` | 4. Read the fit | 6 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 149 | `text` | 4. Read the fit | 5 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 150 | `text` | 4. Read the fit | 5 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 151 | `bash` | 5. Headless | 2 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 152 | `bash` | 5. Headless | 4 | — | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 153 | `python` | 5. Headless | 8 | compiled | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 154 | `python` | 5. Headless | 4 | compiled | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 155 | `text` | 1. Read the verdict (simple mode) | 7 | — | [docs/guides/112_fret_check.md](/guides/112_fret_check.md) |
| 156 | `text` | 1. Read the verdict (simple mode) | 5 | — | [docs/guides/112_fret_check.md](/guides/112_fret_check.md) |
| 157 | `text` | 2. Check the detection (advanced mode) | 6 | — | [docs/guides/112_fret_check.md](/guides/112_fret_check.md) |
| 158 | `text` | 2. Check the detection (advanced mode) | 5 | — | [docs/guides/112_fret_check.md](/guides/112_fret_check.md) |
| 159 | `python` | Headless | 10 | compiled | [docs/guides/112_fret_check.md](/guides/112_fret_check.md) |
| 160 | `text` | 1. Pick a schema and open a file | 6 | — | [docs/guides/113_metadata_editor.md](/guides/113_metadata_editor.md) |
| 161 | `text` | 2. Edit and check | 4 | — | [docs/guides/113_metadata_editor.md](/guides/113_metadata_editor.md) |
| 162 | `python` | Python | 8 | compiled | [docs/guides/113_metadata_editor.md](/guides/113_metadata_editor.md) |
| 163 | `text` | 2. Find a moved file | 4 | — | [docs/guides/114_project_data.md](/guides/114_project_data.md) |
| 164 | `text` | 3. Make the project self-contained | 4 | — | [docs/guides/114_project_data.md](/guides/114_project_data.md) |
| 165 | `python` | Headless | 5 | compiled | [docs/guides/114_project_data.md](/guides/114_project_data.md) |
| 166 | `python` | In ChiSurf | 10 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 167 | `text` | Fitting in the GUI | 8 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 168 | `python` | Reading bursts | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 169 | `python` | Fitting a kinetic scheme | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 170 | `python` | Diagnostics | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 171 | `python` | Measuring an exchange rate: several time bins, one rate | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 172 | `text` | Result | 4 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 173 | `python` | One measurement, one file | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 174 | `text` | Converting on drop | 7 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 175 | `python` | Converting on drop | 4 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 176 | `python` | In ChiSurf | 17 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 177 | `python` | In ChiSurf | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 178 | `text` | Result | 4 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 179 | `text` | Open the tool | 7 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 180 | `text` | Open the tool | 10 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 181 | `text` | Open the tool | 5 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 182 | `python` | Headless | 5 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 183 | `python` | Headless | 6 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 184 | `text` | Result | 4 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 185 | `text` | In the GUI: Accurate FRET | 10 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 186 | `python` | Headless | 8 | compiled | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 187 | `text` | Result | 4 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 188 | `text` | In ChiSurf | 8 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 189 | `text` | In ChiSurf | 6 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 190 | `python` | In ChiSurf | 8 | compiled | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 191 | `text` | Result | 4 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 192 | `python` | In ChiSurf | 23 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 193 | `text` | Burst-wise FCS | 8 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 194 | `text` | Burst-wise FCS | 6 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 195 | `python` | Burst-wise FCS | 12 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 196 | `text` | Result | 4 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 197 | `python` | In ChiSurf | 6 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 198 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 199 | `text` | The Filter Calculator | 6 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 200 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 201 | `python` | 2D-FLCS on many molecules, with error bars | 10 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 202 | `bash` | 2D-FLCS on many molecules, with error bars | 2 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 203 | `python` | 2D-FLCS on many molecules, with error bars | 4 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 204 | `text` | Instrument parameters | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 205 | `text` | Result | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 206 | `python` | In ChiSurf | 9 | compiled | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 207 | `text` | The lifetime-FCS simulator | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 208 | `text` | Setting up species and kinetics in the GUI | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 209 | `text` | Result | 4 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 210 | `python` | In ChiSurf | 8 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 211 | `bash` | In ChiSurf | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 212 | `text` | The H2MM tool | 11 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 213 | `python` | Choosing a decoder | 4 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 214 | `bash` | Writing the states back into the photons | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 215 | `text` | Per-state decays | 8 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 216 | `text` | Result | 4 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 217 | `text` | The ebFRET window | 8 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 218 | `python` | Headless | 10 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 219 | `python` | Headless | 4 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 220 | `text` | Result | 6 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 221 | `text` | Extracting patterns from non-burst photons | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 222 | `python` | Extracting patterns from non-burst photons | 16 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 223 | `python` | In ChiSurf | 14 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 224 | `python` | Measured IRF and background, Opt, Save fit | 11 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 225 | `text` | Measured IRF and background, Opt, Save fit | 8 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 226 | `text` | Measured IRF and background, Opt, Save fit | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 227 | `text` | Measured IRF and background, Opt, Save fit | 7 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 228 | `text` | Result | 9 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 229 | `text` | The lifetime of a state, not of a burst | 5 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 230 | `python` | In ChiSurf | 12 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 231 | `text` | Trace Browser | 9 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 232 | `text` | Trace Browser | 6 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 233 | `python` | Trace Browser | 3 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 234 | `text` | Result | 4 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 235 | `python` | In ChiSurf | 13 | compiled | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 236 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 8 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 237 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 238 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 5 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 239 | `text` | Result | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 240 | `python` | In ChiSurf | 8 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 241 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 242 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 243 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 244 | `python` | Selecting pixels | 5 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 245 | `text` | Result | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 246 | `text` | The Intensity tool | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 247 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 248 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 249 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 250 | `python` | In ChiSurf | 10 | compiled | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 251 | `text` | In the Accurate FRET tool | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 252 | `text` | In the Accurate FRET tool | 6 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 253 | `text` | Result | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 254 | `text` | In ChiSurf | 8 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 255 | `python` | In ChiSurf | 9 | compiled | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 256 | `text` | Result | 7 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 257 | `text` | In ChiSurf | 7 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 258 | `text` | In ChiSurf | 8 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 259 | `python` | In ChiSurf | 9 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 260 | `text` | In ChiSurf | 12 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 261 | `python` | In ChiSurf | 17 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 262 | `text` | Result | 4 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 263 | `text` | In ChiSurf | 10 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 264 | `text` | In ChiSurf | 5 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 265 | `python` | In ChiSurf | 14 | compiled | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 266 | `text` | Result | 4 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 267 | `text` | In ChiSurf | 8 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 268 | `python` | In ChiSurf | 14 | compiled | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 269 | `text` | Result | 4 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 270 | `python` | The steps | 20 | compiled | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 271 | `text` | Exploring the dwells | 10 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 272 | `text` | Exploring the dwells | 4 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 273 | `python` | In ChiSurf | 8 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 274 | `python` | In ChiSurf | 17 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 275 | `text` | In ChiSurf | 10 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 276 | `text` | Result | 4 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 277 | `python` | In ChiSurf | 23 | compiled | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 278 | `text` | In ChiSurf | 9 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 279 | `text` | Result | 5 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 280 | `python` | In ChiSurf | 17 | compiled | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 281 | `text` | In ChiSurf | 11 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 282 | `text` | Result | 7 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 283 | `text` | Legacy Export | 7 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 284 | `text` | Legacy Export | 5 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 285 | `bash` | Legacy Export | 5 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 286 | `python` | Legacy Export | 5 | compiled | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 287 | `python` | Legacy Export | 20 | compiled | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 288 | `text` | Result | 14 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 289 | `text` | In ChiSurf | 9 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 290 | `python` | In ChiSurf | 13 | compiled | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 291 | `text` | Result | 4 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 292 | `python` | In ChiSurf | 10 | compiled | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 293 | `text` | Result | 4 | — | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 294 | `text` | Compute a LUT per channel and add it to the setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 295 | `text` | It lands in the detector setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 296 | `bash` | Headless (CLI / API) | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 297 | `python` | Headless (CLI / API) | 6 | compiled | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 298 | `text` | 2. Concepts | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 299 | `text` | 5. Read the results | 6 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 300 | `text` | 9. Punctate signal? Count objects instead | 5 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 301 | `text` | 9. Punctate signal? Count objects instead | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 302 | `text` | 10. Gate a population in the scatter | 7 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 303 | `bash` | Headless / CLI | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 304 | `python` | Python API | 12 | compiled | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 305 | `python` | 1. Fit something | 20 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 306 | `python` | 2. Attach a prior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 307 | `python` | 3. Sample the posterior | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 308 | `python` | 3. Sample the posterior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 309 | `python` | 4. Read the diagnostics before the answer | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 310 | `text` | 4. Read the diagnostics before the answer | 3 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 311 | `python` | 4. Read the diagnostics before the answer | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 312 | `python` | 6. Global fits | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 313 | `python` | 6. Global fits | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 314 | `python` | 7. Linked global fits: use `collapsed` | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 315 | `python` | 8. Inspecting the structure of a global fit | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 316 | `text` | 8. Inspecting the structure of a global fit | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 317 | `text` | The Dependence tab, and why it is not the correlation tab | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 318 | `text` | The Dependence tab, and why it is not the correlation tab | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 319 | `python` | The Dependence tab, and why it is not the correlation tab | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 320 | `python` | 9. Reusing a chain under a different prior | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 321 | `text` | 10. Opening the chains in nDXplorer | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 322 | `python` | 10. Opening the chains in nDXplorer | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 323 | `python` | 11. Looking at the posterior instead of reading about it | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 324 | `text` | 11. Looking at the posterior instead of reading about it | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 325 | `python` | 11. Looking at the posterior instead of reading about it | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 326 | `text` | 12. In the GUI | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 327 | `python` | 12. In the GUI | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 328 | `python` | 13. Asking directly, without picking an estimator first | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 329 | `python` | 14. From a script, a macro or the server | 14 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 330 | `text` | 15. Error bars on the quantities you publish | 7 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 331 | `python` | 15. Error bars on the quantities you publish | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 332 | `python` | 15. Error bars on the quantities you publish | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 333 | `text` | Using it in the GUI | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 334 | `text` | Walkthrough: from bursts to a distance distribution | 8 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 335 | `text` | Walkthrough: from bursts to a distance distribution | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 336 | `bash` | From another chat client (MCP) | 1 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 337 | `bash` | Using it from a terminal | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 338 | `yaml` | Skills: how it knows *how* | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 339 | `markdown` | Writing your own | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 340 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 341 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 342 | `text` | 3. Pick the dyes (and the setup) | 5 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 343 | `python` | 3. Pick the dyes (and the setup) | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 344 | `text` | 6. Calibrate | 15 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 345 | `text` | 7. Read the plots | 7 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 346 | `text` | 7. Read the plots | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 347 | `python` | Keeping a calibration | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 348 | `bash` | Trying it without data (and checking it works) | 1 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 349 | `python` | Trying it without data (and checking it works) | 10 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 350 | `bash` | Head-less | 9 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 351 | `python` | From Python | 21 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 352 | `python` | In the Global View | 7 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 353 | `python` | In the Global View | 6 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 354 | `python` | A worked run against known truth | 25 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 355 | `text` | Fitting a kinetic scheme | 6 | — | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 356 | `python` | Fitting a kinetic scheme | 11 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 357 | `python` | Uncertainties | 5 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 358 | `text` | Measure | 8 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 359 | `text` | Read the result | 5 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 360 | `text` | Read the result | 6 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 361 | `bash` | Headless | 2 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 362 | `text` | Headless | 7 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 363 | `python` | Python | 8 | compiled | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 364 | `text` | The window | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 365 | `text` | Loading and looking | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 366 | `text` | Loading and looking | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 367 | `text` | Integrative (bead) models | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 368 | `text` | Integrative (bead) models | 8 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 369 | `text` | Integrative (bead) models | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 370 | `text` | RMF models from IMP | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 371 | `text` | Whether the camera follows the frame | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 372 | `text` | Whether the camera follows the frame | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 373 | `text` | Choosing a resolution | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 374 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 375 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 376 | `text` | Simulating a map, and fitting a model into one | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 377 | `text` | Simulating a map, and fitting a model into one | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 378 | `text` | The Map panel | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 379 | `text` | Playing a trajectory | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 380 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 381 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 382 | `text` | Crystal symmetry | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 383 | `text` | Making it look good | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 384 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 385 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 386 | `text` | Seeing through a surface | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 387 | `text` | How finely the surface is built | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 388 | `text` | A picture behind the scene, so transparency reads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 389 | `text` | A picture behind the scene, so transparency reads | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 390 | `text` | Clipping, and how to get out of it | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 391 | `text` | Every setting, in the view it changes | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 392 | `text` | How big the chrome draws | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 393 | `text` | Tuning a metaball | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 394 | `text` | Tidying and shielding | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 395 | `text` | Adding hydrogens | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 396 | `text` | Saving a session | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 397 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 398 | `text` | Organising the panel | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 399 | `text` | Organising the panel | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 400 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 401 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 402 | `text` | Organising the panel | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 403 | `text` | Selecting | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 404 | `text` | How far a click spreads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 405 | `text` | Drawing | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 406 | `text` | Drawing | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 407 | `text` | Measuring | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 408 | `text` | Measuring | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 409 | `text` | Measuring by clicking | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 410 | `text` | Polar contacts | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 411 | `text` | Polar contacts | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 412 | `text` | Hydrogen-bond networks | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 413 | `text` | Where two chains touch | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 414 | `text` | Salt bridges, halogen bonds and pi interactions | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 415 | `text` | Clashes | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 416 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 417 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 418 | `text` | The mutagenesis wizard | 15 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 419 | `text` | The mutagenesis wizard | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 420 | `text` | Bonds | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 421 | `text` | Superposing structures | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 422 | `text` | Superposing structures | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 423 | `text` | Superposing structures | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 424 | `text` | Presets — one command to a figure | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 425 | `text` | Side chains that grow out of the ribbon | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 426 | `text` | Colouring by a computed quantity | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 427 | `text` | Colouring by a computed quantity | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 428 | `text` | Showing a quantity as thickness | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 429 | `text` | Showing a quantity as thickness | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 430 | `text` | Getting data in and out | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 431 | `text` | Getting data in and out | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 432 | `text` | Getting data in and out | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 433 | `text` | Exporting the scene as a 3-D model | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 434 | `text` | Images | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 435 | `python` | Headless and scripted use | 17 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 436 | `python` | Headless and scripted use | 11 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 437 | `text` | Open the tool | 8 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 438 | `bash` | Headless | 4 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 439 | `bash` | Launching | 5 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 440 | `python` | ndX in ChiSurf | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 441 | `python` | Lines pushed from another tool | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 442 | `text` | Lines pushed from another tool | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 443 | `text` | Phasor plots are overlays | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 444 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 445 | `text` | Referencing the phasor to the instrument and removing background | 2 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 446 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 447 | `python` | Fitting a constant: moving the data onto the curve | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 448 | `python` | Fitting a constant: moving the data onto the curve | 14 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 449 | `python` | Curves that trace a line rather than evaluate one | 10 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 450 | `python` | Worked example: two smFRET populations and the static FRET line | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 451 | `python` | Worked example: two smFRET populations and the static FRET line | 4 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 452 | `text` | Worked example: two smFRET populations and the static FRET line | 10 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 453 | `text` | Fit 2-D Gaussians to the populations on the map | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 454 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 455 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 456 | `text` | Find the informative projections | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 457 | `python` | Find the informative projections | 9 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 458 | `text` | Session state in the measurement | 3 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 459 | `text` | The workflow | 8 | — | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 460 | `python` | The workflow | 31 | compiled | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 461 | `text` | The region editor | 7 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 462 | `text` | The region editor | 8 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 463 | `text` | The single-molecule imaging workflow | 9 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 464 | `python` | The single-molecule imaging workflow | 2 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 465 | `bash` | Headless | 2 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 466 | `text` | Headless | 4 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 467 | `python` | Python | 28 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 468 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 469 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 470 | `text` | Region MLE: the demo's fit assumptions | 5 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 471 | `text` | Open the tool | 10 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 472 | `text` | Open the tool | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 473 | `text` | The transition-time scan | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 474 | `bash` | Headless | 4 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 475 | `bash` | Headless | 2 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 476 | `text` | Open the tool | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 477 | `text` | 2. Link | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 478 | `bash` | Headless | 4 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 479 | `bash` | Headless | 2 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 480 | `text` | Open the tool | 7 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 481 | `bash` | Headless | 3 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 482 | `text` | Doing it | 7 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 483 | `json` | Advertising another analysis | 13 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 484 | `python` | Headless | 10 | compiled | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 485 | `text` | What counts as a change | 1 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 486 | `text` | What counts as a change | 9 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 487 | `json` | The stamp files | 16 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 488 | `python` | Forcing a recomputation | 3 | compiled | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 489 | `text` | Open the tool | 10 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 490 | `text` | Load a trace | 4 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 491 | `text` | Choose the number of states | 5 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 492 | `text` | Read the result | 7 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 493 | `bash` | Headless | 2 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 494 | `python` | Headless | 26 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 495 | `python` | Headless | 2 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 496 | `text` | The tool | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 497 | `bash` | The tool | 2 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 498 | `python` | The tool | 3 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 499 | `python` | The cheap reading: a pCF curve from a carpet you already have | 12 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 500 | `python` | The real thing: position-resolved pCF | 14 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 501 | `text` | The real thing: position-resolved pCF | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 502 | `python` | A line scan | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 503 | `python` | The arrows: a velocity field | 7 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 504 | `text` | The arrows: a velocity field | 6 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 505 | `python` | The arrows: a velocity field | 6 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 506 | `python` | The second route, for a cross-check | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 507 | `bash` | Regenerating the figures | 1 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 508 | `text` | 4. Read the four outputs | 9 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 509 | `json` | 5. Build your own scheme | 10 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 510 | `bash` | 6. Headless | 8 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 511 | `python` | 7. From the Python API | 12 | compiled | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 512 | `text` | 1. Load the folder | 4 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 513 | `text` | 2. Fit the static model first | 9 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 514 | `text` | 2. Fit the static model first | 7 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 515 | `python` | 5. Headless | 13 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 516 | `python` | 5. Headless | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 517 | `python` | 6. Try it on data whose answer you know | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 518 | `text` | 1. Open the step | 6 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 519 | `text` | 2. Look at the curve before choosing a threshold | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 520 | `text` | 5. Write the fused folder | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 521 | `text` | 5. Write the fused folder | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 522 | `text` | 5. Write the fused folder | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 523 | `bash` | Headless | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 524 | `python` | Headless | 8 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 525 | `python` | Headless | 6 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 526 | `text` | Driving ChiSurf from its console | 5 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 527 | `python` | The first thing to know | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 528 | `text` | The first thing to know | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 529 | `python` | Reading a fit | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 530 | `python` | Reading a fit | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 531 | `text` | Reading a fit | 5 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 532 | `text` | Turning what you did into a script | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 533 | `text` | Long commands and Ctrl+C | 3 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 534 | `python` | Plotting | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 535 | `text` | Plotting | 6 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 536 | `text` | 2. Open the parameter network | 10 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 537 | `text` | 3. Link the shared parameter | 4 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 538 | `text` | 4. Check that the link took effect | 7 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 539 | `python` | Headless: linking two fits | 25 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 540 | `text` | Headless: linking two fits | 2 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 541 | `python` | Headless: linking two fits | 2 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 542 | `python` | Headless: the joint fit | 9 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 543 | `text` | Headless: the joint fit | 1 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 544 | `text` | Step 2 — use your own dyes | 9 | — | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 545 | `python` | Headless | 8 | compiled | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 546 | `text` | Maximum-entropy decay analysis | 4 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 547 | `text` | Maximum-entropy decay analysis | 5 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 548 | `text` | Step 2 — run once, and distrust the answer | 16 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 549 | `python` | Headless | 10 | compiled | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 550 | `text` | How it got there | 11 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 551 | `text` | The settings are the recipe | 13 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 552 | `json` | Opening the tool that made a result | 5 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 553 | `python` | Verifying | 4 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 554 | `bash` | Headless | 7 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 555 | `python` | Headless | 11 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 556 | `python` | Plots | 7 | compiled | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 557 | `text` | The kernel terminal | 4 | — | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 558 | `text` | The Acquisition fit window | 7 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 559 | `python` | The Acquisition fit window | 4 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 560 | `python` | Without a GUI | 25 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 561 | `python` | Without a GUI | 10 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 562 | `text` | The simple workflow | 6 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 563 | `text` | 3 — Alternation, measured rather than typed | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 564 | `text` | Titration | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 565 | `bash` | Export | 1 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 566 | `bash` | Headless | 5 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 567 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 568 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 569 | `bash` | Headless | 1 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 570 | `python` | Headless | 9 | compiled | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 571 | `text` | Asking | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 572 | `bash` | From the command line | 1 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 573 | `text` | From the command line | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 574 | `python` | From Python | 6 | compiled | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 575 | `text` | Open the tool | 8 | — | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 576 | `python` | Headless | 12 | compiled | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 577 | `text` | Generate a decay | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 578 | `text` | Correlate | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 579 | `python` | Headless | 28 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 580 | `python` | Headless | 12 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 581 | `text` | Open the tool | 9 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 582 | `text` | Open a tool | 6 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 583 | `text` | The tools | 4 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 584 | `python` | Headless | 27 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 585 | `python` | Headless | 7 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 586 | `bash` | Headless | 1 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 587 | `bash` | Open the tool | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 588 | `text` | 1. Channel Definitions | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 589 | `text` | 2. Files & Steps | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 590 | `text` | Time regions | 4 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 591 | `text` | 3. Photon / Burst Filter | 8 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 592 | `text` | 4. Correlator | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 593 | `text` | 5. FCS Merger | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 594 | `bash` | The settings file beside every `.cor` | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 595 | `python` | The settings file beside every `.cor` | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 596 | `text` | The settings file beside every `.cor` | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 597 | `bash` | Converting correlation files | 2 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 598 | `python` | Headless | 29 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 599 | `python` | Headless | 6 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 600 | `python` | Headless | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 601 | `text` | Open the tools | 4 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 602 | `text` | Settings | 8 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 603 | `text` | Settings | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 604 | `text` | Reading the output | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 605 | `text` | VV/VH: lifetimes and rotations together | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 606 | `text` | VV/VH: lifetimes and rotations together | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 607 | `bash` | VV/VH: lifetimes and rotations together | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 608 | `python` | VV/VH: lifetimes and rotations together | 5 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 609 | `text` | Synthetic Decay Generator | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 610 | `text` | Synthetic Decay Generator | 7 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 611 | `text` | Synthetic Decay Generator | 5 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 612 | `bash` | Headless | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 613 | `python` | Headless | 22 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 614 | `text` | Open the tool | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 615 | `text` | Set it up | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 616 | `python` | Headless | 13 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 617 | `python` | Headless | 19 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 618 | `text` | Open the tool | 8 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 619 | `text` | 2. Loaded data (optional) | 5 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 620 | `text` | 4. Run | 7 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 621 | `python` | Headless | 23 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 622 | `bash` | Headless | 3 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 623 | `python` | Headless | 27 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 624 | `text` | HydroPro: diffusion coefficients from a structure | 5 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 625 | `text` | Open the tool | 7 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 626 | `text` | Run and read the result | 6 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 627 | `python` | Headless | 10 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 628 | `text` | Headless | 18 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 629 | `python` | Headless | 3 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 630 | `text` | Open the tool | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 631 | `bash` | Headless | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 632 | `python` | Headless | 10 | compiled | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 633 | `text` | Align | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 634 | `text` | Convert | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 635 | `text` | Remove Clashed | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 636 | `text` | Energy Calc | 6 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 637 | `text` | FRET | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 638 | `bash` | FRET | 2 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 639 | `python` | Headless | 33 | compiled | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 640 | `python` | Headless | 10 | compiled | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 641 | `text` | Open the tool | 8 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 642 | `text` | Start with your dye pair | 5 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 643 | `python` | Start with your dye pair | 11 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 644 | `text` | Read the result | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 645 | `text` | Where the lines go next | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 646 | `bash` | Headless | 3 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 647 | `json` | Headless | 9 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 648 | `python` | Headless | 16 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 649 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 650 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 651 | `bash` | 3. Push to the MMFDB | 2 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 652 | `text` | 4. Compute R₀ | 7 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 653 | `python` | 4. Compute R₀ | 8 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 654 | `python` | 6. Headless | 28 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 655 | `bash` | 6. Headless | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 656 | `text` | Narrow windows | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 657 | `text` | 1. Open the tool | 9 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 658 | `text` | 3. A real image | 5 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 659 | `text` | 3. A real image | 6 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 660 | `bash` | 6. Headless | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 661 | `python` | 6. Headless | 10 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 662 | `python` | 6. Headless | 5 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 663 | `text` | Window and bright pixels | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 664 | `text` | 1. Where it is | 6 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 665 | `bash` | 4. Headless | 5 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 666 | `python` | 4. Headless | 17 | compiled | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 667 | `text` | See also | 7 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 668 | `text` | 1. Open the tool | 8 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 669 | `text` | 2. The detector setup | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 670 | `text` | 4. Look at the image | 5 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 671 | `bash` | 7. From the command line and Python | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 672 | `python` | 7. From the command line and Python | 9 | compiled | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 673 | `text` | 1. The page | 7 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 674 | `text` | 2. Typing into a table | 4 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 675 | `python` | 4. From Python | 6 | compiled | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 676 | `text` | 5. Edit the complete working definition | 5 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 677 | `text` | 6. Independent reference calibration | 8 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 678 | `text` | 6. Independent reference calibration | 6 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 679 | `text` | 1. Docking and screening | 4 | — | [docs/guides/88_fret_docking.md](/guides/88_fret_docking.md) |
| 680 | `text` | 1. Open the tool | 9 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 681 | `bash` | Headless | 2 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 682 | `python` | Headless | 5 | compiled | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 683 | `bash` | 1. Open the tool | 1 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 684 | `text` | 1. Open the tool | 9 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 685 | `text` | 3. Detector, channels and gates | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 686 | `python` | Headless | 11 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 687 | `python` | Headless | 13 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 688 | `text` | Timing when comparing earlier results | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 689 | `text` | 1. Open the tool | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 690 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 691 | `text` | 5. Package Manager | 4 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 692 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 693 | `python` | Headless / Python | 2 | compiled | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 694 | `bash` | 1. Open the tool and load the fast reference | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 695 | `text` | 1. Open the tool and load the fast reference | 7 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 696 | `text` | 5. Batch, export, archive | 6 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 697 | `python` | Headless and Python | 9 | compiled | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 698 | `bash` | Headless and Python | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 699 | `text` | 1. Open the tool and load a trace | 8 | — | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 700 | `python` | 4. Save and reuse | 7 | compiled | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 701 | `text` | 1. Open the tool and load a stack | 5 | — | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 702 | `python` | Headless and Python | 4 | compiled | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 703 | `text` | Audifier: photon streams as sound and as a waterfall | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 704 | `text` | Layout and saved preferences | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 705 | `text` | 1. The window | 4 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 706 | `text` | 1. The window | 4 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 707 | `text` | Help, Restart and Guide | 7 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 708 | `python` | 4. Python | 8 | compiled | [docs/guides/95_games.md](/guides/95_games.md) |
| 709 | `text` | 1. Open the tool | 6 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 710 | `text` | 4. Read a failure | 5 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 711 | `bash` | From the command line and from Python | 1 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 712 | `python` | From the command line and from Python | 8 | compiled | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 713 | `text` | 1. The window | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 714 | `text` | 2. The destinations | 4 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 715 | `text` | 2. The destinations | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 716 | `text` | CLSM Simulator: a scan whose answer is known | 4 | — | [docs/guides/98_clsm_generator.md](/guides/98_clsm_generator.md) |
| 717 | `text` | The imaging pipeline in one window (Image Tools) | 6 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 718 | `text` | 1. Open the window | 7 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 719 | `text` | 1. Choose the photons and the detector | 6 | — | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 720 | `python` | The correction | 6 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 721 | `text` | Where the factors come from | 10 | — | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 722 | `python` | 1. Light-path prior → data-optimized posterior | 10 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 723 | `python` | 2. Reference samples (donor-only, acceptor-only) | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 724 | `python` | 3. The donor lifetime and the static FRET line | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 725 | `python` | All three at once | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 726 | `python` | The general case: crosstalk matrices | 13 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 727 | `python` | Naive vs. stable un-mixing | 2 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 728 | `python` | Preserving photon-counting statistics (integer "photon shuffling") | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 729 | `python` | ndxplorer: stable / shuffle un-mixing | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 730 | `python` | Per-pixel / FLIM imaging | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 731 | `python` | Scalar multi-chromophore path | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 732 | `python` | Global analysis and ndxplorer | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 733 | `python` | Global analysis and ndxplorer | 3 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 734 | `text` | Inputs and outputs | 13 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 735 | `text` | GUI | 6 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 736 | `bash` | CLI | 5 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 737 | `python` | Python API | 7 | compiled | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 738 | `text` | Projects and session lifecycle | 3 | — | [docs/guides/index.md](/guides/index.md) |
| 739 | `text` | Photon data and the burst pipeline | 26 | — | [docs/guides/index.md](/guides/index.md) |
| 740 | `text` | smFRET: efficiency, stoichiometry and corrections | 18 | — | [docs/guides/index.md](/guides/index.md) |
| 741 | `text` | Dynamics: distributions, kinetics and hidden states | 18 | — | [docs/guides/index.md](/guides/index.md) |
| 742 | `text` | Fluorescence decays and anisotropy | 8 | — | [docs/guides/index.md](/guides/index.md) |
| 743 | `text` | Correlation spectroscopy | 10 | — | [docs/guides/index.md](/guides/index.md) |
| 744 | `text` | Imaging and microscopy | 19 | — | [docs/guides/index.md](/guides/index.md) |
| 745 | `text` | Structure and modelling | 11 | — | [docs/guides/index.md](/guides/index.md) |
| 746 | `text` | Exploration, simulation and automation | 16 | — | [docs/guides/index.md](/guides/index.md) |
| 747 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 748 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 749 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 750 | `text` | Application and settings | 8 | — | [docs/guides/index.md](/guides/index.md) |
| 751 | `text` | Algorithm Pipeline | 12 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 752 | `text` | In the window | 6 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 753 | `python` | Basic Usage | 11 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 754 | `python` | Step-by-Step Usage | 24 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 755 | `python` | Multi-Channel Data | 7 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 756 | `python` | Visualization | 9 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 757 | `python` | Constructor | 1 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 758 | `text` | Richardson-Lucy Algorithm | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 759 | `bash` | Testing | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 760 | `text` | Saving and reopening projects | 5 | — | [docs/guides/saving_projects.md](/guides/saving_projects.md) |
| 761 | `text` | Adding the membrane-diffusion models | 10 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 762 | `text` | Adding the membrane-diffusion models | 4 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 763 | `text` | Analysis dock | 1 | — | [docs/manual/analysis_dock.md](/manual/analysis_dock.md) |
| 764 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 765 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 766 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 767 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 768 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 769 | `text` | Calculation of co-diffusing molecules | 1 | — | [docs/manual/calculation_of_codiffusing_molecules.md](/manual/calculation_of_codiffusing_molecules.md) |
| 770 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 771 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 772 | `text` | Calculation of the overlap volume and co-diffusion amplitude | 1 | — | [docs/manual/calculations_2.md](/manual/calculations_2.md) |
| 773 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 774 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 775 | `text` | Correction factors for spectral crosstalk & direct acceptor excitation | 1 | — | [docs/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md](/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md) |
| 776 | `text` | Correlation merging | 1 | — | [docs/manual/correlation_merging.md](/manual/correlation_merging.md) |
| 777 | `text` | Correlator | 1 | — | [docs/manual/correlator.md](/manual/correlator.md) |
| 778 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 779 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 780 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 781 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 782 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 783 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 784 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 785 | `text` | Data import | 2 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 786 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 787 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 788 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 789 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 790 | `text` | Data import | 3 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 791 | `text` | Data input and file format | 12 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 792 | `text` | Data input and file format | 5 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 793 | `shell` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 794 | `text` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 795 | `text` | Determination of g-factor and depolarization factors using ChiSurf | 1 | — | [docs/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md](/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md) |
| 796 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 797 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 798 | `text` | Discrete FRET rate constants | 2 | — | [docs/manual/discrete_fret_rate_constants.md](/manual/discrete_fret_rate_constants.md) |
| 799 | `text` | Equation parsing | 1 | — | [docs/manual/equation_parsing.md](/manual/equation_parsing.md) |
| 800 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 801 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 802 | `text` | F-Calculator | 1 | — | [docs/manual/fcalculator.md](/manual/fcalculator.md) |
| 803 | `text` | Fit interface | 1 | — | [docs/manual/fit_interface.md](/manual/fit_interface.md) |
| 804 | `text` | Fit models | 3 | — | [docs/manual/fit_models.md](/manual/fit_models.md) |
| 805 | `text` | Fit of the green-excitation FCS curve | 4 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 806 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 807 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 808 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 809 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 810 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 811 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 812 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 813 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 814 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 815 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 816 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 817 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 818 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 819 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 820 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 821 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 822 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 823 | `text` | Fit of auto- and cross-correlation curves | 1 | — | [docs/manual/fit_of_auto_and_crosscorrelation_curves.md](/manual/fit_of_auto_and_crosscorrelation_curves.md) |
| 824 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 825 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 826 | `text` | Fit of the red-excitation FCS curve | 1 | — | [docs/manual/fit_of_fcs_curve.md](/manual/fit_of_fcs_curve.md) |
| 827 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 828 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 829 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 830 | `text` | Fluorescence Lifetime | 5 | — | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 831 | `text` | Static FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 832 | `text` | Dynamic FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 833 | `text` | Visualizing FRET Lines | 14 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 834 | `text` | Visualizing FRET Lines | 21 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 835 | `text` | Example: Complete Analysis Workflow | 71 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 836 | `text` | Troubleshooting | 3 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 837 | `text` | Example Script | 2 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 838 | `text` | Global fit of auto- and cross-correlation curves | 1 | — | [docs/manual/global_fit_of_auto_and_crosscorrelation_curves.md](/manual/global_fit_of_auto_and_crosscorrelation_curves.md) |
| 839 | `text` | Global fit of FCS curves | 1 | — | [docs/manual/global_fit_of_fcs_curves.md](/manual/global_fit_of_fcs_curves.md) |
| 840 | `text` | Fitting interface & worked examples | 20 | — | [docs/manual/index.md](/manual/index.md) |
| 841 | `text` | Fitting interface & worked examples | 10 | — | [docs/manual/index.md](/manual/index.md) |
| 842 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 843 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 844 | `text` | Fitting interface & worked examples | 7 | — | [docs/manual/index.md](/manual/index.md) |
| 845 | `text` | Fitting interface & worked examples | 23 | — | [docs/manual/index.md](/manual/index.md) |
| 846 | `text` | Fitting interface & worked examples | 9 | — | [docs/manual/index.md](/manual/index.md) |
| 847 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 848 | `text` | Fitting interface & worked examples | 15 | — | [docs/manual/index.md](/manual/index.md) |
| 849 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 850 | `text` | Influence of FRET efficiency | 1 | — | [docs/manual/influence_of_fret_efficiency.md](/manual/influence_of_fret_efficiency.md) |
| 851 | `text` | Influence of triplet blinking | 1 | — | [docs/manual/influence_of_triplet_blinking.md](/manual/influence_of_triplet_blinking.md) |
| 852 | `text` | Introduction | 6 | — | [docs/manual/introduction.md](/manual/introduction.md) |
| 853 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 854 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 855 | `text` | Loading & plotting data | 1 | — | [docs/manual/loading__plotting_data.md](/manual/loading__plotting_data.md) |
| 856 | `text` | Loading and setting up the eGFP data set | 1 | — | [docs/manual/loading_and_setting_up_the_egfp_data_set.md](/manual/loading_and_setting_up_the_egfp_data_set.md) |
| 857 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 858 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 859 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 860 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 861 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 862 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 863 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 864 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 865 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 866 | `text` | Model scores | 2 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 867 | `text` | Model scores | 3 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 868 | `text` | Model scores | 1 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 869 | `text` | Model scoring range | 1 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 870 | `text` | Model scoring range | 2 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 871 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 872 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 873 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 874 | `text` | Arranging the windows | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 875 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 876 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 877 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 878 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 879 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 880 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 881 | `text` | Correlator: overview | 1 | — | [docs/manual/overview_2.md](/manual/overview_2.md) |
| 882 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 883 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 884 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 885 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 886 | `text` | Parameter optimization | 1 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 887 | `text` | Settings | 25 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 888 | `text` | Parameter sampling | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 889 | `text` | Parameter sampling | 1 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 890 | `text` | From the shell | 2 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 891 | `text` | From the shell | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 892 | `text` | Parameter scan | 1 | — | [docs/manual/parameter_scan.md](/manual/parameter_scan.md) |
| 893 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 894 | `text` | Parameters | 8 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 895 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 896 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 897 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 898 | `text` | Parameters | 3 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 899 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 900 | `text` | Partial donor-donor energy migration | 3 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 901 | `text` | Parameters | 5 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 902 | `text` | Reference curves | 1 | — | [docs/manual/reference_curves.md](/manual/reference_curves.md) |
| 903 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 904 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 905 | `text` | Saving & exporting the results | 8 | — | [docs/manual/saving__exporting_the_results.md](/manual/saving__exporting_the_results.md) |
| 906 | `xml` | Saving and loading networks | 14 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 907 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 908 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 909 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 910 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 911 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 912 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 913 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 914 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 915 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 916 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 917 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 918 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 919 | `text` | Step 1: Approximating g-factor with small fluorophore | 1 | — | [docs/manual/step_1_approximating_gfactor_with_small_fluorophore.md](/manual/step_1_approximating_gfactor_with_small_fluorophore.md) |
| 920 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 921 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 922 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 923 | `text` | Two single files | 1 | — | [docs/manual/two_single_files.md](/manual/two_single_files.md) |
| 924 | `text` | VV/VH format | 1 | — | [docs/manual/vv_vh_format.md](/manual/vv_vh_format.md) |
| 925 | `text` | Worm-like chain | 4 | — | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 926 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 927 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 928 | `text` | Usage | 7 | — | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 929 | `python` | Correlation section | 5 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 930 | `python` | Correlation section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 931 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 932 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 933 | `text` | Intensity trace section | 6 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 934 | `python` | Correlation arrays | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 935 | `python` | Intensity arrays | 9 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 936 | `text` | ALV-7004/USB `.asc` (openASC_ALV_7004) | 7 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 937 | `text` | File formats | 4 | — | [docs/reference/file_formats/index.md](/reference/file_formats/index.md) |
| 938 | `python` | Single-file structure reader | 6 | compiled | [docs/reference/file_formats/structure_files.md](/reference/file_formats/structure_files.md) |
| 939 | `python` | Workflow | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 940 | `python` | Becker-SDT | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 941 | `python` | Preview and Add | 7 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 942 | `text` | Reference | 12 | — | [docs/reference/index.md](/reference/index.md) |
| 943 | `bash` | Local (primitive) | 10 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 944 | `bash` | MMFDB round trip | 13 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 945 | `bash` | Local (primitive) | 4 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 946 | `bash` | Local (primitive) | 3 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 947 | `bash` | MMFDB round trip | 7 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 948 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 949 | `python` | From a script | 9 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 950 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 951 | `python` | Saving a single parameter | 7 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 952 | `text` | Plugin catalogue | 4 | — | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 953 | `yaml` | 3. `settings_colors.yaml` (global color palette) | 3 | — | [docs/reference/settings.md](/reference/settings.md) |
| 954 | `python` | User-Defined Models in ChiSurf | 2 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 955 | `python` | 1.1 Write the model | 21 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 956 | `yaml` | 1.3 List it in `experiment_configs.yaml` | 3 | — | [docs/reference/user_models.md](/reference/user_models.md) |
| 957 | `python` | 3. Turning a plain function into a model | 7 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
