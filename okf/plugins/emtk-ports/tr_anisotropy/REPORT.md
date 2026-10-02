# emtk port report - `tr_anisotropy` (upgrade to verified parity, audit-all row 53)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`. Claim `T-20261002-UPG6`. Verdict: **accept** with the open items in section 9 (click evidence is partial: 10 of ~17 planned frames, the capture script stalled at the table-edit step; every control is nevertheless covered by a test).

Commits: `00aa988f0` Qt baseline + earlier-stream files (pre-upgrade/), then the upgrade commit and the evidence commit of this pass.

## 0. Regressions and defects found

* The earlier-stream app's **default corrections were 1.0 / 0 / 0** where the Qt wizard starts from the stored 1.16 / 0.12 / 0.44 (`anisotropy_corrections.json`); the window now reads the stored defaults and spectra without writing (test `corrections_defaults_and_spectra_files_equal_the_qt_wizard`).
* Next was **gated** on files/spectra in the earlier app, the Qt wizard never gates (and shows check marks); now ungated with the Qt check marks (`[x]`).
* Layout: full-width sliders with captions to the right, labels right-aligned, tables stacked 180 px high with empty space, emoji in the navigation (Qt pictograms), IRF plot legend over the peak, no status/Back/Next bar. All replaced (before/after PNGs).
* Idle controls: Load, Export, background fields, Create fits, first-column / bin-width fields are greyed when they mean nothing.
* A crossed background region: Qt silently skips the subtraction (empty region); native swaps the two numbers (deliberate, test `a_crossed_region_is_swapped...`).
* **Pre-existing test wrote into the user's real `~/.chisurf/anisotropy_corrections.json`** (`test_view_model.py::test_corrections_are_float_properties`; my baseline run of it overwrote the file with 1.5/0.11/0.22 because my first env script was broken). I restored the shipped default content (1.16/0.12/0.44, the file was seeded from it on 2026-09-08; the user's own values, if any, are lost) and made that test file hermetic.
* Own bug caught by a click test: a button and a field with the same `##id` share one emtk id, and the two spectra tables' "add"/"delete" collide across child windows (fixed with `push_id`).

## 1. State at start
`pre-upgrade/git_status_at_start.txt`; copies of the earlier stream's files in `pre-upgrade/`. Qt baseline: `before.png/json` (46 controls), `before_populated_{1_data..5_finish}.png` (synthetic IRFs/decays with a known answer, Qt wizard on a stub session with a `TCSPCReader`), `qt_values.json`, `before_emtk_*` (earlier app, 6 steps x 2 sizes).

## 2. Qt control checklist
| Qt control | emtk | Test |
|---|---|---|
| nav list with check marks, 6 steps, tooltips | selectable `[x] Title`, subtitle tooltip | `each_step_is_reached...`, `the_check_marks_follow...`, `qt_wizards_step_texts_and_check_marks...` |
| Back / Next | Back / Next bottom right, greyed at the ends | `back_and_next_walk_the_steps...` |
| Guide, ? | Guide, Help | `help_opens...`, `tour_is_walked...` |
| 4 file fields + "..." | typed path + Browse + found/missing | `each_path_field...`, `browse_opens...[x4]`, dialog Cancel/close |
| info checklist of the files | found / missing marks + text | same |
| Load / reload data | Load / reload data (greyed without files) | `load_is_greyed...`, `bad_file...` |
| BG from / to spin boxes | Background from / to spin fields | `typing_the_background...`, `clamp...`, `arrows...` |
| IRF plot, region drag | implot, log y, 4 curves, legend, axes, draggable box, wheel zoom | `dragging_the_green_box...`, `the_plot_has_axes...`, `the_wheel_zooms...` |
| g-factor, l1, l2 | spin fields, Qt limits | `each_correction_takes...`, arrows |
| two spectra tables, a/l/rho + add/remove | `data_table` x2 (edit, Delete), add fields, Add / Remove | `double_clicked_cell...`, `escape...`, `refused_edit...`, `add_component...`, `remove_selected...`, `delete_key...` |
| Save / Load spectrum | Save spectra (stored file, else dialog) / Load spectra | `save_spectra...`, `fresh_window_saves_to_the_stored_default...`, `load_spectra...`, damaged file |
| Create fits + status | Create fits + status line + "Created:" list | `create_fits...` x2 |
| Finish button (closes window) | none (deliberate) | |
| (gained) stacked files, reader settings, Export corrected IRFs, file drops | yes | `stacked...`, `reader_fields...`, `export...`, `dropping_files...` |

## 3. Numeric parity (Qt wizard built offscreen, same data)
`loading_and_the_background_correction_equal_the_qt_wizard` (all raw and corrected curves, default region, 4 regions), spectra files byte-equal as JSON, defaults equal. Fit creation: both use the shared `build_link_plan`; native parameter values / links asserted in `create_fits...` and `test_native.py`.

## 4. Tests
```
$ python -m pytest chisurf/plugins/fluorescence_decay/tr_anisotropy -q -p no:cacheprovider
94 passed in 47.96s       (71 new in test_emtk_tr_anisotropy_parity.py + 23 existing; seam/PRD guards: 99 passed with test/test_plugin_help_guide_seam.py, test_prd_mentions.py)
```
Deliberate breakage (restored): swapped amplitude/value in Add + dropped region recompute -> 3 failed (`typing_the_background...`, `background_fields_clamp...`, `add_component...`); removed the await notification and the Create-fits guard -> 1 failed (`tour_is_walked...`).
`compare`: exit 0 (lost 0, explained 22, stale 0, untooltipped 0); `after.json` = union over all six steps (`scripts/after_all_states.py`); qt-free yes.

## 5. Layout (1200x800 and 800x600, read at full size)
`after_populated_{1..6}_{1200x800,800x600}.png` vs `before_emtk_*` and `before_populated_*`: two-column label/field grids (emtk_layout), capped widths, grouped reader settings, plot takes all remaining space, tables expand, side-by-side at >=760 px else stacked, no clipped text (test `no_text_is_cut_off_in_the_small_window`).

## 6. Click evidence
`click_1..10_*.png` (Data via nav, typed path, Browse dialog, file chosen, two files dropped, Load, drag of the box edge, typed channel, wheel zoom, g typed). Frames 11+ (table edit, add, save, create fits, help, guide) not captured: the capture script stalled; the same flows are asserted in the tests.

## 7. Reuse
Used: `emtk_layout` (layout_spec, LabelColumn, button_row), `view_form` spec forms with `spin`, `data_table` (edit/delete/select), `FileDialog`+`DialogWindow`, help window/tour, `chisurf.emtk.datasets`. New shared test helper `chisurf/plugins/emtk_test_input.py` (real-input Driver) for the other ports. Not applicable: detector/channel editor, dataset picker, imaging shell. Local duplicates removed: hand-built spectrum spec/handlers (`spectrum_spec`, `add_/remove_/edit_lifetime`) replaced by `SpectrumTable` + the spec.

## 8. Docs
`docs/guides/10_lifetime_anisotropy_fitting.md` (new "Anisotropy Wizard" section, steps = emtk controls), figures `docs/guides/figures/tr_anisotropy_{data,normalize,components}.png` from the app, `docs/reference/plugins/tr_anisotropy.md` (hand-edited: surfaces + native window table; the generator will drop it until it reads the emtk spec), plugin README. Concept page `anisotropy.md` unchanged (no wording change). Guide: 6 steps, 5 `await`; help.md unchanged (links verified).

## 9. Open
* emtk gaps (repros): (a) `draw_table` passes modifiers 0 to `DataTable.key`, so Ctrl+A in an open cell editor does nothing (open a cell, send key 0x41 with Ctrl, type: text appended); (b) buttons/fields `Label##id` share an id with any same-`##id` widget, also across child windows (`push_id` needed).
* Click evidence frames 11+ missing; `emtk_preview.json` untouched.
