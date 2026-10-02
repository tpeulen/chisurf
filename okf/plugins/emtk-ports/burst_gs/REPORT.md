# emtk port report — `burst_gs` (upgrade, audit-all row 30)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_gs` / `chisurf/plugins/burst/burst_gs` |
| Port type | B (run port): the Qt `BurstGsTool` draws `BurstGsApp` in a `ControlHost`, fits through ChiSurfProgress and reports in its status bar; the emtk app fits with the stream's `BurstGsController` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | (second pass, real-input: section 6a) `6c499df76` baseline; `d4972bba0` emtk app at parity with the Qt tool; evidence commit "burst_gs: evidence and report" |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/app.py` (docks, report tables, the remaining parameters, emtk help/guide),
`manifest.json` (emtk entrypoint); untracked `gui/controller.py`, `test/test_native.py`. All committed with the app.

## 2. Parity checklist (Qt run → emtk run; `before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt `BurstGsTool` | Stream's controller | Now |
|---|---|---|
| fit off the UI thread, progress fraction + message, Cancel | worker; fraction dropped | progress bar with the optimiser's message; Stop |
| after a fit: "logL = …, k(1→2) = … /s, k(2→1) = … /s" | "Kinetics fit completed." | Qt line |
| no result: "The fit did not produce a result — see the report."; failure "The fit failed: …" | report text / "Error: …" | Qt messages |
| Export CSV: "Run a fit first." before a fit; suggests `<first table>.gs.csv` | always; `kinetics.csv` | Qt behaviour |
| drop: `.bur` paths added | `.bur` paths and folders (gained) | same, and says when nothing was added |
| — | one full-viewport chooser | sized dialog per action |
| — | continuous rendering | 10 Hz while fitting |

Shared drawing, fixed: the kinetics plot ("Parameter / Time" vs "Rate / Likelihood", numeric x, a draggable "Rate: 1000 s⁻¹"
line and a region drop target that fed nothing — `threshold_y`/`_last_dropped_region` were never read) is now one named bar per
transition k(i→j) (= `K[j, i]`, as the Qt status line reads the matrix), the simulated rates as markers in simulation mode, y room
above both (limits applied on change — see burst_fusion's emtk COND_ONCE issue); with the transition-time scan, the model's
scan series with real labels. HEAD's Qt plot was a placeholder "Expected Exchange Profile". Guide: only `guide`/`help` were drawn
targets of nine steps and nothing waited; now every target is recorded (spec-style attribute names, `Fit`, `Rates`, `bur_files`)
and the Simulate and Fit steps wait.

## 4. Automated evidence

```
after: 68 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_gs
compare: exit=0   (lost [] / stale [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: progress bar in the window instead of a modal dialog; status line in the controls pane instead
of the status bar; folder drops (gained).

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_gs -q -p no:cacheprovider
40 passed in 43.62s
```

`test_emtk_gs_parity.py` (13), on the tool's own simulation (k 3000 / 1000 /s, E 0.25 / 0.75): the same rate matrix, logL, status
line and report as the Qt tool (subprocess), both rates within 15 % of the simulated ones (2879 / 1017); the rates plot's labels,
truth markers and drawn y range; progress and frames while fitting, stop; errors, no result, failure; export refused before a fit,
the Qt file name after; drops; every guide target drawn; the Simulate and Fit awaits released by pointer presses; draws at both
sizes; Qt-free; tooltips.

Deliberate breakage, round 1: the old "Kinetics fit completed." → status test failed; `K[i, j]` instead of `K[j, i]` → rates-plot
test failed. Round 2: export guard removed → errors test failed; Fit press not tracked → await test failed. All restored.

## 6a. Real-input coverage (second pass) -- every control -> the test that operates it

`test/test_emtk_gs_clicks.py` (32 tests passing + 1 strict xfail) presses and releases the pointer at the rectangle a control was drawn in
(`app.item_rects` for buttons and the guide's targets, `form_state.rects` for the spec's fields, the drawn text for dialog buttons), types with
`key`, drags with `pointer_move` / `press` / `drag` / `release`, wheels with `wheel`, and delivers host drops with `files_dropped`. Plugin total:
`72 passed, 1 xfailed` (`python -m pytest chisurf/plugins/burst/burst_gs`).

| Control (checklist item) | Test |
|---|---|
| Use Simulation Mode (switches the input panel; Fit enabled; greyed Fit shows its hint and a click does nothing) | `test_the_simulation_checkbox_switches_the_input_panels_and_enables_fit` |
| Fit Kinetics: rates, logL, status, report equal the Qt tool's (subprocess), Rates / States table cells, plot | `test_fit_click_gives_the_qt_tools_rates_status_report_and_tables` |
| k(1->2), k(2->1), E state 1 / 2, Photon rate, Bursts, Photons/burst, Seed: typed, clamped to the spec's ranges, simulated truth = typed | `test_the_simulation_fields_are_typed_clamped_and_reach_the_simulated_rates`, `test_the_same_seed_gives_the_same_fit_through_the_ui` |
| States (2..5), Initial rate, Max iterations, Macro-time tick, Scan points: typed + clamped; 3 states give six transitions | `test_the_model_fields_are_typed_and_the_number_of_states_changes_the_tables` |
| Fix efficiencies, Scan transition time, Decode state path, Cross-check with H2MM | `test_the_four_checkboxes_are_clicked`, `test_scan_transition_time_and_decode_states_through_the_checkboxes_show_the_scan_plot` |
| Optimiser and Container choices (list, pick, Escape) | `test_the_optimiser_and_container_choices_are_picked_from_their_lists` |
| TTTR folder, Donor / Acceptor channels, Min photons, Max bursts | `test_the_data_fields_are_typed` |
| second fit replaces the result | `test_a_second_fit_with_new_settings_replaces_the_result` |
| progress bar, Stop fit, "Kinetics fit cancelled."; Stop idle | `test_progress_bar_stop_fit_and_the_cancelled_message`, `test_stop_does_nothing_when_idle` |
| every button and field inert while a fit runs | `test_the_buttons_and_fields_are_inert_while_a_fit_is_running` |
| failed fit / empty result messages | `test_a_failed_fit_and_an_empty_result_are_reported_in_the_window` |
| Open BUR files: dialog with the BUR filter, click file, Open; Cancel and close x | `test_open_bur_files_dialog_selects_files_by_clicks_and_open_adds_them`, `test_the_open_dialog_cancel_and_close_buttons_add_nothing` |
| Add burst folder | `test_add_burst_folder_dialog_adds_every_table_below_it` |
| file drop (tables, folders, stray file, empty drop) | `test_a_dropped_table_or_folder_is_added_and_a_stray_file_is_reported` |
| Remove (per file), Clear burst files (also drops the result) | `test_each_listed_table_has_a_remove_button_and_clear_removes_all_and_the_result`, `test_a_fit_on_a_dropped_table_reports_the_load_failure_in_the_report` |
| MMFDB datasets: window, list row selected, close x | `test_mmfdb_datasets_picker_lists_a_dataset_selects_it_and_the_window_closes` (Open selected / Cancel: emtk gap 1, as in burst_fusion) |
| Export CSV: greyed before a fit; dialog, typed name, Save writes the CSV; Cancel | `test_export_is_greyed_before_a_fit_then_writes_the_csv_the_qt_tool_wrote`, `test_the_export_dialog_cancel_writes_nothing` |
| Rates / States tables: row and header clicks (sort), no value changes | `test_a_click_on_a_table_row_and_header_changes_no_value_and_the_columns_have_tooltips` |
| FRET states / Kinetics dynamics tabs | `test_the_fret_states_tab_is_clicked_and_shows_the_state_lines` |
| rates plot: drag pan; wheel zoom | `test_a_drag_pans_the_rates_plot`; `test_the_wheel_zooms_the_rates_plot` (xfail, emtk gap 2) |
| Guide: Next, Prev, Close Tour, Escape while a step waits, awaited Simulate and Fit, walked to Finish by clicks | `test_guide_click_starts_the_tour_whose_close_prev_and_next_buttons_are_clicked`, `test_escape_closes_the_tour_even_while_a_step_waits_for_its_control`, `test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control`, `test_every_guide_target_is_a_real_control_that_can_be_clicked` |
| Help: Start Guided Tour, Close, Escape | `test_help_click_opens_the_window_whose_buttons_and_escape_close_it` |
| small window | `test_the_flow_works_in_the_small_window_too` |

### What the click tests found, and what changed (all in the plugin's own app)

1. **The settings had no typed entry and no limits.** The hand-drawn `input_float` / `input_int` / slider widgets are drags with arrow buttons in emtk:
   no way to type 4000 for a rate, a drag that applies nothing (emtk reports a non-live drag only on release, with the old value), and a step below
   zero reachable (a negative rate). The authored AutoForm spec `gui/burst_gs.view.json` already declares every field with its range (States 2..5,
   rates 0.1..1e7, E 0..1, ...). The settings now draw those spec fields (`emtk.view_form.draw_sections`: typed, Enter commits, clamped, a description
   tooltip each), grouped as before (Simulation Parameters or Data Input & Channels, Kinetic Model Settings, Extras). The Number of States slider
   (2..4) became the spec's 2..5 field.
2. **Hand-drawn tables.** The rate matrix and state table were `begin_table` drawings; they are now the spec's own `table` sections (`rate_rows`,
   `state_rows`: Transition / k / 1/k, State / E / Population), the Rates alias kept for the guide.
3. **Edits during a fit.** The greyed fields still took typing; they now draw against a throw-away copy while a fit runs (as in burst_fusion).
4. **A host file drop reached nothing outside Qt** (`files_dropped` missing): added.
5. **The guided tour was not usable by clicking on this layout.** The card was drawn into the root window under the dock windows: an emtk button is
   hovered only when no other window is under the pointer, so Close Tour, Prev and several Next presses (for instance step 5 at a dock edge) never
   arrived and the tour could not be finished. When no control is awaited the card now draws in a transparent full-viewport window of its own; while a
   step waits for its control the card stays in the root so the highlighted control keeps the click (Escape closes the tour then).
   `test_emtk_gs_parity.py::test_the_simulate_and_fit_steps_wait_for_their_controls` gained a frame between the pointer move and the press (the overlay
   window leaves one frame after it is closed).

Deliberate breakage (second pass): round 1, the in-flight copy removed -> `test_the_buttons_and_fields_are_inert_while_a_fit_is_running` failed; round 2,
the awaiting branch forced to the overlay -> the guide and walk tests failed. Both restored (`diff` against the saved copy empty).

Evidence: `click_1 ... click_12_*.png` from `scripts/capture_clicks.py` (simulation ticked, typed fields, running, fitted tables and plot, FRET states
tab, three states, transition-time scan, export dialog, open dialog, dropped table with the data panel, the guide waiting for Simulate, help), read at
full size; `after_*` and `after_populated_*` regenerated. `compare` exit 0 (66 controls, 0 without tooltip).

### emtk gaps seen (not edited)

1. The MMFDB picker's buttons stop working after the first click (repro in burst_fusion's report, section 6a).
2. The wheel never reaches an implot inside a `DockManager` window.
3. `EmTkGuidedTour.draw` (shared `chisurf/emtk/help_guide.py`) puts its card buttons in whatever window is current; in a `DockManager` app they sit
   under the dock windows. Repro: a `DockManager` app, `tour.start()`, press "Close Tour" at its drawn rectangle: nothing happens. (Worked around here
   by the overlay window; not edited.)
4. Numeric `input_float` / `input_int` / `drag_*` have no typed entry and a non-live drag applies nothing.

## 7. Screenshots read

`before_populated.png` (Qt HEAD: placeholder plot), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,
800x600}.png`, `after_*`.

## 9. Persistence, guide, help, docs

Window geometry (Qt) / host's; no settings persisted by either. Guide content unchanged, now walkable. Docs: none.

## 10. Blocked / open

none.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
