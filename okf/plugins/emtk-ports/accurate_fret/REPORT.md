# emtk port report — `accurate_fret` (swap-candidate upgrade, audit-all row 5)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `accurate_fret` / `chisurf/plugins/burst/accurate_fret` |
| Port type | A: the committed Qt `AccurateFretTool` hosts an emtk `AccurateFretApp(tool, on_…=…)`; the earlier stream rewrote `app.py` into a standalone app with a controller |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `f964c0eaf` accurate_fret: Qt baseline and current emtk state; `dd38807de` accurate_fret: emtk app at parity with the Qt tool; evidence commit "accurate_fret: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

```
 M chisurf/plugins/burst/accurate_fret/gui/__init__.py
 M chisurf/plugins/burst/accurate_fret/gui/app.py
 M chisurf/plugins/burst/accurate_fret/gui/tool.py
 M chisurf/plugins/burst/accurate_fret/gui/view_model.py
 M chisurf/plugins/burst/accurate_fret/manifest.json
?? chisurf/plugins/burst/accurate_fret/gui/controller.py
?? chisurf/plugins/burst/accurate_fret/test/test_native.py
```

All committed with the app (copies/diff in `pre-upgrade/`).

**Baseline method.** The working `app.py` is the rewritten one, so the committed Qt tool can only be built with HEAD sources:
`scripts/qt_head.py` loads HEAD `tool.py`, `app.py` and `view_model.py` under their real module names and runs the parity tool's
`qt_before` (`before.png`, `before.json`: 0 Qt controls, the window is the embedded emtk app); `scripts/head_app_inventory.py`
inventories that embedded HEAD app (`before_head_app.json`, 46 controls), which is the meaningful control list.

## 2. Control checklist (committed tool → current emtk)

| # | Committed (HEAD app / hidden Qt toolbar) | Current emtk | Present? |
|---|---|---|---|
| 1 | Calibrate (with progress) | Calibrate (controller job), Stop calibration / read | yes |
| 2 | From ndX, To ndX, Share in session, Store on setup, Export CSV | same, in "Data, session and catalogue actions" (+ Refresh dye catalogue, Refresh optical priors, database path) | yes |
| 3 | Guide, Help (`guide.json`, `help.md`) | Guide, Help | yes; tour fixed (below) |
| 4 | Burst Data & Columns: file + I_DD / I_DA / I_AA / Lifetime column fields | Open burst table, MMFDB burst datasets, Channels panel (four column choices) | yes (renames) |
| 5 | Photophysics & Prior: Donor Tau, Förster R₀, Linker σ, BG DD/DA/AA, Combine with Optics Prior, Show Dynamic FRET Line | Photophysics (tau_D(0), R_0, Linker width, Dynamic line), Background (Bg I_DD/DA/AA), Optics prior (Use the optics prior, Light path, Φ, g) | yes (renames, collapsed panels) |
| 6 | Correction-factor table, status console | Correction factors / Populations / Report tabs | yes (the HEAD table overprinted its text, `before_populated.png`) |
| 7 | E–S plot with static FRET line and a draggable E/S gate (E_min/E_max tags) | E–S populations, E–lifetime and FRET lines, Accurate-E histogram | gate dropped (deliberate, below) |
| 8 | Detector setup | Detector setup tab (shared editor) | yes |

Numbers: on the suite's simulated bursts (n = 100, no bootstrap) both give α 0.0798, β 1.4283, γ 0.6162, δ 0.0596, R₀ 52.0
(`capture_populated.py` output; `test_calibration_equals_the_qt_tool` compares every factor and population row).

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | stream's rewrite + my fixes: tour `wait_for_controls`, `reveal()` (opens the panel/header/dock of a step's target), `_header()` (collapsing headers register rects, open on reveal), result tabs register rects, Calibrate keyed `"Calibrate"`, Share keyed `"Share in session"`, plot rect recorded after the plot, histogram aliased `"E histogram"`, legends `LOCATION_NORTH_EAST`, histogram y range fitted to the counts (`COND_ONCE`, re-applied when the data change) |
| `test/test_emtk_accurate_fret_parity.py` | new, 9 tests |
| `gui/controller.py`, `test/test_native.py`, `gui/__init__.py`, `gui/tool.py`, `gui/view_model.py`, `manifest.json` | stream's, committed |

`guide.json` untouched (the legacy Qt tour reads it too).

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after accurate_fret --out okf/plugins/emtk-ports/accurate_fret
after: 41 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/accurate_fret
$ python -m test.gui.emtk_port_parity compare accurate_fret --out okf/plugins/emtk-ports/accurate_fret; echo "exit=$?"
exit=0      (the Qt side has 0 controls; the real diff is compare_head_app.json, section 5)
```

## 5. Deliberate differences (`compare_head_app.json`: HEAD embedded app → current)

| Lost entries | Why / where |
|---|---|
| `bgaa`, `bgda`, `bgdd`, `donortau(ns)`, `försterr₀(å)`, `linkerσ(å)`, `combinewithopticsprior`, `showdynamicfretline`, `lifetime(tau)`, `burstdatacolumns`, `photophysicsprior` (+ `v…` header variants) | renamed and regrouped into the spec's panels (Background, Photophysics, Optics prior, Channels); collapsed by default, so absent from the default-state inventory |
| `0.000`, `4.000`, `52.000`, `6.000` | field values of the collapsed Photophysics/Background fields |
| `e_min0.20`, `e_max0.80`, `0.1`…`0.9`, `proximityratio/frete`, `stoichiometrys`, `e–sburstscatterfretline`, `staticfretline(s=0.5)` | the HEAD E–S plot (axis ticks, labels, legend). Its E/S **gate** (drag rectangle + E_min/E_max tags) lived only in the app (`gate_x_min` …) and was never passed to the calibration: a control that changed nothing. Not ported. The new plots draw the measured classes and FRET lines |
| `ndx` | the HEAD toolbar abbreviations "📥 ndX" / "📤 ndX"; now "From ndX" / "To ndX" |
| `statusconsole`, `noburstfileloaded.`, `loadabursttable…`, `presscalibrate.`, `(thedonorchannel…)` | status texts, reworded ("No burst table loaded.", one-line hint, warning without parentheses) |

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/accurate_fret -q -p no:cacheprovider
26 passed in 25.24s
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_calibration_equals_the_qt_tool` | factor and population rows equal `AccurateFretTool`'s (subprocess) |
| 2 | `test_native.py` (stream): source/drop/load/calibrate/cancel/export/setup store | |
| 3 | `test_every_control_has_a_tooltip` (spec walk) | every spec field and button described |
| 4 | `test_draws_calibrated_at_both_sizes[1200x800, 800x600]` | factors and classes drawn |
| 5 | `test_every_guide_target_is_drawn_and_the_calibrate_step_waits`, `test_the_legend_leaves_the_donor_only_corner_free` | 9/9 targets drawn, await only on the Calibrate step and released by the button; legend NE, donor-only data at E≈0, S≈1 |
| 6 | `test_port_is_qt_free` | |
| 7 | `test_every_control_has_a_tooltip` | inventory empty |
| 8 | `test_settings_round_trip` | R₀ survives export/restore |

Deliberate breakage: histogram range fixed at 1.0 → `test_the_histogram_is_drawn_with_its_range_fitted_to_the_counts` failed; legend back to north-west → legend test failed (`{5} == {9}`); `wait_for_controls=False` → guide test
failed (`AssertionError: (6, 'Calibrate')`). Restored.

## 7. Screenshots read

| File | Observation / fix |
|---|---|
| `before_emtk_populated_1200x800.png` | donor-only cluster hidden under the E–S legend → legend moved |
| `after_populated_1200x800.png`, `_800x600` | donor-only at (0, 1), FRET 0/1 at S≈0.5, acceptor-only at S≈0; factors table |
| `after_populated_tau_1200x800.png` | E–lifetime with static/dynamic lines |
| `after_populated_hist_1200x800.png` | first grab: the E ≈ 0.77 peak cut off at the top (range set before data) → fitted range; a second grab came out blank (an exception in my first fix, `array or [0]`) → fixed; third grab correct |
| `after_1200x800.png`, `after_800x600.png` | empty: "Load a burst table …", empty plots with axes |

## 9. Persistence, guide, help, docs

* `export_settings()`: all calibration parameters + the channel-definition settings (stream's; more than the Qt tool's AutoForm state).
* Guide: 10 steps, 1 await, all targets drawn. Help: existing `help.md`.
* Docs: no user-visible change beyond the legend position.

## 10. Blocked / open

* The result tables are hand-drawn (`im.begin_table` in `_table`), against the "tables are specs" rule; porting them to
  `data_table` sections is open.
* `guide.json` step 9 asks the user to find the donor-only population at E ≈ 0 in the **E histogram**, but `efficiency_histogram()` (view model, same in Qt) bins only the FRET populations: the step cannot be followed. Either the histogram includes donor-only bursts or the step points at the E–S plot (also read by the legacy Qt tour, so not changed here).
* The E–S plot has no gate now; if a gate is wanted it must feed the calibration (a model attribute), not only the picture.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10

## 12. Verification and click coverage by SWAP4B (2026-10-01, board `T-20261001-SWAP4B`)

Verdict: **accept**. The first pass (EMTK-1, section 0-11 above, commits `f964c0eaf`, `dd38807de`, `7e5d806d8`, `96fbe8fb2`) holds up; checked independently, and four things were still wrong, fixed in the plugin's own app. Commits of this pass: the code and tests commit
"accurate_fret: result tables as data_table sections, plot rectangles, click-driven tests" and the evidence commit "accurate_fret: verification addendum and click evidence". Nothing of EMTK-1's was redone; the Qt baseline of section 1 was re-read, not recaptured.

**Probes that found nothing wrong** (each repeated by hand, outputs in the tests below): a drop through `ControlHost` (`dragEnterEvent` accepted, `dropEvent` loads, `test_a_file_dropped_on_the_host_loads_like_the_dialog`) - the app answers the host's `on_paths_dropped`, so the dead-drop-hook trap of the earlier batch does not apply;
a missing file, a table that cannot be read, Calibrate without data, Export before a calibration, To ndX before a calibration each leave a status line and no stuck window; the file dialog is closed by Cancel; `compare` exit 0 (`lost []`, 41 controls, 0 without tooltip, qt-free).

**What was wrong and is fixed:**

1. The two result tables were drawn by hand (`im.begin_table`), against rule 4. They are `data_table` sections now (`_table` builds the spec; columns with descriptions and widths; the populations table at 1200x800 shows `0.3152 ± 0.0043` whole,
   `click_5_after_click_on_the_Populations_tab`).
2. The plot targets (`es_plot`, `lifetime_plot`, `histogram`, `E histogram`) were the rectangle of the last item drawn, the legend (35x14 px): a click or a guide spotlight there missed the plot. They are the window content now.
3. Rectangles of fields in a panel that was collapsed again stayed as click and tour targets at their old positions (`form_state.rects` was never cleared). Cleared per frame, stale entries dropped from `item_rects`
   (`test_the_collapsing_headers_open_and_close_with_a_click`).
4. Guide step 9 asked the user to find the donor-only population in the E histogram, which bins only the FRET populations (open item of section 10 above). It points at the E-S plot now, where the donor-only population (S about 1, E about 0) is drawn.

**Tests:** `test/test_emtk_accurate_fret_clicks.py`, 32 tests (31 passing, 1 strict xfail); the plugin folder: `57 passed, 1 xfailed` (26 first-pass + 31 click tests passing + 1 xfail; output pasted from the run after the IMP build finished: a rebuild of the imp-tricks libraries by another session
made `IMP.bff` unimportable for about ten minutes and failed 22 tests of this folder in that window, not related to this change).

**Click coverage (control -> test):**

| Control | Test |
|---|---|
| Open burst table -> dialog -> file entry -> Open | `test_open_burst_table_dialog_loads_the_file_the_user_clicks` |
| dialog Cancel; a table that cannot be read | `test_the_dialog_cancel_button_closes_it_and_loads_nothing`, `test_a_burst_table_that_cannot_be_read_says_so_and_the_dialog_is_not_stuck` |
| drop on the host; a dropped missing path | `test_a_file_dropped_on_the_host_loads_like_the_dialog`, `test_a_dropped_path_that_does_not_exist_is_reported` |
| the four channel lists (I_DD, I_DA, I_AA, lifetime) | `test_each_channel_list_opens_and_a_click_on_a_column_maps_it[4]` |
| Calibrate (refused without data, then runs; factors equal the Qt tool's) | `test_calibrate_click_is_refused_with_the_reason_until_a_table_is_loaded_then_runs` |
| Stop calibration / read | `test_the_stop_button_cancels_a_running_calibration_and_keeps_the_previous_state` |
| result tabs: Correction factors, Populations, Report | `test_the_result_tabs_are_clicked_and_show_factors_populations_and_the_report` |
| E-S plot drag; wheel zoom | `test_the_plots_show_the_classes_and_a_drag_pans_the_efficiency_plot`; `test_the_wheel_zooms_the_efficiency_plot` (strict xfail: emtk gap 2, a docked window consumes the wheel) |
| collapsing headers (Data, Dyes, Photophysics, Background, ...) | `test_the_collapsing_headers_open_and_close_with_a_click` |
| Photophysics / Background fields, Dynamic line toggle | `test_photophysics_and_background_fields_take_typed_values_and_the_toggle_is_clicked`, `test_dye_and_optics_fields_are_reachable_and_typed_values_reach_the_model` |
| From ndX, To ndX, Share in session, Store on setup | `test_from_ndx_and_to_ndx_answer_with_a_status_when_no_ndx_source_exists`, `test_the_session_buttons_before_a_calibration_say_what_to_do[3]`, `test_the_session_share_and_setup_store_buttons_after_a_calibration` |
| Export per-burst CSV (typed name, error before a calibration) | `test_export_per_burst_csv_through_the_dialog_with_a_typed_name`, `test_export_before_a_calibration_reports_the_error_and_closes_the_dialog` |
| Refresh dye catalogue, Refresh optical priors, database path field | `test_the_catalogue_refresh_buttons_run_in_the_background_and_report`, `test_the_database_path_field_takes_typed_text` |
| MMFDB burst datasets; Select / configure detector setup | `test_the_datasets_button_opens_the_database_window_and_it_can_be_closed`, `test_select_detector_setup_button_brings_the_detector_setup_dock_forward` |
| Guide, awaited Calibrate step, Close Tour, Next / Prev | `test_guide_button_starts_the_tour_and_the_awaited_calibrate_step_waits_for_the_click`, `test_the_tour_next_and_prev_buttons_can_be_clicked` |
| Help, Start Guided Tour, Close, Close Help, Escape | `test_help_button_opens_the_help_window_whose_buttons_work` |
| small window | `test_the_load_and_calibrate_flow_works_in_the_small_window_too` |

**Populated click sequence** (read at full size, `scripts/capture_clicks.py`): `click_0_before_any_click_empty`, `click_1_after_click_on_Open_burst_table_dialog`, `click_2_after_click_on_the_file_entry`, `click_3_after_click_on_Open_table_loaded_channels_mapped`,
`click_4_after_click_on_Calibrate` (alpha 0.0798, beta 1.4283, gamma 0.6162, delta 0.0596, R0 52: the Qt tool's numbers on these bursts), `click_5_after_click_on_the_Populations_tab`, `click_6_after_click_on_the_Photophysics_header`,
`click_7_typed_55_into_Forster_R0_Enter` (R0 = 55 in the model), `click_8_after_click_on_Export_per_burst_CSV_dialog`, `click_9_after_Cancel_and_click_on_Help`. `after_populated_*` were re-captured with the new tables.

**Open (new):** the settings window cannot be scrolled with the wheel (emtk gap 2): the panels below Photophysics are reachable only by collapsing the ones above; the first draft of the click tests had to collapse Channels first. emtk gap 1 (id collisions) was fixed for the tour buttons during this pass; the help window's section buttons still share `##filter`.
