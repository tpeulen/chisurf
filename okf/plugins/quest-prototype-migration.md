---
type: Migration Plan
title: QuEst prototype migration (MalE quenching analysis)
description: Gap matrix between the MalE quenching-analysis prototype (~/dev/quest/prototype) and the quenching_estimator plugin, the split into parallel work packages with file claims, and the reference numbers each port must reproduce.
resource: chisurf/plugins/quenching_estimator/
tags: [plugins, modelling, quenching, quest, migration, prd-154]
timestamp: '2026-10-20T00:00:00Z'
---

# Where to pick this up

The plan below is the open front. Nothing in `chisurf/` has been changed for it yet.

1. **Open: WP0 (data + golden) first.** Every other package tests against
   `test/baselines/male_prototype.json`, so this file has to exist before they start.
   **Measure:** it is made by *executing* the prototype's deterministic notebook cells
   (Steps 0–3, cell 25 helpers, the `Site` class of cell 29) against the prototype's
   own `cache/` npz files. Copying printed numbers is not enough. The notebook's printed
   tables are rounded to 2–4 digits, and its table in cell 17 is truncated (`...`).
   **Trap:** the stored notebook outputs are from a cordeshub run (`RUN_STAMP 20261001-134626`).
   That run's CSVs are *not* in `prototype/output/`. The full-model CSVs that are on disk
   (`20260930-162323_*`) come from an older model (lam free, no `dtau_shield`, no `FIXED`),
   so do not use them as fit references. Data-only CSVs (`20261001-142438_*`) are identical to
   the notebook (checked: `measured_lifetimes_with_errors.csv`, `chapter1_stern_volmer_posterior.csv`).
2. **Open: WP2 (IMP.bff kernels) blocks WP3.** Without per-voxel exposure, rotamer quencher
   ensembles and voxel-centre/neighbour accessors in IMP.bff, the site tables would have to
   be written in Python here. That breaks the rule that geometry kernels belong in IMP.bff, and it
   costs about 6 min per 54 tables in pure Python. The `water_exposure` loop over 64 shell points
   with Python per-voxel KD queries is the hot spot. scipy is no longer a chisurf runtime dependency
   ([scipy retirement](/subsystems/scipy-retirement.md)), so the prototype's `cKDTree` cannot be
   carried over either.
3. **Open: owner questions to settle before WP4 is accepted** (findings from reading the notebook):
   (a) **The "key figure" does not show what its text claims in the stored run.** Stage B and
     Stage C both give a quench scale of 0.11 (0.08–0.15/0.16). The narrowing that cells 50/56
     promise is not there. The profile plot only draws Laplace-Gaussian samples (`profile()`),
     not a profile likelihood. A real profile, as in `it08/it10 *_profiles.csv`, is a WP4 option.
   (b) **Direct method vs random walk:** 2.59 ns vs 2.31 ± 0.03 ns (APO 233, slow 0.3, L 21.5).
     That passes the 0.35 ns tolerance, but it is a 12 % gap, and the text calls it "exact".
     WP3 must decide whether the IMP.bff closed-form `DynamicAccessibleVolume.update_occupancy`
     (Itô flux, p ∝ 1/D) is the same estimator as the prototype's `p ∝ 1/s`, and must record which
     one is used.
   (c) **AF488 rms 0.62 ns vs median |dev| 0.047 ns.** Site 233 apo alone causes the gap
     (measured 1.339 ns, LOO z = 15.3). Cy3B has only 5 sites (10 lifetimes).
   (d) Cell 32's markdown says "16 searches", but the code runs `N_STARTS = 64`.
   (e) **AV width/grid conflict** (see the conflicts table): MalE uses W 0.5 / dg 0.5. The owner's 2026-10-11 "all use same defaults" sets W 4.5 / dg 0.9. Proposed: the notebook values are measured analysis settings, and the generic defaults stay IMP.bff's.
4. **Blocked: German/French catalogues** of the new view.json are deferred to the i18n batch.
   Owner rule: no translation work in PRD-154 batches.
5. **Tried and reverted:** (in the prototype itself, do not re-port) the Brownian-walk *objective*
   (it01–it06) as the fit target. It does not equilibrate at slow factors ≤ 0.1 (it07 docstring), and the
   equilibrium ensemble replaced it **in the inverse fit**. The walk itself stays (owner decision 2026-10-20, see WP9).
   A single stickiness or a residue-count shielding term
   `exp(-α n)` (it11) was replaced by per-group stickiness (it08) and Shrake–Rupley exposure
   (it12). The Cauchy loss of it05 was replaced by the Student-t (ν = 3) search plus a Gaussian
   joint fit. The AF4_C2R linker (16.46 Å) was the wrong reagent; AF488 is A48_C1R, 20.4 Å (it10).
6. **Open: WP8** marks the prototype as migrated, last, once every WP has a commit hash.
7. **Open: WP9.** The plugin's forward simulator still produces the known-wrong number in the sticky regime
   (quest known-issue "At QuEst's default stickiness (0.1) the dye walk does not equilibrate", 2026-09-30).
   **Measure:** MalE APO 95, AF488 reference kQ: the walk gives τX 1.36 ns at slow 0.3 and 2.41 ns at slow 0.1,
   which is impossible at equilibrium. **Owner decision 2026-10-20: keep both ensembles** — the equilibrium ensemble
   (the notebook's, for static τX/QY and the inverse fit) **and** the Brownian walk (more straightforward for FRET:
   donor and acceptor move in time, photon race). The sticky-regime defect is fixed by **solving the diffusion PDE**
   (Smoluchowski with the stickiness potential and the quenching sink on the AV grid; IMP.bff's grid diffusion solver),
   whose stationary state must equal the equilibrium ensemble — not by dropping the walk. The quest package never
   had the equilibrium ensemble, so the move did not lose it.
8. **Open: tracked in PRD-154 as W16** ([prd-154](/prds/prd-154.md)).

# The rest of the quest repo vs the plugin (checked 2026-10-20)

`fe93055` (the move) is quest's HEAD: there are **no quest commits after the move**. The last code commits before it
are `bdcf3e8` (AV defaults from IMP.bff), `b84c88d` (load_project_dict refuses non-projects), `0c4f121` (attach to the
first protein chain), `741dd1a` (no numexpr), `148b891` (numba retired), `4102e50`, `3e197b9` (PET chemistry from the
compiled core). All of them are present in the plugin (`gui/form_model.py:276-283`, `:455`; no numexpr/numba in `core/`;
`test/test_{av_defaults,no_numba,pet_chemistry_source,quencher_distances}.py`). The plugin's `core/av.py`, `dye_diffusion.py`
and `structure/reader.py` differ by hundreds of lines from quest's because of the deliberate port to the flat IMP.bff API.
`dye_repository.json` is byte-identical.

Never brought over. Each entry says where it goes or why it is skipped.

| quest item | status | disposition |
|---|---|---|
| `notebooks/01_quenching`, `02_fret`, `03_et_distance_distribution` (E(t) → distance distribution), `04_diffusion_modulated_fret` (Haas–Steinberg PDE), `notebooks/quest_notebook.py` | not in chisurf; the docs do not mention Haas–Steinberg | **WP7b**: port 01–03 as plugin `examples/*.py` scripts (headless, numbers asserted) plus guide sections. 04 needs a 1-D PDE solver: check the IMP.bff `DiffusionSolver` first. Skip 04 if it would add a dependency. |
| `examples/01_donor_quenching.py`, `02_fret_pair.py`, `03_labeling_scan.py`, `_common.py`, `tests/test_examples.py`, `tests/test_notebooks.py` | missing | WP7b (same files under `examples/`, test `test/test_examples.py`) |
| `doc/quenching_manual.md` + `doc/img/quenching_manual/*` (legacy Qt manual), `doc/index.md`, `doc/cli.md` | partly covered by `docs/guides/80_quenching_estimator.md` | WP7: fold the CLI table into guide 80's *Headless* section. The manual describes the retired Qt GUI: skip. |
| `doc/parameters.md` (+ `.de`/`.fr`), `doc/generate_parameter_docs.py` | covered by the generated `docs/reference/plugins/quenching_estimator.md` | skip; de/fr goes to the deferred i18n batch |
| `quest/rpc/zmq_server.py`, `tests/test_zmq_rpc.py` | chisurf's server hosts the plugin's RPC | skip (chisurf server), keep `test/test_rpc_methods.py` |
| `webui/` (React frontend + FastAPI backend + desktop shell), `tests/test_webui_e2e.py` | not ported | skip: the release is emtk-only (W15) |
| `quest/hosts/chisurf.py`, `quest/gui/*` Qt widgets, `tour.py`, `theme.py` | replaced by emtk card + guide.json | skip |
| `simulation_old/` (Cython/C++ legacy walk) | legacy | skip |
| `tests/numba_oracles`, `test_numba_parity.py` | numba is retired | skip (the parity was proven before retirement, `148b891`) |
| `okf/references/pet-quenching-theory.md` | partly in `docs/concepts/dye_quenching.md` | WP7 checks that its approximations list ("what the numbers can and cannot be trusted to mean") is in the concept |
| `okf/references/known-issues.md`: walk does not equilibrate at slow 0.1 | open, inherited | **WP9** |
| known-issue: IMP.bff C++ fps.json reader collapses a 3-radius AV to 1 radius | upstream, open in quest | WP2 re-checks it in imp.bff and files it there if still open |
| `handover.md`: `asa`/`spherePoints` → IMP (`DUP-05`) | `core/av.py:535,542` still has them | WP2's `probe_solvent_exposure` and IMP.bff `sphere_points` replace them (WP9 deletes the copies) |
| `okf/validation/2026-10-06-contact-distances.json` | receipt only | skip (its test is `test/test_quencher_distances.py`) |
| `data/*.xlsx` (untracked in quest) | missing | WP0 (CSV under `examples/male/`) |
| `okf/subsystems/quenching-model.md` § "Dye-specific kQ from amino-acid titrations" | describes an *older* method, see conflicts | the notebook wins; WP7 writes the current method |

# Conflicts: the notebook wins (owner precedence rule)

| topic | quest package / it-scripts / quest OKF | notebook (wins) | owner |
|---|---|---|---|
| Ensemble for τX | Brownian walk + photon race (`core/dye_diffusion.py`, it01–it06) | equilibrium ensemble p ∝ ∏ s_t^(−n_t), no walk (cell 22) | WP3 (analysis), WP9 (forward sim) |
| Stickiness | one `slow_factor` 0.1 for every residue in every dye preset (`settings/dye_repository.json`) | five chemical groups + common, ridge prior ln 10 | WP1 presets, WP4 |
| kq error model | σ = max(slope SE, leave-one-day-out jackknife, day-to-day 0.11 M⁻¹ + 7 %) (quest OKF quenching-model) | hierarchical closed-form posterior, day-to-day abs 0.01 M⁻¹ + rel 2 % | WP1 |
| Negative/weak kq | "negative or not above 2σ counts as no quenching" (OKF; it scripts; notebook `load_titrations` still computes the unused flag `counts`) | positive part only, no 2σ cut (cell 19) | WP1 |
| Cy3B brightening | Cy3B τ₀ freed (OKF "Findings") | τ₀ fixed at the free dye, + `dtau_shield·(1−e)` (cell 41); polarity brightening tested and rejected (quest `d3c5414`) | WP4 |
| Water shielding | `exp(−α n)` (it11), `e^γ` option (it12) | `kq_w,free · e`, zero parameters (cell 50) | WP4 |
| Robust loss | Cauchy (it05) | Student-t ν = 3 search + Gaussian joint fit | WP4 |
| Error bars | MCMC DE posteriors (notebook 2026-09-30, superseded) | Laplace on the joint fit; MCMC only as an optional check | WP4 |
| Linker | QuEst 21.5 Å for every dye (it02–it09, repository `Alexa488`/`AF488`) | A48_C1R 20.4, C3B_C2R 19.74, T65_C2R 20.12 Å | WP1 presets, WP2 kernel |
| AV width / grid | quest `bdcf3e8` + owner 2026-10-11 "all use same defaults": IMP.bff W 4.5 Å, dg 0.9 | MalE analysis: W 0.5 Å, dye radius 3.5 Å, grid 0.5 Å | **ask the owner.** Proposal: MalE presets carry the notebook's values explicitly as measured analysis settings (`site_model.yaml`); the generic defaults stay IMP.bff's. Record the decision here. |
| D, τ₀ in presets | `D` 7, τ₀ 4.2 ns (Alexa488) | D 7.5 (grid options only, irrelevant at equilibrium), τ₀ 4.108 measured | WP1 presets |
| Static quenching | "dark only below TAU_MIN" (it08) | separate static channel `exp(−static·contacts(δ_static))`, fixed off for AF488/Cy3B (cell 29) | WP3/WP4 |

# What the prototype is

`~/dev/quest/prototype/male_quenching_analysis.ipynb` (60 cells, ~1460 code lines) is the
consolidated end state of 13 iteration scripts (`it01…it13_*.py`). It turns MalE lifetimes
(three dyes AF488/Cy3B/Atto655 × 9 sites × apo 1OMP/holo 1ANF × % D₂O) and free-dye/amino-acid
titrations into per-dye stickiness, quench scale, contact offset, rotamer weight, static
(dark) channel and shielding parameters. It does this with one Bayesian graph, solved by
multistart search, a joint least-squares fit and the Laplace approximation, with leave-one-out
outlier detection. The helper scripts are `dye_linker_length.py` (stretched linker,
superseded by notebook cell 21), `prediction_errors.py` (model error s from median χ²₁ = 0.455,
error propagation), `male_quenching_plots.py`, `interim_plot.py` (log scraper, not ported) and
`it11–it13` (water shielding path). Data: `~/dev/quest/data/*.xlsx` (owner's own MalE
measurements, 200 KB + 11 KB, **untracked** in the quest repo), `prototype/cache/` (54+ site
npz, ~240 KB each, 13 MB; site PDBs), `results/`, `output/`.

The plugin today (`chisurf/plugins/quenching_estimator`) is a **forward simulator only**. It does a
Brownian walk plus a photon race on one structure/site (`core/dye_diffusion.py`, `core/av.py`,
`core/simulation.py`, `core/scan.py`), with an emtk card, CLI, RPC and docs
([concept](../../docs/concepts/dye_quenching.md), [guide 80](../../docs/guides/80_quenching_estimator.md)).
It has no titration analysis, water analysis, exposure, rotamer ensemble, equilibrium ensemble
or inverse fit. A grep for `rotamer|exposure|stern|titration|d2o|laplace|leave.one|equilibri`
over the plugin's code returns nothing relevant.

# Gap matrix

"Where" follows the ChiSurf rules: geometry kernels go in IMP.bff, analysis I/O is
declared in YAML with mmfdb terms, GUIs use emtk + AutoForm, plots go through emtk implot,
optimisers come from `chisurf/core/math/numerics.py` (IMP.bff), and there is no pandas, scipy
or biopython at runtime.

| # | Capability (prototype source) | In plugin? | Where it must live |
|---|---|---|---|
| 1 | Load lifetimes + titrations from xlsx; fix site number from the file name `MalE(\d+)(dye)` (cell 8; 6 AF488 rows 95→186) | no | WP0: CSV fixtures `examples/male/` (xlsx is not a runtime format: openpyxl is only a `scrape` extra), reader `core/inference/measurements.py` |
| 2 | Per-day Stern–Volmer line fits, slope SE (cell 10) | no | WP1 `core/inference/titration.py` |
| 3 | Hierarchical day-to-day error (abs + rel, shared by all titrations) solved in closed form on a 60×60 log grid; mixture posterior of K_SV (cell 10) | no | WP1 `titration.py` (numpy; grid evidence, no sampler) |
| 4 | kq = K_SV/τ₀ table, positive part only (cells 10, 19) | no | WP1 |
| 5 | Water quenching kq_w per site from 1/τ vs H₂O fraction (cell 13) | no | WP1 `core/inference/lifetime_errors.py` |
| 6 | Series fits, pooled/LOO/MAD scatter, per-site σ mixed with `PRIOR_POINTS = 2`, extrapolation to 0 %/100 % D₂O, LOO coverage check (cells 15, 17) | no | WP1 `lifetime_errors.py` |
| 7 | Free-dye τ₀ (H₂O/D₂O), kq_w,free = 1/τ₀(H₂O) − 1/τ₀(D₂O) (cell 17) | no | WP1 |
| 8 | Per-dye contact kQ = kQ_textbook × kq(dye)/kq(AF488); Pro uses Trp ratio; numeric error propagation (cell 19) | partial: plugin has textbook kQ via `IMP.bff.amino_acid_quenching_defaults` (`core/dye_diffusion.py:170`) | WP1 `core/inference/kq_scaling.py`; per-dye presets (AF488/Cy3B/Atto655 are **missing** from `settings/dye_repository.json`) WP1 |
| 9 | Stretched linker length Cβ→chromophore centre (cell 21; `dye_linker_length.py`) | no (repository uses 21.5 Å) | WP2 IMP.bff (`MolecularGraph` rings + path) → `IMP.bff.stretched_linker_length`; values 20.4/19.74/20.12 Å into WP1's presets |
| 10 | Site-truncated structure (no water/H, labelled residue cut to backbone+Cβ), AV via `get_av_from_pdb` (cell 23) | partial: AV via `IMP.bff.get_av` (`core/av.py:90`), water stripping exists (`test_water_stripping.py`) | WP3 `core/inference/site_table.py` using the plugin's `core/structure` reader (IMP.bff `parse_structure_table`), **not** Bio.PDB |
| 11 | Equilibrium ("direct") ensemble p ∝ 1/s instead of the walk; validation vs walk (cells 22–23) | no (walk only) | WP3 `core/inference/site_model.py`; check against IMP.bff `DynamicAccessibleVolume.update_occupancy` (`include/spectroscopy/PhotophysicsQuenchingModel.h:165`) |
| 12 | Per-voxel residue-type neighbour counts n_t(x) within `SLOW_RADIUS` 8.5 Å (cell 25, via slow-factor map trick s = 0.5^n) | no | WP2 IMP.bff kernel `residue_type_neighbour_counts(av, atoms, radius, types)`; WP3 calls it |
| 13 | Side-chain rotamer quencher centres: Dunbrack (FASPR bbdep) at the residue's φ/ψ, χ1/χ2 rotation, clash filter 2.8 Å, renormalised probabilities (cell 25) | no. IMP.bff has `read_protein_sidechain_dunbrack_rotamers` (`include/structure/ProteinSidechainRotamerLibrary.h:104`) and `dihedral_deg`/ZMatrix, but no ensemble builder | WP2 IMP.bff `quencher_rotamer_ensemble(...)` (φ/ψ from the backbone, χ placement, clash, centre of `quench_atoms`) |
| 14 | Contact maps per quencher × δ ∈ {−4…+5 Å} × {crystal, rotamer} (cell 25, `ResidueQuenchingMap` of point quenchers) | no | WP3 (uses existing `QuenchedDonorDecay.update_grids`/`get_quenching_rate_map`) |
| 15 | Water exposure e(x): Shrake–Rupley, 64 golden-spiral points on R_dye + 1.4 Å, covered if within r_vdW + 1.4 Å (C 1.70, N 1.55, O 1.52, S 1.80) (cells 25–26; `it12`) | no. IMP.bff `solvent_accessible_surface_area*` is per atom, not per arbitrary probe centre | WP2 IMP.bff `probe_solvent_exposure(centres, xyz, radii, probe_radius, water_radius, n_points)` in `SolventAccessibleSurface.h` |
| 16 | Voxel-centre convention x0 + (ijk − (ng−1)//2 + 0.5)·dg (cell 25; it04 check) | implicit in `core/av.py:443 grid_center_index` | WP2 expose `get_voxel_centres()` on the AV / QuenchedDonorDecay so callers stop re-deriving it |
| 17 | Site-table cache (content key of geometry + settings), npz (cell 25) | no | WP3, cache under the plugin's settings cache (`core/fio/staging` / demo_cache pattern), key includes the IMP.bff version |
| 18 | `Site` model: unique-feature compression (~15×), per-group stickiness ln s, quench scale, δ interpolation, λ crystal/rotamer mix, TAU_MIN⁴ visibility, static dark channel, `dtau_shield × (1−e)`, water × e; returns (τX, dark fraction, visible exposure) (cell 29) | no | WP3 `site_model.py` (numpy) |
| 19 | Parameter set, bounds, per-dye `FIXED`, `BRIGHTENS`, ν = 3, model-error floor 0.05 ns, outlier 3σ, MAX_VARIANCE 0.25, ridge ln 10 (cell 29) | no | WP4 `settings/analysis/fit_parameters.yaml` (declarative, not hardcoded) |
| 20 | Robust Student-t multistart search (64 starts, L-BFGS-B), model error by median χ²₁ root, outlier mask (cell 29; `prediction_errors.py`) | no | WP4 `core/inference/graph_fit.py` with `numerics.minimize`/`numerics.root_scalar`; parallelism through the plugin's job runner (`core/tasks.py`), not `multiprocessing` fork |
| 21 | Graph: blocks + titration slopes K as parameters (K prior N(K_mean, K_sd)), u∈[0,1] scaling, joint `least_squares` trf (cell 29) | no | WP4 `graph_fit.py` with `numerics.least_squares` |
| 22 | Laplace covariance (eigen-clipped inverse of JᵀJ), prediction SD by error propagation, notes (not determined / edge / other regions) (cell 29) | no | WP4; may use IMP.bff `bayesian_delta_variance`/Laplace helpers (`include/bayesian/BayesianLaplace.h`, `BayesianDeltaMethod.h`) |
| 23 | Leave-one-site-out by one Newton step on the curvature (cell 29) | no | WP4 |
| 24 | `propagate()` of any derived quantity; Laplace "profile" of the quench scale (cell 29) | no | WP4 (+ optional true profile likelihood, see Where-to-pick-up 3) |
| 25 | InferenceFactorGraph description (components, separators, treewidth) (cell 33) | no; chisurf has `core/fitting/factorgraph.py` | WP4 via `IMP.bff.InferenceFactorGraph` (already used by the prototype) |
| 26 | Optional MCMC check vs Laplace (`LocalPosterior` GraphNode + `MCMCSampler("stretch")`) (cell 29/40) | no | WP4 through `chisurf/core/fitting/sampler_bff.py`/`ensemble.py` (in-tree samplers), marked slow |
| 27 | Stage A (AF488, Cy3B H₂O), Stage B (Atto655 D₂O alone), naive H₂O transfer test, Stage C (joint D₂O+H₂O, water = kq_w,free·e, no new parameter), measured vs model water access per site, time-weighted visible exposure (cells 33–55; it11–it13) | no | WP4 `core/inference/stages.py` (stage list declared in `settings/analysis/stages.yaml`) |
| 28 | Summary across dyes, plain-language explanation (`explain`) (cells 57–59) | no | WP4 `core/inference/report.py` (text from numbers; GUI shows it) |
| 29 | Figures: Stern–Volmer panels + hyper-posterior contour, water bars, exposure sketch + histograms, parity plots with error bars/outliers, parameter forest, LOO bars, scale profile, graph sketch, K before/after, water-access parity, summary (`male_quenching_plots.py`, cells 10–58) | no | WP6 emtk implot in the analysis card; no matplotlib |
| 30 | Headless entry, settings cell, QUICK mode, output folder with timestamped CSV/PNG | no | WP5 API/RPC/CLI `quest.analysis.*`, `csc quest analyse`; QUICK becomes a declared preset |

# Work packages

The file claims are disjoint. "Edits" means hunks in an existing file. The owner of a file is the
only package that touches it. Order: **WP0 → (WP1 ∥ WP2 ∥ WP7-theory ∥ WP7b) → WP3 → (WP4 ∥ WP9) → (WP5 ∥ WP6) → WP7-guide → WP8.**
WP1 and WP2 have no dependency on each other. WP5 and WP6 depend on the WP4 *interface*
(function signatures fixed in WP4's first commit), not on its numbers.

Paths are relative to `chisurf/plugins/quenching_estimator/` unless absolute.

## WP0: data, fixtures, golden numbers (small; lands first)

- **Goal:** the MalE data as shipped CSV, the two PDB structures, one prototype site table,
  and a full-precision golden file produced by executing the prototype.
- **Create:** `examples/male/tcspc_fit_results.csv` (sheet "TCSPC fit results", 248 rows; keep
  Date, D2O %, Variant, Dye, Condition, tauX, Data path name), `examples/male/amino_acid_quenching_flt.csv`
  (sheet "amino acid quenching FLT": Dye, Amino acid, Date, Concentration mM, tauX0, tauX),
  `examples/male/titration_summary.csv` ("amino acids dynamic quenching.xlsx", 17 rows),
  `examples/male/provenance.json` (owner's data, source workbook names, sha256, 2026-09-29),
  `examples/male/1OMP.cif`, `examples/male/1ANF.cif` (copy from `~/dev/imp.bff/examples/structure/MBP/`, PDB data CC0, ~330 KB each),
  `core/inference/__init__.py`, `core/inference/measurements.py` (csv → numpy record arrays,
  site correction from file name), `test/data/male_site_1omp72_L20.12.npz` (copy of the matching
  prototype cache file; compute its key with cell 25's `site_table` key `["nb-v1", "APO", 72, 20.12, 0.5, 8.5, RADIUS_OFFSETS, 2.8, QUENCHERS, RESIDUES]`),
  `test/baselines/male_prototype.json` + `test/baselines/make_male_prototype.py` (runs the notebook's
  cells 2–29 code from `~/dev/quest/prototype` with `QUICK=False`, `RUN_VALIDATION=True`; records
  K_POSTERIOR, hyper quantiles, water table, scatter, per-site `data` table (64 rows), coverage, TAU0,
  KQW_FREE, KQ_TABLE ± SD, stretched AF488 linker, direct-vs-walk, and `Site.lifetime` for every
  row at each stage's printed parameter set, plus the printed Stage estimates below),
  `test/test_male_measurements.py` (248/17 rows, the 6 corrected rows).
- **Accept:** reader gives 17 titration results and 248 lifetimes; 6 corrections 95→186 (AF488 APO 0/90/54 %, HOLO 0/87.84/52.65 %).
- **Docs:** none (data only). **Deps:** none. Python is run in the `arm64` env; openpyxl only in the one-off converter (not shipped).

## WP1: measurement statistics (titrations, water, lifetime errors, kQ per dye)

- **Goal:** chapters 1–3a as Qt-free numpy code with declared outputs.
- **Create:** `core/inference/titration.py`, `core/inference/lifetime_errors.py`,
  `core/inference/kq_scaling.py`, `settings/analysis/measurement_columns.yaml` (columns of the
  K posterior table, water table, measured-lifetime table, kQ table; each with `term:`),
  `test/test_inference_titration.py`, `test/test_inference_lifetime_errors.py`, `test/test_inference_kq_scaling.py`.
- **Edit:** `settings/dye_repository.json` (add `AF488_C1R_MalE`, `Cy3B_C2R`, `Atto655_C2R` presets:
  τ₀ 4.108/2.391/1.846 ns (Atto655 D₂O 3.69), linker 20.4/19.74/20.12 Å, width 0.5, radius 3.5, kQ row of the table below).
  **mmfdb (`~/dev/mmfdb`, `mmfdb_flr_ext.dic`): WP1 owns every new term for the whole migration.** Add them up front so
  WP3/WP4 never edit the dictionary: Stern–Volmer constant, bimolecular quenching constant, day-to-day error abs/rel,
  water quenching rate, measurement relative scatter, solvent exposure (probe), dark fraction, slow factor per group,
  quench scale, contact offset, rotamer weight, static strength, static offset, shield lifetime increment, model error,
  LOO z, water access, predicted lifetime + SD. Reuse `_flr_fit_parameter.kQ` (line 1837). Guard: `test/core/test_analysis_feature_terms.py`.
  Commit in mmfdb locally.
- **Port:** cells 8, 10, 13, 15, 17, 19.
- **Accept (from the stored notebook):**
  - Day-to-day error (posterior median, 68 %): absolute 0.01 (0.01–0.03) M⁻¹, relative 2 % (1–3 %); mass on the grid edge < 0.05.
  - K_SV posterior (M⁻¹, ± posterior), kq (10⁹ M⁻¹s⁻¹): AF488 Trp 14.44 ± 0.22 / 3.51 ± 0.05; Tyr 8.57 ± 0.66 / 2.08;
    Met 6.49 ± 0.12 / 1.59; His 6.24 ± 0.11 / 1.52; NC-Tyr 11.82 ± 1.02 / 2.87; Phe −0.06 ± 0.04.
    Atto655 Trp 5.61 ± 0.14 / 3.04; Tyr 10.40 ± 0.42 / 5.62; Met −0.09; His −0.47; Phe −1.28.
    Cy3B Trp 11.10 ± 0.29 / 4.64; Tyr −0.12 ± 0.72; Met 0.06 ± 0.04; His −0.04 ± 0.02; NC-Tyr −1.37; Phe −0.10.
    Full precision: `output/20261001-142438_chapter1_stern_volmer_posterior.csv` (e.g. AF488 His K = 6.23562603290228).
  - kq_w on MalE (ns⁻¹) median/min/max: AF488 0.012/−0.040/0.077; Atto655 0.158/0.028/0.280; Cy3B 0.024/0.011/0.029.
  - Single-point scatter (% of τ) regression/LOO/typical: AF488 4.78/4.74/0.91; Cy3B 1.16/1.04/0.75; Atto655 2.87/2.89/1.72.
  - LOO 1σ coverage: AF488 57 %, Atto655 69 %, Cy3B 61 %.
  - τ₀: AF488 4.108, Cy3B 2.391, Atto655 H₂O 1.846, D₂O 3.69 ns; kq_w,free = 0.271 ns⁻¹.
  - Median site σ (ns): AF488 H₂O 0.026, Atto655 D₂O 0.039, Atto655 H₂O 0.022, Cy3B 0.018. 64 site rows,
    byte-compare with `output/20261001-142438_measured_lifetimes_with_errors.csv` (e.g. AF488 H₂O APO 72: 3.0882338779942993 ± 0.023607500932585287).
  - kQ at contact (ns⁻¹; TRP TYR MET HIS PRO): AF488 3.500 2.000 1.670 1.000 2.000 (reference, ±0);
    Cy3B 4.625 ± 0.139, 0.000 ± 0.240, 0.024 ± 0.017, 0.000, 2.643 ± 0.079;
    Atto655 3.030 ± 0.088, 5.397 ± 0.445, 0.000, 0.000, 1.732 ± 0.050.
  - Measured water access per site (data only; (1/τH − 1/τD)/kq_w,free): 72A 0.498, 92A 0.102, 95A 0.644, 186A 0.830,
    211A 0.593, 219A 0.474, 233A 0.549, 309A 0.709, 322A 1.034, 72H 0.493, 92H 0.578, 95H 0.536, 186H 0.799,
    211H 0.542, 219H 0.487, 233H 0.589, 309H 0.647, 322H 0.974.
- **GUI:** none. **Docs:** feeds WP7. **Deps:** WP0.

## WP2: IMP.bff kernels (in `~/dev/imp.bff`, committed there)

- **Goal:** the C++-worthy geometry the site tables need, each with a Python-visible SWIG name and an IMP.bff test.
- **Create/Edit (imp.bff only):** `include/structure/SolventAccessibleSurface.h` + `src/...`:
  `probe_solvent_exposure(centres, atom_xyz, atom_radii, probe_radius=3.5, water_radius=1.4, n_points=64)`, which returns the
  uncovered fraction per centre (cell-list neighbour search, golden-spiral `sphere_points`).
  `include/structure/ProteinSidechainRotamerLibrary.h` + src: `quencher_rotamer_ensemble(structure, chain, residue,
  library_path, quench_atoms, clash=2.8)`, which returns centres + renormalised probabilities. It computes φ/ψ from the backbone
  (default −60/−45 at chain ends), places χ1/χ2 by rotation about CA–CB / CB–CG, drops side chains closer than `clash` to
  any other heavy atom, and falls back to the crystal centre when no rotamer survives.
  Probe/spectroscopy: `residue_type_neighbour_counts(...)` (per voxel, per residue name, count within radius) and
  `get_voxel_centres()` on `QuenchedDonorDecay`/AV. Probe/structure: `stretched_linker_length(library_name, linker_residue, dye_residue)`
  (cell 21 algorithm: bond graph, all-trans × sin(109.5°/2) on flexible bonds, rings through space, + entry→chromophore centroid).
  Tests in `test/` comparing against the prototype's Python on 1OMP site 72.
- **Port:** cells 21, 25 (`dihedral`, `rotate`, `set_chi`, `quencher_positions`, `water_exposure`, neighbour trick, voxel centres); `dye_linker_length.py` for cross-check.
- **Accept:** exposure array equals `test/data/male_site_1omp72_L20.12.npz["exposure"]` within 1e-6 (float32). Neighbour counts
  equal `["neighbours"]` exactly (int8). AF488 A48_C1R stretched length 20.4 Å (1 decimal). Rotamer centres reproduce the
  prototype's contacts (`["contacts"][..., 1]`) within float16 eps once WP3 builds them. Speed: one site table in seconds, not
  ~7 s of Python.
- **Then:** the coordinator bumps the imp.bff pin. Owner runs a non-editable arm64 env: reinstall there on the pin bump.
- **Deps:** none (reads WP0's npz only for its test; it can copy the file itself).

## WP3: site tables and the site model (plugin)

- **Goal:** turn (structure, site, linker) into the per-voxel feature table, cached, and predict τX for a parameter set.
- **Create:** `core/inference/site_table.py` (build with WP2 kernels + `QuenchedDonorDecay` contact maps per quencher ×
  δ × source; content-addressed cache), `core/inference/site_model.py` (`Site`: unique-row compression, `weights`, `seen`,
  `lifetime` → τX, dark fraction, visible exposure; `predict`), `settings/analysis/site_model.yaml` (QUENCHERS, GROUPS,
  SLOW_RADIUS 8.5, RADIUS_OFFSETS −4…+5, CLASH 2.8, TAU_MIN 0.10, GRID 0.5, LINKER_WIDTH 0.5, DYE_RADIUS 3.5,
  GRID_OPTIONS of cell 23), `test/test_inference_site_table.py`, `test/test_inference_site_model.py`.
- **Port:** cells 22–25, the `Site` class and `predict` of cell 29, cell 53's time-weighted exposure.
- **Accept:** a rebuilt `1OMP/72/20.12` table equals the shipped npz (neighbours exact, contacts within float16 eps,
  exposure 1e-6). Direct method at APO 233, slow 0.3, L 21.5, τ₀ 4.108: **2.59 ns**, and the walk (3 seeds × 16 traj × 16 µs)
  2.31 ± 0.03 ns, |Δ| < 0.35 (mark the walk test slow). `Site.lifetime` reproduces every golden row of `male_prototype.json`
  to 1e-9 at the stage parameter sets. Exposure histograms: Atto655 apo sites 72/186 average e over reachable positions
  as recorded by WP0 (cell 27 legend).
- **Deps:** WP0, WP2 (until WP2's pin lands, develop against an editable imp.bff build. No silent Python fallback: owner rule, a fallback must warn).

## WP4: the Bayesian graph fit and the stages

- **Goal:** chapter 6 and Stages A/B/C as an engine with declared parameters and outputs.
- **Create:** `core/inference/graph_fit.py` (Block, Graph, robust search, model error, outlier mask, joint fit, Laplace,
  `clipped_inverse`, LOO, `propagate`, scale profile, factor-graph description), `core/inference/stages.py` (Stage A/B/C,
  naive H₂O test, water access, time-weighted exposure, summary), `core/inference/report.py` (the `explain` text),
  `settings/analysis/fit_parameters.yaml` (NAMES, LOWER/UPPER, FIXED per dye, BRIGHTENS, NU 3, MODEL_ERROR_FLOOR 0.05,
  OUTLIER_LIMIT 3, MAX_VARIANCE 0.25, RIDGE ln 10, N_STARTS 64, QUICK preset 8 starts/60 iters),
  `settings/analysis/stages.yaml`, `settings/analysis/result_columns.yaml` (prediction + estimate tables, `term:` from WP1),
  `test/test_inference_graph_fit.py` (fast: Cy3B block on cached tables, QUICK), `test/test_male_reproduction.py` (`slow`: full run).
- **Port:** cells 29, 33, 35–55, 58; `prediction_errors.py` (cross-check of the model-error criterion).
- **Rules:** optimisers from `chisurf/core/math/numerics.py` (`minimize` L-BFGS-B, `least_squares` trf, `root_scalar`). Run the
  multistart searches as jobs in `core/tasks.py`'s runner (thread/process pool usable on macOS; the prototype only parallelised on
  Linux fork). The MCMC cross-check goes through `chisurf/core/fitting/sampler_bff.py`. No pandas: record arrays + the YAML columns.
- **Accept (stored notebook, the 64-start run).** The optimiser differs from scipy's, so compare each best fit against the
  notebook's 68 % interval. Outlier sets and model errors must match exactly. LOO rankings must have the same top site.
  - Graph: 3 blocks, 41 parameters, 12 titration slopes; factor graph 48 variables, 20 likelihoods, 3 priors, treewidth 18,
    2 components (AF488 alone, 0 slopes; Atto655 + Cy3B with 17 slopes).
  - Search: model error AF488 0.050 (4 outlier lifetimes), Cy3B 0.050 (0), Atto655 joint 0.108 (3); Stage B alone 0.065 (2).
  - **AF488 H₂O (Stage A):** s_common 0.352 (0.125–0.992), s_aromatic 1.000 (0.676–1, edge), s_hydrophobic 0.495 (0.411–0.596),
    s_basic 0.129 (0.109–0.153), s_acidic 0.397 (0.358–0.439), s_polar 0.214 (0.195–0.234), scale 6.157 (4.630–8.189),
    delta −0.417 (−0.584 to −0.251), lam 0.022 (0–0.119); static/delta_static fixed. rms 0.62, median |dev| 0.047, median pred SD 0.047 ns;
    outliers 92, 219, 233; LOO worst |z|: 233 15.3, 219 4.1, 92 3.5, 95 2.8, 186 1.6, 322 1.2, 72 1.1, 211 0.9, 309 0.6;
    mean dark fraction 13 %; scale profile 6.1× (4.6–8.1, factor 1.8).
  - **Cy3B H₂O:** s_common 0.207 (0.069–0.619), s_aromatic 0.943 (0.689–1), s_hydrophobic 0.291 (0.223–0.379), s_basic 0.116
    (0.072–0.186), s_acidic 0.146 (0.112–0.189), s_polar 0.083 (0.028–0.243), scale 1.133 (0.192–6.685), delta 1.010 (0.997–1.023),
    dtau_shield 1.371 (0.959–1.784); lam = 1, static off. rms 0.02, median |dev| 0.010 ns; no outliers; LOO 92 1.3, 95 1.1, 233 1.1, 186 0.3, 219 0.1.
  - **Atto655 D₂O (Stage B, own graph: 1 block, 19 parameters, 8 slopes):** s_common 0.0213 (0.0051–0.0892), s_aromatic 0.0011
    (0.0010–0.0044), s_hydrophobic 0.172 (0.088–0.337), s_basic 0.0029 (0.0010–0.0227), s_acidic 0.443 (0.269–0.730), s_polar
    0.0186 (0.0088–0.0393), scale 0.1106 (0.0798–0.1535), delta −2.824 (−3.0 to −2.335), static 0.0010 (0.0010–0.1000), delta_static
    −1.00 (not determined), dtau_shield 0.061 (0–0.126), model error 0.0653. rms 0.63, median |dev| 0.061 ns; outliers 211, 219, 322;
    LOO 322 31.6, 219 3.9, 211 3.1, 72 2.9, 92 2.1, 233 1.9, 309 1.1, 186 0.9, 95 0.5.
  - **Naive H₂O transfer test (expected to fail):** median |dev| 0.48 ns; 16 of 18 sites measure above the free-dye τ₀(H₂O) 1.85 ns.
  - **Atto655 D₂O + H₂O (Stage C, 36 lifetimes):** s_common 0.0503 (0.0164–0.1541), s_aromatic 0.0108 (0.0059–0.0200),
    s_hydrophobic 0.2125 (0.1523–0.2964), s_basic 0.0033 (0.0010–0.0129), s_acidic 0.2549 (0.1649–0.3939), s_polar 0.1663
    (0.0954–0.2899), scale 0.1119 (0.0799–0.1569), delta −2.631 (−3.0 to −2.203), static 0.0011 (0.0010–0.1084), delta_static −1.00
    (not determined), dtau_shield 0.0214 (0–0.1114), model error 0.1079. rms 0.52, median |dev| 0.094, median pred SD 0.043 ns;
    outlier 322; LOO 322 20.0, 219 2.6, 233 2.2, 211 2.2, 92 2.1, 186 1.9, 72 1.9, 95 1.4, 309 1.4.
  - Titration slopes after the graph (K_graph, 68 %): AF488 Trp 14.456 (14.238–14.673), Tyr 8.381 (7.724–9.038), Met 6.487, His 6.236;
    Cy3B Trp 11.102, Tyr −0.122, Met 0.054, His −0.039; Atto655 Trp 5.597 (5.457–5.736), Tyr 10.460 (10.038–10.883), Met −0.085, His −0.475.
  - Summary: AF488 scale 6.2 (4.6–8.2), stickiest basic, outliers 92/219/233; Cy3B 1.1 (0.19–6.7), polar, none; Atto655 0.11 (0.08–0.16), basic, 322.
  - Not recorded in the stored output: the water-access r (all/without 322) in cell 51's title. WP0 must regenerate it, or WP4 reports it fresh.
  - Runtime reference: 64 searches AF488 405 s, Cy3B 148 s, Atto655 737 s on cordeshub (44 cores); graph 23.6 min. The fast test must stay under 60 s.
- **Deps:** WP1, WP3. The interface (Stage/Block result dataclasses) lands in WP4's first commit so WP5/WP6 can start.

## WP5: headless surfaces (API, RPC, CLI, jobs)

- **Goal:** the analysis from Python, ZMQ RPC and `csc quest`, as background jobs with stored runs.
- **Edit:** `api/local.py`, `api/contract.py`, `api/client.py`, `rpc/services.py`, `rpc/contract.py`, `manifest.json`
  (`quest.analysis.template`, `.run`, `.result`, `.site_table`; each with `description` for the AutoForm RPC form),
  `cli/cli.py` (`csc quest analyse --data examples/male --stage all --quick`), `core/tasks.py`, `core/runs.py` (an analysis run kind).
- **Create:** `test/test_inference_api.py`, `test/test_inference_cli.py`.
- **Accept:** `csc quest analyse --quick` on the shipped data writes the declared tables. The RPC round-trip returns the same
  estimates as the in-process call, and a job can be cancelled.
- **Deps:** the WP4 interface.

## WP6: GUI (emtk + AutoForm), demo, tour

- **Goal:** an *Analysis* surface in the QuEst window: load the MalE demo or the user's own CSVs, run the stages, read the tables and plots.
- **Create:** `gui/analysis.view.json` (settings + `data_table` sections for the K posterior, measured lifetimes, kQ, estimates and predictions;
  `source` must be callable methods, never properties), `gui/analysis_card.py` (implot drawing only for the plots: Stern–Volmer panels +
  hyper contour, water bars, exposure histograms, parity with x-error bars and outlier rings, parameter forest, LOO bars with the 3σ line,
  scale profile B vs C, K before/after, water-access parity, summary), `gui/analysis_help.md` (`?` modal, live links), `gui/analysis_guide.json`
  (steps `await` the user's presses; step 1 targets `load_example`), `test/test_emtk_analysis_card.py`.
- **Edit:** `gui/app.py` (add the tab), `demo.py` (MalE demo: `make_demo` also stages `examples/male` + QUICK preset; the cache stamp `DEMO` gains
  a key), `gui/help.md` (link to the analysis help), `test/test_demo_and_guide.py`.
- **Screenshots (required, read by the implementer):** `QT_QPA_PLATFORM=offscreen`, arm64, real MalE demo loaded, QUICK run finished,
  every tab and every plot visited, at default and narrow sizes. Check for clipped labels, log axes on scale/stickiness, outlier rings,
  and that the Atto655 Stage C parity shows both solvents. The new surface has no legacy Qt baseline. Record that in the commit.
- **Deps:** the WP4 interface, WP5 (the GUI calls the API facade only).

## WP7: documentation

- **Theory (can start after WP1):** `docs/concepts/quenching_inference.md`. It covers: Stern–Volmer and kq; the hierarchical day-to-day model
  and its closed-form evidence; kQ scaling relative to AF488; the equilibrium ensemble p ∝ ∏ s_t^{−n_t}; the TAU_MIN visibility and static
  channel; shielding τ₀ + Δτ(1−e); water quenching kq_w,free·e; Shrake–Rupley exposure; the Laplace approximation with clipped eigenvalues;
  LOO by a Newton step; the model-error criterion median χ²₁ = 0.455. Cite Peulen 2017 [10.1021/acs.jpcb.7b03441](https://doi.org/10.1021/acs.jpcb.7b03441),
  Shrake & Rupley 1973, Dunbrack (FASPR bbdep library). Register it in `docs/concepts/index.md` and cross-link `docs/concepts/dye_quenching.md`.
- **Application (after WP6):** `docs/guides/111_quenching_analysis.md` (check the next free number). It covers the tool, settings, the headless CLI,
  the Python API, a real screenshot, and the MalE walk-through with the numbers above. Register it in `docs/guides/index.md` and link it from
  `80_quenching_estimator.md`. Run `pixi run -e docs docs-plugins`.
- **OKF:** this concept's status and resume list, plus one `okf/log.md` bullet per landing (`safe_edit log`).
- **Deps:** WP1 (theory), WP6 (guide screenshots).

## WP9: the forward simulator follows the notebook

- **Goal:** QuEst's own simulate path must not give the non-equilibrated sticky-regime τX, and its dye presets must
  carry the MalE-measured values.
- **Edit:** `core/simulation.py`, `core/dye_diffusion.py` (an `ensemble: "equilibrium" | "walk" | "pde"` choice, all three kept — owner 2026-10-20: the walk is the
  straightforward FRET path and stays; the PDE (grid diffusion solver with stickiness potential + quenching sink) gives the
  dynamics without the walk's equilibration defect; equilibrium is the static limit and the default for τX/QY in the inverse fit;
  the walk must be started from p(x) and checked against the PDE), `core/av.py`
  (delete `asa`/`spherePoints` once WP2's kernel is pinned), `settings/parameter_catalog.json`, `gui/generate_view_spec.py`
  + the regenerated `gui/quest.view.json` (en only; de/fr deferred), `test/test_equilibrium_ensemble.py` (new),
  `test/baselines/{generate.py,imp_bff.json}` (re-pin with a log line accounting for every moved number).
- **Accept:** MalE APO 95 AF488 reference kQ: equilibrium τX decreases monotonically from slow 1 → 0.3 → 0.1; the PDE's
  stationary distribution equals the equilibrium ensemble (test); the PDE decay and a long p(x)-started walk agree within
  their statistical error at slow 1 and 0.3, and the walk's deviation at slow 0.1 is reported, not hidden. The APO 233,
  slow 0.3 value matches WP3's 2.59 ns.
- **Deps:** WP3 (the site model's equilibrium code is reused, not duplicated). It does not touch WP5/WP6 files.

## WP7b: quest tutorials as examples

- **Create:** `examples/01_donor_quenching.py`, `examples/02_fret_pair.py`, `examples/03_labeling_scan.py`,
  `examples/04_et_distance_distribution.py` (from notebooks 01–03 and quest `examples/`), `test/test_examples.py`;
  guide sections in `docs/guides/80_quenching_estimator.md`. Linear beginner scripts, no `__main__` boilerplate beyond
  quest's style. Port notebook 04 (Haas–Steinberg) only if IMP.bff's diffusion solver covers it.
- **Deps:** none beyond the current plugin. It can run in parallel with everything.

## WP8: mark the prototype as migrated (last)

- **Goal:** anyone opening `~/dev/quest/prototype` sees what moved where, without the prototype code changing.
- **Create:** `~/dev/quest/prototype/MIGRATED.md` (table: prototype item → chisurf path/function → chisurf commit (+ imp.bff/mmfdb commit); a second table covers the non-prototype quest items of "The rest of the quest repo" above, with their disposition;
  one row per gap-matrix line; also the items deliberately **not** migrated: `interim_plot.py` (log scraper),
  `it01–it06` walk objective, `it11` residue-count shielding, the matplotlib plots, Bio.PDB/pandas/openpyxl, the Linux fork pool).
- **Edit (headers and notes only):**
  - Every `it*.py`, `dye_linker_length.py`, `prediction_errors.py`, `male_quenching_plots.py` and `interim_plot.py` gets a comment block
    *above* the module docstring: `# CHISURF-MIGRATED: <date>`, `# CHISURF-TAKEN: <what → path>`, `# CHISURF-SKIPPED: <what, why>`,
    `# CHISURF-RECORD: okf/plugins/quest-prototype-migration.md`. Same spirit as the `junk/` CHISURF-REVIEWED rule.
  - The notebook gets one new markdown cell at index 0 (the overview pointing to MIGRATED.md) and one new markdown cell at the
    top of each chapter (before cells 9, 12, 18, 22, 24, 28, 32, 34, 44, 50, 57).
  - **Proof of no code change:** a check script loads the notebook before and after and asserts that the list of code-cell sources
    (and outputs) is identical. For the .py files, `git diff` shows insertions only.
- **Commit:** `~/dev/quest` is a git repo on branch `dev` (39 commits ahead of `origin/dev`; tracked in `prototype/` are the 18 `.py`/`.ipynb`
  files; `cache/`, `results/`, `output/`, the PNGs and `../data/` are untracked). Make one focused local commit there with only those files
  (temp `GIT_INDEX_FILE` from HEAD if the tree has other edits), no trailers, never push (batch pushes once the scope is settled).
  Leave `data/` untracked: the shipped copy now lives in chisurf `examples/male/`.
- **Deps:** all others landed (needs their commit hashes).

# File-claim summary

| WP | chisurf files (plugin-relative unless absolute) | other repos |
|---|---|---|
| 0 | `examples/male/*`, `core/inference/{__init__,measurements}.py`, `test/data/male_site_1omp72_L20.12.npz`, `test/baselines/{make_male_prototype.py,male_prototype.json}`, `test/test_male_measurements.py` | read-only quest |
| 1 | `core/inference/{titration,lifetime_errors,kq_scaling}.py`, `settings/analysis/measurement_columns.yaml`, `settings/dye_repository.json`, `test/test_inference_{titration,lifetime_errors,kq_scaling}.py` | mmfdb `mmfdb_flr_ext.dic` (all terms) |
| 2 | none | imp.bff `include/structure/{SolventAccessibleSurface,ProteinSidechainRotamerLibrary}.h`, probe/spectroscopy headers + src + tests |
| 3 | `core/inference/{site_table,site_model}.py`, `settings/analysis/site_model.yaml`, `test/test_inference_site_{table,model}.py` | none |
| 4 | `core/inference/{graph_fit,stages,report}.py`, `settings/analysis/{fit_parameters,stages,result_columns}.yaml`, `test/test_inference_graph_fit.py`, `test/test_male_reproduction.py` | none |
| 5 | `api/{local,contract,client}.py`, `rpc/{services,contract}.py`, `manifest.json`, `cli/cli.py`, `core/{tasks,runs}.py`, `test/test_inference_{api,cli}.py` | none |
| 6 | `gui/{analysis.view.json,analysis_card.py,analysis_help.md,analysis_guide.json,app.py,help.md}`, `demo.py`, `test/test_emtk_analysis_card.py`, `test/test_demo_and_guide.py` | none |
| 7 | `docs/concepts/{quenching_inference,dye_quenching,index}.md`, `docs/guides/{111_quenching_analysis,80_quenching_estimator,index}.md`, `docs/plugins*` (generated), this concept | none |
| 8 | none | quest `prototype/*.py`, `prototype/male_quenching_analysis.ipynb`, `prototype/MIGRATED.md` |
| 9 | `core/{simulation,dye_diffusion,av}.py`, `settings/parameter_catalog.json`, `gui/generate_view_spec.py`, `gui/quest.view.json`, `test/test_equilibrium_ensemble.py`, `test/baselines/{generate.py,imp_bff.json}` | none |
| 7b | `examples/0[1-4]_*.py`, `test/test_examples.py` (guide 80 sections go through WP7) | none |

`okf/log.md` is shared and is only edited through `python -m build_tools.dev_utils.safe_edit log`.
