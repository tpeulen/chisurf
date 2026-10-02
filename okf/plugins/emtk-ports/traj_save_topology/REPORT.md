# emtk port report — `traj_save_topology` (upgrade, audit-all row 37)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_save_topology` / `chisurf/plugins/traj/traj_save_topology` |
| Port type | A+B: the Qt `SaveTopology` widget (AutoForm over `save_topology.view.json`, custom `traj_save_topology_io` section: trajectory + topology rows, save button; info log) over `SaveTopologyViewModel`; the stream's hand-drawn emtk `app.py` over the same view model |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `f639974c9` baseline; `32c73e41b` known issue (emtk help window markdown); `2cb97ce87` emtk app at parity with the Qt tool; evidence commit "traj_save_topology: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py` (lazy Qt import), `manifest.json` (emtk entrypoint),
`view_model.py` (`log_text()`); untracked `app.py`, `strings.py`, `test/test_native.py`. The tracked edits are committed with
the app; `app.py` is rewritten, `strings.py` and `test_native.py` are dropped (copies in `pre-upgrade/`). Qt `widget.py` and
`sections.py` are unchanged (= HEAD).

## 2. A shared app for the trajectory family

Align, Rotate/Translate, Remove Clashed, Join and Save Topology are one window shape around different view models. The new
`chisurf/plugins/traj/emtk_tool.py` (`TrajToolApp`, `PathField`, `SaveAction`) draws a tool's spec with `draw_form`, its
custom io section from row/action declarations, and the spec's log `info` section as a following scroll region; Save
Topology is the first user (`app.py` is ~50 lines). The other four rows reuse it.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Trajectory row: read-only path, `…` opens "Open trajectory" (*.dcd), drop of one existing file | free-text field, no dialog, no drop | read-only path (end shown), `…` opens the same dialog in a sized window, drop routed by type |
| Topology row: same, "Open topology" (*.pdb *.cif *.ent) | free-text field | same as the Qt row |
| 💾 Save topology…: no trajectory → "Open a trajectory first." box; save dialog "Save PDB-file"; cancel logs "Save cancelled"; failure → "Save failed" box | button + free-text Output path; no precondition, no dialog | same precondition text (status line), same dialog (name suggested `<stem>_frame0.pdb`), cancel logged, failure in the window and the log |
| log (info, 120 px) | log lines | scrolling log filling the window, follows new lines |
| synchronous save (window frozen) | synchronous | worker thread, form disabled, "Working…" |
| no help, no guide (allow-listed) | none | `help.md`, `guide.json` (rows and save await presses), Guide/Help buttons |

## 4. Automated evidence

```
after: 9 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_save_topology
compare: exit=0   (lost [] / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json` is empty: nothing lost. Behaviour: a drop routes each file to the row its type matches (the Qt rows each
took a drop on themselves; emtk drops carry no position); errors appear in the window instead of message boxes; the save
runs off the drawing thread.

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_save_topology -q -p no:cacheprovider
21 passed in 24.91s
```

`test_emtk_save_topology_parity.py` (13): the Qt widget runs in a subprocess on the hgbp1 trajectory (464 frames, 5235 atoms)
through its own section (no trajectory, cancelled dialog, save); the emtk save through its dialog writes the same atoms and
coordinates as the Qt file and frame 0 read directly (< 1e-3 Å, PDB precision), with the same log; the precondition and
cancel answers equal the Qt ones; a failed save and a DCD without topology are shown in the window; rows take existing files
from dialogs and drops; worker busy state (animating, second press ignored); guide targets drawn, card drawn, awaits released
by pointer presses on `…` and Save; draws empty/populated at both sizes with the log inside the window; settings round trip
(a moved file is not restored); help page; Qt-free; tooltips.

Deliberate breakage, round 1 (12 faults: picked path ignored, cancel not logged, no precondition, drop routing, browse not
reported to the tour, busy guard, failure swallowed, missing files taken, suggested name, browse tooltip, log not drawn, stale
path restored): all caught. Round 2 (the 12 again + 8: guide names a missing control, save rect not remembered, dialog cancel
ignored, topology filter, not animating while busy, help page missing, status not drawn, topology row dropped): all caught.
"help page missing" first passed because the fault renamed `help.md` to `HELP.md`, which a case-insensitive filesystem still
finds; re-run with a missing name, caught.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`, `after_help_1200x800.png`,
and the Traj Tools hub with the Save Topol panel (embeds unchanged).

## 9. Persistence, guide, help, docs

Paths (only if the file still exists) via `export_settings`. Help and guide new; off the help/guide allow-list. README
corrected (no PyQt5/mdtraj/H5, current steps). Guide 81's Save Topol section still holds.

## 10. Blocked / open

The emtk help window draws `help.md` as raw markdown (known issue, `32c73e41b`; `chisurf/emtk/help_guide.py` is outside the
claim).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10


## 12. Second upgrade pass: real-input click coverage (session TRAJCLICK, 2026-10-02)

Scope of the pass: every control of the Save-Topology tool operated with **simulated pointer and keyboard input and host drops** (not calls to
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
3. **Tour card buttons that do not answer on some steps** (gap 3), not fixable in the plugin: none: no tour button is dead on any of its 5 steps.

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
| Save topology: `Open a trajectory first.`, dialog `Save PDB-file` (`<stem>_frame0.pdb`), Cancel logs `Save cancelled`, typed name + Save writes frame 0 (equal to the DCD's frame 0 within the PDB's 3 decimals), second Save onto it asks first | `test_save_writes_frame_zero_as_the_typed_pdb_and_asks_before_replacing_it` |

### Evidence read at full size

`before_populated.png` (Qt, read again), `before_emtk_populated_*` (first-pass app), `after_populated_{1200x800,800x600}.png`,
`after_dialog_1200x800.png`, `after_guide_800x600.png`, and the click session `after_click_<n>_<what>.png`
(produced by `okf/plugins/emtk-ports/scripts/traj_click_capture.py traj_save_topology`: files chosen through the real dialog, fields typed, arrows
pressed, the save dialog with a typed name, the result in the log, Guide and Help opened). Read one by one at full size (all `after_click_*`, `after_populated_*`, the dialog and the guide shots, `before_*`). In the tour-card shots the
log shows through the card (gap 3: the log's child window paints above it); a text field stays highlighted after a click elsewhere (gap 4);
nothing is clipped at either size.

### Tests (pasted)

```
python -m pytest chisurf/plugins/traj/traj_save_topology -q -p no:cacheprovider
30 passed in 37.14s
```

### Deliberate breakage (twice; each restored byte for byte, the suite green again afterwards)

1. `chisurf/plugins/traj/emtk_tool.py`: the host drop verb declines  ->  FAILED chisurf/plugins/traj/traj_save_topology/test/test_emtk_save_topology_clicks.py::test_dropped_files_fill_the_rows_by_type_and_a_foreign_file_is_answered ; 1 failed, 6 passed in 1.46s
2. `chisurf/plugins/traj/traj_save_topology/view_model.py`: writes frame 1, not frame 0  ->  FAILED chisurf/plugins/traj/traj_save_topology/test/test_emtk_save_topology_clicks.py::test_save_writes_frame_zero_as_the_typed_pdb_and_asks_before_replacing_it ; 1 failed, 7 passed in 1.79s

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

**Accept.** all controls present and operated; no tour button is dead; the only open item is the wheel on spin boxes (this tool has none). The three suites (parity against the Qt tool, click coverage, plugin tests) are green; the strict xfails are the emtk gaps above and flip to failures the day emtk fixes them.
Report: `okf/plugins/emtk-ports/traj_save_topology/REPORT.md`.
