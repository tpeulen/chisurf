# emtk port report: `burst_mle_analysis` (ML0-ML5 done, port complete)

## Header
| Field | Value |
|---|---|
| Plugin | `burst_mle_analysis`, `chisurf/plugins/burst/burst_mle_analysis` |
| Commits | `78b2aab43` earlier-stream edits + pre-upgrade; `eacbbce97` ML-X; `9d3e4a27d` Qt-free engine; `2a1ee532c` engine tables; `628c25a97` standalone emtk app |
| Entry | `entrypoints.emtk = ...gui.native:create_app` (standalone app, Qt-free) |

## ML-X: invented data removed (done)
The app drew a Gaussian IRF and an `exp` decay for any data, a lifetime histogram from its own `tau1`/`tau2`, and read wizard attributes that do not exist
(`irf_background_patterns`, `burst_files`: its status lines were always "default IRF", "Burst Files: 0"). Now:
* `fit_display.decay_curves` (new, Qt-free): the windowing/scaling that `plot_fit_result` did inline; the wizard calls it and keeps `wizard.fit_curves`; the app draws that. Same numbers as the Qt plot (tested).
* `wizard.burst_results` (rows of the last `process_bursts`) feed the lifetime histogram; `gui/fit_view.py` reads parameters, lifetimes, pooled state lifetimes, input status.
* Start value and fit window are the spec `gui/mle.view.json` over the wizard (typed, clamped; a change refits). Tau2/Fraction 1 had no wizard counterpart and are gone; the drag-rect on the plot (unitless index axis) is gone.
* `gui/help.md`, `gui/guide.json` added (the Fit step waits for the real press).
* Defects found and fixed on the way: `_fit_diverged` read the quality with `.get` (a `Fit2xResult` has none: no fit was ever flagged diverged); the tail fit's mapping result raised in `update_fit_ui` inside the Qt event loop (now `TailFitResult`, read by attribute); `test_mle_gui_end_to_end.py` read `/Users/tpeulen/dev/tttr-data` and was skipped everywhere: it now runs on the in-repo BH sample (20 pass), three of its assertions used removed pyqtgraph APIs and were updated to `Plot.series()`.

Fixtures: in-repo `burst_selection/tests/data/bh_spc132_sm_dna` (real photons; copied to a temp folder), fitted by the wizard's own `auto_extract_irf_bg` and `process_bursts`; no generated or external data. Hermetic `tests/conftest.py` (module-scoped temp HOME/settings/MMFDB so a wizard closed at module teardown cannot write to `~/.chisurf`; guard on the real one excluding `logs`: it caught exactly that).

## ML0-ML5: Engine and Standalone App (done)
* `9d3e4a27d`: Created `engine.py` - Qt-free engine handling burst loading, decays, IRF/background, auto binning, single-decay fit, and batch fitting. Parity tests added against wizard.
* `2a1ee532c`: Engine now writes `b?4` tables and keeps settings. Export parity tested.
* `628c25a97`: Standalone emtk app (`gui.native:create_app`) over the Qt-free engine. Features files and parameter data_tables, shared detector editor, inspected burst plots, batch processing, and settings I/O. Added real-input tests (`test_emtk_mle_native.py`).

## Tests
`tests/test_emtk_mle_native.py` and `test_emtk_mle_no_invented_data.py` verify that plots, parameters, and tables mirror the engine results.
Evidence: `after_detectors_1200x800.png`, `after_empty_1200x800.png`, `after_irf_1200x800.png`, `after_populated_1200x800.png`, `after_populated_800x600.png`, `after_tab_inspected_1200x800.png`, `after_tab_table_1200x800.png`.

## Open
None. Port complete and Qt-free.
