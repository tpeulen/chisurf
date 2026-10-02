# emtk port report — `traj_rotate_translate` (upgrade, audit-all row 39)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_rotate_translate` / `chisurf/plugins/traj/traj_rotate_translate` |
| Port type | A+B: the Qt `RotateTranslateTrajectoryWidget` (AutoForm over `rotate_translate.view.json`: custom `traj_rotate_translate_io` with trajectory + topology rows, 3×3 rotation grid, translation row and save button; `stride`; info log) over `RotateTranslateViewModel`; the stream's hand-drawn emtk `app.py` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `61087e75f` baseline; `32bfacb67` emtk app at parity with the Qt tool (+ guide 81 wording); evidence commit "traj_rotate_translate: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `manifest.json`, `view_model.py` (`log_text()`); untracked
`app.py`, `strings.py`. Tracked edits committed with the app; `app.py` rewritten, `strings.py` dropped. Qt `widget.py` /
`sections.py` unchanged (= HEAD).

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Trajectory / Topology rows with `…` dialogs and drops | free-text fields | read-only rows, dialogs, typed drops (shared app) |
| Rotation matrix: 3×3 grid of numeric edits, group tooltip | nine stacked fields R00…R22 | 3×3 grid of numeric fields, same tooltip |
| Translation [Ang.]: row of 3 | T0…T2 stacked | row of 3, tooltip |
| 💾 Save rotated/translated…: precondition box, dialog "Save trajectory" (DCD), cancel logged, "Save failed" box | button + free-text Output | same precondition, dialog (`<stem>_moved.dcd`), cancel logged, "Save failed: …" in the window and log |
| Stride (spin) | float field "4.000" | the spec's int field |
| matrix not checked | not checked | **new**: "Not a rotation: …" under the grid for RᵀR ≠ 1 or det R = −1 (the save still runs) |
| no help, no guide | none | `help.md`, `guide.json` (8 steps; rows, matrix and save await) |

## 4. Automated evidence

```
after: 15 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_rotate_translate
compare: exit=0   (lost [] / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json` is empty: nothing lost. Gained: the non-rotation warning (the docs had listed its absence as a defect;
guide 81 updated). Matrix fields write the model as they are edited (the Qt editors wrote it on editing-finished and again
before a save; the emtk fields have no pending state).

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_rotate_translate -q -p no:cacheprovider
27 passed
```

`test_emtk_rotate_translate_parity.py` (14 + parametrised): the Qt widget in a subprocess with R (90° about z) and t (10 Å
along x) typed into its editors; the emtk save writes 116 frames equal to the Qt file (1e-4 Å) and to x′ = R x + t computed
in the test (1e-3 Å), atom 0 lands at (10 − y, x, z); same precondition, cancel and "Save failed" answers, the failure drawn;
editors write R and t; shear / mirror / proper rotation named or not, drawn or not; busy state with a second press
ignored; guide targets drawn, the matrix step released by an edit, the file and save steps by presses; draws at both sizes;
settings round trip (R and t included); help page; Qt-free; tooltips.

Deliberate breakage, round 1 (10 tool faults: matrix edit transposed, translation edit lost, warning never shown, mirror
accepted, matrix not reported to the tour, matrix not persisted, translation rect missing, matrix tooltip missing, wrong
stride in the action, suggested name): all caught. Round 2 (12 shared-app faults): "browse does not tell the tour" and
"status not drawn" passed at first (this suite pressed no file row in the guide test and checked the failure only as state);
both checks added, both caught.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`,
`after_shear_warning_800x600.png`.

## 9. Persistence, guide, help, docs

Paths, stride, R and t via `export_settings`. Help and guide new; off the allow-list. README rewritten (it described 3D
manipulation, batch processing and alignment the tool never had). Guide 81's Rot Translate paragraph updated for the warning.

## 10. Blocked / open

none for this plugin. Incident while editing guide 81: my edit script opened the file for writing before reading it and
emptied the working copy, which held another agent's uncommitted tags change; restored from HEAD plus that one-line hunk
(captured earlier in full), and the working blob hash matched the pre-incident diff header (`4388c842a`) before my edit was
applied again. Committed only HEAD + my wording (temp-index blob); the tags change remains theirs, uncommitted.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10


## 12. Second upgrade pass: real-input click coverage (session TRAJCLICK, 2026-10-02)

Scope of the pass: every control of the Rotate/Translate tool operated with **simulated pointer and keyboard input and host drops** (not calls to
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
3. **Tour card buttons that do not answer on some steps** (gap 3), not fixable in the plugin: Close Tour and Prev on steps 2 and 8 (over the Stride field, and the log).
4. **The rotation matrix and the translation could not be typed.** The nine matrix cells and the three translation cells were `im.input_float`, which in emtk is a *drag*
   field (a click does not even focus it): one unit cost a 100 px drag. The Qt editors are line edits. Replaced by typed cells that commit on Enter or when the click goes elsewhere
   and ignore text that is no number; the two first-pass parity tests that injected values by monkeypatching `im.input_float` now inject through `im.input_text`.

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
| Wheel over a spin box (Qt: steps) | `test_the_wheel_steps_*` (strict xfail, gap 1) |
| Rotation matrix (9 cells) and Translation (3 cells): each cell takes a typed number on Enter | `test_every_matrix_and_translation_cell_takes_a_typed_number_on_enter` |
| A cell: text that is no number leaves the value; a click away commits | `test_a_cell_keeps_its_value_when_the_text_is_no_number_and_commits_when_clicked_away` |
| `Not a rotation` warning (sheared / scaled, mirrored) appears and goes | `test_the_warning_names_a_matrix_that_is_not_a_rotation_and_goes_when_it_is_one_again` |
| Save rotated/translated: typed matrix + translation + stride arrow; the DCD equals `R x + t` of the source (1e-3 A) and the help page's example point | `test_rotating_and_translating_through_the_ui_writes_R_x_plus_t` |
| Action button: precondition message, dialog title and suggested name, Cancel (cancelled line in the log), window x, typed name + Save, overwrite question (Choose another name / Cancel / Replace existing file) | `test_the_action_flow_dialog_cancel_close_save_and_replace` |

### Evidence read at full size

`before_populated.png` (Qt, read again), `before_emtk_populated_*` (first-pass app), `after_populated_{1200x800,800x600}.png`,
`after_dialog_1200x800.png`, `after_guide_800x600.png`, and the click session `after_click_<n>_<what>.png`
(produced by `okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_rotate_translate`: files chosen through the real dialog, fields typed, arrows
pressed, the save dialog with a typed name, the result in the log, Guide and Help opened). Read one by one at full size (all `after_click_*`, `after_populated_*`, the dialog and the guide shots, `before_*`). In the tour-card shots the
log shows through the card (gap 3: the log's child window paints above it); a text field stays highlighted after a click elsewhere (gap 4);
nothing is clipped at either size.

### Tests (pasted)

```
python -m pytest chisurf/plugins/traj/traj_rotate_translate -q -p no:cacheprovider
40 passed, 2 xfailed in 50.07s
```

### Deliberate breakage (twice; each restored byte for byte, the suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: the host drop verb declines  ->  FAILED chisurf/plugins/traj/traj_rotate_translate/test/test_emtk_rotate_translate_clicks.py::test_dropped_files_fill_the_rows_by_type_and_a_foreign_file_is_answered ; 1 failed, 5 passed, 1 xfailed in 1.34s
2. `chisurf/plugins/traj/traj_rotate_translate/view_model.py`: the translation is not applied  ->  FAILED chisurf/plugins/traj/traj_rotate_translate/test/test_emtk_rotate_translate_clicks.py::test_rotating_and_translating_through_the_ui_writes_R_x_plus_t ; 1 failed, 10 passed, 2 xfailed in 3.25s

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

**Accept.** all controls present and operated, the matrix is typeable again; open: the wheel on Stride (gap 1) and the tour's Prev / Close Tour on steps 2 and 8 (gap 3). The three suites (parity against the Qt tool, click coverage, plugin tests) are green; the strict xfails are the emtk gaps above and flip to failures the day emtk fixes them.
Report: `okf/plugins/emtk-ports/traj_rotate_translate/REPORT.md`.
