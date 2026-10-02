# emtk port report — `traj_remove_clashes` (upgrade, audit-all row 40)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_remove_clashes` / `chisurf/plugins/traj/traj_remove_clashes` |
| Port type | A+B: the Qt `RemoveClashedFrames` widget (AutoForm over `remove_clashes.view.json`: custom `traj_remove_clashes_io` with trajectory + topology rows and save button; `atom_selection`, `stride`, `min_distance`; info log) over `RemoveClashesViewModel`; the stream's hand-drawn emtk `app.py` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `e3abdd390` baseline; `ed1aa7d01` emtk app at parity with the Qt tool (+ two shared defects, guide 81 wording); evidence commit "traj_remove_clashes: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `manifest.json`, `view_model.py` (`log_text()`); untracked
`app.py`, `strings.py`. Tracked edits committed with the app; `app.py` rewritten, `strings.py` dropped.

## 2. Defects fixed for both hosts (`ed1aa7d01`)

- **The Qt save dialog asked for `.h5`** ("H5-Trajectory file", `*.h5`) although the view model writes a DCD: a user who
  followed the dialog got DCD bytes in a file named `.h5`. Now "Save clash-free trajectory", `*.dcd`; the tooltips no longer
  say H5. Guarded in the parity test (the Qt dialog's title and filter are recorded in the subprocess).
- **The log never said how many frames were kept**; guide 81 told users to read the output back to count them. The view
  model now logs `Kept N of M frames (min distance d Å)`; guide 81 updated.
- Stale view-model docstrings (a "divided by ten / nm" threshold, an `.h5` target) corrected.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Trajectory / Topology rows with `…` dialogs and drops | free-text fields | read-only rows, dialogs, typed drops |
| 💾 Save clash-free…: precondition box, save dialog, cancel logged, "Save failed" box | button + free-text Output | same precondition, DCD dialog (`<stem>_clash_free.dcd`), cancel logged, "Save failed: …" in the window |
| Atom selection (multi-line), Stride (spin), Min distance (spin, 2 decimals) | text, int, float | the spec's fields via draw_form, descriptions as tooltips |
| log | log lines | scrolling, wrapping log; now with the kept count |
| synchronous | synchronous | worker thread, "Working…" |
| no help, no guide | none | `help.md` (what the test does not know: no bond exclusion, no radii), `guide.json` (8 steps) |

## 4. Automated evidence

```
after: 16 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_remove_clashes
compare: exit=0   (lost [] / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json` is empty: nothing lost. Atom selection single-line; drops typed; errors in the window; work off the
drawing thread.

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_remove_clashes -q -p no:cacheprovider
24 passed
```

`test_emtk_remove_clashes_parity.py` (11): the Qt widget in a subprocess (nothing chosen, cancel, save, an unparsable
selection) on hgbp1 with Cα at 3.5 Å, stride 4; the emtk save keeps exactly the 42 of 116 frames a `scipy` pdist test keeps,
equal to the Qt file's frames and source times (the gaps stay on the time axis); both logs say "Kept 42 of 116 frames";
the Qt dialog now asks for DCD; same precondition, cancel and "Save failed" answers; spec fields drawn with descriptions,
an edit reaches the model and settings; busy state; guide targets drawn, awaits released by presses; draws at both sizes;
settings round trip; help page; Qt-free; tooltips.

Deliberate breakage, round 1 (8: kept count off by the stride, kept count not logged, Qt dialog back to h5, emtk filter h5,
threshold ignored, suggested name, guide threshold step points nowhere, spec descriptions dropped by the shared app): all
caught. Round 2 (12 shared-app faults): all caught.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`.

## 9. Persistence, guide, help, docs

Paths, selection, stride and threshold via `export_settings`. Help and guide new; off the allow-list. README rewritten
(it described van der Waals radii, repair and 3D views). Guide 81's Remove Clashed paragraph updated.

## 10. Blocked / open

none for this plugin.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10


## 12. Second upgrade pass: real-input click coverage (session TRAJCLICK, 2026-10-02)

Scope of the pass: every control of the Remove-Clashed-Frames tool operated with **simulated pointer and keyboard input and host drops** (not calls to
model methods), the outcome read from what is drawn, the fields and the files written. Board claim `T-20261002-TRAJCLICK`.
Commits: `6bb3d7be9` (code and tests of the whole traj family), the traj-family evidence commit that follows it (evidence and reports). Helper:
`chisurf/plugins/traj/traj_save_topology/test/real_input.py` (`Ui`: press / release / move / wheel / key / drop at the drawn rectangles of
`app.item_rects` or at the text a button drew; `check_*` functions the family shares), imported by the other plugins' click suites.

### Regressions found in the first-pass app (fixed in the plugin's own app, both hosts where shared)

1. **No spin arrows on any number field** (shared app `chisurf/plugins/traj/emtk_tool.py`, all seven single-panel tools). The Qt AutoForm draws `int` / `float`
   values as spin boxes (arrows, a step - the spec's, or Qt's default 1 - and the range); the first-pass app drew plain text fields while its report listed "spin" as
   present. Seen by reading `after_populated_*` against `before_populated.png`; the click tests found no `*.stepper`. Fixed: the spec is drawn with the spin style and the
   Qt step (`_spin_numbers`); typed values, both limits, the arrows and the tooltip are tested for every field. The wheel half is gap 1.
2. **The host drop verb was missing.** The app had `on_paths_dropped` (what the Qt host calls) but not `on_files_dropped`, which the native / glfw hosts and `ControlSurface`
   call: a drop on those hosts was silently ignored. Added; it always returns True, because a refused drop's answer is a status line that must be repainted.
3. **Tour card buttons that do not answer on some steps** (gap 3), not fixable in the plugin: none: no tour button is dead on any of its 8 steps.

### Control -> test list (`test/test_emtk_*_clicks.py`; "Qt checklist" = section 3 above plus the Qt baselines read again)

| Qt control / behaviour | Operated in |
|---|---|
| Guide button; tour Next, Prev, Close Tour | `test_guide_and_help_buttons_are_pressed`, `test_no_tour_card_button_is_dead_on_any_step` |
| Help button; Close Help | `test_guide_and_help_buttons_are_pressed` |
| Trajectory `...`: dialog title, DCD filter, folder enter / up, select + Open, double click, Open with nothing selected (`Select a file first.`), Cancel, window x | `test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Topology `...`: same with the PDB filter | `test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Path rows are read-only (typing + Enter changes nothing) | `test_the_path_rows_do_not_take_typing` |
| Host drop (`on_files_dropped`): by file type, empty row first, a foreign file is answered in the window and the drop is still accepted | `test_dropped_files_*` |
| Log (wheel scrolls it) | `test_the_log_scrolls_under_the_wheel_and_back` |
| Stride spin box (1 - 999999): typed + Enter, committed by a click away, text that is no number ignored, clamped at both limits, up / down arrows step and stop at the limits, tooltip on hover | `test_the_stride_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows` |
| Min distance spin box (0 - 100, step 0.1): typed + Enter, committed by a click away, text that is no number ignored, clamped at both limits, up / down arrows step and stop at the limits, tooltip on hover | `test_the_min_distance_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows` |
| Wheel over a spin box (Qt: steps) | `test_the_wheel_steps_*` (strict xfail, gap 1) |
| Atom selection (typed, may be emptied; Enter on the emptied field = gap 2) | `test_the_atom_selection_field_is_typed_and_may_be_emptied`, `test_enter_commits_an_emptied_atom_selection` (strict xfail) |
| Save clash-free: min distance typed to 3.72, dialog with typed name; exactly the frames pdist keeps, with their source times, `Kept N of 8 frames` in the log | `test_filtering_through_the_ui_keeps_exactly_the_frames_without_a_clash` |
| A selection that is not a selection: `Save failed: ...` in the window, nothing written | `test_a_selection_that_is_not_a_selection_is_reported_in_the_window_and_writes_nothing` |
| Action button: precondition message, dialog title and suggested name, Cancel (cancelled line in the log), window x, typed name + Save, overwrite question (Choose another name / Cancel / Replace existing file) | `test_the_action_flow_dialog_cancel_close_save_and_replace` |

### Evidence read at full size

`before_populated.png` (Qt, read again), `before_emtk_populated_*` (first-pass app), `after_populated_{1200x800,800x600}.png`,
`after_dialog_1200x800.png`, `after_guide_800x600.png`, and the click session `after_click_<n>_<what>.png`
(produced by `okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_remove_clashes`: files chosen through the real dialog, fields typed, arrows
pressed, the save dialog with a typed name, the result in the log, Guide and Help opened). Read one by one at full size (all `after_click_*`, `after_populated_*`, the dialog and the guide shots, `before_*`). In the tour-card shots the
log shows through the card (gap 3: the log's child window paints above it); a text field stays highlighted after a click elsewhere (gap 4);
nothing is clipped at either size.

### Tests (pasted)

```
python -m pytest chisurf/plugins/traj/traj_remove_clashes -q -p no:cacheprovider
38 passed, 3 xfailed in 48.80s
```

### Deliberate breakage (twice; each restored byte for byte, the suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: a closed dialog logs nothing  ->  FAILED chisurf/plugins/traj/traj_remove_clashes/test/test_emtk_remove_clashes_clicks.py::test_the_action_flow_dialog_cancel_close_save_and_replace ; 1 failed, 12 passed, 3 xfailed in 5.27s
2. `chisurf/plugins/traj/traj_remove_clashes/view_model.py`: clashed frames are kept  ->  FAILED chisurf/plugins/traj/traj_remove_clashes/test/test_emtk_remove_clashes_clicks.py::test_filtering_through_the_ui_keeps_exactly_the_frames_without_a_clash ; 1 failed, 10 passed, 3 xfailed in 4.76s

`compare`: exit 0 (`lost` empty, `stale_explanations` empty, `untooltipped` empty) after the pass.

**emtk / shared-helper gaps found by the click tests** (none edited: `~/dev/emtk` and `chisurf/emtk/*` untouched). Every
one is reproduced by `okf/plugins/emtk-ports/scripts/emtk_gaps_repro.py` (run with `PYTHONPATH=~/dev/emtk`; output pasted):

```
plain n after wheel +3: 8
docked n after wheel +3: 5
text '' Enter reported 0 (expected text '' and 1)
overlay button pressed: False | input field has the keyboard: True
typing field has the keyboard: True
checkbox toggled: True | keyboard still captured: True (expected False)
```

1. **The wheel does not reach a field inside a `DockManager` window** (a plain `im.begin` window steps it: 8, docked: 5). The Qt spin boxes
   step on the wheel, so the wheel half of the spin-box parity is blocked: the arrows, typing and limits are done and tested.
   Strict xfail `test_the_wheel_steps_*`.
2. **Enter in a text field that was just emptied is not reported as Enter** (`input_text` with `ENTER_RETURNS_TRUE`); a click away
   commits the empty value, so a field can still be cleared. Strict xfail where a text field exists.
3. **A widget drawn after a window, over one of its inputs, loses the press to the input.** The tour card's buttons are such widgets:
   on some steps a card button lies over a field or the log (which is a child window and also paints above the card), the press
   focuses the field and the button does nothing. `dead_tour_buttons` lists them per tool; strict xfail where the list is not empty
   (below). A tour can always be closed with Escape. Fix belongs in `chisurf/emtk/help_guide.py` (the card should be a window of its
   own, or block the widgets under it): the shared helper is another stream's, not edited.
4. **A text field keeps the keyboard after a click on a checkbox or a button elsewhere** (visible as the highlighted field in
   `after_click_*`); a click on another text field does commit and move it. Strict xfail in `traj_convert`.
5. **`kind: "text"` (the Qt multi-line box of the atom selection) is not drawn by `draw_form`**: it becomes a one-line field (read from
   `view_form.py`, which has no multi-line branch). The selection is a short expression, so the single line was kept (deliberate
   difference, no data lost).

### Verdict of the second pass

**Accept.** all controls present and operated; open: the wheel on Stride / Min distance (gap 1), Enter on an emptied Atom selection (gap 2), the multi-line selection box (gap 5). The three suites (parity against the Qt tool, click coverage, plugin tests) are green; the strict xfails are the emtk gaps above and flip to failures the day emtk fixes them.
Report: `okf/plugins/emtk-ports/traj_remove_clashes/REPORT.md`.
