# emtk port report — `burst_irf_bg` (upgrade, audit-all row 31)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_irf_bg` / `chisurf/plugins/burst/burst_irf_bg` |
| Port type | B (run port): the Qt `BurstIrfBackgroundTool` draws `BurstIrfBackgroundApp` in a `ControlHost`, computes synchronously and hands the MLE patterns to the burst-analysis shell; the emtk app computes with the stream's `IrfBackgroundController` (a `BackgroundController` subclass) and an `mle_receiver` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | (second pass, real-input: section 6a) `43336be5a` baseline; `b3652dca8` core fix (background window); `f5cec2e6a` emtk app at parity with the Qt tool; evidence commit "burst_irf_bg: evidence and report". Docs corrected because of the core fixes: `b1b23fd18` (guide 15), `8e272e832` (guide 57) |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/app.py`, `gui/view_model.py` (cancel check, `tttr_provider`), `manifest.json`;
untracked `gui/controller.py`, `test/test_native.py`. All committed with the app.

## 2. Science: the background rate (core, `b3652dca8`)

On the demo measurement (the same non-burst stream on both detectors) both hosts reported 0.69 / 0.15 kHz; an exact tail
estimate of the same photons is 1.83 / 1.84. `extract_irf_background` fitted the tail above 80 % of the longest gap — a few
mostly empty bins. burst_background's quantile-seeded window moved to core (`background.seed_tail_window`) and serves both tools:
2.04 / 2.05 kHz. Everything downstream of `extract_irf_background` moved with it: the MFD reader's background on guide 57's
simulated folder (no dark counts) went from 0.335 kHz to 0.001 kHz; guide 15's numbers (from the earlier stalled tail fit,
`8e2c1f892`) were re-measured on their BH file against a direct truncated-exponential MLE and corrected, figures regenerated.

## 3. Parity checklist (Qt → emtk; `before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| detectors from the AutoForm detector page | emtk channel editor (inherited) | same |
| files pushed by the shell | own file inputs, MMFDB (inherited, gained) | same; folder drop skips the `.pto` container (burst_background fix) |
| Compute synchronous, error dialog | worker | worker; errors in the window; 10 Hz frames while running |
| Send to MLE → shell's `apply_irf_background_to_mle`; "Compute the IRF and background first."; "Sent IRF + background to MLE for N detector(s)." | `mle_receiver`, same messages | same |
| — | Export MLE patterns (`.npz`, gained) — dialog without the sized window the base now draws in | sized window; refused before a result |
| status line | drawn twice | once |

Shared drawing, fixed: results-table headers overlapped in a narrow pane (fixed widths). Guide: only the plot target existed;
`irf_bg_channels`, `files`, `min_photons`, `irf_bg_run`, `irf_bg_results` are recorded now and the Extract step waits for Compute.

## 4. Automated evidence

```
after: 34 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_irf_bg
compare: exit=0   (lost [] / stale [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: compute on a worker; errors in the window instead of a dialog; the gained inputs/export.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_irf_bg -q -p no:cacheprovider
16 passed in 30.10s
```

`test/demo_data.py`: SPC-130, 4096 micro-time channels, scatter IRF at 2.0 ns + flat background between 300 bursts (τ 4 ns).
`test_emtk_irf_bg_parity.py` (11): results equal the Qt tool's (subprocess) and the known IRF peak, equal rates on both
detectors; Send to MLE with and without a receiver, as the Qt tool; pattern export; errors; status once and frames while
computing; every guide target drawn and the Extract await released by a pointer press; folder drop; draws with fitting headers;
Qt-free; tooltips. Core guard: `test/plugins/burst/test_irf_background_window.py`.

Deliberate breakage, round 1: controller status copy restored → status-once test failed; export guard removed → export test
failed. Round 2: results rect not remembered → guide test failed; Compute press not tracked → await test failed. All restored.
Trap met again: the await test first read the button rect from a `RecordingPainter` frame and pressed in pixel frames — draw a
`PixelPainter` frame before reading rects you press.

## 6a. Real-input coverage (second pass) -- every control -> the test that operates it

`test/test_emtk_irf_bg_clicks.py` (42 tests passing + 2 strict xfails) presses and releases the pointer at the rectangle a control was drawn in
(`app.item_rects` for buttons and the guide's targets, `form_state.rects` for the spec's fields, the drawn text for dialog buttons), types with `key`,
drags with `pointer_move` / `press` / `drag` / `release`, wheels with `wheel`, and delivers host drops with `files_dropped`. Plugin total:
`58 passed, 2 xfailed` (`python -m pytest chisurf/plugins/burst/burst_irf_bg`).

| Control (checklist item) | Test |
|---|---|
| Compute: without files; with the demo the rows equal the Qt tool's (subprocess) and the IRF the demo was made with; table cells and plot drawn; status once | `test_compute_without_files_says_why_and_a_click_on_a_loaded_demo_gives_the_qt_tools_rows` |
| Stop computation (running: cancel, previous results kept; idle: nothing) | `test_stop_computation_cancels_and_keeps_the_previous_results`, `test_stop_does_nothing_when_idle` |
| everything inert while a computation runs (second Compute, Open TTTR files, typing, Clear files) | `test_everything_is_inert_while_a_computation_runs` |
| broken file -> the error in the window | `test_a_broken_file_reports_its_error_in_the_window` |
| Min photons/burst, Photon window, Time window, Dark-count floor, Micro-time binning: typed, clamped to the spec's ranges, shown | `test_each_parameter_is_typed_and_clamped_to_the_qt_ranges[15]` |
| a parameter changes what is found | `test_a_parameter_changes_what_the_extraction_finds` |
| Micro-time binning = the channel editor's microtime binning | `test_the_binning_field_and_the_channel_editors_microtime_binning_are_one_value` |
| Channel definition button / dock tab; editor sections (Setups, TTTR reading, Detectors); a typed routing channel reaches the detectors; tabs back and forth | `test_the_channel_definition_button_opens_the_editor_and_a_typed_routing_reaches_the_detectors`, `test_the_ptu_reading_section_lists_its_fields`, `test_the_dock_tabs_switch_between_the_parameters_and_the_channel_editor`; a typed list "0, 8, 2": `test_a_typed_list_of_routing_channels_arrives_as_a_list` (xfail, shared editor gap) |
| Send to MLE: before a result, with a receiver (the Qt words and the received detectors), without one | `test_send_to_mle_before_a_result_then_with_a_receiver_as_the_qt_tool_does`, `test_send_to_mle_without_a_receiver_points_at_the_export` |
| Export MLE patterns: refused without a result; dialog, typed name, Save writes every irf / bg pattern equal to the model's; Cancel and close x | `test_export_mle_patterns_needs_a_result_then_writes_the_npz_with_every_pattern`, `test_the_export_dialog_cancel_and_close_write_nothing` |
| Open TTTR files (the TTTR filter, click, Open; Cancel, close x) | `test_open_tttr_files_dialog_lists_measurements_and_open_adds_the_clicked_one`, `test_the_open_dialog_cancel_and_close_buttons_add_nothing` |
| Add TTTR folder | `test_add_tttr_folder_dialog_adds_the_measurement_in_it` |
| file drop (folder with a vendor file and its .pto container, stray file, empty drop) | `test_a_dropped_measurement_folder_or_container_is_handled_as_the_qt_tool_does` |
| Remove (per file), Clear files (also drops the result) | `test_each_listed_file_has_a_remove_button_and_clear_files_drops_files_and_results` |
| MMFDB datasets: window, row selected, close x | `test_mmfdb_datasets_picker_lists_a_dataset_selects_it_and_the_window_closes` (Open selected / Cancel: emtk gap 1) |
| results table: row click, header sort and flip | `test_a_click_on_a_row_and_on_the_headers_sorts_and_changes_no_result` |
| IRF plot: drag pan; wheel zoom | `test_a_drag_pans_the_irf_plot`; `test_the_wheel_zooms_the_irf_plot` (xfail, emtk gap 2) |
| Guide: Next, Prev, Close Tour, the Extract step waits and a press releases it, walked to Finish, Escape while waiting | `test_guide_click_starts_the_tour_whose_close_prev_and_next_buttons_are_clicked`, `test_the_tour_is_walked_to_the_end_and_waits_for_the_extract_button`, `test_escape_closes_the_tour_while_a_step_waits` |
| Help: Start Guided Tour, Close, Escape | `test_help_click_opens_the_window_whose_buttons_and_escape_close_it` |
| small window | `test_the_flow_works_in_the_small_window_too` |

### What the click tests found, and what changed (all in the plugin's own app)

1. **Four of the five parameters could not be set.** They were `drag_int` / `drag_float`: no typed entry, and a drag applied nothing (emtk reports a
   non-live drag only on release, with the old value). The authored spec `gui/irf_bg.view.json` declares every field with its range (min photons 2..100000,
   photon window 2..10000, time window 0.001..1000 ms, quantile 0..0.9, binning 1..64). The parameters now draw those spec fields (typed, Enter commits,
   clamped, a description tooltip each); the micro-time binning stays equal to the channel editor's value (`_sync_binning`).
2. **The results table was hand-drawn** (`begin_table`, cell by cell); it is now a `data_table` section (`gui/irf_bg_results_emtk.view.json`, source
   `results_rows`, sortable, a tooltip per column).
3. **Edits during a computation**: the greyed fields still took typing; they draw against a throw-away copy while a run is in flight.
4. **A host file drop reached nothing outside Qt** (`files_dropped` missing): added.
5. **The guided tour could not be finished by clicking** (same cause as burst_gs: the card's buttons sat under the dock windows): when no control is
   awaited the card draws in a transparent full-viewport window of its own; while a step waits the card stays in the root so the highlighted control
   keeps the click (Escape closes the tour then).

Deliberate breakage (second pass): round 1, the in-flight copy removed -> `test_everything_is_inert_while_a_computation_runs` failed; round 2, the binning
sync removed -> `test_the_binning_field_and_the_channel_editors_microtime_binning_are_one_value` failed. Both restored (`diff` against the saved copy empty).

Evidence: `click_1 ... click_12_*.png` from `scripts/capture_clicks.py` (the open dialog, a dropped measurement listed, typed parameters, computing, the computed
plot and table, the table sorted, the channel definition tab and its Detectors section, Send to MLE with no workflow, the export dialog, the guide, help), read
at full size; `after_*` and `after_populated_*` regenerated. `compare` exit 0 (35 controls, 0 without tooltip).

### Gaps seen (not edited; not this plugin's files)

1. The MMFDB picker's buttons stop working after the first click (repro in burst_fusion's report, section 6a).
2. The wheel never reaches an implot inside a `DockManager` window.
3. The shared channel editor (`chisurf/emtk/channel_definition.py`, the "Channel definition" tab) re-formats the routing channels from the parsed list every
   frame, so the comma of "0, 8" is eaten as it is typed and "0, 8, 2" arrives as [82] (the same class of bug burst_bva had in its own fields).
   Repro: open Channel definition > Detectors, click the routing field, Ctrl+A, type `0, 8`: the model holds `[8]`/`[82]`.
4. `EmTkGuidedTour.draw` (shared `chisurf/emtk/help_guide.py`) puts its card buttons in the current window; in a `DockManager` app they sit under the dock windows
   (worked around here and in burst_gs by the overlay window).
5. The detectors / PIE windows of the Qt original's embedded "Channel definition" wizard are the shared editor's sections; their other controls are covered by the
   editor's own tests, not here.

## 7. Screenshots read

`before_populated.png` (Qt HEAD), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_*`.

## 9. Persistence, guide, help, docs

Detector setups through the shared setup store; window geometry host's. Guide content unchanged, now walkable. Docs: guides 15
and 57 corrected for the core fixes (above).

## 10. Blocked / open

* The IRF plot shows the floor-subtracted, normalised histogram on a log axis; its near-zero floor bins draw as a solid band
  that hides the second detector (both hosts). Plotting the raw non-burst histogram (where the flat floor *is* the background
  the help describes) would read better — a display choice left for the plugin owner.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
