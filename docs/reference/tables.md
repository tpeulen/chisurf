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

*820 tables.*

| # | Section | Columns | Page |
| --- | --- | --- | --- |
| 1 | Entry points | Command, Purpose | [docs/getting_started/index.md](/getting_started/index.md) |
| 2 | What happens before emission | Process, Timescale | [docs/fundamentals/absorption_and_emission.md](/fundamentals/absorption_and_emission.md) |
| 3 | The excited state | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 4 | Anisotropy | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 5 | FRET | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 6 | FCS | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 7 | Units | Quantity, Unit | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 8 | Fundamentals (photophysics) | Layer, Question | [docs/fundamentals/index.md](/fundamentals/index.md) |
| 9 | Detectors | Detector, Timing resolution, Notes | [docs/fundamentals/instrumentation.md](/fundamentals/instrumentation.md) |
| 10 | \eta_d = \tfrac{1}{2}\,\Gamma\!\left(1 - \tfrac{d}{6}\right)\frac{C}{C_0}, | Dimensionality, Physical case, Exponent, $C_0$, $\eta_d$ at $C=C_0$ | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 11 | Choosing the geometry: fit all three | Simulated, Fitted as 1-D, Fitted as 2-D, Fitted as 3-D | [docs/concepts/acceptor_density.md](/concepts/acceptor_density.md) |
| 12 | \qquad (E \approx 0.58). | $\langle R_{DA}\rangle$, $\sigma = 3$ Å, $\sigma = 6$ Å, $\sigma = 10$ Å, $\sigma = 15$ Å | [docs/concepts/accessible_volume.md](/concepts/accessible_volume.md) |
| 13 | The four factors | channel, alias, what it holds | [docs/concepts/accurate_fret.md](/concepts/accurate_fret.md) |
| 14 | \approx 10\ \mathrm{ns}. | system, $\rho$, $\tau/\rho$, $r/r_0$ | [docs/concepts/anisotropy.md](/concepts/anisotropy.md) |
| 15 | The cost: a fused burst is one interval | Control, Question it answers | [docs/concepts/burst_fusion.md](/concepts/burst_fusion.md) |
| 16 | What to report | Report, Because | [docs/concepts/colocalization.md](/concepts/colocalization.md) |
| 17 | The iteration count is the regularisation | iterations, 5, 20, 100, 400 | [docs/concepts/deconvolution.md](/concepts/deconvolution.md) |
| 18 | Two things that quietly go wrong | support, 3.7 σ, 5.0 σ, 6.3 σ, 7.7 σ | [docs/concepts/deconvolution.md](/concepts/deconvolution.md) |
| 19 | The parameters, in the order that matters | Parameter, What it decides | [docs/concepts/density_clustering.md](/concepts/density_clustering.md) |
| 20 | Why drift is not just blur | Frame lag $\Delta$, $G(0,0,\Delta)$ uncorrected, corrected | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 21 | C(\xi, \psi) = \mathcal{F}^{-1}\bigl\{\, \mathcal{F}(a)\,\overline{\mathcal{F}(b)} \,\bigr\} | Reference, Behaviour | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 22 | The QuEst model | residue, $k_Q$ (1/ns), contact from dye surface (Å), $R_i$ from dye centre (Å), quenching centre | [docs/concepts/dye_quenching.md](/concepts/dye_quenching.md) |
| 23 | Why it hides | Observable, Effect of homo-transfer | [docs/concepts/energy_migration.md](/concepts/energy_migration.md) |
| 24 | The posterior factorises | operation, in canonical form | [docs/concepts/factor_graphs.md](/concepts/factor_graphs.md) |
| 25 | The model | Array, Meaning | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 26 | The second apparent diffusion time | Power, V_eff/V₀, apparent τ_D, one-component residual, two-component fit | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 27 | Fitting it: a global triplet times two diffusion times | amplitude, τ_D | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 28 | File tools: operations on the container, not the measurement | tool, does | [docs/concepts/file_tools.md](/concepts/file_tools.md) |
| 29 | Conditioning: the price of similar patterns | $\tau_2$, $\tau_2/\tau_1$, condition number, largest filter value | [docs/concepts/filtered_fcs.md](/concepts/filtered_fcs.md) |
| 30 | The four statistics | statistic, weight, notes | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 31 | Why the Neyman weighting is biased | counts per bin, Neyman (data-weighted), Pearson (model-weighted) | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 32 | \text{conf} = F_{\text{cdf}}\!\left(\frac{\chi^2_{r,1}}{\chi^2_{r,2}};\ \nu_1, \nu_2\right), | comparison, $\chi^2_r$, variance-ratio conf., extra-SS $F$, $p$, $\Delta$AIC | [docs/concepts/fitting_objectives.md](/concepts/fitting_objectives.md) |
| 33 | `_flr_analysis_feature` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 34 | `_flr_fit_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 35 | `_flr_fret_analysis` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 36 | `_flr_fret_calibration_parameters` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 37 | `_flr_fret_forster_radius` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 38 | `_flr_poly_probe_position` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 39 | `_flr_probe_descriptor` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 40 | `_flr_probe_list` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 41 | `_flr_sample` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 42 | `_flr_sample_condition` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 43 | `_flr_sample_probe_details` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 44 | `_ihm_chemical_component_descriptor` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 45 | `_ihm_external_files` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 46 | `_mmfdb_acl_entry` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 47 | `_mmfdb_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 48 | `_mmfdb_artifact_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 49 | `_mmfdb_artifact_owner` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 50 | `_mmfdb_audit_log` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 51 | `_mmfdb_auth_attempt` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 52 | `_mmfdb_branch` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 53 | `_mmfdb_bundle_document` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 54 | `_mmfdb_bundle_file` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 55 | `_mmfdb_burst_column` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 56 | `_mmfdb_column` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 57 | `_mmfdb_constant` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 58 | `_mmfdb_container` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 59 | `_mmfdb_derived_column` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 60 | `_mmfdb_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 61 | `_mmfdb_event_log` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 62 | `_mmfdb_group` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 63 | `_mmfdb_group_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 64 | `_mmfdb_label_score` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 65 | `_mmfdb_object` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 66 | `_mmfdb_object_acl` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 67 | `_mmfdb_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 68 | `_mmfdb_operation_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 69 | `_mmfdb_operation_parameter_def` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 70 | `_mmfdb_optical_property` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 71 | `_mmfdb_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 72 | `_mmfdb_pipeline` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 73 | `_mmfdb_pipeline_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 74 | `_mmfdb_pipeline_node` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 75 | `_mmfdb_pipeline_run` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 76 | `_mmfdb_pipeline_run_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 77 | `_mmfdb_probe` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 78 | `_mmfdb_protocol` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 79 | `_mmfdb_provenance_artifact` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 80 | `_mmfdb_provenance_edge` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 81 | `_mmfdb_provenance_operation` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 82 | `_mmfdb_provenance_parameter` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 83 | `_mmfdb_reagent_lot` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 84 | `_mmfdb_reagent_usage` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 85 | `_mmfdb_session` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 86 | `_mmfdb_setup` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 87 | `_mmfdb_setup_calibration` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 88 | `_mmfdb_setup_detector_channel` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 89 | `_mmfdb_setup_fcs_pair` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 90 | `_mmfdb_setup_pie_window` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 91 | `_mmfdb_spectrum` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 92 | `_mmfdb_state_transition` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 93 | `_mmfdb_state_transition_rule` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 94 | `_mmfdb_study` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 95 | `_mmfdb_study_key_value` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 96 | `_mmfdb_study_member` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 97 | `_mmfdb_units` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 98 | `_mmfdb_vocabulary` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 99 | `_mmfdb_workflow` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 100 | `_mmfdb_workflow_step` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 101 | `_struct_ref` | Item, Type, Description | [docs/concepts/flrcif_vocabulary.md](/concepts/flrcif_vocabulary.md) |
| 102 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | $E$, $6E(1-E)$, $\Delta R/R$ for $\Delta E = 0.02$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 103 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | error in $J$ or $Q_D$, effect on $R_0$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 104 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | $\kappa^2$, $R$ scaled by, situation | [docs/concepts/fret.md](/concepts/fret.md) |
| 105 | Linking is not fixing | asserts, uses data, keeps its uncertainty | [docs/concepts/global_analysis.md](/concepts/global_analysis.md) |
| 106 | Decoding: "most likely path" is not "how the photons distribute" | decoder, draws from, photon distribution, dwell / transition structure | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 107 | \qquad\text{here } 10^{3}\ \mathrm{s^{-1}} \dots 5\times10^{4}\ \mathrm{s^{-1}} . | $K$, $k$ ($P=2$, DD/DA), $k$ ($P=3$, with AA) | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 108 | When to use something else | Situation, Better tool | [docs/concepts/hidden_markov_models.md](/concepts/hidden_markov_models.md) |
| 109 | HYDROPRO | INDMODE, primary model, calculation, AER | [docs/concepts/hydrodynamics.md](/concepts/hydrodynamics.md) |
| 110 | Worked numbers | Step, Lag time, Ratio to previous | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 111 | Which method is which | Method, Region read, Clock that dominates, Scale | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 112 | Using it in ChiSurf | Release this, To fit | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 113 | What the gate actually tested | quantity, measured / model-free, forward model | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 114 | Testing it against simulated dynamics | regime, true rate, fitted, bursts between the states | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 115 | Three sources, one model | source, what it uses, what it is for | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 116 | Choosing a density | `dot_density`, points per atom, typical error | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 117 | What the peak time means | transport, peak of $G(\tau,\delta)$, scaling | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 118 | Reading the numbers | what you see, what it means | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 119 | Three uncertainty estimates, in increasing generality | Method, What it does, Assumes | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 120 | Why the proposal matters so much | Sampler, Proposal, $\tau$, Effective samples per 1000 model evaluations | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 121 | Collapsing: integrate the private parameters out | Sampler, τ(shared), min ESS, ESS / 1000 evals, reported $a$ | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 122 | Changing your mind about a prior, without sampling again | $\hat k$, meaning | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 123 | The numbers you actually publish | lower arm, upper arm | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 124 | Three stages, three failure modes | stage, question, how it fails | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 125 | Why a wavelet, and why two scales | threshold, 128², 256², 512² | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 126 | \mathrm{Var}(k) - \langle k\rangle = \gamma_2\,N\,(\epsilon\,T)^2 , | sample, $\epsilon$, $N$, $\epsilon T$, $\langle k\rangle$, $\mathrm{Var}-\langle k\rangle$, $B$ | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 127 | How much heterogeneity can PDA actually detect? | $N$ (photons/burst), 20, 50, 100, 200, 500 | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 128 | How much heterogeneity can PDA actually detect? | $\sigma_\text{het}$, $\sigma_\text{obs}$ at $N=50$, at $N=200$, ratio | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 129 | What a burst looks like | symbol, excitation → detection | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 130 | \underbrace{M}_{\text{emission}} | matrix, shape, meaning | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 131 | The problem with histograms | exchange, histogram, what you can measure | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 132 | Relation to H2MM | H2MM, Gopich–Szabo | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 133 | What ChiSurf writes, and what it only reads | what, where it goes | [docs/concepts/photon_container.md](/concepts/photon_container.md) |
| 134 | The scalar focus: the Airy pattern | Feature, Where, Distance | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 135 | What ChiSurf computes | Model / pupil state, FWHM $x$, FWHM $y$, FWHM $z$ | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 136 | What ChiSurf computes | NA, medium, lateral: vectorial vs $0.514\,\lambda/\mathrm{NA}$, axial: vectorial vs $0.886\,\lambda/(n-\sqrt{n^2-\mathrm{NA}^2})$ | [docs/concepts/point_spread_function.md](/concepts/point_spread_function.md) |
| 137 | k_\text{FRET} = \frac{3}{2}\,\kappa^2\,\frac{1}{\tau_{D(0)}}\left(\frac{R_0}{R}\right)^6 , | averaging, $\kappa^2 = 2/3$, $\kappa^2$ per frame ($\langle\kappa^2\rangle$ = 0.574) | [docs/concepts/structure_trajectories.md](/concepts/structure_trajectories.md) |
| 138 | Where this connects in ChiSurf | Question, Page | [docs/concepts/super_resolution.md](/concepts/super_resolution.md) |
| 139 | \;\sim\; F(\Delta p,\, \nu_{n+1}), | Rule, Referred to, $R$ needed at 68 %, at 95 % | [docs/concepts/tcspc_lifetime.md](/concepts/tcspc_lifetime.md) |
| 140 | TTTR Tools: the two clocks of a photon record | clock, scale, wraps, builds | [docs/concepts/tttr_stream_tools.md](/concepts/tttr_stream_tools.md) |
| 141 | The four streams, and what they are for | stream, excitation, emission, used for | [docs/concepts/us_alex.md](/concepts/us_alex.md) |
| 142 | ceiling the fusion is capped at. | Control, Default, Meaning | [docs/guides/02_recurrence_rasp.md](/guides/02_recurrence_rasp.md) |
| 143 | profile use the same channel and slicing definition as the burst points. | Control, Default, Meaning | [docs/guides/08_burst_variance_analysis.md](/guides/08_burst_variance_analysis.md) |
| 144 | 3. Simulate and read | tab, content | [docs/guides/104_lightpath_simulator.md](/guides/104_lightpath_simulator.md) |
| 145 | the accepted **Macro time interval**. | Control, Default, Meaning | [docs/guides/13_burst_identification.md](/guides/13_burst_identification.md) |
| 146 | Choosing a decoder | *Decoder*, what it does, use it for | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 147 | ~6.8 ns. Solid is S0 (low FRET: little red), dashed is S1 (high FRET). | Column, Meaning | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 148 | 16-burst photon demo. This pooled calculation does not prove batch execution. | Model, Inputs in parameter order, Interpretation | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 149 | The lifetime of a state, not of a burst | Detector, Colour, State, Photons (parallel), Photons (perpendicular), Photons, Tau, 2I*, … | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 150 | Trace Browser | Button, What it does | [docs/guides/22_binned_photon_traces.md](/guides/22_binned_photon_traces.md) |
| 151 | Result | table, one row per, columns | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 152 | 5. Choosing a sampler | `method`, Use when | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 153 | [e['mean'] for e in r['parameters']] | `pareto_k`, what to do | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 154 | print(q['name'], q['median'], q['low'], q['high'], q['method'], q['warning']) | Method, What it is, Read the interval as | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 155 | Setting it up | Provider, Base URL, Processing location, Key from | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 156 | Things to ask it | Ask it, What it does | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 157 | Using it in the GUI | Mode, What it can do | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 158 | Skills: how it knows *how* | Skill, Loaded when you ask about | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 159 | 2. Check the channel mapping | combo, channel | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 160 | Naming differences to watch | ndX, meaning, Hellenkamp | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 161 | bursts = simulation.burst_table(min_photons=50) | factor, declared, recovered | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 162 | Loading data | reader, use it for | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 163 | fetch PDBDEV_00000012 # ...or an integrative model from PDB-IHM | Repository, Looks like, Gives you | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 164 | A simulation is more than motion | What the file says, What you see | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 165 | level, click empty histogram to add one, right-click a marker to remove it. | Map, Opens at, Why | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 166 | Trying it out: the Demo menu | Entry, What it shows | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 167 | Selecting with the mouse | Gesture, Action, Effect | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 168 | Measuring by clicking | Control, What it does | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 169 | distance com, chain A, chain B, mode=4 # one line, centroid to centroid | `mode`, What it draws | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 170 | hbond_network solvent, only # the water wires alone | Argument, Meaning | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 171 | * 5 9.9% strain 29.45 N-CA-CB-CG=61, CA-CB-CG-CD1=-90 | Detail, What happens | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 172 | Where things stand | Area, State | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 173 | Read the result | Predicted error, Verdict, What to do | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 174 | sample from a stable one with broader populations. | Control, What it does | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 175 | What it does | Bridge, ChiSurf RPC, Produces | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 176 | Where regions appear | Tool, What a region does there | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 177 | 1. Detect | what you see, what it means | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 178 | The menu is not a list ndX keeps | Target, RPC, What comes back | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 179 | and **Next ▶**. | Step, Reuses when, Recomputes when | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 180 | Everything downstream is handed the same files | Panel, Receives | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 181 | Settings reference | Setting, What it does | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 182 | Which route to use | you want, use, resolution | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 183 | 1. Open the calculator and pick a scheme | Scheme, States, Use it for | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 184 | 3. A worked case: Rhodamine 6G at 488 nm | Power, k_exc(0,0), V_eff/V₀, apparent τ_D, G(0) vs unsaturated, no bunching | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 185 | 1. Load the folder | Setting, What it does | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 186 | 3. Set the two controls | Control, Question, How to choose | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 187 | 3. Set the two controls | Threshold, Window, Bursts, Proximity-ratio width | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 188 | 4. Judge it from the summary, not from the burst count | Row, Expected, What it means if not | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 189 | What is already in scope | Name, What it is | [docs/guides/59_console.md](/guides/59_console.md) |
| 190 | What you need first | Field, Measure it on | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 191 | Step 3 — read the right number | Reading, What it means | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 192 | Step 4 — the step that decides whether you can publish it | Outcome, Reading | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 193 | What is in it | column, what it is | [docs/guides/63_pto_inspector.md](/guides/63_pto_inspector.md) |
| 194 | The toolbar | Control, What it does | [docs/guides/64_notebooks.md](/guides/64_notebooks.md) |
| 195 | Where each window went | ALEX-Suite, here | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 196 | check. | stream, burst-table column | [docs/guides/66_alex_suite.md](/guides/66_alex_suite.md) |
| 197 | If it will not answer | It says, What to do | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 198 | The world you are looking at | On the map, Means | [docs/guides/71_lumis_quest.md](/guides/71_lumis_quest.md) |
| 199 | Controls | Action, Keyboard, Does | [docs/guides/71_lumis_quest.md](/guides/71_lumis_quest.md) |
| 200 | Export | Format, Contents, For | [docs/guides/72_psf_calculator.md](/guides/72_psf_calculator.md) |
| 201 | Find the levels (HMM tab) | Path, Content | [docs/guides/74_intensity_traces_and_file_tools.md](/guides/74_intensity_traces_and_file_tools.md) |
| 202 | The `.cor` file | Column, Content | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 203 | csc fcs-convert -i PyCorrFit_CC_A488.csv -it pycorrfit -o a488.yaml -ot yaml | Readers (`-it`), Writers (`-ot`) | [docs/guides/75_fcs_toolbox.md](/guides/75_fcs_toolbox.md) |
| 204 | Open the tools | Tool, How to open it | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 205 | search box filters it by name or purpose, **Help** and **Guide** belong to the window. | Panel, What it does, Guide | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 206 | plugin's `lifetime_settings.yml`, copied once into the system temp folder. | Key, Default, Meaning | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 207 | The component-count scan | True decay, Chosen $n$ (seeds 1, 2, 3), What went wrong | [docs/guides/76_decay_analysis_tools.md](/guides/76_decay_analysis_tools.md) |
| 208 | Reading it: the case where the tests disagree | comparison, $\chi^2_r$, tool confidence, $\chi^2_{r,2}$ needed at 95 %, extra-SS $F$ ($p$), $\Delta$AIC | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 209 | Where results go | item, $\tau_1$ (ns), $\tau_2$ (ns), $\langle\tau\rangle_x$ (ns), $\langle\tau\rangle_F$ (ns), $\chi^2_r$ | [docs/guides/78_model_comparison_and_batch.md](/guides/78_model_comparison_and_batch.md) |
| 210 | The standard lines | Line, Components, Vary, Range | [docs/guides/82_fret_lines.md](/guides/82_fret_lines.md) |
| 211 | **Overview** on the staging database of this machine: 2141 components, 1808 of them with at least one spectrum; 977 fluorophores, 898 filters, 190 dichroics, 69… | panel, what it does | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 212 | 2. Where the spectra come from, and the terms they come under | source, carries, terms | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 213 | 5. Check it against published values | pair, spectra, $Q_D$, ε_max (M⁻¹ cm⁻¹), $J$ (M⁻¹ cm⁻¹ nm⁴), $R_0$ ChiSurf, $R_0$ table | [docs/guides/83_spectra_and_r0.md](/guides/83_spectra_and_r0.md) |
| 214 | 2. Settings | workflow, method, for | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 215 | 2. Settings | control, meaning | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 216 | 3. A real image | workflow, regions | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 217 | 3. A real image | threshold, 0.05, 5, 20, 50, 100 | [docs/guides/84_spot_finder.md](/guides/84_spot_finder.md) |
| 218 | 1. Where it is | control, what it does | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 219 | 2. What it checks | line of the report, what was done | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 220 | 2. What it checks | detector, channels, micro-time window | [docs/guides/85_mfd_prepare.md](/guides/85_mfd_prepare.md) |
| 221 | 6. Export | button, writes | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 222 | 8. Where things go wrong | symptom, cause | [docs/guides/86_image_browser.md](/guides/86_image_browser.md) |
| 223 | of configured corrections, not a measured TAC calibration. | Where, Control, What it does | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 224 | of configured corrections, not a measured TAC calibration. | Setup row, **Setup**, **Save**, **Rename**, **Delete**, Choose a saved setup (the one used last opens at start); Save, Rename and Delete ask in a small prompt. | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 225 | of configured corrections, not a measured TAC calibration. | **Public**, Make the saved setup visible to all users of the MMFDB with the next Save; only its owner can. | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 226 | of configured corrections, not a measured TAC calibration. | **Calibration**, Apply a stored G/l1/l2 snapshot of the selected setup to the detectors; *Latest* leaves them. | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 227 | of configured corrections, not a measured TAC calibration. | TTTR Reading routine, **File Type**, *Auto* or a container (PTU, HT3, SPC-130, SPC-600, PHOTON-HDF5, CZ-RAW, SM, PHOTONS, SPC-QC, BRIGHTEYES-TTR, FLIMLABS, PTO)… | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 228 | of configured corrections, not a measured TAC calibration. | **Read**, Take the macro and micro time from a measurement and the decay of every routing channel. | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 229 | of configured corrections, not a measured TAC calibration. | **Macrotime res. (ns)**, **Microtime res. (ps)**, **Microtime binning**, **Eff. microtime (ps)**, Type numbers; the effective tick is read-only. | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 230 | of configured corrections, not a measured TAC calibration. | LUT handling, **Apply TAC linearization (LUT) when reading**, Switch the linearization on for every read (adding a LUT switches it on). | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 231 | Developer API for an embedded native page | Flag, Exposed controls | [docs/guides/87_channel_definition.md](/guides/87_channel_definition.md) |
| 232 | the 3D View beside them with the selected position's accessible volume (red) in front and the others muted. | Tab, Controls | [docs/guides/88_structure_tools.md](/guides/88_structure_tools.md) |
| 233 | 2. Mix | Window, Control, What it does | [docs/guides/94_tttr_audifier.md](/guides/94_tttr_audifier.md) |
| 234 | 2. Keys and pointer | Game, Keys, Pointer | [docs/guides/95_games.md](/guides/95_games.md) |
| 235 | 3. Read the table | Column, Means | [docs/guides/96_plugin_check.md](/guides/96_plugin_check.md) |
| 236 | right, **Guide** and **?** at the top right, the status line and **Back / >> / Next** at the bottom. | Where, Control, What it does | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 237 | 2. The destinations | Destination, Panel, Figure | [docs/guides/97_settings_hub.md](/guides/97_settings_hub.md) |
| 238 | 2. The list | Group, Tools | [docs/guides/98_imaging_tools.md](/guides/98_imaging_tools.md) |
| 239 | 3. Windows, backgrounds, shifts | Field, Meaning | [docs/guides/99_img_calibration.md](/guides/99_img_calibration.md) |
| 240 | The correction | factor, symbol, meaning | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 241 | Compute engines | engine, description, accuracy | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 242 | Where each guide starts in ChiSurf | Tutorial, ChiSurf entry point | [docs/guides/index.md](/guides/index.md) |
| 243 | Design Choices | Aspect, Implementation | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 244 | :align: center | Control, What it does | [docs/manual/fit_plots.md](/manual/fit_plots.md) |
| 245 | Convolution modes | Mode, Use it for | [docs/manual/fluorescence_lifetime.md](/manual/fluorescence_lifetime.md) |
| 246 | report = chisurf.core.fitting.fit.sample_fit(fit, "/output/directory") | `method`, When to use it | [docs/manual/parameter_sampling.md](/manual/parameter_sampling.md) |
| 247 | Parameters | Parameter, Meaning | [docs/manual/partial_donordonor_energy_migration.md](/manual/partial_donordonor_energy_migration.md) |
| 248 | Parameters | Parameter, Meaning | [docs/manual/wormlike_chain.md](/manual/wormlike_chain.md) |
| 249 | Code index | #, Language, Section, Lines, Verified, Page | [docs/reference/code.md](/reference/code.md) |
| 250 | Figure index | #, Image, Caption, Origin, Page | [docs/reference/figures.md](/reference/figures.md) |
| 251 | One file, many curves | curve type, meaning | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 252 | The setting that chooses the method | Setting, What you get | [docs/reference/file_formats/ics_files.md](/reference/file_formats/ics_files.md) |
| 253 | Reading a parameter table | Appearance, Meaning | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 254 | Parameter glossary | Parameter, Meaning, Keywords | [docs/reference/parameters.md](/reference/parameters.md) |
| 255 | Identity | Field, Value | [docs/reference/plugins/about.md](/reference/plugins/about.md) |
| 256 | Identity | Field, Value | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 257 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 258 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 259 | Dyes (database) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 260 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 261 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 262 | Optics prior (light path) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 263 | Procedure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 264 | Identity | Field, Value | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 265 | Device session | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 266 | Routing and output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 267 | Simulator configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 268 | Result visibility | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 269 | Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 270 | Correlation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 271 | Count rate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 272 | MCS | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 273 | Macrotime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 274 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 275 | Identity | Field, Value | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 276 | API Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 277 | Models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 278 | Generation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 279 | Identity | Field, Value | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 280 | Fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 281 | Burst filters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/alex_suite.md](/reference/plugins/alex_suite.md) |
| 282 | Identity | Field, Value | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 283 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 284 | Files & fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 285 | Run | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 286 | Identity | Field, Value | [docs/reference/plugins/bid_to_analysis.md](/reference/plugins/bid_to_analysis.md) |
| 287 | Identity | Field, Value | [docs/reference/plugins/boarding.md](/reference/plugins/boarding.md) |
| 288 | Identity | Field, Value | [docs/reference/plugins/breakout.md](/reference/plugins/breakout.md) |
| 289 | Identity | Field, Value | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 290 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 291 | Identity | Field, Value | [docs/reference/plugins/burst_analysis.md](/reference/plugins/burst_analysis.md) |
| 292 | Identity | Field, Value | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 293 | Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 294 | Fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 295 | Identity | Field, Value | [docs/reference/plugins/burst_browser.md](/reference/plugins/burst_browser.md) |
| 296 | Identity | Field, Value | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 297 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 298 | Identity | Field, Value | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 299 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 300 | Select Series | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 301 | Crop | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 302 | Select States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 303 | States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 304 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 305 | Number of States | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 306 | Time Series Group | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 307 | Expected Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 308 | Prior Strength | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 309 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 310 | Identity | Field, Value | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 311 | Correlator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 312 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 313 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 314 | Identity | Field, Value | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 315 | Fusion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 316 | P(same molecule) estimate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 317 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 318 | Identity | Field, Value | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 319 | Photons | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 320 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 321 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 322 | Extras | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 323 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 324 | Identity | Field, Value | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 325 | Data | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 326 | Model selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 327 | Optimisation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 328 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 329 | Burst | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 330 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 331 | Identity | Field, Value | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 332 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 333 | Identity | Field, Value | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 334 | Start value and fit window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 335 | Burst files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 336 | Detector and window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 337 | Measured IRF and background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 338 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 339 | H2MM states | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 340 | Burst | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 341 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 342 | Identity | Field, Value | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 343 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 344 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 345 | Burst search | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 346 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 347 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 348 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 349 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 350 | Scatter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 351 | GMM settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 352 | Metadata | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 353 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 354 | Identity | Field, Value | [docs/reference/plugins/calculators.md](/reference/plugins/calculators.md) |
| 355 | Identity | Field, Value | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 356 | Identity | Field, Value | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 357 | File | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 358 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 359 | Brush & Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 360 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 361 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 362 | Identity | Field, Value | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 363 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 364 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 365 | Identity | Field, Value | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 366 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 367 | Identity | Field, Value | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 368 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 369 | Identity | Field, Value | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 370 | F-test — compare two nested models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 371 | χ²-max — upper limit from one fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 372 | Identity | Field, Value | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 373 | Species | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 374 | Kinetics / statistics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 375 | Identity | Field, Value | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 376 | Diffusion / volume | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 377 | Occupancy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 378 | Constraint (choose one) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 379 | Reference dye (D @ 25 °C, water) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 380 | Molecular shape | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 381 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 382 | Identity | Field, Value | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 383 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 384 | Identity | Field, Value | [docs/reference/plugins/fcs_convert.md](/reference/plugins/fcs_convert.md) |
| 385 | Identity | Field, Value | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 386 | Correlation Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 387 | Correlation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 388 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 389 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 390 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 391 | Change-point parameters (BOCPD / Kalman / CUSUM) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 392 | Plot settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 393 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 394 | Identity | Field, Value | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 395 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 396 | Mixed decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 397 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 398 | Auto-fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 399 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 400 | Identity | Field, Value | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 401 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 402 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 403 | Identity | Field, Value | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 404 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 405 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 406 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 407 | Identity | Field, Value | [docs/reference/plugins/fcs_toolbox.md](/reference/plugins/fcs_toolbox.md) |
| 408 | Identity | Field, Value | [docs/reference/plugins/filetools.md](/reference/plugins/filetools.md) |
| 409 | Identity | Field, Value | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 410 | 2D-FDC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 411 | Lifetime inversion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 412 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 413 | Dynamics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 414 | Kinetics (advanced) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 415 | 1D-MEM + Gaussian | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 416 | Simulator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 417 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 418 | Identity | Field, Value | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 419 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 420 | Identity | Field, Value | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 421 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 422 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 423 | Identity | Field, Value | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 424 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 425 | Docking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 426 | Monte-Carlo (mc method only) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 427 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 428 | Candidate sites from residues | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 429 | Efficiency | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 430 | Selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 431 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 432 | Identity | Field, Value | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 433 | Your dyes | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 434 | Components | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 435 | Sweep | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 436 | Identity | Field, Value | [docs/reference/plugins/games.md](/reference/plugins/games.md) |
| 437 | Identity | Field, Value | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 438 | Toolbar | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 439 | View | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 440 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 441 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 442 | Identity | Field, Value | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 443 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 444 | Identity | Field, Value | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 445 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 446 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 447 | State scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 448 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 449 | Identity | Field, Value | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 450 | Executable & input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 451 | Primary model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 452 | Solvent & macromolecule | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 453 | Optional calculations | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 454 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 455 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 456 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 457 | Identity | Field, Value | [docs/reference/plugins/imaging_common.md](/reference/plugins/imaging_common.md) |
| 458 | Identity | Field, Value | [docs/reference/plugins/imaging_tools.md](/reference/plugins/imaging_tools.md) |
| 459 | Identity | Field, Value | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 460 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 461 | Identity | Field, Value | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 462 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 463 | Background / thresholds | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 464 | Scatter gate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 465 | Region of interest | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 466 | Objects (punctate signal) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 467 | Significance / profile | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 468 | Identity | Field, Value | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 469 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 470 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 471 | Identity | Field, Value | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 472 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 473 | Scanner | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 474 | Display and estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 475 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 476 | Identity | Field, Value | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 477 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 478 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 479 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 480 | Identity | Field, Value | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 481 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 482 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 483 | Identity | Field, Value | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 484 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 485 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 486 | Identity | Field, Value | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 487 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 488 | IRF preparation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 489 | Fit flags | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 490 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 491 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 492 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 493 | Fit parameters (fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 494 | Fit parameters (fit24) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 495 | Fit parameters (fit25) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 496 | Lifetime map | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 497 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 498 | Identity | Field, Value | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 499 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 500 | Stack corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 501 | Detector | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 502 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 503 | Parameter plane / gates | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 504 | Cross N&B | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 505 | Identity | Field, Value | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 506 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 507 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 508 | IRF reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 509 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 510 | Identity | Field, Value | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 511 | Movie | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 512 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 513 | 1. Detect | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 514 | 2. Link | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 515 | 3. Transport | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 516 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 517 | Core | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 518 | File → Data | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 519 | Help | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 520 | Main → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 521 | Microscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 522 | Setup | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 523 | Spectroscopy → Correlation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 524 | Spectroscopy → Decay | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 525 | Spectroscopy → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 526 | Spectroscopy → Imaging | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 527 | Spectroscopy → Imaging → Lifetime | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 528 | Spectroscopy → Imaging → Simulate | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 529 | Spectroscopy → Imaging → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 530 | Spectroscopy → Kinetics | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 531 | Spectroscopy → Single-Molecule | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 532 | Structure → Computation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 533 | Structure → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 534 | Structure → Modelling | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 535 | Structure → Structure | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 536 | Structure → Trajectory | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 537 | TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 538 | TTTR → Editor | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 539 | Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 540 | Tools → Burst | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 541 | Tools → Calculators | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 542 | Tools → Converter | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 543 | Tools → Miscellaneous | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 544 | Tools → Miscellaneous → Games | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 545 | Tools → Photon data | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 546 | Tools → System | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 547 | Tools → TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 548 | Tools → Views | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 549 | Uncategorized | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 550 | Identity | Field, Value | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 551 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 552 | Time Window | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 553 | Histogram Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 554 | HMM Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 555 | Identity | Field, Value | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 556 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 557 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 558 | Identity | Field, Value | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 559 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 560 | Anisotropy Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 561 | Calculation Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 562 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 563 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 564 | Identity | Field, Value | [docs/reference/plugins/lifetime_analysis.md](/reference/plugins/lifetime_analysis.md) |
| 565 | Identity | Field, Value | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 566 | Graph view | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 567 | Backend | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 568 | MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 569 | Connections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 570 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 571 | Identity | Field, Value | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 572 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 573 | Identity | Field, Value | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 574 | MEM settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 575 | Lifetime grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 576 | Distance grid | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 577 | Periodic convolution | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 578 | Instrument | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 579 | Nuisance optimization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 580 | L-curve | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 581 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 582 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 583 | Identity | Field, Value | [docs/reference/plugins/menu_switch.md](/reference/plugins/menu_switch.md) |
| 584 | Identity | Field, Value | [docs/reference/plugins/mfd_prepare.md](/reference/plugins/mfd_prepare.md) |
| 585 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mfd_prepare.md](/reference/plugins/mfd_prepare.md) |
| 586 | Identity | Field, Value | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 587 | Run | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 588 | Detector and channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 589 | Reading and gates | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 590 | Time step, G-factor and shifts | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 591 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 592 | Identity | Field, Value | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 593 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 594 | Entity | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 595 | Probes | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 596 | Alignment | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 597 | Shifts | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 598 | Save | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 599 | MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 600 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 601 | Identity | Field, Value | [docs/reference/plugins/minesweeper.md](/reference/plugins/minesweeper.md) |
| 602 | Identity | Field, Value | [docs/reference/plugins/mle_common.md](/reference/plugins/mle_common.md) |
| 603 | Identity | Field, Value | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 604 | Connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 605 | Choose | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 606 | Enter a value | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 607 | Change password | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 608 | Jump to branch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 609 | Overview | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 610 | All items | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 611 | Measurements | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 612 | Sample Metadata | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 613 | Detail | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 614 | Spectra | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 615 | Provenance Graph | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 616 | Import / Export | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 617 | eLabFTW connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 618 | eLabFTW | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 619 | Import into MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 620 | Export from MMFDB | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 621 | Studies | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 622 | Protocols | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 623 | Lifecycle | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 624 | Register calibration value | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 625 | Reagent Lots | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 626 | Add lot | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 627 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 628 | Advanced — user & connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 629 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 630 | Identity | Field, Value | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 631 | Registered models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 632 | Selected model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 633 | Identity | Field, Value | [docs/reference/plugins/ndxplorer.md](/reference/plugins/ndxplorer.md) |
| 634 | Identity | Field, Value | [docs/reference/plugins/number_quest.md](/reference/plugins/number_quest.md) |
| 635 | Identity | Field, Value | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 636 | Data settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 637 | Model fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 638 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 639 | Identity | Field, Value | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 640 | Controls | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 641 | Reference geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 642 | Two-component line | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 643 | Mixing region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 644 | Cursor | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 645 | Excitation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 646 | Identity | Field, Value | [docs/reference/plugins/photon_table.md](/reference/plugins/photon_table.md) |
| 647 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/photon_table.md](/reference/plugins/photon_table.md) |
| 648 | Identity | Field, Value | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 649 | Rendering Backend | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 650 | Colors | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 651 | Appearance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 652 | Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 653 | Node Graphs (Global View) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 654 | Advanced: pyqtgraph Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plot_settings.md](/reference/plugins/plot_settings.md) |
| 655 | Identity | Field, Value | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 656 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 657 | Identity | Field, Value | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 658 | Installed plugins | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 659 | Selected plugin | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 660 | Plugin Manager | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 661 | Icon | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 662 | Identity | Field, Value | [docs/reference/plugins/pong.md](/reference/plugins/pong.md) |
| 663 | Identity | Field, Value | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 664 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 665 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 666 | Identity | Field, Value | [docs/reference/plugins/proteinmc.md](/reference/plugins/proteinmc.md) |
| 667 | Identity | Field, Value | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 668 | Objective | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 669 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 670 | Polarization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 671 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 672 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 673 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 674 | Identity | Field, Value | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 675 | PSF parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 676 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 677 | Fit Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 678 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 679 | Identity | Field, Value | [docs/reference/plugins/pto_inspector.md](/reference/plugins/pto_inspector.md) |
| 680 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/pto_inspector.md](/reference/plugins/pto_inspector.md) |
| 681 | Identity | Field, Value | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 682 | Formats | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 683 | ALEX modulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 684 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 685 | Input file | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 686 | Excitation regions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 687 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 688 | Identity | Field, Value | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 689 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 690 | Identity | Field, Value | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 691 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 692 | Regions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 693 | Fit (Fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 694 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/region_mle.md](/reference/plugins/region_mle.md) |
| 695 | Identity | Field, Value | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 696 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 697 | Optics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 698 | Scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 699 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 700 | Identity | Field, Value | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 701 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 702 | Advanced Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 703 | Device Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 704 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 705 | Geometry | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 706 | Microtime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 707 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 708 | Identity | Field, Value | [docs/reference/plugins/setup_channel_definition.md](/reference/plugins/setup_channel_definition.md) |
| 709 | Identity | Field, Value | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 710 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 711 | Advanced — connection & authentication | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 712 | Identity | Field, Value | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 713 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 714 | Detector | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 715 | Spot width (log / dog) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 716 | Filters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 717 | Pick by clicking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 718 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/spot_finder.md](/reference/plugins/spot_finder.md) |
| 719 | Identity | Field, Value | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 720 | Selected restraint | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 721 | Structure and attachment | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 722 | Selected position | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 723 | Dye | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 724 | Dye dimensions | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 725 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 726 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 727 | Identity | Field, Value | [docs/reference/plugins/style_manager.md](/reference/plugins/style_manager.md) |
| 728 | Identity | Field, Value | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 729 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 730 | Identity | Field, Value | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 731 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 732 | IRF & noise | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 733 | Anisotropy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 734 | VV/VH detection corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 735 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 736 | Identity | Field, Value | [docs/reference/plugins/tetris.md](/reference/plugins/tetris.md) |
| 737 | Identity | Field, Value | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 738 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 739 | Reader settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 740 | Background region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 741 | Instrument corrections | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 742 | Lifetime spectrum | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 743 | Rotation spectrum | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 744 | Identity | Field, Value | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 745 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 746 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 747 | Identity | Field, Value | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 748 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 749 | Identity | Field, Value | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 750 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 751 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 752 | Identity | Field, Value | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 753 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 754 | Identity | Field, Value | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 755 | Reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 756 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 757 | Identity | Field, Value | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 758 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 759 | Identity | Field, Value | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 760 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 761 | Identity | Field, Value | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 762 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 763 | Identity | Field, Value | [docs/reference/plugins/traj_save_topology.md](/reference/plugins/traj_save_topology.md) |
| 764 | Identity | Field, Value | [docs/reference/plugins/traj_tools.md](/reference/plugins/traj_tools.md) |
| 765 | Identity | Field, Value | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 766 | Audio | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 767 | Waterfall params | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 768 | Micro-time | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 769 | Lifetime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 770 | Identity | Field, Value | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 771 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 772 | Identity | Field, Value | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 773 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 774 | Identity | Field, Value | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 775 | Files | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 776 | Toolbar | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 777 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 778 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 779 | Identity | Field, Value | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 780 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 781 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 782 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 783 | LUT flow | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 784 | Compute LUT | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 785 | settings.tttr.json | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 786 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 787 | Identity | Field, Value | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 788 | Input / Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 789 | Split options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 790 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 791 | Identity | Field, Value | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 792 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 793 | Identity | Field, Value | [docs/reference/plugins/tttr_to_pto.md](/reference/plugins/tttr_to_pto.md) |
| 794 | Identity | Field, Value | [docs/reference/plugins/tttr_toolbox.md](/reference/plugins/tttr_toolbox.md) |
| 795 | Identity | Field, Value | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 796 | Installed Packages | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 797 | Search & Install | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 798 | ChiSurf Package Manager | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 799 | Installed version | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 800 | Startup behavior | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 801 | Update | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 802 | ChiSurf Updater | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 803 | Identity | Field, Value | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 804 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 805 | Identity | Field, Value | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 806 | VV/VH anisotropy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 807 | Correction | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 808 | r-infinity region | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 809 | Identity | Field, Value | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 810 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 811 | Tail matching | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 812 | Manual G | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 813 | Slow-reference mixing | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 814 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 815 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 816 | Identity | Field, Value | [docs/reference/plugins/wizards.md](/reference/plugins/wizards.md) |
| 817 | 1.8.2.1 `gui.console` | Key, Default, Meaning | [docs/reference/settings.md](/reference/settings.md) |
| 818 | Table index | #, Section, Columns, Page | [docs/reference/tables.md](/reference/tables.md) |
| 819 | User-Defined Models in ChiSurf | What it does, Use it when | [docs/reference/user_models.md](/reference/user_models.md) |
| 820 | 5.1 Using the code view | Control, What it does | [docs/reference/user_models.md](/reference/user_models.md) |
