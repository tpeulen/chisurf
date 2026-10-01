# All emtk ports with a Qt tool: faithful-replacement audit (2026-10-01)

Scope: every plugin whose manifest declares `entrypoints.emtk`, minus the ids already accepted or covered by the settings audit
(pch, region_mle, flc-2d, trace_browser, model_manager, user_editor, plot_settings, ai_settings, plugin_manager, tttr_lut_tools, boarding,
switch_user, fcs_channel_preset, style_manager, setup, setup_channel_definition). Method: the four checks of `settings-audit.md` /
`UPGRADE_BRIEF.md` (looks good, parity with Qt, works, tested), measured cheaply and mechanically. Empty/offline state only, hermetic
temp settings folders, `python -m test.gui.emtk_port_parity before|after|compare <id>` with a 120 s timeout; output in `/tmp`, not the repo.

## How to read the numbers (limits)

* **Qt LOC / emtk LOC**: line count of the file named by `entrypoints.gui` (the Qt tool class file only; thin tools that delegate to widgets elsewhere
  are understated) and of `entrypoints.emtk` (the app file only; the gui-folder total is not shown).
* **Tests**: `def test_` count in test files that exercise the emtk app (mention make_app/emtk/gui.app) AND live in the plugin folder, carry the plugin
  id in the file name, or import the plugin package. Written `own (all)`: *own* = files in the plugin folder or named after the id; *all* adds generic
  files (e.g. `test_native_factories.py`, `test_chiplot.py`, shared by several plugins), so *all* overstates. Heuristic grep, not a test run.
* **Controls before/after**: `control_inventory` of the Qt widget vs `emtk_inventory` of the emtk app. **Lost** is the raw `compare` count (no
  `deliberate.json` exists for these); **lost-text** (`lt`) drops purely numeric/symbol entries. Qt table/tree/list cell contents count as
  controls, so lost is inflated for table-heavy tools (e.g. `plugin_check`: the whole plugin table is "lost" although the emtk screenshot shows it).
  Treat lost as an upper bound, ordering signal only. A Qt side of 1 control is a custom canvas (games, chimol) and says nothing.
* **Verdict rules (heuristic, see below for the 10 viewed)**: *swap-candidate* = lost-text <= 5, no untooltipped control, Qt-free import OK, >= 5 own
  (or >= 15 total) tests. *port-incomplete* = stub/missing UI (screenshot), failed draw, or emtk has <35 % of the Qt controls with >= 25 lost-text.
  *upgrade* = everything else (an emtk app exists and works but has a measurable gap or too few tests). *emtk-only* = no Qt tool.
  None is final: a swap needs the populated-state side-by-side read that `settings-audit.md` requires; offline empty state hides data behaviour.
* Qt-free proof: all measured apps pass `qt_free` (the `qf` column is omitted). Untooltipped counts are in the reason text when non-zero.


## Counts

* swap-candidate: 27
* upgrade: 53
* port-incomplete: 7
* emtk-only: 6
* total: 93

## Table (sorted by priority: swap-candidates, upgrades cheapest gap first, port-incomplete biggest gap first, emtk-only)

| # | id | Qt LOC | emtk LOC | tests own (all) | controls before/after | lost (text) | verdict | reason |
|---|---|---|---|---|---|---|---|---|
| 1 | `chimol` | - | 192 | 500 (1797) | 1/1 | 1 (0) | swap-candidate | Qt side measures as one canvas; 500 chimol tests; needs hand compare |
| 2 | `code_editor` | 117 | 1855 | 68 (97) | 0/85 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 97 tests |
| 3 | `help` | 2062 | 1907 | 48 (114) | 0/44 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 114 tests |
| 4 | `globalview` | 13 | 14 | 26 (31) | 0/22 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 31 tests |
| 5 | `accurate_fret` | 248 | 494 | 20 (20) | 0/41 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 20 tests |
| 6 | `tttr_count_rate_analysis` | 141 | 365 | 18 (18) | 0/43 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 18 tests |
| 7 | `tttr_time_windows` | 260 | 252 | 17 (35) | 0/35 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 35 tests |
| 8 | `ndxplorer` | 277 | 170 | 16 (35) | 0/60 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 35 tests |
| 9 | `number_quest` | 305 | 254 | 14 (49) | 1/1 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 49 tests |
| 10 | `photon_table` | 80 | 96 | 14 (21) | 0/20 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 21 tests |
| 11 | `pong` | 238 | 270 | 13 (49) | 1/1 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 49 tests |
| 12 | `tetris` | 263 | 237 | 9 (49) | 1/1 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 49 tests |
| 13 | `traj_energy_calculator` | 95 | 260 | 9 (9) | 5/22 | 0 (0) | swap-candidate | 0 text labels unmatched, 9 tests |
| 14 | `kappa2_dist` | 239 | 453 | 8 (24) | 0/65 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 24 tests |
| 15 | `minesweeper` | 355 | 241 | 8 (8) | 1/1 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 8 tests |
| 16 | `pto_inspector` | 241 | 437 | 8 (8) | 15/33 | 3 (2) | swap-candidate | 2 text labels unmatched, 8 tests |
| 17 | `f_test` | 180 | 155 | 7 (20) | 14/31 | 2 (1) | swap-candidate | 1 text labels unmatched, 20 tests |
| 18 | `fret_calculator` | 102 | 574 | 7 (23) | 0/54 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 23 tests |
| 19 | `synthetic_decay` | 52 | 157 | 7 (7) | 37/59 | 7 (0) | swap-candidate | 0 text labels unmatched, 7 tests |
| 20 | `tttr_to_pto` | 124 | 220 | 6 (6) | 4/8 | 3 (1) | swap-candidate | 1 text labels unmatched, 6 tests |
| 21 | `burst_background` | 18 | 441 | 4 (63) | 1/28 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 63 tests |
| 22 | `vv_vh_anisotropy` | 23 | 205 | 4 (63) | 11/38 | 4 (3) | swap-candidate | 3 text labels unmatched, 63 tests |
| 23 | `burst_2cde` | 432 | 416 | 3 (69) | 2/40 | 1 (0) | swap-candidate | 0 text labels unmatched, 69 tests |
| 24 | `fcs-lfcs-sim` | 230 | 118 | 2 (117) | 14/20 | 4 (3) | swap-candidate | 3 text labels unmatched, 117 tests |
| 25 | `rics_precision` | 145 | 424 | 2 (18) | 0/49 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 18 tests |
| 26 | `burst_browser` | 17 | 575 | 1 (62) | 0/32 | 0 (0) | swap-candidate | Qt side is a single canvas (control diff not meaningful): needs a hand play-compare; 0 text labels unmatched, 62 tests |
| 27 | `calculators` | 182 | 144 | 0 (16) | 20/64 | 6 (1) | swap-candidate | 1 text labels unmatched, 16 tests |
| 28 | `burst_bva` | 580 | 546 | 7 (7) | 3/45 | 1 (0) | upgrade | 2 controls without tooltip; no *view.json |
| 29 | `burst_fusion` | 211 | 412 | 2 (2) | 0/71 | 0 (0) | upgrade | only 2 plugin-specific tests |
| 30 | `burst_gs` | 212 | 501 | 2 (2) | 0/80 | 0 (0) | upgrade | only 2 plugin-specific tests |
| 31 | `burst_irf_bg` | 124 | 423 | 2 (6) | 0/33 | 0 (0) | upgrade | only 2 plugin-specific tests |
| 32 | `lightpath_simulator` | 147 | 718 | 30 (109) | 0/87 | 0 (0) | upgrade | 6 controls without tooltip; no *view.json |
| 33 | `phasor_calculator` | 72 | 436 | 5 (5) | 0/58 | 0 (0) | upgrade | 2 controls without tooltip |
| 34 | `project_browser` | 599 | 524 | 4 (4) | 16/24 | 0 (0) | upgrade | only 4 plugin-specific tests; no *view.json |
| 35 | `psf_calculator` | 262 | 213 | 0 (16) | - | - | upgrade | parity tool failed: Qt before capture fails (Qt tool needs 3-D volume renderer of emtk chiplot backend) |
| 36 | `traj_energy` | 95 | 260 | 0 (0) | 5/22 | 0 (0) | upgrade | only 0 plugin-specific tests; no *view.json |
| 37 | `traj_save_topology` | 67 | 59 | 2 (2) | 3/7 | 0 (0) | upgrade | only 2 plugin-specific tests |
| 38 | `traj_align` | 81 | 56 | 0 (0) | 6/10 | 1 (1) | upgrade | only 0 plugin-specific tests |
| 39 | `traj_rotate_translate` | 99 | 73 | 0 (0) | 5/24 | 2 (2) | upgrade | only 0 plugin-specific tests |
| 40 | `traj_remove_clashes` | 83 | 59 | 0 (0) | 7/13 | 3 (3) | upgrade | only 0 plugin-specific tests |
| 41 | `traj_join` | 98 | 68 | 0 (0) | 11/11 | 5 (5) | upgrade | only 0 plugin-specific tests |
| 42 | `microtime_shifter` | 924 | 883 | 11 (19) | 15/39 | 6 (6) | upgrade | 6 Qt labels unmatched (partly table cells); no *view.json |
| 43 | `traj_convert` | 126 | 63 | 0 (0) | 17/19 | 7 (6) | upgrade | 6 Qt labels unmatched (partly table cells); only 0 plugin-specific tests |
| 44 | `lltf` | 891 | 354 | 4 (4) | 17/30 | 9 (8) | upgrade | 8 Qt labels unmatched (partly table cells); only 4 plugin-specific tests; 2 controls without tooltip; no *view.json |
| 45 | `traj_fret` | 127 | 250 | 8 (8) | 14/20 | 10 (9) | upgrade | 9 Qt labels unmatched (partly table cells) |
| 46 | `filetools` | 58 | 278 | 7 (7) | 24/39 | 16 (10) | upgrade | 10 Qt labels unmatched (partly table cells); no *view.json |
| 47 | `img_calibration` | 109 | 332 | 5 (5) | 16/24 | 11 (10) | upgrade | 10 Qt labels unmatched (partly table cells) |
| 48 | `games` | 27 | 148 | 49 (49) | 20/18 | 15 (11) | upgrade | 11 Qt labels unmatched (partly table cells); no *view.json |
| 49 | `irf_estimator` | 990 | 254 | 8 (8) | 21/44 | 13 (12) | upgrade | 12 Qt labels unmatched (partly table cells); no *view.json |
| 50 | `fcs_calculator` | 757 | 153 | 0 (16) | 31/37 | 14 (13) | upgrade | 13 Qt labels unmatched (partly table cells); only 0 plugin-specific tests |
| 51 | `fcs_merger` | 62 | 333 | 5 (16) | 17/33 | 14 (13) | upgrade | 13 Qt labels unmatched (partly table cells); no *view.json |
| 52 | `hydropro` | 386 | 243 | 6 (72) | 37/35 | 17 (13) | upgrade | 13 Qt labels unmatched (partly table cells) |
| 53 | `tr_anisotropy` | 101 | 420 | 5 (64) | 46/24 | 38 (16) | upgrade | 16 Qt labels unmatched (partly table cells) |
| 54 | `batch_analysis` | 80 | 56 | 3 (3) | 26/18 | 23 (17) | upgrade | 17 Qt labels unmatched (partly table cells); only 3 plugin-specific tests |
| 55 | `wizards` | 168 | 76 | 2 (2) | 48/28 | 38 (17) | upgrade | 17 Qt labels unmatched (partly table cells); only 2 plugin-specific tests; no *view.json |
| 56 | `psf_determination` | 60 | 345 | 8 (15) | 44/50 | 27 (20) | upgrade | 20 Qt labels unmatched (partly table cells) |
| 57 | `ptu_alex_creator` | 53 | 445 | 4 (4) | 49/39 | 36 (20) | upgrade | 20 Qt labels unmatched (partly table cells); only 4 plugin-specific tests |
| 58 | `vv_vh_g_factor` | 1094 | 494 | 5 (14) | 23/62 | 22 (20) | upgrade | 20 Qt labels unmatched (partly table cells); no *view.json |
| 59 | `hmm` | 107 | 100 | 2 (2) | 31/18 | 25 (21) | upgrade | 21 Qt labels unmatched (partly table cells); only 2 plugin-specific tests |
| 60 | `img_pixel_intensity` | 23 | 429 | 6 (6) | 35/18 | 32 (21) | upgrade | 21 Qt labels unmatched (partly table cells) |
| 61 | `burst_fcs_correlator` | 448 | 375 | 2 (4) | 24/86 | 22 (22) | upgrade | 22 Qt labels unmatched (partly table cells); only 2 plugin-specific tests |
| 62 | `lifetime_analysis` | 112 | 177 | 1 (1) | 40/51 | 26 (22) | upgrade | 22 Qt labels unmatched (partly table cells); only 1 plugin-specific tests; no *view.json |
| 63 | `fcs_saturation` | 1021 | 252 | 0 (16) | 84/89 | 60 (23) | upgrade | 23 Qt labels unmatched (partly table cells); only 0 plugin-specific tests |
| 64 | `img_pixel_micro_time` | 23 | 496 | 4 (4) | 36/30 | 33 (23) | upgrade | 23 Qt labels unmatched (partly table cells); only 4 plugin-specific tests |
| 65 | `img_pixel_phasor` | 60 | 477 | 6 (6) | 46/31 | 41 (31) | upgrade | 31 Qt labels unmatched (partly table cells); 2 controls without tooltip |
| 66 | `tttr_toolbox` | 49 | 323 | 6 (6) | 68/48 | 48 (31) | upgrade | 31 Qt labels unmatched (partly table cells); no *view.json |
| 67 | `clsm_generator` | 109 | 414 | 8 (8) | 46/18 | 43 (33) | upgrade | 33 Qt labels unmatched (partly table cells) |
| 68 | `img_pixel_mle` | 35 | 516 | 5 (5) | 71/55 | 45 (34) | upgrade | 34 Qt labels unmatched (partly table cells) |
| 69 | `maxent_decay` | 833 | 627 | 8 (67) | 44/68 | 37 (34) | upgrade | 34 Qt labels unmatched (partly table cells); no *view.json |
| 70 | `clsm` | 108 | 542 | 5 (5) | 70/74 | 42 (36) | upgrade | 36 Qt labels unmatched (partly table cells) |
| 71 | `fcs_filter_calculator` | 3650 | 1097 | 11 (70) | 60/70 | 50 (37) | upgrade | 37 Qt labels unmatched (partly table cells) |
| 72 | `traj_tools` | 124 | 189 | 7 (7) | 53/20 | 45 (42) | upgrade | 42 Qt labels unmatched (partly table cells); no *view.json |
| 73 | `spot_finder` | 106 | 476 | 7 (7) | 79/56 | 53 (43) | upgrade | 43 Qt labels unmatched (partly table cells) |
| 74 | `img_coloc` | 191 | 500 | 7 (7) | 86/45 | 65 (54) | upgrade | 54 Qt labels unmatched (partly table cells); screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 75 | `img_pixel_nb` | 90 | 501 | 7 (7) | 85/37 | 73 (60) | upgrade | 60 Qt labels unmatched (partly table cells); 6 controls without tooltip; screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 76 | `microtime_histogram` | 1692 | 553 | 9 (68) | 76/69 | 69 (60) | upgrade | 60 Qt labels unmatched (partly table cells); no *view.json; screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 77 | `tttr_audifier` | 51 | 582 | 11 (11) | 115/38 | 107 (82) | upgrade | 82 Qt labels unmatched (partly table cells); screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 78 | `fret_line` | 773 | 636 | 0 (16) | 161/95 | 133 (85) | upgrade | 85 Qt labels unmatched (partly table cells); only 0 plugin-specific tests; 1 controls without tooltip; no *view.json; screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 79 | `imaging_tools` | 839 | 501 | 4 (4) | 158/42 | 137 (105) | upgrade | 105 Qt labels unmatched (partly table cells); only 4 plugin-specific tests; no *view.json; screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 80 | `plugin_check` | 489 | 141 | 5 (5) | 169/196 | 152 (152) | upgrade | 152 Qt labels unmatched (partly table cells); no *view.json; screenshot viewed: app looks complete, lost count is mostly Qt table/tree cell text |
| 81 | `tttr_image_browser` | 283 | 336 | 0 (5) | 121/22 | 117 (87) | port-incomplete | screenshot opens on detector setup only; 22 vs 121 Qt controls |
| 82 | `structure_tools` | 156 | 194 | 7 (66) | 73/11 | 71 (55) | port-incomplete | screenshot: "Native version pending" stub for 4 of 6 hub tools |
| 83 | `img_tracking` | 174 | 70 | 2 (92) | 66/9 | 64 (52) | port-incomplete | screenshot: 3 controls (stack, simulate, Track); Qt has the full tracking workflow |
| 84 | `img_frc` | 142 | 69 | 2 (92) | 58/10 | 55 (44) | port-incomplete | thin app (69 LOC), 44 of 58 Qt labels not found |
| 85 | `img_drift` | 164 | 100 | 2 (92) | 48/12 | 46 (35) | port-incomplete | thin app (100 LOC vs Qt 164), 35 of 48 Qt labels not found |
| 86 | `img_flow` | 160 | 97 | 0 (92) | 35/14 | 31 (26) | port-incomplete | thin app (97 LOC), 26 of 35 Qt labels not found |
| 87 | `breakout` | 187 | 286 | 0 (49) | - | - | port-incomplete | after draw does not finish within 120 s (game loop in draw?) |
| 88 | `about` | - | 51 | 2 (7) | - | - | emtk-only | no entrypoints.gui |
| 89 | `bid_to_analysis` | - | 339 | 5 (5) | - | - | emtk-only | no entrypoints.gui |
| 90 | `menu_switch` | - | 44 | 2 (607) | - | - | emtk-only | no entrypoints.gui |
| 91 | `spectra_downloader` | 24 | 441 | 12 (12) | - | - | emtk-only | entrypoints.gui already resolves to the emtk SpectraApp (no Qt tool; before capture fails: no resize) |
| 92 | `tttr_header_edit` | - | 120 | 12 (12) | - | - | emtk-only | no entrypoints.gui |
| 93 | `tttr_splitter` | - | 219 | 11 (18) | - | - | emtk-only | no entrypoints.gui |

## Screenshots viewed (the 10 worst by raw lost count; after_1200x800 only)

* `plugin_check`: complete (startup-check table with Status/Source/Depends on/Error, details dock). The 152 "lost" are the Qt table's cell text. Looks plain but at parity in structure: upgrade only for tests (5).
* `imaging_tools`: complete hub (13 workflow destinations with search, Previous/Next/Help, detector setup + image browser). Qt "lost" are mostly tree/cell text. Upgrade: 4 plugin tests.
* `tttr_image_browser`: opens on the shared detector-setup editor; the browser's actual controls (folder, rating, mosaic) are not visible; 22 vs 121 controls. **port-incomplete**.
* `fret_line`: rich (mixture, sweep, live model editor, two plots). Looks like a faithful port; lost is Qt parameter-table text. Upgrade: no plugin tests (16 generic).
* `tttr_audifier`: layout plausible (detector setup, waterfall/audio transport, colours/notes). 38 vs 115 controls: per-detector rows are only shown with data. Upgrade: populated-state check.
* `microtime_histogram`: complete (detector definition, files/options, decay plot). Upgrade: populated-state check, no *view.json.
* `img_pixel_nb`: complete (N&B settings, 8 result tabs). Upgrade: populated-state check.
* `structure_tools`: **stub**: "Native version pending" for FPS JSON Editor, Docking, QuEst, ... **port-incomplete**.
* `img_coloc`: complete (toolbar, analysis settings, 7+ result tabs). Upgrade.
* `img_tracking`: **bare**: three controls and a sentence; none of the Qt workflow's tabs/results. **port-incomplete** (same family: `img_drift`, `img_flow`, `img_frc` are 69-100 LOC apps and share this shape).


## Recommended order for upgrade cycles

1. **Flip the swap-candidates first** (cheap, no new UI): for each, read the Qt/emtk pair with data (populated state), confirm the four checks and
   write the report. Games and chimol have a canvas Qt side, so compare by playing/loading. 27 plugins; do the ones with the most own tests first (top of the table).
2. **Upgrade cycles, cheapest gap first** (the table order of the *upgrade* rows): burst family (`burst_bva`, `burst_fusion`, `burst_gs`, `burst_irf_bg`: tests +
   tooltips), then the `traj_*` family (they share one test file; add per-plugin tests, one cycle for the family), then `phasor_calculator`, `project_browser`,
   `lightpath_simulator` (tooltips), then the table-heavy tools with gaps (`lltf`, `filetools`, `microtime_shifter`, `img_calibration`, `traj_fret`).
3. **Imaging hub family** (`imaging_tools`, `img_pixel_*`, `img_coloc`, `spot_finder`, `clsm*`, `psf_determination`): one shared cycle for the Qt
   control inventory vs the hub's pages, because they share the shell; then per-tool populated-state checks.
4. **Port-incomplete last, as real ports (PRD-153 full cycle each)**: `img_tracking` + `img_drift` + `img_flow` + `img_frc` together (one shared result-view
   pattern), `tttr_image_browser`, `structure_tools` (needs the four sub-tools ported; hub only is a stub), `traj_tools`, `breakout` (fix the non-terminating draw first).
5. **emtk-only plugins**: only tests/QA, no parity question; see list below.

## Top 15 upgrade priorities (upgrade verdict, cheapest gap first)

1. `burst_bva`: 2 controls without tooltip; no *view.json
2. `burst_fusion`: only 2 plugin-specific tests
3. `burst_gs`: only 2 plugin-specific tests
4. `burst_irf_bg`: only 2 plugin-specific tests
5. `lightpath_simulator`: 6 controls without tooltip; no *view.json
6. `phasor_calculator`: 2 controls without tooltip
7. `project_browser`: only 4 plugin-specific tests; no *view.json
8. `psf_calculator`: parity tool failed: Qt before capture fails (Qt tool needs 3-D volume renderer of emtk chiplot backend)
9. `traj_energy`: only 0 plugin-specific tests; no *view.json
10. `traj_save_topology`: only 2 plugin-specific tests
11. `traj_align`: only 0 plugin-specific tests
12. `traj_rotate_translate`: only 0 plugin-specific tests
13. `traj_remove_clashes`: only 0 plugin-specific tests
14. `traj_join`: only 0 plugin-specific tests
15. `microtime_shifter`: 6 Qt labels unmatched (partly table cells); no *view.json

## emtk-only (no Qt tool to compare against)

* `about`: emtk 51 LOC, tests own 2 (all 7); no entrypoints.gui
* `bid_to_analysis`: emtk 339 LOC, tests own 5 (all 5); no entrypoints.gui
* `menu_switch`: emtk 44 LOC, tests own 2 (all 607); no entrypoints.gui
* `spectra_downloader`: emtk 441 LOC, tests own 12 (all 12); entrypoints.gui already resolves to the emtk SpectraApp (no Qt tool; before capture fails: no resize)
* `tttr_header_edit`: emtk 120 LOC, tests own 12 (all 12); no entrypoints.gui
* `tttr_splitter`: emtk 219 LOC, tests own 11 (all 18); no entrypoints.gui
