# References

* [Architecture Doc](architecture-doc.md) - The maintained source-of-truth architecture document.
* [Project Instructions](claude-md.md) - CLAUDE.md, the agent-facing guidance for this repo.
* [Roadmap PRDs](roadmap-prds.md) - Numbered PRD design notes that drive current work.
* [Known issues & gotchas](known-issues.md) - Open functional bugs and recurring engineering pitfalls distilled from working bug logs.
* [MMFDB architecture ideas](mmfdb-architecture-ideas.md) - The observed-problem → design-decision rationale behind the MMFDB architecture PRDs (17–27).
* [MMFDB LIMS diagnosis](mmfdb-lims-diagnosis.md) - LIMS gap analysis and prior-art comparison behind the provenance/LIMS PRDs (12–15).
* [Node/workflow-toolkit lessons](orange3-lessons.md) - Architecture lessons from an established visual node/workflow analysis toolkit, mapped to PRDs.
* [ELN crosslinking & info-management lessons](eln-crosslinking-lessons.md) - What a mature ELN's auth/linking/tagging/metadata model teaches MMFDB; adopted metadata→edge materialization + resolvable audit labels, deferred a tags layer.
* [Modelling / ProteinMC roadmap](modelling-roadmap.md) - Durable modelling/simulation roadmap notes salvaged from a personal worklist.
* [Two-focus FCS (2fFCS) status and gaps](two-focus-fcs.md) - What ChiSurf's absolute-diffusion two-focus FCS models cover today and what a full Dertinger 2fFCS workflow still needs.
* [FCS model theory](fcs-model-theory.md) - The physics behind the FCS fit-model catalogue: the G(τ) decomposition, confocal Gaussian MDF, the τ_D-vs-D parameterizations, triplet/bunching/anti-bunching/flow/two-focus factors, and derived quantities (Veff, concentration, cpm, focus calibration). Pedagogy drawn from QuickFit3's help.
* [TCSPC lifetime theory](tcspc-lifetime-theory.md) - Reconvolution fitting of fluorescence decays: the multi-exponential model, the IRF and the reconvolution integral, scatter/background/pile-up/DNL nuisances, least-squares vs fit2x Poisson-MLE, and amplitude- vs intensity-weighted average lifetimes.
* [smFRET burst analysis](smfret-burst-analysis.md) - Single-molecule burst analysis: burst search, proximity ratio vs accurate FRET efficiency E, ALEX/PIE stoichiometry S, and the four correction factors (leakage, direct excitation, gamma, beta) that straighten the E–S FRET line.
* [Photon-by-photon HMM (H2MM)](h2mm-theory.md) - The hidden-Markov model for confocal photon streams: per-channel emission + transition-rate matrices, why H2MM works on raw inter-photon times, Baum-Welch/forward-backward, model selection (BIC/ICL), and dwell/transition outputs.
* [Accessible-volume (AV) dye modeling](accessible-volume-theory.md) - Linker-tethered dye position distributions: the AV grid model, mean position and ACV reweighting, the three AV-to-distance measures, the κ²=2/3 assumption, and how AV distances become FRET restraints for structural modeling.
* [FCS catalogue & FLCS filters: PAM port](fcs-pam-port.md) - The PAM-referenced (A/B-verified) FCS fit-model catalogue expansion and FLCS lifetime-filter fixes, with remaining gaps.
* [QuickFit3 mining — algorithms & models](quickfit3-mining.md) - Survey of ~80 QuickFit3 plugins for portable algorithms, models, UI patterns; ranked by value/effort against chisurf's coverage. Identifies Tier-1 gaps (TIRF-FCS, SPIM-FCS, imaging-FCS correlation, global optimization) and reference implementations.
* [Spectral crosstalk / linear-mixing core](crosstalk.md) - The shared crosstalk-matrix utility (build/apply/invert) behind the light-path calculator, ratiometric/sensitized-emission FRET, phasor unmixing and DDEM.
* [smFRET calibration: light-path prior → data-optimized posterior](fret-calibration.md) - Calibration factors as fitting parameters whose prior comes from the light-path calculator and whose posterior comes from optimizing against burst E-S data.
* [VV/VH stacked-decay format (historically "jordi")](vv-vh-decay-format.md) - Descriptive name, layout, and API for the stacked polarization-resolved decay format; records the historic "jordi" name for discoverability.
