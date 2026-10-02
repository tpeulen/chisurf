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
