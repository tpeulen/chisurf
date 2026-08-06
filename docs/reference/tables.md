(table-index)=
# Table index

Every table in the documentation, with the section it belongs to and its
columns. Tables carrying *generated* content — the plugin catalogue, the
parameter glossary, the Literature page — are rebuilt by their
generators; the rest are written by hand and are checked when the page
they sit on is reviewed.

*440 tables.*

| # | Section | Columns | Page |
| --- | --- | --- | --- |
| 1 | Entry points | — | [docs/getting_started/index.rst](/getting_started/index.rst) |
| 2 | \qquad (E \approx 0.58). | $\langle R_{DA}\rangle$, $\sigma = 3$ Å, $\sigma = 6$ Å, $\sigma = 10$ Å, $\sigma = 15$ Å | [docs/concepts/accessible_volume.md](/concepts/accessible_volume.md) |
| 3 | The four factors | channel, alias, what it holds | [docs/concepts/accurate_fret.md](/concepts/accurate_fret.md) |
| 4 | \approx 10\ \mathrm{ns}. | system, $\rho$, $\tau/\rho$, $r/r_0$ | [docs/concepts/anisotropy.md](/concepts/anisotropy.md) |
| 5 | The cost: a fused burst is one interval | Control, Question it answers | [docs/concepts/burst_fusion.md](/concepts/burst_fusion.md) |
| 6 | What to report | Report, Because | [docs/concepts/colocalization.md](/concepts/colocalization.md) |
| 7 | Why drift is not just blur | Frame lag $\Delta$, $G(0,0,\Delta)$ uncorrected, corrected | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 8 | C(\xi, \psi) = \mathcal{F}^{-1}\bigl\{\, \mathcal{F}(a)\,\overline{\mathcal{F}(b)} \,\bigr\} | Reference, Behaviour | [docs/concepts/drift_correction.md](/concepts/drift_correction.md) |
| 9 | The model | Array, Meaning | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 10 | The second apparent diffusion time | Power, V_eff/V₀, apparent τ_D, one-component residual, two-component fit | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 11 | Fitting it: a global triplet times two diffusion times | amplitude, τ_D | [docs/concepts/fcs_saturation.md](/concepts/fcs_saturation.md) |
| 12 | Conditioning: the price of similar patterns | $\tau_2$, $\tau_2/\tau_1$, condition number, largest filter value | [docs/concepts/filtered_fcs.md](/concepts/filtered_fcs.md) |
| 13 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | $E$, $6E(1-E)$, $\Delta R/R$ for $\Delta E = 0.02$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 14 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | error in $J$ or $Q_D$, effect on $R_0$ | [docs/concepts/fret.md](/concepts/fret.md) |
| 15 | \frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} . | $\kappa^2$, $R$ scaled by, situation | [docs/concepts/fret.md](/concepts/fret.md) |
| 16 | Linking is not fixing | asserts, uses data, keeps its uncertainty | [docs/concepts/global_analysis.md](/concepts/global_analysis.md) |
| 17 | Decoding: "most likely path" is not "how the photons distribute" | decoder, draws from, photon distribution, dwell / transition structure | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 18 | \qquad\text{here } 10^{3}\ \mathrm{s^{-1}} \dots 5\times10^{4}\ \mathrm{s^{-1}} . | $K$, $k$ ($P=2$, DD/DA), $k$ ($P=3$, with AA) | [docs/concepts/h2mm.md](/concepts/h2mm.md) |
| 19 | When to use something else | Situation, Better tool | [docs/concepts/hidden_markov_models.md](/concepts/hidden_markov_models.md) |
| 20 | Worked numbers | Step, Lag time, Ratio to previous | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 21 | Which method is which | Method, Region read, Clock that dominates, Scale | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 22 | Using it in ChiSurf | Release this, To fit | [docs/concepts/image_correlation.md](/concepts/image_correlation.md) |
| 23 | What the gate actually tested | quantity, measured / model-free, forward model | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 24 | Testing it against simulated dynamics | regime, true rate, fitted, bursts between the states | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 25 | Three sources, one model | source, what it uses, what it is for | [docs/concepts/mfd_fitting.md](/concepts/mfd_fitting.md) |
| 26 | Choosing a density | `dot_density`, points per atom, typical error | [docs/concepts/molecular_surfaces.md](/concepts/molecular_surfaces.md) |
| 27 | What the peak time means | transport, peak of $G(\tau,\delta)$, scaling | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 28 | Reading the numbers | what you see, what it means | [docs/concepts/pair_correlation.md](/concepts/pair_correlation.md) |
| 29 | Three uncertainty estimates, in increasing generality | Method, What it does, Assumes | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 30 | Why the proposal matters so much | Sampler, Proposal, $\tau$, Effective samples per 1000 model evaluations | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 31 | Collapsing: integrate the private parameters out | Sampler, τ(shared), min ESS, ESS / 1000 evals, reported $a$ | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 32 | Changing your mind about a prior, without sampling again | $\hat k$, meaning | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 33 | The numbers you actually publish | lower arm, upper arm | [docs/concepts/parameter_uncertainty.md](/concepts/parameter_uncertainty.md) |
| 34 | Three stages, three failure modes | stage, question, how it fails | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 35 | Why a wavelet, and why two scales | threshold, 128², 256², 512² | [docs/concepts/particle_tracking.md](/concepts/particle_tracking.md) |
| 36 | \mathrm{Var}(k) - \langle k\rangle = \gamma_2\,N\,(\epsilon\,T)^2 , | sample, $\epsilon$, $N$, $\epsilon T$, $\langle k\rangle$, $\mathrm{Var}-\langle k\rangle$, $B$ | [docs/concepts/pch_fida.md](/concepts/pch_fida.md) |
| 37 | How much heterogeneity can PDA actually detect? | $N$ (photons/burst), 20, 50, 100, 200, 500 | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 38 | How much heterogeneity can PDA actually detect? | $\sigma_\text{het}$, $\sigma_\text{obs}$ at $N=50$, at $N=200$, ratio | [docs/concepts/pda2c.md](/concepts/pda2c.md) |
| 39 | What a burst looks like | symbol, excitation → detection | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 40 | \underbrace{M}_{\text{emission}} | matrix, shape, meaning | [docs/concepts/pda3c.md](/concepts/pda3c.md) |
| 41 | The problem with histograms | exchange, histogram, what you can measure | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 42 | Relation to H2MM | H2MM, Gopich–Szabo | [docs/concepts/photon_by_photon_kinetics.md](/concepts/photon_by_photon_kinetics.md) |
| 43 | Choosing a decoder | *Decoder*, what it does, use it for | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 44 | ~6.8 ns. Solid is S0 (low FRET: little red), dashed is S1 (high FRET). | Column, Meaning | [docs/guides/19_h2mm_hidden_markov.md](/guides/19_h2mm_hidden_markov.md) |
| 45 | The lifetime of a state, not of a burst | Detector, Colour, State, Photons (parallel), Photons (perpendicular), Photons, Tau, 2I*, … | [docs/guides/21_lifetime_from_bursts.md](/guides/21_lifetime_from_bursts.md) |
| 46 | Result | table, one row per, columns | [docs/guides/34_exporting_burst_data.md](/guides/34_exporting_burst_data.md) |
| 47 | 5. Choosing a sampler | `method`, Use when | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 48 | [e['mean'] for e in r['parameters']] | `pareto_k`, what to do | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 49 | print(q['name'], q['median'], q['low'], q['high'], q['method'], q['warning']) | Method, What it is, Read the interval as | [docs/guides/39_parameter_uncertainty.md](/guides/39_parameter_uncertainty.md) |
| 50 | Setting it up | Provider, Base URL, Processing location, Key from | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 51 | Things to ask it | Ask it, What it does | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 52 | Using it in the GUI | Mode, What it can do | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 53 | Skills: how it knows *how* | Skill, Loaded when you ask about | [docs/guides/40_ai_assistant.md](/guides/40_ai_assistant.md) |
| 54 | 2. Check the channel mapping | combo, channel | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 55 | Naming differences to watch | ndX, meaning, Hellenkamp | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 56 | bursts = simulation.burst_table(min_photons=50) | factor, declared, recovered | [docs/guides/41_accurate_fret.md](/guides/41_accurate_fret.md) |
| 57 | Loading data | reader, use it for | [docs/guides/42_pda3c.md](/guides/42_pda3c.md) |
| 58 | fetch PDBDEV_00000012 # ...or an integrative model from PDB-IHM | Repository, Looks like, Gives you | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 59 | A simulation is more than motion | What the file says, What you see | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 60 | level, click empty histogram to add one, right-click a marker to remove it. | Map, Opens at, Why | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 61 | Trying it out: the Demo menu | Entry, What it shows | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 62 | distance com, chain A, chain B, mode=4 # one line, centroid to centroid | `mode`, What it draws | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 63 | Where things stand | Area, State | [docs/guides/44_molecular_viewer.md](/guides/44_molecular_viewer.md) |
| 64 | Read the result | Predicted error, Verdict, What to do | [docs/guides/45_scan_precision.md](/guides/45_scan_precision.md) |
| 65 | sample from a stable one with broader populations. | Control, What it does | [docs/guides/46_ndxplorer.md](/guides/46_ndxplorer.md) |
| 66 | What it does | Bridge, ChiSurf RPC, Produces | [docs/guides/47_ndxplorer_bridges.md](/guides/47_ndxplorer_bridges.md) |
| 67 | Where regions appear | Tool, What a region does there | [docs/guides/48_regions.md](/guides/48_regions.md) |
| 68 | 1. Detect | what you see, what it means | [docs/guides/50_particle_tracking.md](/guides/50_particle_tracking.md) |
| 69 | The menu is not a list ndX keeps | Target, RPC, What comes back | [docs/guides/52_send_bursts_to_analysis.md](/guides/52_send_bursts_to_analysis.md) |
| 70 | Unchanged — kept the previous BVA result (🔁 Restart recomputes it) | Step, Reuses when, Recomputes when | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 71 | Everything downstream is handed the same files | Panel, Receives | [docs/guides/53_reusing_results.md](/guides/53_reusing_results.md) |
| 72 | Settings reference | Setting, What it does | [docs/guides/54_hidden_markov_models.md](/guides/54_hidden_markov_models.md) |
| 73 | Which route to use | you want, use, resolution | [docs/guides/55_pair_correlation.md](/guides/55_pair_correlation.md) |
| 74 | 1. Open the calculator and pick a scheme | Scheme, States, Use it for | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 75 | 3. A worked case: Rhodamine 6G at 488 nm | Power, k_exc(0,0), V_eff/V₀, apparent τ_D, G(0) vs unsaturated | [docs/guides/56_fcs_saturation.md](/guides/56_fcs_saturation.md) |
| 76 | 1. Load the folder | Setting, What it does | [docs/guides/57_mfd_fitting.md](/guides/57_mfd_fitting.md) |
| 77 | 3. Set the two controls | Control, Question, How to choose | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 78 | 3. Set the two controls | Threshold, Window, Bursts, Proximity-ratio width | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 79 | 4. Judge it from the summary, not from the burst count | Row, Expected, What it means if not | [docs/guides/58_burst_fusion.md](/guides/58_burst_fusion.md) |
| 80 | What is already in scope | Name, What it is | [docs/guides/59_console.md](/guides/59_console.md) |
| 81 | The correction | factor, symbol, meaning | [docs/guides/fret_calibration.md](/guides/fret_calibration.md) |
| 82 | Compute engines | engine, description, accuracy | [docs/guides/h2mm.md](/guides/h2mm.md) |
| 83 | Where each guide starts in ChiSurf | Tutorial, ChiSurf entry point | [docs/guides/index.md](/guides/index.md) |
| 84 | Design Choices | Aspect, Implementation | [docs/guides/irf_estimation.md](/guides/irf_estimation.md) |
| 85 | Convolution modes | — | [docs/manual/fluorescence_lifetime.rst](/manual/fluorescence_lifetime.rst) |
| 86 | From the shell | — | [docs/manual/parameter_sampling.rst](/manual/parameter_sampling.rst) |
| 87 | Parameters | — | [docs/manual/partial_donordonor_energy_migration.rst](/manual/partial_donordonor_energy_migration.rst) |
| 88 | Parameters | — | [docs/manual/wormlike_chain.rst](/manual/wormlike_chain.rst) |
| 89 | Code index | #, Language, Section, Lines, Verified, Page | [docs/reference/code.md](/reference/code.md) |
| 90 | Figure index | #, Image, Caption, Origin, Page | [docs/reference/figures.md](/reference/figures.md) |
| 91 | One file, many curves | curve type, meaning | [docs/reference/file_formats/fcs_files.md](/reference/file_formats/fcs_files.md) |
| 92 | The setting that chooses the method | Setting, What you get | [docs/reference/file_formats/ics_files.md](/reference/file_formats/ics_files.md) |
| 93 | Reading a parameter table | Appearance, Meaning | [docs/reference/parameter_linking.md](/reference/parameter_linking.md) |
| 94 | Parameter glossary | Parameter, Meaning, Keywords | [docs/reference/parameters.md](/reference/parameters.md) |
| 95 | Identity | Field, Value | [docs/reference/plugins/about.md](/reference/plugins/about.md) |
| 96 | Identity | Field, Value | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 97 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 98 | Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 99 | Dyes (database) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 100 | Photophysics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 101 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 102 | Optics prior (light path) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 103 | Procedure | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/accurate_fret.md](/reference/plugins/accurate_fret.md) |
| 104 | Identity | Field, Value | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 105 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/acq.md](/reference/plugins/acq.md) |
| 106 | Identity | Field, Value | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 107 | API Configuration | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 108 | Models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 109 | Generation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ai_settings.md](/reference/plugins/ai_settings.md) |
| 110 | Identity | Field, Value | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 111 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/batch_analysis.md](/reference/plugins/batch_analysis.md) |
| 112 | Identity | Field, Value | [docs/reference/plugins/bid_to_analysis.md](/reference/plugins/bid_to_analysis.md) |
| 113 | Identity | Field, Value | [docs/reference/plugins/boarding.md](/reference/plugins/boarding.md) |
| 114 | Identity | Field, Value | [docs/reference/plugins/breakout.md](/reference/plugins/breakout.md) |
| 115 | Identity | Field, Value | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 116 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_2cde.md](/reference/plugins/burst_2cde.md) |
| 117 | Identity | Field, Value | [docs/reference/plugins/burst_analysis.md](/reference/plugins/burst_analysis.md) |
| 118 | Identity | Field, Value | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 119 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_background.md](/reference/plugins/burst_background.md) |
| 120 | Identity | Field, Value | [docs/reference/plugins/burst_browser.md](/reference/plugins/burst_browser.md) |
| 121 | Identity | Field, Value | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 122 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_bva.md](/reference/plugins/burst_bva.md) |
| 123 | Identity | Field, Value | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 124 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_ebfret.md](/reference/plugins/burst_ebfret.md) |
| 125 | Identity | Field, Value | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 126 | Correlator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 127 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 128 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fcs_correlator.md](/reference/plugins/burst_fcs_correlator.md) |
| 129 | Identity | Field, Value | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 130 | Fusion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 131 | P(same molecule) estimate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 132 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_fusion.md](/reference/plugins/burst_fusion.md) |
| 133 | Identity | Field, Value | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 134 | Photons | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 135 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 136 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 137 | Extras | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 138 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_gs.md](/reference/plugins/burst_gs.md) |
| 139 | Identity | Field, Value | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 140 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_h2mm.md](/reference/plugins/burst_h2mm.md) |
| 141 | Identity | Field, Value | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 142 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_irf_bg.md](/reference/plugins/burst_irf_bg.md) |
| 143 | Identity | Field, Value | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 144 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_mle_analysis.md](/reference/plugins/burst_mle_analysis.md) |
| 145 | Identity | Field, Value | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 146 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 147 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/burst_selection.md](/reference/plugins/burst_selection.md) |
| 148 | Identity | Field, Value | [docs/reference/plugins/burst_state_mle.md](/reference/plugins/burst_state_mle.md) |
| 149 | Identity | Field, Value | [docs/reference/plugins/calculators.md](/reference/plugins/calculators.md) |
| 150 | Identity | Field, Value | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 151 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/chimol.md](/reference/plugins/chimol.md) |
| 152 | Identity | Field, Value | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 153 | File | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 154 | Acquisition | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 155 | Brush & Decay | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 156 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 157 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/clsm.md](/reference/plugins/clsm.md) |
| 158 | Identity | Field, Value | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 159 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 160 | Simulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/clsm_generator.md](/reference/plugins/clsm_generator.md) |
| 161 | Identity | Field, Value | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 162 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/code_editor.md](/reference/plugins/code_editor.md) |
| 163 | Identity | Field, Value | [docs/reference/plugins/converter.md](/reference/plugins/converter.md) |
| 164 | Identity | Field, Value | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 165 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/database_connector.md](/reference/plugins/database_connector.md) |
| 166 | Identity | Field, Value | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 167 | F-test — compare two nested models | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 168 | χ²-max — upper limit from one fit | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/f_test.md](/reference/plugins/f_test.md) |
| 169 | Identity | Field, Value | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 170 | Species (lifetime + diffusion) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 171 | Kinetics / statistics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs-lfcs-sim.md](/reference/plugins/fcs-lfcs-sim.md) |
| 172 | Identity | Field, Value | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 173 | Diffusion / volume | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 174 | Occupancy | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 175 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_calculator.md](/reference/plugins/fcs_calculator.md) |
| 176 | Identity | Field, Value | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 177 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_channel_preset.md](/reference/plugins/fcs_channel_preset.md) |
| 178 | Identity | Field, Value | [docs/reference/plugins/fcs_convert.md](/reference/plugins/fcs_convert.md) |
| 179 | Identity | Field, Value | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 180 | Correlation Channels | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 181 | Correlation Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 182 | Channel selection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 183 | Macro time interval | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 184 | Filter | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 185 | Change-point parameters (BOCPD / Kalman / CUSUM) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 186 | Plot settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 187 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_correlator.md](/reference/plugins/fcs_correlator.md) |
| 188 | Identity | Field, Value | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 189 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 190 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_filter_calculator.md](/reference/plugins/fcs_filter_calculator.md) |
| 191 | Identity | Field, Value | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 192 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_merger.md](/reference/plugins/fcs_merger.md) |
| 193 | Identity | Field, Value | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 194 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fcs_saturation.md](/reference/plugins/fcs_saturation.md) |
| 195 | Identity | Field, Value | [docs/reference/plugins/fcs_toolbox.md](/reference/plugins/fcs_toolbox.md) |
| 196 | Identity | Field, Value | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 197 | 2D-FDC | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 198 | Lifetime inversion | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 199 | IRF | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 200 | Dynamics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 201 | Kinetics (advanced) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 202 | 1D-MEM + Gaussian | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 203 | Simulator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 204 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/flc-2d.md](/reference/plugins/flc-2d.md) |
| 205 | Identity | Field, Value | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 206 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fps_json_editor.md](/reference/plugins/fps_json_editor.md) |
| 207 | Identity | Field, Value | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 208 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 209 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_calculator.md](/reference/plugins/fret_calculator.md) |
| 210 | Identity | Field, Value | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 211 | Inputs | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 212 | Docking | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 213 | Monte-Carlo (mc method only) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 214 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/fret_docking.md](/reference/plugins/fret_docking.md) |
| 215 | Identity | Field, Value | [docs/reference/plugins/fret_line.md](/reference/plugins/fret_line.md) |
| 216 | Identity | Field, Value | [docs/reference/plugins/games.md](/reference/plugins/games.md) |
| 217 | Identity | Field, Value | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 218 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/globalview.md](/reference/plugins/globalview.md) |
| 219 | Identity | Field, Value | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 220 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/help.md](/reference/plugins/help.md) |
| 221 | Identity | Field, Value | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 222 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 223 | Fitting | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 224 | State scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 225 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hmm.md](/reference/plugins/hmm.md) |
| 226 | Identity | Field, Value | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 227 | Executable & input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 228 | Primary model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 229 | Solvent & macromolecule | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 230 | Optional calculations | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 231 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 232 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/hydropro.md](/reference/plugins/hydropro.md) |
| 233 | Identity | Field, Value | [docs/reference/plugins/imaging_tools.md](/reference/plugins/imaging_tools.md) |
| 234 | Identity | Field, Value | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 235 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_calibration.md](/reference/plugins/img_calibration.md) |
| 236 | Identity | Field, Value | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 237 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 238 | Background / thresholds | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 239 | Scatter gate | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 240 | Region of interest | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 241 | Objects (punctate signal) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 242 | Significance / profile | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_coloc.md](/reference/plugins/img_coloc.md) |
| 243 | Identity | Field, Value | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 244 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 245 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_drift.md](/reference/plugins/img_drift.md) |
| 246 | Identity | Field, Value | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 247 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 248 | Scanner | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 249 | Display and estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 250 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_flow.md](/reference/plugins/img_flow.md) |
| 251 | Identity | Field, Value | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 252 | Settings | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 253 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 254 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_frc.md](/reference/plugins/img_frc.md) |
| 255 | Identity | Field, Value | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 256 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_intensity.md](/reference/plugins/img_pixel_intensity.md) |
| 257 | Identity | Field, Value | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 258 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_micro_time.md](/reference/plugins/img_pixel_micro_time.md) |
| 259 | Identity | Field, Value | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 260 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 261 | IRF preparation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 262 | Fit flags | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 263 | Background | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 264 | Performance | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 265 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_mle.md](/reference/plugins/img_pixel_mle.md) |
| 266 | Identity | Field, Value | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 267 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_nb.md](/reference/plugins/img_pixel_nb.md) |
| 268 | Identity | Field, Value | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 269 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 270 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_pixel_phasor.md](/reference/plugins/img_pixel_phasor.md) |
| 271 | Identity | Field, Value | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 272 | Movie | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 273 | Simulate instead | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 274 | 1. Detect | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 275 | 2. Link | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 276 | 3. Transport | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 277 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/img_tracking.md](/reference/plugins/img_tracking.md) |
| 278 | Analysis → Kinetics | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 279 | Core | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 280 | Help | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 281 | Imaging | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 282 | Imaging → Lifetime | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 283 | Imaging → Simulate | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 284 | Imaging → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 285 | Main → Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 286 | Microscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 287 | Setup | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 288 | Spectroscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 289 | Spectroscopy → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 290 | Spectroscopy → Fluorescence Correlation Spectroscopy | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 291 | Spectroscopy → Fluorescence decay | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 292 | Spectroscopy → Single-Molecule | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 293 | Structure → Computation | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 294 | Structure → FRET | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 295 | Structure → Structure | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 296 | Structure → Trajectory | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 297 | Tools | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 298 | Tools → Converter | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 299 | Tools → Miscellaneous | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 300 | Tools → Miscellaneous → Games | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 301 | Tools → TTTR | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 302 | {{ cookiecutter.plugin_category }} | Plugin, Summary | [docs/reference/plugins/index.md](/reference/plugins/index.md) |
| 303 | Identity | Field, Value | [docs/reference/plugins/intensity_trace.md](/reference/plugins/intensity_trace.md) |
| 304 | Identity | Field, Value | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 305 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/irf_estimator.md](/reference/plugins/irf_estimator.md) |
| 306 | Identity | Field, Value | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 307 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 308 | Anisotropy Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 309 | Calculation Options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 310 | Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 311 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/kappa2_dist.md](/reference/plugins/kappa2_dist.md) |
| 312 | Identity | Field, Value | [docs/reference/plugins/lifetime_analysis.md](/reference/plugins/lifetime_analysis.md) |
| 313 | Identity | Field, Value | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 314 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/lightpath_simulator.md](/reference/plugins/lightpath_simulator.md) |
| 315 | Identity | Field, Value | [docs/reference/plugins/lltf.md](/reference/plugins/lltf.md) |
| 316 | Identity | Field, Value | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 317 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/maxent_decay.md](/reference/plugins/maxent_decay.md) |
| 318 | Identity | Field, Value | [docs/reference/plugins/menu_switch.md](/reference/plugins/menu_switch.md) |
| 319 | Identity | Field, Value | [docs/reference/plugins/microtime_histogram.md](/reference/plugins/microtime_histogram.md) |
| 320 | Identity | Field, Value | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 321 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/microtime_shifter.md](/reference/plugins/microtime_shifter.md) |
| 322 | Identity | Field, Value | [docs/reference/plugins/minesweeper.md](/reference/plugins/minesweeper.md) |
| 323 | Identity | Field, Value | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 324 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 325 | Advanced — user & connection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 326 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/mmfdb_admin.md](/reference/plugins/mmfdb_admin.md) |
| 327 | Identity | Field, Value | [docs/reference/plugins/model_manager.md](/reference/plugins/model_manager.md) |
| 328 | Identity | Field, Value | [docs/reference/plugins/ndxplorer.md](/reference/plugins/ndxplorer.md) |
| 329 | Identity | Field, Value | [docs/reference/plugins/number_quest.md](/reference/plugins/number_quest.md) |
| 330 | Identity | Field, Value | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 331 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/pch.md](/reference/plugins/pch.md) |
| 332 | Identity | Field, Value | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 333 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/phasor_calculator.md](/reference/plugins/phasor_calculator.md) |
| 334 | Identity | Field, Value | [docs/reference/plugins/plugin_check.md](/reference/plugins/plugin_check.md) |
| 335 | Identity | Field, Value | [docs/reference/plugins/plugin_manager.md](/reference/plugins/plugin_manager.md) |
| 336 | Identity | Field, Value | [docs/reference/plugins/pong.md](/reference/plugins/pong.md) |
| 337 | Identity | Field, Value | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 338 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/project_browser.md](/reference/plugins/project_browser.md) |
| 339 | Identity | Field, Value | [docs/reference/plugins/proteinmc.md](/reference/plugins/proteinmc.md) |
| 340 | Identity | Field, Value | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 341 | Objective | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 342 | Model | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 343 | Polarization | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 344 | Sampling | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 345 | Display | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_calculator.md](/reference/plugins/psf_calculator.md) |
| 346 | Identity | Field, Value | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 347 | PSF parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 348 | Detection | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 349 | Fit Results | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 350 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/psf_determination.md](/reference/plugins/psf_determination.md) |
| 351 | Identity | Field, Value | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 352 | Formats | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 353 | ALEX modulation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 354 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 355 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/ptu_alex_creator.md](/reference/plugins/ptu_alex_creator.md) |
| 356 | Identity | Field, Value | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 357 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/quenching_estimator.md](/reference/plugins/quenching_estimator.md) |
| 358 | Identity | Field, Value | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 359 | Sample | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 360 | Optics | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 361 | Scan | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 362 | Estimator | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/rics_precision.md](/reference/plugins/rics_precision.md) |
| 363 | Identity | Field, Value | [docs/reference/plugins/screenshot.md](/reference/plugins/screenshot.md) |
| 364 | Identity | Field, Value | [docs/reference/plugins/setup.md](/reference/plugins/setup.md) |
| 365 | Identity | Field, Value | [docs/reference/plugins/setup_channel_definition.md](/reference/plugins/setup_channel_definition.md) |
| 366 | Identity | Field, Value | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 367 | Analysis | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 368 | Segmentation | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 369 | Fit (Fit23) | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 370 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/sm_image_mle.md](/reference/plugins/sm_image_mle.md) |
| 371 | Identity | Field, Value | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 372 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 373 | Advanced — connection & authentication | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/spectra_downloader.md](/reference/plugins/spectra_downloader.md) |
| 374 | Identity | Field, Value | [docs/reference/plugins/structure_tools.md](/reference/plugins/structure_tools.md) |
| 375 | Identity | Field, Value | [docs/reference/plugins/style_manager.md](/reference/plugins/style_manager.md) |
| 376 | Identity | Field, Value | [docs/reference/plugins/switch_user.md](/reference/plugins/switch_user.md) |
| 377 | Identity | Field, Value | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 378 | Histogram | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 379 | IRF & noise | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 380 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/synthetic_decay.md](/reference/plugins/synthetic_decay.md) |
| 381 | Identity | Field, Value | [docs/reference/plugins/tetris.md](/reference/plugins/tetris.md) |
| 382 | Identity | Field, Value | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 383 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tr_anisotropy.md](/reference/plugins/tr_anisotropy.md) |
| 384 | Identity | Field, Value | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 385 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/trace_browser.md](/reference/plugins/trace_browser.md) |
| 386 | Identity | Field, Value | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 387 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_align.md](/reference/plugins/traj_align.md) |
| 388 | Identity | Field, Value | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 389 | Input | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 390 | Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_convert.md](/reference/plugins/traj_convert.md) |
| 391 | Identity | Field, Value | [docs/reference/plugins/traj_energy.md](/reference/plugins/traj_energy.md) |
| 392 | Identity | Field, Value | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 393 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_energy_calculator.md](/reference/plugins/traj_energy_calculator.md) |
| 394 | Identity | Field, Value | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 395 | Reference | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 396 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_fret.md](/reference/plugins/traj_fret.md) |
| 397 | Identity | Field, Value | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 398 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_join.md](/reference/plugins/traj_join.md) |
| 399 | Identity | Field, Value | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 400 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_remove_clashes.md](/reference/plugins/traj_remove_clashes.md) |
| 401 | Identity | Field, Value | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 402 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/traj_rotate_translate.md](/reference/plugins/traj_rotate_translate.md) |
| 403 | Identity | Field, Value | [docs/reference/plugins/traj_save_topology.md](/reference/plugins/traj_save_topology.md) |
| 404 | Identity | Field, Value | [docs/reference/plugins/traj_tools.md](/reference/plugins/traj_tools.md) |
| 405 | Identity | Field, Value | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 406 | Audio | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 407 | Waterfall params | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 408 | Micro-time | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 409 | Lifetime | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_audifier.md](/reference/plugins/tttr_audifier.md) |
| 410 | Identity | Field, Value | [docs/reference/plugins/tttr_correlate.md](/reference/plugins/tttr_correlate.md) |
| 411 | Identity | Field, Value | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 412 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_count_rate_analysis.md](/reference/plugins/tttr_count_rate_analysis.md) |
| 413 | Identity | Field, Value | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 414 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_header_edit.md](/reference/plugins/tttr_header_edit.md) |
| 415 | Identity | Field, Value | [docs/reference/plugins/tttr_histogram.md](/reference/plugins/tttr_histogram.md) |
| 416 | Identity | Field, Value | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 417 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 418 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_image_browser.md](/reference/plugins/tttr_image_browser.md) |
| 419 | Identity | Field, Value | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 420 | General | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 421 | Parameters | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 422 | Advanced | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 423 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_lut_tools.md](/reference/plugins/tttr_lut_tools.md) |
| 424 | Identity | Field, Value | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 425 | Input / Output | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 426 | Split options | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 427 | Batch | Parameter, Attribute, Type, Default, Range / options, Meaning | [docs/reference/plugins/tttr_splitter.md](/reference/plugins/tttr_splitter.md) |
| 428 | Identity | Field, Value | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 429 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/tttr_time_windows.md](/reference/plugins/tttr_time_windows.md) |
| 430 | Identity | Field, Value | [docs/reference/plugins/tttr_toolbox.md](/reference/plugins/tttr_toolbox.md) |
| 431 | Identity | Field, Value | [docs/reference/plugins/updater.md](/reference/plugins/updater.md) |
| 432 | Identity | Field, Value | [docs/reference/plugins/user_editor.md](/reference/plugins/user_editor.md) |
| 433 | Identity | Field, Value | [docs/reference/plugins/vv_vh_anisotropy.md](/reference/plugins/vv_vh_anisotropy.md) |
| 434 | Identity | Field, Value | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 435 | JSON-RPC methods | Method, Long-running, Summary | [docs/reference/plugins/vv_vh_g_factor.md](/reference/plugins/vv_vh_g_factor.md) |
| 436 | Identity | Field, Value | [docs/reference/plugins/wizards.md](/reference/plugins/wizards.md) |
| 437 | Identity | Field, Value | [docs/reference/plugins/{{ cookiecutter.plugin_name }}.md](/reference/plugins/{{ cookiecutter.plugin_name }}.md) |
| 438 | 1.8.2.1 `gui.console` | Key, Default, Meaning | [docs/reference/settings.md](/reference/settings.md) |
| 439 | Table index | #, Section, Columns, Page | [docs/reference/tables.md](/reference/tables.md) |
| 440 | User-Defined Models in ChiSurf | What it does, Use it when | [docs/reference/user_models.md](/reference/user_models.md) |
