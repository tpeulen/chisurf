---
type: Reference
title: Table index
description: Every table in the documentation, with the section it belongs to and its columns.
tags: [reference, tables, index]
anchor: table-index
generator: build_tools/docs/make_registers.py
---

(table-index)=
# Table index

Every table in the documentation, with the section it belongs to and its
columns. Tables carrying *generated* content — the plugin catalogue, the
parameter glossary, the Literature page — are rebuilt by their
generators; the rest are written by hand and are checked when the page
they sit on is reviewed.

*837 tables.*

| # | Section | Columns | Page |
| --- | --- | --- | --- |
| 1 | Entry points | Command, Purpose | [docs/getting_started/index.md](/getting_started/index.md) |
| 2 | Colours tell the kind of task | Colour, Kind of task, Where | [docs/getting_started/index.md](/getting_started/index.md) |
| 3 | Fonts | Section, Setting, What it does | [docs/getting_started/settings.md](/getting_started/settings.md) |
| 4 | What happens before emission | Process, Timescale | [docs/fundamentals/absorption_and_emission.md](/fundamentals/absorption_and_emission.md) |
| 5 | The excited state | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 6 | Anisotropy | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 7 | FRET | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 8 | FCS | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 9 | Units | Quantity, Unit | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 10 | Fundamentals (photophysics) | Layer, Question | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 11 | Detectors | Detector, Timing resolution, Notes | [docs/fundamentals/instrumentation.md](/fundamentals/instrumentation.md) |
| 12 | The three decay laws | Dimensionality, Physical case, Exponent, $C_0$, $\eta_d$ at $C=C_0$ | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 13 | Choosing the geometry: fit all three | Simulated, Fitted as 1-D, Fitted as 2-D, Fitted as 3-D | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 14 | Three AV-to-distance measures | $\langle R_{DA}\rangle$, $\sigma = 3$ Å, $\sigma = 6$ Å, $\sigma = 10$ Å, $\sigma = 15$ Å | [docs/concepts/accessible_volume.md](/concepts/accessible_volume.md) |
| 15 | The four factors | channel, alias, what it holds | [docs/concepts/accurate_fret.md](/concepts/accurate_fret.md) |
| 16 | The Perrin equation: $\rho$, volume and viscosity | system, $\rho$, $\tau/\rho$, $r/r_0$ | [docs/concepts/anisotropy.md](/concepts/anisotropy.md) |
| 17 | The application shell: settings, interface, account, help and hubs | State, Owner, Lives in, Changed by | [docs/concepts/application_shell.md](/concepts/application_shell.md) |
| 18 | The cost: a fused burst is one interval | Control, Question it answers | [docs/concepts/burst_fusion.md](/concepts/burst_fusion.md) |
| 19 | What to report | Report, Because | [docs/concepts/colocalization.md](/concepts/colocalization.md) |
| 20 | The iteration count is the regularisation | iterations, 5, 20, 100, 400 | [docs/concepts/deconvolution.md](/concepts/deconvolution.md) |
| 21 | Two things that quietly go wrong | support, 3.7 σ, 5.0 σ, 6.3 σ, 7.7 σ | [docs/concepts/deconvolution.md](/concepts/deconvolution.md) |
| 22 | The parameters, in the order that matters | Parameter, What it decides | [docs/concepts/density_clustering.md](/concepts/density_clustering.md) |
| 23 | Why drift is not just blur | Frame lag $\Delta$, $G(0,0,\Delta)$ uncorrected, corrected | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 24 | Measuring the shift | Reference, Behaviour | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 25 | The QuEst model | residue, $k_Q$ (1/ns), contact from dye surface (Å), $R_i$ from dye centre (Å), quenching centre | [docs/concepts/dye_quenching.md](/concepts/dye_quenching.md) |
| 26 | Why it hides | Observable, Effect of homo-transfer | [docs/concepts/energy_migration.md](/concepts/energy_migration.md) |
| 27 | The posterior factorises | operation, in canonical form | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 28 | The model | Array, Meaning | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 29 | The second apparent diffusion time | Power, V_eff/V₀, apparent τ_D, one-component residual, two-component fit | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 30 | Fitting it: a global triplet times two diffusion times | amplitude, τ_D | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 31 | File tools: operations on the container, not the measurement | tool, does | [docs/concepts/file_tools.md](/concepts/file_tools.md) |
| 32 | Conditioning: the price of similar patterns | $\tau_2$, $\tau_2/\tau_1$, condition number, largest filter value | [docs/concepts/filtered_fcs.md](/concepts/filtered_fcs.md) |
| 33 | The statistics | statistic, weight, notes | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 34 | Why the Neyman weighting is biased | counts per bin, Neyman (data-weighted), Pearson (model-weighted) | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 35 | Comparing nested models: the F-test | comparison, $\chi^2_r$, variance-ratio conf., extra-SS $F$, $p$, $\Delta$AIC | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 36 | `_flr_analysis_feature` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 37 | `_flr_fit_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 38 | `_flr_fret_analysis` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 39 | `_flr_fret_calibration_parameters` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 40 | `_flr_fret_forster_radius` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 41 | `_flr_poly_probe_position` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 42 | `_flr_probe_descriptor` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 43 | `_flr_probe_list` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 44 | `_flr_sample` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 45 | `_flr_sample_condition` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 46 | `_flr_sample_probe_details` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 47 | `_ihm_chemical_component_descriptor` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 48 | `_ihm_external_files` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 49 | `_mmfdb_acl_entry` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 50 | `_mmfdb_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 51 | `_mmfdb_artifact_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 52 | `_mmfdb_artifact_owner` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 53 | `_mmfdb_audit_log` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 54 | `_mmfdb_auth_attempt` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 55 | `_mmfdb_branch` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 56 | `_mmfdb_bundle_document` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 57 | `_mmfdb_bundle_file` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 58 | `_mmfdb_burst_column` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 59 | `_mmfdb_column` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 60 | `_mmfdb_constant` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 61 | `_mmfdb_container` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 62 | `_mmfdb_derived_column` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 63 | `_mmfdb_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 64 | `_mmfdb_event_log` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 65 | `_mmfdb_group` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 66 | `_mmfdb_group_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 67 | `_mmfdb_label_score` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 68 | `_mmfdb_object` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 69 | `_mmfdb_object_acl` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 70 | `_mmfdb_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 71 | `_mmfdb_operation_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 72 | `_mmfdb_operation_parameter_def` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 73 | `_mmfdb_optical_property` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 74 | `_mmfdb_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 75 | `_mmfdb_pipeline` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 76 | `_mmfdb_pipeline_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 77 | `_mmfdb_pipeline_node` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 78 | `_mmfdb_pipeline_run` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 79 | `_mmfdb_pipeline_run_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 80 | `_mmfdb_probe` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 81 | `_mmfdb_protocol` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 82 | `_mmfdb_provenance_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 83 | `_mmfdb_provenance_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 84 | `_mmfdb_provenance_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 85 | `_mmfdb_provenance_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 86 | `_mmfdb_reagent_lot` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 87 | `_mmfdb_reagent_usage` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 88 | `_mmfdb_session` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 89 | `_mmfdb_setup` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 90 | `_mmfdb_setup_calibration` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 91 | `_mmfdb_setup_detector_channel` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 92 | `_mmfdb_setup_fcs_pair` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 93 | `_mmfdb_setup_pie_window` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 94 | `_mmfdb_spectrum` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 95 | `_mmfdb_state_transition` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 96 | `_mmfdb_state_transition_rule` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 97 | `_mmfdb_study` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 98 | `_mmfdb_study_key_value` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 99 | `_mmfdb_study_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 100 | `_mmfdb_units` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 101 | `_mmfdb_vocabulary` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 102 | `_mmfdb_workflow` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 103 | `_mmfdb_workflow_step` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 104 | `_struct_ref` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 105 | How precise is the distance? | $E$, $6E(1-E)$, $\Delta R/R$ for $\Delta E = 0.02$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 106 | How precise is the distance? | error in $J$ or $Q_D$, effect on $R_0$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 107 | How precise is the distance? | $\kappa^2$, $R$ scaled by, situation | [docs/concepts/fret.md](/concepts/fret.md) |
| 108 | Linking is not fixing | asserts, uses data, keeps its uncertainty | [docs/concepts/global_analysis.md](/concepts/global_analysis.md) |
| 109 | Decoding: "most likely path" is not "how the photons distribute" | decoder, draws from, photon distribution, dwell / transition structure | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 110 | What H2MM can and cannot resolve | $K$, $k$ ($P=2$, DD/DA), $k$ ($P=3$, with AA) | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 111 | When to use something else | Situation, Better tool | [docs/concepts/hidden_markov_models.md](/concepts/hidden_markov_models.md) |
| 112 | HYDROPRO | INDMODE, primary model, calculation, AER | [docs/concepts/hydrodynamics.md](/concepts/hydrodynamics.md) |
| 113 | Worked numbers | Step, Lag time, Ratio to previous | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 114 | Which method is which | RICS, STICS, TICS, iMSD | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 115 | Using it in ChiSurf | Release this, To fit | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 116 | What the gate actually tested | quantity, measured / model-free, forward model | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 117 | Testing it against simulated dynamics | regime, true rate, fitted, bursts between the states | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 118 | Three sources, one model | source, what it uses, what it is for | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 119 | Choosing a density | `dot_density`, points per atom, typical error | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 120 | What the peak time means | transport, peak of $G(\tau,\delta)$, scaling | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 121 | Reading the numbers | what you see, what it means | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 122 | Three uncertainty estimates, in increasing generality | Method, What it does, Assumes | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 123 | Why the proposal matters so much | Sampler, Proposal, $\tau$, Effective samples per 1000 model evaluations | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 124 | Collapsing: integrate the private parameters out | Sampler, τ(shared), min ESS, ESS / 1000 evals, reported $a$ | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 125 | Changing your mind about a prior, without sampling again | $\hat k$, meaning | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 126 | The numbers you actually publish | lower arm, upper arm | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 127 | Three stages, three failure modes | stage, question, how it fails | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 128 | Why a wavelet, and why two scales | threshold, 128², 256², 512² | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 129 | Why the histogram carries brightness | sample, $\epsilon$, $N$, $\epsilon T$, $\langle k\rangle$, $\mathrm{Var}-\langle k\rangle$, $B$ | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 130 | How much heterogeneity can PDA actually detect? | $N$ (photons/burst), 20, 50, 100, 200, 500 | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 131 | How much heterogeneity can PDA actually detect? | $\sigma_\text{het}$, $\sigma_\text{obs}$ at $N=50$, at $N=200$, ratio | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 132 | What a burst looks like | symbol, excitation → detection | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 133 | Excitation, transfer, emission | matrix, shape, meaning | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 134 | The problem with histograms | exchange, histogram, what you can measure | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 135 | Relation to H2MM | H2MM, Gopich–Szabo | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 136 | What ChiSurf writes, and what it only reads | what, where it goes | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 137 | The scalar focus: the Airy pattern | Feature, Where, Distance | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 138 | What ChiSurf computes | Model / pupil state, FWHM $x$, FWHM $y$, FWHM $z$ | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 139 | What ChiSurf computes | NA, medium, lateral: vectorial vs $0.514\,\lambda/\mathrm{NA}$, axial: vectorial vs $0.886\,\lambda/(n-\sqrt{n^2-\mathrm{NA}^2})$ | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 140 | Energy | Name, Term | [docs/concepts/protein_monte_carlo.md](/concepts/protein_monte_carlo.md) |
| 141 | FRET along a trajectory | averaging, $\kappa^2 = 2/3$, $\kappa^2$ per frame ($\langle\kappa^2\rangle$ = 0.574) | [docs/concepts/structure_trajectories.md](/concepts/structure_trajectories.md) |
| 142 | Where this connects in ChiSurf | Question, Page | [docs/concepts/super_resolution.md](/concepts/super_resolution.md) |
| 143 | How many components? | Rule, Referred to, $R$ needed at 68 %, at 95 % | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 144 | The two clocks of a photon record | clock, scale, wraps, builds | [docs/concepts/tttr_stream_tools.md](/concepts/tttr_stream_tools.md) |
| 145 | The four streams, and what they are for | stream, excitation, emission, used for | [docs/concepts/us_alex.md](/concepts/us_alex.md) |
| 146 | In the GUI: the same-molecule probability | Control, Default, Meaning | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 147 | In ChiSurf | Control, Default, Meaning | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 148 | Which tool for which clock | tool, acts on, guide | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 149 | 3. Simulate and read | tab, content | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 150 | 2. Run it | Option, Meaning | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 151 | 2. Photons and markers | Kind, What it is, Colour | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 152 | 3. Navigate and filter | Control, Effect | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 153 | Reading bursts | Entry, Read as | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 154 | Open the tool | Control, Default, Meaning | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 155 | Choosing a decoder | *Decoder*, what it does, use it for | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 156 | Per-state decays | Column, Meaning | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 157 | The Burst MLE tool | Model, Inputs in parameter order, Interpretation | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 158 | The lifetime of a state, not of a burst | Detector, Colour, State, Photons (parallel), Photons (perpendicular), Photons, Tau, 2I*, … | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 159 | Trace Browser | Button, What it does | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 160 | Result | table, one row per, columns | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 161 | 5. Choosing a sampler | `method`, Use when | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 162 | 9. Reusing a chain under a different prior | `pareto_k`, what to do | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 163 | 15. Error bars on the quantities you publish | Method, What it is, Read the interval as | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 164 | Setting it up | Provider, Base URL, Processing location, Key from | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 165 | Things to ask it | Ask it, What it does | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 166 | Using it in the GUI | Mode, What it can do | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 167 | Skills: how it knows *how* | Skill, Loaded when you ask about | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 168 | 2. Check the channel mapping | combo, channel | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 169 | Naming differences to watch | ndX, meaning, Hellenkamp | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 170 | Trying it without data (and checking it works) | factor, declared, recovered | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 171 | Loading data | reader, use it for | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 172 | Loading and looking | Repository, Looks like, Gives you | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 173 | A simulation is more than motion | What the file says, What you see | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 174 | The Map panel | Map, Opens at, Why | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 175 | Trying it out: the Demo menu | Entry, What it shows | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 176 | Selecting with the mouse | Gesture, Action, Effect | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 177 | Measuring by clicking | Control, What it does | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 178 | Polar contacts | `mode`, What it draws | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 179 | Hydrogen-bond networks | Argument, Meaning | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 180 | Mutating a residue | Detail, What happens | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 181 | Where things stand | Area, State | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 182 | Read the result | Predicted error, Verdict, What to do | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 183 | Play the measurement back | Control, What it does | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 184 | What it does | Bridge, ChiSurf RPC, Produces | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 185 | Where regions appear | Tool, What a region does there | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 186 | 1. Detect | what you see, what it means | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 187 | The menu is not a list ndX keeps | Target, RPC, What comes back | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 188 | What counts as a change | Step, Reuses when, Recomputes when | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 189 | Everything downstream is handed the same files | Panel, Receives | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 190 | Settings reference | Setting, What it does | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 191 | Which route to use | you want, use, resolution | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 192 | 1. Open the calculator and pick a scheme | Scheme, States, Use it for | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 193 | 3. A worked case: Rhodamine 6G at 488 nm | Power, k_exc(0,0), V_eff/V₀, apparent τ_D, G(0) vs unsaturated, no bunching | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 194 | 1. Load the folder | Setting, What it does | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 195 | 3. Set the two controls | Control, Question, How to choose | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 196 | 3. Set the two controls | Threshold, Window, Bursts, Proximity-ratio width | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 197 | 4. Judge it from the summary, not from the burst count | Row, Expected, What it means if not | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 198 | What is already in scope | Name, What it is | [docs/guides/59_console.md](/guides/59_console.md) |
| 199 | What you need first | Field, Measure it on | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 200 | Step 3 — read the right number | Reading, What it means | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 201 | Step 4 — the step that decides whether you can publish it | Outcome, Reading | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 202 | What is in it | column, what it is | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 203 | The toolbar | Control, What it does | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 204 | Where each window went | ALEX-Suite, here | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 205 | 3 — Alternation, measured rather than typed | stream, burst-table column | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 206 | If it will not answer | It says, What to do | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 207 | Export | Format, Contents, For | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 208 | Find the levels (HMM tab) | Path, Content | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 209 | The `.cor` file | Column, Content | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 210 | Converting correlation files | Readers (`-it`), Writers (`-ot`) | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 211 | Open the tools | Tool, Opens from, What it does, Guide | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 212 | Settings | Key, Default, Meaning | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 213 | The component-count scan | True decay, `noise_model`, Chosen $n$ (seeds 1, 2, 3), Recovered | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 214 | VV/VH: lifetimes and rotations together | Truth, Seeds, Recovered | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 215 | Reading it: the case where the tests disagree | comparison, $\chi^2_r$, tool confidence, $\chi^2_{r,2}$ needed at 95 %, extra-SS $F$ ($p$), $\Delta$AIC | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 216 | Where results go | item, $\tau_1$ (ns), $\tau_2$ (ns), $\langle\tau\rangle_x$ (ns), $\langle\tau\rangle_F$ (ns), $\chi^2_r$ | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 217 | The standard lines | Line, Components, Vary, Range | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 218 | 1. Open the Spectra Downloader | panel, what it does | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 219 | 2. Where the spectra come from, and the terms they come under | source, carries, terms | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 220 | 5. Check it against published values | pair, spectra, $Q_D$, ε_max (M⁻¹ cm⁻¹), $J$ (M⁻¹ cm⁻¹ nm⁴), $R_0$ ChiSurf, $R_0$ table | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 221 | 2. Settings | workflow, method, for | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 222 | 2. Settings | control, meaning | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 223 | 3. A real image | workflow, regions | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 224 | 3. A real image | threshold, 0.05, 5, 20, 50, 100 | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 225 | 1. Where it is | control, what it does | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 226 | 2. What it checks | line of the report, what was done | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 227 | 2. What it checks | detector, channels, micro-time window | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 228 | 6. Export | button, writes | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 229 | 8. Where things go wrong | symptom, cause | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 230 | 1. The page | Where, Control, What it does | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 231 | 2. Mix | Window, Control, What it does | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 232 | 2. Keys and pointer | Game, Keys, Pointer | [docs/guides/95_games.md](/guides/95_games.md) |
| 233 | 3. Read the table | Column, Means | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 234 | 1. The window | Where, Control, What it does | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 235 | 2. The destinations | Destination, Panel, Figure | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 236 | 2. The list | Group, Tools | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 237 | 3. Windows, backgrounds, shifts | Field, Meaning | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 238 | The correction | factor, symbol, meaning | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 239 | Compute engines | engine, description, accuracy | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 240 | Where each guide starts in ChiSurf | Tutorial, ChiSurf entry point | [docs/guides/index.md](/guides/index.md) |
| 241 | Fit Plots | Control, What it does | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 242 | Convolution modes | Mode, Use it for | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 243 | Arranging the windows | Command, What it does | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 244 | From the shell | `method`, When to use it | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 245 | Parameters | Parameter, Meaning | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 246 | Parameters | Parameter, Meaning | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 247 | Code index | #, Language, Section, Lines, Verified, Page | [docs/reference/code.md](/reference/code.md) |
| 248 | Figure index | #, Image, Caption, Origin, Page | [docs/reference/figures.md](/reference/figures.md) |
| 249 | SdtFile | Attribute, Content | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 250 | BeckerHicklSetReader | Member, Content | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 251 | Properties | Property, Definition, Unit | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 252 | Parameters | Name, Meaning | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 253 | FCS file formats | Reader, `experiment_reader`, Files | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 254 | Column layout (write side) | Column, Content | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 255 | FCS-CSV (generic ASCII) | Column, Content | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 256 | One file, many curves | curve type, meaning | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 257 | China FCS MATLAB `.mat` | Correlation, Intensity, Curve | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 258 | The setting that chooses the method | Setting, What you get | [docs/reference/file_formats/ics_files.md](/reference/file_formats/ics_files.md) |
| 259 | R_DA axis settings | Key, Meaning, Shipped | [docs/reference/file_formats/rda_axis_settings.md](/reference/file_formats/rda_axis_settings.md) |
| 260 | Format, columns and errors | Format, Reads | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 261 | Reading a parameter table | Appearance, Meaning | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 262 | Parameter glossary | Parameter, Meaning, Keywords | [docs/reference/parameters.md](/reference/parameters.md) |
| 263 | Identity | Field, Value | [docs/reference/plugins/about.md](/reference/plugins/about.md) |
| 264 | Identity | Field, Value | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 265 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 266 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 267 | Dyes (database) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 268 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 269 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 270 | Optics prior (light path) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 271 | Procedure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 272 | Identity | Field, Value | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 273 | Device session | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 274 | Routing and output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 275 | Simulator configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 276 | Result visibility | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 277 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 278 | CFD | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 279 | Sync | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 280 | TAC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 281 | Timing | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 282 | Mode | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 283 | Hardware acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 284 | SPC file output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 285 | Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 286 | Correlation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 287 | Count rate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 288 | MCS | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 289 | Macrotime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 290 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 291 | Sample & brightness | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 292 | Geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 293 | Microtime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 294 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 295 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 296 | Identity | Field, Value | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 297 | API Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 298 | Models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 299 | Generation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 300 | Identity | Field, Value | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 301 | Fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 302 | Burst filters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 303 | Identity | Field, Value | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 304 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 305 | Files & fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 306 | Run | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 307 | Identity | Field, Value | [docs/reference/plugins/bid_to_analysis.md](/reference/plugins/bid_to_analysis.md) |
| 308 | Identity | Field, Value | [docs/reference/plugins/boarding.md](/reference/plugins/boarding.md) |
| 309 | Identity | Field, Value | [docs/reference/plugins/breakout.md](/reference/plugins/breakout.md) |
| 310 | Identity | Field, Value | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 311 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 312 | Identity | Field, Value | [docs/reference/plugins/burst_analysis.md](/reference/plugins/burst_analysis.md) |
| 313 | Identity | Field, Value | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 314 | Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 315 | Fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 316 | Identity | Field, Value | [docs/reference/plugins/burst_browser.md](/reference/plugins/burst_browser.md) |
| 317 | Identity | Field, Value | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 318 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 319 | Identity | Field, Value | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 320 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 321 | Select Series | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 322 | Crop | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 323 | Select States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 324 | States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 325 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 326 | Number of States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 327 | Time Series Group | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 328 | Expected Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 329 | Prior Strength | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 330 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 331 | Identity | Field, Value | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 332 | Correlator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 333 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 334 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 335 | Identity | Field, Value | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 336 | Fusion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 337 | P(same molecule) estimate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 338 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 339 | Identity | Field, Value | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 340 | Photons | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 341 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 342 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 343 | Extras | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 344 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 345 | Identity | Field, Value | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 346 | Data | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 347 | Model selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 348 | Optimisation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 349 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 350 | Burst | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 351 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 352 | Identity | Field, Value | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 353 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 354 | Identity | Field, Value | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 355 | Burst files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 356 | Detector and window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 357 | Measured IRF and background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 358 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 359 | H2MM states | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 360 | Burst | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 361 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 362 | Identity | Field, Value | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 363 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 364 | Burst search | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 365 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 366 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 367 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 368 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 369 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 370 | Scatter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 371 | GMM settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 372 | Metadata | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 373 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 374 | Identity | Field, Value | [docs/reference/plugins/calculators.md](/reference/plugins/calculators.md) |
| 375 | Identity | Field, Value | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 376 | Identity | Field, Value | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 377 | File | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 378 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 379 | Brush & Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 380 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 381 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 382 | Identity | Field, Value | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 383 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 384 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 385 | Identity | Field, Value | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 386 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 387 | Identity | Field, Value | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 388 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 389 | Identity | Field, Value | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 390 | F-test — compare two nested models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 391 | χ²-max — upper limit from one fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 392 | Identity | Field, Value | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 393 | Species | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 394 | Kinetics / statistics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 395 | Identity | Field, Value | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 396 | Diffusion / volume | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 397 | Occupancy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 398 | Constraint (choose one) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 399 | Reference dye (D @ 25 °C, water) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 400 | Molecular shape | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 401 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 402 | Identity | Field, Value | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 403 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 404 | Identity | Field, Value | [docs/reference/plugins/fcs_convert.md](/reference/plugins/fcs_convert.md) |
| 405 | Identity | Field, Value | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 406 | Correlation Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 407 | Correlation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 408 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 409 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 410 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 411 | Change-point parameters (BOCPD / Kalman / CUSUM) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 412 | Plot settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 413 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 414 | Identity | Field, Value | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 415 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 416 | Mixed decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 417 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 418 | Auto-fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 419 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 420 | Identity | Field, Value | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 421 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 422 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 423 | Identity | Field, Value | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 424 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 425 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 426 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 427 | Identity | Field, Value | [docs/reference/plugins/fcs_toolbox.md](/reference/plugins/fcs_toolbox.md) |
| 428 | Identity | Field, Value | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 429 | 2D-FDC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 430 | Lifetime inversion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 431 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 432 | Dynamics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 433 | Kinetics (advanced) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 434 | 1D-MEM + Gaussian | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 435 | Simulator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 436 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 437 | Identity | Field, Value | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 438 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 439 | Identity | Field, Value | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 440 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 441 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 442 | Identity | Field, Value | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 443 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 444 | Docking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 445 | Monte-Carlo (mc method only) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 446 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 447 | Candidate sites from residues | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 448 | Efficiency | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 449 | Selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 450 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 451 | Identity | Field, Value | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 452 | Your dyes | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 453 | Components | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 454 | Sweep | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 455 | Identity | Field, Value | [docs/reference/plugins/games.md](/reference/plugins/games.md) |
| 456 | Identity | Field, Value | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 457 | Toolbar | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 458 | View | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 459 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 460 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 461 | Identity | Field, Value | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 462 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 463 | Identity | Field, Value | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 464 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 465 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 466 | State scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 467 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 468 | Identity | Field, Value | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 469 | Executable & input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 470 | Primary model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 471 | Solvent & macromolecule | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 472 | Optional calculations | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 473 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 474 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 475 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 476 | Identity | Field, Value | [docs/reference/plugins/imaging_common.md](/reference/plugins/imaging_common.md) |
| 477 | Identity | Field, Value | [docs/reference/plugins/imaging_tools.md](/reference/plugins/imaging_tools.md) |
| 478 | Identity | Field, Value | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 479 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 480 | Identity | Field, Value | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 481 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 482 | Background / thresholds | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 483 | Scatter gate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 484 | Region of interest | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 485 | Objects (punctate signal) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 486 | Significance / profile | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 487 | Identity | Field, Value | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 488 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 489 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 490 | Identity | Field, Value | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 491 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 492 | Scanner | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 493 | Display and estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 494 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 495 | Identity | Field, Value | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 496 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 497 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 498 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 499 | Identity | Field, Value | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 500 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 501 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 502 | Identity | Field, Value | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 503 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 504 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 505 | Identity | Field, Value | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 506 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 507 | IRF preparation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 508 | Fit flags | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 509 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 510 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 511 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 512 | Fit parameters (fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 513 | Fit parameters (fit24) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 514 | Fit parameters (fit25) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 515 | Lifetime map | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 516 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 517 | Identity | Field, Value | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 518 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 519 | Stack corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 520 | Detector | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 521 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 522 | Parameter plane / gates | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 523 | Cross N&B | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 524 | Identity | Field, Value | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 525 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 526 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 527 | IRF reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 528 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 529 | Identity | Field, Value | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 530 | Movie | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 531 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 532 | 1. Detect | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 533 | 2. Link | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 534 | 3. Transport | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 535 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 536 | Core | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 537 | File → Data | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 538 | Help | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 539 | Main → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 540 | Microscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 541 | Setup | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 542 | Spectroscopy → Correlation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 543 | Spectroscopy → Decay | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 544 | Spectroscopy → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 545 | Spectroscopy → Imaging | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 546 | Spectroscopy → Imaging → Lifetime | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 547 | Spectroscopy → Imaging → Simulate | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 548 | Spectroscopy → Imaging → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 549 | Spectroscopy → Kinetics | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 550 | Spectroscopy → Single-Molecule | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 551 | Structure → Computation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 552 | Structure → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 553 | Structure → Modelling | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 554 | Structure → Trajectory | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 555 | Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 556 | Tools → Calculators | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 557 | Tools → Miscellaneous | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 558 | Tools → Miscellaneous → Games | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 559 | Tools → Photon data | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 560 | Tools → System | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 561 | Tools → TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 562 | Tools → Views | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 563 | Uncategorized | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 564 | Identity | Field, Value | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 565 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 566 | Time Window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 567 | Histogram Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 568 | HMM Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 569 | Identity | Field, Value | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 570 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 571 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 572 | Identity | Field, Value | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 573 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 574 | Anisotropy Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 575 | Calculation Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 576 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 577 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 578 | Identity | Field, Value | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 579 | Graph view | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 580 | Backend | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 581 | MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 582 | Connections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 583 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 584 | Identity | Field, Value | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 585 | Input Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 586 | Fitting Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 587 | Anisotropy (VV/VH) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 588 | Identity | Field, Value | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 589 | MEM settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 590 | Lifetime grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 591 | Distance grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 592 | Periodic convolution | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 593 | Instrument | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 594 | Nuisance optimization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 595 | L-curve | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 596 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 597 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 598 | Identity | Field, Value | [docs/reference/plugins/menu_switch.md](/reference/plugins/menu_switch.md) |
| 599 | Identity | Field, Value | [docs/reference/plugins/mfd_prepare.md](/reference/plugins/mfd_prepare.md) |
| 600 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mfd_prepare.md](/reference/plugins/mfd_prepare.md) |
| 601 | Identity | Field, Value | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 602 | Run | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 603 | Detector and channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 604 | Reading and gates | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 605 | Time step, G-factor and shifts | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 606 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 607 | Identity | Field, Value | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 608 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 609 | Entity | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 610 | Probes | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 611 | Alignment | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 612 | Shifts | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 613 | Save | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 614 | MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 615 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 616 | Identity | Field, Value | [docs/reference/plugins/minesweeper.md](/reference/plugins/minesweeper.md) |
| 617 | Identity | Field, Value | [docs/reference/plugins/mle_common.md](/reference/plugins/mle_common.md) |
| 618 | Identity | Field, Value | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 619 | Connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 620 | Choose | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 621 | Enter a value | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 622 | Change password | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 623 | Jump to branch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 624 | Overview | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 625 | All items | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 626 | Measurements | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 627 | Sample Metadata | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 628 | Detail | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 629 | Spectra | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 630 | Provenance Graph | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 631 | Import / Export | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 632 | eLabFTW connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 633 | eLabFTW | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 634 | Import into MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 635 | Export from MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 636 | Studies | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 637 | Protocols | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 638 | Lifecycle | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 639 | Register calibration value | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 640 | Reagent Lots | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 641 | Add lot | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 642 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 643 | Advanced — user & connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 644 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 645 | Identity | Field, Value | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 646 | Registered models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 647 | Selected model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 648 | Identity | Field, Value | [docs/reference/plugins/ndxplorer.md](/reference/plugins/ndxplorer.md) |
| 649 | Identity | Field, Value | [docs/reference/plugins/number_quest.md](/reference/plugins/number_quest.md) |
| 650 | Identity | Field, Value | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 651 | Data settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 652 | Model fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 653 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 654 | Identity | Field, Value | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 655 | Excitation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 656 | Reference geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 657 | Two-component line | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 658 | Mixing region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 659 | Cursor | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 660 | Identity | Field, Value | [docs/reference/plugins/photon_table.md](/reference/plugins/photon_table.md) |
| 661 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/photon_table.md](/reference/plugins/photon_table.md) |
| 662 | Identity | Field, Value | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 663 | Curves | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 664 | Fit range | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 665 | Global fits | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 666 | Axes and grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 667 | Show | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 668 | Node graphs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 669 | Identity | Field, Value | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 670 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 671 | Identity | Field, Value | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 672 | Installed plugins | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 673 | Selected plugin | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 674 | Plugin Manager | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 675 | Icon | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 676 | Identity | Field, Value | [docs/reference/plugins/pong.md](/reference/plugins/pong.md) |
| 677 | Identity | Field, Value | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 678 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 679 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 680 | Identity | Field, Value | [docs/reference/plugins/proteinmc.md](/reference/plugins/proteinmc.md) |
| 681 | Identity | Field, Value | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 682 | Objective | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 683 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 684 | Polarization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 685 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 686 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 687 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 688 | Identity | Field, Value | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 689 | PSF parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 690 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 691 | Fit Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 692 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 693 | Identity | Field, Value | [docs/reference/plugins/pto_inspector.md](/reference/plugins/pto_inspector.md) |
| 694 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pto_inspector.md](/reference/plugins/pto_inspector.md) |
| 695 | Identity | Field, Value | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 696 | Formats | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 697 | ALEX modulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 698 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 699 | Input file | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 700 | Excitation regions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 701 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 702 | Identity | Field, Value | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 703 | Structure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 704 | Dye | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 705 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 706 | Quenching | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 707 | FRET | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 708 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 709 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 710 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 711 | Identity | Field, Value | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 712 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 713 | Regions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 714 | Fit (Fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 715 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 716 | Identity | Field, Value | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 717 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 718 | Optics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 719 | Scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 720 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 721 | Identity | Field, Value | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 722 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 723 | Advanced Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 724 | Device Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 725 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 726 | Geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 727 | Microtime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 728 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 729 | Interface | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 730 | Editor and console | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 731 | Documentation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 732 | Formulas | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 733 | Rendering | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 734 | Identity | Field, Value | [docs/reference/plugins/setup_channel_definition.md](/reference/plugins/setup_channel_definition.md) |
| 735 | Identity | Field, Value | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 736 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 737 | Advanced — connection & authentication | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 738 | Identity | Field, Value | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 739 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 740 | Detector | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 741 | Spot width (log / dog) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 742 | Filters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 743 | Pick by clicking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 744 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 745 | Identity | Field, Value | [docs/reference/plugins/style_manager.md](/reference/plugins/style_manager.md) |
| 746 | Identity | Field, Value | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 747 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 748 | Identity | Field, Value | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 749 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 750 | IRF & noise | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 751 | Anisotropy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 752 | VV/VH detection corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 753 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 754 | Identity | Field, Value | [docs/reference/plugins/tetris.md](/reference/plugins/tetris.md) |
| 755 | Identity | Field, Value | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 756 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 757 | Reader settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 758 | Background region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 759 | Instrument corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 760 | Lifetime spectrum | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 761 | Rotation spectrum | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 762 | Identity | Field, Value | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 763 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 764 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 765 | Identity | Field, Value | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 766 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 767 | Identity | Field, Value | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 768 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 769 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 770 | Identity | Field, Value | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 771 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 772 | Identity | Field, Value | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 773 | Reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 774 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 775 | Identity | Field, Value | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 776 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 777 | Identity | Field, Value | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 778 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 779 | Identity | Field, Value | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 780 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 781 | Identity | Field, Value | [docs/reference/plugins/traj_save_topology.md](/reference/plugins/traj_save_topology.md) |
| 782 | Identity | Field, Value | [docs/reference/plugins/traj_tools.md](/reference/plugins/traj_tools.md) |
| 783 | Identity | Field, Value | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 784 | Audio | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 785 | Waterfall params | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 786 | Micro-time | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 787 | Lifetime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 788 | Identity | Field, Value | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 789 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 790 | Identity | Field, Value | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 791 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 792 | Identity | Field, Value | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 793 | Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 794 | Toolbar | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 795 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 796 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 797 | Identity | Field, Value | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 798 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 799 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 800 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 801 | LUT flow | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 802 | Compute LUT | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 803 | settings.tttr.json | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 804 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 805 | Identity | Field, Value | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 806 | Input / Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 807 | Split options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 808 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 809 | Identity | Field, Value | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 810 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 811 | Identity | Field, Value | [docs/reference/plugins/tttr_to_pto.md](/reference/plugins/tttr_to_pto.md) |
| 812 | Identity | Field, Value | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 813 | Installed Packages | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 814 | Search & Install | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 815 | ChiSurf Package Manager | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 816 | Installed version | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 817 | Startup behavior | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 818 | Update | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 819 | ChiSurf Updater | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 820 | Identity | Field, Value | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 821 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 822 | Identity | Field, Value | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 823 | VV/VH anisotropy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 824 | Correction | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 825 | r-infinity region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 826 | Identity | Field, Value | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 827 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 828 | Tail matching | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 829 | Manual G | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 830 | Slow-reference mixing | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 831 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 832 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 833 | Identity | Field, Value | [docs/reference/plugins/wizards.md](/reference/plugins/wizards.md) |
| 834 | 1.8.2.1 `gui.console` | Key, Default, Meaning | [docs/reference/settings.md](/reference/settings.md) |
| 835 | Table index | #, Section, Columns, Page | [docs/reference/tables.md](/reference/tables.md) |
| 836 | User-Defined Models in ChiSurf | What it does, Use it when | [docs/reference/user_models.md](/reference/user_models.md) |
| 837 | 5.1 Using the code view | Control, What it does | [docs/reference/user_models.md](/reference/user_models.md) |
