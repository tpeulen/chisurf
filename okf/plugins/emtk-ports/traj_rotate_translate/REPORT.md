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
