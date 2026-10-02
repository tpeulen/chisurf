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
