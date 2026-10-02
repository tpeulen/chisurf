# emtk port report — `burst_fusion` (upgrade, audit-all row 29)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_fusion` / `chisurf/plugins/burst/burst_fusion` |
| Port type | B (run port): at HEAD the Qt `BurstFusionTool` drew `BurstFusionApp` whose buttons called the model synchronously, with its own demo loader; the stream gave the app a `FusionController` (worker, settings files, report, MMFDB picker) used by both hosts |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | (second pass, real-input: section 6a) `ab54d527b` baseline; `a2ca536f1` emtk app at parity with the Qt tool; evidence commit "burst_fusion: evidence and report". Related: `cf90cf323` (burst_2cde axis test measures the drawn range) |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `core/fusion.py` (cancel check), `gui/app.py`, `gui/tool.py` (closes the app),
`gui/view_model.py` (cancel check), `manifest.json` (emtk entrypoint), `tests/test_gui.py` (help/guide now in-emtk); untracked
`gui/controller.py`, `tests/test_native.py`. All committed with the app.

## 2. Parity checklist (`before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt (HEAD) | Stream's emtk | Now |
|---|---|---|
| Demo (toolbar action, progress in the status reporter); Estimate / Run synchronous | worker for all three | same; frames at 10 Hz while running (was continuous) |
| result: the form's text ("428 → 283 bursts (125 fused …)") | plus the controller repeating the model status | once |
| — | Open folder, MMFDB, load/save settings, export report (gained) | kept; one sized dialog per action (was one full-viewport "input / output" dialog with a JSON filter for the folder too) |
| drop (host → app) set any path as the folder | same | folder or container, else "Burst fusion reads a burst-analysis folder; … is not one." |
| workflow API `set_folder`, `set_channel_settings`, `output_folder`, `process_bursts` | on the app too | unchanged |

Shared drawing, fixed: the fragments histogram (log y) auto-fitted the bar tops only (20–158 on the demo: the 3-fragment bar on
the floor, the 1-fragment bar past the top). A first `COND_ONCE` limits request on an already-drawn plot is not applied by
emtk (and it switches auto-fit off), which left the axis at 1e-6–1 in the live order of events
(`after_live_1200x800.png` is that order). Now applied with `COND_ALWAYS` whenever the bars change, held otherwise; integer
fragment ticks. Guide: targets were looked up among buttons only, so `folder`, `threshold`, `max_gap_ms` (spec fields), `Load demo`
and `Summary` were never found, and the `await` steps never waited; now both rect sources, those names, `wait_for_controls`.

## 4. Automated evidence

```
after: 71 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_fusion
compare: exit=0   (lost [] / stale [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: Demo/Estimate/Run on a worker; the gained file actions.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_fusion -q -p no:cacheprovider
64 passed in 68.88s
```

`test_emtk_fusion_parity.py` (12): the plugin's demo fused by the Qt tool (subprocess, own settings folder) and by the emtk app
(own demo folder — the shared cache already holds fused folders, and the writer then names the output `…_0`) gives the same
output name, files, status and summary, and 283 bursts is nearer the declared 300 molecules than 428; stop before writing; the
result once; settings round trip, invalid settings, report; errors; per-action dialogs, folder by dialog and drop; the fragments
axis read from the drawn plot after the plot existed empty; guide targets (buttons and form fields); draws; Qt-free; tooltips.

Deliberate breakage, round 1: fragments limits removed → axis test failed; drop validation removed → errors test failed. Round 2:
controller status copy restored → status-once test failed; the Summary alias removed → guide test failed. The ONCE-only call
(the first fix) → axis test failed `(1e-06, 1.0, [158, 105, 20])`. All restored.

Measurement trap recorded: a limits test that checks only the *request* passed while the drawn axis was 1e-6–1. Read the plot's
range at `end_plot`, on a plot drawn before the data arrives.

## 6a. Real-input coverage (second pass) -- every control -> the test that operates it

`tests/test_emtk_fusion_clicks.py` (35 tests passing + 2 strict xfails) presses and releases the pointer at the rectangle a control was drawn
in (`app.item_rects` for the buttons, `form_state.rects` for the spec's fields, the drawn text for dialog buttons), types with `key` (and pastes
through `emtk.clipboard.receive` + Ctrl+V where a multi-line field would pair brackets), drags with `pointer_move` / `press` / `drag` / `release`,
wheels with `wheel`, and delivers host drops with `files_dropped`. Plugin total: `99 passed, 2 xfailed` (`python -m pytest chisurf/plugins/burst/burst_fusion`).

| Control (checklist item) | Test |
|---|---|
| Demo (generates, loads, status shows the declared truth) | `test_demo_click_generates_and_loads_the_demo_with_its_declared_truth` |
| Estimate (curve, summary table cells drawn, status, nothing written) | `test_estimate_click_gives_the_curve_the_summary_table_and_the_status` |
| Run (Fuse): folder, files, status, summary equal the Qt tool's (subprocess), nearer the declared 300 molecules | `test_run_click_fuses_writes_the_folder_as_the_qt_tool_did_and_reports_it` |
| Run / Estimate without or with a missing folder | `test_run_without_a_folder_and_with_a_missing_folder_say_why` |
| Stop fusion (running: cancel, previous results kept; idle: nothing) | `test_stop_click_cancels_before_writing_and_keeps_the_previous_results`, `test_stop_does_nothing_when_idle` |
| everything inert while a run is in flight (second Run, typing into the form, no edit lost) | `test_buttons_and_fields_are_inert_while_a_run_is_in_flight` |
| Folder field: typed path + Enter | `test_the_folder_field_takes_a_typed_path_and_enter_selects_it` |
| Open burst folder: dialog, click a folder, Choose, Cancel, close x | `test_open_burst_folder_dialog_choose_by_clicks_cancel_and_close` |
| file drop (folder, stray file, empty drop, the demo folder then estimated) | `test_a_dropped_folder_is_taken_and_a_stray_file_is_reported`, `test_a_dropped_demo_folder_is_what_the_estimate_runs_on` |
| MMFDB datasets: window, list row selected by a click, close x | `test_mmfdb_datasets_picker_lists_a_dataset_selects_it_and_the_window_closes`; Open selected / Cancel: `test_mmfdb_datasets_picker_open_selected_takes_the_folder_and_cancel_closes` (xfail, emtk gap 1) |
| P(same) >= (typed, clamped 0..1), Max gap (0..10000), Max fragments (0..1000) | `test_the_main_fields_take_typed_values_clamped_to_the_qt_ranges[7]` |
| a changed setting invalidates the estimate and says so; a higher threshold fuses fewer | `test_a_changed_setting_invalidates_the_estimate_and_says_so`, `test_a_higher_threshold_fuses_fewer_bursts_through_the_ui` |
| "P(same molecule) estimate" panel: Lag from, Lag to, Lag bins (5..500), Min pairs/bin, Pool files, Record grouping | `test_the_estimate_panel_opens_and_its_fields_and_toggles_are_operated`, `test_the_pooling_toggle_changes_the_estimate_through_the_ui` |
| TTTR file type | `test_the_tttr_file_type_field_is_typed` |
| Detector definitions: expand, edit, Apply, invalid refused | `test_detector_definitions_expand_are_edited_applied_and_refused_when_invalid` |
| Save settings (dialog, typed name, Save writes JSON) / Load settings (click file, Open) / broken file | `test_save_settings_writes_the_json_and_load_settings_reads_it_back`, `test_loading_a_broken_settings_file_says_so_and_changes_nothing` |
| Export fusion report (refused without an analysis, then written) | `test_export_report_needs_an_analysis_then_writes_the_statistics` |
| Cancel and close x of the three file dialogs | `test_the_settings_dialogs_cancel_and_close_buttons_write_nothing` |
| plot tabs (All, P(same), Proximity ratio, Photons, Duration, Fragments) | `test_each_plot_tab_is_clicked_and_shows_its_own_plot` |
| plot drag pan / wheel zoom | `test_a_drag_pans_a_plot`; `test_the_wheel_zooms_a_plot` (xfail, emtk gap 2) |
| Guide: waits for Demo, Next greyed, Close Tour, walked to the end operating each control | `test_guide_click_starts_the_tour_that_waits_for_the_demo_button_and_next_is_greyed`, `test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control` |
| Help: Start Guided Tour, Close, Escape | `test_help_click_opens_the_window_whose_buttons_and_escape_close_it` |
| small window | `test_the_flow_works_in_the_small_window_too` |

### Defects the click tests found (fixed in the plugin's own app / model strings)

1. **Edits during a run were typed into the greyed form and silently lost**: `begin_disabled` greys the spec's fields but they still take typing; the
   worker's snapshot then overwrote the model, so the typed threshold vanished. The fields now draw against a throw-away copy while a run is in flight.
2. **A host file drop reached nothing outside Qt**: the app had `on_paths_dropped` (the Qt host's spelling) but no `files_dropped`, which the desktop and
   web hosts call. Added `files_dropped` (returns whether anything was dropped).
3. **The status said "press Analyze"** (three places, and help.md): there is no such button, it is Estimate. Reworded.
4. The earlier parity tests called `controller.on_paths_dropped` directly; the new ones go through the host's `files_dropped`.

Deliberate breakage (second pass): round 1, the in-flight copy removed -> `test_buttons_and_fields_are_inert_while_a_run_is_in_flight` failed; round 2,
`files_dropped` renamed -> both drop tests failed. Both restored (`diff` against the saved copy empty). Measurement trap: a worker still running when a
test ends can crash tttrlib's `get_supported_container_names` (segfault in the demo's burst search) when the next test starts; every test settles first.

Evidence: `click_1 ... click_11_*.png` from `scripts/capture_clicks.py` (demo generating and loaded, Estimate, threshold typed and the estimate
invalidated, Photons tab, lag bins typed in the opened panel, detector definitions, folder dialog, save dialog, guide waiting on Demo, help), read at
full size. `compare` exit 0.

### emtk gaps seen (not edited)

1. The MMFDB picker (`chisurf/emtk/dataset_picker.py`) buttons stop working after the first click. Repro (plain `ImApp`, no docks): stub client with
   one dataset; `pk = DatasetPicker(client=stub)`; `app = ImApp(gui=lambda: pk.render((0, 0, 1200, 800)))`; `pk.open()`; draw frames; press the row
   (selects, works); press "Open selected" or "Cancel" or "Refresh": nothing fires (the header x works).
2. The wheel never reaches an implot inside a `DockManager` window (as in kappa2_dist's report).
3. `input_text_multiline` pairs brackets and quotes while typing (typing `{"a": 1}` gives `{"a": 1}}""`); tests paste instead.
4. The numeric spec fields (`kind: float` / `int`) draw as plain text fields without the step arrows the spec's `step` implies (the Qt host draws the same).

## 7. Screenshots read

`before_populated.png` (Qt HEAD), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_live_1200x800.png`, `after_*`.

## 9. Persistence, guide, help, docs

Settings files via the controller (gained); window geometry host's. Guide content unchanged, now walkable. Docs: none.

## 10. Blocked / open

* emtk: a first `COND_ONCE` `setup_axis_limits` on a plot that already exists is ignored but disables auto-fit — worth a look
  in emtk (recorded, not changed: emtk is out of scope for this claim).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
