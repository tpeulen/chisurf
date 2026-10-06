# Burst and large-tool survey (card S, second pass 2026-10-02)

## Where to pick this up (T-20261006-ALEXHUB, done 2026-10-06)

**The ALEX Suite is native, as a simple Next workflow.** Cards **AS1-AS4 done**: `a577affef` (AS1: Qt-free
`alex_suite/gui/alternation_model.py`, `demo.py`), `4f6add194` (AS3: `gui/export_model.py`), `5d54f60de` (AS2:
`gui/step_apps.py`, titration on `TitrationViewModel` with emtk file choosers), `5912033fa` (AS4: `gui/native.py`
`AlexHubApp(BurstAnalysisHubApp)`, manifest `entrypoints.emtk`, hub-membership extractor on its `STEPS`), `4e51d24fe`
(evidence, guide 66 "The simple workflow"). Evidence in `alex_suite/` (`after_steps/`, `compare.json` lost 0,
`deliberate.json`); report text in the T-20261006-ALEXHUB hand-back (subagents may not write REPORT.md).

Measured, and how to re-derive it: `alex_suite/demo.py` writes a seeded µs-ALEX stream (period 8000 ticks, donor 0 /
acceptor 1, micro-time 0); with Load demo data and Next presses only the hub converts it (period 8000, gates 235-3685 /
4235-7685, contrast ~15000x), the burst search finds **462 bursts** in the container, Accurate FRET calibrates
(alpha 0.009, delta 0.067 vs the planted 0.06 direct excitation, gamma 0.94, beta 1.10) and ndX shows two FRET populations
at S ~ 0.5 (`alex_suite/tests/test_emtk_native_hub.py::test_next_alone_takes_the_demo_from_files_to_an_es_histogram`, 11 s).
On the PIE fixture the alternation step leaves the data alone and the search still finds **198 bursts**.
**Traps:** a status line wider than its room becomes one hovered item over Back / >> / Next and they stop taking clicks
(`ToolHubApp` defect, worked around in `AlexHubApp.render` by `_fit`; known-issues); a burst run inside a `.pto` is not a
file, so tools that test `is_file()`/`exists()` refuse it (Accurate FRET and the browser fixed in `5912033fa`); ndX opens
on its last-used axes, the hub sets E/S itself once the load is in.

Open, in order:
1. Retire the Qt shells: `alex_suite/gui/tool.py` (+ `alternation.py`, `titration.py`, `legacy_export_panel.py`,
   `tests/test_workflow_shape.py`, `tests/test_ndx_step.py`) and the three-tab `AlexSuiteApp` in `gui/app.py`, together with
   Burst Analysis's (item 4 below). `gui/app.py` and `tests/test_emtk_clicks.py` carry the typed-field lane's uncommitted
   edits and `tests/test_emtk_typed_fields.py` drives `AlexSuiteApp`: retire it with that lane, not over it.
2. The help window shows markdown emphasis raw (`**Next**`): `chisurf/emtk/help_guide.py` has no inline emphasis.
3. The setup step's own button reads "Proceed to Data Selection" in the ALEX rail (shared setup app; a label attribute as
   done for the data step would fix it).

## Where to pick this up (T-20261005-BURSTEMTK, done 2026-10-06)

**Burst Analysis and Burst Selection are native.** Card status: **BS0-BS6 done** (`9c39340c4`, `ee14af4bd`, `ddd07e123`),
**MLE split by H2MM state done** (`a5981e47c`, test `burst_mle_analysis/tests/test_engine_state_split.py`), **BA3/BA4 done**
(`966163d53`), **BA0-BA2 done**: `burst_analysis/gui/native.py` on `chisurf/emtk/tool_hub.py`, manifest `entrypoints.emtk`,
hub-membership extractor on the native `STEPS` (`77337cfd6`, `f6a98f22d`, `6eca22141`, docs `351987e61`). Report text:
the T-20261005-BURSTEMTK final message (the subagent environment refused writing `burst_analysis/REPORT.md`; evidence
PNGs, `after.json`, `compare.json` (exit 0) and `deliberate.json` are in `burst_analysis/`).

Measured, and how to re-derive it: on copies of `burst_selection/tests/data/bh_spc132_sm_dna/m000.spc,m001.spc` with the
stored setup `probe` (green 0,1 / red 8,9, SPC-130) the hub's Next runs Burst Selection to **198 bursts** (the Qt tool's
number), folder `sliding_window_All 0.1500#60`, and every later step receives its input
(`burst_analysis/tests/test_emtk_native_hub.py::test_the_workflow_hands_every_step_its_input`). On all ten files: 1130
bursts, 71 in `m000.spc` (guide 27's figure). **Trap:** the search writes beside the source and into a `.pto`; always copy
the fixture first (the untracked `burstwise_All 0.1000#15/{bh4,h2mm}/` folders in the tree are such run outputs: leave
them, do not commit them).

Open, in order:

1. ~~**`alex_suite` shell (AS4).**~~ Done 2026-10-06 (T-20261006-ALEXHUB, section above): `AlexHubApp(BurstAnalysisHubApp)`
   in `alex_suite/gui/native.py`; `test_hub_membership.py` reads its `STEPS`.
2. **ToolHubApp limits** the hub inherits (fixed rail, clips `7. Burst segmentation (H2MM)` at 800 px; the header repeats
   the rail badge): an additive option in `chisurf/emtk/tool_hub.py` (collapsible rail, header display name). Recorded in
   `okf/references/known-issues.md`.
3. **Five red click tests at HEAD** in `burst_gs` (wheel zoom, two tour walks) and `burst_fcs_correlator` (guide/help,
   tour walk), shown on a worktree of HEAD; their files carry other lanes' edits. known-issues has the list.
4. **Retire the Qt shells** once AS4 lands: `burst_analysis/gui/{tool.py,app.py}` (app.py still holds the 2026-10-03 B2
   tooltip edits, snapshotted in `burst_analysis/pre-upgrade/`, never committed) and the Qt Burst Selection with its three
   recorded defects (known-issues, top Burst Selection entry).

Deliberate differences of the hub (from `deliberate.json` and the report): no rail collapse; `[opt]` badge dropped (the name
says optional); `Next ▶` / `⏩ Run` / `? Help` → `Next` / `>>` / `Help` + `Tool help`; the status line is a live
summary; the setup is not published to the `detector_setups.*` RPC store (the native editors read the setups store);
2CDE, Burst FCS and GS now get the setup's channels (the Qt shell handed only folders, so they ran on 0,8 / 1,9
defaults); accurate FRET's column hints prefer `Number of Photons (<detector>)` (both hosts mapped `First Photon (green)`
before).

Script trap: a probe run from the scratchpad cannot `import test.gui...` (stdlib `test` wins) — put the repo first on
`sys.path` and `sys.modules.pop("test")` before importing.


Plugins: `burst_selection`, `burst_mle_analysis`, `burst_analysis`, `burst_h2mm`, `burst_ebfret`, `alex_suite`, `mfd_prepare`,
`fret_docking`, `fps_json_editor`, `acq`, `mmfdb_admin` (and a closing note on `trace_browser`, which the first pass covered).
Read-only: no code changed, no analysis run, no test run. Tools used: `wc -l`, `grep`, `git status`/`git diff HEAD`/`git ls-tree`,
reading the code and manifests. "Qt LOC" counts files that import `qtpy`/`pyqtgraph`/`chisurf.gui` widgets (`grep -c -E
'qtpy|PyQt|pyqtgraph|QtWidgets|QtCore'` per file, then `wc -l`); 0 hits means Qt-free. Per-stage Qt LOC are summed from `def` line ranges
of the Qt file and are approximate (about +-10 %). Companion to [`wave3-plan.md`](wave3-plan.md); replaces the 2026-10-01 survey (its
content is kept below, updated where the tree moved).

## 0. What changed since the first pass, and what is still open

* **Decisions the first pass left open are now answered.**
  AutoForm/emtk specs *do* support conditional sections: `emtk/view_form.py` `_hidden()` honours `visible: false` and
  `hidden_when: {target, attr, ...}` on a section, so the algorithm-dependent filter groups of `burst_selection` are one spec with
  `hidden_when` on the algorithm field (BS2). `chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups` and `setup_client`
  have 0 Qt hits, and the package `__init__.py` files (`tttr_channeldefinition`, `wizard`) have 0 Qt hits, so importing them is Qt-free.
  `chisurf.gui.widgets.tools.emtk_help_guide` is now a 5-line alias for `chisurf.emtk.help_guide` (see B1).
* **A shared emtk MMFDB dataset picker exists**: `chisurf/emtk/dataset_picker.py` (`DatasetPicker`, `DatasetSelection`,
  `kinds`/`formats`/`scope`, resolves a local path). It is used by `tttr_time_windows`, `tttr_splitter`, `microtime_histogram`, `tttr_lut_tools`,
  `ptu_alex_creator`, `tttr_microtime_shifter`, `tttr_count_rate_analysis`. It removes the "needs an emtk sample picker" item of BS6 and BA3
  for **dataset** selection; the BS6 *output-sample* picker (`show_sample_picker_dialog`) is a different question (check that
  `kinds` can name samples, else extend the helper with tests).
* **The shared one-page detector editor exists**: `chisurf/emtk/channel_definition.py` (`ChannelDefinitionWidget`, 1244 lines, one scroll
  like the Qt page: setup row, TTTR reading, PIE windows, Detectors with polarization switch, LUT handling, optical setup, decay preview, floating
  dialogs via `draw_dialogs(frame)`), backed by `chisurf/core/setup_channel_definition.py` (`ChannelDefinition`, 335 lines, Qt-free: setups
  store, save/rename/delete, LUT, G factor) and `chisurf/emtk/channel_setup_bar.py` (257). Commit `2773e29d6`. Embedding templates:
  `burst/bid_to_analysis/gui/app.py` (docks it as a "Detector setup" dock, takes `model=`; `get_settings()`), `burst_fcs_correlator/gui/app.py`,
  `burst_background/gui/controller.py`, `accurate_fret/gui/controller.py`, `trace_browser/gui/app.py`.
* **The first pass called `fret_docking` F1-F3 open and `fps_json_editor` "own design"; both now have native cards** inside
  `structure_tools` (commit `2f41ebf97`, repaired by `39c998740`): `cards/docking.py` + `docking_model.py` (draws the Qt tool's own
  `fret/gui/fret_dock.view.json`, structures `data_table`, results table, score plot, 3D structure via `implot3d`) and
  `cards/fps_json.py` + `fps_model.py` + `views/fps_*.view.json` (Positions, Distances, FlexFit, JSON, 3D). F3's open question
  ("child of ChiMol or link") was answered by drawing the structure natively with `implot3d`. See sections 8 and 9.
* **`trace_browser` is no longer a candidate**: T0, T1 (reports in `okf/plugins/emtk-ports/trace_browser/`), and commits `adcb725e3`,
  `7554500f5`, `12ead5009` (T4 manifest entry, docs, T5 host adapter) landed; the app imports the shared editor. Only an uncommitted edit to
  `test/test_emtk_trace_browser_t1.py` is pending.

## 1. Blockers and hazards (read before dispatching)

| id | blocker | effect | who decides |
|---|---|---|---|
| B1 | **`chisurf/emtk/` is mostly untracked.** `git ls-tree HEAD chisurf/emtk` lists only `channel_definition.py` and `channel_setup_bar.py`; `git status` shows both as **staged deletions** (`D `) next to `?? chisurf/emtk/` (22 files on disk: `jobs.py`, `dataset_picker.py`, `help_guide.py`, `datasets.py`, `optical_configuration.py`, ...), plus staged deletion of `chisurf/core/setup_channel_definition.py` (also `??` on disk). The board says the editor "is being reworked". | Every card imports `chisurf.emtk.{jobs,help_guide,dataset_picker,channel_definition}`; none of it reproduces from HEAD, and a stray `git commit` (no pathspec) by anyone would delete the shared editor from HEAD. Cards must commit by explicit path and cannot rely on a clean checkout until the owner of that stream commits `chisurf/emtk/` and `core/setup_channel_definition.py`. | owner of the emtk stream |
| B2 | **Pending cosmetic edits in every burst `gui/app.py`** (tooltips via `im.set_item_tooltip`, `remember` moved into `TourTarget`, import of `TourTarget`): `burst_selection` (+122/-8), `burst_mle_analysis` (+21), `burst_analysis` (`app.py`, `data_selection_app.py`, `tool.py`), `burst_h2mm` (also a dock split 0.62 to 0.72, `_next_row_if_clipped`), `burst_ebfret` (+11), `alex_suite` (`app.py` +93, `tool.py` +2 `INITIAL_ROLE`), `mfd_prepare` (+12), also `bid_to_analysis` and `mmfdb_admin/__init__.py` (lazy `MMFDBWidget` import). All depend on the untracked `chisurf.emtk.help_guide.TourTarget` (B1). | The wave-3 rule "`git status --short -- <plugin dir>` must be empty" blocks every card until these are committed or dropped. They are small and mechanical: one commit per plugin by the owner of that stream unblocks them. | owner of the tooltip / TourTarget stream |
| B3 | **`burst_analysis/gui/setup_selection_app.py`: 2078 uncommitted insertions** (588 lines at HEAD, 2178 in the tree) that grew the hand-written detector/PIE editor into a full duplicate of the shared editor, with JSON editor window, region selector, Save/Rename/Delete modals. | Card BA4 deletes this file's content in favour of `ChannelDefinitionWidget`. That discards another stream's uncommitted work: **needs the owner's explicit yes** (copy it to `okf/plugins/emtk-ports/burst_analysis/pre-upgrade/` first, as `UPGRADE_BRIEF.md` prescribes). Do not touch it before then. | owner of the burst_analysis stream |
| B4 | `structure_tools/cards/shell.py` and `test/test_cards.py` are `MM` (staged and unstaged edits). | FD1 / FJ1 (below) reuse the cards; wait until those are committed. | EMTKUP5 stream |
| B5 | Fixtures outside the repo: `burst_mle_analysis/tests/test_mle_gui_end_to_end.py` hard-codes `/Users/tpeulen/dev/tttr-data/bh/bh_spc132_sm_dna/sliding_window_All 0.1500#60_3/...` (skipped when absent; the folder exists on this machine); `burst_selection/tests/test_filter_ui_elements.py` uses `TTTRLIB_DATA` default under `~/dev/tttr-data`; `alex_suite/tests/test_alternation.py:210` reads `~/dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n.sm` (the only mu-s-ALEX raw file; no in-repo ALEX fixture). `test/data/tttr/BH/132/BH_SPC132.pto` is untracked. | A card that must prove "same numbers as the Qt tool" for MLE or ALEX conversion can only do so on this machine. Use the in-repo fixtures below for everything else. | reviewer |

In-repo burst fixtures (tracked): `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/` (25 files: `m000..m007.spc` raw BH
SPC-132, `burstwise_All 0.1000#15/bi4_bur/m000..m009.bur`, `burst_analysis_handoff/{burst_analysis_handoff.json,bi4_bur/m000.bur}`; the handoff
JSON no longer carries `channel_settings`, supply the detector definition as `test_mle_gui_end_to_end.py` does), `test/data/tttr/BH/{132,630_256,830}`,
`burst_ebfret/tests/data/` (SMD/session/octave fixtures, `simulated-K04-N350`), `burst_h2mm/examples/generate_example_data.py` (labelled simulation, may be
used as a demo only behind an explicit Demo action). **No IRF or background files for the MLE are tracked**; the MLE cards use the BH `.bur` plus
`CHANNEL_SETTINGS` and set IRF from the decay.

## 2. Summary

| plugin | stages walked | Qt LOC | Qt-free logic | emtk today | dirty tree | cards | size |
|---|---|---|---|---|---|---|---|
| burst_selection | 5: files and setup; filter settings; run; diagnostics and feature plots; output | 5.9k (`gui/tool.py` 4176, `legacy/burst_selector.py` 983, `gui.ui` 378, `sections.py` 195, `gmm_settings_dialog.py` 132) | `api/` 3.0k, `backend/` 386, `gui/{adapter,client,display_view_model,timeline}.py` 1.4k | `gui/app.py` 2166, hosted by the Qt tool, reads 19 tool attributes and the Qt wizard | yes (B2) | BS0-BS6 (7) | L total |
| burst_mle_analysis | 4: detector; files; parameters; fit and plots (+ outputs) | 5.7k (`wizard.py` 5667) + `utils.py` 749 | `_mp_worker.py` 421, `core/export.py` 212, `backend/services.py` 80; **the science sits in the Qt class** | `gui/app.py` 422: preview mock, **invented data**, used only by `burst_analysis` | yes (B2) | ML-X, ML0-ML5 (7) | L total |
| burst_analysis | 14-step shell; 2 own steps | 1.9k `gui/tool.py` | `api/workflow.py` 1421 (not used by the GUI) | shell `app.py` 694, `data_selection_app.py` 391, `setup_selection_app.py` 2178 (duplicate editor) | yes (B2, B3) | BA0-BA4 (5) | L total |
| burst_h2mm | 4: folder; settings; channels; run and results (+ bootstrap, LL scan) | 2.0k `gui/tool.py` | `core/` 3.8k, `backend/services.py` 680, `api/`, `gui/client.py` | `gui/app.py` 532 over the Qt tool, **invented data** | yes (B2) | H-X, H0-H5 (7) | L total |
| burst_ebfret | 1 window, 10 panels; all emtk | 140 `gui/tool.py` (a `ControlHost` wrapper) | everything else (`core/` 4.2k, `io.py` 1659, `backend/`) | `gui/app.py` 827 + `controls.py` + `dialogs.py` + 8 `*.view.json`; takes a **client, not the tool** | yes (B2, 11 lines) | E1 (1) | S |
| alex_suite | 7 pipeline steps + 4 side tools; 3 own emtk apps | 1.3k (`tool.py` 547, `alternation.py` 588, `titration.py` 95, `legacy_export_panel.py` 114) | `api/` 1.2k (`titration.py`, `histograms.py`, `convert.py`, `legacy_export.py`), `gui/titration_view_model.py` 366 | `gui/app.py` 700: `LegacyExportApp`, `TitrationApp`, `AlexAlternationApp`, each driven by a Qt panel | yes (B2) | AS1-AS4 (4) | M total |
| mfd_prepare | 1 (folder, Prepare, report) | 85 `gui/tool.py` | `api/` 272, `backend/services.py` 36 | `gui/app.py` 161 over the tool (2 attributes) | yes (B2, 12 lines) | MP1 (1) | S |
| fret_docking | tool: form + PDB list + run/stop + results + score plot + structure; second tool: pair selection | 1.2k (`gui/dock_tool.py` 831, `pair_selection_wizard.py` 336) | `api/`, `core/` (imp_engine 766, av 603, trajectory 475, ...), `cli/`, `backend/` | **`structure_tools/cards/docking.py` covers the dock tool** (hub card); no standalone emtk entry | clean | FD1, FD2 (2); old F1-F3 superseded | M total |
| fps_json_editor | tabs Positions, Distances, FlexFit; JSON; 3D | 3.5k (`position_panel.py` 2035, `distance_panel.py` 837, `editor.py` 312, `flexfit_panel.py` 301) | `core/` (model, payload, pdb, naming, colors), `api/` | **`structure_tools/cards/fps_json.py` covers all tabs** (hub card); no standalone entry | clean | FJ1 (1) | S-M |
| acq | device and settings; run; 5 live windows; save | 6.1k (`gui/tool.py` 2670, `gui/{controllers,windows,settings_panel}.py` 1121, device setup dialogs 2.4k: `simulation/setup_dialog.py` 1231, `bh_spc/card_setup_dialog.py` 815, `brickmic` 196, `picoquant` 113) | `pipeline.py` 546 (`AcquisitionPipeline`, decoder), `services.py`, `tcspc_devices/*/wrapper.py` | none | clean | AQ0-AQ5 (6), **needs design** | L total |
| mmfdb_admin | about 20 navigation panels (entity docks are generated from a registry) | 11.7k (`gui/tool.py` 7079, `optical_components/` 1.4k, small views, dialogs) | `gui/client.py` 1496, `entity_registry.py`, `entity_schema.py`, `provenance_graph.py` (Qt-free builder), `session.py`, `backend/`, `api/` | none; `autoform_entity_form.py` already an AutoForm spec form | `__init__.py` (lazy import) | MA0-MA9 (10), **needs design** | L total |

Reusable building blocks, with what each one replaces:

| shared piece | where | replaces |
|---|---|---|
| one-page detector editor | `chisurf/emtk/channel_definition.py` + `core/setup_channel_definition.py` | `burst_analysis/gui/setup_selection_app.py` (2178), the detector tab of `burst_mle_analysis`, `burst_h2mm`'s channel tab (partly), `alex_suite`'s "Files/channels" step (the Qt `DetectorWizardPage`), `burst_selection`'s channel dialog (`_show_channel_settings`) |
| dataset picker | `chisurf/emtk/dataset_picker.py` | `BurstDataSelectionWidget._browse_mmfdb`, `show_sample_picker_dialog` (dataset part) |
| file chooser | `emtk.file_dialog.FileDialog` (title, mode, multiselect, filters, filename), as in `burst_fcs_correlator/gui/app.py:99` | every `QFileDialog` in these tools, including the two `from qtpy import QtWidgets` in `burst_selection/gui/app.py:715,733` and the one in `mfd_prepare/gui/tool.py` |
| background job | `chisurf/emtk/jobs.py` `SnapshotJob` | `QThread`/worker classes (`analysis_cache` worker, `_fit_worker`, `AcquisitionThread` is a device loop: needs its own design) |
| help and tour | `chisurf/emtk/help_guide.py` (`EmTkHelpWindow`, `EmTkGuidedTour`, `TourTarget`) | per-app `remember`, Qt `HelpGuideMixin` |
| spec forms and `data_table` | `emtk.view_form.draw_form`, `chisurf/plugins/emtk_layout.py` (`layout_spec`, `LabelColumn`) | every hand-drawn settings block and table below |
| `imaging_emtk` shell (`pixel_model.py`, `pixel_app.py`, `editors.py`, `plane.py`, `path_list.py`) | `chisurf/plugins/microscopy/imaging_emtk/` | **not applicable** to the burst tools (it is the per-pixel analysis shell; the detector editor is embedded there as a tab, which is the pattern, not the code). Useful as the pattern for AQ (live view over a model) only after design. |

Port-card conventions (from `wave3-plan.md`, `UPGRADE_BRIEF.md`, PRD-153): one `gui/app.py` that grows card by card, manifest `entrypoints.emtk`
added once by the last card (a card is checked with `--entry chisurf.plugins.<group>.<id>.gui.app:make_app`), Qt-free model in `gui/model.py`,
every control carries a tooltip, no emoji, no hard-coded palette, **no invented data (PRD-153 rule 8a)**, tests hermetic with
`CHISURF_SETTINGS_DIR`, `MMFDB_SETTINGS_DIR`, `MMFDB_DATABASE_PATH` in a temp folder.

## 3. burst_selection

**Entry points**: `gui` = `...burst_selection.gui.tool:BurstSelectionTool`; `cli` = `burst-selection`; `services` = `backend.services:register_services`; `menu_hidden: true`. No `emtk`. `wizard.py`
(32) and `__init__.py` (36) build the tool for script launch; `__init__.py:32` lazily imports `gui/legacy/burst_selector.py` (983).

**Stages, controls, Qt LOC** (approximate, from `def` ranges of `gui/tool.py`; emtk drawing in `gui/app.py`):

| stage | controls | Qt LOC | emtk today (`gui/app.py`) | shared piece to use |
|---|---|---|---|---|
| 1 Files and setup | add files / add folder / remove / clear, per-file include box, active-file switch, drag and drop, detector-setup combo, channel settings dialog, batch dialog (`BatchProcessingDialog` l.276), MMFDB session and sample picker (l.1845-2046) | about 750 + 80 (batch) | `_draw_files_content` (`app.py` ~598); files via `tool._file_paths`, two `QFileDialog` | `FileDialog`, `ChannelDefinitionWidget`, `DatasetPicker` |
| 2 Filter settings | algorithm combo (sliding window, CUSUM/SPRT, Kalman, BOCPD, coincident, max-tree, Bayesian Blocks); per algorithm: min photons L, window m, max dT T, dMT min/max, merge gap, count-rate threshold, CUSUM alpha/beta/bg/SB, Kalman Q/R/z/min-len/merge, BOCPD prob/prior, max-tree/BB p0; background subtraction; detector and window combos | about 700 here, plus the shared 2678-line `WizardTTTRPhotonFilter` that holds the state | `_draw_settings_content` (~748), mirrors the wizard through `_sync_from_tool`/`_sync_to_tool` | spec with `hidden_when` per algorithm |
| 3 Run | Run, Refresh (force), Save .bur, to ndX, Guide, Help; `analyze_files`, worker, `analysis_cache.ResultCache`, blocked-reason and gate-mismatch messages | about 200 | `_draw_top_action_bar` (~510) | `SnapshotJob` |
| 4 Diagnostics and features | MCS with draggable threshold, dT distribution, microtime decay, burst duration, 2D scatter with gate, 1D histogram with GMM fit and `GMMSettingsDialog`, paginated burst table, summary cards, viewport slider | about 1100 + 132 (GMM dialog) + 195 (`sections.py`) | `app.py` 1209-1779 (real data); form `burst_display.view.json` (4 controls) over `display_view_model.py` | `implot`, `data_table` |
| 5 Output | .bur save, FLR-CIF export (`export_flr_cif` l.4077), `MetadataDialog` (l.196), ndX hand-off, output formats (bur, sl5, MMFDB, zip) | about 550 | buttons only; dialogs are Qt | `FileDialog`, form dialog |
| chrome (not a stage) | toolbar, menu, dock layout save/restore, geometry, drag and drop | about 800 | hidden Qt docks still built | deleted by the last card |

**Qt-free logic**: `api/` (`selection.py` 861, `mmfdb.py` 769, `models.py` 314, `contract.py` 294, `features.py` 255, `io.py` 225), `gui/adapter.py` (602, imports `chisurf.gui.autoform.state` at l.312),
`gui/client.py` (`BurstSelectionClient`), `gui/display_view_model.py`, `gui/timeline.py`. The tool builds `AnalysisSettings` from Qt widgets in `_settings_from_controls` (l.1762); that state is not Qt-free.

**Tests**: 30 files, 250 test functions. Qt-constructing: `test_construction_smoke`, `test_display_form`, `test_emtk_parity` (fixture `BurstSelectionTool(embedded=True)`), `test_filter_settings_form`, `test_filter_ui_elements` (27), `test_gmm_settings_dialog`, `test_new_gui` (39), `test_photon_range_controls`, `test_tttrlib_wizard_modes`. Qt-free: `test_api` (672 lines), `test_api_mmfdb`, `test_cli`, `test_io`, `test_replay`, `test_container*`, `test_cusum`, `test_services`, `test_server`, `test_tttrlib_search`, `test_real_data`. Fixture: `tests/data/bh_spc132_sm_dna` (in repo).

**Existing emtk and duplicates**: `gui/app.py` hard-codes `WINDOW_BG`/`PANEL_BG`/`ACCENT_*` and emoji labels (PRD rules 5 and 6); `QFileDialog` twice; the `chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups` import (Qt-free, verified).

**Proposed cut** (every card shares one `gui/app.py`; none starts while B2 stands):
* **BS0 Settings and files model (M, reviewer decision first).** Qt-free `gui/model.py` holding file list, detector setup, `AnalysisSettings` fields and the algorithm parameters now held by the Qt wizard; `app.py` takes the model, not `tool`/`tool.wizard`. The model replaces `WizardTTTRPhotonFilter` for this plugin only; the shared wizard stays untouched. Must not touch `api/`, `backend/`, `cli/`. Test data: `bh_spc132_sm_dna`.
* **BS1 Files and setup stage (M).** File table, `FileDialog`, drops, detector setup via `ChannelDefinitionWidget` (replaces the channel dialog and the Qt setup combo), batch folders as a list form. Depends on BS0. Does not touch the filter form.
* **BS2 Filter settings form (M).** `gui/filter.view.json`, one spec, algorithm groups behind `hidden_when`. Depends on BS0.
* **BS3 Run and results (M).** Run/Refresh/Stop via `SnapshotJob` + `analysis_cache`, results held in the model, status line, blocked-reason messages. Depends on BS0-BS2. Test: search `m000.spc`, compare burst count with `test_real_data`.
* **BS4 Diagnostics plots (M).** MCS with threshold line, dT, decay, burst duration from model data (reuse `display_view_model.py`, `timeline.py`). Depends on BS3.
* **BS5 Burst features (M).** Scatter with gate, 1D histogram with GMM and a GMM-settings form (replaces `GMMSettingsDialog`), bursts `data_table` with `selected_call`, summary. Depends on BS3.
* **BS6 Output (M).** Save .bur, FLR-CIF export, metadata form, ndX hand-off, MMFDB output through `DatasetPicker`. Reviewer decides how the emtk ndX window is opened (cf. `30eb376`) and whether the output-sample picker needs a helper change. Depends on BS3.
* Then (small, part of BS6): drop hidden Qt docks and toolbar, add `entrypoints.emtk`, update `gui/guide.json` (58 lines, targets Qt object names such as `toolAction_add`) to `remember()` keys.

## 4. burst_mle_analysis

**Entry points**: `gui` = `...burst_mle_analysis.wizard:MLELifetimeAnalysisWizard`; `services`; `menu_hidden: true`. No `emtk`.

**Stages** (`wizard.py`; the `QTabWidget` is turned into an AutoForm dock shell at runtime, `_DOCK_LAYOUT` l.1667):

| stage | controls | Qt LOC (approx) | notes |
|---|---|---|---|
| 1 Detector definition (standalone only) | `DetectorWizardPage` (`channel_definer`, l.2918) | page is shared Qt | replace with `ChannelDefinitionWidget` |
| 2 Files | Burst, IRF and Background lists (`FileListWidget`, browse, clear, "One for all", per-detector widgets, `_prepare_irf_bg_widgets` l.2085); hidden when embedded | about 500 (`utils.py` 749 holds the list widgets) | `data_table` + `FileDialog` |
| 3 Burst-MLE parameters | current file/index, detector, fit range, min photons; IRF block (VV, VH, Shift, Threshold, IRF range, Scatter, G, l1, l2, BIFL scatter, 2I*, Save VV/VH); fit-parameter table (tau, gamma, r0, rho, score, rScatter, rExp: initial/fix/fit/result); model combo; dynamic-model rows (`_rebuild_dyn_params` l.3887); "Split by H2MM state" | about 900 (l.2270-3185 is widget building) | spec `view_spec` l.205 with `_MleParameterRows` |
| 4 Plots | "All selections" (decay, IRF, fit, residual), "Inspected burst" (`plot_fit_result` l.4264, `inspect_bursts` l.2210) | about 300 | `implot` |
| 5 Outputs / actions | `process_bursts` (l.4627, about 470 lines, multiprocessing via `_mp_worker.py`), `_save_burst_results_fast` l.663, `write_containers` l.816, `write_state_lifetimes` l.577, `save_fit`, `save_settings`/`load_settings`, `optimize_hyperparameters` l.5420, `auto_optimize`, `auto_extract_irf_bg` | science and Qt interleaved | companion contract must not change |

**Qt-free logic**: `_mp_worker.py` 421, `core/export.py` 212, `backend/services.py` 80 (resolves files and contract), `interpolate.py`. Fit settings are Python properties that read Qt spin boxes (`tau`, `gamma`, `shift`, ...; l.869-1450), and `burst_analysis` writes into those widgets (`_apply_irf_bg_to_mle_widget`), so there is no model: extracting one is the first card.

**emtk**: `gui/app.py` `BurstMleGui`/`BurstMleApp` (422) takes the wizard (`self.wizard`: `process_bursts`, `burst_files`, `irf_background_patterns`, `state_lifetimes`). Used only by `burst_analysis/gui/tool.py:421-460` (`_mle_panel`) where the real wizard is created and hidden. **Invented data: see section 12.** `gui/help.md` and `gui/guide.json` are referenced (`app.py:110-111`) but `ls gui` shows only `app.py`.

**Tests**: 8 files, 59 functions: `test_dock_shell` (8, builds the wizard), `test_file_list` (5), `test_mle_gui_end_to_end` (19, runs the fit; external data, B5), `test_state_split` (11); Qt-free `test_burst_photon_slice`, `test_fit_plot_curves`, `test_mle_fit_simulation`, `test_mle_workflow_services`; repo-level `test/gui/test_mle_frozen_inputs.py`. No test touches `BurstMleApp`.

**Proposed cut** (everything after ML-X blocked until ML0 is decided):
* **ML-X Remove invented data (S).** Draw the model results or an empty-state message in `BurstMleApp`; no change to the wizard; add the missing `gui/help.md` and `gui/guide.json`; add a test that fails when a plot call has no model input. Independent of the port (section 12).
* **ML0 Settings model (L, reviewer decision).** Qt-free `core/settings.py`/`gui/model.py` that the wizard properties delegate to (`tau`, `gamma`, IRF, range, fix flags, model name, dynamic parameters, `_capture_current_ui_state`/`_apply_ui_state` l.1810-1883, `apply_settings_payload` l.5569). Behaviour-preserving; the wizard stays the Qt UI. Must not move `process_bursts`.
* **ML1 Processing engine out of the wizard (L).** `process_bursts`/`make_vv_vh`/`read_burst_analysis` take the model and a progress callback; riskiest cut because of the subprocess pool and `batch_fingerprint`/stamp logic (l.4531-4620). Tests `test_mle_gui_end_to_end`, `test_state_split` stay green. Depends on ML0.
* **ML2 Files stage (M)**, **ML3 Parameters form (M-L)** (`data_table` editable fit-parameter table over `_MleParameterRows`), **ML4 Plots (M)** (real "All selections" and "Inspected burst", fitted-lifetimes table; depends on ML1, ML3), **ML5 Actions, settings I/O, hosting (L)** (Run/Restart/Save defaults, load/save settings with `FileDialog`, auto-optimise, hyper-parameter search, auto IRF/background extract, re-point `burst_analysis._mle_panel`, `entrypoints.emtk`; depends on ML1-ML4; decisions: detector stage via `ChannelDefinitionWidget`, the multiprocessing pool under emtk is a subprocess worker, not a `SnapshotJob`).

## 5. burst_analysis

**Entry points**: `gui` = `...burst_analysis.gui.tool:BurstAnalysisTool`; `optional_requires` lists 13 step plugins. No `emtk`.

**Stages**: the shell, `BURST_PANELS` at `gui/tool.py` ~590-735 (14 entries): 0 Setup Selection, 1 Data Selection, 2 Burst Selection (embeds `BurstSelectionTool`), 3 Burst Fusion (optional), 4 BVA, 5 2CDE, 6 Burst MLE, 7 Segmentation H2MM, 8 Segment MLE, then side tools Browser, Accurate FRET, Burst FCS, Kinetics (GS), Background, IRF and Background. Shell controls (`gui/app.py` 694): navigation rail with search and completion badges (`_draw_sidebar`), header with breadcrumb chips and Back/Next/Fast-forward, Guide/Help, status bar with progress and cancel. Context flows through `BurstWorkflowContext` (tool.py:27), filled by `_sync_*_context` (l.1230-1334), pushed by `_apply_context_to_*` (l.1492-1917, about 430 lines poking Qt widgets).

| own step | controls | emtk app | Qt LOC | replace with |
|---|---|---|---|---|
| 0 Setup Selection | setup combo, PIE/detector tables, TTTR reading, LUT, JSON editor window, region selector, Save/Rename/Delete, "Proceed to 1" | `setup_selection_app.py` 2178 (HEAD 588) hand-written | `BurstSetupSelectionWidget` ~50 (tool.py:300-350) | `ChannelDefinitionWidget` (the duplicate flagged on the board 2026-10-02) |
| 1 Data Selection | add files/folder, MMFDB browse/import, list with remove/clear, filter, status | `data_selection_app.py` 391, drives `BurstDataSelectionWidget` (`self.widget.*`, 11 uses) | about 240 (tool.py:56-300) | model + `FileDialog` + `DatasetPicker` |

**Qt LOC**: `gui/tool.py` 1940 (63 Qt hits: panel factories, the two step widgets, context bridge, status shims `_StatusTextLabel`/`_StatusProgressWidget`/`_StatusButton` l.740-795, Qt fallback overlay l.926-985). Qt-free: `api/workflow.py` 1421 (`BurstWorkflow` and friends; no GUI use). The step factories build the **Qt tools** (`BVATool`, `H2mmTool`, ...), not `create_app()` of the step plugins, although nine of those plugins declare `entrypoints.emtk`.

**What the shared editor lacks relative to the duplicate** (record in `deliberate.json` of BA4, do not rebuild): raw JSON editor window, region-selector drag window, "Proceed to 1. Data Selection" button, built-in fallback setup "ALEX Suite (auto)" (check whether the store seeds it). The shared editor has a decay preview (Plot toggle), Optical Setup, LUT tools and shift adjuster that the duplicate lacks. The widget contract that other workflows still speak (`selected_setup_name()`, `selected_setup_data()`, `apply_setup(name)`, `get_settings()`, `load_data_into_tables(settings)` used by `alex_suite`) must survive: map it onto `ChannelDefinitionWidget.model` (`get_settings()`, `select_setup(name)`) and `on_changed` (replaces `sync_to_tool`).

**Tests**: `test_emtk_workflow.py` (6, constructs `BurstAnalysisTool()` through `qapp`, paints via `QtPainter`), `test_workflow.py` (32, 974 lines, mostly the Qt-free python API plus tool-context tests).

**Proposed cut** (BA4 is independent of the others and ranked early; BA0-BA3 wait for the step plugins):
* **BA4 Setup selection on the shared editor (M).** Reduce `setup_selection_app.py` to a thin `ImApp` around `ChannelDefinitionWidget` (about 150 lines instead of 2178), keep the widget contract, delete the duplicate code. Needs B3 (owner yes, snapshot first) and B1. Tests: setup round trip through `tool.workflow_context`, `apply_setup` by name, `load_data_into_tables` from `alex_suite`; render at 1200x800 and 800x600.
* **BA3 Data selection stage (M).** `BurstDataSelectionWidget` logic (paths, `_on_paths_committed`, `_import_path_to_mmfdb` l.234-300) into a model; `FileDialog`; MMFDB browse through `DatasetPicker`. Fixture: BH `.spc` files.
* **BA0 Reviewer decision (no code):** switch the shell from `factory -> Qt tool -> .app` to each plugin's `entrypoints.emtk` `create_app()`; makes the shell depend on BS/ML/H cards.
* **BA1 Shell model (M):** Qt-free `gui/model.py` (`BurstWorkflowContext`, panel registry, step state and badges, `goto_*`, `fast_forward`, `process_current_step`, task state of the status shims); the app loses `from qtpy import QtCore` (`app.py:25`, one `QRectF`).
* **BA2 Context bridge (M):** uniform `apply_workflow_context(dict)` on each step's model (H2mm already has `H2mmTool.apply_workflow_context` l.1953); do the step side inside that plugin's own cards (BS6, ML5, H5), keep this card to the dispatcher.
* Final (small): `entrypoints.emtk`, remove the Qt fallback overlay and status shims once every step has an emtk app.

## 6. burst_h2mm

**Entry points**: `gui` = `...burst_h2mm.gui.tool:H2mmTool`; `cli` = `h2mm`; `services`; RPC `burst_h2mm.jobs.compute`, `workflow.prepare`, `contract.describe`; `menu_hidden: true`; `optional_requires: ndxplorer`. No `emtk`.

| stage | controls | Qt LOC (approx) | emtk today |
|---|---|---|---|
| 1 Folder | folder button + drop-enabled `_FolderLineEdit` (l.76), `_select_folder` l.899 | about 60 | label only, no picker |
| 2 Settings | Model selection (min/max states, criterion, scan patience); Optimisation (engine, restarts, seed, photon table HDF5/CSV, max iterations, min photons per burst, macro-time scale, nanotime divisors, decoder + seed, state photons PTU/sidecar/write) | `_build_settings_tab` l.374, about 170 | about 8 of about 20 |
| 3 Channels | FRET pair per detector stream (`_build_channels_tab` l.547, `_detector_streams` l.853) | about 80 | none |
| 4 Run | Run, Restart, Stop, Bootstrap (`_run_uncertainty` l.1137), LL scan (`_run_llscan` l.1257, `LikelihoodScanDialog` l.109), Save plot, Dwells in ndX (l.1188), settings save/load; `_fit_worker` l.1054 with ETA | about 450 | Run, Restart, Stop, Bootstrap, LL Scan buttons that click the Qt buttons |
| 5 Results | seven docks (`_build_plot_docks` l.622; plots l.1364-1930, about 700 lines): dwell FRET (E or E-S), TDP with arrows, model selection (BIC/ICL), dwell times, nanotime with state filters, rates matrix, burst path with navigation (`_rebuild_nav_bursts` l.1871) | about 700 | rate matrix, TDP with gate, dwell time; **invented fallbacks** |

**Qt-free logic**: `core/` 3.8k (`analysis.py` 1016, `export.py` 514, `engines.py` 395, `surrogate.py` 404, `decays.py`, `h2mm.py`, `state_tttr.py`, `photons.py`), `backend/services.py` 680, `api/` 406, `gui/client.py`, `cli/main.py`. The tool imports `H2mmSettings`, `StreamSettings`, `run_analysis`, `write_result_tables`, `ENGINES` (tool.py:53-57); `_gather_settings` l.872 builds settings from widgets. Missing: a Qt-free holder for settings and result (`_result`, `_bundle`, `_uncertainty`, `data_folder` live on the tool). Board lines 1598-1621 and 2005-2010 describe backend work in `core/` that these cards must not touch (engine routing, surrogate).

**Tests**: 14 files, 101 functions. Qt-free: engine, routing, cancellation, export, services, decoding, surrogate. Qt-touching: `test_gui.py` (6, builds `H2mmTool`), `test_dwell_censoring.py` (5), `test_state_decays.py` (9). Data: `examples/generate_example_data.py` simulation (label it a demo), BH `.bur` from `burst_selection/tests/data` for a real photon-by-photon fit.

**Proposed cut**:
* **H-X Remove invented data (S).** Section 12. Independent of the port.
* **H0 Model (M).** `gui/model.py` with `H2mmSettings`, `StreamSettings`, folder, result, uncertainty, scans, and actions (`run`, `restart`, `stop`, `bootstrap`, `ll_scan`) through `SnapshotJob` + `run_analysis`; the app takes the model, not `tool`. Must not touch `core/`, `backend/`, `api/`.
* **H1 Settings form (M).** `gui/h2mm.view.json` with all about 20 controls, folder picker with `FileDialog`, settings save/load. Depends on H0.
* **H2 Channel stage (S-M).** Detector-to-FRET-pair table (`data_table` with choice cells); reviewer decides between that and `ChannelDefinitionWidget`. Depends on H0.
* **H3 Core result plots (M).** Dwell FRET, TDP with arrows, rates matrix from `_result` only. Depends on H0.
* **H4 Remaining plots (M).** Model selection (BIC/ICL), dwell times, nanotime with state filters, burst path with navigation. Depends on H0, H3.
* **H5 Uncertainty, LL scan, hand-off (M-L).** Bootstrap and LL scan windows instead of `LikelihoodScanDialog`, Save plot, Dwells in ndX (reviewer: how the emtk ndX window is opened), `apply_workflow_context` on the model, `entrypoints.emtk`, guide update (`gui/guide.json` 65 lines targets Qt names). Depends on H0-H4.

## 7. burst_ebfret

**Entry points**: `gui` = `...burst_ebfret.gui.tool:EbfretTool` (a `QMainWindow` that only hosts `App(EbfretGui(client))` in a `ControlHost`, adds a toolbar "Load demo", a help/guide toolbar, tour anchors and a 50 ms repaint timer); `cli` = `ebfret`; `services`. No `emtk`.

**The app is already a Type A in the good sense**: `EbfretGui(client)` (`gui/app.py` 827) holds state and draws the ten panels of the MATLAB window (Time Series, Select Series, Crop, Ensemble with four plots, Select States, States, Analysis), menus (`MenuBar`), modal dialogs from 8 `*.view.json` (`select_analysis`, `remove_bleaching`, `clip_outliers`, `set_priors`, `assign_smd_channels`, `select_channels`, main), `controls.py` 208, `dialogs.py` 500; the host adapter `App` takes `(painter, x, y, w, h)` and routes pointer and keys. It does **not** read the Qt tool (`grep -c 'self.tool' = 0`) and all Qt-free (`qt=0` on `gui/app.py`, `controls.py`, `dialogs.py`, `core/`, `io.py`). The window's one "Load demo" is an explicit action (`load_demo`, writes `demo.write_demo()`), which PRD-153 8a allows.

**Gaps**: no `make_app`/`create_app` factory and no `entrypoints.emtk` (compare the factory names in the other burst plugins: `create_app(**kwargs)`), the Qt tool's toolbar items (Load demo, Help/Guide) have to exist inside the app: `load_demo` (l.389) is reachable only from the Qt toolbar and the tour's first step (`grep -n -i demo gui/app.py` finds no menu entry), so the standalone app needs its own labelled Demo menu item and a Help/Guide entry, and the dirty 11-line edit (B2) moves `remember` into `TourTarget`.

**Tests**: `tests/test_gui.py` (10, emtk window, hermetic, drives real clicks), `test_tool_qt.py` (3, Qt hosting), Qt-free `test_io`, `test_octave_ab` (data in `tests/octave`), `test_recovery`, `test_services`, `test_session`, `test_vbem`. Fixtures in repo (`tests/data/`, `simulated-K04-N350`).

**Card E1 (S)**: add `make_app()` building `App(EbfretGui(EbfretClient(None)))` with `EmTkHelpWindow`/tour wired if missing, `entrypoints.emtk`, evidence run against the Qt tool for the control inventory (menus, the 10 panels), keep `tool.py` as the Qt host. No model extraction needed. Test data: `tests/data/ebfret_session_k4.json`, `simulated-K04-N350`.

## 8. alex_suite

**Entry points**: `gui` = `...alex_suite.gui.tool:AlexSuiteTool` (a **subclass of `BurstAnalysisTool`**; replaces only the panel list; `INITIAL_ROLE = "channels"` in the pending edit), `cli` = `alex-suite`. No `emtk`. Steps (`gui/tool.py` panel list): 1 Setup (role `channels`), 2 Files, 3 Alternation (mu-s ALEX), 4 Burst search, 5 Background, 6 Accurate FRET, 7 E-S histogram, then Burst properties (browser), Titration, BVA, Export (ALEX-Suite CSV).

| own step | controls | Qt LOC | emtk app | Qt-free logic |
|---|---|---|---|---|
| Alternation | file list, period/donor/acceptor channels, manual windows and gate (`set_gate`), run/convert, phase plot, report, publish setup to MMFDB and RPC (`_publish`) | `alternation.py` 588 (`AlexAlternationPanel`, logic in the panel: `run` l.248, `_convert_detected` l.391, `_publish` l.423; `build_setup` l.514 is a pure function) | `AlexAlternationApp` (`app.py` l.475-700) | `api/convert.py` 285 |
| Titration | concentration/file table, 3 settings, Fit, stack plot, binding isotherm, numbers (`titration.view.json` 197 lines) | `titration.py` 95 (wrapper only) | `TitrationApp` (l.233-466), draws `TitrationViewModel` | `titration_view_model.py` 366, `api/titration.py` 609 |
| Legacy export | burst file picker, sample/buffer text, five CSV parts, Export | `legacy_export_panel.py` 114 | `LegacyExportApp` (l.71-230); reads `panel._bur_files`, `_status_text`, `run_export` | `api/legacy_export.py` |
| Shell and context | `AlexSuiteTool` context bridge (`_sync_channel_context`, `_apply_context_to_*`, `adopt_alex_conversion`, `_publish_setup`, ndX sources) | `tool.py` 547 | none (inherits the burst_analysis shell) | none |

**Tests**: `tests/` 5 files, 38 functions (`test_alternation` 13, `test_api` 15, `test_arrival_converts` 4, `test_workflow_shape` 5, `test_ndx_step` 1). `test_alternation.py:210` uses an external `.sm` file (B5). A shared note on the settings store: the alternation step writes setups to both stores (known issue in `okf/references/known-issues.md`, `_merged_setups`); do not change that in a port.

**Proposed cut** (the manifest switch waits for the burst_analysis shell; until then each card is checked with `--entry ...gui.app:make_app...` per panel):
* **AS2 Titration (S). DONE `5d54f60de`.** Type A: the model exists; make `TitrationApp` take the `TitrationViewModel` and a `FileDialog`, drop the panel coupling. Data: `bh_spc132_sm_dna` `.bur` files as concentrations (labelled test series, ratios are not chemistry).
* **AS3 Legacy export (S). DONE `4f6add194`.** Take `files`/`run_export`/status from a small Qt-free model instead of `panel`.
* **AS1 Alternation (M). DONE `a577affef`.** Move `run`, `_convert_detected`, `_publish`, `_store_phase` to a Qt-free `gui/alternation_model.py` (the app reads only the model), report and phase plot stay in the app. Only external data proves conversion (B5): add a synthetic phase fixture for the Qt-free part.
* **AS4 Shell (L). DONE `5912033fa` (was blocked on Burst Analysis).** After BA0-BA2 and the step plugins' cards; `AlexSuiteTool` is a subclass, so it cannot be switched earlier.

## 9. mfd_prepare

**Entry points**: `gui` = `...mfd_prepare.gui.tool:MfdPrepareTool`; `cli` = `mfd-prepare`; `services`; `menu_hidden: true`. One stage: choose a burst folder (`Browse...`), `Prepare` (verifies channels and count agreement, writes the MFD preparation report), report text. `gui/app.py` 161: `MfdPrepareGui(tool, on_browse, on_prepare)`, `MfdPrepareApp`; reads `tool._folder` and `tool._report_text`; Qt only in `gui/tool.py` (85 lines: `QFileDialog.getExistingDirectory`, `processEvents`, the RPC-or-local call). Qt-free: `api/{prepare,models,contract}.py` (`prepare_folder`, `PrepareRequest`), `backend/services.py`, `gui/client.py`. Tests: `tests/test_plugin.py` (134 lines, Qt-free API and RPC) on `burst_selection/tests/data/bh_spc132_sm_dna/burst_analysis_handoff`. Pending edit: 12 lines (tooltips, `TourTarget`).

**Card MP1 (S)**: `gui/model.py` with `folder`, `report`, `prepare()` (through `SnapshotJob`, local `prepare_folder` or the client), `FileDialog` for the folder, spec-free (3 controls), `make_app`, `entrypoints.emtk`, guide and help exist. No gaps in fixtures.

## 10. fret_docking (`chisurf/plugins/modelling/fret`) and fps_json_editor

**fret_docking** (hidden, tree clean): the Qt dock tool `gui/dock_tool.py` 831 (form from `fret_dock.view.json`, PDB list, results table with numeric sort and best-trial highlight, score plot, `chimol` structure viewer, progress dialog, project save/load, subprocess worker with stop flag), and `gui/pair_selection_wizard.py` 336 (`FRETPairSelectionWindow`, a second Qt tool: trajectory, topology, FPS, run, results, export). Backend (`core/`, `api/`, `cli/`, `backend/`) unchanged. Tests: 17 files in `test/` (`test_dock_gui`, `test_dock_project`, `test_gui`, `test_pair_selection`, `test_fret_pair_selection`, ...), examples `examples/{fps_hiv_rt,olga_t4l}`.

**Overlap with `structure_tools` (decisive)**: `cards/docking.py` (384) + `docking_model.py` (541) already implement F1, F2 and F3 of `wave3-plan.md` natively (Qt-tool's own spec file, Run/Stop with progress, project load/save, results table, score plot, 3D structure through `implot3d`; the 2026-10-02 report lists as **not ported**: the **Database (MMFDB) button**; Stop is present). Test coverage: `structure_tools/test/test_cards.py` (`test_docking_request_equals_the_qt_models`, `test_docking_runs_and_lists_the_result`, `..._repeats_...`, `..._missing_input_and_drop`) and `test_native.py`. So F1-F3 are obsolete as written; the remaining standalone work:
* **FD1 Standalone docking window (S-M).** `fret/gui/app.py` with `make_app` hosting the `structure_tools` docking card (import it, do not copy), the MMFDB database button (via `DatasetPicker`), parity check against `dock_tool.py` controls, `entrypoints.emtk` on `fret_docking`. Blocked by B4 until the structure_tools cards are committed.
* **FD2 Pair selection wizard (M).** `FRETPairSelectionWindow` is not covered anywhere: model over `core/pair_selection.py` (300, Qt-free), spec form (trajectory, topology, FPS pickers with `FileDialog`, parameters), results `data_table`, export. Tests exist for the core (`test_pair_selection`, `test_fret_pair_selection`); data: `examples/olga_t4l` (check it has a trajectory).

**fps_json_editor** (hidden, tree clean): tabs Positions (`position_panel.py` 2035 Qt: table Show/Name/PDB/Chain/Res/Atom/Dye preset/Dye model/Details/Color/delete, Add Row, Compute AVs, Save AV MRC), Distances (`distance_panel.py` 837), FlexFit (301), JSON, 3D; Qt-free `core/` and `api/client.py`; `av_worker.py` 103; tests `test/test_plugin.py` 44 functions, `test_av_worker`, `test_construction_smoke`. **Covered** by `structure_tools/cards/fps_json.py` (697) + `fps_model.py` (1069) + three `views/fps_*.view.json`: all five tabs, `data_table`, AV computation, MRC save, FPS round trip equal to the Qt model (`test_fps_round_trip_equals_the_qt_model`), draws every tab, clicks and file-dialog tests. Known gaps listed in the report: multi-row selection and row context menu (emtk `data_table` has no Ctrl-click), ChiMol residue picking is QuEst's, not FPS's.
* **FJ1 Standalone FPS editor (S-M).** `fps_json_editor/gui/app.py` with `make_app` hosting the card (import), RPC client unchanged, `entrypoints.emtk`; decide with the reviewer whether the multi-row gap is a blocker (`deliberate.json` otherwise). Blocked by B4.

## 11. acq and mmfdb_admin (own design needed; cut is for sizing only)

**acq** (clean tree; hardware): `gui/tool.py` 2670 (`SMAcquisitionManager`, `AcquisitionThread` and `DataProcessingThread` as `QThread`, `AcquisitionDockWidget`), `gui/{controllers,windows,settings_panel}.py` (1121), device setup dialogs per device (simulation 1231, BH SPC 815, Brickmic, PicoQuant), `pipeline.py` 546 (Qt-free `AcquisitionPipeline`, decoder, sinks), `services.py` (`simulation_run`). Stages: select device and initialize (`initialize_device` l.952, `open_card_setup` l.1520), acquisition settings (duration, photon limit, output path, formats, display toggles; JSON save/load l.2074-2209), start/stop with progress, FIFO usage and RAM (l.1403-1520), five live windows (decay, correlation, count rate, macro-time, MCS; update methods l.1796-2653 about 900 Qt+plot lines), save (`_save_data` l.2529). Tests: `test_pipeline` (15), `test_spc_record_decoder` (5); no GUI test. Simulation device (`tcspc_devices/simulation`, tttrlib `Sim*`) needs no hardware and is the only testable device; real devices (BH, PicoQuant, Brickmic) can not be tested in CI. Cut: **AQ0** model + job over `AcquisitionPipeline` with a worker thread contract (design decision: `SnapshotJob` is for snapshots, a live device loop needs its own streaming job in emtk), **AQ1** settings form (spec) + save/load, **AQ2** run/stop + status (FIFO, RAM, progress), **AQ3** decay and count-rate windows, **AQ4** correlation, macro-time, MCS windows, **AQ5** simulation setup dialog (1231 Qt lines; split into forms) and the card setup dialogs per device (needs hardware sign-off). Size L overall; AQ0 is a reviewer decision.

**mmfdb_admin** (`__init__.py` has a pending lazy-import edit): navigation shell `MMFDBWidget(NavigationPanelTool)` (`gui/tool.py` 7079 lines, 544 Qt hits, `_build_panels` l.1851) with panels: Overview, All items, Measurements; one **entity dock per `EntitySpec`** (generated from `entity_registry.py`/`entity_schema.py`; `EntityDock` 302 + `AutoFormEntityForm` 260, already AutoForm); Sample Metadata (5 sub-tabs: Entities, Probes and Positions, FRET Pairs, Condition, Full Description; `metadata_dock.py` 339 + tool l.3084-3300); Spectra (fluorophore dock); Provenance Graph (`provenance_graph.py` 558, Qt-free builder; draws through the old Qt node scene, board line 2511: the last consumer of it); Import/Export; eLabFTW (`elabftw_view.py` 394); Studies, Protocols, Lifecycle, Calibrations, Reagent Lots, Pipelines (six standalone views of 107-142 lines each over the client); optical components (`component_dock.py` 748, `duplicates_dialog.py` 635); connection/auth (`connection_auth.view.json` exists, `connection_dialog.py` 70), `PasswordChangeDialog` (tool.py:199). Qt-free: `gui/client.py` 1496 (`MMFDBClient`), `session.py`, `backend/`, `api/`. Tests: 22 files (`test_admin_navigation`, `test_entity_dock_gui_interactions` 20, `test_optical_components`, one `test_*_view` and `test_*_handlers` per small view). Fixture: `seed_example.py`, temp MMFDB. Cut (sizing): **MA0** nav shell + connection/login (S-M, includes `PasswordChangeDialog`; reviewer decision on the Qt `NavigationPanelTool` replacement), **MA1** generic entity dock from the registry with `data_table` and the existing AutoForm spec (M, largest payoff: most panels are this), **MA2-MA3** the six small views, two cards of three (S each), **MA4** Overview + All items + Measurements (M), **MA5** Import/Export (M), **MA6** eLabFTW (M), **MA7** Sample Metadata sub-tabs (L), **MA8** optical components with duplicates dialog (L), **MA9** provenance graph on `chisurf/emtk/node_editor` (M-L, retires the last Qt node scene user). Not dispatchable before a design pass on the nav shell and on how a 20-panel admin tool is hosted.

## 12. Known defect: invented data in `burst_mle_analysis` and `burst_h2mm` emtk apps

Recorded in `okf/references/known-issues.md` ("Ported burst apps draw invented data (found 2026-10-01)"); PRD-153 rule 8a forbids it. Measured again 2026-10-02 (line numbers of the working tree, B2 edits included):

* `burst_mle_analysis/gui/app.py`: decay plot l.280-290: `chs = np.linspace(0, 4095, 256)`, a Gaussian `irf` (`np.exp`, centre 800, width 20) and an exponential `decay` (tau 400 channels) drawn as "Decay Data" and "IRF Pattern" for any user data; lifetime histogram l.335-338 from `self.tau1`/`self.tau2` (the app's own mirrors, not the wizard's fit). In `burst_analysis` `_mle_panel` the real wizard is created, hidden (`wizard.setParent(host); wizard.hide()`), and this mock is shown.
* `burst_h2mm/gui/app.py`: hard-coded `demo_rates = [[0, 420], [210, 0]]` rate table l.399-421 (shown whenever there is no result); `np.random.seed(123)` + `np.random.normal` "S0 to S1"/"S1 to S0" clusters l.462-467 when `_result.transitions` is absent (the scatter of real transitions is drawn when present); invented dwell curves `exp(-ts/1.5)*500` and `exp(-ts/3.0)*350` l.496-498; no model-selection, nanotime, dwell-FRET or burst-path plot exists in the app at all.
* Neither app is covered by a test (`grep BurstMleApp|H2mmApp` outside `gui/` finds only the two hosts `burst_h2mm/gui/tool.py:254` and `burst_analysis/gui/tool.py:421,450`).
* **Fix cards ML-X and H-X (S each, independent of the ports)**: draw only what the wizard/tool computed (`plot_fit_result` curves, `_result` fields) or an empty-state message; any demo only behind an explicit, labelled Demo action; add a test that renders both apps with no data and asserts no plot call has a data array (use `implot` call spy or the emtk inventory) and that the empty-state text is drawn; the ports H3/H4/ML4 then replace these plots. Both files are in B2; commit order: owner's tooltip commit first, then the fix, so the fix diff is readable.

## 13. Ranked dispatch order for the next 10 cards

Ranking rule: defect first, then smallest cards that prove the pipeline on a plugin class, then the explicitly requested duplicate removal, then
cards whose deliverable unblocks bigger ones. "Precondition" is the minimum that must be true; B1 (committed `chisurf/emtk/`) applies to all.

| # | card | size | precondition | test data | why here |
|---|---|---|---|---|---|
| 1 | **H-X** `burst_h2mm` invented data to empty state + test | S | B2 for `burst_h2mm` (owner commits the tooltip/layout edits of `gui/app.py`) | none (empty state), `_result` synthetic object for the real-data branch | user-facing defect, five plot sites, no dependency |
| 2 | **ML-X** `burst_mle_analysis` invented data + missing `gui/help.md`, `gui/guide.json` | S | B2 for `burst_mle_analysis` | none; wizard on `bh_spc132_sm_dna` `.bur` for the real-data branch (external folder is only needed for the end-to-end test) | same defect, and the hosted panel shows the mock instead of the wizard |
| 3 | **MP1** `mfd_prepare` model, `FileDialog`, `make_app`, manifest | S | B2 (12 lines) | `bh_spc132_sm_dna/burst_analysis_handoff` | smallest complete Type A with a clean split; proves the burst-plugin recipe |
| 4 | **E1** `burst_ebfret` factory, manifest, evidence | S | B2 (11 lines) | `tests/data/ebfret_session_k4.json`, `simulated-K04-N350` | app already independent of Qt; one factory away from done |
| 5 | **BA4** `burst_analysis` setup step on the shared editor (delete the 2178-line duplicate) | M | **B3: owner says yes**, snapshot in `pre-upgrade/` | BH `.spc` (`m000.spc`) for Read and Plot; stored setups in a temp MMFDB | the stated goal; removes 1.6k lines of dead-end editor |
| 6 | **AS2** `alex_suite` titration app on `TitrationViewModel` | S | B2 for `alex_suite` | `bh_spc132_sm_dna` `.bur` series as a labelled test series | model and spec already exist |
| 7 | **AS3** `alex_suite` legacy export app on a small model | S | B2 for `alex_suite` | `.bur` + `burst_analysis_handoff` | same recipe as 6, last small step of the suite |
| 8 | **FD1** standalone docking window hosting the `structure_tools` docking card (+ MMFDB database button) | S-M | B4 (structure_tools cards committed) | `fret/examples/fps_hiv_rt` (check for a 10 min run), stub `ops` for the subprocess path as in `wave3-plan.md` | replaces obsolete F1-F3 with the remaining real work |
| 9 | **FJ1** standalone FPS editor hosting the card | S-M | B4 | `fret/examples/fps_hiv_rt`, `olga_t4l` | same shape as 8 |
| 10 | **H0** `burst_h2mm` model (`H2mmSettings`, result, actions via `SnapshotJob`) | M | H-X done, B2, reviewer confirms scope | `examples/generate_example_data.py` (simulation, labelled) and BH `.bur` | first model extraction of the large plugins; unblocks H1-H5 and BA2/AS4 context bridge |

Next after these ten: AS1 (M, alternation model), BA3 (M), BS0 (M, reviewer decision), ML0 (L, reviewer decision), then H1-H5, FD2, BS1-BS6, ML1-ML5, BA0-BA2, AS4. `acq` and `mmfdb_admin` wait for a design pass (section 11).

## 14. Commands used

`git status --short [-- <dir>]`, `git diff HEAD [--stat|-U0] -- <files>`, `git ls-tree -r HEAD chisurf/emtk`, `git ls-files`, `git log --oneline -- <path>`;
`wc -l`, `find <dir> -name '*.py' ... | xargs wc -l`, per-file `grep -c -E 'qtpy|PyQt|pyqtgraph|QtWidgets|QtCore'`; `grep -n -E "^class |^    def "` on each Qt file;
`grep -o 'getattr(self.tool, "[A-Za-z_]*"' | sort -u | wc -l`; `grep -n "hidden_when\|visible" ~/dev/emtk/emtk/view_form.py`; manifests read as JSON (`entrypoints`);
`grep -c "def test_"` per test directory; `grep -n "burst_selection|...|mmfdb_admin" okf/agent-board.md`. Not verified by running: any on-screen behaviour of the
emtk apps, whether `DatasetPicker.kinds` can name samples, whether `fret/examples/*` hold a short enough docking run, whether `ChannelDefinition` seeds the "ALEX Suite (auto)" setup.

## 15. Notes carried over from the first pass

* Correction (2026-10-01, found in card T2): `StarRatingWidget` has 3 stars (`self._stars = 3`; `StarCombo` offers 0..3), so the ported rating column is 0..3.
* Sibling burst plugins that already declare `entrypoints.emtk` and are the templates to copy: `burst_bva` (`gui/app.py` 546 over `view_model.py`/`controller.py`, `create_app()` l.593), `burst_2cde`, `burst_background`, `burst_gs`, `burst_irf_bg`, `burst_fusion`, `burst_fcs_correlator`, `burst_browser`, `accurate_fret`, `bid_to_analysis`.
* The Qt photon-filter wizard `chisurf/gui/widgets/wizard/tttr_photonfilter/tttr_photon_filter.py` (2678 lines, shared) is the settings store of `burst_selection`; do not edit it, the BS0 model replaces it for that plugin only.
* The `trace_browser` card list of the first pass (T0-T4) is complete; do not dispatch it again.
