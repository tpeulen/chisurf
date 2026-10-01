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
