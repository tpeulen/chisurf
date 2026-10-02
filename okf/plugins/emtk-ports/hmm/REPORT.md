# emtk port report - `hmm` (upgrade to verified parity, audit-all row 59)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`, claim `T-20261002-UPG6`. Verdict: **accept** with the open items in section 7.
Commits: `8328ff1e0` Qt baseline + earlier-stream files (`pre-upgrade/`), then the upgrade commit and the evidence commit.

## 0. Hermetic first
The plugin's code and tests write nothing under the user's home (grep before running; the fits are in memory, saving is an explicit path). `test/conftest.py` (autouse) still points HOME, the chisurf/MMFDB folders, `chisurf_settings_path` and QSettings at a temp folder, and `test_zzz_the_real_chisurf_folder_was_not_touched` compares the real `~/.chisurf` before and after (chisurf's own `logs/` excluded: that logger ignores `CHISURF_SETTINGS_DIR`). Qt captures ran on temp HOME/QSettings.

## 1. What the earlier-stream app was
Not a port of the tool: a one-column page with four integer inputs (States, Iterations, Minimum/Maximum states), a checkbox and two buttons, **no way to load a trace** (no files, no demo), no covariance, bin width, tolerance, decoder or seed, hand-drawn polylines for the three plots (no axes, no legends, every series the same blue, the state path indistinguishable from the data), HTML tables drawn as markdown, no tooltips on the plots, and a `Fit` that ran on the UI thread. It could not fit anything the user supplied.
Replaced by: docked windows (Model, Trace, Fitted states, tabs Histogram / Dwell times / Scan), spec forms with the Qt ranges, a trace list with Add files / Remove / Clear / drops, `data_table` for the states and the transitions, implot plots with axes, legends and the Okabe-Ito state colours, fits in a `SnapshotJob` (the window stays live; fields are greyed while it runs).

## 2. Qt checklist -> emtk -> test
| Qt control | emtk | Test |
|---|---|---|
| toolbar Fit, Scan states | Fit, Scan states (greyed without data / while running) | `empty_window_asks...`, `demo...recovers_its_three_states`, `state_scan_picks_three_states...` |
| Guide, ? | Guide, Help | `help_opens...`, `tour_waits...`, `every_tour_target_is_drawn` |
| Traces list: + Files, Remove, Clear | file table, Add files... (multi-select dialog), Remove / Delete key, Clear, drops | `add_files_through_the_dialog...`, `dialog_cancel_and_close...`, `dropped_files...`, `remove_and_clear...`, `unreadable_file...` |
| Traces: Database | not ported (open item) | |
| States, Covariance, Bin width | spin / choice / spin fields, Qt limits | `model_fields_take_typed_values...[6]`, `arrows_step...`, `covariance_and_decoder_choices...` |
| Fitting: Max EM maps, Tolerance, Accelerate, Decoder, Seed | collapsed section | `fitting_fields_are_behind_their_header...`, `acceleration_switch...`, `every_setting_reaches_the_fit` |
| State scan: From, To | collapsed section | typed / arrow tests |
| trace + decoded path, intensity histogram, dwell times, scan plots | implot plots in tabs/windows | `plot_tabs_draw_axes_and_legends`, `wheel_zooms_the_trace_plot_and_a_drag_pans_it` |
| states table, transition matrix with rates | `data_table`s | `states_and_transitions_tables_show_the_fit`, `tables_show_what_the_qt_html_tables_show` |
| (gained) Demo trace, Save fit, set_traces, drops | yes | `demo...`, `save_writes_the_fit_json...`, `set_traces_is_the_seam...` |

## 3. Numeric parity (the Qt tool's own model on the same file)
`fit_started_in_the_native_window_equals_the_qt_tools_fit` (log L, means, transition matrix and rates, status line), `state_scan_equals_the_qt_tools_scan` (BIC/AIC per state count, best 3 / 3), `tables_show_what_the_qt_html_tables_show` (every cell), `native_forms_carry_the_ranges_choices_and_decimals_of_the_qt_spec` (min, max, options, decimals, kind of every field of `hmm.view.json`). Qt: 3 states recovered from the generated trace, BIC prefers 3, AIC 3 (`qt_values.json`).

## 4. Tests
```
$ python -m pytest chisurf/plugins/core/hmm -q -p no:cacheprovider
58 passed in 25.06s     (45 new + 13 existing; the existing native render test now names the docked windows)
```
Deliberate breakage (restored): occupancy halved + button enabling removed -> 1 failed (`tables_show_what_the_qt_html_tables_show`); tour notification removed + add_files replaced by assignment -> 3 failed (`dropped_files...`, `remove_and_clear...`, `tour_waits...`).
`compare`: exit 0 (lost 0, explained 3, stale 0, untooltipped 0), qt-free yes; `after.json` is the union with a fit and a scan done, both sections open, every plot tab, the choice lists open and the help window (193 controls).

## 5. Layout and evidence
`after_populated_{1200x800,800x600}.png` vs `before_populated_*` (Qt) and `before_emtk_populated_*`; `click_*.png` (empty greyed window, dialog, drop, typed fields, fit, Dwell times tab, scan, choice list, wheel zoom, demo, Help, Guide). Grouped panels with two-column label/field grids, plots with axes and legends in tabs, no text past the edge at 800x600 (test); at 800 px the two tables scroll sideways.

## 6. Reuse and docs
Reuse: `chisurf.emtk.jobs.SnapshotJob`, `emtk_layout` (layout_spec, LabelColumn, button_row), spec forms with `spin` and `choice`, `data_table` (with `columns_source`, `fit_columns`, Delete), `FileDialog`+`DialogWindow`, help/tour, `chisurf/plugins/emtk_test_input.py`. Not applicable: channel editor, dataset picker, imaging shell. Removed: the hand-drawn `_plot` and `_input_int` helpers.
Docs: **new numbered guide `docs/guides/92_hmm_binned_traces.md`** (theory + application, headless snippet, figure `figures/hmm_window.png` from the app), registered in `docs/guides/index.md`; `docs/reference/plugins/hmm.md` (hand-edited native-window table and guide link); `help.md` gained live Further-reading links; `guide.json`: targets `add_files`, `request_scan`, `covariance_type`, `request_run`, 3 awaits (the old targets, a `path_list` key and a collapsed field, never highlighted in the emtk window).

## 7. Open
* The Qt "Database" button (traces from the MMFDB object store) is not ported: it needs the path-list/database dialog of the Qt tool; the file list takes files and drops.
* At 800x600 the plots and tables are small (the four result windows share 72 % of the width).
* `emtk_preview.json` untouched.
