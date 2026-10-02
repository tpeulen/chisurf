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
