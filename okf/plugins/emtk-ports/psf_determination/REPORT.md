# emtk port report - `psf_determination` (upgrade to verified parity, audit-all row 56)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`, claim `T-20261002-UPG6`. Verdict: **accept** with the open items in section 7.
Commits: `85fe2e44f` Qt baseline + earlier-stream files (`pre-upgrade/`), then the upgrade commit and the evidence commit.

## 0. Hermetic first
The plugin writes nothing under the user's home (grep: only `Path.home()` as a read-only default folder of the Qt path picker in `sections.py`; saving is an explicit file). `test/conftest.py` and `tests/conftest.py` (autouse) point HOME, the chisurf/MMFDB folders, `chisurf_settings_path` and QSettings at a temp folder (the dataset picker queries MMFDB: the temp database has no session, the picker shows its own "Authentication required" log), and `test_zzz_the_real_chisurf_folder_was_not_touched` compares the real `~/.chisurf` before and after (chisurf's own `logs/` excluded: that logger ignores `CHISURF_SETTINGS_DIR`).

## 1. Defects found in the earlier-stream app
* **No help and no guided tour** (no `help.md`, no `guide.json`, no buttons): added both, with awaits on the real controls.
* **No demo**: the plugin has no sample data, so the tour could not be walked. `PsfViewModel.load_demo()` generates a stack with five beads of known size (FWHM 424 nm / 2120 nm), labelled as a demo.
* Controls: eight stacked buttons, the settings as full-width sliders with captions on the right inside a redundant "Controls" header, the bead index as a slider; actions enabled with nothing to act on (the error text appeared only after the click). Replaced by a wrapping button row whose members are greyed by what they need (stack, selected bead, detected beads, idle), spin fields (Qt ranges, from the same `psf.view.json`), a bead-index field whose range follows the detected beads, a status block.
* The window had no `export_settings` / `restore_settings` (the host seam; the app only had `settings()` / `apply_settings()`): added the aliases and last-folder memory.
* The status line did not name the source of the stack (a demo, a file).

## 2. Qt checklist -> emtk -> test
| Qt control | emtk | Test |
|---|---|---|
| Load Stack, Detect, Fit Selected, Fit All, Export CSV | same buttons, greyed by state | `empty_window_asks...`, `load_stack_through_the_dialog...`, `detect_runs_on_a_job...`, `fit_all_lists...`, `buttons_are_greyed_while_a_job_runs` |
| Bead # spin box + "Detected beads: n" | Bead index field, "n detected beads" | `bead_index_field...`, `bead_index_is_greyed...` |
| Pixel, Z step, ROI xy, ROI z, Px/frame, Min dist, Min area | spin fields from the Qt spec | `each_field_takes_typed_values...[11]`, `arrows_step_each_field[5]`, `native_forms_carry_every_field_range...` |
| image stack: z slider, click to pick, bead markers, fit circle, colormap | shared `ImageCanvas`: z slider, colormap, gamma, levels, wheel zoom, pan, pick | `clicking_a_bead...`, `z_slider...`, `colormap_gamma_levels...`, `wheel_zooms_the_image...` |
| x / y / z profile plots, Fit Results | profile tabs with data and fit, report | `fit_all_lists_every_bead_and_the_profile_tabs...` |
| (pyqtgraph ImageView operations, ROI plot, time range) | not applicable to a bead stack | `deliberate.json` |
| (gained) Demo stack, MMFDB dataset picker, Save/Load settings, drops, Help, Guide | yes | `demo...`, `mmfdb_button...`, `save_and_load_settings...`, `dropped_tiff...`, `help...`, `tour...` |

## 3. Numeric parity (the Qt tool's own model on the same stack)
`detection_fits_and_the_batch_csv_started_in_the_native_window_equal_the_qt_tools` (detected beads, batch report text, **the exported CSV byte-equal to the Qt model's**), `a_picked_bead_fit_equals_the_qt_tools_single_fit` (fit parameters, circle, report), and the physical widths of the known stack are recovered (`physical_widths_of_the_known_stack_are_recovered`: FWHM 424 / 2120 nm within 2 / 3 %; the Qt baseline gave 423.3 nm / 2116 nm, `qt_values.json`).

## 4. Tests
```
$ python -m pytest chisurf/plugins/microscopy/psf_determination -q -p no:cacheprovider
64 passed in 46.59s     (49 new + 15 existing: the earlier stream's native tests and the Qt view-model tests, unchanged)
```
Deliberate breakage (restored): fit/export always enabled + demo z step changed -> 5 failed; bead-index change no longer fits + last folder lost -> `bead_index_field_selects_and_fits...` failed.
`compare`: exit 0 (lost 0, explained 21, stale 0, untooltipped 0), qt-free yes; `after.json` is the union with a stack, beads, a fit, every profile tab, the colormap list, manual levels and the help window.

## 5. Layout and evidence
`after_populated_{1200x800,800x600}.png` vs `before_populated_*` (Qt, every tab) and `before_emtk_populated_*`; `click_*.png` (empty greyed window, dialog, TIFF drop, calibration, detection, picking, z profile, fit all, wheel zoom, colormap, bead index, Help, Guide). Grouped panels with two-column label/field grids, buttons wrap, no text past the edge at 800x600 (test).

## 6. Reuse and docs
Reuse: `chisurf.emtk.image_canvas.ImageCanvas`, `chisurf.emtk.jobs.SnapshotJob` (through the plugin's re-export modules), `DatasetPicker`, `emtk_layout` (layout_spec, LabelColumn, button_row), spec forms with `spin` built from the Qt `psf.view.json` (one source of truth), `FileDialog`+`DialogWindow`, help/tour, `chisurf/plugins/emtk_test_input.py`. Not applicable: channel editor, imaging shell hub (this is a standalone tool). Removed: the slider-based `native_form.fields` use and the hand-written action loop.
Docs: **new numbered guide `docs/guides/93_psf_determination.md`** (theory, steps, checks, Python snippet; figure `figures/psf_determination.png` from the app), registered in `docs/guides/index.md`; `docs/reference/plugins/psf_determination.md` (hand-edited native-window table and guide link); new `help.md` with live links; new `guide.json` (5 steps, 3 awaits).

## 7. Open
* The stack view is the shared canvas: its controls (z slider, colormap, gamma, levels, Reset view) take about a third of the stack window's height, so the image is small at 800x600 (equal-aspect plot). Not touched (shared); the split between stack and profiles is 0.60.
* `emtk_preview.json` untouched.
