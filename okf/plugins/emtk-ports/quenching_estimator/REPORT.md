# emtk port report - quenching_estimator (backend repaired in part; port BLOCKED on the simulation core)

Agent (Sonnet), 2026-10-02. Verdict: **not accepted, manifest not switched.** The native window exists (reused, see Reuse) and every provable control is tested, but no simulation can run on this machine, so no number can be compared with the Qt tool.

## Backend diagnosis (first step)
Root cause 1 (fixed): `IMP.bff.quenching` was deleted when the PET model moved to C++; QuEst's `_pet()` imported it, so the tool, `quest template`, the form and 3 plugin tests failed with ModuleNotFoundError. Fix in the quest repo (`3e197b9`): the tables are built from the top-level `IMP.bff` functions, the interaction tables are plain mappings (the C++ `ResidueQuenching` objects could not be deep-copied: the form crashed), `quench_radius` NaN <-> None; guardrail `tests/test_pet_chemistry_source.py` (4 tests; breakage run: failed, restored). `4102e50`: the AV import error now names the missing module.
Root cause 2 (NOT fixed, in known-issues.md): a simulation stops at `IMP.bff.av.compute`, and behind it ~15 more removed Python entry points. Needs the port of `quest.core` to the C++ API with a baseline simulation; no baseline exists here. Plugin tests: 14 passed (was 11 passed, 3 failed).

## Qt baseline (populated, hermetic)
`before*.png`, `before.json`, `qt_values.json` (`scripts/capture_qt_populated.py`): the Qt tool builds now; with 148L loaded (chain E, residue 117) Run Simulation ends in the failure status recorded in `qt_values.json`. Quenching table edit, project save and the JSON tab are recorded.

## Native window
`gui/app.py` hosts the Structure Tools QuEst card (`make_app`). Tests (`test/test_emtk_quenching_estimator.py`, 6): builds and draws at 1200x800 / 800x600, Qt-free subprocess, 0 untooltipped controls, structure loading, a typed value reaches the project, Simulate without a structure says why, with one ends in a readable failure (never a crash). Structure Tools tests: 22 passed + 1 new. `compare` exit 0 (16 explained entries in `deliberate.json`: Qt ChiMol viewer texts and data, label renames), qt-free yes.
Defect found and fixed: `CardShell.key` (a string) shadowed `ImApp.key`, so **every typed key on a Structure Tools card (and through the hub) raised TypeError**; renamed `card_key`, test added (breakage run: 2 failed, restored).

## Not done (blocked or time)
Numeric parity and the simulation workflow (blocked, see above); the full control -> real-input table for the card (only Simulate, a typed field and loading are covered here; the card's own suite in structure_tools covers drops, dialogs and tabs); layout tests; `entrypoints.emtk` (not switched); residue picking in a 3D viewer (the Qt ChiMol viewer does not build here either).

## Reuse
Hosted the existing card (`cards/quest.py`, `CardShell`, `quest.view.json`, `ProjectFormModel`, `data_table`, FileDialog, help/tour); no copy. `gui/__init__.py` made lazy (Qt tool import on first use).

## Docs
`docs/guides/80_quenching_estimator.md`: warning, failure listing and Known defects rewritten to the new state, figure regenerated from the native window (`quest_native_failure.png`). Reference page not regenerated.
