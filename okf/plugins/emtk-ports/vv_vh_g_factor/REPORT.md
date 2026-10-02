# emtk port report - `vv_vh_g_factor` (upgrade to verified parity, audit-all row 58)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`, claim `T-20261002-UPG6`. Verdict: **accept**; click evidence partial (10 frames, the capture script stopped at the batch dialog; those flows are asserted in tests).
Commits: `7115aedea` Qt baseline + earlier-stream files (`pre-upgrade/`), then the upgrade commit and the evidence commit.

## 0. Defects found in the earlier-stream app
* Layout: full-width borderless number fields with captions above, ~25 label/field lines in one scroll, **Export, Archive, Help and Guide below the fold** (unreachable at 1200x800), a plain "Batch" tab with a hand-listed queue, wrapped paths over the controls, decay checkboxes running past the window at 800 px.
* Edits made while a background job ran were overwritten when the job published its snapshot (fields are now greyed while busy; `model.busy`).
* A dropped second file / more files were ignored (`on_paths_dropped` loaded only the first): first = fast, second = slow, rest = batch queue (chained jobs, so the snapshot cannot drop them).
* No result table: 6 labelled text lines; a redundant "Calculate G" button (edits recompute on their own) was removed.
* Tools gaps: fields that mean nothing without data / without Background correction / without a manual toggle are now greyed through `model.enabled`.
* Hermetic: the tests of this plugin never wrote to `~/.chisurf` (checked by grep before running); the new test module asserts it (`test_zzz_the_real_chisurf_folder_was_not_touched`). chisurf's own session log in `~/.chisurf/logs` ignores `CHISURF_SETTINGS_DIR` (excluded from the assertion; repro: set the variable, import chisurf, a `session_*.log` appears in the real folder).

## 1. Qt checklist -> emtk -> test
| Qt control | emtk | Test |
|---|---|---|
| Load VV/VH File, path field | Fast reference... + path line | `fast_reference_loads_through_the_dialog...`, cancel/close, bad file |
| Load FP VV/VH File | Slow protein... | `slow_reference_adds_the_mixing_estimate` |
| Batch... (modal) | Batch anisotropy tab | `batch_queue_run_save_remove_and_clear...` |
| G-Factor / StdDev / corrected / BG fields | results table | all `g_factor_mixing_and_defaults_equal_the_qt_tool` |
| G field typing = manual | Manual G + G used | `manual_g_overrides...` |
| Background correction | toggle + background region fields | `background_toggle_enables...` |
| Flip, Shift | Flip VV/VH, VH shift | `flip_toggle...`, `arrows_step...`, `shift_and_flip_recompute_like_the_qt_tool` |
| rho, dt, r0 | spin fields | `mixing_parameters_are_typed...` |
| tau, Target rS, l1/l2 (typing = override) | manual toggles + fields | `manual_mixing_overrides...`, out-of-range warning |
| Show fast/slow/raw/corrected | checkboxes (+ Log counts) | `trace_checkboxes...` |
| plots with draggable tail/background regions | implot, axes, legends, draggable lines, wheel | `dragging_a_yellow...`, `blue_background_lines...`, `wheel_zooms...`, `plots_have_axes...` |
| warning label | status text under the tables | `out_of_range_estimate...` |
| (Qt batch: Run Batch, Save CSV, table) | Run batch, Save table..., table, Delete, Clear | batch test |
| (gained) Export calibration JSON, Archive, drops | yes | `export...`, `archive...` x2, `dropped_files...` |

## 2. Numeric parity (Qt tool built offscreen, same files)
G raw / corrected / SD, backgrounds, default tail and background regions, lifetime estimate, expected rS, shift and flip variants, and the batch r(inf) of two files equal the Qt tool and its batch window (4 parametrized/variant tests).

## 3. Tests
```
$ python -m pytest chisurf/plugins/vv_vh_g_factor -q -p no:cacheprovider
58 passed in 46.45s     (44 new + 14 existing; one existing tooltip-count test adjusted: form tooltips come from the spec)
```
Deliberate breakage (restored): background fields always enabled + renamed row + unsorted region -> 3 failed; drag adds 5 bins + await notification removed -> 1 failed (`tour_waits_for_the_real_controls`).
`compare`: exit 0 (lost 0, explained 19, stale 0, untooltipped 0), qt-free yes; `after.json` is the union of both tabs, populated, manual overrides on (`scripts/after_all_states.py`).

## 4. Layout and evidence
`after_populated_{1200x800,800x600}.png` vs `before_populated_*` (Qt) and `before_emtk_populated_*`; `click_1..10_*.png`. Grouped panels (Channels, Tail matching, Manual G, Slow-reference mixing), two-column label/field grids with capped widths and arrows, tables for results, all action buttons in one wrapping row at the top, plots get the right two thirds, legends top right, no text past the edge at 800x600 (test).

## 5. Reuse
`emtk_layout` (layout_spec, LabelColumn, button_row), spec forms with `spin`, `data_table` (results, mixing, batch queue with Delete), `FileDialog`+`DialogWindow`, help/tour, local `VvVhGFactorClient`, `chisurf/plugins/emtk_test_input.py`. Not applicable: channel editor, dataset picker, imaging shell. Duplicate removed: hand-drawn `numeric`/`check` helpers and the selectable-list batch queue.

## 6. Docs
New numbered guide `docs/guides/91_vv_vh_g_factor.md` (theory + application, headless snippet, figure `docs/guides/figures/vv_vh_g_factor_calibrated.png` from the app), registered in `docs/guides/index.md`; `docs/reference/plugins/vv_vh_g_factor.md` hand-edited (the generator will drop the native-window table until it reads the emtk spec). Concept page unchanged. `help.md` gained live Further-reading links; `guide.json` rewritten: 4 steps, 3 awaits on the real controls.

## 7. Open
* Click evidence stops at frame 10. Wheel zoom works (test), as in the other ports; tables cannot be edited (read-only by design).
* `emtk_preview.json` untouched.
