# emtk port report: `burst_h2mm` (PARTIAL: H-X, H0, H1, H3 core done; H2, H4, H5 open)

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
