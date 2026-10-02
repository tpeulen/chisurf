# emtk port report — `traj_join` (upgrade, audit-all row 41)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_join` / `chisurf/plugins/traj/traj_join` |
| Port type | A+B: the Qt `JoinTrajectoriesWidget` (AutoForm over `join_trajectories.view.json`: custom `traj_join_io` with two trajectory rows, topology row and save button; `join_mode` radio, two reverse toggles, `chunk_size`; info log) over `JoinTrajectoriesViewModel`; the stream's hand-drawn emtk `app.py` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `ddf6dc5ec` baseline; `9fdd52bab` emtk app at parity + the join defect fixed (guide 81, known-issues item 7); evidence commit "traj_join: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `manifest.json`, `view_model.py` (`log_text()`); untracked
`app.py`, `strings.py`. Tracked edits committed with the app; `app.py` rewritten, `strings.py` dropped.

## 2. The join defect (guide 81 "Known defects", known-issues item 7), fixed for both hosts

**Measured at HEAD** on the baseline case (hgbp1, 464 frames, joined in time with itself reversed, chunk 100): the output had
the right length (928) but frame 100 was trajectory 2's frame 99 — chunk 0 of trajectory 2, reversed within the chunk — and
the file deviated up to **88.9 Å** from the correct join. Three faults in one loop: chunks of 1 and 2 were `zip`ped and
written alternately (A0–99, B99–0, A100–199, …), the `zip` truncated the longer trajectory, and *Reverse* reversed each chunk.
The loader decodes a file whole anyway (`trajectory_data.iterload` slices a fully loaded trajectory), so the chunked read
saved nothing. `save_joined` now reads both whole; time mode writes all of 1 then all of 2 (same atoms required), atoms
mode stacks frame i of both (same frame count required), a mismatch raises with both counts, *Reverse* reverses the whole
trajectory, chunk size is the write block, and the log says `Wrote N frames of M atoms`. Re-derive with the HEAD view model
(`git show ddf6dc5ec:chisurf/plugins/traj/traj_join/view_model.py`) and the baseline script's `traj_join` populate step.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Trajectory 1 / 2, Topology rows with `…` dialogs and drops | free-text fields | read-only rows, dialogs; dropped DCDs fill empty rows in order, a PDB the topology |
| 💾 Save joined…: "Open two trajectories first."; dialog "Save trajectory" (DCD); cancel logs "Join cancelled"; "Join failed" box | button + free-text Output; no precondition | same texts (status line / log), dialog (`<stem>_joined.dcd`), "Join failed: …" in the window |
| Join mode radio (time / atoms), Reverse 1 / 2, Chunk size | combo, two checkboxes, **no chunk size** | the spec's radio, toggles and int field, descriptions as tooltips (reversal and chunk descriptions corrected) |
| log | log lines | scrolling, wrapping log with the written counts |
| synchronous | synchronous | worker thread |
| no help, no guide | none | `help.md`, `guide.json` (9 steps) |

## 4. Automated evidence

```
after: 18 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_join
compare: exit=0   (lost [] / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json` is empty: nothing lost. Behaviour changed for both hosts by the defect fix (§2). Drops route by type and
fill empty rows first (the Qt rows each took a drop on themselves).

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_join -q -p no:cacheprovider
27 passed in 29.49s
```

`test_emtk_join_parity.py` (14 + parametrised): at chunk 100 (smaller than the trajectory on purpose) the emtk file equals the
Qt file and `concat(source, source[::-1])` computed in numpy (928 × 5235); the turn frame repeats; atoms mode equals
`concat(source, source, axis=1)` (464 × 10470); a frame-count mismatch (atoms) and an atom mismatch (time, self-describing
PDBs, since a shared topology refuses a foreign DCD on load) stop the join with the counts; one file / cancel answer as the
Qt widget; two dropped DCDs plus a PDB fill all three rows; spec fields and descriptions; busy state; guide awaits; draws;
settings round trip; help; Qt-free; tooltips. The first version took 114 s because `pytest.approx` compared 14 million
values element by element; `np.testing.assert_allclose` takes it to 29 s.

Deliberate breakage, round 1 (11: interleave again, reversal dropped, atoms mismatch truncates, time mismatch unchecked,
count not logged, cancel caption, failure caption, one file enough, drop fills the filled row, spec says "chunk" again,
suggested name): all caught. Round 2 (12 shared-app faults): all caught.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`.

## 9. Persistence, guide, help, docs

Paths, mode, toggles and block size via `export_settings`. Help and guide new; off the allow-list. README corrected. Guide
81: Join section rewritten, the "Join interleaves chunks" known defect removed; known-issues item 7 marks it fixed.

## 10. Blocked / open

none for this plugin.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10


## 12. Second upgrade pass: real-input click coverage (session TRAJCLICK, 2026-10-02)

Scope of the pass: every control of the Join-Trajectories tool operated with **simulated pointer and keyboard input and host drops** (not calls to
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
3. **Tour card buttons that do not answer on some steps** (gap 3), not fixable in the plugin: Prev on step 9 (over the log).

### Control -> test list (`test/test_emtk_*_clicks.py`; "Qt checklist" = section 3 above plus the Qt baselines read again)

| Qt control / behaviour | Operated in |
|---|---|
| Guide button; tour Next, Prev, Close Tour | `test_guide_and_help_buttons_are_pressed`, `test_no_tour_card_button_is_dead_on_any_step` |
| Help button; Close Help | `test_guide_and_help_buttons_are_pressed` |
| Trajectory 1 / Trajectory 2 `...` (dialogs `Open trajectory 1` / `2`, every way out) | `test_each_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Topology `...`: same with the PDB filter | `test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Path rows are read-only (three rows) | `test_the_path_rows_do_not_take_typing` |
| Host drop: two DCDs fill trajectory 1 then 2, a PDB the topology, a foreign file answered | `test_dropped_files_fill_the_empty_row_first_and_a_pdb_the_topology` |
| Log (wheel scrolls it) | `test_the_log_scrolls_under_the_wheel_and_back` |
| Join mode radios (By time / By atoms): click each, the checked one stays checked | `test_the_join_mode_radios_are_clicked_and_the_choice_is_drawn_checked` |
| Reverse trajectory 1 / 2 check boxes: on, off, the box itself | `test_each_reverse_checkbox_is_clicked_on_and_off` |
| Chunk size spin box (1 - 9999999): typed + Enter, committed by a click away, text that is no number ignored, clamped at both limits, up / down arrows step and stop at the limits, tooltip on hover | `test_the_chunk_size_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows` |
| Wheel over a spin box (Qt: steps) | `test_the_wheel_steps_*` (strict xfail, gap 1) |
| Save joined, time mode: reverse 2 ticked and chunk 3 typed; the file is `concat(A, B[::-1])` | `test_a_time_join_through_the_ui_appends_the_second_trajectory_reversed_when_its_box_is_ticked` |
| Reverse 1 ticked: `concat(A[::-1], B)` | `test_reversing_trajectory_one_reverses_the_first_half` |
| Atoms mode through the radio: `concat(A, B, axis=1)` (10470 atoms) | `test_an_atoms_join_through_the_radio_stacks_the_two_trajectories_frame_by_frame` |
| One trajectory only: `Open two trajectories first.`, no dialog | `test_one_trajectory_is_not_enough_and_the_dialog_does_not_open` |
| Action button: precondition message, dialog title and suggested name, Cancel (cancelled line in the log), window x, typed name + Save, overwrite question (Choose another name / Cancel / Replace existing file) | `test_the_action_flow_dialog_cancel_close_save_and_replace` |

### Evidence read at full size

`before_populated.png` (Qt, read again), `before_emtk_populated_*` (first-pass app), `after_populated_{1200x800,800x600}.png`,
`after_dialog_1200x800.png`, `after_guide_800x600.png`, and the click session `after_click_<n>_<what>.png`
(produced by `okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_join`: files chosen through the real dialog, fields typed, arrows
pressed, the save dialog with a typed name, the result in the log, Guide and Help opened). Read one by one at full size (all `after_click_*`, `after_populated_*`, the dialog and the guide shots, `before_*`). In the tour-card shots the
log shows through the card (gap 3: the log's child window paints above it); a text field stays highlighted after a click elsewhere (gap 4);
nothing is clipped at either size.

### Tests (pasted)

```
python -m pytest chisurf/plugins/traj/traj_join -q -p no:cacheprovider
45 passed, 2 xfailed in 43.95s
```

### Deliberate breakage (twice; each restored byte for byte, the suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: a drop fills the filled row first  ->  FAILED chisurf/plugins/traj/traj_join/test/test_emtk_join_clicks.py::test_dropped_files_fill_the_empty_row_first_and_a_pdb_the_topology ; 1 failed, 7 passed, 1 xfailed in 1.64s
2. `chisurf/plugins/traj/traj_join/view_model.py`: trajectory 2 is never reversed  ->  FAILED chisurf/plugins/traj/traj_join/test/test_emtk_join_clicks.py::test_a_time_join_through_the_ui_appends_the_second_trajectory_reversed_when_its_box_is_ticked ; 1 failed, 12 passed, 2 xfailed in 3.52s

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

**Accept.** all controls present and operated; open: the wheel on Chunk size (gap 1) and Prev on the last tour step (gap 3). The three suites (parity against the Qt tool, click coverage, plugin tests) are green; the strict xfails are the emtk gaps above and flip to failures the day emtk fixes them.
Report: `okf/plugins/emtk-ports/traj_join/REPORT.md`.
