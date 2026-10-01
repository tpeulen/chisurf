# emtk port report — `tttr_time_windows` (swap-candidate upgrade, audit-all row 7)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `tttr_time_windows` / `chisurf/plugins/tttr/tttr_time_windows` |
| Port type | B → existing emtk app; the committed Qt `TTTRTimeWindowTool` (toolbar, DockArea: Settings / Files / Preview / Summary); the stream rewrote `gui/tool.py` to host the emtk app |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `af03166a4` baseline; `892ab2c3b` emtk app at parity with the Qt tool; evidence commit "tttr_time_windows: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

Modified `gui/tool.py`, `manifest.json`, `tests/test_construction_smoke.py`; untracked `gui/app.py`, `gui/controller.py`,
`gui/guide.json`, `gui/help.md`, `tests/test_emtk_controller.py` (`pre-upgrade/`). Baseline from HEAD `tool.py`
(`scripts/qt_head.py`): 14 controls. Incident: the first Qt populated run wrote its output next to the test file
(`test/data/clsm/Leica_SP5_TW_10000ms/`, the script set the wrong output field); the folder (mine, untracked, created that minute)
was moved to the scratchpad and the script fixed.

## 2. Control checklist

| Qt (committed) | emtk | Present? |
|---|---|---|
| Toolbar Process / Clear / Help; menu File ▸ Exit, Help ▸ About | Process, Clear, Help (twice), Guide; window close is the host's | yes (menus: host level) |
| Settings: Time window (ms suffix), Output folder + Browse… | Time window (ms), Output folder + Browse… | yes |
| Files: path list, add files/folder/database, remove, drop | Files, Folder, Database, Remove, drop, list | yes |
| Preview: Preview file combo, intensity trace with window boundaries | click a file in the list → trace with boundaries | yes (deliberate) |
| Summary: log | Processing log | yes |
| Status bar ("Ready", "Preview: …", "Processing complete") | status line in the Settings pane | **fixed** (was a full-viewport window) |

Output: Leica_SP5.ptu, 10 000 ms → 16 windows, `Leica_SP5.bst` 246 bytes, sha256 `4e4d0add2e46ce4f…` from both tools.

## 3. Files

| File | Change |
|---|---|
| `gui/controller.py` | status window removed; job / file dialogs in `DialogWindow`s; `process_pending` queues Process behind a preview load; dock `LayoutStore` (saved on close only if changed) |
| `gui/app.py` | labels without pictograms, plain Process, `Time window (ms):`, status line, unused colour constants removed, boundaries capped at `MAX_BOUNDARY_LINES` |
| `tests/test_emtk_time_windows_parity.py` | new, 10 tests |
| `tests/test_emtk_controller.py` | stream's; photon_table parts removed (its controller no longer exists after the photon_table port) |
| `test/prd_mention_allowlist.txt` | struck `tests/test_construction_smoke.py` (no longer names a PRD) |

## 4. Automated evidence

```
after: 35 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/tttr_time_windows
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences (`deliberate.json`)

| Item | Why / replacement |
|---|---|
| `droptttrfileshere` | longer caption with the extensions |
| `previewfile` | the Preview-file combo became "click a file in the list" |
| `selectafiletopreviewitsintensitytrace.` | hint now in the empty plot |
| `timewindow` | unit moved from the spin-box suffix into the label |

## 6. Tests

```
$ python -m pytest chisurf/plugins/tttr/tttr_time_windows -q -p no:cacheprovider
27 passed in 11.72s
```

| Required | Test | Asserts |
|---|---|---|
| 1 / 5 | `test_process_writes_the_qt_tools_bst` | Process pressed while the preview loads; through app frames the `.bst` equals the Qt tool's (size, sha256), 16 windows |
| 2 | `test_a_status_message_does_not_cover_the_tool`, `test_the_job_and_file_windows_are_sized` | message drawn with the tool around it; file window smaller than the viewport |
| 4 | `test_labels_have_no_pictograms_and_draw_at_both_sizes[...]`, `test_process_is_a_plain_button` | |
| 6 / 7 | `test_port_is_qt_free`, `test_every_control_has_a_tooltip` | |
| 8 | `test_dock_layout_is_kept_only_when_changed` | nothing written on open/close; saved when changed |
| extra | `test_window_boundaries_are_drawn_only_when_they_can_be_told_apart` | 15 014 → none, 15 → drawn |

Deliberate breakage: not re-running the queued Process → bst test failed (`AssertionError: []`); status line removed → status test
failed. Restored.

Pre-existing failures found and fixed: `test_emtk_controller.py::test_pure_apps_render_with_file_choosers` and
`::test_photon_load_publishes_only_when_polled` imported `photon_table.gui.controller`, removed by the photon_table port (0ad96ee1f).

## 7. Screenshots read

| File | Observation / fix |
|---|---|
| `before_emtk_populated_preview_*`, `before_emtk_populated_processed_1200x800.png` | the whole window replaced by "Preview: …" / "Processing complete" on black → fixed |
| `after_populated_processed_1200x800.png` | files, settings with status, 16 windows, log |
| `after_populated_preview_*` | first grab: the 10 ms preview drew 15 014 boundary lines (`len(bounds)`), filling the plot and hiding the trace (same in Qt, `before_populated_preview.png`) → boundaries drawn only up to 300 (`MAX_BOUNDARY_LINES`); re-grab shows the trace |

## 9. Persistence, guide, help, docs

Dock layout as Qt (settings folder instead of QSettings); geometry is the host's. Guide/help: stream's files. Docs: none changed.

## 10. Blocked / open

* none open for this plugin (the boundary-line flood is fixed here; the Qt tool keeps it).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10

## 12. Verification pass (2026-10-01, T-20261001-SWAP4B)

Re-verified against the committed Qt tool (`scripts/qt_head.py`, `before_populated_*.png`). The earlier port stands; two real defects,
one dropped log line and the guard failures were found.

| # | Finding | Reproduction (5 lines) | Fix |
|---|---|---|---|
| 1 | **REGRESSION: dropped files did nothing, in every host.** The hook `on_paths_dropped` sat on the controller, not on the app; the Qt window also accepted dropped folders | `app = create_app(); [n for n in dir(app) if "drop" in n]` -> `[]` (the controller has `on_paths_dropped`) | `files_dropped` = `on_files_dropped` = `on_paths_dropped` on the app; a dropped folder is searched recursively; a drop with nothing supported says "Nothing to queue: ..." |
| 2 | **Failures left the status line at "Processing files..."** (Qt showed "Processing failed" / "Preview failed") | `create_app(client=<raises in analyze_files>)`, add a file, `_process_all()`, poll -> `message == "Processing files…"`; only the log had the error | `_fail()` sets "Processing failed" / "Preview failed" and logs the detail |
| 3 | The log lacked the Qt tool's first line `Processing N file(s) with time window = X ms…` | process, read `_log_lines[0]` | logged when Process starts |
| 4 | Guide never waited and had bare-string targets (guards `test_guide_is_a_tour_not_a_slideshow`); help.md was a 12-line stub | seam test `-k tttr_time_windows` | 5-step guide with `{"action": ...}` targets and `await`s on Files, Time window and Process; `wait_for_controls=True`; fuller help |
| 5 | Allow-list lines struck: `test/plugin_help_guide_allowlist.txt` (`tttr_time_windows/gui`) and `test/prd_mention_allowlist.txt` (`tttr_time_windows/__init__.py`, whose docstring named a PRD) | the two stale-entry tests | struck; the PRD name removed from the docstring |

Checked and fine: Process with no files (log line), the byte-identical `.bst` (size, sha256), Remove/Clear, dock layout kept only when changed,
status line not a window over the tool, Stop button, both sizes, Qt-free, tooltips.

Tests added (`tests/test_emtk_time_windows_parity.py`): `test_dropped_files_and_folders_are_queued`,
`test_a_failing_process_is_reported_not_left_as_processing`, `test_a_failing_preview_is_reported`,
`test_process_without_files_says_so_and_a_good_run_logs_the_windows`, `test_remove_and_clear`, `test_guide_waits_for_the_user`.
`tests/test_construction_smoke.py::test_help_and_guide_have_real_content` expected 4 guide steps, now 5 (queue, duration, output, preview, process).

```
$ python -m pytest chisurf/plugins/tttr/tttr_time_windows -q -p no:cacheprovider
33 passed in 12.77s
```

Deliberate breakage (restored): the failure publisher reverted to log-only -> `test_a_failing_process_is_reported_not_left_as_processing`
failed; the drop hook made to return `False` -> `test_dropped_files_and_folders_are_queued` failed.

`after` / `compare`: `35 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [] / stale []).
Screenshots read: `verify_process_failed_1200x800.png` (status line "Processing failed" and the reason in the log),
`verify_drop_folder_1200x800.png` / `_800x600.png` (a dropped folder queued, preview), `verify_drop_nothing_1200x800.png`,
`verify_guide_await_files_1200x800.png`. Script: `scripts/capture_verify.py`.

## 13. Click-driven coverage (added after the verification pass; `tests/test_emtk_time_windows_clicks.py`, driver `tests/pointer.py`)

The tests move the pointer, press and release at the drawn control, type into fields and read the next frame. **New regression
found by typing: the duration was `im.input_float`, which in emtk is a drag field that takes no typed number** (the Qt spin box
did): fixed, it is now the spec's `value` field (typed, Qt range 0.001..3 600 000 ms, up/down arrows, preview follows); the
inventory shows the control as an `input_text` now (`after.json`).

| Control | Test |
|---|---|
| Files (dialog, Cancel, pick two, Open, first previewed) | `test_files_button_opens_the_dialog_cancel_closes_it_and_open_queues_the_picked_files` |
| dialog x / Escape | `test_the_file_dialog_closes_with_its_x_and_with_escape` |
| Folder | `test_folder_button_queues_the_supported_files_of_a_folder` |
| Database | `test_database_button_opens_the_dataset_picker` |
| row click (preview) | `test_clicking_a_file_row_previews_that_file` |
| - Remove | `test_remove_button_takes_the_previewed_file_off_the_queue` |
| Clear | `test_clear_button_empties_the_queue_the_preview_and_the_log` |
| Time window field, range, arrows | `test_time_window_field_takes_typed_text_and_the_preview_follows`, `test_time_window_arrows_step_by_one_millisecond` |
| Output folder field, Browse... | `test_output_folder_field_takes_typed_text`, `test_browse_button_chooses_an_output_folder` |
| Process (none, typed settings, failure) | `test_process_button_without_files_says_so_in_the_log`, `test_process_button_runs_the_analysis_with_the_typed_settings_and_logs_the_windows`, `test_a_failing_process_is_shown_on_the_status_line_after_the_click` |
| Stop | `test_stop_button_discards_the_running_job` |
| Help (both), Close Help | `test_each_help_button_opens_the_help_window[0,1]` |
| Guide, awaited Files / time window / Process, Close Tour | `test_guide_button_starts_the_tour_which_waits_for_each_control` |
| Next / Prev | `test_the_tour_next_and_prev_buttons_can_be_clicked` (**xfail strict**, emtk gap) |
| drop (native host, Qt host) | `test_a_drop_reaches_the_native_and_the_qt_host` |

```
$ python -m pytest chisurf/plugins/tttr/tttr_time_windows -q -p no:cacheprovider
52 passed, 1 xfailed in 17.44s
after: 35 controls, 0 without tooltip, qt-free=yes ;  compare: exit 0 (lost [] / stale [])
```

Break-on-purpose (restored): the file removal skipped -> `test_remove_button_takes_the_previewed_file_off_the_queue` failed.
Click sequence (real client, Leica_SP5.ptu): `click_1_before_files` ... `click_7_after_click_clear` (Files -> pick -> Open -> preview ->
type 10000 ms -> type the output folder -> Process -> `leica.bst` written, log "16 windows" -> Clear). Read: the trace shows the
boundaries at 10 s, the status line and the log follow each click.
