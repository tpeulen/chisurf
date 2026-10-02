# emtk port report - `maxent_decay` (upgrade to verified parity, audit-all row 69)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`, claim `T-20261002-UPG6`. Verdict: **accept** with the open items in section 7.
Commits: `da3166399` Qt baseline + earlier-stream files (`pre-upgrade/`), then the upgrade commit and the evidence commit.

## 0. Hermetic first
Before any run I grepped the plugin: `core/settings.py` writes `~/.chisurf/maxent_decay/settings.json` (via `get_path("settings")` or `Path.home()`), and the existing Qt smoke test closes a `MaxentDecayWidget`, which writes **QSettings** (geometry, dock layout). New `test/conftest.py` (autouse, applies to all tests of the folder) points HOME, `CHISURF_SETTINGS_DIR`, `MMFDB_*`, `chisurf_settings_path`, the plugin's `_get_path` and QSettings (INI format) at a temp folder; `test_zzz_the_real_chisurf_folder_was_not_touched` compares the real `~/.chisurf` file list and mtimes before and after (the session logs chisurf itself starts in `logs/` ignore `CHISURF_SETTINGS_DIR` and are excluded). The Qt baseline captures ran with temp HOME/settings/QSettings too.

## 1. Defects found in the earlier-stream app
* Layout: all controls in one column of full-width sliders with captions on the right, 13 stacked action buttons, three collapsing headers, the right plots cramped; **Run MEM, L-curve, Sample and Save were only reachable by scrolling past the settings**. Replaced by a spec form (spin fields, grouped panels), action rows at the top, mode-specific panels (lifetime grid or distance grid), a collapsed L-curve/sampling section.
* Taking a live fit did not do what the Qt Refresh did: the smallest lifetime follows the IRF width (tau min 0.113 ns here) and the period the decay window (8.24 ns). Without it the same data gave a different grid than Qt. Fixed (`MEMModel.load_fit`, rounded like the Qt spin boxes) and tested against the Qt widget.
* Actions that cannot work were enabled: Run with no data, Save/Sample with no result, Donor outside FRET mode, Run in FRET mode without a donor; the period field was live while periodic convolution was off. All greyed now.
* The "Start fraction of peak" box, which the Qt tool keeps hidden, was exposed (removed from the form; the value stays in the JSON preferences); "MEM iterations" stays as an extra.
* No drops, no last-folder memory, status line stale after loading data.
* Name clash found while writing the tests: an app method named `press` shadows `ImApp.press` and breaks input (renamed).

## 2. Qt checklist -> emtk -> test
| Qt control | emtk | Test |
|---|---|---|
| toolbar Run, L-curve, Sample, Save | Run MEM, L-curve, Sample, Save (greyed rules above) | `run_gives_the_solver_result...`, `lcurve_button_sweeps...`, `save_writes...`, `empty_window...` |
| Refresh, IRF, Prior, Donor, Fit | Refresh (+ Fit, Use as decay/IRF), Load decay, IRF file, Clear IRF, Prior, Donor, Donor from fit | `refresh_lists_live_fits...`, `load_decay_and_irf...`, `fret_fields_and_the_donor_gate` |
| JSON, Guide, ? | JSON editor (Apply / Close), Guide, Help | `json_editor...`, `help_opens...`, `tour_waits...` |
| Mode, nu, L-curve span, tau grid, tau0, R0, period, periodic, R range, donor-only + fix, timeshift/background/IRF bg/lamp scatter + fix, Fit nuisance | spec fields (Qt ranges), switches | `each_setting_takes_typed_values...[19]`, `arrows_step...[5]`, `mode_choice...`, `period_field_is_greyed...`, `every_switch_is_clicked[5]`, `fixed_nuisance_values_reach_the_solver` |
| Sampling group (steps, thinning, walkers, chunk, CPUs, vectorized) | spec fields | same tests, `save_writes_the_result_folder_and_sample_writes_the_chains` |
| plots: decay with fit range region, residuals, distribution, L-curve | implot, axes, legends, draggable fit range, wheel zoom, L-curve point click | `dragging_the_fit_range_box...`, `wheel_zooms...`, `lcurve_button...` |
| (gained) file drops, cancel, last folder | yes | `dropped_files...`, `run_is_cancelled...`, `settings_round_trip` |

## 3. Numeric parity (Qt tool fed the same stub live fit)
`refreshing_from_a_live_fit_sets_the_same_values...` (tau min, period, background, timeshift, IRF background, fit range, data and IRF labels), `the_mem_run_equals_the_qt_run` (chi2 rel 1e-6, S, p, tau axis), `the_lcurve_sweep_equals_the_qt_sweep` (16 chi2 / norm / nu values; chi2 within 0.05 %, see open items).

## 4. Tests
```
$ python -m pytest chisurf/plugins/fluorescence_decay/maxent_decay -q -p no:cacheprovider
78 passed in 47.69s     (61 new + 17 existing; the existing export test now gets a clean tmp folder)
```
Deliberate breakage (restored): IRF-width rounding removed + period always enabled -> 4 failed (Qt refresh, Qt run, Qt L-curve, period greying); Save always enabled + last folder lost + cancel button inert -> 2 failed.
`compare`: exit 0 (lost 0, explained 16, stale 0, untooltipped 0), qt-free yes; `after.json` is the union of lifetime and FRET mode, the opened L-curve/sampling section and the JSON editor.

## 5. Layout and evidence
`after_populated_{1200x800,800x600}.png` vs `before_populated_*` (Qt) and `before_emtk_populated_*`; `click_*.png` (empty greyed window, dialog, loaded decay and IRF, run, typed nu, L-curve, clicked L-curve point, dragged fit range, wheel zoom, mode list, FRET, JSON, Help, Guide). Two-column label/field grids with arrows, capped widths, grouped panels, all four plots with axes and legends, plots 62 % of the width, no text past the edge at 800x600 (test).

## 6. Reuse and docs
Reuse: `emtk_layout` (layout_spec, LabelColumn, button_row), spec forms with `spin` and `choice`, `FileDialog`+`DialogWindow`, help/tour, `chisurf/plugins/emtk_test_input.py`. Not applicable: channel editor, dataset picker (the plugin lists session datasets itself from `chisurf.imported_datasets`), imaging shell. Removed: `bounded_float` sliders and the hand-written field/checkbox helpers.
Docs: `docs/guides/62_maxent_decay.md` (new window figure `figures/maxent_decay_window.png`, step 1 and 2 names), `docs/reference/plugins/maxent_decay.md` (hand-edited native-window table; the generator will drop it until it reads the emtk spec), `help.md` (no emoji), `guide.json` (awaits on Refresh, Run MEM, L-curve; Qt-era target names kept as aliases).

## 7. Open
* The Qt L-curve chi2 plateau is 0.05 % higher than the native sweep with identical grid, range and settings; the single runs agree to 1e-6. Not explained (Qt passes no `tol`; the solver default equals the setting); the corner and the curve shape agree.
* Click evidence ends with the Guide start; `emtk_preview.json` untouched. Wheel scrolling of the controls window works (used by the tests).
