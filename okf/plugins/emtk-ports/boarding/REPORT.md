# emtk port report: `boarding` (upgrade to parity with the Qt wizard)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `boarding` / `chisurf/plugins/core/boarding/` (flat layout: no `gui/` folder; `app.py`, `model.py`, `view_model.py`, `utils.py`, `wizard.py` beside `manifest.json`) |
| Port type and why | Upgrade of an existing emtk app (brief `UPGRADE_BRIEF.md`). The Qt wizard has eight steps with Back / Next; the emtk app had four pages and neither the detector nor the FCS editor. |
| Agent / date | claude implementing agent, 2026-10-01 |
| Effort spent (hours) | not measured |
| Commits | `784470352` boarding: Qt baseline and current emtk state for the upgrade; `700906158` boarding: emtk app at parity with the Qt wizard; `fdd4dfd0d` boarding: layout at narrow widths (steps list minimum width, wrapped subtitle, table column widths); `7c701f11b` boarding: evidence and report |
| Agent-board entry | `T-20261001-BOARD` in `okf/agent-board.md` |

## 1. State at start (P1)

```
 M chisurf/plugins/core/boarding/manifest.json
 M chisurf/plugins/core/boarding/utils.py
?? chisurf/plugins/core/boarding/app.py
?? chisurf/plugins/core/boarding/strings.py
?? chisurf/plugins/core/boarding/test/test_native.py
```

These are the earlier emtk-migration stream's files, kept in `okf/plugins/emtk-ports/boarding/pre-upgrade/` (copies of the three untracked
files, the diff of the two modified ones) and committed in the baseline commit. Files I edited that I did not write: `utils.py` (the earlier
stream's uncommitted Qt-free edit is the base of mine), `manifest.json` (its `entrypoints.emtk` line is the earlier stream's and is
committed with the app), and one line of the shared `test/plugin_help_guide_allowlist.txt` (struck `chisurf/plugins/core/boarding`, as the
procedure's P8 asks). Not touched: emtk, `chisurf/emtk/*`, `emtk_preview.json`, the two shared editors, any other plugin.

## 2. What the Qt tool offered: control checklist

The Qt wizard is an AutoForm `wizard` section (`boarding.view.json`): a navigation list, a header with a subtitle, a stacked page per
step, a Back / Next / Finish bar. Screenshots: `before.png`, `before_populated_step1_welcome.png` .. `before_populated_step8_finish.png`,
`before_populated_fix_restored.png`, `before_populated_experiments_updated.png`, `before_populated_finish_last.png`, and the earlier emtk app
`before_emtk_*.png`.

| # | Qt control (as shown) | Where | emtk equivalent | Present? |
|---|---|---|---|---|
| 1 | Navigation list, 8 steps, check mark per completed step, steps clickable | left | `draw_steps`: one selectable per step, `✓` prefix from `BoardingModel.step_complete` | yes |
| 2 | Step header: title and subtitle | top of page | `draw_page` (title, wrapped dimmed subtitle), the Qt texts | yes |
| 3 | Back (disabled on the first step) | bar | spec button `go_back`, `enabled()` greys it on step 1 | yes |
| 4 | Next (hidden on the last step; never gated, `linear: false`) | bar | spec button `go_next`, `hidden_when is_last` | yes |
| 5 | Finish (only on the last step, closes the window) | bar | spec button `finish`, `hidden_when` not last; sets `finished`, app calls `request_close` | yes |
| 6 | Welcome: text, Open settings folder | step 1 | markdown + button `open_settings_dir` | yes |
| 7 | Settings: status table (settings dir, `settings_chisurf.yaml`, colours, anisotropy, `styles/`, `plugins/`, `logs/`, MMFDB, detector and FCS setups, runtime settings), Refresh, Open settings editor | step 2 | `data_table` `status_rows` (Item / Status / Location, tooltip = full path), buttons `refresh`, `open_settings_editor` | yes (editor: host, see section 5) |
| 8 | Fix / Initialize: text, Create missing files, Restore defaults (overwrite), outcome line | step 3 | markdown, buttons `create_missing`, `request_restore`, coloured outcome line | yes (confirmation added) |
| 9 | Experiments: text, Update experiments, outcome line | step 4 | markdown, button `update_experiments`, outcome line | yes |
| 10 | Dependencies: table (tttrlib, pyqtgraph, markdown, pymol: OK/MISSING, purpose, import error), Refresh | step 5 | `data_table` `deps_rows` (Package / Status / Used for / Import error), button `refresh` | yes |
| 11 | Detector setup: Setup choice, Save, Rename, Delete, Public, Calibration, `?`, TTTR reading, PIE windows, detectors table (name, channels, ranges, G, l1, l2, G-factor channels, G calc, delete), Polarization resolved, LUT handling (Assign LUT, Configure LUTs, Adjust shifts), Edit JSON, Save, Optical Setup | step 6 | the shared editor of Setup: Channel Definition, hosted unedited: its toolbar (Setup, Save, Rename, Delete, Public, Calibration, Help, Guide, in-app prompts) and its six tabs | yes (renames and two dialogs, section 5) |
| 12 | FCS channels: Detector setup, Public, Reload, Channel pairs (A, B, label, Add, table Name / Channel A / Channel B / Bins / Cascades / Fine), Save, Close | step 7 | the shared FCS editor (`PresetApp.draw_setup`, `draw_pairs`) hosted unedited, plus its file chooser, Help and Guide | yes |
| 13 | Finish: text, Open Help, Open Plugin Manager | step 8 | markdown, buttons `open_help`, `open_plugin_manager` | yes (host, see section 5) |
| 14 | Remembered step (QSettings `autoform-wizard/boarding/step`) | n/a | `export_settings()["step"]` | yes |
| 15 | Tooltips on every button | all | every spec section, column and button has a description; hosted editors' own | yes |

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `boarding_emtk.view.json` | new | spec: `navigation`, `confirm`, one panel per step; two `data_table`s |
| `model.py` | new | Qt-free `BoardingModel(BoardingViewModel)`: steps, Back / Next / Finish, completion marks, confirmation, host hook |
| `app.py` | changed (was 59 lines) | docked window: step list + page, hosts the two shared editors, dialogs, help, tour |
| `view_model.py` | changed (+4 lines) | plain-text outcome (`repair_message`, `repair_ok`) next to the HTML one |
| `utils.py` | changed | status and dependency rows as data (`status_cells`, `deps_cells`), HTML built from the same rows; file manager opened without Qt; detector setup count from the core store (no `chisurf.gui` import) |
| `guide.json`, `help.md` | new | 7-step tour (5 with `await`), help page |
| `strings.py` | changed | translations for the added labels |
| `test/test_emtk_boarding_parity.py` | new | 39 tests |
| `test/test_native.py` | changed | the earlier four-page smoke test, updated to steps (explained in the file) |
| `manifest.json` | already modified | `entrypoints.emtk` kept (earlier stream) |

Qt files untouched: `wizard.py`, `boarding.view.json`, `view_model.py` apart from the four-line additive change. `test/plugin_help_guide_allowlist.txt`:
one line struck.

## 4. Automated evidence

`compare` (exit code 0):

```
{
  "lost": [],
  "untooltipped": []
}
qt-free: True
exit=0
```

`compare.json`: `before_controls` 86, `after_controls` 244, `lost` `[]`, `stale_explanations` `[]`, `explained` 34 entries.

`after` summary line (stock command; it draws the first step only):

```
after: 22 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/boarding
```

The wizard shows one step at a time, so `after.json` is the stock `after` result merged by `capture_after_steps.py` with the inventory
(`emtk_inventory`, the tool's own function) of 22 states: every step empty, all six editor tabs, populated detector and FCS steps, the
confirmation, narrow. `states_merged` = 22, 244 controls, 139 interactive rows.

`qt_free` (from `after.json`): `"ok": true`, output `QT-FREE OK`. A second, stricter test also visits every step, runs the actions and
asserts no `chisurf.gui` module is loaded.

Controls without tooltip: `[]`.

## 5. Deliberate differences

`deliberate.json` has 34 entries, all explained in the file and none a control I forgot:

| Lost/changed item | Why | Where it went / what replaces it |
|---|---|---|
| `next›`, `‹back` | Renamed: the chevrons are dropped | buttons `Next`, `Back`, same action; Back greyed on step 1 |
| `?` | Qt's red `?` button of the detector and FCS steps | the `Help` button of each hosted editor, plus a wizard Help |
| `channelpairs` | Qt collapsible box title in the FCS step | the pairs table of the hosted editor |
| 30 detector-editor labels (`filetype`, `macrotimeres.(ns)`, `microtimeres.(ps)`, `eff.microtime(ps)`, `read`, `plot`, `tttrreadingroutine`, `piewindows`, `pie-windows`, `g-factor`, `g-factorchannels`, `l1`, `l2`, `channel`, `channels`, `lut`, `shift`, `—none—`, `luthandling(taclinearization)`, `applytaclinearization(lut)whenreading`, `assignlut`, `configureluts`, `adjustshifts`, `editjson`, `0`..`8`) | The shared editor of Setup: Channel Definition, accepted in `okf/plugins/emtk-ports/setup_channel_definition/`, has other label texts and tabs; two Qt dialogs (Configure LUTs, Adjust shifts) are not offered there | see that port's `deliberate.json` and report; each entry here repeats its reason |

Changes of behaviour that are not lost controls:

* **Restore defaults asks first** (Qt overwrote at once): it replaces every settings file, so an in-app question with Restore defaults /
  Keep my settings sits in front of it. Declining changes nothing (tested).
* **Open settings editor, Open Help, Open Plugin Manager** open windows of the Qt main window. An emtk app cannot open another plugin's
  window, so each calls an optional `host(kind) -> bool` of the embedding application and, without one, says where the window is on a
  line under the buttons (`BoardingModel.notice`). Stand-alone they therefore do not open anything. A host can be passed to
  `BoardingApp(host=...)`; the default factory passes none.
* **FCS editor Close** closes an embedded widget in Qt (it leaves a blank step); here it goes on to the last step.
* **Settings step mark.** As in Qt it needs `settings_chisurf.yaml`, which Create missing files never writes (known issue added to
  `okf/references/known-issues.md`).
* Help and Guide buttons of the wizard itself are new (the Qt wizard had none), as are the detector and FCS step marks refreshing while
  the editors are open (every 1.5 s, Qt re-reads on model events).

## 6. Tests

Whole plugin folder:

```
$PY -m pytest chisurf/plugins/core/boarding -q -p no:cacheprovider
62 passed in 20.91s
$PY -m pytest test/plugins/boarding -q -p no:cacheprovider
2 passed in 0.83s
```

Tool self-test: `test/gui/test_emtk_port_parity.py` 13 passed in 31.47s. Help/guide seam for this plugin
(`test/test_plugin_help_guide_seam.py -k "boarding or drawn"`) 4 passed. Hermetic: temp `CHISURF_SETTINGS_DIR`, `MMFDB_*`, Qt settings, the
file manager replaced, no network, no pip or conda (the dependency table only imports).

| Required test | Test name | What it asserts |
|---|---|---|
| 1 model equals Qt | `test_steps_are_the_qt_steps_in_order`, `test_marks_equal_the_qt_nav_marks_*` (2), `test_back_and_next_enabled_states_equal_qt`, `test_status_table_rows_equal_the_qt_html_rows` | titles, subtitles, optional and `complete_when` of the Qt spec; check marks and Back / Next / Finish state compared with the Qt `WizardWidget` offscreen (fresh folder, after Create missing, with a saved setup); table rows equal the Qt HTML rows |
| 2 actions and errors | `test_create_missing_*`, `test_restore_defaults_asks_and_declining_changes_nothing`, `test_failing_copy_is_reported_not_raised`, `test_update_experiments_*`, `test_open_settings_folder_*`, `test_refresh_*`, `test_actions_that_open_another_window_use_the_host` (3 cases), `test_without_a_host_*` | files written or kept, decline = no change, a failing copy is a red message not an exception, host true / false / raising |
| 3 spec keys exist | `test_every_spec_key_exists_on_the_model` | every button action, `hidden_when`, markdown source, table source, custom key |
| 4 draws both sizes | `test_every_step_draws_empty_and_populated[1200x800, 800x600]`, `test_settings_table_shows_the_populated_rows` | each step has its text empty and populated |
| 5 workflow | `test_saved_detector_setup_marks_the_step_and_is_stored`, `test_fcs_editor_saves_a_pair_and_marks_the_step`, `test_restore_question_is_drawn_and_declined_by_keep`, `test_the_awaited_buttons_are_noticed_by_the_tour`, `test_finish_closes_the_window` | pointer clicks on drawn buttons; a detector setup saved in the hosted editor is stored and ticks its step; an FCS pair saved ticks the next |
| 6 Qt-free | `test_port_is_qt_free`, `test_every_step_is_qt_free_including_the_embedded_editors` | no Qt, no `chisurf.gui` over every step and action |
| 7 tooltips | `test_every_control_has_a_tooltip_on_every_step`, `test_guide_targets_are_real_controls` | recorder per step plus spec walk incl. columns |
| 8 persistence | `test_settings_round_trip` | step index, garbage and out-of-range values |

Deliberate-breakage check (run on the model, then restored):

| Test | What I broke | Result when broken |
|---|---|---|
| `test_back_next_finish_follow_the_qt_bar` | `go_next` stepped by 2 | FAILED |
| `test_restore_defaults_asks_and_declining_changes_nothing` | `confirm_no` also restored the defaults | FAILED (`2 failed, 1 passed` for the three selected tests) |

Pre-existing failures I did not cause: `test/test_plugin_help_guide_seam.py::test_allowlist_has_no_stale_entries` and
`test/test_prd_mentions.py::test_prd_mention_allowlist_has_no_stale_entries` fail on other plugins' entries (the PRD one names
`kappa2_dist/gui/tool.py` and `tttr_time_windows/tests/test_construction_smoke.py`); boarding is in neither.

## 7. Screenshots I looked at

All read at full size.

| File | Observation | Fix applied |
|---|---|---|
| `after_empty_step1_welcome_1200x800.png` | step list with marks (Settings, Detector setup, FCS channels unchecked), Back greyed, text and button | none |
| `after_empty_step2_settings_*` | table of 11 rows, MISSING rows, full path in the tooltip row; at 800 the Location column is cut (tooltip has it) | column widths changed (Item 180, Status 82, Location 340) after the first run clipped "User settings d." |
| `after_empty_step3_fix_*`, `step4_*` | text, two buttons, outcome line | none |
| `after_populated_step3_after_actions_*` | green outcome line | none |
| `after_dialog_restore_defaults_*` | in-app question over the page | none |
| `after_empty_step5_dependencies_*`, `after_populated_step5_*` | four rows, Import error column empty | none |
| `after_empty_step6_detector_*`, `after_tab_*` (6 tabs x 2 sizes) | shared editor: toolbar, tabs (a section choice at 800), scroll on the long tabs | none (shared editor) |
| `after_populated_step6_detector_saved_*` | setup `lab` selected, step 6 checked | none |
| `after_populated_step7_fcs_saved_*` | two pairs (CCF, ACF), step 7 checked | none |
| `after_populated_step8_finish_notice_*` | notice line under the buttons | none |
| `after_populated_narrow_520x500.png`, `..._detector_...` | nav label "Fix / Initializ" was clipped, subtitle cut | steps list minimum width 165, subtitle wrapped |

Clipped label, text past its box, overlapping windows, empty panel: none visible in the final set. Tooltips visible in a few images are the
pointer left over from the tab clicks.

## 8. Workflow walk-through

Data: temporary settings only (no measurement file is needed).

1. Open: step 1. Next: step 2, Settings table lists the folder (`step_complete(1)` false while `settings_chisurf.yaml` is missing).
2. Fix / Initialize: Create missing files writes the packaged files that are missing; the table and marks refresh; Restore defaults asks, Keep leaves everything.
3. Experiments: Update experiments re-syncs `experiment_configs.yaml` only; "already up to date" on a second press.
4. Detector setup: Save in the hosted editor stores `lab`; the step gets its mark within 1.5 s (test calls `refresh_completion`).
5. FCS channels: choose `lab`, A and B, Add, Save: the pair is stored, the step is marked.
6. Finish: Finish closes the window (`request_close`).

## 9. Persistence, guide, help, docs

* `export_settings()`: `step`, `docks` (Qt kept `boarding/step` in QSettings).
* Guide: 7 steps, targets `nav_list`, `go_next`, `create_missing`, `update_experiments`, `detector_save`, `fcs_Save`, `finish`; five have `await`
  (step list click, Next, Create missing files, Update experiments, Finish);
  `test_guide_targets_are_real_controls` draws every step and checks that each target is a drawn rect.
* Help: `test/test_plugin_help_guide_seam.py -k "boarding or drawn"` passes; the one link is `docs/reference/plugins/index.md`.
* Docs: no `docs/guides/NN_*.md` or `docs/concepts` page exists for the wizard (docs gap); no catalogue change (name and description unchanged).

## 10. Blocked / open questions

Nothing blocked: both shared editors embed without edits (`SetupChannelDefinitionApp._draw_window()`, `PresetApp.draw_setup()` /
`draw_pairs()` called from the host's window).

Open, for the reviewer:

* Settings status of `settings_chisurf.yaml` (known issue added, not changed: parity with Qt).
* The hosted editors' private methods (`_draw_window`, `_draw_prompt`, `draw_setup`) are what the wizard calls; a public "draw into the
  current window" API on both apps would make this less fragile.
* emtk: `begin_child` was not used; the page is a docked window (own scrolling), which draws long editor tabs correctly.

## 11. Self-check against the Definition of Done

- [x] D1 `entrypoints.emtk` is `chisurf.plugins.core.boarding.app:make_app`, Qt-free (section 4)
- [x] D2 every Qt control present or explained (sections 2, 5)
- [x] D3 no untooltipped control (section 4)
- [x] D4 screenshots read, nothing clipped (section 7)
- [x] D5 workflow tested (sections 6, 8)
- [x] D6 persistence (section 9)
- [x] D7 guide and help (section 9)
- [x] D8 docs: gap listed (section 9)
- [x] D9 plugin tests green (section 6)
- [x] D10 report written, evidence committed, board updated

## Review (reviewer, 2026-10-01)
Re-run by the reviewer: `chisurf/plugins/core/boarding` + `test/plugins/boarding` 64 passed; `compare` exit 0 with `lost` [] and `untooltipped` [], qt-free True; no Qt imports in the plugin's
`app.py` / `model.py`; no file under the real `~/.chisurf` is newer than the report. Screenshots read: the step list with check marks and Back / Next / Help / Guide, the Settings step as a
`data_table` (status OK / MISSING / connected, tooltip with the full path), the Detector step hosting the unedited channel-definition editor (setup choice, Save / Rename / Delete, Public, six tabs).
Known open points carried from the agent: the wizard calls private draw methods of the two shared editors; `settings_chisurf.yaml` is reported MISSING by Qt as well (known issue);
no docs page. **Accepted.** `boarding` is removed from `emtk_preview.json`.
