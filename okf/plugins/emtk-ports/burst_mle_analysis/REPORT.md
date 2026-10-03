# emtk port report: `burst_mle_analysis` (PARTIAL: ML-X done; ML0-ML5 open)

## Header
| Field | Value |
|---|---|
| Plugin | `burst_mle_analysis`, `chisurf/plugins/burst/burst_mle_analysis` |
| Commits | `78b2aab43` earlier-stream edits + pre-upgrade; `eacbbce97` ML-X; the entrypoint/report commit after it |
| Entry | `entrypoints.emtk = ...gui.app:create_app` (INTERIM: the app reads the Qt `MLELifetimeAnalysisWizard`, which it creates; no settings model yet = ML0) |

## ML-X: invented data removed (done)
The app drew a Gaussian IRF and an `exp` decay for any data, a lifetime histogram from its own `tau1`/`tau2`, and read wizard attributes that do not exist
(`irf_background_patterns`, `burst_files`: its status lines were always "default IRF", "Burst Files: 0"). Now:
* `fit_display.decay_curves` (new, Qt-free): the windowing/scaling that `plot_fit_result` did inline; the wizard calls it and keeps `wizard.fit_curves`; the app draws that. Same numbers as the Qt plot (tested).
* `wizard.burst_results` (rows of the last `process_bursts`) feed the lifetime histogram; `gui/fit_view.py` reads parameters, lifetimes, pooled state lifetimes, input status.
* Start value and fit window are the spec `gui/mle.view.json` over the wizard (typed, clamped; a change refits). Tau2/Fraction 1 had no wizard counterpart and are gone; the drag-rect on the plot (unitless index axis) is gone.
* `gui/help.md`, `gui/guide.json` added (the Fit step waits for the real press).
* Defects found and fixed on the way: `_fit_diverged` read the quality with `.get` (a `Fit2xResult` has none: no fit was ever flagged diverged); the tail fit's mapping result raised in `update_fit_ui` inside the Qt event loop (now `TailFitResult`, read by attribute); `test_mle_gui_end_to_end.py` read `/Users/tpeulen/dev/tttr-data` and was skipped everywhere: it now runs on the in-repo BH sample (20 pass), three of its assertions used removed pyqtgraph APIs and were updated to `Plot.series()`.

Fixtures: in-repo `burst_selection/tests/data/bh_spc132_sm_dna` (real photons; copied to a temp folder), fitted by the wizard's own `auto_extract_irf_bg` and `process_bursts`; no generated or external data. Hermetic `tests/conftest.py` (module-scoped temp HOME/settings/MMFDB so a wizard closed at module teardown cannot write to `~/.chisurf`; guard on the real one excluding `logs`: it caught exactly that).

## Tests
`tests/test_emtk_mle_no_invented_data.py` (18): no plot call without a fit; plotted arrays equal the wizard's curves and the Qt plot's series; follow a detector change; typed window/tau reach the wizard and change the plotted curves; Refit and Fit Bursts clicks (real batch) fill the histogram from the batch rows; AST guard; guide targets drawn, the Fit step released by the press. Plugin total `81 passed`.
Evidence: `before_populated.png`, `before_populated_batch.png` (Qt), `after_populated_1200x800.png`, `after_populated_800x600.png` (read).

## Open
ML0 settings model (wizard properties delegate to a Qt-free model), ML1 processing engine out of the wizard, ML2 files stage (data_table + FileDialog), ML3 parameters form (editable data_table), ML4 plots (inspected burst, state table), ML5 actions/settings I/O/hosting in `burst_analysis._mle_panel`, detector stage via `ChannelDefinitionWidget`; docs (guide 21 figures, plugin reference). Reuse used: `emtk.view_form`, `emtk_layout.cap_widths`, help/tour, `Driver`. Not yet: detector editor, `FileDialog`, `data_table`.
