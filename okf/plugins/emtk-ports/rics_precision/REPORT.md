# emtk port report — `rics_precision` (swap-candidate upgrade, audit-all row 25)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `rics_precision` / `chisurf/plugins/calculator/rics_precision` |
| Port type | B → existing emtk app: the Qt tool is the committed AutoForm `RicsPrecisionTool` (`precision.view.json`, toolbar Predict / Export CSV / Guide / ?); the earlier stream wrote a hand-drawn `gui/app.py` and rewrote `gui/tool.py` to host it |
| Agent / date | claude implementing agent, 2026-10-01 |
| Commits | `b541f2dac` Qt baseline + current emtk state + pre-upgrade; `b902ca236` emtk app at parity; `1c7cea063` click-driven tests; evidence commit "rics_precision: evidence and report" |
| Board | `T-20261001-SWAP4B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/guide.json`, `gui/tool.py`, `manifest.json`; untracked `gui/app.py`, `tests/`
(`pre-upgrade/{gui/app.py,tests/,tracked_modified.diff}`). The audit's "Qt side is a single canvas" measured the rewritten `tool.py`;
the baseline is HEAD's AutoForm tool (`scripts/qt_head.py` builds it from `git show HEAD:`): 27 controls.

## 2. Control checklist (Qt, committed)

| Qt control | emtk | Present? |
|---|---|---|
| Toolbar Predict | Predict (plain button, greyed while a sweep runs) | yes |
| Toolbar Export CSV | Export CSV (file dialog in a sized window; `.csv` added) | yes |
| Toolbar Guide, `?` | Guide, Help | yes (`?` is a labelled Help) |
| Sample: D, Molecules in view, Brightness | typed spin fields, Qt ranges and decimals | **fixed** (were sliders) |
| Optics: w_r, w_z, Pixel size, Membrane (2-D) | same | **fixed** |
| Scan: Pixel dwell, Line overhead, Pixels per line, Lines per frame, Frames | same | **fixed** |
| Estimator (folded): Lags fitted, Repeats, Seed | same, folded at first | yes |
| Error vs dwell plot: both axes log, line + markers, "your setting" diamond | same; gaps where a dwell is not realisable | **fixed** (were unconnected points) |
| Numbers table: Dwell, Line, Frame, Error | `data_table`, numeric columns, header sort | **fixed** (was hand-drawn text) |
| Status bar: progress, verdict, failure | status line (progress, verdict, failure, export notice) | yes |

## 3. Files

| File | Change |
|---|---|
| `gui/view_model.py` | `status_text`, `predict()` (progress), `request_predict/export`, `enabled`, `csv_text/export_csv` (the Qt CSV), `sweep_numbers()`, `export_settings/restore_settings` |
| `gui/precision_emtk.view.json` | new: form (field names, ranges, decimals, descriptions equal to `precision.view.json`) and numbers table |
| `gui/app.py` | rewritten: spec form, `SnapshotJob` sweep, plot, sized export dialog, help/guide, drop-in `make_app(**kw)` for the hub |
| `gui/tool.py` | now only hosts the app (hub embedding `RicsPrecisionTool(embedded=, view_model=)` kept) |
| `gui/guide.json` | plot target fixed, Predict step added |
| `test/test_emtk_rics_parity.py` (19), `test/test_emtk_rics_clicks.py`, `test/pointer.py`, `tests/__init__.py` | new / added |

## 4. Regressions found in the earlier emtk app (all fixed)

| # | Finding | 5-line reproduction |
|---|---|---|
| 1 | **The curve was unconnected points** (`set_next_line_style` then `plot_scatter`) | `before_emtk_populated_1200x800.png` |
| 2 | **Fields were sliders** (`bounded_float`): no typed value, the handle covers the number | same image |
| 3 | **Hand-drawn table** | `begin_table` in `pre-upgrade/gui/app.py` |
| 4 | **Inputs stayed editable during a sweep and the sweep's result overwrote the edit** (SnapshotJob copies every attribute back) | type a value while Predict runs: after the sweep the field is back at its old value |
| 5 | **A worker exception was not reported** (`job.error` unread) | make `predict` raise: status stays "Predicting..." forever |
| 6 | **A long failure message was clipped at the window edge** (`text_colored`) | `before_emtk_error_1200x800.png` |
| 7 | **Export CSV opened the file dialog before checking there was anything to write; its window covered the whole app** (shared `install_csv_export`, unsized `im.begin`) | press CSV before Predict |
| 8 | Emoji labels (`▶ Predict`, `💾 CSV`, `⚙️`), a green Predict | `before_emtk_*` |
| 9 | Guide target `{"key": "plot"}` resolved to nothing (seam guard failed), no Predict step | `pytest test/test_plugin_help_guide_seam.py -k rics_precision` |
| 10 | No settings persistence | `export_settings` absent |
| 11 | **Table sort sorted text** (`"314.8"` before `"4.5"`) | click `Error [%]` twice: found by the click test; the table now has numeric columns |

## 5. Numbers equal the Qt tool

The Qt AutoForm tool and the emtk app share `PrecisionViewModel`/`core`; the evidence run of the Qt tool
(`before_populated.log`, n_repeats 10, n_images 20, seed 1) printed the verdict
`At 8 µs: 7.3 % error (usable) — about 1.7x worse than the best dwell (15.8 µs).`, nine rows
(`0.5 / 0.0384 / 2.46 / 314.8` ... `500 / 38.4 / 2.46e+03 / 9.8`), the CSV and the failure
`Prediction failed: n_lags=15 is too large for a 8x8 image: ...`; `test_predict_gives_the_qt_tools_numbers` pins all of them and
reproduces them through the app's worker (button and direct), and `test_the_form_has_the_qt_specs_fields` compares every field
(attr, kind, min, max, decimals, label, description) with the Qt spec.

## 6. Automated evidence

```
after: 48 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/rics_precision
compare: exit 0   (lost [] / stale_explanations [] / untooltipped [])
$ python -m pytest chisurf/plugins/calculator/rics_precision -q -p no:cacheprovider
82 passed, 1 xfailed in 37.95s
$ python -m pytest chisurf/plugins/calculator/test/test_native_factories.py -q -k rics   (the hub's factory tests)
2 passed, 22 deselected in 2.58s
```

Deliberate differences (`deliberate.json`, 6): the Qt `?` is Help; Lags/Repeats/Seed are drawn only while the Estimator panel is
unfolded (the static inventory is taken folded); `w_r`/`w_z` show the underscore where Qt renders a subscript.

Break-on-purpose (restored): the curve drawn as scatter -> `test_the_curve_is_drawn_as_a_line_...` failed; the CSV joined with
commas -> `test_predict_gives_the_qt_tools_numbers` and `test_export_csv_paths` failed; the inputs no longer greyed during a sweep ->
`test_predict_is_greyed_while_the_sweep_runs_and_inputs_cannot_be_typed` failed.

## 7. Click coverage (`test/test_emtk_rics_clicks.py`)

| Control | Test |
|---|---|
| Predict (start, greyed while running, progress text) | `test_predict_button_runs_the_sweep_and_the_table_and_verdict_appear`, `test_predict_is_greyed_while_the_sweep_runs_and_inputs_cannot_be_typed` |
| failure message, no stale curve, Export refused | `test_a_failing_prediction_shows_the_message_and_clears_the_curve` |
| Export CSV (nothing yet, Cancel, Save, typed name, x, Escape, unwritable) | `test_export_csv_before_a_prediction_says_so_and_after_writes_the_file`, `..._name_typed_without_a_suffix_gets_csv_and_the_dialog_x_closes_it`, `test_export_to_an_unwritable_place_is_reported` |
| D, Molecules, Brightness, w_r, w_z, Pixel size, Pixel dwell, Line overhead, Pixels per line, Lines per frame, Frames, Lags, Repeats, Seed: typed text, Qt clamp | `test_each_field_takes_typed_text_and_clamps_to_the_qt_range[...]` (14) |
| the same fields' arrows | `test_each_field_has_working_arrows[...]` (14) |
| typed dwell reaches the next prediction | `test_typed_values_reach_the_next_prediction` |
| Membrane (2-D) | `test_membrane_checkbox_switches_the_2d_geometry` |
| Sample / Optics / Scan / Estimator headers | `test_panel_headers_fold_and_unfold[...]` (4) |
| Help, Close Help | `test_help_button_opens_and_closes_the_help_window` |
| Guide, awaited D field and Predict, Close Tour | `test_guide_button_starts_the_tour_and_it_waits_for_the_controls` |
| tour Next / Prev | `test_the_tour_next_and_prev_buttons_can_be_clicked` (**xfail strict**, emtk gap) |
| plot wheel and drag | `test_the_plot_takes_the_wheel_and_a_drag_without_losing_the_curve` |
| table header sort | `test_clicking_a_table_header_sorts_the_rows_by_that_column` |

## 8. Screenshots read

`before.png`, `before_populated*` (Qt), `before_emtk_*`, `after_*_1200x800/800x600` (empty, populated, error, estimator unfolded,
export dialog, guide, help) and the click sequence `click_1_before_predict` ... `click_7_after_click_export_csv_nothing_to_write`
(Predict -> type dwell 15.8 -> Predict -> sort the error column -> unfold Estimator -> type 15/8/8 -> Predict fails -> Export
refused). Nothing clipped at 1200x800 or 800x600.

## 9. Persistence, guide, help, docs

`export_settings` / `restore_settings` of the 15 inputs (round trip, bad types ignored). Guide: 6 steps with awaits on D and Predict;
help.md unchanged (substantive, links live). Docs: none changed. The Qt-hosted `RicsPrecisionTool` is unchanged for the hub.

## 10. Blocked / open

Same emtk gaps as `vv_vh_anisotropy/REPORT.md` section 10 (tour Next/Prev share an id; a table keeps a removed row's selection;
`input_float` is a drag field). Docs gap: none.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
