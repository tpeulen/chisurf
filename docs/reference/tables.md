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

*457 tables.*

| # | Section | Columns | Page |
| --- | --- | --- | --- |
| 1 | Entry points | — | [docs/getting_started/index.rst](/getting_started/index.rst) |
| 2 | What happens before emission | Process, Timescale | [docs/fundamentals/absorption_and_emission.md](/fundamentals/absorption_and_emission.md) |
| 3 | The excited state | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 4 | Anisotropy | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 5 | FRET | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 6 | FCS | Quantity, ChiSurf, In code / UI, Also written | [docs/fundamentals/conventions.md](/fundamentals/conventions.md) |
| 7 | Fundamentals (photophysics) | What each documentation layer answers | [docs/fundamentals/index.rst](/fundamentals/index.rst) |
| 8 | Detectors | Detector, Timing resolution, Notes | [docs/fundamentals/instrumentation.md](/fundamentals/instrumentation.md) |
| 9 | \qquad (E \approx 0.58). | $\langle R_{DA}\rangle$, $\sigma = 3$ Å, $\sigma = 6$ Å, $\sigma = 10$ Å, $\sigma = 15$ Å | [docs/concepts/accessible_volume.md](/concepts/accessible_volume.md) |
| 10 | The four factors | channel, alias, what it holds | [docs/concepts/accurate_fret.md](/concepts/accurate_fret.md) |
| 11 | \approx 10\ \mathrm{ns}. | system, $\rho$, $\tau/\rho$, $r/r_0$ | [docs/concepts/anisotropy.md](/concepts/anisotropy.md) |
| 12 | The cost: a fused burst is one interval | Control, Question it answers | [docs/concepts/burst_fusion.md](/concepts/burst_fusion.md) |
| 13 | What to report | Report, Because | [docs/concepts/colocalization.md](/concepts/colocalization.md) |
| 14 | \eta_d = \tfrac{1}{2}\,\Gamma\!\left(1 - \tfrac{d}{6}\right)\frac{C}{C_0}, | Dimensionality, Physical case, Exponent, $C_0$, $\eta_d$ at $C=C_0$ | [docs/concepts/distributed_acceptors.md](/concepts/distributed_acceptors.md) |
| 15 | Choosing the geometry: fit all three | Simulated, Fitted as 1-D, Fitted as 2-D, Fitted as 3-D | [docs/concepts/distributed_acceptors.md](/concepts/distributed_acceptors.md) |
| 16 | Why drift is not just blur | Frame lag $\Delta$, $G(0,0,\Delta)$ uncorrected, corrected | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 17 | C(\xi, \psi) = \mathcal{F}^{-1}\bigl\{\, \mathcal{F}(a)\,\overline{\mathcal{F}(b)} \,\bigr\} | Reference, Behaviour | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 18 | Why it hides | Observable, Effect of homo-transfer | [docs/concepts/energy_migration.md](/concepts/energy_migration.md) |
| 19 | The model | Array, Meaning | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 20 | The second apparent diffusion time | Power, V_eff/V₀, apparent τ_D, one-component residual, two-component fit | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 21 | Fitting it: a global triplet times two diffusion times | amplitude, τ_D | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 22 | Conditioning: the price of similar patterns | $\tau_2$, $\tau_2/\tau_1$, condition number, largest filter value | [docs/concepts/filtered_fcs.md](/concepts/filtered_fcs.md) |
| 23 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | $E$, $6E(1-E)$, $\Delta R/R$ for $\Delta E = 0.02$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 24 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | error in $J$ or $Q_D$, effect on $R_0$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 25 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | $\kappa^2$, $R$ scaled by, situation | [docs/concepts/fret.md](/concepts/fret.md) |
| 26 | Linking is not fixing | asserts, uses data, keeps its uncertainty | [docs/concepts/global_analysis.md](/concepts/global_analysis.md) |
| 27 | Decoding: "most likely path" is not "how the photons distribute" | decoder, draws from, photon distribution, dwell / transition structure | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 28 | \qquad\text{here } 10^{3}\ \mathrm{s^{-1}} \dots 5\times10^{4}\ \mathrm{s^{-1}} . | $K$, $k$ ($P=2$, DD/DA), $k$ ($P=3$, with AA) | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 29 | When to use something else | Situation, Better tool | [docs/concepts/hidden_markov_models.md](/concepts/hidden_markov_models.md) |
| 30 | Worked numbers | Step, Lag time, Ratio to previous | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 31 | Which method is which | Method, Region read, Clock that dominates, Scale | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 32 | Using it in ChiSurf | Release this, To fit | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 33 | What the gate actually tested | quantity, measured / model-free, forward model | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 34 | Testing it against simulated dynamics | regime, true rate, fitted, bursts between the states | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 35 | Three sources, one model | source, what it uses, what it is for | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 36 | Choosing a density | `dot_density`, points per atom, typical error | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 37 | What the peak time means | transport, peak of $G(\tau,\delta)$, scaling | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 38 | Reading the numbers | what you see, what it means | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 39 | Three uncertainty estimates, in increasing generality | Method, What it does, Assumes | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 40 | Why the proposal matters so much | Sampler, Proposal, $\tau$, Effective samples per 1000 model evaluations | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 41 | Collapsing: integrate the private parameters out | Sampler, τ(shared), min ESS, ESS / 1000 evals, reported $a$ | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 42 | Changing your mind about a prior, without sampling again | $\hat k$, meaning | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 43 | The numbers you actually publish | lower arm, upper arm | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 44 | Three stages, three failure modes | stage, question, how it fails | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 45 | Why a wavelet, and why two scales | threshold, 128², 256², 512² | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 46 | \mathrm{Var}(k) - \langle k\rangle = \gamma_2\,N\,(\epsilon\,T)^2 , | sample, $\epsilon$, $N$, $\epsilon T$, $\langle k\rangle$, $\mathrm{Var}-\langle k\rangle$, $B$ | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 47 | How much heterogeneity can PDA actually detect? | $N$ (photons/burst), 20, 50, 100, 200, 500 | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 48 | How much heterogeneity can PDA actually detect? | $\sigma_\text{het}$, $\sigma_\text{obs}$ at $N=50$, at $N=200$, ratio | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 49 | What a burst looks like | symbol, excitation → detection | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 50 | \underbrace{M}_{\text{emission}} | matrix, shape, meaning | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 51 | The problem with histograms | exchange, histogram, what you can measure | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 52 | Relation to H2MM | H2MM, Gopich–Szabo | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 53 | Choosing a decoder | *Decoder*, what it does, use it for | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 54 | ~6.8 ns. Solid is S0 (low FRET: little red), dashed is S1 (high FRET). | Column, Meaning | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 55 | The lifetime of a state, not of a burst | Detector, Colour, State, Photons (parallel), Photons (perpendicular), Photons, Tau, 2I*, … | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 56 | Result | table, one row per, columns | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 57 | 5. Choosing a sampler | `method`, Use when | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 58 | [e['mean'] for e in r['parameters']] | `pareto_k`, what to do | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 59 | print(q['name'], q['median'], q['low'], q['high'], q['method'], q['warning']) | Method, What it is, Read the interval as | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 60 | Setting it up | Provider, Base URL, Processing location, Key from | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 61 | Things to ask it | Ask it, What it does | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 62 | Using it in the GUI | Mode, What it can do | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 63 | Skills: how it knows *how* | Skill, Loaded when you ask about | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 64 | 2. Check the channel mapping | combo, channel | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 65 | Naming differences to watch | ndX, meaning, Hellenkamp | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 66 | bursts = simulation.burst_table(min_photons=50) | factor, declared, recovered | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 67 | Loading data | reader, use it for | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 68 | fetch PDBDEV_00000012 # ...or an integrative model from PDB-IHM | Repository, Looks like, Gives you | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 69 | A simulation is more than motion | What the file says, What you see | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 70 | level, click empty histogram to add one, right-click a marker to remove it. | Map, Opens at, Why | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 71 | Trying it out: the Demo menu | Entry, What it shows | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 72 | Selecting with the mouse | Gesture, Action, Effect | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 73 | distance com, chain A, chain B, mode=4 # one line, centroid to centroid | `mode`, What it draws | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 74 | hbond_network solvent, only # the water wires alone | Argument, Meaning | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 75 | Where things stand | Area, State | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 76 | Read the result | Predicted error, Verdict, What to do | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 77 | sample from a stable one with broader populations. | Control, What it does | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 78 | What it does | Bridge, ChiSurf RPC, Produces | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 79 | Where regions appear | Tool, What a region does there | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 80 | 1. Detect | what you see, what it means | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 81 | The menu is not a list ndX keeps | Target, RPC, What comes back | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 82 | Unchanged — kept the previous BVA result (🔁 Restart recomputes it) | Step, Reuses when, Recomputes when | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 83 | Everything downstream is handed the same files | Panel, Receives | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 84 | Settings reference | Setting, What it does | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 85 | Which route to use | you want, use, resolution | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 86 | 1. Open the calculator and pick a scheme | Scheme, States, Use it for | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 87 | 3. A worked case: Rhodamine 6G at 488 nm | Power, k_exc(0,0), V_eff/V₀, apparent τ_D, G(0) vs unsaturated | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 88 | 1. Load the folder | Setting, What it does | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 89 | 3. Set the two controls | Control, Question, How to choose | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 90 | 3. Set the two controls | Threshold, Window, Bursts, Proximity-ratio width | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 91 | 4. Judge it from the summary, not from the burst count | Row, Expected, What it means if not | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 92 | What is already in scope | Name, What it is | [docs/guides/59_console.md](/guides/59_console.md) |
| 93 | What you need first | Field, Measure it on | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 94 | Step 3 — read the right number | Reading, What it means | [docs/guides/61_kappa2_distribution.md](/guides/61_kappa2_distribution.md) |
| 95 | Step 4 — the step that decides whether you can publish it | Outcome, Reading | [docs/guides/62_maxent_decay.md](/guides/62_maxent_decay.md) |
| 96 | If it will not answer | It says, What to do | [docs/guides/70_ask_the_documentation.md](/guides/70_ask_the_documentation.md) |
| 97 | The correction | factor, symbol, meaning | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 98 | Compute engines | engine, description, accuracy | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 99 | Where each guide starts in ChiSurf | Tutorial, ChiSurf entry point | [docs/guides/index.md](/guides/index.md) |
| 100 | Design Choices | Aspect, Implementation | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 101 | Convolution modes | — | [docs/manual/fluorescence_lifetime.rst](/manual/fluorescence_lifetime.rst) |
| 102 | From the shell | — | [docs/manual/parameter_sampling.rst](/manual/parameter_sampling.rst) |
| 103 | Parameters | — | [docs/manual/partial_donordonor_energy_migration.rst](/manual/partial_donordonor_energy_migration.rst) |
| 104 | Parameters | — | [docs/manual/wormlike_chain.rst](/manual/wormlike_chain.rst) |
| 105 | Code index | #, Language, Section, Lines, Verified, Page | [docs/reference/code.md](/reference/code.md) |
| 106 | Figure index | #, Image, Caption, Origin, Page | [docs/reference/figures.md](/reference/figures.md) |
| 107 | One file, many curves | curve type, meaning | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 108 | The setting that chooses the method | Setting, What you get | [docs/reference/file_formats/ics_files.md](/reference/file_formats/ics_files.md) |
| 109 | Reading a parameter table | Appearance, Meaning | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 110 | Parameter glossary | Parameter, Meaning, Keywords | [docs/reference/parameters.md](/reference/parameters.md) |
| 111 | Identity | Field, Value | [docs/reference/plugins/about.md](/reference/plugins/about.md) |
| 112 | Identity | Field, Value | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 113 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 114 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 115 | Dyes (database) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 116 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 117 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 118 | Optics prior (light path) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 119 | Procedure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 120 | Identity | Field, Value | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 121 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 122 | Identity | Field, Value | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 123 | API Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 124 | Models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 125 | Generation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 126 | Identity | Field, Value | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 127 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 128 | Identity | Field, Value | [docs/reference/plugins/bid_to_analysis.md](/reference/plugins/bid_to_analysis.md) |
| 129 | Identity | Field, Value | [docs/reference/plugins/boarding.md](/reference/plugins/boarding.md) |
| 130 | Identity | Field, Value | [docs/reference/plugins/breakout.md](/reference/plugins/breakout.md) |
| 131 | Identity | Field, Value | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 132 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 133 | Identity | Field, Value | [docs/reference/plugins/burst_analysis.md](/reference/plugins/burst_analysis.md) |
| 134 | Identity | Field, Value | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 135 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 136 | Identity | Field, Value | [docs/reference/plugins/burst_browser.md](/reference/plugins/burst_browser.md) |
| 137 | Identity | Field, Value | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 138 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 139 | Identity | Field, Value | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 140 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 141 | Identity | Field, Value | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 142 | Correlator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 143 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 144 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 145 | Identity | Field, Value | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 146 | Fusion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 147 | P(same molecule) estimate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 148 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 149 | Identity | Field, Value | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 150 | Photons | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 151 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 152 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 153 | Extras | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 154 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 155 | Identity | Field, Value | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 156 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 157 | Identity | Field, Value | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 158 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 159 | Identity | Field, Value | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 160 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 161 | Identity | Field, Value | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 162 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 163 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 164 | Identity | Field, Value | [docs/reference/plugins/calculators.md](/reference/plugins/calculators.md) |
| 165 | Identity | Field, Value | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 166 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 167 | Identity | Field, Value | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 168 | File | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 169 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 170 | Brush & Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 171 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 172 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 173 | Identity | Field, Value | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 174 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 175 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 176 | Identity | Field, Value | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 177 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 178 | Identity | Field, Value | [docs/reference/plugins/converter.md](/reference/plugins/converter.md) |
| 179 | Identity | Field, Value | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 180 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 181 | Identity | Field, Value | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 182 | F-test — compare two nested models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 183 | χ²-max — upper limit from one fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 184 | Identity | Field, Value | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 185 | Species (lifetime + diffusion) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 186 | Kinetics / statistics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 187 | Identity | Field, Value | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 188 | Diffusion / volume | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 189 | Occupancy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 190 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 191 | Identity | Field, Value | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 192 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 193 | Identity | Field, Value | [docs/reference/plugins/fcs_convert.md](/reference/plugins/fcs_convert.md) |
| 194 | Identity | Field, Value | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 195 | Correlation Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 196 | Correlation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 197 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 198 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 199 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 200 | Change-point parameters (BOCPD / Kalman / CUSUM) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 201 | Plot settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 202 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 203 | Identity | Field, Value | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 204 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 205 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 206 | Identity | Field, Value | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 207 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 208 | Identity | Field, Value | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 209 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 210 | Identity | Field, Value | [docs/reference/plugins/fcs_toolbox.md](/reference/plugins/fcs_toolbox.md) |
| 211 | Identity | Field, Value | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 212 | 2D-FDC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 213 | Lifetime inversion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 214 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 215 | Dynamics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 216 | Kinetics (advanced) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 217 | 1D-MEM + Gaussian | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 218 | Simulator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 219 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 220 | Identity | Field, Value | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 221 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 222 | Identity | Field, Value | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 223 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 224 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 225 | Identity | Field, Value | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 226 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 227 | Docking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 228 | Monte-Carlo (mc method only) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 229 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 230 | Identity | Field, Value | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 231 | Identity | Field, Value | [docs/reference/plugins/games.md](/reference/plugins/games.md) |
| 232 | Identity | Field, Value | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 233 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 234 | Identity | Field, Value | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 235 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 236 | Identity | Field, Value | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 237 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 238 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 239 | State scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 240 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 241 | Identity | Field, Value | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 242 | Executable & input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 243 | Primary model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 244 | Solvent & macromolecule | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 245 | Optional calculations | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 246 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 247 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 248 | Identity | Field, Value | [docs/reference/plugins/imaging_tools.md](/reference/plugins/imaging_tools.md) |
| 249 | Identity | Field, Value | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 250 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 251 | Identity | Field, Value | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 252 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 253 | Background / thresholds | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 254 | Scatter gate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 255 | Region of interest | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 256 | Objects (punctate signal) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 257 | Significance / profile | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 258 | Identity | Field, Value | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 259 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 260 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 261 | Identity | Field, Value | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 262 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 263 | Scanner | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 264 | Display and estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 265 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 266 | Identity | Field, Value | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 267 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 268 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 269 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 270 | Identity | Field, Value | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 271 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 272 | Identity | Field, Value | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 273 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 274 | Identity | Field, Value | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 275 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 276 | IRF preparation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 277 | Fit flags | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 278 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 279 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 280 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 281 | Identity | Field, Value | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 282 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 283 | Identity | Field, Value | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 284 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 285 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 286 | Identity | Field, Value | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 287 | Movie | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 288 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 289 | 1. Detect | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 290 | 2. Link | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 291 | 3. Transport | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 292 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 293 | Analysis → Kinetics | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 294 | Core | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 295 | Help | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 296 | Imaging | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 297 | Imaging → Lifetime | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 298 | Imaging → Simulate | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 299 | Imaging → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 300 | Main → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 301 | Microscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 302 | Setup | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 303 | Spectroscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 304 | Spectroscopy → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 305 | Spectroscopy → Fluorescence Correlation Spectroscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 306 | Spectroscopy → Fluorescence decay | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 307 | Spectroscopy → Single-Molecule | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 308 | Structure → Computation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 309 | Structure → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 310 | Structure → Structure | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 311 | Structure → Trajectory | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 312 | TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 313 | TTTR → Editor | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 314 | Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 315 | Tools → Converter | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 316 | Tools → Miscellaneous | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 317 | Tools → Miscellaneous → Games | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 318 | Tools → TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 319 | {{ cookiecutter.plugin_category }} | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 320 | Identity | Field, Value | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 321 | Identity | Field, Value | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 322 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 323 | Identity | Field, Value | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 324 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 325 | Anisotropy Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 326 | Calculation Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 327 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 328 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 329 | Identity | Field, Value | [docs/reference/plugins/lifetime_analysis.md](/reference/plugins/lifetime_analysis.md) |
| 330 | Identity | Field, Value | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 331 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 332 | Identity | Field, Value | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 333 | Identity | Field, Value | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 334 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 335 | Identity | Field, Value | [docs/reference/plugins/menu_switch.md](/reference/plugins/menu_switch.md) |
| 336 | Identity | Field, Value | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 337 | Identity | Field, Value | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 338 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 339 | Identity | Field, Value | [docs/reference/plugins/minesweeper.md](/reference/plugins/minesweeper.md) |
| 340 | Identity | Field, Value | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 341 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 342 | Advanced — user & connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 343 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 344 | Identity | Field, Value | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 345 | Identity | Field, Value | [docs/reference/plugins/ndxplorer.md](/reference/plugins/ndxplorer.md) |
| 346 | Identity | Field, Value | [docs/reference/plugins/number_quest.md](/reference/plugins/number_quest.md) |
| 347 | Identity | Field, Value | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 348 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 349 | Identity | Field, Value | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 350 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 351 | Identity | Field, Value | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 352 | Identity | Field, Value | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 353 | Identity | Field, Value | [docs/reference/plugins/pong.md](/reference/plugins/pong.md) |
| 354 | Identity | Field, Value | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 355 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 356 | Identity | Field, Value | [docs/reference/plugins/proteinmc.md](/reference/plugins/proteinmc.md) |
| 357 | Identity | Field, Value | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 358 | Objective | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 359 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 360 | Polarization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 361 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 362 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 363 | Identity | Field, Value | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 364 | PSF parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 365 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 366 | Fit Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 367 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 368 | Identity | Field, Value | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 369 | Formats | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 370 | ALEX modulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 371 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 372 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 373 | Identity | Field, Value | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 374 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 375 | Identity | Field, Value | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 376 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 377 | Optics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 378 | Scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 379 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 380 | Identity | Field, Value | [docs/reference/plugins/screenshot.md](/reference/plugins/screenshot.md) |
| 381 | Identity | Field, Value | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 382 | Identity | Field, Value | [docs/reference/plugins/setup_channel_definition.md](/reference/plugins/setup_channel_definition.md) |
| 383 | Identity | Field, Value | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 384 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 385 | Segmentation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 386 | Fit (Fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 387 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 388 | Identity | Field, Value | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 389 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 390 | Advanced — connection & authentication | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 391 | Identity | Field, Value | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 392 | Identity | Field, Value | [docs/reference/plugins/style_manager.md](/reference/plugins/style_manager.md) |
| 393 | Identity | Field, Value | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 394 | Identity | Field, Value | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 395 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 396 | IRF & noise | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 397 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 398 | Identity | Field, Value | [docs/reference/plugins/tetris.md](/reference/plugins/tetris.md) |
| 399 | Identity | Field, Value | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 400 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 401 | Identity | Field, Value | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 402 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 403 | Identity | Field, Value | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 404 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 405 | Identity | Field, Value | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 406 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 407 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 408 | Identity | Field, Value | [docs/reference/plugins/traj_energy.md](/reference/plugins/traj_energy.md) |
| 409 | Identity | Field, Value | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 410 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 411 | Identity | Field, Value | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 412 | Reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 413 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 414 | Identity | Field, Value | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 415 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 416 | Identity | Field, Value | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 417 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 418 | Identity | Field, Value | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 419 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 420 | Identity | Field, Value | [docs/reference/plugins/traj_save_topology.md](/reference/plugins/traj_save_topology.md) |
| 421 | Identity | Field, Value | [docs/reference/plugins/traj_tools.md](/reference/plugins/traj_tools.md) |
| 422 | Identity | Field, Value | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 423 | Audio | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 424 | Waterfall params | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 425 | Micro-time | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 426 | Lifetime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 427 | Identity | Field, Value | [docs/reference/plugins/tttr_correlate.md](/reference/plugins/tttr_correlate.md) |
| 428 | Identity | Field, Value | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 429 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 430 | Identity | Field, Value | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 431 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 432 | Identity | Field, Value | [docs/reference/plugins/tttr_histogram.md](/reference/plugins/tttr_histogram.md) |
| 433 | Identity | Field, Value | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 434 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 435 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 436 | Identity | Field, Value | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 437 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 438 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 439 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 440 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 441 | Identity | Field, Value | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 442 | Input / Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 443 | Split options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 444 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 445 | Identity | Field, Value | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 446 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 447 | Identity | Field, Value | [docs/reference/plugins/tttr_toolbox.md](/reference/plugins/tttr_toolbox.md) |
| 448 | Identity | Field, Value | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 449 | Identity | Field, Value | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 450 | Identity | Field, Value | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 451 | Identity | Field, Value | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 452 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 453 | Identity | Field, Value | [docs/reference/plugins/wizards.md](/reference/plugins/wizards.md) |
| 454 | Identity | Field, Value | [docs/reference/plugins/{{ cookiecutter.plugin_name }}.md](/reference/plugins/{{ cookiecutter.plugin_name }}.md) |
| 455 | 1.8.2.1 `gui.console` | Key, Default, Meaning | [docs/reference/settings.md](/reference/settings.md) |
| 456 | Table index | #, Section, Columns, Page | [docs/reference/tables.md](/reference/tables.md) |
| 457 | User-Defined Models in ChiSurf | What it does, Use it when | [docs/reference/user_models.md](/reference/user_models.md) |
