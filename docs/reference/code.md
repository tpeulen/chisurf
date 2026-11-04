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

*976 blocks, 244 Python, 0 executed.*

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
| 49 | `text` | Single-molecule FRET (bursts) | 14 | — | [docs/concepts/index.md](/concepts/index.md) |
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
| 166 | `text` | 1. Check a setup against a measurement (Excitation Windows) | 8 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 167 | `text` | 1. Check a setup against a measurement (Excitation Windows) | 5 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 168 | `text` | 2. In the setup editor: Auto-detect | 3 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 169 | `text` | 3. During a Record run | 4 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 170 | `text` | 3. During a Record run | 6 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 171 | `text` | 4. Before burst selection | 4 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 172 | `bash` | 6. Headless: `csc windows` | 4 | — | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 173 | `python` | 7. Python | 19 | compiled | [docs/guides/115_excitation_windows.md](/guides/115_excitation_windows.md) |
| 174 | `python` | In ChiSurf | 10 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 175 | `text` | Fitting in the GUI | 8 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 176 | `python` | Reading bursts | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 177 | `python` | Fitting a kinetic scheme | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 178 | `python` | Diagnostics | 6 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 179 | `python` | Measuring an exchange rate: several time bins, one rate | 9 | compiled | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 180 | `text` | Result | 4 | — | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 181 | `python` | One measurement, one file | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 182 | `text` | Converting on drop | 7 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 183 | `python` | Converting on drop | 4 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 184 | `python` | In ChiSurf | 17 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 185 | `python` | In ChiSurf | 7 | compiled | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 186 | `text` | Result | 4 | — | [docs/guides/12_handling_tttr_files.md](/guides/12_handling_tttr_files.md) |
| 187 | `text` | Open the tool | 7 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 188 | `text` | Open the tool | 10 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 189 | `text` | Open the tool | 5 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 190 | `python` | Headless | 5 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 191 | `python` | Headless | 6 | compiled | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 192 | `text` | Result | 4 | — | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 193 | `text` | In the GUI: Accurate FRET | 10 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 194 | `python` | Headless | 8 | compiled | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 195 | `text` | Result | 4 | — | [docs/guides/14_multiparameter_es.md](/guides/14_multiparameter_es.md) |
| 196 | `text` | In ChiSurf | 8 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 197 | `text` | In ChiSurf | 6 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 198 | `python` | In ChiSurf | 8 | compiled | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 199 | `text` | Result | 4 | — | [docs/guides/15_background_rates.md](/guides/15_background_rates.md) |
| 200 | `python` | In ChiSurf | 23 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 201 | `text` | Burst-wise FCS | 8 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 202 | `text` | Burst-wise FCS | 6 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 203 | `python` | Burst-wise FCS | 12 | compiled | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 204 | `text` | Result | 4 | — | [docs/guides/16_fret_fcs.md](/guides/16_fret_fcs.md) |
| 205 | `python` | In ChiSurf | 6 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 206 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 207 | `text` | The Filter Calculator | 6 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 208 | `text` | The Filter Calculator | 5 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 209 | `python` | 2D-FLCS on many molecules, with error bars | 10 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 210 | `bash` | 2D-FLCS on many molecules, with error bars | 2 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 211 | `python` | 2D-FLCS on many molecules, with error bars | 4 | compiled | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 212 | `text` | Instrument parameters | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 213 | `text` | Result | 4 | — | [docs/guides/17_filtered_fcs.md](/guides/17_filtered_fcs.md) |
| 214 | `python` | In ChiSurf | 9 | compiled | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 215 | `text` | The lifetime-FCS simulator | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 216 | `text` | Setting up species and kinetics in the GUI | 6 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 217 | `text` | Result | 4 | — | [docs/guides/18_tttr_simulation.md](/guides/18_tttr_simulation.md) |
| 218 | `python` | In ChiSurf | 8 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 219 | `bash` | In ChiSurf | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 220 | `text` | The H2MM tool | 11 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 221 | `python` | Choosing a decoder | 4 | compiled | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 222 | `bash` | Writing the states back into the photons | 1 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 223 | `text` | Per-state decays | 8 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 224 | `text` | Result | 4 | — | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 225 | `text` | The ebFRET window | 8 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 226 | `python` | Headless | 10 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 227 | `python` | Headless | 4 | compiled | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 228 | `text` | Result | 6 | — | [docs/guides/20_ebfret_binned_hmm.md](/guides/20_ebfret_binned_hmm.md) |
| 229 | `text` | Extracting patterns from non-burst photons | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 230 | `python` | Extracting patterns from non-burst photons | 16 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 231 | `python` | In ChiSurf | 14 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 232 | `python` | Measured IRF, buffer, Opt, Save fit | 11 | compiled | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 233 | `text` | Measured IRF, buffer, Opt, Save fit | 8 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 234 | `text` | Measured IRF, buffer, Opt, Save fit | 6 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 235 | `text` | Measured IRF, buffer, Opt, Save fit | 7 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 236 | `text` | Result | 9 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 237 | `text` | The lifetime of a state, not of a burst | 5 | — | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 238 | `python` | In ChiSurf | 12 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 239 | `text` | Trace Browser | 9 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 240 | `text` | Trace Browser | 6 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 241 | `python` | Trace Browser | 3 | compiled | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 242 | `text` | Result | 4 | — | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 243 | `python` | In ChiSurf | 13 | compiled | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 244 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 8 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 245 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 246 | `text` | The FPS JSON editor (ChiMOL's labelling window) | 5 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 247 | `text` | Result | 4 | — | [docs/guides/23_accessible_volume.md](/guides/23_accessible_volume.md) |
| 248 | `python` | In ChiSurf | 8 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 249 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 250 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 251 | `text` | Selecting pixels | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 252 | `python` | Selecting pixels | 5 | compiled | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 253 | `text` | Result | 6 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 254 | `text` | The Intensity tool | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 255 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 256 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 257 | `text` | Mean micro-time, phasor and pixel-wise MLE | 3 | — | [docs/guides/24_scan_images.md](/guides/24_scan_images.md) |
| 258 | `python` | In ChiSurf | 10 | compiled | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 259 | `text` | In the Accurate FRET tool | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 260 | `text` | In the Accurate FRET tool | 6 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 261 | `text` | Result | 8 | — | [docs/guides/25_rcm_from_fret_samples.md](/guides/25_rcm_from_fret_samples.md) |
| 262 | `text` | In ChiSurf | 8 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 263 | `python` | In ChiSurf | 9 | compiled | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 264 | `text` | Result | 7 | — | [docs/guides/26_2d_peak_fitting.md](/guides/26_2d_peak_fitting.md) |
| 265 | `text` | In ChiSurf | 7 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 266 | `text` | In ChiSurf | 8 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 267 | `python` | In ChiSurf | 9 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 268 | `text` | In ChiSurf | 12 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 269 | `python` | In ChiSurf | 17 | compiled | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 270 | `text` | Result | 4 | — | [docs/guides/27_alex_smfret_workflow.md](/guides/27_alex_smfret_workflow.md) |
| 271 | `text` | In ChiSurf | 10 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 272 | `text` | In ChiSurf | 5 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 273 | `python` | In ChiSurf | 14 | compiled | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 274 | `text` | Result | 4 | — | [docs/guides/28_selecting_fret_populations.md](/guides/28_selecting_fret_populations.md) |
| 275 | `text` | In ChiSurf | 8 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 276 | `python` | In ChiSurf | 14 | compiled | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 277 | `text` | Result | 4 | — | [docs/guides/29_fret_histogram_fitting.md](/guides/29_fret_histogram_fitting.md) |
| 278 | `python` | The steps | 20 | compiled | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 279 | `text` | Exploring the dwells | 10 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 280 | `text` | Exploring the dwells | 4 | — | [docs/guides/30_h2mm_workflow_results.md](/guides/30_h2mm_workflow_results.md) |
| 281 | `python` | In ChiSurf | 8 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 282 | `python` | In ChiSurf | 17 | compiled | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 283 | `text` | In ChiSurf | 10 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 284 | `text` | Result | 4 | — | [docs/guides/31_h2mm_simulation_validation.md](/guides/31_h2mm_simulation_validation.md) |
| 285 | `python` | In ChiSurf | 23 | compiled | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 286 | `text` | In ChiSurf | 9 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 287 | `text` | Result | 5 | — | [docs/guides/32_nsalex_lifetime.md](/guides/32_nsalex_lifetime.md) |
| 288 | `python` | In ChiSurf | 17 | compiled | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 289 | `text` | In ChiSurf | 11 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 290 | `text` | Result | 7 | — | [docs/guides/33_timestamps_and_bursts.md](/guides/33_timestamps_and_bursts.md) |
| 291 | `text` | Legacy Export | 7 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 292 | `text` | Legacy Export | 5 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 293 | `bash` | Legacy Export | 5 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 294 | `python` | Legacy Export | 5 | compiled | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 295 | `python` | Legacy Export | 20 | compiled | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 296 | `text` | Result | 14 | — | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 297 | `text` | In ChiSurf | 9 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 298 | `python` | In ChiSurf | 13 | compiled | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 299 | `text` | Result | 4 | — | [docs/guides/35_combining_repeats.md](/guides/35_combining_repeats.md) |
| 300 | `python` | In ChiSurf | 10 | compiled | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 301 | `text` | Result | 4 | — | [docs/guides/36_multispot.md](/guides/36_multispot.md) |
| 302 | `text` | Compute a LUT per channel and add it to the setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 303 | `text` | It lands in the detector setup | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 304 | `bash` | Headless (CLI / API) | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 305 | `python` | Headless (CLI / API) | 6 | compiled | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 306 | `text` | 2. Concepts | 4 | — | [docs/guides/37_tttr_microtime_lut.md](/guides/37_tttr_microtime_lut.md) |
| 307 | `text` | 5. Read the results | 6 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 308 | `text` | 9. Punctate signal? Count objects instead | 5 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 309 | `text` | 9. Punctate signal? Count objects instead | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 310 | `text` | 10. Gate a population in the scatter | 7 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 311 | `bash` | Headless / CLI | 4 | — | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 312 | `python` | Python API | 12 | compiled | [docs/guides/38_colocalization.md](/guides/38_colocalization.md) |
| 313 | `python` | 1. Fit something | 20 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 314 | `python` | 2. Attach a prior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 315 | `python` | 3. Sample the posterior | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 316 | `python` | 3. Sample the posterior | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 317 | `python` | 4. Read the diagnostics before the answer | 6 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 318 | `text` | 4. Read the diagnostics before the answer | 3 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 319 | `python` | 4. Read the diagnostics before the answer | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 320 | `python` | 6. Global fits | 8 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 321 | `python` | 6. Global fits | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 322 | `python` | 7. Linked global fits: use `collapsed` | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 323 | `python` | 8. Inspecting the structure of a global fit | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 324 | `text` | 8. Inspecting the structure of a global fit | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 325 | `text` | The Dependence tab, and why it is not the correlation tab | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 326 | `text` | The Dependence tab, and why it is not the correlation tab | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 327 | `python` | The Dependence tab, and why it is not the correlation tab | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 328 | `python` | 9. Reusing a chain under a different prior | 10 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 329 | `text` | 10. Opening the chains in nDXplorer | 4 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 330 | `python` | 10. Opening the chains in nDXplorer | 4 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 331 | `python` | 11. Looking at the posterior instead of reading about it | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 332 | `text` | 11. Looking at the posterior instead of reading about it | 5 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 333 | `python` | 11. Looking at the posterior instead of reading about it | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 334 | `text` | 12. In the GUI | 6 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 335 | `python` | 12. In the GUI | 5 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 336 | `python` | 13. Asking directly, without picking an estimator first | 9 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 337 | `python` | 14. From a script, a macro or the server | 14 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 338 | `text` | 15. Error bars on the quantities you publish | 7 | — | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 339 | `python` | 15. Error bars on the quantities you publish | 2 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 340 | `python` | 15. Error bars on the quantities you publish | 1 | compiled | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 341 | `bash` | Setting it up | 3 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 342 | `text` | Using it in the GUI | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 343 | `text` | Walkthrough: from bursts to a distance distribution | 8 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 344 | `text` | Walkthrough: from bursts to a distance distribution | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 345 | `bash` | From another chat client (MCP) | 1 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 346 | `bash` | Using it from a terminal | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 347 | `yaml` | Skills: how it knows *how* | 6 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 348 | `markdown` | Writing your own | 13 | — | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 349 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 350 | `text` | What it does | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 351 | `text` | 3. Pick the dyes (and the setup) | 5 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 352 | `python` | 3. Pick the dyes (and the setup) | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 353 | `text` | 6. Calibrate | 15 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 354 | `text` | 7. Read the plots | 7 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 355 | `text` | 7. Read the plots | 8 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 356 | `python` | Keeping a calibration | 5 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 357 | `bash` | Trying it without data (and checking it works) | 1 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 358 | `python` | Trying it without data (and checking it works) | 10 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 359 | `bash` | Head-less | 9 | — | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 360 | `python` | From Python | 21 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 361 | `python` | In the Global View | 7 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 362 | `python` | In the Global View | 6 | compiled | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 363 | `python` | A worked run against known truth | 25 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 364 | `text` | Fitting a kinetic scheme | 6 | — | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 365 | `python` | Fitting a kinetic scheme | 11 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 366 | `python` | Uncertainties | 5 | compiled | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 367 | `text` | Measure | 8 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 368 | `text` | Read the result | 5 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 369 | `text` | Read the result | 6 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 370 | `bash` | Headless | 2 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 371 | `text` | Headless | 7 | — | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 372 | `python` | Python | 8 | compiled | [docs/guides/43_drift_correction.md](/guides/43_drift_correction.md) |
| 373 | `text` | The window | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 374 | `text` | Loading and looking | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 375 | `text` | Loading and looking | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 376 | `text` | Integrative (bead) models | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 377 | `text` | Integrative (bead) models | 8 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 378 | `text` | Integrative (bead) models | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 379 | `text` | RMF models from IMP | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 380 | `text` | Whether the camera follows the frame | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 381 | `text` | Whether the camera follows the frame | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 382 | `text` | Choosing a resolution | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 383 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 384 | `text` | Voxel maps | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 385 | `text` | Simulating a map, and fitting a model into one | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 386 | `text` | Simulating a map, and fitting a model into one | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 387 | `text` | The Map panel | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 388 | `text` | Playing a trajectory | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 389 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 390 | `text` | Trajectories and holding part of a structure still | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 391 | `text` | Crystal symmetry | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 392 | `text` | Making it look good | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 393 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 394 | `text` | Making it look good | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 395 | `text` | Seeing through a surface | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 396 | `text` | How finely the surface is built | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 397 | `text` | A picture behind the scene, so transparency reads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 398 | `text` | A picture behind the scene, so transparency reads | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 399 | `text` | Clipping, and how to get out of it | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 400 | `text` | Every setting, in the view it changes | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 401 | `text` | How big the chrome draws | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 402 | `text` | Tuning a metaball | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 403 | `text` | Tidying and shielding | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 404 | `text` | Adding hydrogens | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 405 | `text` | Saving a session | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 406 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 407 | `text` | Organising the panel | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 408 | `text` | Organising the panel | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 409 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 410 | `text` | Organising the panel | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 411 | `text` | Organising the panel | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 412 | `text` | Selecting | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 413 | `text` | How far a click spreads | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 414 | `text` | Drawing | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 415 | `text` | Drawing | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 416 | `text` | Measuring | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 417 | `text` | Measuring | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 418 | `text` | Measuring by clicking | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 419 | `text` | Polar contacts | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 420 | `text` | Polar contacts | 6 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 421 | `text` | Hydrogen-bond networks | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 422 | `text` | Where two chains touch | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 423 | `text` | Salt bridges, halogen bonds and pi interactions | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 424 | `text` | Clashes | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 425 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 426 | `text` | Mutating a residue | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 427 | `text` | The mutagenesis wizard | 15 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 428 | `text` | The mutagenesis wizard | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 429 | `text` | Bonds | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 430 | `text` | Superposing structures | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 431 | `text` | Superposing structures | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 432 | `text` | Superposing structures | 2 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 433 | `text` | Presets — one command to a figure | 9 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 434 | `text` | Side chains that grow out of the ribbon | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 435 | `text` | Colouring by a computed quantity | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 436 | `text` | Colouring by a computed quantity | 7 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 437 | `text` | Showing a quantity as thickness | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 438 | `text` | Showing a quantity as thickness | 5 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 439 | `text` | Getting data in and out | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 440 | `text` | Getting data in and out | 1 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 441 | `text` | Getting data in and out | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 442 | `text` | Exporting the scene as a 3-D model | 3 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 443 | `text` | Images | 4 | — | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 444 | `python` | Headless and scripted use | 17 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 445 | `python` | Headless and scripted use | 11 | compiled | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 446 | `text` | Open the tool | 8 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 447 | `bash` | Headless | 4 | — | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 448 | `bash` | Launching | 5 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 449 | `python` | ndX in ChiSurf | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 450 | `python` | Lines pushed from another tool | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 451 | `text` | Lines pushed from another tool | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 452 | `text` | Phasor plots are overlays | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 453 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 454 | `text` | Referencing the phasor to the instrument and removing background | 2 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 455 | `text` | Referencing the phasor to the instrument and removing background | 4 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 456 | `python` | Fitting a constant: moving the data onto the curve | 7 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 457 | `python` | Fitting a constant: moving the data onto the curve | 14 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 458 | `python` | Curves that trace a line rather than evaluate one | 10 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 459 | `python` | Worked example: two smFRET populations and the static FRET line | 5 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 460 | `python` | Worked example: two smFRET populations and the static FRET line | 4 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 461 | `text` | Worked example: two smFRET populations and the static FRET line | 10 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 462 | `text` | Fit 2-D Gaussians to the populations on the map | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 463 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 464 | `text` | Population-wise parameters: one value per population | 6 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 465 | `text` | Find the informative projections | 7 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 466 | `python` | Find the informative projections | 9 | compiled | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 467 | `text` | Session state in the measurement | 3 | — | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 468 | `text` | The workflow | 8 | — | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 469 | `python` | The workflow | 31 | compiled | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 470 | `text` | The region editor | 7 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 471 | `text` | The region editor | 8 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 472 | `text` | The single-molecule imaging workflow | 9 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 473 | `python` | The single-molecule imaging workflow | 2 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 474 | `bash` | Headless | 2 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 475 | `text` | Headless | 4 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 476 | `python` | Python | 28 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 477 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 478 | `python` | Python | 13 | compiled | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 479 | `text` | Region MLE: the demo's fit assumptions | 5 | — | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 480 | `text` | Open the tool | 10 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 481 | `text` | Open the tool | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 482 | `text` | The transition-time scan | 9 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 483 | `bash` | Headless | 4 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 484 | `bash` | Headless | 2 | — | [docs/guides/49_photon_by_photon_kinetics.md](/guides/49_photon_by_photon_kinetics.md) |
| 485 | `text` | Open the tool | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 486 | `text` | 2. Link | 8 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 487 | `bash` | Headless | 4 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 488 | `bash` | Headless | 2 | — | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 489 | `text` | Open the tool | 7 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 490 | `bash` | Headless | 3 | — | [docs/guides/51_frc_resolution.md](/guides/51_frc_resolution.md) |
| 491 | `text` | Doing it | 7 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 492 | `json` | Advertising another analysis | 13 | — | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 493 | `python` | Headless | 10 | compiled | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 494 | `text` | What counts as a change | 1 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 495 | `text` | What counts as a change | 9 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 496 | `json` | The stamp files | 16 | — | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 497 | `python` | Forcing a recomputation | 3 | compiled | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 498 | `text` | Open the tool | 10 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 499 | `text` | Load a trace | 4 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 500 | `text` | Choose the number of states | 5 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 501 | `text` | Read the result | 7 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 502 | `bash` | Headless | 2 | — | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 503 | `python` | Headless | 26 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 504 | `python` | Headless | 2 | compiled | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 505 | `text` | The tool | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 506 | `bash` | The tool | 2 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 507 | `python` | The tool | 3 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 508 | `python` | The cheap reading: a pCF curve from a carpet you already have | 12 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 509 | `python` | The real thing: position-resolved pCF | 14 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 510 | `text` | The real thing: position-resolved pCF | 8 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 511 | `python` | A line scan | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 512 | `python` | The arrows: a velocity field | 7 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 513 | `text` | The arrows: a velocity field | 6 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 514 | `python` | The arrows: a velocity field | 6 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 515 | `python` | The second route, for a cross-check | 4 | compiled | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 516 | `bash` | Regenerating the figures | 1 | — | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 517 | `text` | 4. Read the four outputs | 9 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 518 | `json` | 5. Build your own scheme | 10 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 519 | `bash` | 6. Headless | 8 | — | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 520 | `python` | 7. From the Python API | 12 | compiled | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 521 | `text` | 1. Load the folder | 4 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 522 | `text` | 2. Fit the static model first | 9 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 523 | `text` | 2. Fit the static model first | 7 | — | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 524 | `python` | 5. Headless | 13 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 525 | `python` | 5. Headless | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 526 | `python` | 6. Try it on data whose answer you know | 10 | compiled | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 527 | `text` | 1. Open the step | 6 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 528 | `text` | 2. Look at the curve before choosing a threshold | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 529 | `text` | 5. Write the fused run | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 530 | `text` | 5. Write the fused run | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 531 | `text` | 5. Write the fused run | 4 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 532 | `bash` | Headless | 5 | — | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 533 | `python` | Headless | 14 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 534 | `python` | Headless | 6 | compiled | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 535 | `text` | Driving ChiSurf from its console | 5 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 536 | `python` | The first thing to know | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 537 | `text` | The first thing to know | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 538 | `python` | Reading a fit | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 539 | `python` | Reading a fit | 1 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 540 | `text` | Reading a fit | 5 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 541 | `text` | Turning what you did into a script | 1 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 542 | `text` | Long commands and Ctrl+C | 3 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 543 | `python` | Plotting | 3 | compiled | [docs/guides/59_console.md](/guides/59_console.md) |
| 544 | `text` | Plotting | 6 | — | [docs/guides/59_console.md](/guides/59_console.md) |
| 545 | `text` | 2. Open the parameter network | 10 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 546 | `text` | 3. Link the shared parameter | 4 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 547 | `text` | 4. Check that the link took effect | 7 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 548 | `python` | Headless: linking two fits | 25 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 549 | `text` | Headless: linking two fits | 2 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 550 | `python` | Headless: linking two fits | 2 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 551 | `python` | Headless: the joint fit | 9 | compiled | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 552 | `text` | Headless: the joint fit | 1 | — | [docs/guides/60_global_analysis.md](/guides/60_global_analysis.md) |
| 553 | `text` | Step 2 — use your own dyes | 9 | — | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 554 | `python` | Headless | 8 | compiled | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 555 | `text` | Maximum-entropy decay analysis | 4 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 556 | `text` | Maximum-entropy decay analysis | 5 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 557 | `text` | Step 2 — run once, and distrust the answer | 16 | — | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 558 | `python` | Headless | 10 | compiled | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 559 | `text` | How it got there | 11 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 560 | `text` | The settings are the recipe | 13 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 561 | `json` | Opening the tool that made a result | 5 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 562 | `python` | Verifying | 4 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 563 | `bash` | Headless | 7 | — | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 564 | `python` | Headless | 11 | compiled | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 565 | `python` | Plots | 7 | compiled | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 566 | `text` | The kernel terminal | 4 | — | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 567 | `text` | Devices: phacq | 5 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 568 | `text` | Devices: phacq | 5 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 569 | `json` | Imaging, picking molecules, measuring them point by point | 3 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 570 | `text` | Imaging, picking molecules, measuring them point by point | 5 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 571 | `text` | Imaging, picking molecules, measuring them point by point | 5 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 572 | `text` | Imaging, picking molecules, measuring them point by point | 5 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 573 | `python` | Imaging, picking molecules, measuring them point by point | 13 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 574 | `text` | Survey: a larger area, automatically | 7 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 575 | `text` | Survey: a larger area, automatically | 4 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 576 | `python` | Provenance: from a point back to its image and survey, and forward | 6 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 577 | `text` | The Acquisition fit window | 7 | — | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 578 | `python` | The Acquisition fit window | 4 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 579 | `python` | Without a GUI | 25 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 580 | `python` | Without a GUI | 10 | compiled | [docs/guides/65_live_acquisition.md](/guides/65_live_acquisition.md) |
| 581 | `text` | The simple workflow | 6 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 582 | `text` | 3 — Alternation, measured rather than typed | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 583 | `text` | Titration | 9 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 584 | `bash` | Export | 1 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 585 | `bash` | Headless | 5 | — | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 586 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 587 | `text` | Try it on data whose answer is known | 4 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 588 | `bash` | Headless | 1 | — | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 589 | `python` | Headless | 9 | compiled | [docs/guides/67_number_and_brightness.md](/guides/67_number_and_brightness.md) |
| 590 | `text` | Asking | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 591 | `bash` | From the command line | 1 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 592 | `text` | From the command line | 7 | — | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 593 | `python` | From Python | 6 | compiled | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 594 | `text` | Open the tool | 8 | — | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 595 | `python` | Headless | 12 | compiled | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 596 | `text` | Generate a decay | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 597 | `text` | Correlate | 7 | — | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 598 | `python` | Headless | 28 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 599 | `python` | Headless | 12 | compiled | [docs/guides/73_tttr_decay_and_correlation.md](/guides/73_tttr_decay_and_correlation.md) |
| 600 | `text` | Open the tool | 9 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 601 | `text` | Open a tool | 6 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 602 | `text` | The tools | 4 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 603 | `python` | Headless | 27 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 604 | `python` | Headless | 7 | compiled | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 605 | `bash` | Headless | 1 | — | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 606 | `bash` | Open the tool | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 607 | `text` | 1. Channel Definitions | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 608 | `text` | 2. Files & Steps | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 609 | `text` | Time regions | 4 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 610 | `text` | 3. Photon / Burst Filter | 8 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 611 | `text` | 4. Correlator | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 612 | `text` | 5. FCS Merger | 6 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 613 | `bash` | The settings file beside every `.cor` | 1 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 614 | `python` | The settings file beside every `.cor` | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 615 | `text` | The settings file beside every `.cor` | 5 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 616 | `bash` | Converting correlation files | 2 | — | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 617 | `python` | Headless | 29 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 618 | `python` | Headless | 6 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 619 | `python` | Headless | 3 | compiled | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 620 | `text` | Open the tools | 4 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 621 | `text` | Settings | 8 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 622 | `text` | Settings | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 623 | `text` | Reading the output | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 624 | `text` | VV/VH: lifetimes and rotations together | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 625 | `text` | VV/VH: lifetimes and rotations together | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 626 | `bash` | VV/VH: lifetimes and rotations together | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 627 | `python` | VV/VH: lifetimes and rotations together | 5 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 628 | `text` | Synthetic Decay Generator | 6 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 629 | `text` | Synthetic Decay Generator | 7 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 630 | `text` | Synthetic Decay Generator | 5 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 631 | `bash` | Headless | 9 | — | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 632 | `python` | Headless | 22 | compiled | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 633 | `text` | Open the tool | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 634 | `text` | Set it up | 8 | — | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 635 | `python` | Headless | 13 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 636 | `python` | Headless | 19 | compiled | [docs/guides/77_phasor_calculator.md](/guides/77_phasor_calculator.md) |
| 637 | `text` | Open the tool | 8 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 638 | `text` | 2. Loaded data (optional) | 5 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 639 | `text` | 4. Run | 7 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 640 | `python` | Headless | 23 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 641 | `bash` | Headless | 3 | — | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 642 | `python` | Headless | 27 | compiled | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 643 | `text` | HydroPro: diffusion coefficients from a structure | 5 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 644 | `text` | Open the tool | 7 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 645 | `text` | Run and read the result | 6 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 646 | `python` | Headless | 10 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 647 | `text` | Headless | 18 | — | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 648 | `python` | Headless | 3 | compiled | [docs/guides/79_hydropro.md](/guides/79_hydropro.md) |
| 649 | `text` | Open the tool | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 650 | `bash` | Headless | 6 | — | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 651 | `python` | Headless | 10 | compiled | [docs/guides/80_quenching_estimator.md](/guides/80_quenching_estimator.md) |
| 652 | `text` | Align | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 653 | `text` | Convert | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 654 | `text` | Remove Clashed | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 655 | `text` | Energy Calc | 6 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 656 | `text` | FRET | 5 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 657 | `bash` | FRET | 2 | — | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 658 | `python` | Headless | 33 | compiled | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 659 | `python` | Headless | 10 | compiled | [docs/guides/81_trajectory_tools.md](/guides/81_trajectory_tools.md) |
| 660 | `text` | Open the tool | 8 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 661 | `text` | Start with your dye pair | 5 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 662 | `python` | Start with your dye pair | 11 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 663 | `text` | Read the result | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 664 | `text` | Where the lines go next | 4 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 665 | `bash` | Headless | 3 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 666 | `json` | Headless | 9 | — | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 667 | `python` | Headless | 16 | compiled | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 668 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 669 | `text` | 1. Open the Spectra Downloader | 4 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 670 | `bash` | 3. Push to the MMFDB | 2 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 671 | `text` | 4. Compute R₀ | 7 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 672 | `python` | 4. Compute R₀ | 8 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 673 | `python` | 6. Headless | 28 | compiled | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 674 | `bash` | 6. Headless | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 675 | `text` | Narrow windows | 5 | — | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 676 | `text` | 1. Open the tool | 9 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 677 | `text` | 3. A real image | 5 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 678 | `text` | 3. A real image | 6 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 679 | `bash` | 6. Headless | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 680 | `python` | 6. Headless | 10 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 681 | `python` | 6. Headless | 5 | compiled | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 682 | `text` | Window and bright pixels | 4 | — | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 683 | `text` | 1. Where it is | 6 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 684 | `bash` | 4. Headless | 5 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 685 | `python` | 4. Headless | 17 | compiled | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 686 | `text` | See also | 7 | — | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 687 | `text` | 1. Open the tool | 8 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 688 | `text` | 2. The detector setup | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 689 | `text` | 4. Look at the image | 5 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 690 | `bash` | 7. From the command line and Python | 4 | — | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 691 | `python` | 7. From the command line and Python | 9 | compiled | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 692 | `text` | 1. The page | 7 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 693 | `text` | 2. Typing into a table | 4 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 694 | `python` | 4. From Python | 6 | compiled | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 695 | `text` | 5. Edit the complete working definition | 5 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 696 | `text` | 6. Independent reference calibration | 8 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 697 | `text` | 6. Independent reference calibration | 6 | — | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 698 | `text` | 1. Docking and screening | 4 | — | [docs/guides/88_fret_docking.md](/guides/88_fret_docking.md) |
| 699 | `text` | 1. Open the tool | 9 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 700 | `bash` | Headless | 2 | — | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 701 | `python` | Headless | 5 | compiled | [docs/guides/88_microtime_shifter.md](/guides/88_microtime_shifter.md) |
| 702 | `bash` | 1. Open the tool | 1 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 703 | `text` | 1. Open the tool | 9 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 704 | `text` | 3. Detector, channels and gates | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 705 | `python` | Headless | 11 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 706 | `python` | Headless | 13 | compiled | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 707 | `text` | Timing when comparing earlier results | 7 | — | [docs/guides/89_microtime_histogram.md](/guides/89_microtime_histogram.md) |
| 708 | `text` | 1. Open the tool | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 709 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 710 | `text` | 5. Package Manager | 4 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 711 | `text` | 5. Package Manager | 5 | — | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 712 | `python` | Headless / Python | 2 | compiled | [docs/guides/90_updater.md](/guides/90_updater.md) |
| 713 | `bash` | 1. Open the tool and load the fast reference | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 714 | `text` | 1. Open the tool and load the fast reference | 7 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 715 | `text` | 5. Batch, export, archive | 6 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 716 | `python` | Headless and Python | 9 | compiled | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 717 | `bash` | Headless and Python | 1 | — | [docs/guides/91_vv_vh_g_factor.md](/guides/91_vv_vh_g_factor.md) |
| 718 | `text` | 1. Open the tool and load a trace | 8 | — | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 719 | `python` | 4. Save and reuse | 7 | compiled | [docs/guides/92_hmm_binned_traces.md](/guides/92_hmm_binned_traces.md) |
| 720 | `text` | 1. Open the tool and load a stack | 5 | — | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 721 | `python` | Headless and Python | 4 | compiled | [docs/guides/93_psf_determination.md](/guides/93_psf_determination.md) |
| 722 | `text` | Audifier: photon streams as sound and as a waterfall | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 723 | `text` | Layout and saved preferences | 4 | — | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 724 | `text` | 1. The window | 4 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 725 | `text` | 1. The window | 4 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 726 | `text` | Help, Restart and Guide | 7 | — | [docs/guides/95_games.md](/guides/95_games.md) |
| 727 | `python` | 4. Python | 8 | compiled | [docs/guides/95_games.md](/guides/95_games.md) |
| 728 | `text` | 1. Open the tool | 6 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 729 | `text` | 4. Read a failure | 5 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 730 | `bash` | From the command line and from Python | 1 | — | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 731 | `python` | From the command line and from Python | 8 | compiled | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 732 | `text` | 1. The window | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 733 | `text` | 2. The destinations | 4 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 734 | `text` | 2. The destinations | 5 | — | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 735 | `text` | CLSM Simulator: a scan whose answer is known | 4 | — | [docs/guides/98_clsm_generator.md](/guides/98_clsm_generator.md) |
| 736 | `text` | The imaging pipeline in one window (Image Tools) | 6 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 737 | `text` | 1. Open the window | 7 | — | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 738 | `text` | 1. Choose the photons and the detector | 6 | — | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 739 | `python` | The correction | 6 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 740 | `text` | Where the factors come from | 10 | — | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 741 | `python` | 1. Light-path prior → data-optimized posterior | 10 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 742 | `python` | 2. Reference samples (donor-only, acceptor-only) | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 743 | `python` | 3. The donor lifetime and the static FRET line | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 744 | `python` | All three at once | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 745 | `python` | The general case: crosstalk matrices | 13 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 746 | `python` | Naive vs. stable un-mixing | 2 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 747 | `python` | Preserving photon-counting statistics (integer "photon shuffling") | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 748 | `python` | ndxplorer: stable / shuffle un-mixing | 8 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 749 | `python` | Per-pixel / FLIM imaging | 9 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 750 | `python` | Scalar multi-chromophore path | 4 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 751 | `python` | Global analysis and ndxplorer | 5 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 752 | `python` | Global analysis and ndxplorer | 3 | compiled | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 753 | `text` | Inputs and outputs | 13 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 754 | `text` | GUI | 6 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 755 | `bash` | CLI | 5 | — | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 756 | `python` | Python API | 7 | compiled | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 757 | `text` | Projects and session lifecycle | 3 | — | [docs/guides/index.md](/guides/index.md) |
| 758 | `text` | Photon data and the burst pipeline | 26 | — | [docs/guides/index.md](/guides/index.md) |
| 759 | `text` | smFRET: efficiency, stoichiometry and corrections | 19 | — | [docs/guides/index.md](/guides/index.md) |
| 760 | `text` | Dynamics: distributions, kinetics and hidden states | 18 | — | [docs/guides/index.md](/guides/index.md) |
| 761 | `text` | Fluorescence decays and anisotropy | 8 | — | [docs/guides/index.md](/guides/index.md) |
| 762 | `text` | Correlation spectroscopy | 10 | — | [docs/guides/index.md](/guides/index.md) |
| 763 | `text` | Imaging and microscopy | 19 | — | [docs/guides/index.md](/guides/index.md) |
| 764 | `text` | Structure and modelling | 11 | — | [docs/guides/index.md](/guides/index.md) |
| 765 | `text` | Exploration, simulation and automation | 16 | — | [docs/guides/index.md](/guides/index.md) |
| 766 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 767 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 768 | `bash` | Regenerating the figures | 1 | — | [docs/guides/index.md](/guides/index.md) |
| 769 | `text` | Application and settings | 8 | — | [docs/guides/index.md](/guides/index.md) |
| 770 | `text` | Algorithm Pipeline | 12 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 771 | `text` | In the window | 6 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 772 | `python` | Basic Usage | 11 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 773 | `python` | Step-by-Step Usage | 24 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 774 | `python` | Multi-Channel Data | 7 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 775 | `python` | Visualization | 9 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 776 | `python` | Constructor | 1 | compiled | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 777 | `text` | Richardson-Lucy Algorithm | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 778 | `bash` | Testing | 1 | — | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 779 | `text` | Saving and reopening projects | 5 | — | [docs/guides/saving_projects.md](/guides/saving_projects.md) |
| 780 | `text` | Adding the membrane-diffusion models | 10 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 781 | `text` | Adding the membrane-diffusion models | 4 | — | [docs/manual/adding_the_membranediffusion_models.md](/manual/adding_the_membranediffusion_models.md) |
| 782 | `text` | Analysis dock | 1 | — | [docs/manual/analysis_dock.md](/manual/analysis_dock.md) |
| 783 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 784 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 785 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 786 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 787 | `text` | Anisotropy Wizard | 1 | — | [docs/manual/anisotropy_wizard.md](/manual/anisotropy_wizard.md) |
| 788 | `text` | Calculation of co-diffusing molecules | 1 | — | [docs/manual/calculation_of_codiffusing_molecules.md](/manual/calculation_of_codiffusing_molecules.md) |
| 789 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 790 | `text` | Calculation of the red detection volume | 1 | — | [docs/manual/calculations.md](/manual/calculations.md) |
| 791 | `text` | Calculation of the overlap volume and co-diffusion amplitude | 1 | — | [docs/manual/calculations_2.md](/manual/calculations_2.md) |
| 792 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 793 | `text` | Changing visualizations | 1 | — | [docs/manual/changing_visualizations.md](/manual/changing_visualizations.md) |
| 794 | `text` | Correction factors for spectral crosstalk & direct acceptor excitation | 1 | — | [docs/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md](/manual/correction_factors_for_spectral_crosstalk__direct_acceptor_excitation.md) |
| 795 | `text` | Correlation merging | 1 | — | [docs/manual/correlation_merging.md](/manual/correlation_merging.md) |
| 796 | `text` | Correlator | 1 | — | [docs/manual/correlator.md](/manual/correlator.md) |
| 797 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 798 | `text` | Creating fits | 1 | — | [docs/manual/creating_fits.md](/manual/creating_fits.md) |
| 799 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 800 | `text` | Crosstalk-induced correlations | 1 | — | [docs/manual/crosstalkinduced_correlations.md](/manual/crosstalkinduced_correlations.md) |
| 801 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 802 | `text` | Data import | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 803 | `text` | One way in: dropping files | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 804 | `text` | One way in: dropping files | 2 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 805 | `text` | One way in: dropping files | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 806 | `text` | One way in: dropping files | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 807 | `text` | One way in: dropping files | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 808 | `text` | One way in: dropping files | 1 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 809 | `text` | One way in: dropping files | 3 | — | [docs/manual/data_import.md](/manual/data_import.md) |
| 810 | `text` | Data input and file format | 12 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 811 | `text` | Data input and file format | 5 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 812 | `shell` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 813 | `text` | Data input and file format | 1 | — | [docs/manual/data_input_and_file_format.md](/manual/data_input_and_file_format.md) |
| 814 | `text` | Determination of g-factor and depolarization factors using ChiSurf | 1 | — | [docs/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md](/manual/determination_of_gfactor_and_depolarization_factors_using_chisurf.md) |
| 815 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 816 | `text` | Determination of molecular brightness | 1 | — | [docs/manual/determination_of_molecular_brightness.md](/manual/determination_of_molecular_brightness.md) |
| 817 | `text` | Discrete FRET rate constants | 2 | — | [docs/manual/discrete_fret_rate_constants.md](/manual/discrete_fret_rate_constants.md) |
| 818 | `text` | Equation parsing | 1 | — | [docs/manual/equation_parsing.md](/manual/equation_parsing.md) |
| 819 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 820 | `text` | Estimation of the fluorophore concentration | 1 | — | [docs/manual/estimation_of_the_fluorophore_concentration.md](/manual/estimation_of_the_fluorophore_concentration.md) |
| 821 | `text` | F-Calculator | 1 | — | [docs/manual/fcalculator.md](/manual/fcalculator.md) |
| 822 | `text` | Fit interface | 1 | — | [docs/manual/fit_interface.md](/manual/fit_interface.md) |
| 823 | `text` | Fit models | 3 | — | [docs/manual/fit_models.md](/manual/fit_models.md) |
| 824 | `text` | Fit of the green-excitation FCS curve | 4 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 825 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 826 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 827 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 828 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 829 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 830 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 831 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 832 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 833 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 834 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 835 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 836 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 837 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 838 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 839 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 840 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 841 | `text` | Fit of the green-excitation FCS curve | 1 | — | [docs/manual/fit_of_a_fcs_curve.md](/manual/fit_of_a_fcs_curve.md) |
| 842 | `text` | Fit of auto- and cross-correlation curves | 1 | — | [docs/manual/fit_of_auto_and_crosscorrelation_curves.md](/manual/fit_of_auto_and_crosscorrelation_curves.md) |
| 843 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 844 | `text` | Fit of autocorrelation curves | 1 | — | [docs/manual/fit_of_autocorrelation_curves.md](/manual/fit_of_autocorrelation_curves.md) |
| 845 | `text` | Fit of the red-excitation FCS curve | 1 | — | [docs/manual/fit_of_fcs_curve.md](/manual/fit_of_fcs_curve.md) |
| 846 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 847 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 848 | `text` | Fit Plots | 1 | — | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 849 | `text` | Fluorescence Lifetime | 5 | — | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 850 | `text` | Static FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 851 | `text` | Dynamic FRET Line | 26 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 852 | `text` | Visualizing FRET Lines | 14 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 853 | `text` | Visualizing FRET Lines | 21 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 854 | `text` | Example: Complete Analysis Workflow | 71 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 855 | `text` | Troubleshooting | 3 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 856 | `text` | Example Script | 2 | — | [docs/manual/fret_lines.md](/manual/fret_lines.md) |
| 857 | `text` | Global fit of auto- and cross-correlation curves | 1 | — | [docs/manual/global_fit_of_auto_and_crosscorrelation_curves.md](/manual/global_fit_of_auto_and_crosscorrelation_curves.md) |
| 858 | `text` | Global fit of FCS curves | 1 | — | [docs/manual/global_fit_of_fcs_curves.md](/manual/global_fit_of_fcs_curves.md) |
| 859 | `text` | Fitting interface & worked examples | 20 | — | [docs/manual/index.md](/manual/index.md) |
| 860 | `text` | Fitting interface & worked examples | 10 | — | [docs/manual/index.md](/manual/index.md) |
| 861 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 862 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 863 | `text` | Fitting interface & worked examples | 7 | — | [docs/manual/index.md](/manual/index.md) |
| 864 | `text` | Fitting interface & worked examples | 23 | — | [docs/manual/index.md](/manual/index.md) |
| 865 | `text` | Fitting interface & worked examples | 9 | — | [docs/manual/index.md](/manual/index.md) |
| 866 | `text` | Fitting interface & worked examples | 8 | — | [docs/manual/index.md](/manual/index.md) |
| 867 | `text` | Fitting interface & worked examples | 15 | — | [docs/manual/index.md](/manual/index.md) |
| 868 | `text` | Fitting interface & worked examples | 4 | — | [docs/manual/index.md](/manual/index.md) |
| 869 | `text` | Influence of FRET efficiency | 1 | — | [docs/manual/influence_of_fret_efficiency.md](/manual/influence_of_fret_efficiency.md) |
| 870 | `text` | Influence of triplet blinking | 1 | — | [docs/manual/influence_of_triplet_blinking.md](/manual/influence_of_triplet_blinking.md) |
| 871 | `text` | Introduction | 6 | — | [docs/manual/introduction.md](/manual/introduction.md) |
| 872 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 873 | `text` | Linking parameters | 1 | — | [docs/manual/linking_parameters.md](/manual/linking_parameters.md) |
| 874 | `text` | Loading & plotting data | 1 | — | [docs/manual/loading__plotting_data.md](/manual/loading__plotting_data.md) |
| 875 | `text` | Loading and setting up the eGFP data set | 1 | — | [docs/manual/loading_and_setting_up_the_egfp_data_set.md](/manual/loading_and_setting_up_the_egfp_data_set.md) |
| 876 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 877 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 878 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 879 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 880 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 881 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 882 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 883 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 884 | `text` | Loading the Alexa488 data into the anisotropy plugin | 1 | — | [docs/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md](/manual/loading_the_alexa488_data_into_the_anisotropy_plugin.md) |
| 885 | `text` | Model scores | 2 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 886 | `text` | Model scores | 3 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 887 | `text` | Model scores | 1 | — | [docs/manual/model_scores.md](/manual/model_scores.md) |
| 888 | `text` | Model scoring range | 1 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 889 | `text` | Model scoring range | 2 | — | [docs/manual/model_scoring_range.md](/manual/model_scoring_range.md) |
| 890 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 891 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 892 | `text` | Multiple document interface | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 893 | `text` | Arranging the windows | 1 | — | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 894 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 895 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 896 | `text` | Nuisances | 1 | — | [docs/manual/nuisances.md](/manual/nuisances.md) |
| 897 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 898 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 899 | `text` | Overview | 1 | — | [docs/manual/overview.md](/manual/overview.md) |
| 900 | `text` | Correlator: overview | 1 | — | [docs/manual/overview_2.md](/manual/overview_2.md) |
| 901 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 902 | `text` | Global view: overview | 1 | — | [docs/manual/overview_3.md](/manual/overview_3.md) |
| 903 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 904 | `text` | Parameter optimization | 2 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 905 | `text` | Parameter optimization | 1 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 906 | `text` | Settings | 25 | — | [docs/manual/parameter_optimization.md](/manual/parameter_optimization.md) |
| 907 | `text` | Parameter sampling | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 908 | `text` | Parameter sampling | 1 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 909 | `text` | From the shell | 2 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 910 | `text` | From the shell | 5 | — | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 911 | `text` | Parameter scan | 1 | — | [docs/manual/parameter_scan.md](/manual/parameter_scan.md) |
| 912 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 913 | `text` | Parameters | 8 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 914 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 915 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 916 | `text` | Parameters | 1 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 917 | `text` | Parameters | 3 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 918 | `text` | Parameters | 2 | — | [docs/manual/parameters.md](/manual/parameters.md) |
| 919 | `text` | Partial donor-donor energy migration | 3 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 920 | `text` | Parameters | 5 | — | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 921 | `text` | Reference curves | 1 | — | [docs/manual/reference_curves.md](/manual/reference_curves.md) |
| 922 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 923 | `text` | Re-using the parameter to analyse the actual samples | 1 | — | [docs/manual/reusing_the_parameter_to_analyse_the_actual_samples.md](/manual/reusing_the_parameter_to_analyse_the_actual_samples.md) |
| 924 | `text` | Saving & exporting the results | 8 | — | [docs/manual/saving__exporting_the_results.md](/manual/saving__exporting_the_results.md) |
| 925 | `xml` | Saving and loading networks | 14 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 926 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 927 | `text` | Saving and loading networks | 1 | — | [docs/manual/saving_and_loading_networks.md](/manual/saving_and_loading_networks.md) |
| 928 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 929 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 930 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 931 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 932 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 933 | `text` | Setting up the joint global fit of A488 & eGFP | 1 | — | [docs/manual/setting_up_the_joint_global_fit_of_a488__egfp.md](/manual/setting_up_the_joint_global_fit_of_a488__egfp.md) |
| 934 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 935 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 936 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 937 | `text` | Species-filtered FCS to recover dynamics | 1 | — | [docs/manual/speciesfiltered_fcs_to_recover_dynamics.md](/manual/speciesfiltered_fcs_to_recover_dynamics.md) |
| 938 | `text` | Step 1: Approximating g-factor with small fluorophore | 1 | — | [docs/manual/step_1_approximating_gfactor_with_small_fluorophore.md](/manual/step_1_approximating_gfactor_with_small_fluorophore.md) |
| 939 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 940 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 941 | `text` | Step 2: Joint analysis to determine g-factor, ls and lp | 1 | — | [docs/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md](/manual/step_2_joint_analysis_to_determine_gfactor_ls_and_lp.md) |
| 942 | `text` | Two single files | 1 | — | [docs/manual/two_single_files.md](/manual/two_single_files.md) |
| 943 | `text` | VV/VH format | 1 | — | [docs/manual/vv_vh_format.md](/manual/vv_vh_format.md) |
| 944 | `text` | Worm-like chain | 4 | — | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 945 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 946 | `python` | Usage | 9 | compiled | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 947 | `text` | Usage | 7 | — | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 948 | `python` | Correlation section | 5 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 949 | `python` | Correlation section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 950 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 951 | `python` | Intensity trace section | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 952 | `text` | Intensity trace section | 6 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 953 | `python` | Correlation arrays | 2 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 954 | `python` | Intensity arrays | 9 | compiled | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 955 | `text` | ALV-7004/USB `.asc` (openASC_ALV_7004) | 7 | — | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 956 | `text` | File formats | 4 | — | [docs/reference/file_formats/index.md](/reference/file_formats/index.md) |
| 957 | `python` | Single-file structure reader | 6 | compiled | [docs/reference/file_formats/structure_files.md](/reference/file_formats/structure_files.md) |
| 958 | `python` | Workflow | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 959 | `python` | Becker-SDT | 5 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 960 | `python` | Preview and Add | 7 | compiled | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 961 | `text` | Reference | 12 | — | [docs/reference/index.md](/reference/index.md) |
| 962 | `bash` | Local (primitive) | 10 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 963 | `bash` | MMFDB round trip | 13 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 964 | `bash` | Local (primitive) | 4 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 965 | `bash` | Local (primitive) | 3 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 966 | `bash` | MMFDB round trip | 7 | — | [docs/reference/ndxplorer_headless_cli.md](/reference/ndxplorer_headless_cli.md) |
| 967 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 968 | `python` | From a script | 9 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 969 | `python` | From a script | 4 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 970 | `python` | Saving a single parameter | 7 | compiled | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 971 | `text` | Plugin catalogue | 4 | — | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 972 | `yaml` | 3. `settings_colors.yaml` (global color palette) | 3 | — | [docs/reference/settings.md](/reference/settings.md) |
| 973 | `python` | User-Defined Models in ChiSurf | 2 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 974 | `python` | 1.1 Write the model | 21 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
| 975 | `yaml` | 1.3 List it in `experiment_configs.yaml` | 3 | — | [docs/reference/user_models.md](/reference/user_models.md) |
| 976 | `python` | 3. Turning a plain function into a model | 7 | compiled | [docs/reference/user_models.md](/reference/user_models.md) |
