# emtk port report — `traj_fret` (upgrade, audit-all row 45)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_fret` / `chisurf/plugins/traj/fret_trajectory` |
| Port type | A+B: the Qt `Structure2Transfer` (AutoForm over `structure2transfer.view.json`: Reference (custom `fret_traj_io` trajectory row, stride), Dipole atoms (custom `fret_atom_pairs`, four PDBSelectors), Parameters, Process (custom `fret_run` + log)) over `FretTrajectoryViewModel`; the stream's hand-drawn emtk `app.py` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `733469ea2` baseline; `4c7cf3806` emtk app at parity + topology row on both hosts (guide 81, known-issues item 7); evidence commit "traj_fret: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `manifest.json`, `view_model.py` (`log_text()`); untracked
`app.py`, `strings.py`, `test/test_native.py`, `test/capture_native.py`, `test/renders/` (left untracked). Tracked edits
committed; the stream's app rewritten, its strings and two test scripts dropped (copies in `pre-upgrade/`).

## 2. Defects fixed

- **The Qt tool could not open a trajectory from its window**: its browse filter offered only the retired `.h5`, and it had
  no topology row although a DCD stores coordinates only (guide 81 *Known defects*). The Qt section gains the topology row
  and a DCD filter.
- **Trajectory before topology raised** in the view model (`stores coordinates only; pass top=`), losing the pick; it now
  logs what is missing and loads the atoms when the topology arrives.
- The stream's atom combos **labelled every atom wrongly** (atom 1, MET1 CA, showed as `MET1:N`: `atom_id` and `element`
  read where `res_id` and `atom_name` belong) — replaced by cascading pickers.
- Found in the port itself: the atom cache was named `_index`, shadowing `ImApp._index(button)`, so **no pointer press
  reached the app**; only the press tests showed it.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| Trajectory row (`.h5` filter), no topology row | trajectory + topology free-text rows | trajectory + topology rows, dialogs, typed drops (shared app); Qt gains the topology row too |
| Stride | stepper | spec field |
| Donor / Acceptor: 2 PDBSelectors each (Chain, Residue, Atom combos) | one combo per atom over all atoms, mislabelled | 2 × (Chain → Residue → Atom) per dye with the same captions; a chain or residue change takes its first atom |
| R0, τ0, t-step, Dipole (κ2) | fields | spec fields (τ0 and κ2 written in Greek in the spec, as Qt's AutoForm showed them) |
| ▶ Process trajectory → save dialog → CSV; boxes for "no trajectory" / "Processing failed" | free-text output + Process | same button and texts, CSV dialog (`<stem>_fret.csv`), worker |
| log | log | scrolling, wrapping log |
| no help, no guide | none | `help.md`, `guide.json` (8 steps) |

## 4. Automated evidence

```
after: 24 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_fret
compare: exit=0   (Chain / Residue / Atom captions: drawn once atoms are loaded; deliberate.json)
```

## 5. Deliberate differences

`deliberate.json`: the Qt selectors' captions are drawn above the emtk pickers once a topology is loaded; the inventory
runs the app empty.

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/fret_trajectory -q -p no:cacheprovider
26 passed
```

`test_emtk_fret_parity.py` (15): the Qt tool in a subprocess (its new topology row used, donor 1/20, acceptor 3000/3010,
dipoles on, stride 4) — its pickers show A/1/CA, A/3/C, B/332/HA, B/334/CA as the emtk pickers do, and the 116-row
tables agree; the table equals frame numbers, dipole-centre distances, κ and 3/2 κ² (R0/R)⁶/τ0 computed from the
coordinates; without dipoles the first atoms and κ² = 2/3; the trajectory may come before its topology; the Qt answers
for nothing chosen and cancel; a failure shown in the window; the pickers cascade (a residue change takes its first atom,
the other dye untouched); spec fields with descriptions; one run for two presses; guide targets drawn, file and Process
awaits released by presses; draws at both sizes with both caption rows and the log; settings round trip (ready to
process); help; Qt-free; tooltips.

Deliberate breakage, round 1 (13: trajectory first raises, picker resets to residue 1, picker writes the wrong dye, atom
names shown wrong, restore skips the engine topology, donor/acceptor not persisted, process without precondition, failure
and cancel captions, suggested name, donor rect missing, the cache shadowing `ImApp._index`, Qt topology row missing):
12 caught; **"Qt topology row missing" passed because the Qt fixture skipped** when the subprocess failed — the fixture now
skips only when Qt is absent and fails otherwise; caught. Round 2 (12 shared-app faults): "log not drawn" passed (no log
assertion); added; all caught. The skip-on-failure fixture pattern is in every Qt fixture of this session's ports — swept
in a follow-up commit.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`, `after_help_1200x800.png`.
They caught the acceptor column's missing Residue/Atom captions (offsets measured from the wrong origin inside a group).

## 9. Persistence, guide, help, docs

Paths, stride, dye parameters, donor and acceptor via `export_settings`; restoring goes through `set_topology` so the engine
and the pickers are ready. Help and guide new; off the allow-list. README rewritten. Guide 81: the FRET section lists the
topology row, the "no topology field" paragraph and known defect removed; known-issues item 7 marks it fixed.

## 10. Blocked / open

none for this plugin.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10


## 12. Second upgrade pass: real-input click coverage (session TRAJCLICK, 2026-10-02)

Scope of the pass: every control of the Trajectory-to-FRET tool operated with **simulated pointer and keyboard input and host drops** (not calls to
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
3. **Tour card buttons that do not answer on some steps** (gap 3), not fixable in the plugin: Close Tour on steps 2, 3, 4, 5 and 8, Prev on step 3 (over the pickers, fields and log).

### Control -> test list (`test/test_emtk_*_clicks.py`; "Qt checklist" = section 3 above plus the Qt baselines read again)

| Qt control / behaviour | Operated in |
|---|---|
| Guide button; tour Next, Prev, Close Tour | `test_guide_and_help_buttons_are_pressed`, `test_no_tour_card_button_is_dead_on_any_step` |
| Help button; Close Help | `test_guide_and_help_buttons_are_pressed` |
| Trajectory `...`: dialog title, DCD filter, folder enter / up, select + Open, double click, Open with nothing selected (`Select a file first.`), Cancel, window x | `test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Topology `...`: same with the PDB filter | `test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Path rows are read-only (typing + Enter changes nothing) | `test_the_path_rows_do_not_take_typing` |
| Host drop: either order (trajectory before topology says so and waits), a foreign file answered | `test_dropped_files_fill_the_rows_by_type_and_either_order_works` |
| Log (wheel scrolls it) | `test_the_log_scrolls_under_the_wheel_and_back` |
| The twelve pickers (donor / acceptor x two atoms x chain / residue / atom): each list opens, an atom choice moves only that atom, a residue choice takes its first atom, a chain choice the first atom of its first residue | `test_each_of_the_twelve_pickers_opens_its_list_and_a_choice_changes_the_atom` |
| A picker list closes with Escape without choosing | `test_a_picker_list_closes_with_escape_without_choosing` |
| Stride / R0 / tau0 / t-step spin box (1 - 99999 / 0 - 9999 / 0 - 1000 step 0.1 / 0 - 100000 step 0.1): typed + Enter, committed by a click away, text that is no number ignored, clamped at both limits, up / down arrows step and stop at the limits, tooltip on hover | `test_each_number_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows (4 cases)` |
| Wheel over a spin box (Qt: steps) | `test_the_wheel_steps_*` (strict xfail, gap 1) |
| Dipole (kappa2) check box | `test_the_dipole_checkbox_is_clicked_on_and_off` |
| Reference / Dipole atoms / Parameters / Process panel headers fold and unfold | `test_the_panel_headers_fold_and_unfold_their_controls` |
| Process trajectory: dialog `Output-file` (`<stem>_fret.csv`), picked atoms, stride, R0, tau0, t-step typed; the table equals the distance, kappa and rate computed from the coordinates (frame x t-step on the time axis) | `test_processing_through_the_ui_writes_the_physics_of_the_picked_atoms` |
| Dipole box off: first atoms only and kappa2 = 2/3 | `test_without_the_dipole_box_the_first_atoms_and_two_thirds_are_used` |
| Action button: precondition message, dialog title and suggested name, Cancel (cancelled line in the log), window x, typed name + Save, overwrite question (Choose another name / Cancel / Replace existing file) | `test_the_action_flow_dialog_cancel_close_save_and_replace` |

### Evidence read at full size

`before_populated.png` (Qt, read again), `before_emtk_populated_*` (first-pass app), `after_populated_{1200x800,800x600}.png`,
`after_dialog_1200x800.png`, `after_guide_800x600.png`, and the click session `after_click_<n>_<what>.png`
(produced by `okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_fret`: files chosen through the real dialog, fields typed, arrows
pressed, the save dialog with a typed name, the result in the log, Guide and Help opened). Read one by one at full size (all `after_click_*`, `after_populated_*`, the dialog and the guide shots, `before_*`). In the tour-card shots the
log shows through the card (gap 3: the log's child window paints above it); a text field stays highlighted after a click elsewhere (gap 4);
nothing is clipped at either size.

### Tests (pasted)

```
python -m pytest chisurf/plugins/traj/fret_trajectory -q -p no:cacheprovider
44 passed, 5 xfailed in 49.74s
```

### Deliberate breakage (twice; each restored byte for byte, the suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: the host drop verb declines  ->  FAILED chisurf/plugins/traj/fret_trajectory/test/test_emtk_fret_clicks.py::test_dropped_files_fill_the_rows_by_type_and_either_order_works ; 1 failed, 5 passed, 1 xfailed in 1.75s
2. `chisurf/plugins/traj/fret_trajectory/app.py`: the second atom of a dipole is never stored  ->  FAILED chisurf/plugins/traj/fret_trajectory/test/test_emtk_fret_clicks.py::test_each_of_the_twelve_pickers_opens_its_list_and_a_choice_changes_the_atom ; 1 failed, 6 passed, 1 xfailed in 1.94s

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

**Accept.** all controls present and operated, the twelve pickers included; open: the wheel on the four number fields (gap 1) and the tour's dead buttons (gap 3). The three suites (parity against the Qt tool, click coverage, plugin tests) are green; the strict xfails are the emtk gaps above and flip to failures the day emtk fixes them.
Report: `okf/plugins/emtk-ports/traj_fret/REPORT.md`.
