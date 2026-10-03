# emtk port report - `ptu_alex_creator` (audit-all row 57, upgrade)

Agent: claude (Sonnet), 2026-10-03, board entry `T-20261003-EMTKUP7`. Verdict: **accept** (one emtk gap reported, section 7).

Commits: `7ed707fa2` Qt baseline + the earlier stream's manifest entrypoint and README, `83c038740` app, tests, translations, Qt help button, then the evidence/docs commit.

## 1. State at start
The earlier stream's app (`gui/app.py`, guide, help, translations, tests) was in HEAD without manifest/README; both committed with the baseline (`pre-upgrade/` has copies and the diff). Qt baseline: `before.png`, `before_populated_{controls,histogram,batch}_{1200x800,800x600}.png` (Qt shows three tabs), `before_emtk_populated_*` (the earlier emtk app: labels right of the fields, stacked file row, drag fields for Period/Shift, labels clipped at 800 px, queue showing base names only).

## 2. Qt control checklist
| Qt control | emtk | Test |
|---|---|---|
| file line edit (editingFinished loads, drop) | `File` field, Enter / click-away loads, drop outside the queue loads | typing_a_path_and_enter_loads_it, dropping_one_file..., a_path_that_is_not_a_file_says_so |
| Load (browse) | Open… (file chooser) + Load button | open_button_..., load_button_... |
| Save (grey until loaded, save dialog, "Saved to") | Save as… same rule, chooser with suggested name, written path above the plot | save_* tests |
| Input / Output choice | spec choices, same options | defaults_and_choices_equal..., input_format_choice_is_clicked, another_output_container... |
| Period / Shift spin boxes (1..1e6 step 100, +-1e6 step 1) | spec `spin` fields: typed + Enter, arrows, wheel, clamp | typed_values..., each_arrow..., wheel_over_a_field... |
| histogram plot | implot with axes, wheel zoom, drag pan, live refold | histogram_and_converted_file_equal..., layout |
| Batch mode radios | spec radio | mode_radios_are_clicked |
| path list: Files / Folder / Database / Remove / Clear, drops | Add files… (multiselect) / Folder… / Database / Remove / Clear on a `data_table` (Delete key, wheel scroll); drops | add_files..., folder_button..., database_button..., remove_is_grey..., delete_key..., clear_empties..., wheel_scrolls_a_long_queue, drops tests |
| Output folder edit + `...` | typed field + Browse… (folder chooser) | output_folder_is_typed_and_browsed |
| Run batch (warnings, "Batch complete") | Run batch, reasons in red above the plot, written names listed | run_batch_says_what_is_missing, run_batch_with_real_input_writes_the_files |
| (none) help | Help + Guide buttons; the Qt tool gained a `?` help button | guide_and_help_buttons_work, the_qt_tool_has_a_help_button |

Deliberate (`deliberate.json`, compare exit 0, stale [] ): choice entries are drawn only while a list is open; "Save"/"Files" are "Save as…"/"Add files…"; the list heading is the queue table. Behaviour: the queue selects one row (Qt: extended selection); message boxes ("Saved", "Batch complete", warnings) are the status line above the plot; the dock tabs are two side-by-side windows; the dock layout is no longer saved (nothing to dock).

## 3. Regressions found and fixed
* Earlier app: Period/Shift were drag fields (a typed value was impossible, `input_int` is a drag field in emtk): now spec spin fields with the Qt range and step.
* The whole form was greyed while the live histogram recomputed (every arrow click or wheel notch): the preview has its own worker; load/save/batch alone grey the form.
* A wheel notch stepped a spin field once per frame while unconsumed (emtk gap, section 7): the app consumes the notch at the end of the frame.
* Labels right of the fields and clipped at 800 px, queue without full paths: one label column, capped widths, tooltips with the full path.
* A preview finishing after a new file was loaded overwrote the new histogram: guarded by the loaded path.

## 4. Tests
`python -m pytest chisurf/plugins/tttr/ptu_alex_creator`: 63 passed (49 new in `test_emtk_alex_parity.py`: hermetic temp HOME / CHISURF_SETTINGS_DIR / MMFDB_*, real `~/.chisurf` snapshot guard ignoring logs and the bytecode cache; numbers equal the Qt view model for histogram, converted file, convert and merge batch, HT3 output; real pointer/key/wheel/drop input for every control; layout at 1200x800 and 800x600; tooltips via inventory; all spec/guide/message texts in five locales; Qt-free). Deliberate breakage twice (queue removal disabled, period clamp removed): 3 failed (remove, Delete key, settings round trip); restored.

## 5. Layout
Screens `after_populated_{1200x800,800x600}.png`, `after_*`: no overlaps, one label column, short number fields, plot gets >35 % of the window, queue >= 60 px. Tour card cleared of every target (both sizes).

## 6. Reuse and Docs
Reuse: `emtk.view_form` spec form + `data_table`, `emtk_layout` (layout_spec, LabelColumn, button_row), `emtk.file_dialog`, `chisurf.emtk.dataset_picker`, help/tour, `BackgroundJob`, `emtk_test_input.Driver`; no local duplicate found. Docs: new `docs/guides/100_alex_creator.md` (+ figure `figures/alex_creator.png` from the app, index entry), `docs/reference/plugins/ptu_alex_creator.md`, in-app `help.md` and its translations; concept `us_alex.md` unchanged.

## 7. emtk gap (5-line repro)
```
app.pointer_move(x, y over a spin field); app.wheel(x, y, 1.0); app.draw(...)   # +1 step
app.draw(...)                                                                 # +1 step again: the field does not consume io.mouse_wheel
```
`view_form` (line ~441) should set `io.mouse_wheel = 0` after stepping. Also, wheel zoom of an implot works only outside a DockManager (this app uses plain windows).
