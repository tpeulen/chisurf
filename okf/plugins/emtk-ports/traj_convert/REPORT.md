# emtk port report — `traj_convert` (upgrade, audit-all row 43)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_convert` / `chisurf/plugins/traj/traj_convert` |
| Port type | A+B: the Qt `MDConverter` widget (AutoForm over `convert_structures.view.json`: *Input* panel with the custom `traj_convert_io` rows (topology, trajectory — a folder when the toggle is on —, target folder), the folder toggle and the frame range; *Output* panel with name, format, split and the custom `traj_convert_run` ▶ Convert; info log) over `MDConverterViewModel`; the stream's hand-drawn emtk `app.py` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `e0ac97b3f` baseline; `826e3fe66` emtk app at parity + one frame selection for every mode (guide 81, known-issues); evidence commit "traj_convert: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `manifest.json`, `view_model.py` (`log_text()`); untracked
`app.py`, `strings.py`. Tracked edits committed with the app; `app.py` rewritten, `strings.py` dropped.

## 2. The conversion, fixed for both hosts

**Measured at baseline** (frames 10 to 50 at stride 10 into one DCD): both hosts wrote **4** frames (10–40), not 5 — the
range was `slice(first, last, stride)`. Guide 81 also listed split mode ignoring the stride and crashing on a range (it
called `iterload` without the stride, and with `chunk=None` when a range was set) and folder mode reading the folder path
itself. `convert()` now takes one `frame_selection(n)` (first to last **inclusive**, −1 = the end) for both outputs, reads a
folder's `*.pdb` in name order as consecutive frames (`trajectory_data.join`), names split files by their source frame,
refuses an empty selection ("The frame range selects no frames.") and a missing target folder (it used to write into the
working directory). Multi-frame PDB output already worked (append mode and MODEL records are in core): that defect was
stale. New known issue: `trajectory_data.load` reads a multi-model PDB as its first model, so ChiSurf cannot read back a
multi-frame PDB it wrote (guide 81 *Known defects* says so).

## 3. The shared app grew four things (`chisurf/plugins/traj/emtk_tool.py`)

Rows that take a folder (always, or when `folder(model)` says so — the converter's toggle); specs of several panels kept as
titled, folding panels (single-panel tools unchanged); an action drawn in a custom section of its own (`action_key`) that
runs without a save dialog (`dialog_title=None`); a `done` notice after a successful run (the Qt confirmation box). The
status is drawn once (a first version drew it beside the rows too — caught by the breakage round).

## 4. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Topology / Trajectory / Target folder rows, `…` (file, or folder per the toggle; target always a folder) | free-text fields | read-only rows, file or folder dialogs per the toggle, drops (a dropped folder goes to the folder row) |
| folder toggle, First/Last frame, Stride | toggles and int steppers | the spec's fields, descriptions as tooltips |
| Filename, Format (.dcd/.pdb), Split | text, combo, toggle | the spec's fields |
| ▶ Convert; "Choose a trajectory first.", "Conversion done!", "Conversion failed" boxes | button | same button in the Output panel; same texts in the window; also "Choose a target folder first." |
| collapsible Input / Output panels | flat | folding panels |
| log | log lines | scrolling, wrapping log |
| synchronous | synchronous | worker thread |

## 5. Automated evidence

```
after: 26 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_convert
compare: exit=0   (lost: the Qt Format combo's internals, in deliberate.json)
```

## 6. Deliberate differences

`deliberate.json`: ".pdb" and "2" are the Qt Format combo's second item and its popup's row number. Behaviour changed for
both hosts by §2; a missing target folder is refused.

## 7. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_convert -q -p no:cacheprovider
29 passed
```

`test_emtk_convert_parity.py` (16): the Qt widget in a subprocess (nothing chosen, a range, an empty range) — the emtk file
equals the Qt file and `source[[10, 20, 30, 40, 50]]`; −1 reaches the end; split writes `frames_00000000.pdb` … `_400`
at stride 100, each equal to its source frame; a multi-frame PDB holds three MODELs whose coordinates, read from the PDB
columns, equal the source (the loader cannot be the reference, see §2); a folder of three PDBs becomes three frames, the
browse dialog a folder dialog; same answers and captions as Qt, a missing target refused, the failure drawn once; spec
fields with descriptions, panels fold; busy state with exactly one run for two presses; drops fill all three rows; guide
awaits; draws (log lines drawn); settings round trip; help; Qt-free; tooltips. The stream's (uncommitted) Traj Tools hub
test restored a non-existent `run.dcd`; the shared app does not restore a missing path, so that test now uses the hgbp1
file — edited in place, left uncommitted for the hub's port (board note).

Deliberate breakage, round 1 (12: last frame exclusive again, split ignores the selection, split numbered by position,
folder mode reads the folder, no target check, done not said, failure caption, browse ignores the toggle, target row takes
files, panels do not fold, empty range not refused, nested log not hosted): all caught. Round 2 (9 applicable shared-app
faults): "busy guard removed" (no run count), "log not drawn" (no log assertion) and "status not drawn" (the duplicate
drawing hid it) passed at first; run count and log assertion added, the duplicate removed and the failure asserted drawn
once — all caught.

## 8. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png` (the target-folder dialog: an action without a save
dialog shows a row's browse dialog), `after_guide_800x600.png`.

## 9. Persistence, guide, help, docs

Paths (if still present), toggles, range, name, format, split via `export_settings`. Help and guide new; off the allow-list.
README corrected. Guide 81: Convert paragraph rewritten, four Known defects replaced by the multi-model read-back one;
known-issues item 7 marks the convert defects fixed and a new entry records the read-back gap.

## 10. Blocked / open

- Multi-model PDB read-back (known issue, core).
- The hub test edit (above) waits for the Traj Tools port to commit it.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10


## 12. Second upgrade pass: real-input click coverage (session TRAJCLICK, 2026-10-02)

Scope of the pass: every control of the trajectory converter operated with **simulated pointer and keyboard input and host drops** (not calls to
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
3. **Tour card buttons that do not answer on some steps** (gap 3), not fixable in the plugin: Close Tour on steps 2, 3, 5 and 9, Prev on steps 2 and 3 (over the Filename and Format fields).

### Control -> test list (`test/test_emtk_*_clicks.py`; "Qt checklist" = section 3 above plus the Qt baselines read again)

| Qt control / behaviour | Operated in |
|---|---|
| Guide button; tour Next, Prev, Close Tour | `test_guide_and_help_buttons_are_pressed`, `test_no_tour_card_button_is_dead_on_any_step` |
| Help button; Close Help | `test_guide_and_help_buttons_are_pressed` |
| Trajectory `...`: dialog title, DCD filter, folder enter / up, select + Open, double click, Open with nothing selected (`Select a file first.`), Cancel, window x | `test_the_trajectory_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Topology `...`: same with the PDB filter | `test_the_topology_browse_button_opens_a_filtered_dialog_and_every_way_out_works` |
| Path rows are read-only (typing + Enter changes nothing) | `test_the_path_rows_do_not_take_typing` |
| Target folder `...`: folder dialog lists folders only, Choose takes the selected or the shown folder, starts in the chosen one, `[..]`, Cancel, window x | `test_the_target_folder_dialog_lists_folders_only_and_chooses_the_selected_or_the_shown_one` |
| `Input is a folder of PDBs` check box turns the trajectory row into a folder chooser (and back) | `test_the_folder_checkbox_turns_the_trajectory_row_into_a_folder_chooser` |
| Host drop: files by type, a folder on the target row (or on the trajectory row in folder mode), a foreign file answered | `test_dropped_files_and_folders_fill_the_rows_by_type_and_a_foreign_file_is_answered` |
| First frame / Last frame / Stride spin box (0 - 99999999 / -1 - 9999999 / 1 - 99999): typed + Enter, committed by a click away, text that is no number ignored, clamped at both limits, up / down arrows step and stop at the limits, tooltip on hover | `test_each_frame_range_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows (3 cases)` |
| Wheel over a spin box (Qt: steps) | `test_the_wheel_steps_*` (strict xfail, gap 1) |
| Filename text field (typed, committed by a click away) | `test_the_filename_field_is_typed_and_a_click_away_commits` |
| Format combo (.dcd / .pdb): list opened, each entry clicked, Escape closes without choosing | `test_the_format_combo_lists_both_formats_and_each_is_clicked` |
| Split into one file per frame check box | `test_the_split_checkbox_is_clicked_on_and_off` |
| Input / Output panel headers fold and unfold | `test_the_panel_headers_fold_and_unfold_their_controls` |
| Convert: `Choose a trajectory first.` / `Choose a target folder first.` before it runs | `test_convert_says_what_is_missing_before_it_runs` |
| Convert a range (first 1, last 6, stride 2 typed): frames 1, 3, 5 written (the inclusive last frame rule), `Conversion done!` | `test_converting_a_range_through_the_ui_writes_those_frames_and_says_done` |
| Last frame -1 reaches the end; the format combo writes a multi-model PDB | `test_last_frame_minus_one_reaches_the_end_and_the_format_combo_writes_a_multi_model_pdb` |
| Split: `f_00000000.pdb`, `f_00000003.pdb`, `f_00000006.pdb` (named by source frame, stride honoured) | `test_split_writes_one_file_per_selected_frame_named_by_its_source_frame` |
| A range that selects nothing: `Conversion failed: The frame range selects no frames.` in the window, nothing written; fixing the field and running again works | `test_a_range_that_selects_nothing_is_reported_in_the_window_and_writes_nothing` |
| Folder of PDBs read as consecutive frames (`Read 3 files as 3 frames`) | `test_a_folder_of_pdbs_is_converted_as_consecutive_frames` |
| A text field keeps the keyboard after a click on a check box (gap 4) | `test_a_text_field_gives_up_the_keyboard_when_a_checkbox_elsewhere_is_clicked` (strict xfail) |

### Evidence read at full size

`before_populated.png` (Qt, read again), `before_emtk_populated_*` (first-pass app), `after_populated_{1200x800,800x600}.png`,
`after_dialog_1200x800.png`, `after_guide_800x600.png`, and the click session `after_click_<n>_<what>.png`
(produced by `okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_convert`: files chosen through the real dialog, fields typed, arrows
pressed, the save dialog with a typed name, the result in the log, Guide and Help opened). Read one by one at full size (all `after_click_*`, `after_populated_*`, the dialog and the guide shots, `before_*`). In the tour-card shots the
log shows through the card (gap 3: the log's child window paints above it); a text field stays highlighted after a click elsewhere (gap 4);
nothing is clipped at either size.

### Tests (pasted)

```
python -m pytest chisurf/plugins/traj/traj_convert -q -p no:cacheprovider
52 passed, 5 xfailed in 46.96s
```

### Deliberate breakage (twice; each restored byte for byte, the suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: spin arrows step by 2  ->  FAILED chisurf/plugins/traj/traj_convert/test/test_emtk_convert_clicks.py::test_each_frame_range_field_is_typed_clicked_away_clamped_and_stepped_by_its_arrows[first_frame-0-3-0-99999999] ; 1 failed, 9 passed, 1 xfailed in 2.70s
2. `chisurf/plugins/traj/traj_convert/view_model.py`: the last frame is left out again  ->  FAILED chisurf/plugins/traj/traj_convert/test/test_emtk_convert_clicks.py::test_last_frame_minus_one_reaches_the_end_and_the_format_combo_writes_a_multi_model_pdb ; 1 failed, 18 passed, 4 xfailed in 6.81s

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

**Accept.** all controls present and operated; open: the wheel on the three frame fields (gap 1), the tour's dead buttons (gap 3), a text field keeping the keyboard (gap 4). The three suites (parity against the Qt tool, click coverage, plugin tests) are green; the strict xfails are the emtk gaps above and flip to failures the day emtk fixes them.
Report: `okf/plugins/emtk-ports/traj_convert/REPORT.md`.
