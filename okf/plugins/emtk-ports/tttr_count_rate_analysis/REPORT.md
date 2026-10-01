# emtk port report — `tttr_count_rate_analysis` (swap-candidate upgrade, audit-all row 6)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `tttr_count_rate_analysis` / `chisurf/plugins/tttr/tttr_count_rate_analysis` |
| Port type | B → existing emtk app: the committed Qt `CountRateAnalyzer` is an AutoForm on `count_rate.view.json`; the earlier stream wrote an emtk app and rewrote `gui/tool.py` to host it |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `93bc73867` baseline; `160534bd7` emtk app at parity with the Qt tool; evidence commit "tttr_count_rate_analysis: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `cli.py`, `gui/tool.py`, `gui/view_model.py`, `manifest.json`,
`test/test_widgets.py`, `test_cli.py`; untracked `gui/app.py`, `gui/controller.py`, `gui/guide.json`, `gui/help.md`, `tests/`.
All committed with the app. **Audit correction:** the audit's "Qt side is a single canvas" measured the rewritten `tool.py`; the
baseline is the committed AutoForm tool (`scripts/qt_head.py`: HEAD `tool.py` + `view_model.py`), 92 controls.

## 2. Control checklist

| Qt (committed) | emtk | Present? |
|---|---|---|
| Channel Definition tab (setup, reading routine, PIE, detectors table, LUT handling, Optical Setup…) | "Detector channels" window: the shared channel editor, one section at a time | yes, with the shared editor's gaps (section 5) |
| Files tab: list, + Files, Folder, Database, Remove, Clear; drop | "TTTR files": Add files, Folder…, Database…, Clear, **Remove** (added), drop | fixed |
| Calculate, Save | Calculate (plain now), Save | yes |
| Count Rates tab: rate vs file per channel | "Count rate per file" plot | yes |
| Results tab: Channel / Mean (kHz) / Std (kHz) / #Photons / Time (s) | declared `data_table`, same columns and formats (was hand-drawn) | fixed |
| — | Help, Guide (`help.md`, `guide.json`) | added by the stream |

Numbers (`scripts/capture_populated.py`, `Leica_SP5.ptu`, one channel `all`): Qt and emtk both
`{'channel': 'all', 'mean_khz': 44.72292671613037, 'std_khz': 0.0, 'photons': 6714549, 'time_s': 150.13661879999998}`.

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | selection + Remove, `remove_file` → `model.update()`, `RESULTS_TABLE` data_table via `draw_form`, no button colours |
| `tests/test_emtk_count_rate_parity.py` | new, 9 tests |
| stream's files | committed (section 1) |

## 4. Automated evidence

```
after: 43 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/tttr_count_rate_analysis
compare: exit=0   (lost [] / stale_explanations [] / untooltipped [])
```

`after_all_sections.json` (`scripts/cr_union.py`): the inventory over all six editor sections, 94 controls, 0 untooltipped.

## 5. Deliberate differences and inherited gaps (`deliberate.json`, 76 entries)

* Combo-popup entries and row numbers (binning values, file types, `—none—`): inventory artefacts.
* Populated-state controls (result columns, Remove): drawn once files/results exist.
* Renames in the shared editor (Read → Read TTTR header and decay, File Type → TTTR format, Macrotime res. → Macro-time tick, …)
  and controls in other editor sections (Detectors, PIE windows, Optical setup, TAC corrections).
* Default data: Qt's default setup has a `yellow` detector and `prompt`/`delayed` PIE windows; the shared editor's default has
  green/red and no windows.
* **NOT PORTED (shared editor, `chisurf/emtk/channel_definition.py`, another stream's file):** `Configure LUTs`, `Adjust shifts`,
  `Edit JSON`; detectors and PIE windows are stacked blocks, not tables. Recorded in known issue "Setup:Channel Definition … shared-editor
  gaps" and `okf/plugins/emtk-ports/setup_channel_definition/REPORT.md`; this plugin cannot fix them.

## 6. Tests

```
$ python -m pytest chisurf/plugins/tttr/tttr_count_rate_analysis -q -p no:cacheprovider
29 passed in 16.34s
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_calculate_gives_the_qt_tools_row` | Calculate path on Leica_SP5.ptu reproduces the Qt row; cells drawn as `44.72`, `6714549`, `150.137` |
| 2 | `test_remove_selected_file`, `test_calculate_is_a_plain_button` | removal + refresh event, unknown path ignored; no style colours |
| 3 | `test_results_table_is_declared_with_the_qt_columns` | data_table, Qt column titles, descriptions |
| 4 | `test_draws_empty_and_populated[1200x800, 800x600]` | |
| 6 | `test_port_is_qt_free` | |
| 7 | `test_every_control_has_a_tooltip` | inventory empty in every editor section |
| 8 | `test_settings_round_trip` | queue survives export/restore |

Deliberate breakage: removing `model.update()` → `test_remove_selected_file` failed (`'files' in []`); Mean format `%.1f` →
`test_calculate_gives_the_qt_tools_row` failed (`'44.72' in [...]`). Restored. Pre-existing failures: none.

## 7. Screenshots read

`before_populated_tab_*.png` (Qt: the Files list stays empty after `add_files` — the AutoForm path_list does not refresh on
`notify`, a Qt-side defect, not ported), `before_emtk_populated_*`, `after_populated_1200x800.png` / `_800x600` (queue with Remove,
plot point at 44.7 kHz, table), `after_1200x800.png` / `after_800x600.png`. Nothing clipped.

## 9. Persistence, guide, help, docs

`export_settings()`: files, selected setup, setups path, setup definition (stream's). Guide/help: stream's files (allow-list checked by
the seam test). Docs: none changed.

## 10. Blocked / open

Shared channel-editor gaps (section 5).

## 11. Self-check

- [x] D1 · [x] D2 (shared-editor gaps declared) · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10

## 12. Verification pass (2026-10-01, T-20261001-SWAP4B)

Re-verified against the committed Qt tool (`before_populated_tab_*.png`, `scripts/qt_head.py`) with the lens of the first accepted
batch (dead drop hooks, edits not reaching the model, undismissable errors). The earlier port stands; three real defects and the two
guard failures were found.

| # | Finding | Reproduction (5 lines) | Fix |
|---|---|---|---|
| 1 | **REGRESSION: drop reached nothing in the native and web hosts.** The Qt list took drops of files and folders; the app only had the Qt-era `on_paths_dropped` (the Qt host calls it, `emtk.native` / `emtk.web` call `files_dropped` / `on_files_dropped`) | `app = create_app(); hasattr(app, "files_dropped")` -> `False`; `app.on_files_dropped([ptu])` -> `AttributeError` | `files_dropped` = `on_files_dropped` = `on_paths_dropped` on the app; folders are expanded, non-TTTR drops say so on the status line |
| 2 | Guide never waited (guard `test_guide_is_a_tour_not_a_slideshow`) and its targets were bare strings (guard `test_guide_steps_point_at_real_widgets` crashed with `'str' object has no attribute 'get'`) | `pytest test/test_plugin_help_guide_seam.py -k tttr_count_rate_analysis` | 5-step guide with `{"action": ...}` targets and three `await`s; the tour has `wait_for_controls=True` and the buttons call `notify_used` |
| 3 | Adding files while an analysis runs was ignored without a word | `tool.calculate(); tool.add_paths([p])` -> `message == ""` | message "Wait for the running analysis to finish before adding files." |
| 4 | Allow-list line `tttr_count_rate_analysis/gui` was stale (help.md and guide.json exist) | seam test `test_allowlist_has_no_stale_entries` | struck from `test/plugin_help_guide_allowlist.txt` |

Checked and fine: Calculate with no files / no channels (status line, no box to dismiss), a failing file read (status line shows the
reader's message, results stay empty), Save with nothing computed, Save writes the Qt table text, Remove/Clear, Stop analysis, settings
round trip, Qt-free, tooltips in all six editor sections, both sizes.

Tests added (`tests/test_emtk_count_rate_parity.py`, now 33 passed for the folder):
`test_dropped_files_and_folders_are_queued`, `test_calculate_and_save_errors_reach_the_status_line`,
`test_failing_read_is_reported_and_save_writes_the_table`, `test_guide_waits_for_the_user`.

```
$ python -m pytest chisurf/plugins/tttr/tttr_count_rate_analysis -q -p no:cacheprovider
33 passed in 20.61s
$ python -m pytest test/test_plugin_help_guide_seam.py test/test_prd_mentions.py -q -p no:cacheprovider -k "tttr_count_rate_analysis or tttr_time_windows"
5 passed, 1 skipped, 239 deselected in 1.00s
```

Deliberate breakage (restored): renaming the app's drop hooks -> `test_dropped_files_and_folders_are_queued` failed; `wait_for_controls=False`
-> `test_guide_waits_for_the_user` failed.

`after` / `compare`: `43 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [] / stale []).
Screenshots read: `verify_error_no_files_1200x800.png` (status line, not a box), `verify_populated_1200x800.png` / `_800x600.png`,
`verify_guide_await_add_files_1200x800.png` (spotlight on Add files, Next disabled until pressed), `verify_guide_channels_1200x800.png`.
Script: `scripts/capture_verify.py`.

## 13. Click-driven coverage (added after the verification pass; `tests/test_emtk_count_rate_clicks.py`, driver `tests/pointer.py`)

The tests move the pointer, press and release at the drawn control (found by the text it drew), type into fields, and read the next
frame. Three more findings: **the file chooser was an unsized window covering the whole app and ignoring Escape** (fixed: a sized
window with an x, closed by Escape); the shared channel editor's numeric inputs are drag fields that take no typed number (its file,
not touched); Tour Next / Prev never fire (emtk gap below).

| Control | Test |
|---|---|
| Add files (dialog, Cancel, pick two, Open), rows | `test_add_files_button_dialog_cancel_and_open` |
| dialog x / Escape | `test_the_file_dialog_is_a_window_with_an_x_and_closes_with_escape` |
| Folder... | `test_folder_button_queues_a_folder_recursively` |
| Database... | `test_database_button_opens_the_dataset_picker` |
| row click, Remove (greyed first) | `test_selecting_a_row_enables_remove_and_remove_takes_it_off` |
| row right-click menu | `test_right_click_on_a_row_offers_remove_from_queue` |
| Clear | `test_clear_button_empties_the_queue_and_the_results` |
| Calculate: the Qt row, plot, no files, unreadable file, no channels | `test_calculate_button_fills_the_table_and_the_plot_with_the_qt_tools_row`, `test_calculate_without_files_says_so`, `test_calculate_with_an_unreadable_file_reports_the_reason`, `test_calculate_with_no_detector_channel_asks_for_a_setup` |
| Save (nothing, dialog, typed name, table text) | `test_save_button_before_and_after_a_calculation` |
| Stop analysis | `test_stop_analysis_button_discards_the_incomplete_run` |
| Help, Close Help | `test_help_button_opens_and_closes_the_help_window` |
| Guide, awaited Add files / Calculate / Save, Close Tour | `test_guide_button_starts_the_tour_which_waits_for_each_awaited_button` |
| Next / Prev | `test_the_tour_next_and_prev_buttons_can_be_clicked` (**xfail strict**) |
| drop (native host, Qt host, folder) | `test_a_drop_reaches_the_native_and_the_qt_host` |
| editor section combo, Refresh setups, detector-setup combo, Public setup | `test_the_editor_section_combo_switches_the_section`, `test_refresh_setups_button_and_the_detector_setup_combo`, `test_the_editor_setup_name_field_takes_typed_text` |

```
$ python -m pytest chisurf/plugins/tttr/tttr_count_rate_analysis -q -p no:cacheprovider
52 passed, 1 xfailed in 26.15s
```

Break-on-purpose (restored): `remove_file` made a no-op -> `test_selecting_a_row_enables_remove_and_remove_takes_it_off` and
`test_right_click_on_a_row_offers_remove_from_queue` failed. Click sequence (real reader, Leica_SP5.ptu):
`click_1_before_add_files` ... `click_9_after_click_save_with_nothing_new` (Calculate without files -> Add files -> pick -> Open ->
Calculate -> select row -> right-click -> Remove from queue). Read: the dialog is a window, not a page; the context menu opens at
the row; the table keeps `44.72 / 0.00 / 6714549 / 150.137`.

Emtk gap (5 lines): `Close Tour##tour`, `◄ Prev##tour`, `Next ►##tour` share one id: `app.tour.start(2); Pointer(app).click("Next ►")`
leaves `step_idx` at 2 (shared `chisurf/emtk/help_guide.py`, every port).
