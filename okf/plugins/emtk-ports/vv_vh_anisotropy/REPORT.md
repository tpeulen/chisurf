# emtk port report — `vv_vh_anisotropy` (swap-candidate upgrade, audit-all row 22)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `vv_vh_anisotropy` / `chisurf/plugins/vv_vh_anisotropy` (deprecated, `menu_hidden`) |
| Port type | B → existing emtk app: the Qt tool is the committed `__init__.py` (now moved verbatim to `qt_tool.py`, `diff` empty); the earlier stream wrote `gui/{app,model,strings}.py` (hand-drawn form, hand-drawn batch panel) |
| Agent / date | claude implementing agent, 2026-10-01 |
| Commits | `fedc02092` Qt baseline + current emtk state + pre-upgrade; `03ba42269` emtk app at parity; `888eaec50` click-driven tests; evidence commit "vv_vh_anisotropy: evidence and report" |
| Board | `T-20261001-SWAP4B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt` (modified `__init__.py`, `manifest.json`; untracked `gui/`, `qt_tool.py`, `test/capture.py`,
`test/renders/`, `test/test_native.py`); `pre-upgrade/{gui,qt_tool.py,test}` hold the files, `tracked_modified.diff` the tracked
diff. The audit's "lost 4 / 11 unmatched" measured an app that had no help/guide and a hand-drawn batch. All plugin files were
committed with the app (`test/renders/` stays untracked: the stream's own self-assessed screenshots).

## 2. Control checklist (Qt: `qt_tool.py`)

| Qt control | emtk | Present? |
|---|---|---|
| Deprecation label | "Deprecated: ..." info line (emoji removed) | yes |
| Load VV/VH File, path field | Load VV/VH file..., read-only File field | yes |
| Save... | Save outputs... (greyed until a file is loaded) | yes (renamed) |
| Batch... | Batch files... (opens the sized batch window) | yes (renamed) |
| g-factor (5 decimals, 0..10) | G-factor, spin arrows, same range and decimals | yes |
| Apply backgrounds; BG VV; BG VH (3 decimals, +-1e9) | same | yes |
| Flip VV<->VH | Flip VV<->VH | yes (shorter label) |
| Shift VH (channels) (-150..150) | same | yes |
| r-infinity read-out ("N/A", 5 decimals) | r-infinity field | yes |
| Decays plot (log y, legend, blue VV / red VH) | same series names and colours | **fixed** (were plain "VV"/"VH") |
| r(t) plot, y 0..0.45, movable green region | same; two draggable lines + shading + Region start/end fields | **fixed** (lines could cross; no shading) |
| Batch window: Files / Folder / Database / Remove / Clear / drop list | the same five buttons, a queue `data_table`, drop | **fixed** (had only "Add batch files...") |
| Batch: Run Batch, Save CSV, 7-column table | Run Batch, Save CSV..., 8-column `data_table` (+ error) | **fixed** (was text lines) |
| Dialogs: "No files to process.", "No results to save.", "Processed N file(s)." | status line text (greyed buttons for the first two) | yes |
| (none) | Help, Guide (`help.md`, `guide.json`) | added |

## 3. Files

| File | Change |
|---|---|
| `gui/model.py` | region properties (`region_min/max`), `r_infty_text`, requests, `enabled`, batch queue (`add_batch_paths`, `select_batch_file`, `remove_selected`, `clear_batch`), snapshot semantics, per-file error rows, LF line ends, `forget_selection` |
| `gui/vv_vh_emtk.view.json` | new: form, queue table, results table |
| `gui/app.py` | rewritten around the spec; sized in-app batch and file windows; drop hooks; region-line rects |
| `gui/guide.json`, `gui/help.md` | new (7-step tour with awaits) |
| `test/test_emtk_vv_vh_parity.py` (25), `test/test_emtk_vv_vh_clicks.py`, `test/pointer.py` | new |
| `test/plugin_help_guide_allowlist.txt` | struck the `vv_vh_anisotropy` line |

## 4. Regressions found in the earlier emtk app (all fixed in `gui/`)

| # | Finding | 5-line reproduction |
|---|---|---|
| 1 | **Drops reached nothing in native/web hosts** (only `on_paths_dropped`) | `app = create_app(); hasattr(app, "files_dropped")` -> False |
| 2 | **Batch window and file chooser were unsized windows covering the whole app** (`before_emtk_batch_results_1200x800.png`) | `app.batch_open = True; draw` -> a full-viewport black page |
| 3 | **Batch had no Remove, Clear, Folder, Database, no ordering, results as text lines** | read `pre-upgrade/gui/app.py` `draw_batch` |
| 4 | Batch used the live settings, not the Qt snapshot taken when the window opens | change g after opening: Qt rows keep the old g |
| 5 | Region lines could be dragged inside out and the average became one point | `region_bounds = [140, 100]` -> r-infinity of a single channel |
| 6 | CSV files ended lines in CRLF (the Qt tool wrote LF); found by the byte comparison with the Qt tool | `csv.writer(stream)` with `newline=""` |
| 7 | Plot series lacked the Qt legend names ("VV (BG corrected)", "VH (shift 1.500 ch, ...)") and colours; an emoji label | `before_emtk_populated_1200x800.png` |
| 8 | A removed file that was queued again came back highlighted while the model had nothing selected (the table keeps its selection by row key) | remove a row, queue the same file, click it: it is deselected |

**Qt defects, not reproduced (tested as fixed):** (a) the Qt `Save...` never writes `_shifted.dat`: it calls
`write_vv_vh(array, path)` with the arguments in the wrong order inside a bare `except: pass`; the evidence run wrote only
`result_anisotropy.txt` and `result_rinf.csv` (`scripts/capture_qt.py` output). (b) A file without numbers makes the Qt load slot
and the Qt batch raise `IndexError`; emtk keeps the loaded data and reports `Could not load words.dat: ...` / a row with its error.

## 5. Numbers equal the Qt tool (tests, not estimates)

`test_trace_rinf_and_files_equal_the_qt_tool[...]` builds the genuine Qt tool (`qt_tool.py`, offscreen), loads the same generated
file (`scripts/data.py`, seeded), sets the same settings (plain; background + shift; flip + negative shift) and compares r(t)
(rtol 1e-12), r-infinity, the five-decimal text, and the **bytes** of `_anisotropy.txt` and `_rinf.csv`.
`test_batch_rows_equal_the_qt_batch_window[...]` compares every batch row with `VvVhAnisotropyBatchWindow._compute_rinf_for_file`
(region clamped past the last channel in both). Evidence run: Qt r-infinity `0.01652595584079851` (g 1.05, bg 12/9, shift 1.5),
emtk the same; batch `a.dat 0.01652595584079851`, `b.dat 0.05170757867193667` in both.

## 6. Automated evidence

```
after: 41 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/vv_vh_anisotropy
compare: exit 0   (lost [] / stale_explanations [] / untooltipped [])
```

Deliberate differences (`deliberate.json`, 4): Batch... -> Batch files..., Save... -> Save outputs..., the shorter flip caption,
"Deprecated:" instead of the emoji.

```
$ python -m pytest chisurf/plugins/vv_vh_anisotropy -q -p no:cacheprovider
57 passed, 1 xfailed, 5 warnings in 29.92s
$ python -m pytest test/test_plugin_help_guide_seam.py test/test_prd_mentions.py -q -k "rics_precision or vv_vh_anisotropy or tttr_count_rate_analysis or tttr_time_windows"
11 passed, 1 skipped, 239 deselected in 2.31s
```

Break-on-purpose (restored each time): the batch ignoring its snapshot -> 4 tests failed (`test_batch_rows_equal_the_qt_batch_window`
x3, `test_batch_uses_the_snapshot_...`); the drop hooks removed -> `test_a_dropped_file_is_loaded_or_queued` failed; CRLF line ends ->
`test_trace_rinf_and_files_equal_the_qt_tool` x2 failed (bytes differ); Remove greyed -> `test_batch_remove_clear_delete_key_...`
failed; the tour no longer hearing the form -> the two tour tests failed.

## 7. Click coverage (`test/test_emtk_vv_vh_clicks.py`: events -> the next frame; `test/pointer.py` is the driver)

| Control | Test |
|---|---|
| Load VV/VH file..., dialog Open / Cancel / x / Escape | `test_load_button_dialog_cancel_and_open`, `test_file_dialog_window_closes_with_its_x_button_and_with_escape` |
| a file without numbers through the dialog | `test_a_bad_file_through_the_dialog_is_a_status_line_not_a_crash` |
| File path field (read-only) | `test_the_file_path_field_is_read_only` |
| Save outputs... (greyed, dialog, name field, files) | `test_save_outputs_button_dialog_and_files`, `test_the_file_path_name_field_accepts_backspace` |
| G-factor field, arrows, range | `test_g_factor_field_typed_value_changes_r_infinity`, `test_g_factor_stepper_arrows_and_the_range` |
| Apply backgrounds, BG VV, BG VH | `test_background_checkbox_and_fields` |
| Flip VV<->VH | `test_flip_checkbox_swaps_the_channels` |
| Shift VH (channels) | `test_shift_field_and_its_range` |
| Region start / end fields | `test_region_fields_move_the_averaging_region` |
| Region lines of the r(t) plot (drag, inside out) | `test_dragging_the_green_lines_moves_the_region` |
| Help, Close Help | `test_help_button_opens_the_help_window_and_close_help_closes_it` |
| Guide, awaited Load / G-factor, Close Tour | `test_guide_button_starts_the_tour_which_waits_for_the_load_button`, `test_the_tour_waits_for_the_g_factor_field_to_be_edited` |
| Tour Next / Prev | `test_the_tour_next_and_prev_buttons_can_be_clicked` (**xfail strict**, emtk gap, section 10) |
| drop on the native host and on the Qt host | `test_a_file_dropped_on_the_native_and_the_qt_host`, `test_drop_with_the_batch_window_open_queues_the_files` |
| Batch files..., Close, window x | `test_batch_button_opens_and_close_button_and_title_x_close_it` |
| Batch Files (dialog, multi-select), queue rows | `test_batch_files_button_dialog_adds_files_and_table_rows_select` |
| Batch Folder, Database | `test_batch_folder_button_queues_a_folder`, `test_batch_database_button_opens_the_picker` |
| Batch Remove, Clear, Delete key, greyed Run | `test_batch_remove_clear_delete_key_and_the_disabled_buttons` |
| Run Batch, Save CSV..., results cells | `test_run_batch_button_fills_the_results_table_and_save_csv_writes_it` |
| snapshot of the settings; a bad file row | `test_batch_uses_the_settings_current_when_it_was_opened`, `test_a_bad_file_in_the_batch_shows_its_error_in_the_table` |

## 8. Screenshots read

`before.png`, `before_populated*.png` (Qt), `before_emtk_*` (stream's app: full-viewport batch/file windows), `after_*_1200x800` and
`_800x600` (empty, populated, load error, batch queued/results/bad file, file dialog, guide, help), and the click sequence
`click_1_before_load` ... `click_8_after_click_run_batch` (clicks and typing only: Load -> pick a.dat -> Open -> type g 1.2 -> drag
the start line -> Batch files... -> Files -> Run Batch). The 800x600 first grab clipped the Guide/Help buttons (form share too
small): the form window now takes a larger share of a small window (`CONTROLS_HEIGHT`); the batch table headers `region_min`/`region_max`
were cut at 90 px: 105 px now. Help prints markdown bold as literal asterisks (emtk gap): the text is plain.

## 9. Persistence, guide, help, docs

`export_settings` / `restore_settings`: g, backgrounds, flip, shift, region, loaded file, batch queue (round-trip test; a missing
file does not stop the rest). Guide/help: new, guard tests green. Docs: guide 10 mentions the tool; labels unchanged apart from the
two renames above (docs gap: none to fix). Qt tool left untouched (`qt_tool.py`).

## 10. Blocked / open (emtk gaps, 5-line reproductions)

* **Tour Next / Prev never fire** (shared `chisurf/emtk/help_guide.py`, all ports): `Close Tour##tour`, `◄ Prev##tour`, `Next ►##tour`
  share the id `tour`. Repro: `app.tour.start(2); Pointer(app).click("Next ►")` -> `step_idx` stays 2 (`Close Tour` works). The
  xfail test documents it; the awaited controls themselves are tested.
* **`im.input_float` is a drag field** (no typed numbers); the shared channel editor uses it (`_float_input`). Fixed here by using
  spec `value` fields.
* **A table keeps its selection by row key after the row is gone**: queue a, select it, Remove, queue a again -> highlighted but the
  model has nothing selected. Worked around (`forget_selection`).
* **Painted Markdown shows `**bold**` and backticks literally** in the help window.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
