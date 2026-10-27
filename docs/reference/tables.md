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

*877 tables.*

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
| 17 | The application shell: settings, interface, account and help | State, Owner, Lives in, Changed by | [docs/concepts/application_shell.md](/concepts/application_shell.md) |
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
| 65 | `_mmfdb_file_dependency` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 66 | `_mmfdb_group` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 67 | `_mmfdb_group_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 68 | `_mmfdb_label_score` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 69 | `_mmfdb_object` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 70 | `_mmfdb_object_acl` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 71 | `_mmfdb_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 72 | `_mmfdb_operation_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 73 | `_mmfdb_operation_parameter_def` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 74 | `_mmfdb_optical_property` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 75 | `_mmfdb_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 76 | `_mmfdb_pipeline` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 77 | `_mmfdb_pipeline_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 78 | `_mmfdb_pipeline_node` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 79 | `_mmfdb_pipeline_run` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 80 | `_mmfdb_pipeline_run_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 81 | `_mmfdb_probe` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 82 | `_mmfdb_protocol` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 83 | `_mmfdb_provenance_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 84 | `_mmfdb_provenance_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 85 | `_mmfdb_provenance_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 86 | `_mmfdb_provenance_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 87 | `_mmfdb_reagent_lot` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 88 | `_mmfdb_reagent_usage` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 89 | `_mmfdb_record` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 90 | `_mmfdb_session` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 91 | `_mmfdb_setup` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 92 | `_mmfdb_setup_calibration` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 93 | `_mmfdb_setup_detector_channel` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 94 | `_mmfdb_setup_fcs_pair` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 95 | `_mmfdb_setup_pie_window` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 96 | `_mmfdb_spectrum` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 97 | `_mmfdb_state_transition` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 98 | `_mmfdb_state_transition_rule` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 99 | `_mmfdb_study` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 100 | `_mmfdb_study_key_value` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 101 | `_mmfdb_study_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 102 | `_mmfdb_units` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 103 | `_mmfdb_vocabulary` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 104 | `_mmfdb_workflow` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 105 | `_mmfdb_workflow_step` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 106 | `_struct_ref` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 107 | How precise is the distance? | $E$, $6E(1-E)$, $\Delta R/R$ for $\Delta E = 0.02$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 108 | How precise is the distance? | error in $J$ or $Q_D$, effect on $R_0$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 109 | How precise is the distance? | $\kappa^2$, $R$ scaled by, situation | [docs/concepts/fret.md](/concepts/fret.md) |
| 110 | 2. Streams and the burst search | Quantity, Definition | [docs/concepts/fret_check.md](/concepts/fret_check.md) |
| 111 | 4. The quality checks | Check, Value, ok / warn / bad | [docs/concepts/fret_check.md](/concepts/fret_check.md) |
| 112 | 4. The quality checks | Check, Value, ok / warn / bad | [docs/concepts/fret_check.md](/concepts/fret_check.md) |
| 113 | Linking is not fixing | asserts, uses data, keeps its uncertainty | [docs/concepts/global_analysis.md](/concepts/global_analysis.md) |
| 114 | Decoding: "most likely path" is not "how the photons distribute" | decoder, draws from, photon distribution, dwell / transition structure | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 115 | What H2MM can and cannot resolve | $K$, $k$ ($P=2$, DD/DA), $k$ ($P=3$, with AA) | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 116 | When to use something else | Situation, Better tool | [docs/concepts/hidden_markov_models.md](/concepts/hidden_markov_models.md) |
| 117 | HYDROPRO | INDMODE, primary model, calculation, AER | [docs/concepts/hydrodynamics.md](/concepts/hydrodynamics.md) |
| 118 | Worked numbers | Step, Lag time, Ratio to previous | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 119 | Which method is which | RICS, STICS, TICS, iMSD | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 120 | Using it in ChiSurf | Release this, To fit | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 121 | The burst folder | operation, ending | [docs/concepts/legacy_export.md](/concepts/legacy_export.md) |
| 122 | The ALEX-Suite CSVs | file, content | [docs/concepts/legacy_export.md](/concepts/legacy_export.md) |
| 123 | Schema and extras | Attribute, Meaning | [docs/concepts/metadata_editor.md](/concepts/metadata_editor.md) |
| 124 | Schema and extras | Schema, Factory, Typed fields | [docs/concepts/metadata_editor.md](/concepts/metadata_editor.md) |
| 125 | What a host gets back | Host, Schema, On Apply | [docs/concepts/metadata_editor.md](/concepts/metadata_editor.md) |
| 126 | What the gate actually tested | quantity, measured / model-free, forward model | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 127 | Testing it against simulated dynamics | regime, true rate, fitted, bursts between the states | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 128 | Three sources, one model | source, what it uses, what it is for | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 129 | Choosing a density | `dot_density`, points per atom, typical error | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 130 | What the peak time means | transport, peak of $G(\tau,\delta)$, scaling | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 131 | Reading the numbers | what you see, what it means | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 132 | Three uncertainty estimates, in increasing generality | Method, What it does, Assumes | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 133 | Why the proposal matters so much | Sampler, Proposal, $\tau$, Effective samples per 1000 model evaluations | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 134 | Collapsing: integrate the private parameters out | Sampler, τ(shared), min ESS, ESS / 1000 evals, reported $a$ | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 135 | Changing your mind about a prior, without sampling again | $\hat k$, meaning | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 136 | The numbers you actually publish | lower arm, upper arm | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 137 | Three stages, three failure modes | stage, question, how it fails | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 138 | Why a wavelet, and why two scales | threshold, 128², 256², 512² | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 139 | Why the histogram carries brightness | sample, $\epsilon$, $N$, $\epsilon T$, $\langle k\rangle$, $\mathrm{Var}-\langle k\rangle$, $B$ | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 140 | How much heterogeneity can PDA actually detect? | $N$ (photons/burst), 20, 50, 100, 200, 500 | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 141 | How much heterogeneity can PDA actually detect? | $\sigma_\text{het}$, $\sigma_\text{obs}$ at $N=50$, at $N=200$, ratio | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 142 | What a burst looks like | symbol, excitation → detection | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 143 | Excitation, transfer, emission | matrix, shape, meaning | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 144 | The problem with histograms | exchange, histogram, what you can measure | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 145 | Relation to H2MM | H2MM, Gopich–Szabo | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 146 | What ChiSurf writes, and what it only reads | what, where it goes | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 147 | The scalar focus: the Airy pattern | Feature, Where, Distance | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 148 | What ChiSurf computes | Model / pupil state, FWHM $x$, FWHM $y$, FWHM $z$ | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 149 | What ChiSurf computes | NA, medium, lateral: vectorial vs $0.514\,\lambda/\mathrm{NA}$, axial: vectorial vs $0.886\,\lambda/(n-\sqrt{n^2-\mathrm{NA}^2})$ | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 150 | Energy | Name, Term | [docs/concepts/protein_monte_carlo.md](/concepts/protein_monte_carlo.md) |
| 151 | Quenching inference: stickiness and quench strength from measured lifetimes | level, data, gives | [docs/concepts/quenching_inference.md](/concepts/quenching_inference.md) |
| 152 | Where the dye sits: three ensembles | $s$, equilibrium (static), PDE, walk from $p(x)$, fast exchange | [docs/concepts/quenching_inference.md](/concepts/quenching_inference.md) |
| 153 | Stages | stage, data, role | [docs/concepts/quenching_inference.md](/concepts/quenching_inference.md) |
| 154 | MalE results (stored run) | dye, quench scale κ (68 %), stickiest group, model error, outlier sites, rms / median \, dev\ | [docs/concepts/quenching_inference.md](/concepts/quenching_inference.md) |
| 155 | MalE refit on the corrected geometry | data set, stored run (old tables), refit, `full` preset, refit, `quick` preset | [docs/concepts/quenching_inference.md](/concepts/quenching_inference.md) |
| 156 | FRET along a trajectory | averaging, $\kappa^2 = 2/3$, $\kappa^2$ per frame ($\langle\kappa^2\rangle$ = 0.574) | [docs/concepts/structure_trajectories.md](/concepts/structure_trajectories.md) |
| 157 | Where this connects in ChiSurf | Question, Page | [docs/concepts/super_resolution.md](/concepts/super_resolution.md) |
| 158 | How many components? | Rule, Referred to, $R$ needed at 68 %, at 95 % | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 159 | Two kinds of pane | Pane, What runs, Needs | [docs/concepts/terminal.md](/concepts/terminal.md) |
| 160 | What a Python pane has in scope | Name, What it is | [docs/concepts/terminal.md](/concepts/terminal.md) |
| 161 | The two clocks of a photon record | clock, scale, wraps, builds | [docs/concepts/tttr_stream_tools.md](/concepts/tttr_stream_tools.md) |
| 162 | The four streams, and what they are for | stream, excitation, emission, used for | [docs/concepts/us_alex.md](/concepts/us_alex.md) |
| 163 | The tool registry | Tier, Tools (examples), Effect | [docs/concepts/workflow_agent.md](/concepts/workflow_agent.md) |
| 164 | The burst-to-distance chain | Tool, Runs, Reports | [docs/concepts/workflow_agent.md](/concepts/workflow_agent.md) |
| 165 | Surfaces | Surface, Start, Serves | [docs/concepts/workflow_agent.md](/concepts/workflow_agent.md) |
| 166 | In the GUI: the same-molecule probability | Control, Default, Meaning | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 167 | In ChiSurf | Control, Default, Meaning | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 168 | Which tool for which clock | tool, acts on, guide | [docs/guides/101_photon_data_tools.md](/guides/101_photon_data_tools.md) |
| 169 | 3. Simulate and read | tab, content | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 170 | 2. Run it | Option, Meaning | [docs/guides/106_protein_monte_carlo.md](/guides/106_protein_monte_carlo.md) |
| 171 | 2. Photons and markers | Kind, What it is, Colour | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 172 | 3. Navigate and filter | Control, Effect | [docs/guides/108_photon_table.md](/guides/108_photon_table.md) |
| 173 | Keys | Key, Where, Does | [docs/guides/110_terminal.md](/guides/110_terminal.md) |
| 174 | 1. Load the data | file, content | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 175 | 2. Choose the settings | control, meaning | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 176 | 2. Choose the settings | stage, data, role | [docs/guides/111_quenching_analysis.md](/guides/111_quenching_analysis.md) |
| 177 | 3. Export | Button, Writes | [docs/guides/112_fret_check.md](/guides/112_fret_check.md) |
| 178 | Reading bursts | Entry, Read as | [docs/guides/11_pda2c.md](/guides/11_pda2c.md) |
| 179 | Open the tool | Control, Default, Meaning | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 180 | Choosing a decoder | *Decoder*, what it does, use it for | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 181 | Per-state decays | Column, Meaning | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 182 | The Burst MLE tool | Model, Inputs in parameter order, Interpretation | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 183 | The lifetime of a state, not of a burst | Detector, Colour, State, Photons (parallel), Photons (perpendicular), Photons, Tau, 2I*, … | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 184 | Trace Browser | Button, What it does | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 185 | Result | table, one row per, columns | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 186 | 5. Choosing a sampler | `method`, Use when | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 187 | 9. Reusing a chain under a different prior | `pareto_k`, what to do | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 188 | 15. Error bars on the quantities you publish | Method, What it is, Read the interval as | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 189 | Setting it up | Provider, Base URL, Processing location, Key from | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 190 | Things to ask it | Ask it, What it does | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 191 | Using it in the GUI | Mode, What it can do | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 192 | Walkthrough: from bursts to a distance distribution | Step, Tool, What to read in its result | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 193 | Skills: how it knows *how* | Skill, Loaded when you ask about | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 194 | 2. Check the channel mapping | combo, channel | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 195 | Naming differences to watch | ndX, meaning, Hellenkamp | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 196 | Trying it without data (and checking it works) | factor, declared, recovered | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 197 | Loading data | reader, use it for | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 198 | Loading and looking | Repository, Looks like, Gives you | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 199 | A simulation is more than motion | What the file says, What you see | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 200 | The Map panel | Map, Opens at, Why | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 201 | Trying it out: the Demo menu | Entry, What it shows | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 202 | Selecting with the mouse | Gesture, Action, Effect | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 203 | Measuring by clicking | Control, What it does | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 204 | Polar contacts | `mode`, What it draws | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 205 | Hydrogen-bond networks | Argument, Meaning | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 206 | Mutating a residue | Detail, What happens | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 207 | Where things stand | Area, State | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 208 | Read the result | Predicted error, Verdict, What to do | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 209 | Play the measurement back | Control, What it does | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 210 | What it does | Bridge, ChiSurf RPC, Produces | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 211 | Where regions appear | Tool, What a region does there | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 212 | 1. Detect | what you see, what it means | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 213 | The menu is not a list ndX keeps | Target, RPC, What comes back | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 214 | What counts as a change | Step, Reuses when, Recomputes when | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 215 | Everything downstream is handed the same files | Panel, Receives | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 216 | Settings reference | Setting, What it does | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 217 | Which route to use | you want, use, resolution | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 218 | 1. Open the calculator and pick a scheme | Scheme, States, Use it for | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 219 | 3. A worked case: Rhodamine 6G at 488 nm | Power, k_exc(0,0), V_eff/V₀, apparent τ_D, G(0) vs unsaturated, no bunching | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 220 | 1. Load the folder | Setting, What it does | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 221 | 3. Set the two controls | Control, Question, How to choose | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 222 | 3. Set the two controls | Threshold, Window, Bursts, Proximity-ratio width | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 223 | 4. Judge it from the summary, not from the burst count | Row, Expected, What it means if not | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 224 | What is already in scope | Name, What it is | [docs/guides/59_console.md](/guides/59_console.md) |
| 225 | What you need first | Field, Measure it on | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 226 | Step 3 — read the right number | Reading, What it means | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 227 | Step 4 — the step that decides whether you can publish it | Outcome, Reading | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 228 | What is in it | column, what it is | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 229 | The toolbar | Control, What it does | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 230 | Where each window went | ALEX-Suite, here | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 231 | 3 — Alternation, measured rather than typed | stream, burst-table column | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 232 | If it will not answer | It says, What to do | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 233 | Export | Format, Contents, For | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 234 | Find the levels (HMM tab) | Path, Content | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 235 | The settings file beside every `.cor` | Key, What it holds | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 236 | The `.cor` file | Column, Content | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 237 | Converting correlation files | Readers (`-it`), Writers (`-ot`) | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 238 | Open the tools | Tool, Opens from, What it does, Guide | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 239 | Settings | Key, Default, Meaning | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 240 | The component-count scan | True decay, `noise_model`, Chosen $n$ (seeds 1, 2, 3), Recovered | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 241 | VV/VH: lifetimes and rotations together | Truth, Seeds, Recovered | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 242 | Reading it: the case where the tests disagree | comparison, $\chi^2_r$, tool confidence, $\chi^2_{r,2}$ needed at 95 %, extra-SS $F$ ($p$), $\Delta$AIC | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 243 | Where results go | item, $\tau_1$ (ns), $\tau_2$ (ns), $\langle\tau\rangle_x$ (ns), $\langle\tau\rangle_F$ (ns), $\chi^2_r$ | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 244 | The standard lines | Line, Components, Vary, Range | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 245 | 1. Open the Spectra Downloader | panel, what it does | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 246 | 2. Where the spectra come from, and the terms they come under | source, carries, terms | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 247 | 5. Check it against published values | pair, spectra, $Q_D$, ε_max (M⁻¹ cm⁻¹), $J$ (M⁻¹ cm⁻¹ nm⁴), $R_0$ ChiSurf, $R_0$ table | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 248 | 2. Settings | workflow, method, for | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 249 | 2. Settings | control, meaning | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 250 | 3. A real image | workflow, regions | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 251 | 3. A real image | threshold, 0.05, 5, 20, 50, 100 | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 252 | 1. Where it is | control, what it does | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 253 | 2. What it checks | line of the report, what was done | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 254 | 2. What it checks | detector, channels, micro-time window | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 255 | 6. Export | button, writes | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 256 | 8. Where things go wrong | symptom, cause | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 257 | 1. The page | Where, Control, What it does | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 258 | 2. Mix | Window, Control, What it does | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 259 | 2. Keys and pointer | Game, Keys, Pointer | [docs/guides/95_games.md](/guides/95_games.md) |
| 260 | 3. Read the table | Column, Means | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 261 | 1. The window | Where, Control, What it does | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 262 | 2. The destinations | Destination, Panel, Figure | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 263 | 2. The list | Group, Steps | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 264 | 3. Windows, backgrounds, shifts | Field, Meaning | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 265 | The correction | factor, symbol, meaning | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 266 | Compute engines | engine, description, accuracy | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 267 | Where each guide starts in ChiSurf | Guide, ChiSurf entry point | [docs/guides/index.md](/guides/index.md) |
| 268 | One way in: dropping files | Experiment, What it holds, How a dropped file becomes one | [docs/manual/data_import.md](/manual/data_import.md) |
| 269 | Fit Plots | Control, What it does | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 270 | Convolution modes | Mode, Use it for | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 271 | Arranging the windows | Command, What it does | [docs/manual/multiple_document_interface.md](/manual/multiple_document_interface.md) |
| 272 | From the shell | `method`, When to use it | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 273 | Parameters | Parameter, Meaning | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 274 | Parameters | Parameter, Meaning | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 275 | Code index | #, Language, Section, Lines, Verified, Page | [docs/reference/code.md](/reference/code.md) |
| 276 | Figure index | #, Image, Caption, Origin, Page | [docs/reference/figures.md](/reference/figures.md) |
| 277 | SdtFile | Attribute, Content | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 278 | BeckerHicklSetReader | Member, Content | [docs/reference/file_formats/becker_hickl_files.md](/reference/file_formats/becker_hickl_files.md) |
| 279 | Properties | Property, Definition, Unit | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 280 | Parameters | Name, Meaning | [docs/reference/file_formats/becker_hickl_set.md](/reference/file_formats/becker_hickl_set.md) |
| 281 | FCS file formats | Reader, `experiment_reader`, Files | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 282 | Column layout (write side) | Column, Content | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 283 | FCS-CSV (generic ASCII) | Column, Content | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 284 | One file, many curves | curve type, meaning | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 285 | China FCS MATLAB `.mat` | Correlation, Intensity, Curve | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 286 | The setting that chooses the method | Setting, What you get | [docs/reference/file_formats/ics_files.md](/reference/file_formats/ics_files.md) |
| 287 | R_DA axis settings | Key, Meaning, Shipped | [docs/reference/file_formats/rda_axis_settings.md](/reference/file_formats/rda_axis_settings.md) |
| 288 | Format, columns and errors | Format, Reads | [docs/reference/file_formats/tcspc_files.md](/reference/file_formats/tcspc_files.md) |
| 289 | Reading a parameter table | Appearance, Meaning | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 290 | Parameter glossary | Parameter, Meaning, Keywords | [docs/reference/parameters.md](/reference/parameters.md) |
| 291 | Identity | Field, Value | [docs/reference/plugins/about.md](/reference/plugins/about.md) |
| 292 | Identity | Field, Value | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 293 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 294 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 295 | Dyes (database) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 296 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 297 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 298 | Optics prior (light path) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 299 | Procedure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 300 | Identity | Field, Value | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 301 | Device session | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 302 | Routing and output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 303 | Simulator configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 304 | Result visibility | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 305 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 306 | CFD | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 307 | Sync | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 308 | TAC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 309 | Timing | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 310 | Mode | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 311 | Hardware acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 312 | SPC file output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 313 | Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 314 | Correlation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 315 | Count rate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 316 | MCS | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 317 | Macrotime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 318 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 319 | Sample & brightness | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 320 | Geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 321 | Microtime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 322 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 323 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 324 | Identity | Field, Value | [docs/reference/plugins/agent.md](/reference/plugins/agent.md) |
| 325 | Identity | Field, Value | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 326 | API Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 327 | Models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 328 | Generation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 329 | Identity | Field, Value | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 330 | Fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 331 | Burst filters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 332 | Identity | Field, Value | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 333 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 334 | Files & fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 335 | Run | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 336 | Identity | Field, Value | [docs/reference/plugins/bid_to_analysis.md](/reference/plugins/bid_to_analysis.md) |
| 337 | Identity | Field, Value | [docs/reference/plugins/boarding.md](/reference/plugins/boarding.md) |
| 338 | Identity | Field, Value | [docs/reference/plugins/breakout.md](/reference/plugins/breakout.md) |
| 339 | Identity | Field, Value | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 340 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 341 | Identity | Field, Value | [docs/reference/plugins/burst_analysis.md](/reference/plugins/burst_analysis.md) |
| 342 | Identity | Field, Value | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 343 | Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 344 | Fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 345 | Identity | Field, Value | [docs/reference/plugins/burst_browser.md](/reference/plugins/burst_browser.md) |
| 346 | Identity | Field, Value | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 347 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 348 | Identity | Field, Value | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 349 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 350 | Select Series | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 351 | Crop | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 352 | Select States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 353 | States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 354 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 355 | Number of States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 356 | Time Series Group | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 357 | Expected Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 358 | Prior Strength | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 359 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 360 | Identity | Field, Value | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 361 | Correlator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 362 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 363 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 364 | Identity | Field, Value | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 365 | Fusion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 366 | P(same molecule) estimate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 367 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 368 | Identity | Field, Value | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 369 | Photons | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 370 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 371 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 372 | Extras | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 373 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 374 | Identity | Field, Value | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 375 | Data | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 376 | Model selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 377 | Optimisation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 378 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 379 | Burst | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 380 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 381 | Identity | Field, Value | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 382 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 383 | Identity | Field, Value | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 384 | Burst files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 385 | Detector and window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 386 | Measured IRF and background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 387 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 388 | H2MM states | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 389 | Burst | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 390 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 391 | Identity | Field, Value | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 392 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 393 | Burst search | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 394 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 395 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 396 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 397 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 398 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 399 | Scatter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 400 | GMM settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 401 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 402 | Identity | Field, Value | [docs/reference/plugins/burstwise_import.md](/reference/plugins/burstwise_import.md) |
| 403 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burstwise_import.md](/reference/plugins/burstwise_import.md) |
| 404 | Identity | Field, Value | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 405 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 406 | Identity | Field, Value | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 407 | File | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 408 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 409 | Brush & Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 410 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 411 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 412 | Identity | Field, Value | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 413 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 414 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 415 | Identity | Field, Value | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 416 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 417 | Identity | Field, Value | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 418 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 419 | Identity | Field, Value | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 420 | F-test — compare two nested models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 421 | χ²-max — upper limit from one fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 422 | Identity | Field, Value | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 423 | Species | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 424 | Kinetics / statistics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 425 | Identity | Field, Value | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 426 | Diffusion / volume | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 427 | Occupancy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 428 | Constraint (choose one) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 429 | Reference dye (D @ 25 °C, water) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 430 | Molecular shape | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 431 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 432 | Identity | Field, Value | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 433 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 434 | Identity | Field, Value | [docs/reference/plugins/fcs_convert.md](/reference/plugins/fcs_convert.md) |
| 435 | Identity | Field, Value | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 436 | Correlation Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 437 | Correlation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 438 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 439 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 440 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 441 | Change-point parameters (BOCPD / Kalman / CUSUM) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 442 | Plot settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 443 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 444 | Identity | Field, Value | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 445 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 446 | Mixed decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 447 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 448 | Auto-fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 449 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 450 | Identity | Field, Value | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 451 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 452 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 453 | Identity | Field, Value | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 454 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 455 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 456 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 457 | Identity | Field, Value | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 458 | 2D-FDC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 459 | Lifetime inversion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 460 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 461 | Dynamics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 462 | Kinetics (advanced) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 463 | 1D-MEM + Gaussian | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 464 | Simulator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 465 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 466 | Identity | Field, Value | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 467 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 468 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 469 | Identity | Field, Value | [docs/reference/plugins/fret_check.md](/reference/plugins/fret_check.md) |
| 470 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_check.md](/reference/plugins/fret_check.md) |
| 471 | Identity | Field, Value | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 472 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 473 | Docking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 474 | Monte-Carlo (mc method only) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 475 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 476 | Candidate sites from residues | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 477 | Efficiency | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 478 | Selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 479 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 480 | Identity | Field, Value | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 481 | Your dyes | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 482 | Components | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 483 | Sweep | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 484 | Identity | Field, Value | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 485 | Toolbar | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 486 | View | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 487 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 488 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 489 | Identity | Field, Value | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 490 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 491 | Identity | Field, Value | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 492 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 493 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 494 | State scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 495 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 496 | Identity | Field, Value | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 497 | Executable & input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 498 | Primary model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 499 | Solvent & macromolecule | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 500 | Optional calculations | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 501 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 502 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 503 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 504 | Identity | Field, Value | [docs/reference/plugins/imaging_common.md](/reference/plugins/imaging_common.md) |
| 505 | Identity | Field, Value | [docs/reference/plugins/imaging_tools.md](/reference/plugins/imaging_tools.md) |
| 506 | Identity | Field, Value | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 507 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 508 | Identity | Field, Value | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 509 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 510 | Background / thresholds | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 511 | Scatter gate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 512 | Region of interest | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 513 | Objects (punctate signal) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 514 | Significance / profile | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 515 | Identity | Field, Value | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 516 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 517 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 518 | Identity | Field, Value | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 519 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 520 | Scanner | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 521 | Display and estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 522 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 523 | Identity | Field, Value | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 524 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 525 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 526 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 527 | Identity | Field, Value | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 528 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 529 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 530 | Identity | Field, Value | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 531 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 532 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 533 | Identity | Field, Value | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 534 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 535 | IRF preparation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 536 | Fit flags | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 537 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 538 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 539 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 540 | Fit parameters (fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 541 | Fit parameters (fit24) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 542 | Fit parameters (fit25) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 543 | Lifetime map | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 544 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 545 | Identity | Field, Value | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 546 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 547 | Stack corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 548 | Detector | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 549 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 550 | Parameter plane / gates | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 551 | Cross N&B | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 552 | Identity | Field, Value | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 553 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 554 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 555 | IRF reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 556 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 557 | Identity | Field, Value | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 558 | Movie | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 559 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 560 | 1. Detect | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 561 | 2. Link | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 562 | 3. Transport | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 563 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 564 | Core | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 565 | File → Data | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 566 | Help | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 567 | Setup | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 568 | Spectroscopy → Correlation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 569 | Spectroscopy → Decay | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 570 | Spectroscopy → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 571 | Spectroscopy → Imaging | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 572 | Spectroscopy → Imaging → Lifetime | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 573 | Spectroscopy → Imaging → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 574 | Spectroscopy → Kinetics | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 575 | Spectroscopy → Single-Molecule | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 576 | Structure → Computation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 577 | Structure → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 578 | Structure → Modelling | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 579 | Structure → Trajectory | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 580 | Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 581 | Tools → Calculators | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 582 | Tools → Games | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 583 | Tools → Miscellaneous | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 584 | Tools → Photon data | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 585 | Tools → System | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 586 | Tools → TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 587 | Tools → Views | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 588 | Tools → Wizards | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 589 | Uncategorized | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 590 | Identity | Field, Value | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 591 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 592 | Time Window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 593 | Histogram Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 594 | HMM Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 595 | Identity | Field, Value | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 596 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 597 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 598 | Identity | Field, Value | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 599 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 600 | Anisotropy Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 601 | Calculation Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 602 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 603 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 604 | Identity | Field, Value | [docs/reference/plugins/legacy_export.md](/reference/plugins/legacy_export.md) |
| 605 | Identity | Field, Value | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 606 | Graph view | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 607 | Backend | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 608 | MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 609 | Connections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 610 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 611 | Identity | Field, Value | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 612 | Input Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 613 | Fitting Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 614 | Anisotropy (VV/VH) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 615 | Identity | Field, Value | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 616 | MEM settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 617 | Lifetime grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 618 | Distance grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 619 | Periodic convolution | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 620 | Instrument | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 621 | Nuisance optimization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 622 | L-curve | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 623 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 624 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 625 | Identity | Field, Value | [docs/reference/plugins/menu_switch.md](/reference/plugins/menu_switch.md) |
| 626 | Identity | Field, Value | [docs/reference/plugins/metadata_editor.md](/reference/plugins/metadata_editor.md) |
| 627 | Identity | Field, Value | [docs/reference/plugins/mfd_prepare.md](/reference/plugins/mfd_prepare.md) |
| 628 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mfd_prepare.md](/reference/plugins/mfd_prepare.md) |
| 629 | Identity | Field, Value | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 630 | Run | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 631 | Detector and channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 632 | Reading and gates | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 633 | Time step, G-factor and shifts | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 634 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 635 | Identity | Field, Value | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 636 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 637 | Entity | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 638 | Probes | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 639 | Alignment | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 640 | Shifts | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 641 | Save | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 642 | MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 643 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 644 | Identity | Field, Value | [docs/reference/plugins/minesweeper.md](/reference/plugins/minesweeper.md) |
| 645 | Identity | Field, Value | [docs/reference/plugins/mle_common.md](/reference/plugins/mle_common.md) |
| 646 | Identity | Field, Value | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 647 | Connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 648 | Choose | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 649 | Enter a value | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 650 | Change password | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 651 | Jump to branch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 652 | Overview | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 653 | All items | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 654 | Measurements | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 655 | Sample Metadata | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 656 | Detail | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 657 | Spectra | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 658 | Provenance Graph | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 659 | Import / Export | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 660 | eLabFTW connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 661 | eLabFTW | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 662 | Import into MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 663 | Export from MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 664 | Studies | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 665 | Protocols | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 666 | Lifecycle | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 667 | Register calibration value | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 668 | Reagent Lots | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 669 | Add lot | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 670 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 671 | Advanced — user & connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 672 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 673 | Identity | Field, Value | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 674 | Registered models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 675 | Selected model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 676 | Identity | Field, Value | [docs/reference/plugins/ndxplorer.md](/reference/plugins/ndxplorer.md) |
| 677 | Identity | Field, Value | [docs/reference/plugins/number_quest.md](/reference/plugins/number_quest.md) |
| 678 | Identity | Field, Value | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 679 | Data settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 680 | Model fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 681 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 682 | Identity | Field, Value | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 683 | Excitation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 684 | Reference geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 685 | Two-component line | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 686 | Mixing region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 687 | Cursor | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 688 | Identity | Field, Value | [docs/reference/plugins/photon_table.md](/reference/plugins/photon_table.md) |
| 689 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/photon_table.md](/reference/plugins/photon_table.md) |
| 690 | Identity | Field, Value | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 691 | Curves | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 692 | Fit range | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 693 | Global fits | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 694 | Axes and grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 695 | Show | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 696 | Node graphs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 697 | Identity | Field, Value | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 698 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 699 | Identity | Field, Value | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 700 | Installed plugins | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 701 | Selected plugin | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 702 | Plugin Manager | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 703 | Icon | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 704 | Identity | Field, Value | [docs/reference/plugins/pong.md](/reference/plugins/pong.md) |
| 705 | Identity | Field, Value | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 706 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 707 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 708 | Identity | Field, Value | [docs/reference/plugins/project_data.md](/reference/plugins/project_data.md) |
| 709 | Identity | Field, Value | [docs/reference/plugins/proteinmc.md](/reference/plugins/proteinmc.md) |
| 710 | Identity | Field, Value | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 711 | Objective | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 712 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 713 | Polarization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 714 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 715 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 716 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 717 | Identity | Field, Value | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 718 | PSF parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 719 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 720 | Fit Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 721 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 722 | Identity | Field, Value | [docs/reference/plugins/pto_inspector.md](/reference/plugins/pto_inspector.md) |
| 723 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pto_inspector.md](/reference/plugins/pto_inspector.md) |
| 724 | Identity | Field, Value | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 725 | Formats | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 726 | ALEX modulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 727 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 728 | Input file | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 729 | Excitation regions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 730 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 731 | Identity | Field, Value | [docs/reference/plugins/python_terminal.md](/reference/plugins/python_terminal.md) |
| 732 | Identity | Field, Value | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 733 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 734 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 735 | Structure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 736 | Dye | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 737 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 738 | Quenching | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 739 | FRET | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 740 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 741 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 742 | Identity | Field, Value | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 743 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 744 | Regions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 745 | Fit (Fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 746 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 747 | Identity | Field, Value | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 748 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 749 | Optics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 750 | Scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 751 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 752 | Identity | Field, Value | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 753 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 754 | Advanced Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 755 | Device Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 756 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 757 | Geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 758 | Microtime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 759 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 760 | Interface | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 761 | Editor and console | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 762 | Documentation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 763 | Formulas | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 764 | Rendering | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 765 | Identity | Field, Value | [docs/reference/plugins/setup_channel_definition.md](/reference/plugins/setup_channel_definition.md) |
| 766 | Identity | Field, Value | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 767 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 768 | Advanced — connection & authentication | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 769 | Identity | Field, Value | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 770 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 771 | Detector | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 772 | Spot width (log / dog) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 773 | Filters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 774 | Pick by clicking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 775 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 776 | Identity | Field, Value | [docs/reference/plugins/style_manager.md](/reference/plugins/style_manager.md) |
| 777 | Identity | Field, Value | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 778 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 779 | Identity | Field, Value | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 780 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 781 | IRF & noise | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 782 | Anisotropy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 783 | VV/VH detection corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 784 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 785 | Identity | Field, Value | [docs/reference/plugins/terminal.md](/reference/plugins/terminal.md) |
| 786 | Identity | Field, Value | [docs/reference/plugins/tetris.md](/reference/plugins/tetris.md) |
| 787 | Identity | Field, Value | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 788 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 789 | Reader settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 790 | Background region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 791 | Instrument corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 792 | Lifetime spectrum | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 793 | Rotation spectrum | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 794 | Identity | Field, Value | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 795 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 796 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 797 | Identity | Field, Value | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 798 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 799 | Identity | Field, Value | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 800 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 801 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 802 | Identity | Field, Value | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 803 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 804 | Identity | Field, Value | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 805 | Reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 806 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 807 | Identity | Field, Value | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 808 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 809 | Identity | Field, Value | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 810 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 811 | Identity | Field, Value | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 812 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 813 | Identity | Field, Value | [docs/reference/plugins/traj_save_topology.md](/reference/plugins/traj_save_topology.md) |
| 814 | Identity | Field, Value | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 815 | Audio | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 816 | Waterfall params | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 817 | Micro-time | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 818 | Lifetime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 819 | Identity | Field, Value | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 820 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 821 | Identity | Field, Value | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 822 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 823 | Identity | Field, Value | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 824 | Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 825 | Toolbar | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 826 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 827 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 828 | Identity | Field, Value | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 829 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 830 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 831 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 832 | LUT flow | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 833 | Compute LUT | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 834 | settings.tttr.json | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 835 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 836 | Identity | Field, Value | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 837 | Input / Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 838 | Split options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 839 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 840 | Identity | Field, Value | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 841 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 842 | Identity | Field, Value | [docs/reference/plugins/tttr_to_pto.md](/reference/plugins/tttr_to_pto.md) |
| 843 | Identity | Field, Value | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 844 | Installed Packages | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 845 | Search & Install | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 846 | ChiSurf Package Manager | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 847 | Installed version | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 848 | Startup behavior | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 849 | Update | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 850 | ChiSurf Updater | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 851 | Identity | Field, Value | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 852 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 853 | Identity | Field, Value | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 854 | VV/VH anisotropy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 855 | Correction | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 856 | r-infinity region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 857 | Identity | Field, Value | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 858 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 859 | Tail matching | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 860 | Polarization mixing | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 861 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 862 | Sample decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 863 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 864 | Identity | Field, Value | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 865 | New record | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 866 | Add data | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 867 | Sent to Zenodo (JSON) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 868 | Build from a project script | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 869 | 2 · Review | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 870 | Before upload | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 871 | Draft | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 872 | DOI & publish | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 873 | Token | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/zenodo_deposit.md](/reference/plugins/zenodo_deposit.md) |
| 874 | 1.5.2.1 `gui.console` | Key, Default, Meaning | [docs/reference/settings.md](/reference/settings.md) |
| 875 | Table index | #, Section, Columns, Page | [docs/reference/tables.md](/reference/tables.md) |
| 876 | User-Defined Models in ChiSurf | What it does, Use it when | [docs/reference/user_models.md](/reference/user_models.md) |
| 877 | 5.1 Using the code view | Control, What it does | [docs/reference/user_models.md](/reference/user_models.md) |
