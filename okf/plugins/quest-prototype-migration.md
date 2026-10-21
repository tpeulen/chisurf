---
type: Migration Plan
title: QuEst prototype migration (MalE quenching analysis)
description: Gap matrix between the MalE quenching-analysis prototype (~/dev/quest/prototype) and the quenching_estimator plugin, the split into parallel work packages with file claims, and the reference numbers each port must reproduce.
resource: chisurf/plugins/quenching_estimator/
tags: [plugins, modelling, quenching, quest, migration, prd-154]
timestamp: '2026-10-20T00:00:00Z'
---

# Where to pick this up

Every work package has landed (record below); WP4's science is the open front.

- Open: **WP4c distance-continuous kernel (default `rate_model: kernel`): the full refit is in and pinned
  (2026-10-21, chisurf `e95b1599c`); two of four blocks now have interior optima, the κ–ℓ trade-off remains.**
  Full (κ, ℓ, 68 % Laplace, 26 146 s / 7 workers): AF488 κ 0.019 (0.016–0.023) — a proper interior optimum, a
  factor 326 off the stored 6.2 — with the κ profile interior too (0.0173–0.0180), and the ℓ profile minimal at
  ℓ 0.20–0.25 (deviance +29.2 at the 2.0 bound); **but** full's own searches hold an equal-log-posterior second
  basin at κ 0.028 / ℓ 2.0 (13.45 vs 13.46), and quick's ℓ profile prefers ℓ 2.0 outright: the strong-short vs
  weak-long degeneracy persists across searches (the full profile's single-basin refits do not see the other
  basin — the known polish/jump trap two bullets down); Cy3B κ 0.20 (0.12–0.35) and ℓ 0.58 (0.50–0.68) both
  interior and the profiles agree (κ 0.13–0.30, ℓ minimal at 0.63 with +1.1/+2.8 one step either side) — the clean
  block; Atto655 D₂O κ interior in Laplace (0.27, 0.016–4.7) but ℓ on its 2.0 upper bound (profile monotone down
  to 2.0) and static 33 (68 % 2.0–100) — the plateau moved from κ to (ℓ, γ); Stage C κ 0.026 (0.010–0.099), the
  interval running into the scale lower bound, ℓ on its 0.1 bound (profile prefers 0.20, 0.18–0.23). The
  stored-vs-refit verdict is
  unchanged: no single joint interior optimum. Next decision (owner): a prior tying κ and ℓ (e.g. the
  free-amino-acid contact volume ∫κ f 4πr²dr fixed by the titrations) is what removes this trade-off; the kernel
  alone does not.
- Verify: the slow gate `-m slow test_male_reproduction.py -k refit` has no completed run in the kept guard
  records; the guard killed it twice on 2026-10-21 via the swap-growth heuristic — foreign swap charged to the
  run once the 7-worker tree passes 1 GB (its own tree is stable at ~2.6 GB, under the 4096 MB cap, while the
  desktop sat at 8 GB swap from other apps). Relaunched 2026-10-21 10:25 with
  `CHISURF_TEST_MAX_SWAP_GROWTH_MB=0` and `CHISURF_TEST_MIN_FREE_MB=2048` (tree cap and disk floor unchanged —
  genuine exhaustion still stops the run), log `~/.cache/chisurf/slow-refit-rerun-20261021.log`. **Pending.**
- Measure: refit + profiles: scratch runner pattern `Analysis(preset).run("all")`, then
  `graph_fit.profile_likelihood(view, "delta", values=np.linspace(-4, 5, 19), workers=…)` with
  `profile_likelihood.method: polish`. **Trap:** a polish profile in this landscape is jagged (AF488 deviance 105 at
  κ 17.8, 6.6 at 31.6; full Atto655 D₂O δ deviances 90–910 away from the optimum are failed refits, not
  evidence): warm starts jump basins, so read the minimum and the ends, not the curve.
- Measure: quick runtime 685 s on 6 workers (was 1277 s): the 9 searches per block are now ~80 % of it (AF488
  113 s, Atto655 joint 200 s, Atto655 D₂O 190 s). Full (7 workers): 11 793 s; the serial MINPACK joint fit alone took 5500 s on the
  41-parameter graph; `joint_minpack: false` for full too would cut ~1.5 h (owner decision: MINPACK is the stored
  run's path).
- Open: owner questions 3(a) (the "key figure" does not narrow κ) and 3(c)/(d) (record item 3) are still open.
- Open: WP6 (record item 1f): route the Analysis page through `api.analyse(background=True)`; colour bar on the
  hyper-posterior heatmap. WP7-guide: retake the six figures (`python docs/guides/screenshots/quest.py
  _grab_quest_analysis`) once WP4 settles.
- Open: WP9 (record item 7): IMP.bff's walk takes no start weight; PDE with FRET is not wired.
- Open: `~/dev/quest/prototype/MIGRATED.md`'s Open list mirrors items 1e, 4, 7; the MCMC check (cell 40,
  `sampler_check`) is declared but not run. Tracked in [PRD-154](/prds/prd-154.md) as W16.
- Blocked: German/French catalogues of the new view.json wait for the i18n batch (owner rule).
- Tried and reverted: PCHIP for the δ interpolation (2026-10-20). A monotone C1 cubic has zero slope at an offset next
  to a flat stretch, so τ(δ) became a staircase (slope at δ −1: −0.0015 ns/Å vs −0.07/−6.7 linear left/right). The
  B-spline (1–4–1 smoothing at the offsets) is used instead.
- Tried and reverted: in the prototype, do not re-port: the Brownian-walk *objective* (it01–it06), a single stickiness or
  `exp(-α n)` shielding (it11), the Cauchy loss (it05), the AF4_C2R linker (record item 5).
- Measure: fast suites `pytest chisurf/plugins/quenching_estimator/test/test_inference_{site_table,site_model,graph_fit,api}.py`
  (~3 min); `-m slow test_male_reproduction.py` (stored optimum ~4 min, refit hours).

# Work package record

The history of each package, with its measurements and traps.

1. **Done: WP0 (data + golden).** `examples/male/` (3 CSVs, `provenance.json`, `1OMP.cif`,
   `1ANF.cif`), `core/inference/measurements.py`, `test/data/male_site_1omp72_L20.12.npz`,
   `test/baselines/{make_male_prototype.py,male_prototype.json}`, `test/test_male_measurements.py`.
   **Regenerate:** `QT_QPA_PLATFORM=offscreen <arm64>/bin/python
   chisurf/plugins/quenching_estimator/test/baselines/make_male_prototype.py` (`--convert` also
   rewrites the CSVs from `~/dev/quest/data/*.xlsx`; `--no-walk` skips the 2-min walk). It executes
   notebook cells 2–31 plus cell 33's row selection, reads the 54 site tables from
   `prototype/cache/` (stops if one is missing), and checks that the shipped CSVs read by
   `measurements.py` give the notebook's workbook frames exactly. Two runs give byte-identical JSON.
   **Checks passed:** `data` (64 rows) and `K_POSTERIOR` (17) equal `output/20261001-142438_*` bit for
   bit. `Site.lifetime` at the *printed* (4-digit) stage estimates gives the printed rms/median
   (AF488 0.616/0.047, Cy3B 0.023/0.010, Atto655 D₂O 0.633/0.061, joint 0.523/0.094; AF488 mean dark
   13 %), and the naive H₂O test gives 0.48 ns, 16/18. So the cached tables and the `Site` code
   are the stored run's. Golden keys and their meaning are in the JSON's `about` and in each
   section's `note`. Water-access r at the printed Stage C parameters is 0.32 (0.37 without 322);
   the stored run never printed it.
   **Trap for WP2/WP3: today's IMP.bff does not rebuild the cached tables.** Rebuilding APO 72
   L 20.12 with cell 25's own code and IMP.bff `ab5de21` gives 106 992 AV points, not 97 722 (the
   site PDB is byte-identical, so the AV call changed). The direct method at APO 233 likewise gives
   2.52 ns, not 2.59 (walk here 2.38 ± 0.05). The likely cause is the 2026-10-12 IMP.bff obstacle
   radii change (`imp_atom_radius`), which is not verified. Until it is pinned down, "rebuilt table
   equals the npz" and "direct = 2.59" cannot both pass on the current IMP.bff. WP2/WP3 must find
   which AV argument or radius moved and decide whether to reproduce the old grid or re-pin the
   golden with a log line. The `Site` golden (`site_lifetimes`) does not depend on this, because it
   reads the shipped/cached tables. **Resolved (WP2 bisect + WP3 re-pin, item 1d):** four owner-approved FPS-parity AV
   changes plus a voxel-frame bug; re-pinned on today's geometry, the prototype kept as an exact regression.
   **Interfaces for later packages:** `measurements.load_measurements(folder=None) -> Measurements`
   (`lifetimes`, `titration_points`, `titration_summary` as numpy structured arrays, `corrections`
   as `SiteCorrection` tuples, `folder`). Field names are in `LIFETIME_FIELDS`,
   `TITRATION_POINT_FIELDS` and `TITRATION_SUMMARY_FIELDS`. Lifetimes have `site` (float, NaN for
   the free dye). Titration points drop rows without dye or τ, as the notebook does. Empty floats
   are NaN and empty ints are −1. The CSVs keep the workbook column names, except the summary,
   which has two `+/-` columns and so uses the notebook's names.
   **Trap (still true):** the stored notebook outputs are from a cordeshub run (`RUN_STAMP 20261001-134626`).
   That run's CSVs are *not* in `prototype/output/`. The full-model CSVs that are on disk
   (`20260930-162323_*`) come from an older model (lam free, no `dtau_shield`, no `FIXED`),
   so do not use them as fit references.
1b. **Done: WP7b (examples) and WP7-theory (2026-10-20).** `examples/0[1-5]_*.py` + `test/test_examples.py`
   (11 tests, ~22 s, none slow), `docs/concepts/quenching_inference.md` (registered, cross-linked; `dye_quenching.md`
   updated where the notebook superseded it). **Measure:** `pytest chisurf/plugins/quenching_estimator/test/test_examples.py`.
   **Traps found:** quest's site E:100 is buried at the current AV default (W 4.5): example 01 uses E:5 (TRP, QY 0.715)
   vs E:69 (QY 1.000), example 03 keeps E:100 as the failed-record demo. E(t) → p(R) agrees with the AVs only without
   stickiness (57.6 vs 58.2 Å for E55–E132); at slow 0.1 the walk gives 50.0 Å (the WP9 defect, shown in example 04).
   Notebook 04 (Haas–Steinberg) is covered by IMP.bff: `diffusion_propagate_krylov` on one voxel line of a 3-D grid
   (reflecting walls; the notebook's ends were absorbing); it is example 05. `scan`'s `dominant_quencher` names a residue
   for a trace rate at QY 1.000 (E:55 "TYR 100 %"): the example filters on QY < 0.99. **Fixed in WP9:** `scan.MIN_QUENCHED_FRACTION` (1 %) — no dominant quencher below it.
   The theory page states the overclaims of 3(a), 3(b), 3(d) as they are. **Open:** guide-80 example sections (WP7-guide).
1c. **Done: WP1 (measurement statistics, 2026-10-20).** `core/inference/{columns,titration,lifetime_errors,kq_scaling}.py`,
   `settings/analysis/measurement_columns.yaml` (8 declared tables plus a `settings` block holding every selection the
   notebook hardcoded: grids, prior points, reference dye, `titrated` map, D₂O dyes), 3 presets in `settings/dye_repository.json`,
   `test/test_inference_{titration,lifetime_errors,kq_scaling}.py`. **Measure:** `pytest
   chisurf/plugins/quenching_estimator/test/test_inference_{titration,lifetime_errors,kq_scaling}.py` (19 tests, under 1 s). Every chapter 1–3a number of
   `male_prototype.json` (per_day, K_POSTERIOR, hyper marginals/quantiles/edge, water, scatter, the 64 `data` rows, coverage,
   TAU0, KQW_FREE, KQ_TABLE ± SD, measured water access) comes out **bit for bit**. The tests use rtol 1e-12 only so that
   another LAPACK under `np.polyfit` passes. **Trap:** τ₀(H₂O) is a pandas *grouped* mean in the notebook, which uses a
   compensated sum, so a plain `np.mean` can be one ulp off. `lifetime_errors._compensated_mean` keeps it exact.
   **mmfdb `16da3c3`** (dictionary 1.12) holds every term the migration needs, so WP3/WP4 do not edit the dictionary:
   `_flr_analysis_feature.{measurement_date, ligand_state, solvent_isotope, stern_volmer_constant[_sd], titration_day_count,
   bimolecular_quenching_constant[_sd], day_to_day_error_abs/rel, water_quenching_rate[_sd], lifetime_series_count,
   lifetime_point_count, measured_lifetime[_sd], measurement_relative_scatter, relative_scatter_{pooled,leave_one_out,robust},
   leave_one_out_coverage, water_access[_sd], solvent_exposure, dark_fraction, predicted_lifetime[_sd], leave_one_out_z,
   model_error}` and `_flr_fit_parameter.{kQ_sd, slow_factor_{common,aromatic,hydrophobic,basic,acidic,polar}, quench_scale,
   quench_contact_offset, rotamer_weight, static_quench_strength, static_quench_offset, shield_lifetime_increment}`. Reuse
   `_flr_fit_parameter.{kQ,tau0}`, `_flr_probe_list.chromophore_name` (dye), `_chem_comp.id` (residue),
   `_flr_poly_probe_position.seq_id` (site), and for WP4's estimate tables `_mmfdb_parameter.{name,value,
   confidence_interval_low,confidence_interval_high}`. The red MLE burst columns (`Tau/2I*/gamma/r0/rho (red)`) are in
   `mmfdb_workflow_ext.dic`, because that is the file the burstwise importer reads, not `mmfdb_flr_ext.dic`.
   The same commit fixes an mmfdb parser gap. A looped `_item.name` (the DDL2 parent form) was dropped, so about 60 PDBx key
   items (`_chem_comp.id`, `_entity.id`, …) did not resolve. Descriptions written before `_item.name` were lost too
   (5319 → 259 items without one). **Interfaces for WP3/WP4:** `titration.analyse_titrations(points) -> (per_day,
   TitrationPosterior)` with `.table`, `.weight`, `.k_mean()`, `.k_sd()`, `.tau0()`, `.quantile()`, `.edge_mass`;
   `lifetime_errors.analyse_lifetimes(lifetimes, titration_summary) -> LifetimeErrors` (`.data` = the notebook's `data`
   with `tau_x` for `tauX`, `.tau0[(dye, solvent)]`, `.kqw_free`, `.access`, `.scatter`, `.coverage`, `.water`);
   `kq_scaling.kq_vector(dye, K, tau0, textbook)` (WP4 calls it with the graph's K), `kq_scaling.model_keys()` (the 12
   K_KEYS), `kq_table(posterior)`, and `columns.make_table(name, rows, path)` for WP4's own `result_columns.yaml`.
   **Presets, open:** `av_parameter.linker_width` stays IMP.bff's 4.5, because `test_av_defaults` pins every preset to it and
   owner question 3(e) is open. The notebook's W 0.5 / grid 0.5 are in each preset's `measured_analysis`. The per-group
   slow factors and `quench_scale`/`contact_offset`/`rotamer_weight`/`shield_lifetime_increment` are the stored run's
   *printed* stage estimates. kQ is the unscaled table, so the presets do not reproduce the notebook's τX until WP4/WP9
   decide whether the quench scale is folded into kQ. Cys takes the Trp ratio, as Pro does (MalE has no Cys, so this is
   an extrapolation).
1d. **Done: WP3 (site tables + site model, 2026-10-20).** `core/inference/{site_table,site_model}.py`,
   `settings/analysis/site_model.yaml` (every cell-6/23/25 selection plus the declared `site_predictions` and
   `site_exposure` tables, terms resolve in mmfdb 1.12), `test/test_inference_site_{table,model}.py` (11 fast tests ~13 s,
   2 `slow` ~4 min), `test/data/male_site_1omp72_L20.12_volume.npz` (the prototype's voxel set: indices, ng, dg,
   attachment). **Measure:** `pytest chisurf/plugins/quenching_estimator/test/test_inference_site_{table,model}.py`
   (`-m slow` for the 54-table checks; the golden-row one skips unless `~/dev/quest/prototype/cache` is present with the
   golden's sha256). **Proved exact:** on the prototype volume in its own frame
   (`grid_origin = attachment − ((ng−1)//2 − 0.5)·dg`) the port gives the shipped table bit for bit (neighbours, float16
   contacts, exposure 0.0 diff); `Site.lifetime` gives every one of the 82 golden rows with `==` (not 1e-9) on the 54
   prototype tables, and cell 53's time-weighted exposure exactly. **Re-pinned (decision 2026-10-20, see the AV conflict
   row):** today's IMP.bff AV + the corrected grid frame. APO 72 L 20.12: 97 722 → 106 992 voxels (the array door
   `get_av` with IMP radii × 0.84 equals `get_av_from_pdb` on the site PDB at APO/HOLO 72/233, voxel for voxel); reachable
   e 0.9621 → 0.9644 (186: 0.9748 → 0.9740); Stage C time-weighted e at 72 0.662 → 0.651, 186 0.483 → 0.498. Direct APO 233
   (L 21.5, slow 0.3) **2.832 ns** (notebook 2.59; 2.523 old frame + today's AV), walk 2.76 ± 0.10 ns (seeds 1–3, 2 s):
   |Δ| 0.07 ns, 2.6 % — the frame fix closes most of the 12 % gap of owner question 3(b). At the printed stage parameters
   the rebuilt tables fit worse (rms/median |dev| ns): AF488 0.616/0.047 → 0.649/0.165, Cy3B 0.023/0.010 → 0.255/0.205,
   Atto655 D₂O 0.633/0.061 → 0.853/0.242, Stage C 0.523/0.094 → 0.791/0.225. **This is expected, not a defect:** the
   contact offset δ (AF488 −0.42, Cy3B +1.01, Atto655 −2.8 Å) absorbed the old frame's ≤ 0.5 Å registration error, so
   **WP4 must refit on the corrected geometry**; its accept numbers are the stored run's and can only be compared within
   their 68 % intervals after the refit, not at 1e-9. Every one of the 54 rebuilt tables grows 6–12 % (APO 72 at L 19.74/20.12/20.4: 99 530/106 992/112 774; re-derive any with
   `SiteLibrary().table(state, site, L).n_voxels`). One table builds in ~1.3 s (≈ 2.5 s with the AV
   and caching), 54 in ~2.5 min. **Ensemble:** the site model uses the notebook's closed form p ∝ count·∏ s_g^(−n_g) in
   numpy (`Site.weights`), not IMP.bff's `DynamicAccessibleVolume.update_occupancy`; the Itô stationary state p ∝ 1/D is
   the same estimator only when D ∝ s (imp.bff `okf/quest-site-kernels.md` item 2), which the cell-23 check (`direct_lifetime`,
   p ∝ 1/s of the quenching model's own maps) confirms against the walk. The walk and a PDE path stay for WP9.
   **Interfaces for WP4 (stable):** `site_table.settings()`; `site_table.site_table(structure_path, site, linker_length,
   chain=None, settings_=None, cache_dir=None, use_cache=True) -> SiteTable` (`.neighbours (n,20) int8`, `.contacts
   (n,5,10,2) float16`, `.exposure (n,) float32`, `.voxel_indices`, `.meta`, `.path`, `.voxel_centres()`), cached as
   `<settings>/cache/quenching_estimator/site_tables/site_<key>.npz` (`site_key` = structure sha256 + site + linker + every
   table setting + `SCHEMA` + `IMP.bff.__version__`); `site_table.male_structure(state)`; `site_model.Site(table_or_path)`
   with `.weights(theta)`, `.seen(theta, tau0, water)`, `.lifetime(theta, tau0, water) -> (tau_x, dark, visible_e)`,
   `.exposure_profile(...)`, `.groups`; `site_model.predict(points, theta, tau0)`; `site_model.SiteLibrary(structures=None,
   cache_dir=None)` with `.site(state, site, L)` (memoised) and `.points(rows, linker_length=None, water=None)` (linker from
   the declared `linker_lengths[dye]`); `predictions_table(rows)` / `exposure_table(rows)` (declared columns). θ keys:
   `ln_s_<group>`, `ln_scale`, `delta`, `lam`, `ln_static`, `delta_static`, optional `dtau_shield`, `kq` (5-vector in
   `quenchers` order; from `kq_scaling.kq_vector`). `ln_s_common` does not enter the model (ridge centre only).
   **Traps:** `IMP.bff.__version__` reads `ab5de21` on the build tree although its HEAD is `0b178903a` (configure-time
   stamp), so a kernel rebuild without a reconfigure does **not** invalidate the cache: bump `site_table.SCHEMA` or clear the
   folder when a kernel changes. The labelled-residue cut keys on (chain, res_id) only, not the Bio.PDB hetero flag (no
   effect on MalE). The walk check is not `slow` (2 s), contrary to the plan's guess.
1e. **Done (engine) / open (science): WP4 graph fit + stages + report** (chisurf d465b4f8f interface, 5901dafa0 fast
   `Site` de-duplication, 4ceaad395 fixes + reproduction, final commit pins the refit; mmfdb c190449). Interface stable:
   Files: `core/inference/{graph_fit,stages,report}.py`, `settings/analysis/{fit_parameters,stages,result_columns}.yaml`,
   `test/test_inference_graph_fit.py` (8 fast tests ~6 s, an analytic stand-in site model: truth recovery, outlier + LOO,
   propagation, profile, factor graph 48/20/3/18/2, stage plumbing, cancel, 2 worker processes = 1). mmfdb `c190449`
   (dictionary 1.13: 16 `_flr_analysis_feature` result terms). **Measure:** `pytest
   chisurf/plugins/quenching_estimator/test/test_inference_graph_fit.py`.
   **Headless entry (WP5 wraps these; nothing else is needed):**
   - `stages.load_analysis_data(folder=None, library=None, structures=None, cache_dir=None) -> AnalysisData`
     (measurements, `per_day`, `posterior`, `errors` = `LifetimeErrors`, `context` = `graph_fit.TitrationContext`,
     `library` = anything with `.site(state, site, linker) -> Site`: `SiteLibrary` by default, `stages.TableFiles({(state,
     site, linker): npz})` for stored tables such as the prototype cache).
   - `stages.Analysis(data=None, preset=None | "full" | "quick", fit_overrides=None, workers=None, profile=True)`;
     `.run(stages="all" | "A" | ["A", "C"], progress=None, cancel=None) -> AnalysisResult`. Solved graphs are kept on the
     object, so a later `run("C")` after `run("A")` costs nothing (A and C are views of one graph). `stages.run_stage(stage,
     data=None, preset=None, fit_overrides=None, workers=None, progress=None, cancel=None, profile=True, analysis=None)` and
     `run_analysis(...)` are the one-call forms. `stages.stage_names()` = `["A", "B", "naive_h2o", "C", "summary"]`
     (declared order); `graph_fit.preset_names()` = `["full", "quick"]`.
   - **Progress/cancel** use `JobManager.reporter(job_id)` / `.canceller(job_id)` shapes: `progress(percent: int, message:
     str)` (monotone, ends at 100), `cancel() -> bool`; a cancel raises `core.tasks.CancelledError` at the next checkpoint
     (between searches, at every joint-fit residual evaluation, between profile points; a search already running in a
     worker finishes first, ≤ ~1 min).
   - `workers`: worker *processes* (spawn context, safe on macOS; 1 = in process, default the CPU count). Same numbers as 1.
   - `AnalysisResult`: `.stages {name: StageResult}`, `.graphs {name: GraphResult}`, `.tables() -> {"<stage>.<table>":
     record array}`, `.view(label) -> BlockResult`, `.to_dict()` (JSON-able: per stage `title`, `numbers`, `text`, `tables`
     as row lists; per graph blocks/size/factor-graph summary), `.write(folder)` (one CSV per table + `summary.json` +
     `report.md`). `StageResult`: `name`, `title`, `views` (BlockResult list), `tables`, `plots`, `numbers`, `text`.
   - **Tables** (declared in `result_columns.yaml`, `site_exposure` in `site_model.yaml`): a blocks stage has
     `predictions` (`fit_predictions`), `estimates` (`fit_estimates`: graph, block, dye, parameter, value, low_68, high_68,
     note), `leave_one_out`, `site_ranking`, `searches`, `titration_slopes` (`graph_titration_slopes`), `intervals`
     (`interval_summary`: laplace and profile 68 % of the scale), `scale_profile`; C adds `water_access`
     (`water_access_model`) and `exposure` (`site_exposure`); `naive_h2o` has `predictions`; `summary` has `dyes`
     (`dye_summary`), `estimates`, `titration_slopes`.
   - **Plot data** (`StageResult.plots`, plain lists, for WP6's implot): `parity:<block>` (measured, predicted,
     sigma_total = x error, pred_sd, state, site, solvent, outlier, tau0 per solvent), `estimates:<block>` (rows),
     `loo:<block>` (site, max_abs_z, limit 3), `profile:<block>` (`laplace` samples + summary, `profile` values/deviance/
     best/low/high), `k_graph` (slope rows); C also `water_access` (rows, r_all, r_without) and `exposure` (per site:
     exposure, weight = visible-time histogram, visible, reachable, dark_fraction) and `profiles` (B vs C scale summaries);
     `summary`: `scale` and `stickiness` per dye (value/low/high/note).
   - Lower level (`graph_fit`): `settings(preset, overrides)`, `parameter_specs`, `free_names`, `fixed_values`,
     `model_error`, `ridge`, `clipped_inverse`, `Block`, `search`, `Graph`, `joint_fit`, `block_views`, `fit_graph(blocks,
     ...) -> GraphResult`, `propagate(view, f)`, `laplace_samples(view)` (what the prototype called the profile),
     `profile_likelihood(view)` (a real profile: the block's sub-graph refitted at fixed scale values),
     `describe_graph(graph, titrated)` (IMP.bff `InferenceFactorGraph`). `report.explain/dye_line/summary_text/...` write
     the texts from the numbers.
   Later additions: `graph_fit.settle/adopt`, `Block.add_start` (declared starts, `stages.yaml` `starts`, setting
   `use_declared_starts`), `Analysis.replay(name, values, slopes)` / `solve_from`, `joint_fit(start=, minpack=)` +
   `polish` (projected LM), site-table progress in `Analysis.run`, worker pools that hide `__main__` (plain scripts with
   `workers > 1` need no main guard; subprocess test).
   **(a) Measured** (`pytest -m slow test/test_male_reproduction.py -k stored_optimum`, 4 min, skips without
   `~/dev/quest/prototype/cache`): at the stored optimum (blocks settled at the printed best fits + printed model
   errors, joint fit polished from the printed parameters and slopes) on the 54 prototype tables every printed best fit
   and 68 % end agrees to 4 decimals or within 0.3 % of the parameter's range, outlier sets exactly, LOO |z| within
   0.15, K_graph within 0.002, naive 0.48 ns / 16 of 18, factor graph 48/20/3/18/2, graph sizes 41 and 19. Not compared:
   "other regions possible" (needs the 64 searches), Stage B delta_static (not determined: drifts to its bound).
   **Trap 1 (the search is not reproducible):** the 64 random starts of the stored seeds, on IMP.bff's L-BFGS-B, reach
   other optima than the stored scipy run: AF488 scale 5.8 with 3 search outliers (stored 6.2, 4), Cy3B best log
   posterior 25.0 (32.4 at the stored point; scale 0.22 vs 1.13), Stage B scale 3.3 (0.11); only Stage C lands in the
   stored basin (s 0.107 vs 0.108, scale 0.11). Per-start the two optimisers are equally good (8 Cy3B starts compared);
   the landscape has narrow basins. Hence the declared starts. A 256-start 30-iteration screen + polish still reached
   only 26.2 for Cy3B. **Trap 2:** MINPACK (bounds transform) stopped with Atto655 static on its bound (joint cost 26.609
   vs 26.601 at the stored optimum); restarts did not help (26.605), the projected LM polish from the stored point does.
   **(b) Measured, refit on today's geometry** (`-k refit`, ~2.3 h on 6 workers; numbers pinned in `REFIT`, table in
   [quenching inference](../../docs/concepts/quenching_inference.md) "MalE refit"): full / quick κ (68 %): AF488
   10.0 (7.2–10) s 0.277 / 6.4 (3.0–10) s 0.131 (stored 6.2 (4.6–8.2)); Cy3B 0.058 (0.019–0.18) / 0.070 (0.021–0.24)
   (stored 1.1 (0.19–6.7)); Atto655 D2O 10.0 (8.8–10) / 6.4 (4.9–8.5) (stored 0.111 (0.080–0.154)); Stage C 10.0
   (8.8–10) / 10.0 (6.0–10) (stored 0.112 (0.080–0.157)); naive H2O 0.48 / 0.55 ns, 16 of 18; water-access r 0.49
   (−0.29 without 322). Runtime full 8142 s, quick 1277 s (6 workers, loaded machine).
   **What it blocks / next:** the refit is *not a result*: κ = 10 and δ = +2 (Atto655) are the upper bounds, δ = −1.0
   (AF488 full, Atto655 quick) is a node of the δ interpolation (piecewise linear: kinks make local optima), static runs
   to its bound. The bounds (`fit_parameters.yaml`: scale ≤ 10, delta −3…2) were set for the old frame where δ absorbed
   the registration error. Owner decision needed: widen scale/delta (tables cover δ −4…+5), smooth the δ interpolation
   (WP3 file), or reparametrise. WP6's "quick hits the bounds" is this, not the preset. Quick is still slow (1277 s): the
   serial MINPACK stage dominates; next step is `joint_minpack: false` for quick (polish only, parallel Jacobians) and
   the profile refits on the polish too. Stage C still does not narrow κ (Laplace factor 1.13 vs 1.13).
   **WP4b (2026-10-20, owner decision "diagnose, then widen").** *Geometry: no double shift, no bug.* On today's APO 72
   AV the voxel centres `grid_origin + ijk·dg` all lie within L 20.12 of CB (max 20.114 Å; the old attachment frame
   reaches 20.265) and violate the 3.5 Å clearance for 0.07 % of voxels (old frame 1.6 %). A brute-force count
   (quencher/slow centre snapped to the nearest voxel, `|d| < floor(R/dg)·dg`) equals the TRP/TYR contact maps and every
   neighbour column voxel for voxel at shift 0 and not at ±0.25 voxel; exposure uses the same centres
   (`test_every_feature_sits_in_the_volume_s_own_frame`). The old-minus-new shift at APO 72 is (0.333, 0.237, 0.160) Å
   (not the (0.33, 0.01, 0.25) quoted in imp.bff's concept). *Three-way tables* (A notebook-era volume — Bondi radii,
   stencil 74, no allowed sphere — in the old frame; B the same volume in the grid frame; C today's AV, grid frame) at
   the printed stage parameters, rms / median |dev| ns: Atto655 D₂O P 0.633/0.061, A 0.633/0.061, B 0.768/0.203, C
   0.853/0.242; AF488 0.616/0.047, 0.619/0.057, 0.649/0.180, 0.649/0.165; Cy3B 0.023/0.010, 0.037/0.023, 0.172/0.118,
   0.255/0.205. So A reproduces the prototype (P), and the frame (A→B) is most of the change. The uniform-average contacts
   move per site by −26…+36 % at δ 0 (median ratio 1.01, no common direction) but by 0…×1.7 at δ −3, where a contact is
   a handful of voxels decided by a sub-voxel registration (the voxel snapping itself is up to 0.43 Å): the stored
   Atto655 optimum (δ −2.8) lived exactly there. The AV (B→C) collapses Atto655 HOLO 72/92/95 onto one voxel with two
   aromatic neighbours (p = 0.99999, τ 2.680 ns at all three): with s_aromatic 0.001 one voxel weighs 10⁶ more, so the
   ensemble is decided by single-voxel reachability — the source of the multimodality. *Widened* (fit_parameters.yaml)
   κ 0.01–100, δ −4…+5, γ 0.001–100, δ_s −4…0; *smoothed* (site_model.yaml `delta_interpolation: bspline`); *quick*:
   `joint_minpack: false`, polish 15, profiles polished (`profile_likelihood.method: polish`), Jacobians on one
   `graph_fit.WorkerPool` per fit (a fresh spawn pool per Jacobian before). *Proposal (not implemented):* (1) fit
   κ·C̄(δ) (κ times the count-weighted mean contacts at δ) instead of κ, which removes most of the κ–δ trade-off;
   (2) a distance-continuous rate kernel k(r) = κ k_Q e^{−(r−R_q)/β} on stored per-voxel quencher distances (a table
   change) instead of a step at R_q + δ, so the contact strength has no dark plateau; (3) a lower bound or prior on
   s (e.g. s ≥ 0.01) so the ensemble cannot collapse onto one voxel.
   **WP4c plan (owner decision 2026-10-20: option 2, the distance-continuous rate kernel).**
   (1) *Table* (`site_table.py`, `SCHEMA` v2): beside the contact counts, every voxel stores the rotamer-weighted
   distribution of its quencher distances, per quencher type and side-chain source, as a histogram of u = r − R_q
   (R_q the reference contact radius, r voxel centre to quencher centre in the grid frame, exact, no snapping) on
   declared bins (`site_model.yaml: distance_histogram`, u −4…+10 Å in 0.5 Å, one underflow bin). It is sparse (~9
   non-zeros per voxel at APO 72), stored as row/column/weight arrays: measured ~0.6–1.3 MB compressed per table.
   numpy builds it (no IMP.bff kernel needed: ~5 s per table). (2) *Rate model* (`site_model.yaml: rate_model:
   kernel | contact_shell`): k(x) = κ Σ_q k_Q(q) Σ w f(u), f = 1 for u ≤ 0, e^(−u/ℓ) beyond, averaged exactly over each
   bin (smooth in ℓ). κ stays the strength at contact; the decay length ℓ replaces δ (a free offset would be degenerate
   with κ in the tail: κ e^(−(u−ρ)/ℓ) = e^(−(u−ρ−ℓ ln κ)/ℓ)). The static channel uses the same kernel offset by δ_s.
   `contact_shell` (the prototype's) stays selectable; the reproduction tests declare it. (3) *Fit*
   (`fit_parameters.yaml`): new `decay_length` (log, 0.1–2 Å; e^(−10/2) = 0.7 % is cut at u = 10), every parameter
   gets its mmfdb `term`, parameters used by one rate model only declare `rate_models` and an `inactive` value (δ for
   kernel, ℓ for contact_shell). New term `_flr_fit_parameter.quench_decay_length` (mmfdb dictionary + schema binding).
   (4) Refit quick + full, κ and ℓ profiles per stage, pin, docs. (5) `joint_minpack: false` for full only if the
   polish reaches MINPACK's optimum on the prototype tables (`minpack_vs_polish` check).
   **WP4c done (code):** schema v2 tables (APO 72: 0.98 MB, 691 566 entries, 6.5 per voxel, build ~1.2–2.5 s);
   `Site` kernel path `kernel_weights` / `_kernel_contacts` (rows merged by `unique_sparse_rows`, a double 64-bit
   hash: 47 323 of 106 992 rows; the shell has 11 735) — 5.5 ms per lifetime vs 2.4 ms for the shell, a cache of the
   last four rate sets halves Stage C; voxel-by-voxel equality test to 1e-10; mmfdb 53d94e6 (dictionary 1.14,
   `quench_decay_length`). Quick on the kernel 1136 s (7 workers; shell 685 s). **joint_minpack for full: kept.** On
   the prototype tables, from the printed best fits, polish only reaches cost 26.614 (joint) / 14.216 (heavy water)
   vs MINPACK 26.609 / 14.212 (stored 26.601): close (κ within 0.7 %) but not the same optimum, so full keeps MINPACK.
1f. **Done: WP5 (headless surfaces, 2026-10-20), on the WP4 interface only.** One domain call,
   `core/runs.py: analyse(stages, data=, structures=, tables=, cache_dir=, preset=, fit_overrides=, workers=, profile=,
   output=, project_dir=, save_outputs=True, run_id=, progress=, cancel=, analysis=)` -> `{run_id, directory, files, result,
   analysis}`; the API, the RPC job and the CLI all call it. It writes `AnalysisResult.write` (the declared tables
   `<stage>.<table>.csv`, `summary.json`, `report.md`) plus `run.json` (`kind: analysis`, inputs, table names) into
   `--output` or the run directory `<runs>/<job_id>` (so `quest.runs.list/get` list and read analysis runs too; a
   simulation summary keeps its old keys). `core/tasks.py: JobManager.submit(action, work(progress, cancel), job=)` +
   `wait(job_id, timeout)` run a job on a daemon thread (CancelledError -> `cancelled`).
   - **RPC** (manifest, contract 1.1.0, error codes `invalid_analysis`, `operation_cancelled`, `job_not_finished`):
     `quest.analysis.template` (stages/order/graphs/presets as differences/fit settings/result tables, all from the YAML),
     `quest.analysis.run` (long_running, cancelable; blocking by default and still listed/cancelable; `background: true`
     returns `{job_id}` at once; `continue_from: <job_id>` reuses that job's solved graphs), `quest.analysis.result(job_id)`
     (from memory with plot data, else the stored run's `summary.json` without plots), `quest.analysis.site_table(state,
     site, dye|linker_length, structure, chain, cache_dir)` (a summary, not the arrays). Progress/cancel through the
     existing `quest.jobs.get` / `quest.jobs.cancel`. In process the result is the native `AnalysisResult`; the wire form is
     `rpc.services.analysis_payload` (= `to_dict()` + per-stage `plots`, NaN -> null), registered with `to_payload`.
   - **API** (`api/local.py`): `analysis_template()`, `analyse(...)`, `analysis_result(job_id)`, `site_table(...)`,
     `job(job_id)`, `cancel_job(job_id)`. WP6 calls these.
   - **Measure:** `pytest chisurf/plugins/quenching_estimator/test/test_inference_{api,cli}.py` (20 fast tests ~8 s on
     the stand-in site model + 1 subprocess run of `csc quest analyse` on the shipped MalE data, ~45 s CPU, 2 min under
     load). **Trap / cost:** that run's time is *loading* the 18 Atto655 sites, not the fit: `Site.__init__`'s
     `np.unique(features, axis=0)` (site_model.py, WP3's) is 80 % of it (~5 s per site under load, ~1.5 s idle). A void-view
     or hash de-duplication would make every analysis start ~10x faster; owner of `site_model.py` should take it.
   - **For the WP7 guide author (CLI / Python API section; exact commands. The tests run each option on the stand-in model and `--stage B` on the real data; the full run below is not yet run through the CLI):**
     `csc quest analyse --quick --stage B -o out/` (heavy-water Atto655 only; tables + `report.md` in `out/`);
     `csc quest analyse --stage all -o out/` (the full 64-start run; the prototype took 23.6 min on 44 cores);
     `csc quest analyse --quick --stage A --stage C --format json --no-save` (summary JSON on stdout);
     `csc quest analyse --quick --stage B --format csv --table B.estimates` (one declared table on stdout, byte-equal to the
     file); `--set n_starts=4 --set profile_likelihood.points=5` (declared fit settings, dotted = nested), `--no-profile`,
     `--workers 1`, `--data <folder with the three CSVs>`, `--structure APO=<file>`, `--tables tables.json`
     (`{"APO:72:20.12": "site.npz"}`), `--cache-dir`. Python: `from chisurf.plugins.quenching_estimator.api import local as
     api; r = api.analyse("B", preset="quick"); r["result"].stages["B"].tables["estimates"]`; background:
     `j = api.analyse("all", background=True)["job_id"]; api.job(j)["progress"]; api.cancel_job(j); api.analysis_result(j)`.
     The `docs/reference/plugins/quenching_estimator.md` RPC table needs `pixi run -e docs docs-plugins` after this lands.
1f. **Done: WP6 (Analysis page, demo, tour, 2026-10-20).** The QuEst window has two pages, switched in a strip at its
   top (`gui/app.py`: `QuEstWindow.page`, `show_page`, `draw_pages`): **Forward model** (unchanged) and **Analysis**
   (`gui/analysis_card.py`: `AnalysisModel` Qt-free + `AnalysisCard` on `CardShell`, its own `analysis_help.md` and
   `analysis_guide.json`, 10 steps, 4 awaits, step 2 = `load_example`). The page is `gui/analysis.view.json`: the run
   panel, then the result `tabs` *Data* (Stern-Volmer + hyper-posterior heatmap + K_SV/kq, site lifetimes, free-dye tau0,
   water bars), *kQ per dye*, *Site tables* (row per built table, exposure histogram of the selected one), *Fit* (stage +
   data set choice, report text as markdown, parity with x/y errors, outlier rings, tau0 lines, forest on log x, LOO bars
   + 3 sigma line, scale profile, estimates/predictions, K before/after), *Water* (access parity + r, time-weighted
   exposure stairs, scale B vs C), *Summary* (scale and stickiness on log axes, dye table). Tables read the **declared**
   columns (`tables.<name>.columns` -> `settings/analysis/*.yaml`; only the site-table summary declares its own in the
   spec). Load, site-table building and stages run on a worker thread (`AnalysisModel._start`, `poll` on the UI thread);
   the card builds the missing site tables itself first, one by one, so the first run has a progress line and a cancel
   point per table (WP4's `Analysis.run` reports nothing while `blocks()` builds them). `demo.py`: `DEMO["analysis"]`
   stages `examples/male` into `<demo folder>/male`; `analysis_demo()` -> (folder, `"quick"`). There is no legacy Qt
   baseline (a new surface); de/fr deferred (item 4).
   **Measure:** `pytest chisurf/plugins/quenching_estimator/test/test_emtk_analysis_card.py` (14 tests ~15 s, WP4's
   `FakeLibrary` stand-in: page switch, both sizes, tooltips, load by click, declared columns, run fills every tab
   without blocking the frame, write, cancel, every tour step resolves, settings round trip) + the demo test in
   `test_demo_and_guide.py`. **Real QA (2026-10-20, read by the implementer):** MalE demo + quick, workers = every CPU,
   site tables cached, another agent's full run on the same machine: **1117 s**; site tables from scratch ~10 s each
   (46). Screenshots (scratchpad, not shipped) of every tab at 1280x820, Fit at 1280x2600, narrow 800x600. The quick run
   puts the quench scale at its bounds (AF488 0.01 = lower, Atto655 10 = upper; stored 6.2 / 0.11): that is WP4's open
   acceptance on today's geometry, not the GUI. **Open:** (1) Run calls `core.inference.stages` in process, not WP5's
   `api.analyse(background=True)`: the API takes no site library (the tests' stand-in) and returns JSON over a transport,
   while the card reads `StageResult` objects; route through the facade once it does, and the run then appears in the
   job list. (2) Docs: done, item 1g. (3) The Data tab is long (scrolls);
   no colour bar on the hyper-posterior heatmap.
1g. **Done: WP7-guide (2026-10-20).** `docs/guides/111_quenching_analysis.md` (registered in `docs/guides/index.md`,
   linked from guide 80, `concepts/quenching_inference.md`, `gui/help.md` and `gui/analysis_help.md`): open → load → settings/stages
   → run → read the Fit/Water/Summary tabs → `csc quest analyse` + Python API (blocking and background) + RPC.
   Six figures `docs/guides/figures/111_quest_analysis_{data,running,sites,fit,water,summary}.png` are WP6's real quick-run shots;
   recipe `python docs/guides/screenshots/quest.py _grab_quest_analysis` (one call, all six; ~10 s per site table from
   scratch + ~20 min quick run), registered in `docs/references/figures.yaml`. **Open after WP4 lands:** (1) retake the six
   figures with that recipe (the fit/water/summary shots show today's quick run, scale at its bounds); (2) the guide quotes
   no fit numbers on purpose: it points at the concept's "MalE results" table, so update that table, not the guide.
   **Measure:** `pytest test/test_docs_okf.py test/test_docs_links.py`; the CLI/API snippets were run with
   `--set n_starts=2 --no-profile --workers 2` on cached tables (~3 min under load for stage B).
   **Resolved (4ceaad395):** `api.analyse` with workers > 1 from an unguarded *script* used to fail (spawn re-imported the script);
   __main__ now hides its `__file__`/`__spec__` while the workers start (subprocess test). Work items must not be functions defined in __main__.
2. **Done: WP2 (IMP.bff kernels, imp.bff `0b178903a`).** It unblocked WP3; the kernels and the voxel-frame fix are in
   imp.bff `okf/quest-site-kernels.md`.
3. **Open: owner questions to settle before WP4 is accepted** (findings from reading the notebook):
   (a) **The "key figure" does not show what its text claims in the stored run.** Stage B and
     Stage C both give a quench scale of 0.11 (0.08–0.15/0.16). The narrowing that cells 50/56
     promise is not there. The profile plot only draws Laplace-Gaussian samples (`profile()`),
     not a profile likelihood. A real profile, as in `it08/it10 *_profiles.csv`, is a WP4 option.
   (b) **Direct method vs random walk:** 2.59 ns vs 2.31 ± 0.03 ns (APO 233, slow 0.3, L 21.5).
     That passes the 0.35 ns tolerance, but it is a 12 % gap, and the text calls it "exact".
     WP3 must decide whether the IMP.bff closed-form `DynamicAccessibleVolume.update_occupancy`
     (Itô flux, p ∝ 1/D) is the same estimator as the prototype's `p ∝ 1/s`, and must record which
     one is used. **Answered by WP3 (item 1d):** most of the gap was the voxel-frame bug; in the grid frame direct
     2.832 vs walk 2.76 ± 0.10 ns (2.6 %). The site model uses the notebook's p ∝ ∏ s^(−n) in numpy.
   (c) **AF488 rms 0.62 ns vs median |dev| 0.047 ns.** Site 233 apo alone causes the gap
     (measured 1.339 ns, LOO z = 15.3). Cy3B has only 5 sites (10 lifetimes).
   (d) Cell 32's markdown says "16 searches", but the code runs `N_STARTS = 64`.
   (e) **AV width/grid conflict** (see the conflicts table): MalE uses W 0.5 / dg 0.5. The owner's 2026-10-11 "all use same defaults" sets W 4.5 / dg 0.9. **Decided 2026-10-20:** the notebook values are measured analysis settings (`settings/analysis/site_model.yaml`), and the generic defaults stay IMP.bff's.
4. **Blocked: German/French catalogues** of the new view.json are deferred to the i18n batch.
   Owner rule: no translation work in PRD-154 batches.
5. **Tried and reverted:** (in the prototype itself, do not re-port) the Brownian-walk *objective*
   (it01–it06) as the fit target. It does not equilibrate at slow factors ≤ 0.1 (it07 docstring), and the
   equilibrium ensemble replaced it **in the inverse fit**. The walk itself stays (owner decision 2026-10-20, see WP9).
   A single stickiness or a residue-count shielding term
   `exp(-α n)` (it11) was replaced by per-group stickiness (it08) and Shrake–Rupley exposure
   (it12). The Cauchy loss of it05 was replaced by the Student-t (ν = 3) search plus a Gaussian
   joint fit. The AF4_C2R linker (16.46 Å) was the wrong reagent; AF488 is A48_C1R, 20.4 Å (it10).
6. **Done: WP8 (prototype marked as migrated, 2026-10-20; quest `c798cb2` on `dev`, not pushed).**
   `~/dev/quest/prototype/MIGRATED.md` (commit table, one row per gap-matrix line + scripts, the rest of the quest repo,
   not-migrated list, Open list); a `# CHISURF-MIGRATED/TAKEN/SKIPPED/RECORD` block above the docstring of every `it*.py`
   and helper; 12 markdown cells in the notebook (index 0 + one per chapter, now at 10, 14, 21, 26, 29, 34, 39, 42, 53,
   60, 68). **Measure:** git diff of `c798cb2` is 342 insertions, 0 deletions; the before/after check gave 28 code cells
   identical in every field and all 60 original cells unchanged and in order. **Trap (fixed here):** the golden
   regenerator `test/baselines/make_male_prototype.py` addresses notebook cells by index, so the inserted notes would
   have stopped it ("the notebook changed"); `notebook_cells` now drops cells matching `MIGRATION_NOTE`, and its view
   equals the original 60 cells. The golden's recorded notebook sha256 changes on the next regeneration (no test reads it).
   **Open:** MIGRATED.md's "Open" list mirrors items 1e, 4 and 7 here; when one closes, update that list too. The MCMC
   check (cell 40) is declared (`fit_parameters.yaml: sampler_check`) but no code runs it (gap row 26).
7. **Done: WP9 (forward simulator, three ensembles, 2026-10-20).** `ensemble: "walk" | "equilibrium" | "pde"`
   (`core/ensembles.py`, project key + catalog entry + form combo; default `walk`, FRET only with it). **Walk:** walkers
   start from p ∝ 1/m (`core/av.py: simulate_walkers`, numpy, IMP.bff's walk rule; ~1000 walkers of 20–50 τ₀ per run,
   `ensembles.walk_segment`), panels read walker 0. **Equilibrium:** `site_table.equilibrium_lifetime` (WP3's closed
   form, `direct_lifetime` now calls it) on the walk's own maps. **PDE:** IMP.bff `GridDiffusionSolver(D0·m, b, w·b,
   k, dg, dt, "detailed_balance", False, w=1/m)`, `.lifetime()` (PCG) + `.donor_decay()` (Lanczos) for the photons;
   grids on the outer shell padded. **Measure:** `pytest chisurf/plugins/quenching_estimator/test/test_equilibrium_ensemble.py`
   (fast part ~10 s; `-m slow` runs the walk-vs-PDE check, 3 seeds × 3 slow factors, ~9 min; at 10 ps it gave +0.68 % / +0.50 % / +2.2 %, all inside 3 SE). MalE APO 95, AF488 table, τ₀ 4.2, D 7, dg 0.9,
   template walk (8 × 16 µs, 32 ps, 3 seeds): equilibrium 4.084 / 2.872 / 0.897 ns at slow 1 / 0.3 / 0.1 (monotone);
   PDE 3.637 / 2.494 / 0.890; walk 3.638 ± 0.007 / 2.487 ± 0.014 / 0.876 ± 0.008 (−1.6 %, 1.9 σ at slow 0.1, reported; 105-ns walkers); old uniform-start walk 3.646 / 2.634 / 2.179.
   PDE stationary = equilibrium to 1e-12, PDE D→0 = equilibrium to 1e-9. **Trap:** a short walk at slow 0.1 is few
   independent starts (400 ns, 1 block → 5 walkers), so QY can read 1.000 or 0.5 by luck — noise now, not bias; use `pde`
   for a donor-only number. **Moved:** baselines re-pinned (log 2026-10-20), `test_aa_specific_quenching`'s site pair
   (E96 "does not quench" was the stuck walker; at equilibrium QY 0.47 — now E21 0.289 vs E55 0.935). **Open:** IMP.bff's
   walk takes no start weight (the numpy walk moves there with a rebuild); PDE with FRET (an acceptor-averaged k_T in the
   sink) is not wired; de/fr text of `ensemble` waits for the i18n batch.
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
| `okf/references/known-issues.md`: walk does not equilibrate at slow 0.1 | **resolved by WP9** (walk starts from p(x); PDE ensemble) | WP9 |
| known-issue: IMP.bff C++ fps.json reader collapses a 3-radius AV to 1 radius | upstream, open in quest | WP2 re-checks it in imp.bff and files it there if still open |
| `handover.md`: `asa`/`spherePoints` → IMP (`DUP-05`) | **deleted by WP9** (the walk's ASA was computed and never read) | exposure is `probe_solvent_exposure` (site tables) |
| `okf/validation/2026-10-06-contact-distances.json` | receipt only | skip (its test is `test/test_quencher_distances.py`) |
| `data/*.xlsx` (untracked in quest) | missing | WP0 (CSV under `examples/male/`) |
| `okf/subsystems/quenching-model.md` § "Dye-specific kQ from amino-acid titrations" | describes an *older* method, see conflicts | the notebook wins; WP7 writes the current method |

# Conflicts: the notebook wins (owner precedence rule)

| topic | quest package / it-scripts / quest OKF | notebook (wins) | owner |
|---|---|---|---|
| Ensemble for τX | Brownian walk + photon race (`core/dye_diffusion.py`, it01–it06) | equilibrium ensemble p ∝ ∏ s_t^(−n_t), no walk (cell 22) | WP3 (analysis: `site_model.Site.weights`, done), WP9 (forward sim: equilibrium + walk from p(x) + PDE, done) |
| Stickiness | one `slow_factor` 0.1 for every residue in every dye preset (`settings/dye_repository.json`) | five chemical groups + common, ridge prior ln 10 | WP1 presets, WP4 |
| kq error model | σ = max(slope SE, leave-one-day-out jackknife, day-to-day 0.11 M⁻¹ + 7 %) (quest OKF quenching-model) | hierarchical closed-form posterior, day-to-day abs 0.01 M⁻¹ + rel 2 % | WP1 |
| Negative/weak kq | "negative or not above 2σ counts as no quenching" (OKF; it scripts; notebook `load_titrations` still computes the unused flag `counts`) | positive part only, no 2σ cut (cell 19) | WP1 |
| Cy3B brightening | Cy3B τ₀ freed (OKF "Findings") | τ₀ fixed at the free dye, + `dtau_shield·(1−e)` (cell 41); polarity brightening tested and rejected (quest `d3c5414`) | WP4 |
| Water shielding | `exp(−α n)` (it11), `e^γ` option (it12) | `kq_w,free · e`, zero parameters (cell 50) | WP4 |
| Robust loss | Cauchy (it05) | Student-t ν = 3 search + Gaussian joint fit | WP4 |
| Error bars | MCMC DE posteriors (notebook 2026-09-30, superseded) | Laplace on the joint fit; MCMC only as an optional check | WP4 |
| Linker | QuEst 21.5 Å for every dye (it02–it09, repository `Alexa488`/`AF488`) | A48_C1R 20.4, C3B_C2R 19.74, T65_C2R 20.12 Å | WP1 presets, WP2 kernel |
| AV width / grid | quest `bdcf3e8` + owner 2026-10-11 "all use same defaults": IMP.bff W 4.5 Å, dg 0.9 | MalE analysis: W 0.5 Å, dye radius 3.5 Å, grid 0.5 Å | **Decided 2026-10-20:** W 0.5 / dg 0.5 / R 3.5 are explicit analysis settings in `settings/analysis/site_model.yaml`; generic defaults stay IMP.bff's 4.5 / 0.9. **The AV itself is re-pinned to today's IMP.bff** (FPS-parity link search, allowed sphere, IMP radii × 0.84; bisected in imp.bff `okf/quest-site-kernels.md`, cannot be undone by argument) **and the corrected grid frame**; one exact-prototype regression on the shipped prototype volume keeps the port's arithmetic honest (WP3, item 1d). |
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

- **Status: done 2026-10-20** (chisurf commit in resume item 1c; mmfdb `16da3c3`).
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

- **Status: done 2026-10-20** (resume item 1d). The accept line below was written before the frame bug was found: the
  exact half holds on the prototype volume (shipped table bit for bit, all 82 golden rows `==`); the rebuilt-table and
  "2.59 ns" halves are re-pinned on today's geometry (106 992 voxels, direct 2.832 ns, walk 2.76 ± 0.10).
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

- **Theory (done 2026-10-20, resume item 1b):** `docs/concepts/quenching_inference.md`. It covers: Stern–Volmer and kq; the hierarchical day-to-day model
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

- **Status: done 2026-10-20** — see resume item 7.
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
  slow 0.3 value matches WP3's re-pinned 2.832 ns (`site_table.direct_lifetime`; the notebook's 2.59 was the old frame).
- **Deps:** WP3 (the site model's equilibrium code is reused, not duplicated). It does not touch WP5/WP6 files.

## WP7b: quest tutorials as examples

- **Status: done 2026-10-20** — five scripts (04 = notebook 03, 05 = notebook 04 on IMP.bff's lattice solver); see resume item 1b.

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
| 7b | `examples/0[1-5]_*.py`, `test/test_examples.py` (guide 80 sections go through WP7) | none |

`okf/log.md` is shared and is only edited through `python -m build_tools.dev_utils.safe_edit log`.
