# emtk port report - `calculators` (the hub, `chisurf/plugins/calculator/hub`; swap-candidate verification and upgrade, audit-all row 27)

Agent: claude (Sonnet), 2026-10-01, per `UPGRADE_BRIEF.md`. Board entry `T-20261001-SWAP4B`. Verdict: **accept** after the upgrade. The stream's hub app opened, listed and embedded the nine calculators, but it differed from the Qt hub in the
ways of section 0 (rule 6, a dead drop path, no key handling, a render loop, nothing remembered), all fixed inside the plugin's own app. The Qt hub (`gui/tool.py`) is untouched.

Commits: `812a9eb68` Qt baseline and current emtk state (with `pre-upgrade/`), `d34343fcd` emtk app at parity with the Qt hub (code, tests, allow-list strike), then the evidence commit. All three were made through a private index
(`git commit` with `GIT_INDEX_FILE`), because the shared index held another agent's staged evidence (vv_vh_anisotropy, rics_precision, tttr_*): nothing of theirs was committed, nothing of mine was left staged.

## 0. What the pre-upgrade app got wrong (checked against the Qt hub, not by the heuristic audit)

1. **Emoji in the list labels** (`entry.icon + " " + entry.label`, rule 6): the native list drew pictograms (`before_*` / `pre-upgrade/app.py`).
2. **A dead drop path.** The app had no `files_dropped` / `on_files_dropped` / `on_paths_dropped`, so the Qt host refused every drop (`dragEnterEvent` ignored), while the Qt hub's embedded calculators answered their own drops (the FRET calculator says "takes no dropped files").
   Reproduction at `812a9eb68` (`pre-upgrade/app.py`): `ControlHost(make_app())` then `dragEnterEvent` with a file URL: `isAccepted()` is False. Now the hub hands the drop to the embedded calculator and returns its answer.
3. **No key handling for the hub itself and none for the list.** `key()` went to the embedded calculator only (Escape never reached a hub-level window), the Qt list answered Up and Down (`test_up_and_down_move_the_selection_unless_a_field_is_being_edited`).
4. **A render loop** (`continuous=True`) instead of frames on demand; the embedded calculators' worker threads could not wake an idle host, so the hub had to render continuously. Now `animating` / `next_frame_in` aggregate the child's and each child's frame request is wired to the hub's.
5. Nothing remembered (no `export_settings`), no Help, no Guide, a fixed 70 px header that clipped a long description in a narrow window, an error message without the Qt page's wording.

Not a regression, found on the way: the Qt hub cannot show the PSF calculator at all (`Could not load 'PSF calculator': the 'emtk' backend has no 3-D volume renderer`, `before_populated_psf_calculator.png`); the native hub embeds the native PSF calculator.

## 1. State at start

```
 M chisurf/plugins/calculator/hub/manifest.json
?? chisurf/plugins/calculator/hub/gui/app.py
```

(earlier migration stream; nothing modified in the last 60 minutes by anyone else). `pre-upgrade/` holds `app.py` and the tracked diff; both were committed with the baseline. Qt baseline: `before.png`, `before.json` (20 controls),
`before_populated_{fret_calculator,kappa2_dist,phasor,f_test,psf_calculator,broken_entry,no_entries}.png`, `qt_hub_report.json` (title, subtitle and page widget of every entry). Files edited that I did not write: `test/plugin_help_guide_allowlist.txt`
(one line struck, by blob, another agent has unstaged edits in that file).

## 2. What the Qt hub offered - control checklist

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | list of nine calculators (icon + label), first selected at start | `selectable` list, plain labels, first selected | yes (icons deliberate) |
| 2 | per-entry tooltip (the description) | `set_item_tooltip` per entry | yes |
| 3 | title and description of the selected calculator | header window (label, wrapped description, grows with the text) | yes |
| 4 | the calculator, built on first selection and kept | `select()` builds lazily, `children` keeps the app and its state | yes |
| 5 | a calculator that cannot be built: "Could not load '<label>':\n<error>" in the page | the same words in the header, nothing drawn below; another entry recovers | yes |
| 6 | placeholder page "No calculator selected." / "Select a calculator on the left to get started." (empty catalogue) | the prompt in the header | yes |
| 7 | the embedded calculator's own controls, keys, wheel, drops | pointer, wheel, keys and drops forwarded with the box offset | yes |
| 8 | Up / Down in the list | the same, while no field of the calculator holds the keyboard | yes |
| 9 | splitter between list and calculator | fixed split (25 %, at most 240 px) | deliberate |
| 10 | window geometry persistence | the host's (unchanged); plus the selection and the calculators' inputs | yes |
| - | Guide, Help (new) | buttons under the list, 4-step tour, help window | yes |

## 3. Files

| File | Change |
|---|---|
| `gui/app.py` | the upgrade above; `make_app(entries=)` as before |
| `gui/guide.json`, `gui/help.md` | new: 4 steps (1 awaits a list click); help with a live link |
| `test/test_emtk_hub_parity.py` | new, 33 tests |
| `core/registry.py`, `gui/tool.py`, `manifest.json` | untouched (the stream's `entrypoints.emtk` was already there) |

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after calculators --out okf/plugins/emtk-ports/calculators
after: 69 controls, 0 without tooltip, qt-free=yes
$ python -m test.gui.emtk_port_parity compare calculators --out okf/plugins/emtk-ports/calculators; echo exit=$?
exit=0      (lost [], untooltipped [], explained 8, stale_explanations [])
```

## 5. Deliberate differences (`deliberate.json`)

`3` ... `9`: axis tick labels of the embedded FRET calculator (the Qt inventory lists the strings of the embedded emtk host as well; not controls). `nocalculatorselected.`: the Qt placeholder page, reachable only with an empty catalogue;
the native hub shows the prompt then. Also: list icons are not drawn (rule 6), the splitter is fixed, a drop on a calculator without a drop hook is accepted by the host and answered with nothing (the Qt widget refused it).

## 6. Tests

```
$ python -m pytest chisurf/plugins/calculator/hub -q -p no:cacheprovider
36 passed in 34.87s          (3 registry tests + 33 parity and click tests)
$ python -m pytest chisurf/plugins/calculator/test -q -k "hub or native_factories"   -> 24 passed
$ python -m pytest test/gui/test_emtk_port_parity.py -q                              -> 13 passed
```

| Required test | Test | Asserts |
|---|---|---|
| 1 reference | `test_the_list_header_and_selection_equal_the_qt_hub_entry_by_entry` | all nine ids, labels, tooltips, titles, descriptions equal the committed Qt hub, the first entry selected in both |
| 2 actions, errors | `test_a_calculator_that_cannot_be_built_says_why_like_the_qt_hub`, `test_no_entries_shows_the_prompt_and_no_child`, `test_a_long_description_or_error_is_never_clipped...[3 sizes]` | the Qt page's wording, recovery by another entry, header grows |
| 3 spec / catalogue | `test_every_registry_entry_has_a_native_factory_and_the_factories_import` | no calculator without a native app |
| 4 draws | `test_children_are_built_lazily_kept_and_every_one_builds_and_draws_at_both_sizes`, `test_no_emoji_...` | nine children at 1200x800 and 800x600 |
| 6, 7 | `test_every_control_has_a_tooltip_and_the_port_is_qt_free` | |
| 8 persistence | `test_settings_round_trip_restores_the_selection_and_the_calculators_inputs`, `test_close_closes_every_built_calculator` | selection, opened calculators' inputs applied when built later; bad input ignored |

Deliberate-breakage checks (restored; 36 passed again after the final changes):

| What I broke | Result |
|---|---|
| the hub no longer forwards the pointer press to the embedded calculator | 4 failed: `..._gets_the_pointer_and_the_keys_and_keeps_its_state...`, `test_a_click_in_the_list_area...`, `test_up_and_down_move_the_selection...`, `test_settings_round_trip...` |
| `files_dropped` answers False after handing the file over | `test_a_file_dropped_on_the_host_goes_to_the_embedded_calculator` failed |

Pre-existing failures I did not cause: `test/test_plugin_help_guide_seam.py` fails 17 tests for other plugins; none mentions the hub.

## 6a. Click coverage (every control -> the test that operates it with simulated pointer / keyboard events)

| Control | Test |
|---|---|
| each of the nine list entries (click) | `test_clicking_each_list_entry_selects_it_and_shows_its_calculator[9 ids]`, `test_children_are_built_lazily_...` (both sizes) |
| the embedded calculator: click, typing, Enter through the hub's pointer offset | `test_the_embedded_calculator_gets_the_pointer_and_the_keys_and_keeps_its_state_when_another_is_shown` |
| a click in the list does not reach the calculator, one in its box does | `test_a_click_in_the_list_area_does_not_reach_the_calculator_and_one_outside_the_header_does` |
| Up / Down keys, clamped at both ends, not while a field is edited | `test_up_and_down_move_the_selection_unless_a_field_is_being_edited` |
| wheel and hover forwarded only inside the calculator's box | `test_the_wheel_and_the_hover_are_forwarded_to_the_calculator_inside_its_box_only` |
| frame request from the embedded calculator | `test_the_hub_is_asked_for_frames_by_the_embedded_calculator` |
| Guide, awaited list click, Close Tour, tour walked to the end | `test_guide_button_starts_the_tour_whose_awaited_step_waits_for_a_list_click`, `test_the_tour_targets_are_drawn_and_the_tour_is_walked_to_the_end_by_the_user`; Next: `test_the_tour_next_button_can_be_clicked` |
| Help, Start Guided Tour, Close, Close Help, Escape | `test_help_button_opens_the_help_window_whose_buttons_work` |
| file drop through the host (accepted and answered by the FRET calculator, refused by kappa2) | `test_a_file_dropped_on_the_host_goes_to_the_embedded_calculator` |

Populated click sequence, read at full size (`scripts/capture_clicks.py`): `click_0_before_any_click_FRET_calculator_selected`, `click_1_after_click_on_the_kappa2_entry`, `click_2_after_the_Down_key_f_test_selected`,
`click_3_typed_0.2_into_r_D_inf_of_the_embedded_calculator` (the embedded field shows the typed value, the statistics follow), `click_4_after_click_on_the_FRET_entry_again`, `click_5_typed_58_into_Distance_DA`,
`click_6_back_on_kappa2_its_r_D_inf_is_still_0.2` (state kept), `click_7_after_click_on_Guide`, `click_8_after_click_on_Help`. Final `export_settings`: selected kappa2_dist, FRET R 58, kappa2 r_D∞ 0.2.

## 7. Screenshots I looked at (full size)

`after_populated_{fret_calculator,kappa2_dist,phasor,f_test,psf_calculator}_{1200x800,800x600}.png` (the same states as `before_populated_*`; PSF shows the native calculator where Qt shows the error page),
`after_populated_rics_precision_long_description_1200x800.png` (the longest description), `after_populated_broken_entry_1200x800.png` (the Qt wording under the description, the list still usable),
`after_populated_no_entries_1200x800.png`, `after_populated_help_1200x800.png`, `after_populated_guide_pick_one_1200x800.png`, the nine `click_*` captures. The 70 px header was the only layout defect found (a three-line description plus
label ends at 67 px at 800 px width and overflows below that): it now grows with the text (`test_a_long_description_or_error_is_never_clipped...`). Nothing else clipped or overlapping at the required sizes.

## 8. Workflow

Pick a calculator in the list, use it, pick another and come back: its inputs are still there. Up and Down step through the list; Guide and Help explain the hub. No data file is involved (a dropped file goes to the calculator that takes it).

## 9. Persistence, guide, help, docs

`export_settings`: the selected calculator and the settings of every calculator built so far (their own `export_settings`; restored when built later). The Qt hub remembered the window geometry only. Guide: 4 steps, 1 `await`, all targets drawn (test).
Help: 1 live link. Docs: no guide page for the hub (gap); the `README.md` of the plugin lists three of the nine calculators (stale, not changed: Qt-era text about the registry).

## 10. Blocked / open

* emtk gap 1 (buttons spelled `...##same` share one id: the tour's Next / Prev were fixed at 21:58 in the shared `chisurf/emtk/help_guide.py`, the help window's section buttons `##filter` still have it), emtk gap 2 (the wheel does not reach docked widgets) and emtk gap 3 (a text field keeps the keyboard after a click elsewhere), with reproductions, in
  `okf/plugins/emtk-ports/fret_calculator/REPORT.md` section 10. Gap 3 matters here: after a field of the embedded calculator was edited, Up and Down keep going to that field until the user clicks into another text field
  (the hub only moves the selection when the calculator does not take the key).
* A drop on a calculator with no drop hook is accepted by `ControlHost` (it ignores the answer of a `files_dropped` hook) and then does nothing; the Qt widget refused it.
* `emtk_preview.json` untouched (reviewer removes `calculators` after accepting).

## 11. Self-check against the Definition of Done

- [x] D1 [x] D2 [x] D3 [x] D4 [x] D5 [x] D6 [x] D7 [x] D8 (gap recorded) [x] D9 (36 passed) [x] D10
