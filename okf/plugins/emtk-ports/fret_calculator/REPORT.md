# emtk port report - `fret_calculator` (swap-candidate verification and upgrade, audit-all row 18)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4B`. Verdict: **accept** after the upgrade. The pre-upgrade app computed
the same physics but deviated from the Qt tool in five checkable ways (section 0); none lost data, all fixed inside the plugin's own app.

Commits: `b3d3e17db` Qt baseline and current emtk state (with `pre-upgrade/`), `166f72009` emtk app at parity with the Qt tool (code, tests, allow-list strikes), `e8c2a7c5f` evidence and report, then the click-coverage commit and its evidence.

## 0. What the pre-upgrade app got wrong (found by comparing with the Qt tool, not by the heuristic audit)

1. **Numbers differed from the Qt tool for the same edits.** The Qt spin boxes round every written result to the field's decimals (R 2, tau 4, E and rates 6) and clamp it; the emtk app kept full
   precision. Same inputs, Qt: `E = 0.8` gives `R = 47.62`; pre-upgrade emtk: `R = 47.622031559` (`before_emtk_hetero_inverse_*.png`, script `scripts/capture_emtk_before.py`). The shown value and the
   carried value also differed, so typing back the shown R did nothing. Now both round the same (`test_hetero_defaults_and_every_edit_equal_the_qt_tool`: 15 edits, equal to 1e-9).
2. **No numeric entry like the Qt fields.** Fields were log sliders (Ctrl+Click to type), the Qt tool had spin boxes. Now spec `value` fields with arrows (`style: spin`), typed value + Enter, the unit suffix accepted, range clamped.
3. **Dropped file: lost behaviour.** The Qt tool answered a drop with "The FRET Calculator takes no dropped files." The emtk app had no drop hook, so the host refused the drop silently. Now `files_dropped` / `on_files_dropped` / `on_paths_dropped` put that text on the status line (`test_a_dropped_file_says_...`).
4. **Failed calculations were silent** (Qt too). E = 0 or 1, tau = 0, tau > tau0 and kFRET = 0 each fail in the backend; the fields kept their values and nothing said why. Now the line under Guide/Help says "FRET from efficiency failed: ..." and the next edit clears it.
5. Hand-drawn fields (rule 4) with emoji labels (rule 6), emoji window titles, hard-coded window colours (rule 5), no `export_settings` / `restore_settings`, and a guide whose HomoFRET step had no target and no `await`.

Not a regression, found on the way: the Qt HomoFRET tab shows `k_homo = 0` at start and leaves it stale after an edit of tau0, R0 or rho although R_DA was recomputed (the field refreshes only after a t_RM or R_DA edit). The native field always shows the backend's rate (0.46875 at start). Deliberate, tested.

## 1. State at start

`git status --short chisurf/plugins/calculator/fret_calculator` (earlier migration stream, nothing modified in the last 60 minutes by anyone else, no foreign file staged):

```
 M chisurf/plugins/calculator/fret_calculator/gui/tool.py
 M chisurf/plugins/calculator/fret_calculator/manifest.json
?? chisurf/plugins/calculator/fret_calculator/gui/app.py
?? chisurf/plugins/calculator/fret_calculator/gui/guide.json
?? chisurf/plugins/calculator/fret_calculator/gui/help.md
?? chisurf/plugins/calculator/fret_calculator/gui/model.py
?? chisurf/plugins/calculator/fret_calculator/tests/test_emtk_app.py
```

`pre-upgrade/` holds those files, the tracked diff and `HEAD_tool.py` (the Qt tool as committed: AutoForm tabs). The working-tree `tool.py` is the stream's emtk host, so the Qt baseline is built from git by
`scripts/qt_head.py` (HEAD source, real directory patched in): `before.png`, `before.json` (16 controls), `before_populated_*.png`, `qt_values.json` (what the Qt window showed in each scenario).
Files edited that I did not write: `chisurf/plugins/calculator/test/test_native_factories.py` (untracked, the stream's, not committed by me): one tolerance, see section 6. `test/prd_mention_allowlist.txt`, `test/plugin_help_guide_allowlist.txt`: one struck line each (the second one by blob, another agent has an unstaged edit in that file).

## 2. What the Qt tool offered - control checklist

| # | Qt control | Where | emtk equivalent | Present |
|---|---|---|---|---|
| 1 | Tabs HeteroFRET / HomoFRET | tab bar | tab bar (tooltips, selected tab persisted) | yes |
| 2 | Lifetime D0 (ns, 0.001-9999, 4 dec) | Hetero | spec `tau0`, call `compute_forward` | yes |
| 3 | Foerster R0 (A, 0.1-999, 2 dec) | Hetero | spec `R0`, call `compute_forward` | yes |
| 4 | Distance DA (A, 0.1-9999) | Hetero | spec `R`, call `compute_forward` | yes |
| 5 | Lifetime DA (ns, 0-9999, 4 dec) | Hetero | spec `tau`, call `from_lifetime` (inverse) | yes |
| 6 | Efficiency (0-1, 6 dec) | Hetero | spec `E`, call `from_efficiency` | yes |
| 7 | kFRET (1/ns, 0-9999, 6 dec) | Hetero | spec `kFRET`, call `from_rate` | yes |
| 8 | Sigma (A, 0.1-999) | both | spec `sigma`, label sigma | yes |
| 9 | chi distribution checkbox | both | spec toggle `use_chi` (Hetero recomputes, Homo only changes the plot, as Qt) | yes |
| 10 | tau0, R0, t_RM, rho | Homo | spec fields, call `compute_forward` | yes |
| 11 | k_homo (read-only) | Homo | read-only spec field | yes |
| 12 | R_DA (0-9999) | Homo | spec `R_DA`, call `backmap` | yes |
| 13 | Distance distribution plot (Gaussian vs chi, active solid) | both | implot window, series from the model | yes |
| 14 | Rate-constant plot (Hetero) / anisotropy-time plot (Homo) | | implot window | yes |
| 15 | Panel folds "Parameters", "Distributions" | | "Parameters" fold; the second panel became the two plot windows | yes (deliberate) |
| 16 | Drop notice (status bar) | window | status line | yes |
| 17 | tooltips on every field and plot | | spec `description`, plot description | yes |
| - | Guide, Help (added by the migration stream) | | buttons in the parameter window | yes |

Screenshots: `before.png`, `before_populated_{hetero_forward_chi,hetero_inverse,homo_forward,homo_chi_backmap}.png`, `before_emtk_*_{1200x800,800x600}.png`.

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/model.py` | changed | Qt-free `HeteroFretModel`, `HomoFretModel`, `FretCalculatorModel`: the Qt tab handlers as methods, Qt rounding/clamping, status line, series cache, export/restore |
| `gui/fret.view.json`, `gui/homofret.view.json` | changed | spin fields with `call`s, Qt limits and decimals, labels as Qt shows them, panel descriptions; plot sections (with titles) drive the plot windows |
| `gui/app.py` | rewritten | `FretCalcApp`: tab bar, per-tab dock layout, `draw_form` form, plots, Guide/Help, drop hooks, persistence; `make_app(**kwargs)` |
| `gui/tool.py` | changed | the Qt host now builds `FretCalcApp(model)`; PRD references removed |
| `gui/guide.json`, `gui/help.md` | changed | 9 steps (8 wait for the user, both tabs); help without the Qt-era slider text and without Markdown marks |
| `tests/test_emtk_fret_calculator_parity.py` | new | 39 tests (numbers against the Qt tool and the backend, every edit typed into the real field) |
| `tests/test_emtk_fret_calculator_clicks.py` | new | 31 tests (4 of them strict xfails documenting emtk gaps): every control operated with simulated pointer and keys |
| `tests/test_emtk_app.py` | deleted | monkeypatched the old slider; its cases (coupled recompute, toggle, back-map, series, tabs) are in the new file |
| `manifest.json` | unchanged by me | `entrypoints.emtk` already added by the stream |

Qt files untouched: none exist any more; `gui/client.py` (the Qt tool's RPC client) is unchanged and used by the Qt host.

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after fret_calculator --out okf/plugins/emtk-ports/fret_calculator
after: 59 controls, 0 without tooltip, qt-free=yes
$ python -m test.gui.emtk_port_parity compare fret_calculator --out okf/plugins/emtk-ports/fret_calculator; echo exit=$?
{ "lost": [], "untooltipped": [] }  qt-free: True   exit=0      (explained 7, stale_explanations [])
```

## 5. Deliberate differences (`deliberate.json`)

| Lost entry | Why |
|---|---|
| `distributions` | the Qt panel header over the two plots: the plots are their own dock windows with titles and tooltips |
| `khomo`, `r0`, `rda`, `trm`, `rho`, `tau0` | HomoFRET tab controls: the parity inventory draws only the first tab (the Qt inventory lists both); drawn and tested on tab 2 |

Behaviour differences: status line for failed calculations (Qt: silent); k_homo always refreshed (Qt: stale after tau0/R0/rho edits); Guide and Help buttons (the stream's additions); plot legends top right.

## 6. Tests

```
$ python -m pytest chisurf/plugins/calculator/fret_calculator -q -p no:cacheprovider
85 passed, 4 xfailed in 36.38s     (19 existing + 39 parity + 27 click tests that pass; 4 strict xfails, section 10)
$ python -m pytest chisurf/plugins/calculator/test -q -p no:cacheprovider -k "fret_calc or native_factories"
24 passed
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
13 passed
```

| Required test | Test | Asserts |
|---|---|---|
| 1 reference result | `test_hetero_defaults_and_every_edit_equal_the_qt_tool`, `test_homo_every_edit_equals_the_qt_tool`, `test_the_numbers_the_qt_tool_showed_are_pinned`, `test_native_values_equal_the_backend_services_...`, `test_plot_series_equal_the_qt_plots` | 15 + 10 edits typed into the real emtk fields equal the committed Qt tool (built offscreen from `pre-upgrade/HEAD_tool.py`) to 1e-9; the values of `qt_values.json` pinned; sigma = 0 equals 1/(1+(R/R0)^6) and tau = tau0(1-E); inverse routes round-trip; plot series equal the Qt model's arrays |
| 2 actions and errors | `test_a_failed_inverse_...` (E 0 and 1, tau 0, kFRET 0), tau > tau0, homo R_DA = 0, a failing backend on every route, typed garbage / out-of-range / unit suffix, arrow steppers, chi toggle on both tabs, read-only k_homo, tab bar clicks, drop hooks | each handler and error path through the UI (click, type, Enter) |
| 3 spec keys | `test_every_spec_key_exists_on_the_model[2 specs]`, `test_every_field_has_the_qt_limits_and_decimals` | attr/call/source exist; limits and decimals equal the model's rounding |
| 4 draws | `test_draws_the_form_and_both_plots_at_both_sizes[2 tabs x 2 sizes]`, `test_draws_after_every_edit_even_at_the_ends_of_the_ranges`, `test_no_emoji_...` | 1200x800, 800x600, labels and legends drawn, series finite at range ends |
| 5 workflow | the edit sequences above, `test_the_qt_host_runs_the_same_app_on_the_same_models` | |
| 6 Qt-free | `test_port_is_qt_free` | |
| 7 tooltips | `test_every_control_has_a_tooltip` | inventory on both tabs + spec walk incl. plots and panels |
| 8 persistence | `test_settings_round_trip_and_invalid_values_are_ignored` | export/restore both tabs and the selected tab; NaN, strings, out-of-range, wrong types ignored |
| also | guide targets drawn on the right tab, the tour waits for each control and the tab, Guide/Help buttons, help text plain with live links, manifest and hub kwargs | |

Deliberate-breakage checks (restored, 58 passed again):

| What I broke | Result |
|---|---|
| `KAPPA2 = 0.5` in `model.py` | 5 failed: `test_hetero_defaults_and_every_edit_equal_the_qt_tool`, `test_the_numbers_the_qt_tool_showed_are_pinned`, `test_native_values_equal_the_backend_services_...`, `test_plot_series_equal_the_qt_plots`, `test_the_qt_host_runs_the_same_app_...` |
| spec `E` field `call` changed from `from_efficiency` to `compute_forward` | 5 failed: the same Qt-parity test, the pinned numbers, both E = 0 / 1 error tests, `test_typed_garbage_is_ignored_...` |

Existing-test change with explanation: `chisurf/plugins/calculator/test/test_native_factories.py::test_fret_inverse_and_homo_backmap` asserted that forward then back-map returns t_RM exactly; R_DA is carried as the 2-decimal field shows it (as the Qt spin box did: 51.35, not 51.3521), so the back-mapped time is the Qt tool's 0.9998. Tolerance `rel=1e-3` with a comment. The file is the stream's untracked one; not committed.

Pre-existing failures I did not cause: `test/test_plugin_help_guide_seam.py` has 18 failures for other plugins (stale allow-list entries, tours of burst/img tools); none mentions `fret_calculator` (`-k fret_calculator`: 3 passed).

## 6a. Click coverage (every control -> the test that operates it with simulated pointer / keyboard events)

The tests in `tests/test_emtk_fret_calculator_clicks.py` and the typing helpers of the parity file move the pointer, press and release it at the rectangle a control was drawn in (or at the text a button
drew), type with `key`, and read the visible outcome. Nothing calls a model method to "click".

| Control (Qt checklist item) | Test |
|---|---|
| tab bar: HeteroFRET, HomoFRET | `test_clicking_the_tab_labels_switches_the_window_and_the_selected_tab_is_kept`, `test_a_file_dropped_on_the_host...`, parity `test_the_tab_bar_switches_tabs` |
| Hetero fields tau0, R0, R, tau, E, kFRET, sigma: type + Enter | parity `test_defaults_and_every_edit_equal_the_qt_tool` (15 edits, equal to the Qt tool), `test_typed_garbage_is_ignored_clamped_...` |
| the same fields, up and down arrows | `test_each_hetero_arrow_steps_its_field_up_and_down_and_runs_its_handler[tau0, R0, R, tau, E, kFRET, sigma]` |
| Homo fields tau0, R0, t_RM, rho, R_DA, sigma: type + Enter, arrows | parity `test_homo_every_edit_equals_the_qt_tool`, `test_each_homo_arrow_steps_its_field_up_and_down_and_runs_its_handler[6]` |
| k_homo (read-only) | `test_a_clicked_field_takes_the_keyboard_and_a_read_only_one_ignores_typing`, parity `test_k_homo_is_an_output_it_cannot_be_typed_into` |
| click-away commit, same value again | `test_clicking_away_commits_a_typed_value_and_enter_on_an_unchanged_one_does_nothing` |
| chi distribution (both tabs) | `test_the_chi_toggle_is_a_checkbox_clicked_on_either_tab`, parity `test_the_chi_toggle_recomputes_and_swaps_the_solid_curve` |
| Parameters fold header | `test_the_parameters_fold_header_hides_and_shows_the_fields` |
| distance / rate / anisotropy plots: drag pan | `test_a_drag_pans_a_plot`; wheel zoom: `test_the_wheel_zooms_a_plot` (xfail, emtk gap 2) |
| wheel over a field | `test_the_wheel_over_a_field_steps_it` (xfail, emtk gap 2) |
| Guide button, Close Tour, awaited controls, tour walked to the end | `test_the_guide_button_starts_the_tour_and_close_tour_ends_it`, `test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control`; Next / Prev: `test_the_tour_next_and_prev_buttons_can_be_clicked` |
| Help button, Start Guided Tour, Close, Close Help, Escape | `test_the_help_button_opens_a_window_with_working_buttons`; section buttons: `test_a_help_section_button_shows_only_that_section` (xfail, emtk gap 1) |
| file drop on the host | `test_a_file_dropped_on_the_host_reaches_the_app_and_says_the_calculator_has_no_file_input` |
| small window | `test_the_flow_works_in_the_small_window_too` |

Populated click sequence, read at full size: `click_0_before_any_click`, `click_1_typed_58_in_Distance_DA_not_committed` (the field shows the typed text, nothing recomputed), `click_2_after_Enter_efficiency_lifetime_rate_follow`,
`click_3_after_click_on_chi_distribution` (checkbox ticked, the chi curve solid, E 0.346), `click_4_after_click_on_the_HomoFRET_tab`, `click_5_after_two_clicks_on_the_R_DA_up_arrow` (R_DA 53.35, t_RM 1.2374),
`click_6_after_click_on_Help`, `click_7_after_click_on_Guide` (script `scripts/capture_clicks.py`; model afterwards: R 58, chi on, t_RM 1.2374). Harness trap found while writing it: rectangles recorded under the pixel painter
(screenshots) are stale for the recording painter's font metrics, so the script re-draws before every click.

## 7. Screenshots I looked at (full size)

| File | Observation | Fix |
|---|---|---|
| `after_populated_hetero_{default,forward_chi,inverse,error}_{1200x800,800x600}.png` | form left, both plots right, values equal `qt_values.json`; error: line under Guide/Help, fields unchanged; chi curve solid, Gaussian dashed | legend moved top right (it covered the curve), window titles "FRET parameters" |
| `after_populated_homo_{forward,chi_backmap}_*` | read-only k_homo without arrows, Greek labels drawn, anisotropy-time plot | none |
| `after_populated_help_1200x800.png`, `guide_step1`, `guide_homo_tab` | help window with sections; tour card, HomoFRET tab spotlighted | none |
| `after_populated_dropped_file_1200x800.png` | notice on the status line | none |
| `after_populated_narrow_500x500.png` | usable, but "chi distribution" and the arrows clip at 210 px width | below the required sizes; recorded under open |

None of these shows a clipped label at 1200x800 or 800x600, overlapping windows, an empty panel or a plot without axes. Qt side: `before.png` and `before_populated_*` (spin boxes with units, two plots).

## 8. Workflow

Hetero: type the donor lifetime, R0, distance, sigma; efficiency, lifetime and rate update; edit E (or lifetime or rate) to solve the effective distance; tick chi. Homo: edit t_RM (R_DA and k_homo follow) or R_DA (t_RM and k_homo follow). Data: none, the plugin computes from typed parameters; test values taken from the Qt tool run (`qt_values.json`).

## 9. Persistence, guide, help, docs

`export_settings`: tau0, R0, R, sigma, use_chi (Hetero); tau0, R0, t_RM, rho, sigma, use_chi (Homo); selected tab. The Qt tool remembered window geometry only (manifest state schema keys `last_*` are unused by the tool). Guide: 9 steps, 8 `await`, each verified by `test_the_tour_waits_...` through real edits and a tab click; steps select their tab. Help: 1 live doc link (`docs/concepts/fret.md`), checked by `test_help_text_is_plain_and_its_links_are_live`. Docs: no guide page exists for this plugin (`docs/reference/plugins/fret_calculator.md` is generated and unchanged); Docs gaps: a numbered `docs/guides/NN` page with a screenshot.

## 10. Blocked / open

* **emtk gap 1 (ids), half fixed while this pass ran.** `emtk.im_core.get_id` keeps only the text after `##`, so buttons spelled `...##same` share one id and only the first drawn one fires. The guided tour's `Close Tour##tour`, `◄ Prev##tour`
  and `Next ►##tour` had this defect (Prev and Next could not be clicked); it was fixed at 21:58 in the shared `chisurf/emtk/help_guide.py` (`##tour_close`, `##tour_prev`, `##tour_next`) by another agent, and
  `test_the_tour_next_and_prev_buttons_can_be_clicked` is now a normal passing test (it was a strict xfail until then). Still open in the same file: the help window's section buttons are all `f" {c} ##filter"` (line 204), so a click on any
  but the first never fires. Reproduction:
  ```
  w = EmTkHelpWindow(text="# A\nx\n# B\ny"); w.show()            # in an ImApp frame: w.draw((0, 0, 800, 600))
  # draw 2 frames, click the drawn " B " button (move, press, draw, release, draw)
  print(w.active_category)   # "All" (expected "B"); the same click on the first section button works
  ```
  Test: `test_a_help_section_button_shows_only_that_section` (strict xfail: it flips when the id is fixed).
* **emtk gap 2 (wheel in docked windows).** A `DockManager` window consumes the wheel: a spin field (`style: spin`) and an implot inside it never see it, so no docked plot zooms and no field steps with the wheel (both work in a plain `im.begin` window). Reproduction:
  ```
  dm = DockManager(Split("h", .5, Region("a"), Region("b"))); dm.add_window("a", "A", plot_fn, dock="a"); dm.add_window("b", "B", lambda box: im.text("b"), dock="b")
  app = ImApp(lambda: dm.draw((0, 0, 800, 600)))      # plot_fn: implot.begin_plot + plot_line + end_plot
  # draw 2 frames, pointer_move into window A, app.wheel(x, y, 3.0), draw 2 frames
  # tick labels unchanged; the same plot in `if im.begin("w", (0, 0, 400, 300)):` zooms
  ```
  Tests: `test_the_wheel_zooms_a_plot`, `test_the_wheel_over_a_field_steps_it` (strict xfail).
* **emtk gap 3 (focus).** A text field keeps the keyboard after a click on a checkbox or a button, so the next typed character lands in it. Reproduction: draw `draw_form` with a `value` and a `toggle`; click into the field, click the toggle, `app.key(ord("9"), "9")`: `form.buffers` is `{"R0": "9"}` and `io.want_capture_keyboard` stays True (screenshot `click_3_...`: the Distance DA text is still selected after the toggle click). Test: `test_clicking_a_checkbox_takes_the_keyboard_away_from_a_text_field` (strict xfail).
* emtk gap (shared `chisurf/emtk/help_guide.py`, not emtk): `EmTkHelpWindow` draws Markdown links raw (`[title](docs/concepts/fret.md)` appears literally, `after_populated_help_1200x800.png`). Repro: `EmTkHelpWindow(text="[a](docs/x.md)").show()` then draw.
* emtk layout: a spec toggle label and `spin` arrows clip when the dock is narrower than about 230 px (`after_populated_narrow_500x500.png`).
* Systemic (also on the board): `build_plugin_widget`'s ControlHost never calls an app's `close()`; this app has nothing to close.
* `emtk_preview.json` untouched (reviewer removes `fret_calculator` after accepting).

## 11. Self-check against the Definition of Done

- [x] D1 Qt-free `make_app()` (qt-free: True)
- [x] D2 every Qt control present or explained (sections 2, 5)
- [x] D3 no untooltipped control
- [x] D4 screenshots read, nothing clipped at the required sizes
- [x] D5 workflow tested against the Qt tool
- [x] D6 persistence
- [x] D7 guide + help
- [x] D8 docs: gap recorded
- [x] D9 plugin tests green (58 passed)
- [x] D10 report complete, evidence committed
