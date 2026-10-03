# emtk port report - `fret_line` (audit-all row 78, upgrade to verified parity)

Agent: claude (Sonnet), 2026-10-03, T-20261002-LEFTOVERS, UPGRADE_BRIEF. Type A (the earlier stream's emtk app existed: hand-drawn controls, state kept in the app, no spec, no tests). Verdict: **accept**; the machine was heavily loaded (load 12-21) so every capture ran one at a time.

Commits: baseline + pre-upgrade (see the board status line), then the app/tests commit and the evidence/docs commit.

## 1. State at start
Uncommitted: modified `__init__.py`, `gui/__init__.py`, `manifest.json`; untracked `gui/app.py` (636 lines; copied to `pre-upgrade/app.py.txt`). Defects of the stream's app (`before_emtk_populated_*.png`): every control hand-drawn in one tall window (no spec, no grouping), no Qt-free model, the component list a combo, sweep fields as bare inputs, the lines list as stacked checkboxes and buttons, Save CSV through the shared untitled export window with a CSV format that differs from the Qt writer, Push to ndX greyed, the parameter editor as slider rows (unbounded sliders over +-1e12: unusable except by typing), a failed curve load left no message, no tests.

## 2. Qt checklist (`before.png`, `before_populated_{start,static_line,two_lines,800x600}.png`, `qt_values.json`)
| # | Qt control | emtk | |
|---|---|---|---|
| 1 | Components list (`C0: model (w=1)`), + Add, - Remove (greyed with one) | components `data_table` (same text per row), Add, Remove | yes |
| 2 | Model combo (replaces the selected component, weight kept) | spec choice `Model` | yes |
| 3 | Weight spin (0-1e6, 4 decimals) | spec spin field | yes |
| 4 | Editor (model editor widget of the selected component) | live model editor window: input curves (load/unload with file chooser), donor reference, subcomponent buttons, model settings, `Model parameters` table (value, fixed, bounds, lower, upper; editable cells) | yes |
| 5 | Vary combo (editable, substring filter) | `Filter` field + `Vary` choice; the filter moves the choice onto a listed target | yes |
| 6 | all params | toggle `All parameters` | yes |
| 7 | Min, Max (+-1e9, 4 decimals), log, Points (2-10000), tau_D0 (0-1000, 3 decimals) | spec fields with arrows | yes |
| 8 | + Add FRET line, Save CSV, Push to ndX (greyed without lines) | action bar (same enabling) | yes |
| 9 | FRET lines list with check boxes, Show all, Hide all, - Remove, Clear all | lines `data_table` with an editable Show column, same buttons | yes |
| 10 | two plots (E_FRET vs tau_F, tau_X vs tau_F + dashed diagonal), tab titles | two dock windows with axes, legend, wheel zoom, drag pan | yes |
| 11 | information / warning message boxes | in-app notice (title, text, OK) | yes |
| 12 | ? and Guide | Help and Guide buttons with a real help page and tour | yes |
Gained: tooltips on every control, settings round trip, the Fixed/Bounds/limits editable per parameter.

## 3. Reuse
Shared: `emtk.view_form` spec + `data_table` (as plugin_manager / plugin_check), `chisurf/emtk/help_guide.py`, `plugins/emtk_layout.cap_widths`, `core/algorithms` (sweep engine, unchanged), the Global View parameter registry, `emtk.file_dialog.FileDialog` + `DialogWindow`, `imaging_emtk.testing.Driver`. Replaced duplicates: the app-local state and CSV code moved into one Qt-free `gui/model.py`; the slider rows of `calculator/native_form.parameter_field` (a shared helper for bounded calculator parameters, wrong for unbounded fit parameters) are replaced here by the editable table; `parameter_field` itself is untouched and flagged (it offers a +-1e12 slider for an unbounded parameter). The shared `calculator/export.py` (untitled Save window) is no longer used by this plugin.

## 4. Evidence
`after: 73 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [], untooltipped [], 131 explained = Qt model-editor widget text, sweep-target labels, captions; stale_explanations 0). Populated by real clicks (`scripts/capture_clicks.py`): `click_1..N_*.png` and `after_populated_{1200x800,800x600}.png`; guide figures `docs_fret_line_tool*.png`.

## 5. Layout
1200x800 and 800x600 read at full size. Asserted (`layout_problems`, `clipped_texts`, plots excluded: rotated axis labels): no overlap, nothing outside the window. The Qt arrangement is kept (mixture / editor on top, plots below, action bar under all); the first draft's three-column arrangement cut the editor's combos at 800 px and was replaced. Idle: Remove (one component), Save CSV / Push / Show all / Hide all / Remove line / Clear greyed without lines, no frames requested at rest.

## 6. Tests
`pytest chisurf/plugins/fret_line -q`: ```
$ python -m pytest chisurf/plugins/fret_line -q -p no:cacheprovider
59 passed, 2 xfailed in 170.19s
```
Numeric parity with the live Qt tool: sweep target labels (1 and 2 components, relevant/all), the static line point for point, a log sweep with a user tau_D0 and 40 points, the dynamic line, line names/colours/components strings, visibility/remove/clear rules and numbering, the CSV byte for byte, component list text, add/remove rules, weight kept on a model change, defaults and limits. Breakage twice (the sweep no longer restores the swept parameter; the CSV writes 6 digits): 1 failure each, restored.
Control -> test (real pointer/keys/wheel via `Driver`, outcomes asserted): tabs `test_the_three_tabs_are_clicked...`; Add/Remove `test_add_and_remove_buttons...`; component rows `test_a_click_on_a_component_row...`; Model combo `test_the_model_combo_replaces...`; Weight typed/arrows/clamp `test_the_weight_field...`; parameter cells typed, Fixed/Bounds boxes, limits `test_a_parameter_typed_into_the_editor_table...`, `test_the_fixed_and_bounds_boxes...`; subcomponent buttons, section headers `test_subcomponent_buttons...`, `test_the_editor_headers...`; curve chooser cancel / load / unload / bad file `test_load_curve_file_opens...`, `test_a_curve_file_chosen...`, `test_a_curve_file_that_is_no_curve...`; Min/Max/Points/tau typed, clamped, arrows `test_min_max_points_tau_*`, `test_the_sweep_arrows_*`; log and All parameters `test_the_log_and_all_parameters_checkboxes...`; Filter + Vary `test_the_filter_narrows...`; Add FRET line, error notice `test_add_fret_line_computes...`, `test_a_log_sweep_from_zero_reports...`; Show checkbox in the table `test_the_show_checkbox_in_the_table...`; Show all/Hide all/Remove/Clear `test_show_all_hide_all_remove_and_clear_buttons`; the dynamic line built by clicks `test_the_dynamic_line_is_built_with_clicks...`; Save CSV chooser/cancel/typed name/notice OK `test_save_csv_opens_the_chooser...`; Push notice and host connection `test_push_to_ndx_*`; plot drag and wheel `test_a_drag_pans_the_plot...`, `test_the_wheel_zooms_the_plot`; dock divider `test_the_divider...`; Help/Guide/tour with awaits and card placement `test_help_button...`, `test_the_tour_is_walked...`, `test_every_guide_target...`, `test_the_tour_card_does_not_cover...`; host drop `test_a_file_dropped...`; small window `test_the_whole_flow_works_in_the_small_window_too`. Guard: module fixture fails on any change in the real `~/.chisurf` except `logs/`; tests run on temp settings and HOME.
Strict xfails (emtk gaps, not edited): (1) Ctrl+A does not select in a table cell editor; (2) Enter in a text field that was emptied does not commit it (a click away does).
Pre-existing failures: none in this folder.

## 7. Docs
`docs/guides/82_fret_lines.md` updated to the emtk UI (control names, steps, Push notice, no more "no Guide button" defect) with figures regenerated from the emtk app (`fret_line_tool.png`, `fret_line_tool_lines.png`); `help.md` and `guide.json` rewritten (6 steps, 3 awaits). The generated reference page is unchanged (surfaces already list emtk).

## 7a. Commits
`a23511412` baseline + stream state; the app/tests commit and the evidence/docs commit follow it (hashes on the board).

## 8. Findings
Real defects fixed: the sweep left the swept parameter at its last value in the Qt tool and nothing restored it (the native model restores every parameter; a deliberate difference, tested); the Vary choice could not select the only filtered entry (the filter now moves the choice); the stream's CSV differed from the Qt writer; unbounded fit parameters rode a +-1e12 slider.
Deliberate differences: default sweep target is the mean distance (RDA0), not the first parameter; the native model list adds the backend's "FRET: Fixed distance" entry; Push to ndX shows the Qt notice (no ndX connection) unless the host gives one; the Qt colour text of the lines list is a Colour column.
