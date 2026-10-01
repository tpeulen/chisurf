# Burst tools survey (PRD-153 card S): burst_selection, burst_mle_analysis, burst_analysis, burst_h2mm, trace_browser

Read-only survey on 2026-10-01, no code changed, no analysis run, only read-only git (`status`, `log`, `diff --stat`, `show`).
Manifests found with `grep -rl '"id": "<id>"' chisurf/plugins --include=manifest.json`; all five manifests declare
`entrypoints.gui` (+ `cli`/`services` for some) and **none declares `entrypoints.emtk`** (checked by reading each manifest).
Line counts are `wc -l`. "Qt LOC" = files that import `qtpy`/`pyqtgraph`/`chisurf.gui` (counted per file with
`grep -c -E 'qtpy|PyQt|pyqtgraph|chisurf\.gui|QtWidgets'`); a count of 0 means Qt-free. The emtk apps are listed separately.

## Summary

| plugin | stages | Qt LOC | Qt-free logic location | emtk app exists? | dirty tree? | proposed cards |
|---|---|---|---|---|---|---|
| burst_selection | 5 (Files and setup; Filter settings, 7 algorithms; Run; Diagnostics and feature plots; Output) | about 5.9k Qt (`gui/tool.py` 4176, `legacy/burst_selector.py` 983, `gui.ui` 378, `sections.py` 195, `gmm_settings_dialog.py` 132) + `gui/app.py` 2166 (emtk, hosted) | `api/` (3.2k), `backend/services.py`, `gui/adapter.py`, `gui/client.py`, `gui/display_view_model.py`, `gui/timeline.py`; tool delegates through `BurstSelectionClient` for the search | yes, `gui/app.py` (`BurstSelectionApp`), but coupled to the Qt tool and to its Qt wizard widgets; real data | **yes**, `gui/app.py` + 3 docs modified | 7 (BS0 to BS6), BS0 is a model extraction and a reviewer decision |
| burst_mle_analysis | 4 (Detector definition; Files; Burst-MLE parameters; Fit and plots) + outputs | about 5.7k (`wizard.py` 5667, Qt and logic mixed in one class) + `utils.py` 749 (8 Qt hits) | `_mp_worker.py` 421, `core/export.py` 212, `backend/services.py` 80; the fit science (`process_bursts`, `make_vv_vh`, `_save_burst_results_fast`) sits **inside** the Qt wizard class | partial: `gui/app.py` (`BurstMleApp`, 422) is a **preview mock with simulated curves**, only used by `burst_analysis` | **yes**, `gui/app.py` modified | 6 (ML0 to ML5), ML0 blocked on reviewer |
| burst_analysis | 14 pipeline steps (0 Setup to 8 Segment MLE + 6 side tools); the plugin itself is a navigation shell | about 1.9k (`gui/tool.py`) | `api/workflow.py` 1419 (python API, **not used by the GUI**); `BurstWorkflowContext` dataclass is in `tool.py` | yes: shell `gui/app.py`, `data_selection_app.py`, `setup_selection_app.py`; all other steps are Qt tools that carry their own hosted `ImApp` | **yes**, 4 files modified (`setup_selection_app.py` +2078/-264 lines vs HEAD) | 5 (BA0 to BA4), BA0 only after the step plugins have models |
| burst_h2mm | 4 (Folder; Settings; Channel definitions; Run and results) + Bootstrap, LL scan | about 2.0k (`gui/tool.py` 1998) + `gui/app.py` 532 (emtk) | `core/` (3.8k), `backend/services.py` 680, `api/`, `gui/client.py`; tool runs the fit through `backend.services.run_analysis` | yes, `gui/app.py` (`H2mmApp`), partial (about 8 of about 20 controls, 4 docks) and **draws demo data** when no result | **yes**, `gui/app.py` + `README.md` modified | 6 (H0 to H5) |
| trace_browser | 2 (Setup via DetectorWizard; Browser: folder, file table with ratings and notes, trace plot, export and hand-off) | about 2.8k (`__init__.py` 2631 holds all the Qt, `gui/tool.py` 144) | `core/` (218), `api/` (216), `backend/services.py` 123, `gui/client.py` 121; Qt widget delegates metadata, trace load and CSV export to the client | **no** | clean | 5 (T0 to T4) |

Reading the table: three of the five (selection, MLE, H2MM) already have an emtk `gui/app.py` that a Qt `ChisurfDockTool` hosts
inside `ControlHost`, but each app reads and drives the Qt tool (not a model), so they are **not** Type A in the PRD sense
(PRD "Type A": the app takes a model, the Qt tool is optional). The sibling plugins `burst_bva`, `burst_2cde`, `burst_background`,
`burst_gs`, `burst_irf_bg`, `burst_fusion`, `burst_fcs_correlator`, `burst_browser`, `accurate_fret` all declare
`entrypoints.emtk` (`grep -n '"emtk"' chisurf/plugins/burst/*/manifest.json`) and are the templates to copy
(`burst_bva/gui/app.py` 546 lines over `view_model.py`/`controller.py`, `create_app()` at l.544).

Cross-cutting findings:

* **Reusable building blocks already exist**: `chisurf/emtk/channel_definition.py` (`ChannelDefinitionWidget`, Qt-free, used by 8 apps, including `burst_background` and `accurate_fret`), `chisurf/emtk/jobs.py` (`SnapshotJob`), `chisurf/emtk/help_guide.py` (`chisurf/gui/widgets/tools/emtk_help_guide.py` is an 8-line shim to it, so the `chisurf.gui` import in these apps is only a path, not Qt).
* **The Qt photon-filter wizard is the settings store for burst_selection**: `chisurf/gui/widgets/wizard/tttr_photonfilter/tttr_photon_filter.py` (2678 lines, shared) is embedded and its widgets (`comboBox_burst_filter`, `comboBox_2`, ...) are read and written by `gui/app.py`. Do not edit it; the model must replace it for this plugin.
* **Two hosted apps draw fake data** (`burst_mle_analysis/gui/app.py:280-340`, `burst_h2mm/gui/app.py:398-503`). CLAUDE.md/PRD rules say no simulated preview; fix as part of the card that touches the plot.
* **Missing resources in the MLE app**: `burst_mle_analysis/gui/app.py:110-111` points at `gui/help.md` and `gui/guide.json`, but `ls chisurf/plugins/burst/burst_mle_analysis/gui` shows only `app.py` (not run, read from the code and listing).

---

## burst_selection

**1. Entry points** (`manifest.json`): `gui` = `chisurf.plugins.burst.burst_selection.gui.tool:BurstSelectionTool`; `cli` = `burst-selection=...cli:cli`; `services` = `backend.services:register_services`. No `script`, no `emtk`. `wizard.py` (32 lines) and `__init__.py` (36) build `BurstSelectionTool(...)` for the legacy script launch (`if __name__ == "plugin"`), `__init__.py:32` lazily imports the older `gui/legacy/burst_selector.py` (983 lines).

**2. Stages** (from `gui/tool.py` setup code and `gui/app.py` docks; commands: `grep -n -E "^(class |def )|^    def " gui/tool.py`, `sed -n 76,260p gui/app.py`):
1. *Files and setup* (`app.py:598` `_draw_files_content`; Qt `_build_files_controls_panel` tool.py:1100): add files / add folder / remove / clear, per-file include checkbox, active-file switch, detector-setup combo (`load_detector_setups`), channel settings dialog (`_show_channel_settings` l.1630), drag and drop, batch dialog (`BatchProcessingDialog` l.276), sample picker for MMFDB output (`show_sample_picker_dialog`).
2. *Filter settings* (`app.py:748` `_draw_settings_content`; Qt `_build_wizard_embed` l.583 embeds `WizardTTTRPhotonFilter`): algorithm combo (sliding window, CUSUM/SPRT, Kalman, BOCPD, coincident, max-tree, Bayesian Blocks), per-algorithm parameters (min photons L, window m, max dT T, dMT min/max, merge gap, count-rate threshold, CUSUM alpha/beta/bg/SB, Kalman Q/R/z/min-len/merge, BOCPD prob/prior, max-tree/BB p0), background subtraction, detector and window combos.
3. *Run* (`_draw_top_action_bar` app.py:510): Run, Refresh (force), Save .bur, to ndX, Guide, Help; Qt `analyze_files` l.2289 with worker `_analysis_worker` and `analysis_cache.ResultCache`.
4. *Diagnostics and feature plots* (app.py:1209-1779): count-rate MCS with draggable threshold, dT distribution, microtime decay, burst duration, 2D feature scatter with gate rect, 1D histogram with GMM fit (Qt `GMMSettingsDialog`), paginated bursts table, summary cards; display form `gui/burst_display.view.json` (4 controls) over `display_view_model.py`; viewport slider and `timeline.py`.
5. *Output*: `.bur` save, FLR-CIF export (`export_flr_cif` l.4077), metadata dialog (`MetadataDialog` l.196), ndX hand-off (`_open_in_ndxplorer`, `_send_current_to_ndxplorer`), output formats (`_output_formats_for_inputs` l.3799: bur, sl5, MMFDB, zip), MMFDB session (l.1886-2046).

**3. Qt LOC** (`wc -l`): `gui/tool.py` 4176 (183 Qt hits), `gui/legacy/burst_selector.py` 983, `gui/assets/gui.ui` 378, `gui/sections.py` 195 (custom `burst_time_window` section), `gui/gmm_settings_dialog.py` 132; about 5.9k. emtk side: `gui/app.py` 2166. Qt-free: `api/` 3,018 (`selection.py` 861, `mmfdb.py` 769, `models.py` 314, `contract.py` 294, `features.py` 255, `io.py` 225), `backend/` 386, `gui/adapter.py` 602 (1 Qt hit), `gui/client.py` 373, `gui/display_view_model.py` 219, `gui/timeline.py` 158.

**4. Qt-free logic and delegation**: the tool delegates the search to `BurstSelectionClient` (`gui/client.py`, built tool.py:~480) and uses `AnalysisSettings` from `api/models.py` (`default_analysis_settings`, tool.py:156; `_settings_from_controls` tool.py:1762 builds it from the Qt widgets). The **state** (what the user chose) is not Qt-free: it lives in `WizardTTTRPhotonFilter` widgets, `self._file_paths`, `_last_*` attributes on the tool.

**5. emtk app**: `gui/app.py` `BurstSelectionGui`/`BurstSelectionApp(ImApp)`, hosted from `tool.py:_build_ui` (`ControlHost(self.app, background=WINDOW_BG[:3])`, l.540-550) with the legacy `DockArea`, toolbar and status bar hidden but still built. What the Qt tool still adds: toolbar (`_setup_toolbar` l.3856, with ndX buttons and `add_toolbar_help`), menu (`_setup_menu` l.1384), dock layout save/restore, geometry persistence, drag and drop, MMFDB connection, workers, and the whole Qt wizard (the app mirrors it through `_sync_from_tool`/`_sync_to_tool`, app.py:262-460). Coupling measured: `grep -o 'getattr(self.tool, "[A-Za-z_]*"' gui/app.py` shows 21 distinct tool attributes (`wizard`, `_file_paths`, `_last_frame`, `analyze_files`, `_apply_detector_setup`, `_load_tttr_for_plots`, ...). Qt imports in `app.py`: `from qtpy import QtWidgets` at l.715 and l.733 (two `QFileDialog` calls for add files/folder), `chisurf.gui.widgets.tools.emtk_help_guide` (shim), `chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups.load_detector_setups` (l.44; check that module is Qt-free before relying on it, not verified). Style: hard-coded `WINDOW_BG`/`PANEL_BG`/`ACCENT_*` colours (l.51-61) and emoji in labels, both to be removed per PRD rules 5 and 6.

**6. Tests** (`ls tests`, `grep -c '^\s*def test_'`): 28 test files, 250 test functions. Qt-constructing: `test_construction_smoke` (2), `test_display_form` (5), `test_emtk_parity` (5, fixture `BurstSelectionTool(embedded=True)`), `test_filter_settings_form` (9), `test_filter_ui_elements` (27), `test_gmm_settings_dialog` (3), `test_new_gui` (39), `test_photon_range_controls` (3), `test_tttrlib_wizard_modes` (8); also `test_diagnostic_window`, `test_timeline`, `test_search_bounds`, `test_preview_*`, `test_proximity_ratio_is_not_faked` may build the tool (not all checked). Qt-free: `test_api` (672 lines), `test_api_mmfdb`, `test_cli`, `test_io`, `test_replay`, `test_container*`, `test_cusum`, `test_services`, `test_server`, `test_tttrlib_search`, `test_real_data` (uses `tests/data/bh_spc132_sm_dna`). Repo-level: `test/test_burst_search_form.py`, `test_burst_tool_tasks.py`, `test_burst_reuse.py`, `test_burst_settings_restore.py` (names in `test/gui`; contents not read).

**7. Tree and board**: `git status --short -- chisurf/plugins/burst/burst_selection` shows ` M gui/app.py` and ` M docs/INSTRUCTION_{GUI_VERIFICATION,HDF5_ZIP_TESTS,TTTRLIB_BURSTFILTER}.md`; `git diff --stat` on `gui/app.py`: 114 insertions, 8 deletions (tooltips and a moved `remember`). **Dirty = another agent's uncommitted work.** `grep -n burst_selection okf/agent-board.md`: no claim (the only hits for the five ids are lines 1598-2010, all about `burst_h2mm` engine and ndX call-sites, see burst_h2mm).

**8. Proposed cut** (every card shares one `gui/app.py`; manifest `entrypoints.emtk` is added once, by the last card; none starts while `gui/app.py` is dirty):
* **BS0 Settings and files model (reviewer decision first).** New Qt-free `gui/model.py` holding file list, detector setup, `AnalysisSettings` fields and the algorithm parameters now stored in the Qt wizard; `app.py` takes the model instead of `tool`/`tool.wizard`. Decision needed: the model replaces `WizardTTTRPhotonFilter` for this plugin only; the shared 2678-line wizard stays untouched (BVA/others use it). Must not touch `api/`, `backend/`, `cli/`.
* **BS1 Files and setup stage**: file table, add files/folder with emtk `FileDialog` (removes both `qtpy` imports in app.py), detector setup combo, channel definition via `chisurf.emtk.channel_definition.ChannelDefinitionWidget`. Depends on BS0. Must not touch the filter form.
* **BS2 Filter settings form**: spec `gui/filter.view.json` for the algorithms. Open question for the reviewer: whether AutoForm specs can show/hide groups by the selected algorithm (not verified; look at `view_spec.py` for conditional sections). Depends on BS0.
* **BS3 Run and results**: Run/Refresh/Stop through `SnapshotJob`, `analysis_cache`, results held in the model, status line. Depends on BS0, BS1, BS2.
* **BS4 Diagnostics plots**: MCS (threshold line), dT, decay, burst duration from model data (the Qt-free `display_view_model.py`, `timeline.py` are reusable). Depends on BS3.
* **BS5 Burst features**: scatter with gate, 1D histogram with GMM and GMM-settings form (replaces `GMMSettingsDialog`), bursts `data_table` (`selected_call`), summary. Depends on BS3.
* **BS6 Output**: save .bur, FLR-CIF export, metadata dialog as a form, ndX hand-off, batch dialog. **Blocked part**: MMFDB output and `show_sample_picker_dialog` (Qt dialog, `chisurf/gui/widgets/sample_picker`) need an emtk sample picker, and the ndX launch is an external viewer; reviewer decides. Depends on BS3.
* Then (small, not a card of its own): drop the hidden Qt docks/toolbar, add `entrypoints.emtk`, guide steps in `gui/guide.json` are already present (58 lines) but target Qt object names (`toolAction_add`, "Channel selection"): update to `remember()` keys.

---

## burst_mle_analysis

**1. Entry points**: `gui` = `chisurf.plugins.burst.burst_mle_analysis.wizard:MLELifetimeAnalysisWizard`; `services` = `backend.services:register_services`. `menu_hidden: true`. No `cli`, `script`, `emtk`. `__init__.py` is 29 lines.

**2. Stages** (`grep -n -E "^    def " wizard.py`, `sed -n 1667,1800p`, `_build_files_tab` l.2350, `_build_parameters_tab` l.2422; the QTabWidget is converted to an AutoForm dock shell at runtime, `_DOCK_LAYOUT` l.1667):
1. *Detector Definition* (standalone only; removed when embedded): `DetectorWizardPage` (`self.channel_definer`, l.2918).
2. *Files*: three group boxes, Burst files, IRF files, Background files (`FileListWidget`, browse, clear, "One for all" checkboxes, per-detector file widgets, `_prepare_irf_bg_widgets` l.2085). Hidden when embedded in `burst_analysis`.
3. *Burst-MLE parameters* (toolbar l.2434: Run, Restart, Save defaults via `action_button`): current file and index, detector combo, fit range (micro-time start/stop), min photons; IRF block (VV, VH, Shift, Threshold, IRF range, Shift, Scatter [Hz], G, l1, l2, BIFL scatter, 2I*: P+2S, Save VV/VHs); fit-parameter table (initial value, fix, fit, result for tau [ns], gamma, r0, rho [ns], score, rScatter, rExp; model combo; dynamic-model parameter rows built by `_rebuild_dyn_params` l.3887, spec `view_spec` l.205 with `_MleParameterRows`); "Split by H2MM state" row (segment-level step).
4. *Plots* (`setup_plots` l.2939): "All selections" (decay, IRF, fit, residual), "Inspected burst"; `plot_fit_result` l.4264, `inspect_bursts` l.2210.
5. *Outputs*: `process_bursts` l.4627 (about 470 lines, multiprocessing via `_mp_worker.py`), `_save_burst_results_fast` l.663, `write_containers` l.816, `write_state_lifetimes` l.577, `save_fit`, `save_settings`/`load_settings`, `optimize_hyperparameters` l.5420, `auto_optimize`, `auto_extract_irf_bg`.

**3. Qt LOC**: `wizard.py` 5667 (217 methods; roughly lines 2270-3185 are widget building, 3040-3160 `connect_signals`; science and UI interleaved), `utils.py` 749 (8 Qt hits: file list widgets). No `.ui` files. Qt-free: `_mp_worker.py` 421, `core/export.py` 212, `backend/services.py` 80, `interpolate.py` 10. emtk: `gui/app.py` 422.

**4. Qt-free logic**: only the pieces above. The fit settings are exposed as Python properties on the wizard that read Qt spin boxes (`tau`, `gamma`, `shift`, `irf_start`, `min_photons`, `fix_tau`, ... l.869-1450), and `process_bursts` reads them; `burst_analysis` writes into the wizard's widgets (`_apply_irf_bg_to_mle_widget`, tool.py:1748). So there is no model to delegate to; extracting one is the first card. `backend/services.py` only resolves files and contract (`burst_mle.workflow.prepare`, `burst_mle.contract.describe`).

**5. emtk app**: `gui/app.py` `BurstMleGui`/`BurstMleApp` takes the wizard (`self.wizard`, 4 uses: `process_bursts`, `burst_files`, `irf_background_patterns`, `state_lifetimes`). It has docks Controls, Fitted Lifetimes, Decay and IRF Fits, Burst Lifetime Distribution, with its own mirrors `tau1`, `tau2`, `fit_from_ch`, and the plots are **simulated** (decay: `np.linspace`/`np.exp` at app.py:280-290; lifetime histogram: `np.exp` at l.335-338). It is used **only** by `burst_analysis/gui/tool.py:421-460` (`_mle_panel`), where the real wizard is created, then hidden (`wizard.setParent(host); wizard.hide()`) and the host shows the app. I did not run it, but reading the code, the visible parameters of the MLE step there are the mock's, not the wizard's. The standalone entry (`wizard.py`) has no emtk path. Qt imports in `app.py`: none beyond the `emtk_help_guide` shim (grep `qtpy|PyQt|chisurf\.gui`: only l.28). Missing `gui/help.md`, `gui/guide.json` (see summary).

**6. Tests** (8 files, 59 test functions): `test_dock_shell` (8, builds the wizard), `test_file_list` (5), `test_mle_gui_end_to_end` (19, builds the wizard and runs the fit, 596 lines), `test_state_split` (11); Qt-free: `test_burst_photon_slice` (5), `test_fit_plot_curves` (7), `test_mle_fit_simulation` (2), `test_mle_workflow_services` (2). Repo: `test/gui/test_mle_frozen_inputs.py` (not read). No test touches `BurstMleApp`.

**7. Tree and board**: ` M gui/app.py` (14 insertions, 7 deletions: tooltips). **Dirty, another agent.** Board: no claim.

**8. Proposed cut** (the whole plugin is blocked until ML0 is decided):
* **ML0 Settings model (reviewer decision; large)**: Qt-free `core/settings.py`/`gui/model.py` that the wizard properties delegate to (`tau`, `gamma`, IRF, range, fix flags, model name, dynamic params, `_capture_current_ui_state`/`_apply_ui_state` l.1810-1883, `apply_settings_payload` l.5569). Behaviour-preserving, wizard stays the Qt UI. Must not move `process_bursts`. Decision: whether `process_bursts` and the subprocess pool (`_mp_worker.py`) are moved to a function in `core/` in a second card (ML1) or stay; the subprocess worker and `batch_fingerprint`/`stamp` logic (l.4531-4620) make this the riskiest cut.
* **ML1 Processing engine out of the wizard**: `process_bursts`/`make_vv_vh`/`read_burst_analysis` take the model and a progress callback; wizard calls it. Tests: `test_mle_gui_end_to_end`, `test_state_split` stay green. Depends on ML0.
* **ML2 Files stage** (burst, IRF, background lists; file dialogs through `FileDialog`). Depends on ML0.
* **ML3 Parameters form**: spec for current file/detector/range/min photons, IRF block, fit-parameter table (`data_table`, editable, with the existing `_MleParameterRows` columns), model and dynamic rows, split-by-state toggle. Depends on ML0.
* **ML4 Plots**: replace the simulated decay and lifetime plots with the real "All selections" and "Inspected burst" plots from the model (fit, residual, IRF), and the fitted-lifetimes `data_table`. Depends on ML1, ML3.
* **ML5 Actions, settings I/O and hosting**: Run/Restart/Save defaults, load/save settings (`FileDialog`), auto-optimise, hyper-parameter search, auto IRF/background extract, `burst_analysis` `_mle_panel` and `apply_irf_background_to_mle` re-pointed at the model; add `entrypoints.emtk`. Must not change the companion contract (`write_containers`). Depends on ML1-ML4. **Blocked/decision**: the detector-definition stage (use `ChannelDefinitionWidget`, standalone only), the multiprocessing pool under emtk (a subprocess worker, not a `SnapshotJob`), `optimize_hyperparameters`.

---

## burst_analysis

**1. Entry points**: `gui` = `chisurf.plugins.burst.burst_analysis.gui.tool:BurstAnalysisTool`; no `cli`/`services`/`emtk`; `optional_requires` lists 13 step plugins. `__init__.py` (57 lines) loads the tool lazily.

**2. Stages**: the plugin is the pipeline shell, `BURST_PANELS` at `gui/tool.py:~590-735` (14 entries, each `{name, role, factory}`): 0 Setup Selection (`setup`), 1 Data Selection (`data`), 2 Burst Selection (`selection`, embeds `BurstSelectionTool(embedded=True)`), 3 Burst Fusion optional (`fusion`), 4 BVA, 5 2CDE, 6 Burst MLE, 7 Segmentation H2MM, 8 Segment MLE, then side tools Browser, Accurate FRET, Burst FCS, Kinetics (GS), Background, IRF and Background. Shell controls (`gui/app.py`): left navigation rail with search filter and completion badges (`_draw_sidebar` l.233, `_get_step_badge` l.494), header with title, breadcrumb chips, Back/Next/Fast-forward, Guide/Help (`_draw_header` l.144), status bar with progress and cancel (`_draw_status_bar` l.424). Own steps: *Setup Selection* (`setup_selection_app.py`, detector setup, tables, JSON editor via `TextEditor`) and *Data Selection* (`data_selection_app.py`: add files/folder, MMFDB browse/import, list with remove/clear). Context flow: `BurstWorkflowContext` (tool.py:27) filled by `_sync_*_context` (l.1230-1334), pushed into every step by `_apply_context_to_*` (l.1492-1917).

**3. Qt LOC**: `gui/tool.py` 1940 (panel factories, `BurstDataSelectionWidget` l.56, `BurstSetupSelectionWidget` l.300, the context bridge, status shims, Qt fallback overlay l.926-985). emtk: `app.py` 694, `data_selection_app.py` 391, `setup_selection_app.py` 2178. Qt-free: `api/workflow.py` 1419 (`BurstWorkflow`, `Setup`, `Bursts`, `Bva`, `H2mm`, ... Python API; `grep -n "api.workflow\|BurstWorkflow\b" gui/*.py` finds no GUI use).

**4. Qt-free logic**: the python API above is not the GUI's model. The GUI's state is `BurstWorkflowContext` (dataclass in the Qt module) and `workflow_context` on the tool; step navigation (`goto_next_step`, `fast_forward`, `process_current_step`, tool.py:1099-1160) is on the tool.

**5. emtk apps**: yes, `BurstAnalysisApp` hosts the shell in `ControlHost` (tool.py `__init__`, `ControlHost(self.app, ...)`, `setCentralWidget(self.host)`); a step that has an `app` attribute is drawn by the shell through `_panel_apps` (`_ensure_panel_loaded` l.1041); a step without one falls back to a Qt overlay (`_show_qt_fallback` l.953, "transitional"). What the Qt tool still adds: status shims (`_StatusTextLabel`, `_StatusProgressWidget`, `_StatusButton`, tool.py:740-795 mimic Qt widgets for steps that call them), a log handler to the status bar, the Qt overlay, window geometry. Qt imports needed by the apps: `app.py:25` `from qtpy import QtCore` (only `QtCore.QRectF` clip rect at l.590) and the help-guide shim; `data_selection_app.py`: shim only; `setup_selection_app.py:22,25`: `chisurf.gui.widgets.wizard.tttr_channeldefinition.setup_client` and `tttr_detector_setups` (Qt-free-ness not verified). The apps call back into Qt widgets: `data_selection_app.py` uses `self.widget.paths()`, `_browse_files()`, `_browse_folder()`, `_browse_mmfdb()`, `_remove_index()`, `clear()`, `mmfdb_payload()` (11 uses, grep `self\.widget\.`), i.e. they drive `BurstDataSelectionWidget` in tool.py. The step factories build the **Qt tools** (`BVATool`, `H2mmTool`, ...), not `create_app()` of the plugins, even though nine of those plugins declare `entrypoints.emtk`.

**6. Tests**: `test_emtk_workflow.py` (6 tests; constructs `BurstAnalysisTool()` via `qapp`, paints through `QtPainter`), `test_workflow.py` (32 tests, 974 lines; mostly the Qt-free python API plus tool context tests, 40 Qt-pattern matches, mixed). Qt-free count not separated.

**7. Tree and board**: ` M gui/app.py`, ` M gui/data_selection_app.py`, ` M gui/setup_selection_app.py`, ` M gui/tool.py`. `git diff --stat`: `setup_selection_app.py` 1880 insertions overall (588 lines at HEAD per `git show HEAD:... | wc -l`, 2178 in tree). **Dirty, large uncommitted work by another agent: do not start.** Board: no claim in `okf/agent-board.md`.

**8. Proposed cut** (blocked until the tree is clean and the step plugins have models; this plugin is last):
* **BA0 Reviewer decision, no code**: the shell should switch from `factory -> Qt tool -> .app` to `create_app()` of each plugin's `entrypoints.emtk` (nine already declare it); that makes the shell depend on BS/ML/H cards for `selection`, `mle`, `segment_mle`, `h2mm`.
* **BA1 Shell model**: Qt-free `gui/model.py` with `BurstWorkflowContext`, the panel registry, step state/badges, navigation (`goto_*`, `fast_forward`, `process_current_step`) and the status/task state now in the Qt shims. App takes the model, loses `from qtpy import QtCore`. Must not touch step apps.
* **BA2 Context bridge**: replace `_apply_context_to_*` (tool.py:1492-1917, about 430 lines poking Qt widgets) by a uniform `apply_workflow_context(dict)` on each step's model (H2mm already has one, `H2mmTool.apply_workflow_context` l.1953). One card per group of steps is too big; do it per plugin inside that plugin's cards (BS6, ML5, H5) and keep this card to the shell side (dispatch).
* **BA3 Data selection stage**: `BurstDataSelectionWidget` logic (paths, `_on_paths_committed`, `_import_path_to_mmfdb` l.234-300) into a model; app stops calling `self.widget.*`. MMFDB browse dialog needs an emtk sample picker (same open item as BS6).
* **BA4 Setup selection stage**: only after the dirty `setup_selection_app.py` is committed or dropped; then its model from `BurstSetupSelectionWidget` (l.300-350).
* Final: `entrypoints.emtk`, remove Qt fallback overlay and status shims once every step has an emtk app. Not an agent card before the above.

---

## burst_h2mm

**1. Entry points**: `gui` = `chisurf.plugins.burst.burst_h2mm.gui.tool:H2mmTool`; `cli` = `h2mm=...cli.main:cli`; `services` = `backend.services:register_services`; RPC `burst_h2mm.jobs.compute` (long-running), `workflow.prepare`, `contract.describe`; `menu_hidden: true`; `optional_requires: ndxplorer`. No `emtk`.

**2. Stages** (`grep -n -E "^    def |^class " gui/tool.py`):
1. *Folder* (toolbar `btn_folder` + drop-enabled `_FolderLineEdit` l.76, `_select_folder` l.899).
2. *Settings tab* (`_build_settings_tab` l.374): Model selection (min states, max states, criterion, scan patience), Optimisation (engine, restarts, seed, photon table HDF5/CSV, max iterations, min photons/burst, macro-time scale, nanotime divisors, decoder + decoder seed, state photons PTU/sidecar/write).
3. *Channel Definitions tab* (`_build_channels_tab` l.547, `_refresh_detector_combos` l.585): FRET pair assignment per detector stream (`_detector_streams` l.853).
4. *Run*: Run, Restart, Stop (`_run_analysis` l.944, `_fit_worker` l.1054 with task progress and ETA, `analysis_cache`), Bootstrap uncertainty (`_run_uncertainty` l.1137), LL scan (`_run_llscan` l.1257 with live plot and `LikelihoodScanDialog` l.109), Save plot, Dwells in ndX (`open_dwells_in_ndx` l.1188), settings save/load.
5. *Results* (`_build_plot_docks` l.622, seven docks): dwell FRET (E histogram or E-S scatter), transition density (TDP) with arrows, model selection (BIC/ICL), dwell times, nanotime with state filters, rates matrix, burst path with navigation (`_rebuild_nav_bursts` l.1871).

**3. Qt LOC**: `gui/tool.py` 1998 (pyqtgraph plots, QDialog, drag-drop; seven plots in about 700 lines, l.1364-1930). emtk: `gui/app.py` 532. Qt-free: `core/` 3,812 (`analysis.py` 1016, `export.py` 514, `engines.py` 395, `surrogate.py` 404, `decays.py` 300, `h2mm.py` 374, `state_tttr.py` 266, `photons.py` 231, `h2mm_tttrlib.py` 174, `surrogate_bff.py` 132), `backend/services.py` 680, `api/` 406, `gui/client.py` 81, `cli/main.py` 164. Board lines 1598-1621 and 2005-2010 describe backend work (engine routing, surrogate) in `core/`, which these cards must not touch.

**4. Delegation**: yes; `tool.py:53-57` imports `H2mmSettings`, `StreamSettings`, `run_analysis`, `write_result_tables`, `ENGINES`; `_gather_settings` (l.872) builds `H2mmSettings` from the widgets; `_fit_worker` runs `run_analysis`. What is missing is a Qt-free holder for the settings and result (`self._result`, `self._bundle`, `self._uncertainty`, `self.data_folder` live on the tool).

**5. emtk app**: `gui/app.py` `H2mmGui`/`H2mmApp`, hosted in `tool.py:_build_ui` (`ControlHost`, l.252-262; `toolbar`, `dock_area`, status label are built then hidden). Controls drawn by the app: Run, Restart, Stop, Bootstrap, LL Scan, Guide, Help, min/max states, criterion, engine, restarts, max iters, min photons, burst-folder label, Open Dwells in ndX (about 12 of about 20 settings; **no** folder picker, no seed, photon table, macro-time scale, divisors, decoder, state-photon outputs, no channel stage). Docks: Controls, Rate matrix, TDP with gate, Dwell time. It reads `tool.btn_run.click()`, `tool.sb_min_states`, `tool.cb_criterion`, `tool._result`, `tool._fit_task`, `tool.open_dwells_in_ndx` (grep `getattr\(self\.tool|self\.tool\.`). **Fake data**: demo rate matrix (app.py:398-421), simulated transition clusters with `np.random` (l.462-467), invented dwell curves (l.490-503); none of the model-selection, nanotime, dwell-FRET, burst-path plots exist in the app. Qt imports in `app.py`: none (`grep qtpy|PyQt|chisurf\.gui` finds only the `emtk_help_guide` shim at l.75). What the Qt tool still adds: toolbar, dock layout persistence (`_save_dock_layout` l.806), folder drop, `LikelihoodScanDialog`, progress dialogs (`_make_progress` l.911), settings persistence, `closeEvent`.

**6. Tests** (14 files, 94 test functions): Qt-free `test_ab_vs_h2mm_c`, `test_backend_routing`, `test_engine_cancellation`, `test_examples`, `test_export`, `test_h2mm_engine`, `test_ndx_compat`, `test_services`, `test_state_decoding`, `test_surrogate*`. Qt-touching: `test_gui.py` (6 tests, 290 lines, builds `H2mmTool`), `test_dwell_censoring.py` (5, 3 Qt hits), `test_state_decays.py` (9, 5 Qt hits).

**7. Tree and board**: ` M README.md`, ` M gui/app.py` (57 insertions, 18 deletions). **Dirty, another agent.** Board: lines 1598-1621 (engine routing, touches `core/{engines,analysis,surrogate}.py` and `burst_gs`) and 1949 (ndX call sites in several plugins including burst_h2mm, "own hunks only"), 2005-2010 (surrogate, status done): no GUI claim on `gui/`, but check status of the 1949 entry before touching ndX launching.

**8. Proposed cut**:
* **H0 Model**: Qt-free `gui/model.py` holding `H2mmSettings`, `StreamSettings`, folder, result, uncertainty, scans, and the actions (`run`, `restart`, `stop`, `bootstrap`, `ll_scan`) through `SnapshotJob` + `run_analysis`; app takes the model instead of `tool`. Must not touch `core/`, `backend/`, `api/`. Depends on a clean tree for `gui/app.py`.
* **H1 Settings form**: spec `gui/h2mm.view.json` with Model selection and Optimisation (all about 20 controls above), folder picker with `FileDialog`, settings save/load. Depends on H0.
* **H2 Channel stage**: FRET pair assignment per stream (a `table`/`data_table` of detectors with combo cells) or `ChannelDefinitionWidget`; reviewer decides which. Depends on H0.
* **H3 Core result plots**: dwell FRET, TDP with arrows, rates matrix, replacing the demo curves; real data only. Depends on H0.
* **H4 Remaining plots**: model selection (BIC/ICL), dwell times, nanotime with state filters, burst path with navigation. Depends on H0, H3.
* **H5 Uncertainty, LL scan, hand-off**: Bootstrap and LL scan with a window instead of `LikelihoodScanDialog`, Save plot, Dwells in ndX (external viewer launch: reviewer decides how the emtk ndX window is opened, cf. commit 30eb376), `apply_workflow_context` on the model for `burst_analysis`, `entrypoints.emtk`, guide update (`gui/guide.json` 65 lines targets Qt names). Depends on H0-H4.

---

## trace_browser

**1. Entry points**: `gui` = `chisurf.plugins.tttr.trace_browser.gui.tool:TraceBrowserTool`; `cli` = `trace-browser=...trace_browser.cli:cli`; `services` = `backend.services:register_services`; RPC methods in `manifest.json` (files list, load trace, export CSV, metadata). `__main__.py` (23) and `__plugin__.py` (14) for stand-alone launch. No `emtk`.

**2. Stages** (`TraceBrowser.__init__` l.388-850: "Two-page layout"): 
1. *Setup* (page0): `DetectorWizardPage` ("Setup definition"), Continue (`_on_continue` l.850).
2. *Browser* (page1): Select-setup back button (`_on_back_to_setup` l.865), folder label and Open (`_on_pick_folder` l.873), Include subfolders, rating filter combo, bin window [ms] (`QDoubleSpinBox`), Y min/max spin boxes (`ScientificDoubleSpinBox`), Clear, Clear caches, file table (`NoHoverSelectTable`: name, size, rating via `StarRatingWidget`/`StarCombo`, notes), trace plot (`IntensityPlotWidget` from `plugins/tttr/intensity_trace`, 1724 Qt lines, `plot_trace_and_histogram`), annotation `QTextEdit`, tools row: Export (copy files), CSV, DOCX, Transfer to analysis (`_on_transfer_to_analysis` l.2219), Time window (`_on_transfer_to_tw` l.2332), ndX (`_on_open_in_ndxplorer` l.2399), Delete selected (trash folder, `_on_delete_selected` l.1833), drag and drop of a folder (l.1786-1820), per-folder metadata `.json` (`_load_meta`/`_save_meta`, debounced).
`gui/tool.py` (144 lines) adds the `ChisurfDockTool` shell, a toolbar with the same actions, a Subfolders checkbox and a Help dialog.

**3. Qt LOC**: `__init__.py` 2631 (`StarCombo` l.157, `StarRatingWidget` l.203, `NoHoverSelectTable` l.350, `TraceBrowser` l.387-2631: about 460 lines of widget building, about 60 of scanning and table fill l.927-1220, plot, the rest are handlers and exports), `gui/tool.py` 144; about 2.8k. The plot widget is a second Qt dependency (`intensity_trace/__init__.py`, 1724 lines, not counted). Qt-free: `core/trace.py` 182, `core/metadata.py` 35, `api/` 216, `backend/services.py` 123, `gui/client.py` 121.

**4. Qt-free logic and delegation**: partial. `TraceBrowser` calls `self._client.get_metadata` (l.888), `set_metadata` (l.923), `load_trace` (l.1654) and `export_csv` (l.2014), so metadata, trace compute and CSV export are already behind `TraceBrowserClient`. It also keeps **duplicates** of the Qt-free code (`_meta_path/_load_meta/_save_meta` l.134-155, `_trace_signature`, `_cache_dir_for`, `_load_trace_cache`, `_compute_trace_cached` l.1462-1577 versus `core/trace.py` and `core/metadata.py`), used as fallback (l.1659). Scanning, filtering and the table model (`_scan_and_fill`, `_refresh_list`, `_apply_filter`, `_filter_accept`, `_allowed_exts_for_setup`) are in the widget; `api/io.py:list_files` is the Qt-free counterpart (not verified for equal behaviour).

**5. emtk app**: none (`ls gui`: `__init__.py`, `client.py`, `tool.py`). Nearest emtk pieces: `chisurf/emtk/channel_definition.ChannelDefinitionWidget` (setup stage), `chisurf/emtk/jobs.SnapshotJob` (precompute traces, `_precompute_all_traces` l.1577), the table helper `data_table` section (file list); no emtk trace plot exists in `tttr/intensity_trace` (Qt only; `grep -rln trace` over `tttr/*/gui/app.py` finds only `microtime_histogram` and `tttr_time_windows`, not read for a reusable trace plot).

**6. Tests**: `test/test_api.py` (4, Qt-free), `test/test_manifest.py` (1, 1 Qt hit), `test/test_widgets.py` (3, constructs `TraceBrowser()` under `qtbot`; skips when `tttrlib`/pyqtgraph are missing). 8 tests total; the plugin dir is `test/`, not `tests/`.

**7. Tree and board**: `git status --short -- chisurf/plugins/tttr/trace_browser`: clean (empty). `grep -n trace_browser okf/agent-board.md`: line 1949 only, an ndX call-site entry ("own hunks only") from another stream; check that it is closed before touching `_on_open_in_ndxplorer`.

**8. Proposed cut** (clean tree; the only plugin of the five that can start now, since nothing is mid-edit):
* **T0 Model and de-duplication**: Qt-free `gui/model.py` (current folder, setup settings, selected channels, file rows with rating/notes, filter, window ms, y range, selection); table scan and filter from `api/io.py:list_files`; delete the duplicated cache/meta code in `TraceBrowser` in favour of `core/`. Qt widget keeps working through the model. Must not touch `core/`/`api/` behaviour (add fields only if a test demands it).
* **T1 Setup stage**: `ChannelDefinitionWidget` for setup, Continue/Back, selected channels (`_build_channel_labels` l.1706). Depends on T0.
* **T2 Browser stage**: folder open with `FileDialog` and drop-folder, subfolders, filter, bin window, y range, file table as editable `data_table` (rating as an int/choice column, notes as text), selection, clear, clear caches. **Reviewer decision**: the 5-star `StarRatingWidget` is a custom widget; either a choice column (0..5) or a new emtk widget with tests. Depends on T0, T1.
* **T3 Trace plot and annotation**: trace plus histogram with `implot` (counts per channel, labels, y range) over `SnapshotJob` precompute; annotation text box saved to metadata. Depends on T2. **Decision**: new emtk plot vs reuse of an existing emtk trace plot (`intensity_trace` has only a Qt widget).
* **T4 Export and hand-off**: Export (copy files), CSV, DOCX (optional `python-docx`), delete to trash with confirmation, Transfer to analysis, Time window, ndX hand-off (external viewers: reviewer decides how the emtk ndX/`tttr_time_windows` windows are launched), guide, `entrypoints.emtk`. Depends on T3.

---

## Commands used

`grep -rl '"id": "<id>"' chisurf/plugins --include=manifest.json` (5 ids); `wc -l`/`find ... -name '*.py' -o -name '*.json'` per plugin; `grep -n -E "^(class |def )|^    def "` on each Qt file; `grep -c -E "qtpy|PyQt|pyqtgraph|chisurf\.gui|QtWidgets|from chisurf import gui"` per file; `grep -o 'getattr(self\.tool, "[A-Za-z_]*"' gui/app.py | sort | uniq -c`; `grep -n -E "BurstMleApp|BurstSelectionApp|ControlHost" ...`; `git status --short -- <plugin dir>`; `git diff --stat -- <dir>`; `git log --oneline -3 -- <file>`; `git show HEAD:<file> | wc -l`; `grep -n -E "burst_selection|burst_mle_analysis|burst_analysis|burst_h2mm|trace_browser" okf/agent-board.md` (hits at lines 1598, 1621, 1949, 2005, 2009, 2010 only: burst_h2mm backend/engine work and an ndX call-site sweep, no claim on any `gui/` file); `grep -c '^\s*def test_'` per test file. Not verified by running: any Qt widget behaviour, the hosted apps' on-screen content (only read from code), whether AutoForm specs support conditional sections, and which of the Qt-free-looking imports (`tttr_detector_setups`, `setup_client`) are really Qt-free.

## Reviewer notes (2026-10-01)

Verified against the source, not taken from the hand-over: Qt line counts (`burst_selection/gui/tool.py` 4176,
`gui/app.py` 2166, `burst_mle_analysis/wizard.py` 5667, `trace_browser/__init__.py` 2631,
`burst_analysis/gui/tool.py` 1940 against the survey's "about 1.9k"), `trace_browser` clean tree, and the
**invented data**: `burst_mle_analysis/gui/app.py` (around lines 280-340) draws a synthetic IRF and decay from
`np.exp`/`np.linspace` and a synthetic lifetime histogram from `self.tau1/tau2`; `burst_h2mm/gui/app.py` (around
lines 395-505) draws a hard-coded `demo_rates` table and a seeded `np.random.normal` FRET scatter. These apps look
like analyses of the user's data and are not. Recorded in `okf/references/known-issues.md` and as a PRD-153 rule.

Not checked by the survey agent and still open: whether AutoForm specs support conditional sections, and whether
`tttr_detector_setups` and `setup_client` are really Qt-free. Card boundaries below are proposals: the reviewer turns
them into task cards only after the owner's tree is clean for that plugin.

**Start order that is possible today:** only `trace_browser` has a clean tree and no claim; `burst_selection`,
`burst_mle_analysis`, `burst_analysis` and `burst_h2mm` each have uncommitted edits to their `gui/app.py`.
