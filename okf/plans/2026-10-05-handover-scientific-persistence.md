# Handover — ChiSurf scientific session persistence (2026-10-05)

## Goal

Repair ChiSurf project/session persistence so that:

- canonical validated v5 snapshots and atomic `.cs.pto` save/restore are the only
  persistence path; runtime/Qt objects are never serialized;
- destructive transitions use Save / Don't Save / Cancel, and Save must succeed
  before continuing (cancellation/failure preserves exact state);
- real MMFDB is used only when genuinely authenticated; fake/local/bootstrap
  MMFDB falls back to `.cs.pto`;
- Qt editors are migrated to declarative AutoForm/plain serializable state
  (no legacy model-widget support needed), enhanced where a model does not fit
  AutoForm yet;
- the whole thing is **proven** for all **42 configured scientific models in 11
  families**: real editing through generated GUI controls, scientific
  recomputation, persistence round-trip, ownership/identity, and real Main GUI
  rendering — via the actual-Main probe
  (`test/gui/scientific_document_gui_probe.py` driving
  `test/gui/test_all_model_document_gui.py`).

User constraints quoted:
> not all mdls may fit into autoform, if needed enhance autoform
> the mdls that are qt should be migrated to autoform, so that they serialize, no need to support old models.
> when migrating, take before and after screenshots, to make sure still works!
> so you are not done. I think you can do it, cant be too hard to save a session.

Discipline: shared working tree, **no** git-changing operations; TDD — RED
focused regression before each fix, then GREEN, then real re-verification;
preserve first-failure artifacts.

## What was done (cumulative, verified)

Persistence core (prior sessions):
- Canonical storage / PTO / HTTP validation: 33/33.
- Scientific catalogue roundtrip: 85/85 (42 science + 43 inventory).
- AutoForm migration baseline: 42 entries, 196 before-screenshots.
- Fixes, each with focused regression: `RateMatrixBinding`, display bindings
  (`model_scalar` / `computed_output` / `data_metadata`), semantic canonical
  IDs, grouped TCSPC restore ordering, GeneralFCS ownership + direct-widget
  discovery, TCSPC indices 00–12 (13/13), ParseDecay conditional `dt`,
  MaxEnt absent-`background_pattern` guard, PDA Gaussian `finalize()`
  delegation (raw amplitudes stay inputs; normalization is projection only),
  SAW `repr(value)` precision, acceptor-density `donor_lifetime_spectrum`.

GUI-child lifetime (earlier in this arc):
- ParseFCS-class SIGBUS: GUI children completed every stage (`phase: complete`)
  then died in interpreter teardown. Fixed by `_shutdown_qt_process(report)`
  (pyqtgraph `cleanup()` + processEvents) and `_exit_after_report(report)`
  (`os._exit(0)`) for completed non-package children. ParseFCS 3/3 stable;
  cross-family reruns green. Regression:
  `test/gui/test_scientific_document_gui_probe_lifetime.py` (2 passed).

This session:
1. **GlobalFit global ports in the parameter network.** `session_owners()` in
   `chisurf/core/fitting/parameter_network.py` skipped the aggregate
   `GlobalFitModel` (to avoid double-listing members) and with it the model's
   own declared global ports (`shared rate`). RED
   `test/gui/test_globalfit_parameter_network_ports.py`, then fix: emit an
   owner carrying exactly `get_session_parameters()` when the skipped
   aggregate declares ports. Global View table then enumerates 21 rows
   including `shared rate`. 2 passed.
2. **ForeignTableProxy unwrap in the probe.** ChiTableWidget fronts
   `GlobalParameterTableModel` with a `QSortFilterProxyModel`; both
   `_editor_bindings` and `_edit_control` `isinstance`-checked the source
   model directly and saw 0 cells. Fix: unwrap `sourceModel()` for inventory;
   in `_edit_control`, map source→proxy with `mapFromSource` before
   `scrollTo/setCurrentIndex/edit`. Result: **GlobalFitModel actual-Main
   PASSED (85.74s)**; report shows the edit committed through the real table
   delegate (`shared rate`, row 10, `ScientificDoubleSpinBox`, typed 0.708,
   model recomputed, `phase: complete`). Focused suites 8 passed.
3. **Matrix expansion.** Six TCSPC rows re-verified under the exit contract —
   `tcspc_fret_discrete`, `tcspc_fret_worm_like_chain`, `tcspc_fret_ising_chain`,
   `ParseDecayModel`, `FRETStructure`, `tcspc_maxent_fret` — 6 passed in
   409.38s. **`ParameterTransformModel` PASSED** (146.69s run, 1 failed =
   ProteinMC only). **Matrix receipt: 41/42.**
4. **ProteinMC (row 42) — root-caused and instrumented, one fix from green.**
   Producer's scientific edit is the structure coordinate shift (residue-86 CA
   x +0.1 Å), persisted as adapter state, not a `FittingParameter`; the only
   changed parameter is the `47-86` distance **output** (`is_output: True`,
   correctly excluded by the probe's diff), so `changes == []` and the probe
   aborted. Verified numerically (36.87740413200943 → 36.9027713801158).
   - Model-level contract pinned first (RED→GREEN):
     `test/gui/test_proteinmc_structure_control_contract.py` (3 passed): a
     shifted single-model PDB committed via `setattr(structure_file)` +
     `load_starting_structure()` resets the trajectory, recomputes the
     declared distance outputs from the file coordinates, and is
     deterministic. PDB round-trip fidelity ~1e-7 Å.
   - Probe extended (RED contract tests → implemented):
     `test/gui/test_proteinmc_structural_probe_contract.py` +
     `test_structural_coordinates_extractor.py`. New helpers in the probe:
     `_structural_coordinates(state)` (reads `adapter_state.proteinmc`
     structure coordinates from the atoms-field array adapter, with a plain
     `xyz` fallback), `_structural_edit(first, second)` (detects a
     coordinate-only adapter edit, returns `(member_uid, coordinates)`), and
     `_edit_structural_control(main, app, structural, directory)` (writes the
     archive's exact coordinates as a single-model PDB into the report
     directory and commits it through the **real** Structure `QLineEdit`:
     paste + Return → `editingFinished` → `_commit_file` →
     `load_starting_structure` → distances recomputed). `run()` now branches:
     one changed parameter → `_edit_control`; else structural edit →
     `_edit_structural_control`.

## What was touched (files)

Product code:
- `chisurf/core/fitting/parameter_network.py` — `session_owners` emits the
  aggregate's declared global ports as their own owner (single change).

Test infrastructure (untracked, shared):
- `test/gui/scientific_document_gui_probe.py` — added `import numpy as np`;
  proxy unwrap in `_editor_bindings` + `_edit_control` (with
  `mapFromSource` view-index mapping); `_structural_coordinates`,
  `_structural_edit`, `_edit_structural_control`; branch in `run()`;
  (earlier in arc: `_shutdown_qt_process`, `_exit_after_report`, wiring).
- `test/gui/test_globalfit_parameter_network_ports.py` (new, 2 tests).
- `test/gui/test_proteinmc_structure_control_contract.py` (new, 3 tests).
- `test/gui/test_proteinmc_structural_probe_contract.py` (new, 2 tests).
- `test/gui/test_structural_coordinates_extractor.py` (new, 2 tests).
- `test/gui/test_scientific_document_gui_probe_lifetime.py` (new, 2 tests,
  earlier in arc).

Docs:
- `okf/plans/2026-10-04-full-scientific-session-history.md` — **stale**
  (says 22/42); needs a 41/42 checkpoint once ProteinMC lands.

Untouched on purpose: shared dirty-worktree files listed in the prior session
(`chisurf/core/models/description.py` etc.) — preserved, not reverted.

## Current state / next steps (exact)

Matrix: **41/42 actual-Main rows individually verified green.** Remaining:

1. **One-line bug** (diagnosed by direct trace): `_structural_edit` calls
   `_structural_coordinates(state_first.get(key) or {})` — but the extractor
   expects the **wrapper** `{"proteinmc": payload}` and receives the payload,
   so it returns `None`. Fix at the two call sites: pass
   `{key: state_first.get(key) or {}}` / `{key: state_second.get(key) or {}}`
   (or unwrap inside the extractor). Then re-run
   `test_structural_coordinates_extractor.py` +
   `test_proteinmc_structural_probe_contract.py` (expect 4 passed).
2. **Exact-equality caveat for the structural path:** PDB text stores ~1e-7
   precision, so after the GUI commits the shifted PDB, coordinates/distances
   differ from the archive's full-precision values at ~1e-8. `run()` asserts
   `changed == expected_second["observables"]` exactly — this will fail for
   ProteinMC. Decide and implement a bounded comparison for structural edits
   (e.g. exact for parameters, `numpy.allclose(rtol=1e-6, atol=1e-6)` for
   coordinate-derived observables), documented in the probe.
3. Re-run `test_all_model_document_gui.py -k ProteinMCModel` → expect green.
4. Update `okf/plans/2026-10-04-full-scientific-session-history.md` with the
   42/42 checkpoint (durations, the GlobalFit proxy fix, the ProteinMC
   structural-edit contract, the ParseFCS exit contract).
5. **Strict full-42 aggregate run** (`test_all_model_document_gui.py`, no
   `-k`) — individual successes are not full acceptance. (~90 min.)
6. Remaining SPEC acceptance gaps (from earlier audit, unchanged): ProteinMC
   disk-load assertions omit model type/sampling controls/fit-range checks;
   file-load actions don't prove success-only identity publication after
   transactional failure; failed-save tests don't prove injected save-fault
   reachability.
7. Post-fix screenshot catalogue: spot-review before/edited pairs for the
   newly passing rows (GlobalFit pair verified; DEER/DyeShape/others pending
   visual review).

Known non-blocking warnings: numba "cannot cache function 'advective_flux'"
(imp-tricks); historical transients (one Pda2cSawNu exit 1 rerun-pass; one
rich-control exit 139 rerun-pass) — root cause unknown, do not claim fixed.

## Environment

```text
cd /Users/tpeulen/dev/chisurf
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=.:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:modules/chimol
NUMBA_CACHE_DIR=/Users/tpeulen/.hermes/cache/scratch/chisurf-project-numba
Python=/Users/tpeulen/mambaforge/envs/arm64/bin/python
pytest -p no:cov -o addopts=''
```

Run one row: `... -m pytest -q test/gui/test_all_model_document_gui.py -k
'<ConfiguredPath>' -p no:cov -o addopts=''` (~70–150 s each). Artifacts per
row land in `pytest-of-tpeulen/pytest-*/test_configured_model_actual_m0`
(reports `science-producer/canonical/restored/...-report.json`, PNGs).

## Continuation — 2026-10-05 (claude)

Handover steps 1–3 closed; **ProteinMC actual-Main row PASSED** (104.8 s) →
42/42 rows individually green. Getting there exposed three *product* defects,
each hidden by a `try/except` or by a test that did not do what it claimed:

1. **ProteinMC editor controls never worked.** `_BoundControlMixin._commit`
   calls a view's `call` *with the committed value*; `load_starting_structure`,
   `on_labeling_file_changed` and `reload_distances` took no argument, so the
   Structure, Labelling and Score-set controls raised `TypeError` inside the
   commit's `try` and only logged a warning. The model-level contract test's
   helper claimed to be "exactly what the AutoForm control does" but called the
   method without the value. Fix: `_value: Any = None` on all three; guard
   `test_view_calls_accept_the_committed_value` binds every value/choice
   `call` in `proteinmc.view.json` against the model.
2. **Loading a starting structure left the persisted starting structure stale.**
   `load_starting_structure` replaced only `proteinmc_structure` (sampler
   state); `structure` — what the archive persists beside `structure_source` —
   kept the old coordinates. Now it sets `structure` to the loaded file and
   `proteinmc_structure` to a copy.
3. **ProteinMC plots could not draw a restored project.** Both the 3D Structure
   plot and the Distance Network required a *sampled* `proteinmc_structure`
   (restored unsampled project → empty view / "No FPS network data"), and the
   network re-read the labelling JSON from its original path instead of the
   archived `labeling_payload` (the probe's source-reread guard caught it after
   the edit). Now both fall back to the starting structure, the network reads
   the model's payload first, and the 3D plot replaces its object when the
   structure object changes. Regression:
   `test/gui/test_proteinmc_network_restores_from_archive.py` (labelling file
   deleted before drawing). Verified visually: chimol `renderer.grab_image`
   shows T4L from the archive alone; network draws the 47–86 edge.

Probe changes (`test/gui/scientific_document_gui_probe.py`):
- `_structural_edit` passes the `{key: payload}` wrapper to the extractor and
  compares models by `_model_inputs` (output-parameter *values* excluded — the
  real archives differ only in the recomputed `47-86` output).
- Structural path compares with `_observables_close` (rtol=atol=1e-6; keys,
  lengths, types exact) because the edit travels through PDB text. The
  reference archive is `_structural_reference`: `structure_source` and the
  structure's `filename` become the committed PDB, `current_structure` the
  loaded copy, and the two loaded structures' fresh object `uid`s are adopted
  from the live capture (`_adopt_loaded_structure_identities`), so the
  save→readback still checks they persist. Scalar-port rows keep exact `==`.
- `gui-edited-expected.json` for a structural edit holds the observables the
  GUI produced; the reopened file must match those exactly.
- New tests: `test_structural_observables_tolerance.py` (3),
  `test_proteinmc_structural_probe_contract.py` +1 (output values don't mask a
  structural edit; input changes do).

Known capture gap: Qt `widget.grab()` cannot capture chimol's GPU surface, so
every actual-Main "Structure" tab PNG is black. Use the viewer's
`renderer.grab_image(chrome=False)` when judging 3D tabs.

Not committed: per this arc's "no git-changing operations" discipline, and
because the `proteinmc_model.py` hunks interleave with earlier uncommitted
persistence work.

**Strict full-42 aggregate: 42 passed / 0 failed** (2757 s), after fixing the
environment at its root: `build-tttrlib` now builds sibling envs for real (no
symlinks into pixi's purgeable rattler cache), emtk `f2e051e` (`set_text` is a
load). Open: visual review of late-green rows, the three SPEC acceptance gaps,
and the commit (see project-persistence "Where to pick this up").
