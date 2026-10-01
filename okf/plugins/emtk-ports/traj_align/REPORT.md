# emtk port report — `traj_align` (upgrade, audit-all row 38)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_align` / `chisurf/plugins/traj/traj_align` |
| Port type | A+B: the Qt `AlignTrajectoryWidget` (AutoForm over `align_trajectory.view.json`: custom `traj_align_io` section with trajectory + topology rows and the save button, `atom_selection`, `stride`, info log) over `AlignTrajectoryViewModel`; the stream's hand-drawn emtk `app.py` over the same view model |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `87c0f7a8d` baseline; `388a75722` emtk app at parity with the Qt tool; evidence commit "traj_align: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py` (lazy Qt import), `manifest.json` (emtk entrypoint),
`view_model.py` (`log_text()`); untracked `app.py`, `strings.py`. Tracked edits committed with the app; `app.py` rewritten,
`strings.py` dropped (copies in `pre-upgrade/`). Qt `widget.py`/`sections.py` unchanged (= HEAD).

## 2. Built on the shared trajectory-tool app

`chisurf/plugins/traj/emtk_tool.py` (introduced with traj_save_topology, `2cb97ce87`): `app.py` declares the two rows and
the action; the spec's fields draw through `draw_form`. `SaveAction` gained `failure`, the caption of a failed run, because the
Qt section titles this tool's error box "Align failed".

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Trajectory / Topology rows: read-only, `…` dialogs (*.dcd / *.pdb *.cif *.ent), drop on a row | free-text fields, no dialogs, no drop | read-only rows, same dialogs in a sized window, drop routed by type |
| 💾 Save aligned…: "Open a trajectory first."; dialog "Save aligned trajectory" (DCD); cancel logs "Save cancelled"; error box "Align failed" | button + free-text Output; no precondition, no dialog | same precondition, same dialog (`<stem>_aligned.dcd` suggested), cancel logged, "Align failed: …" in the window |
| Atom selection (multi-line text, placeholder), Stride (spin 1–999999) | text, int stepper | the spec's fields via draw_form (single-line text with placeholder, int field with the spec bounds), descriptions as tooltips |
| log (info, 100 px) | log lines | scrolling log filling the window |
| synchronous alignment | synchronous | worker thread, form disabled, "Working…" |
| no help, no guide (allow-listed) | none | `help.md`, `guide.json` (7 steps; rows and save await presses) |

## 4. Automated evidence

```
after: 14 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_align
compare: exit=0   (lost [] / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json` is empty: nothing lost. Atom selection is a single-line field (the Qt AutoForm drew a multi-line box for
a comma list). Drops route by file type; errors in the window instead of message boxes; the alignment runs off the drawing
thread.

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_align -q -p no:cacheprovider
27 passed in 34.84s
```

`test_emtk_align_parity.py` (11): the Qt widget in a subprocess (nothing chosen, cancelled dialog, save, a selection that is
not ids, an unwritable target) on hgbp1 with atoms 0–3 at stride 4; the emtk save writes 116 frames equal to the Qt file
(1e-4 Å) and to `superpose` done in the test (1e-3 Å), and the frames did move (> 1 Å); same precondition, cancel and
selection messages; "Align failed" caption; spec fields drawn with their descriptions, an edit reaches the model and the
settings; busy state with a second press ignored; guide targets drawn, awaits released by presses on Topology `…` and Save;
draws at both sizes; settings round trip; help page; Qt-free; tooltips.

Deliberate breakage, round 1 (12: fitting set ignored, failure caption lost, suggested name, save filter, spec fields not
persisted / not restored, cancel not logged, no precondition, form not drawn while idle, guide stride step points nowhere,
browse not told to the tour, not animating): all caught. Round 2 (12 base faults from traj_save_topology): "busy guard
removed" and "help page missing" passed at first — this suite had no second press and no help check (the save_topology suite
did); both added, all 12 caught.

The reference test first failed for the wrong reason: `superpose` works in place, so the "source" it compared against had
already been aligned (moved 0.0 Å); the source is now read separately.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`.

## 9. Persistence, guide, help, docs

Paths (if still present), atom selection and stride via `export_settings`. Help and guide new; off the allow-list. README
corrected. Guide 81's Align section still holds.

## 10. Blocked / open

none for this plugin. The emtk help window's raw markdown (known issue `32c73e41b`) applies here too. The window caption is
now the spec panel's title ("Align trajectory"); the stream's Traj Tools hub test finds panels by it, and traj_save_topology
was aligned to the same rule (`e77b020f0`).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
