# emtk port report - `traj_energy` (upgrade, audit-all row 36; second pass: the calculator's app rebuilt, real-input verified)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_energy` / `chisurf/plugins/traj/traj_energy` - a second manifest over `chisurf/plugins/traj/potential_energy` (the same Qt `PotentialEnergyWidget` and the same emtk app as `traj_energy_calculator`) |
| Port type | Type A+B: the Qt AutoForm widget (`calculate_potential.view.json` with the custom `potential_energy_setup` / `potential_energy_run` sections) over `PotentialEnergyViewModel`; the emtk app is now drawn from the same spec by the shared trajectory-tool app |
| Agent / date | claude implementing agent, session TRAJCLICK, 2026-10-02 (first pass EMTK-1C: entrypoint only) |
| Commits | first pass `e3e032b1e`; this pass `6bb3d7be9` (app, help, guide, tests, allow-list), the traj-family evidence commit that follows it (evidence, reports) |
| Board | `T-20261002-TRAJCLICK` (earlier `T-20261002-EMTK1C`) |

## 1. Verdict

**Accept after the rebuild.** The first-pass report said "same app, same widget: the parity evidence is the calculator's". The calculator's app
was in fact a hand-drawn window: every number field a **drag** field (`im.input_float` - a value cannot be typed, a unit costs a 100 px drag),
the table of added potentials hand-drawn with a `-` button per row, the trajectory and topology rows free-text fields on which a
keystroke already set the model, an extra `Output` field the Qt tool does not have, no drop hook, **no Help and no Guide**. None of that
shows in a construction test. It is replaced (section 2) and every control is operated with real input (section 5).

## 2. What was wrong, what changed (`gui/app.py` rebuilt on `chisurf/plugins/traj/emtk_tool.py`)

| Qt widget | First-pass emtk app | Now |
|---|---|---|
| Trajectory / Topology rows: read-only, placeholder, `...` dialogs (`*.dcd`, `*.pdb *.cif *.ent`), single-file drop | editable text fields (the model changed on every keystroke), `...` opening a dialog; no drop | the shared read-only rows, same dialogs in a sized window, drops routed by file type (`on_files_dropped`) |
| Potential type combo + **Add** | combo, `Add` below the weight | combo, **Add** under it (a button section), parameters, weight |
| Parameter editors (spin boxes with the Qt ranges and steps, check boxes, file fields) | drag fields (`input_float`), check boxes, text field + `...` | `draw_form` of a spec built from the Qt-free `potential_specs` registry: spin fields with arrows (typed, clamped, stepped), toggles in one row, file rows with a `...` dialog |
| Weight spin box (+-1e6, 3 decimals) | drag field | spin field, the Qt range |
| Stride spin box (1 - 9999) | drag field | the spec's field, spin style |
| Table of added potentials, double-click removes a row | hand-drawn table, `-` button per row | the spec's `table` section (`source: added_potentials`, `activated_call`) - a double click removes, so does Delete |
| Process: info boxes `Open a trajectory first.` / `Add at least one potential.`, save dialog `CSV-name file (*.txt)`, `Process cancelled` in the log, progress bar, `Processed N frame(s)` box, `Processing failed` box | an `Output` text field + `...`; Process ran at once into it | the same preconditions in the window, the same dialog and filter, the cancelled line in the log, `Working... N frame(s)` while it runs, `Processed N frame(s).` / `Processing failed: ...` in the window |
| log | plain lines | scrolling, wrapping log |
| no help, no guide | none | `help.md` (live links), `guide.json` (9 steps), Guide and Help buttons; off the allow-list |
| parameters of a type are lost on every combo change and after Add (the editor is rebuilt) | kept per type | kept per type while another type is looked at, reset after Add (the Qt reset): a superset of Qt, said in the help |

Persistence: `export_settings` / `restore_settings` keep the paths (while the files exist), stride, weight, the selected type and the typed
parameters; the first-pass key `target` is gone with the `Output` field.

## 3. Qt control checklist (`before_populated.png` of `traj_energy_calculator`, the same widget, read again; `sections.py` read completely)

Trajectory row + `...` + drop; Topology row + `...` + drop; potential combo (nine types); **Add**; Parameters box (per type: spin boxes, check
boxes, file fields with `...`); Weight; Stride; table (Potential, Weight; double-click removes); **Process** + progress bar; log; tooltips.
Every one is present (section 5). Not carried over: the Qt progress bar (a `Working... N frame(s)` text), the Qt message boxes (status line),
the `?` Help of the Qt window did not exist (the emtk Help/Guide are new).

## 4. Automated evidence

```
after: 26 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_energy
compare: exit 0 (lost [] / stale [] / untooltipped [])   (explained: cutoff, ca, h - the Qt H-Bond editor's split label "cutoff CA | H")
```

The calculator's evidence (`okf/plugins/emtk-ports/traj_energy_calculator`) was regenerated against the rebuilt app (`after`, `compare` exit 0)
and its report points here.

## 5. Control -> test list (`potential_energy/test/test_emtk_traj_energy_clicks.py`; pointer, keys and drops only)

| Qt control / behaviour | Operated in |
|---|---|
| Guide button; tour Next, Prev, Close Tour | `test_guide_and_help_buttons_are_pressed`, `test_no_tour_card_button_is_dead_on_any_step` |
| Help button; Close Help | `test_guide_and_help_buttons_are_pressed` |
| Trajectory `...`: dialog title, DCD filter, folder enter / up, select + Open, double click, Open with nothing selected (`Select a file first.`), Cancel, window x | `test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Topology `...`: same with the PDB filter | `test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Path rows are read-only (typing + Enter changes nothing) | `test_the_path_rows_do_not_take_typing` |
| Host drop (`on_files_dropped`): by file type, empty row first, a foreign file is answered in the window and the drop is still accepted | `test_dropped_files_*` |
| Log (wheel scrolls it) | `test_the_log_scrolls_under_the_wheel_and_back` |
| Potential type combo: lists the nine types, each choice shows its own parameters (none for Radius of Gyration), Escape closes without choosing | `test_the_type_combo_lists_every_potential_and_each_choice_shows_its_own_parameters`, `test_escape_closes_the_open_type_list_without_choosing` |
| Parameter spin boxes of every type (14 fields: H-Bond cutoffs, AV nSamples / MinAV, Iso-UNRES, Miyazawa-Jernigan, Go epsilon / cutoff / non-native scale, ASA sphere-points / probe / radius, Clash tolerance / bond length): typed + Enter, click away, clamped to the Qt range, arrows step by the Qt step and stop at the limits, tooltip | `test_each_parameter_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows` (14 cases) |
| Parameter check boxes (H-Bond OH / ON / CN / CH, Go native cutoff on / non-native on) | `test_each_checkbox_is_clicked_off_and_on` |
| Potential file fields (typed path, `...` dialog with the NumPy filter, Cancel, window x) | `test_a_potential_file_field_is_typed_and_its_browse_button_picks_a_file` |
| Parameters kept while another type is looked at, back at the defaults after Add (as the rebuilt Qt editor) | `test_the_parameters_of_a_type_survive_choosing_another_and_return_to_their_defaults_after_add` |
| Weight spin box (-1e6 - 1e6, 3 decimals) | `test_the_weight_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows` |
| Stride spin box (1 - 9999) | `test_the_stride_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows` |
| Wheel over a spin box (Qt: steps) | `test_the_wheel_steps_*` (strict xfail, gap 1) |
| Add: the row with the typed weight appears in the table and the log; a potential that cannot be built is reported under the form and not added | `test_add_puts_the_potential_in_the_table_with_the_typed_weight_and_a_failure_is_shown_in_the_window`, `test_a_potential_that_cannot_be_built_is_reported_under_the_form_and_not_added` |
| Table of added potentials: a click selects, a double click removes the row (Qt `activated_call`), Delete removes the selected row | `test_a_double_click_removes_the_row_and_so_does_delete_on_the_selected_row` |
| Process: `Open a trajectory first.` / `Add at least one potential.` before the dialog; dialog `Save energies` with the Qt filter `CSV-name file (*.txt)` | `test_process_says_what_is_missing_before_it_asks_for_a_file` |
| Process: potentials added through the combo, typed weights, dialog with typed name; the file equals what the Qt widget's model wrote (byte for byte); `Processed 4 frame(s).` | `test_processing_through_the_ui_writes_the_energies_the_qt_widgets_model_wrote` |
| Process dialog Cancel (`Process cancelled`), window x, Save, overwrite question | `test_the_process_dialog_cancel_close_and_replace_buttons` |

Energies are compared with the Qt widget's own model run in a subprocess (`test_emtk_traj_energy_parity.py::qt`): the written file is equal byte for byte.
The IMP-backed potentials need `modules/imp-tricks/src` on `PYTHONPATH`; the tests that add a real potential `importorskip("IMP.cgmol")`
(they ran here).

## 6. Tests (pasted)

```
python -m pytest chisurf/plugins/traj/traj_energy chisurf/plugins/traj/potential_energy -q -p no:cacheprovider   (PYTHONPATH with modules/imp-tricks/src; two runs)
traj_energy: 3 passed in 9.13s
potential_energy: 63 passed, 4 xfailed in 41.35s
```

`test_native.py` and `test_emtk_traj_energy_parity.py` were adapted to the rebuilt app (the hand-drawn app's attributes `target`, `message`, `_future`,
`browse(...)` are gone; the processing, file-dialog and tooltip tests now drive `save`, `begin_save`, the spec fields) - same assertions on the numbers.

### Deliberate breakage (twice, restored, suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: a closed dialog logs nothing  ->  FAILED chisurf/plugins/traj/potential_energy/test/test_emtk_traj_energy_clicks.py::test_the_process_dialog_cancel_close_and_replace_buttons ; 1 failed, 33 passed, 4 xfailed in 24.29s
2. `chisurf/plugins/traj/potential_energy/app.py`: the typed weight is ignored  ->  FAILED chisurf/plugins/traj/potential_energy/test/test_emtk_traj_energy_clicks.py::test_add_puts_the_potential_in_the_table_with_the_typed_weight_and_a_failure_is_shown_in_the_window ; 1 failed, 28 passed, 4 xfailed in 18.24s

## 7. Screenshots read

`before_populated.png` / `before_emtk_populated_*` (the calculator's: Qt and the first-pass app), `after_1200x800.png`, `after_800x600.png`, and the click
session `after_click_0 ... 12` (`okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_energy`): empty, trajectory dialog, entry selected, both files, the
type list, two potentials added (a field hovered: tooltip drawn), a row selected, a row removed by a double click, the save dialog with the typed name, the
result (`Processed 4 frame(s).` and the log), the tour card, the help window. Nothing is clipped; the help window shows the markdown raw (known issue
`32c73e41b`, shared window).

## 8. Deliberate differences

`deliberate.json`: `cutoff`, `ca`, `h` (the Qt H-Bond editor's split label; emtk labels each field `Cutoff CA` / `Cutoff H`). The Add button sits under the type
combo, not beside it; the progress bar is a text; messages are in the window instead of boxes; the typed parameters of a type survive a combo change (Qt rebuilds the editor).

## 9. Persistence, guide, help, docs

Round trip tested (`test_native_state_roundtrip`). `guide.json` (9 steps; the awaits are the two `...` buttons, the type list, Add and Process; targets are real
controls, the table step has none); `help.md`; both off `test/plugin_help_guide_allowlist.txt` (two lines struck). Docs: guide 81 "Energy Calc" still describes the controls
as they are; no change needed.

## 10. emtk gaps and shared-helper gaps found

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


## 11. Self-check

- [x] D1 - [x] D2 - [x] D3 - [x] D4 - [x] D5 (energies equal the Qt model's) - [x] D6 - [x] D7 - [x] D8 - [x] D9 - [x] D10
