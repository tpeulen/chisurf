# emtk port report: `burst_h2mm` (H-X, H0-H5 implemented; parity compare pending the IMP.bff environment, see Open)

## Header
| Field | Value |
|---|---|
| Plugin | `burst_h2mm`, `chisurf/plugins/burst/burst_h2mm` |
| Commits | `78b2aab43` earlier-stream edits + pre-upgrade; `eacbbce97` H-X (invented data removed); the H0/H1/H3 commit that follows it |
| Entry | `entrypoints.emtk = ...gui.native:create_app` (new standalone app, no Qt tool behind it); the Qt `H2mmTool` still hosts the legacy `H2mmApp` |

## H-X: invented data removed
`gui/app.py` (the app hosted by the Qt tool) no longer draws the hard-coded demo rate matrix, the seeded `np.random.normal`
transition clusters or the `exp(-t/1.5)` dwell curves. It also read result fields that do not exist (`rates`, dict-shaped
`transitions`, `n_states`): `tool._result` is the `H2mmResult` summary, the arrays are on `tool._bundle.analysis`; so even after a real fit the
inventions were drawn. Now `gui/result_view.py` derives rates / TDP points / dwell histograms from the analysis; no fit = empty-state text.
Settings controls were local copies (three never reached the tool): they are views on the tool's widgets. `self.remember` was missing (the
earlier stream moved it into `TourTarget`): the app raised on every frame; fixed.
`tests/test_emtk_h2mm_no_invented_data.py` (14): no plot call without a fit; with a fit the plotted arrays equal the analysis; a different fit
gives different plots; AST guard (no numpy/random/literals in plot calls); real `H2mmTool` run through its worker.

## H0 / H1 / H3 core: standalone app
* `gui/model.py` `H2mmViewModel`: folder, donor/acceptor/aex channel lists, every `H2mmSettings` field, result, bundle, `compute()` (the unchanged
  `run_analysis` + `write_result_tables`), `stop()`, rate/state table rows, settings save/load. Run goes through `SnapshotJob`.
* `gui/h2mm.view.json`: all settings of the Qt Settings tab (Model selection 4, Optimisation 7, Output 7) plus folder and channels, a description on each;
  results are the spec's `table` sections. `gui/native.py`: docks (settings, rates+states, TDP, dwell times), Run/Stop/Guide/Help, drop of a folder.
* `gui/plots.py`: TDP with a gate (count computed from the points) and dwell histograms, shared with the legacy app.
* Guide retargeted to the real controls; the folder and Run steps wait for the real input.

Evidence: `before_qt_settings_tab.png`, `before_qt_dock_area.png` (Qt toolbar; the dock plots do not render offscreen), `after_empty_1200x800.png`,
`after_populated_1200x800.png`, `after_populated_800x600.png` (real fit of the in-repo BH sample: 2 states, 2980 bursts, 228338 photons; rates 8420 / 7719 1/s).

## Tests
`tests/test_emtk_h2mm_native.py` (13) on the in-repo BH SPC-132 sample (`burst_selection/tests/data`, copied to a temp folder): settings and defaults equal the Qt tool's
`_gather_settings`; typed + clamped fields; a real fit by clicks equals `run_analysis` (rates, E) and fills tables and plots; Stop; folder drop; toggle click; settings round trip;
guide targets drawn and the Run step released by the real press. Hermetic `tests/conftest.py` (temp HOME/settings/MMFDB, guard on real `~/.chisurf` excluding `logs`).
Deliberate breakage twice (rates transposed; engine ignored): both caught, restored.

## Checklist of the Qt controls
| Qt | emtk |
|---|---|
| folder picker, drop | typed/dropped folder field (FileDialog browse: open) |
| min/max states, criterion, patience; engine, restarts, seed, photon table HDF5/CSV, max iterations, min photons, macro-time scale, divisors, decoder + seed, state photons write/PTU/sidecar | all in the spec |
| detector pairs per stream (Channels tab) | channel lists as text (H2: data_table / ChannelDefinitionWidget open) |
| Run, Stop | done |
| Restart (force refit), Bootstrap, LL scan, Save plot, Dwells in ndX, settings save/load buttons | OPEN (model has settings save/load, no buttons yet; H5) |
| plots: dwell FRET, model selection, nanotime, burst path | OPEN (H4); TDP as scatter (the Qt heatmap: H3 follow-up); rates table instead of heatmap; dwell times done |

## Reuse
Used: `SnapshotJob`, `emtk.view_form` spec forms and `table` sections, `emtk_layout` (`button_row`, `LabelColumn`, `cap_widths`), `EmTkHelpWindow`/`EmTkGuidedTour`/`TourTarget`,
`emtk_test_input.Driver`. Not yet: detector editor (`channel_definition.py`), `FileDialog`. Duplicate flagged: the legacy `gui/app.py` and `native.py` share only `plots.py`; retire the legacy one when H5 re-points the Qt tool.

## Docs
OPEN: `docs/guides/19_h2mm_hidden_markov.md`, `30_h2mm_workflow_results.md` figures from the new app, plugin reference regeneration. `gui/help.md` unchanged (its text matches the controls).


## Second pass: H2, H4, H5
* H2: the donor / acceptor / Aex streams are choices over the detectors of the shared one-page detector editor (`chisurf/emtk/channel_definition.py`, a tab "Detector setup"); the model keeps the definition (`setup`) and builds the streams and the file type from it exactly as `H2mmTool._detector_streams` does (test: an edit in the editor reaches `model.streams()`).
* H4: tabs Dwell FRET (per-state dwell-E histograms with the model E, E-S scatter with an Aex stream), Selection (BIC/ICL), Decays (per colour and state, check boxes), LL scan, TDP, Dwell times, State path (Burst field, Dynamic bursts only). All arrays come from `gui/result_view.py`; tests compare them with the analysis.
* H5: Run keeps a fit of unchanged inputs (fingerprint, as the Qt tool), Restart refits, Stop, Bootstrap (20 resamples) and LL scan run on a snapshot through `SnapshotJob` with the backend's own `bootstrap_uncertainty` / `profile_likelihood`, Save plot (PNG of four plots through matplotlib Agg), Export dwells (CSV, `FileDialog`), Dwells in ndX (the Qt tool's call; says why when ndX cannot open), Save / Load settings (`FileDialog`, JSON incl. the detector definition), Browse folder (`FileDialog`). `ALGORITHM_VERSION` moved to `gui/model.py` (the Qt tool imports it).
* Tests `tests/test_emtk_h2mm_native.py` now 23; the plugin folder: 147 passed. Hermetic conftest ignores `~/.chisurf/logs` and `cache` (bytecode).
* Layout read at 1200x800 and 800x600 (`after_*.png`): the tab strips fit (a first layout with four tabs in a half-width dock overflowed and hid the last tab: fixed by stacking two tab regions); settings column widened; the shared detector editor's narrow-column clipping (see `fcs_filter_calculator` xfail) shows at 800 px: reported there.
* Docs: `docs/guides/19_h2mm_hidden_markov.md` (The H2MM tool paragraph and figure `19_h2mm_tool.png` from the new app), `docs/guides/30_h2mm_workflow_results.md` (dashboard text, ndX/export, figure `30_h2mm_results.png`), `docs/reference/plugins/burst_h2mm.md` regenerated for the new spec.

## Third pass: parity, the remaining plots, the workflow hand-off
* `emtk_port_parity compare burst_h2mm`: exit 0 (`lost []`, `stale_explanations []`, `untooltipped []`, Qt-free yes). `before.json` (65 Qt controls) comes from `scripts/capture_qt_inventory.py`, which shows the dock area and walks the settings and channels pages (the stock `before` finds 2 because `H2mmTool` hides its docks behind the emtk host); `after.json` (116 strings over every tab) from `scripts/capture_after_inventory.py`. `deliberate.json`: the Qt names an icon button by its tooltip and the shared detector editor has the same controls with their own captions (every one listed with its reason); renamed controls (Folder -> Browse folder, Run -> Run H2MM, the two photon-table and three state-photon check boxes, the Uncertainty group -> Bootstrap, the FRET-pair group -> the Data panel's choices).
* TDP is the 41x41 histogram as a heatmap (`result_view.tdp_histogram`; a test compares the drawn grid with `np.histogram2d`), with the gate box over it; the dwell-E plot has the kinetic-scheme arrows (`transition_arrows`: one per transition with a rate, width by rate) and the bootstrap E bands (`e_ci_bands`, only after Bootstrap), both asserted against the analysis.
* Workflow hand-off: `H2mmViewModel.apply_workflow_context` (folder, detector definition, bare file type); `gui/panel.py` `make_panel` hosts the app in a `ControlHost` with the methods the burst-analysis shell calls (`_set_folder`, `detector_page.load_data_into_tables`, `_refresh_detector_combos`, `_run_analysis`, `stop`, `apply_workflow_context`) and a hidden `toolAction_run` the shell's Next clicks. The panel fits through `chisurf.gui.task.run_in_background`, because the shell arms the advance and waits for a *registered task* to finish (a `SnapshotJob` is invisible to it: Next would never advance); a test asserts `running_tasks_under(panel)` is non-empty and the fit lands. `burst_analysis/gui/tool.py` `_burst_h2mm` now returns this panel. Not run end to end through the whole shell in this session.
* Whole plugin folder in one process: 151 passed. An earlier one-process run died once with a Qt segmentation fault in pytest-qt's `_process_events` after about 14 tests (a Qt object destroyed between tests); it did not recur and I could not pin it on a test.

## Open
* Nanotime / burst-path details beyond the Qt tool, the E-S error bars (Aex data: the sample has no Aex stream, so untested), the Qt `LikelihoodScanDialog`'s bootstrap CI lines on the scan plot.
