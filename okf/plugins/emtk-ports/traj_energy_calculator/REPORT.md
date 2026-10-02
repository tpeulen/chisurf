# emtk port report — `traj_energy_calculator` (swap-candidate upgrade, audit-all row 13; shared with `traj_energy`, row 36)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_energy_calculator` / `chisurf/plugins/traj/potential_energy` (the manifest of `traj_energy` points at the same widget and app) |
| Port type | B → existing emtk app: Qt `PotentialEnergyWidget` = AutoForm on `calculate_potential.view.json` with two Qt custom sections; the stream's hand-drawn emtk app over the shared Qt-free view model |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `3685d96d0` baseline; code commit "traj_energy_calculator: emtk app at parity with the Qt tool"; evidence commit |
| Board | `T-20261001-EMTK1` |

## 1. State at start

Modified `__init__.py`, `manifest.json`, `view_model.py`; untracked `app.py`, `potential_specs.py`, `strings.py`,
`test/capture_native.py`, `test/renders/`, `test/test_native.py` (`pre-upgrade/`). All committed.
**Environment trap:** without `modules/imp-tricks/src` on `PYTHONPATH` the Qt setup section fails to build ("No module named
'IMP.cgmol'") and the Qt grab shows only Stride, the table and Process; every capture here has it on the path.

## 2. Control checklist

| Qt | emtk | Present? |
|---|---|---|
| Trajectory + "…", Topology + "…" (drop supported) | fields + "…" (added) | fixed |
| Potential type combo, per-type parameter editor | combo + parameters from `potential_specs` | yes |
| H-Bond / Iso-UNRES / Miyazawa-Jernigan potential file + "…" | added with the bundled defaults (`test_potential_files_match_the_qt_editors`) | fixed |
| Weight, Add | same | yes |
| Stride | same | yes |
| Added potentials table (double-click removes) | table with a remove button per row | yes (deliberate: button instead of double-click) |
| Process (asks for the output file) + progress bar | Output field + "…", Process (asks when empty), worker + frame counter | fixed (was blocking, no progress) |
| Log | Log | yes |

Energies (`scripts/capture_populated.py`, the tests' synthetic peptide, Radius of Gyration ×1 + Clash ×0.5): both write
`FrameNbr Radius-Gyration Clash-Potential` with frame 1 = 5.188, 0.776; `test_process_writes_the_qt_tools_energies` compares the
whole file byte for byte.

## 4. Automated evidence

```
after: 23 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_energy_calculator
compare: exit=0   (explained: 'cutoff', 'ca', 'h' -- the Qt H-Bond editor's split labels, emtk 'Cutoff CA' / 'Cutoff H')
```

## 6. Tests

```
$ python -m pytest chisurf/plugins/traj/potential_energy -q -p no:cacheprovider
28 passed in 18.54s
```

`test_emtk_traj_energy_parity.py` (7): energies vs the Qt widget, file defaults vs the Qt editors' fields, browse and the "…"
buttons, draws at both sizes, Qt-free, tooltips. Deliberate breakage: no progress callback → energies test failed
(`0 >= 1`); MJ default switched to hb.npy → file test failed (`AssertionError: Miyazawa-Jernigan`). Restored.

## 7. Screenshots read

`before.png` (Qt, empty), `before_populated.png`, `before_emtk_populated_*`, `after_populated_1200x800.png`, `after_populated_800x600.png`
(file buttons, H-Bond potential file, table, log). Nothing clipped.

## 9. Persistence, guide, help, docs

`export_settings` (stream's): files, stride, weight, selected type, editor values, output. Guide/help: none in Qt or emtk (traj tools
are outside the help allow-list check here). Docs: none.

## 10. Blocked / open

* **AV-Potential cannot be scored on either side** (pre-existing): the core `AvPotential(distances, positions, av_samples, min_av)`
  is not what the Qt widget (never calls its `__init__`) or the emtk spec (passes `structure`, `labeling_file`) construct;
  emtk raises `TypeError: AvPotential.__init__() got an unexpected keyword argument 'structure'`.
* H-Bond, Iso-UNRES, MJ, Go, ASA need residue data a bare DCD+PDB peptide lacks (`Structure has no attribute 'l_res' / 'dist_ca'`),
  in Qt and emtk alike.
* The emtk form is hand-drawn (the parameter editor is dynamic per type; the table could be a `data_table`).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [ ] D7 none in Qt · [x] D8 · [x] D9 · [x] D10

## Addendum (session TRAJCLICK, 2026-10-02): the emtk app was rebuilt

Operating this app with real input (`okf/plugins/emtk-ports/traj_energy/REPORT.md`) found that the hand-drawn window this report accepted had drag-only number fields, a hand-drawn
table, editable path rows, no drop hook, and no Help or Guide. `chisurf/plugins/traj/potential_energy/app.py` is now drawn from the Qt spec by the shared trajectory-tool app
(commit `6bb3d7be9`); the evidence here (`after*`, `compare.json`) was regenerated against it (`compare` exit 0). Where this report describes the old window (its table, `Output` field,
`-` buttons, locale-aware headings) the traj_energy report is the current one.
