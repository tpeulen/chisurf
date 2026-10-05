# Full scientific session and history acceptance plan

> **For Hermes:** Execute the disjoint workstreams with strict TDD and independent specification review before quality review. Preserve shared work; no git mutation/commit/push.

**Goal:** Project save/load and history navigation work for every shipped experiment/model and complete edited scientific state, including dependencies across fits and GUI model state.

**Architecture:** Canonical typed owner snapshot defines scientific state and resources. Dataset/model codecs explicitly preserve scientific configuration and UID references, not arbitrary object namespaces. History must record/reconstruct document-owned operations without rereading missing sources, changing scientific UIDs, leaking locks/widgets, or mutating the live session before validated publication. GUI is a view of the restored model; history cursor publication follows successful science/presentation acknowledgement.

**Current evidence (not acceptance):** On October 4 the actual shipped YAML resolves 11 experiment families and 42 configured model entries. Full prior project/server/agent regression 1041 pass/2 pre-existing generic skips. `test/history` baseline 91 passes. Parent nevertheless reproduced checkpoint-only history wiping navigation to empty, external caller mutating a stored event through `list_events`, and `validate_event(7)` raising AttributeError. Existing project history fields alone are not a functioning history system.

## AutoForm migration and before/after visual gate — October 4, 2026

The user requires remaining Qt model interfaces to be replaced by AutoForm; do not retain old model/widget compatibility or serialize widgets. Inventory configured compute classes and actual renderer paths separately: a Qt-free compute class does not by itself establish complete serializable configuration. Keep the shared model/document snapshot authoritative.

### Portability constraint — AutoForm now, emtk later

The user's clarification is binding: this port must stay in AutoForm and remain easy to migrate to emtk later; it is **not** an instruction to replace the current AutoForm renderer with emtk in this task. Reuse the existing renderer and data-spec machinery. Do not build a parallel UI framework, a model-specific Qt widget, or a new backend abstraction merely for a future migration.

- Keep scientific configuration, validation, computation and model actions in Qt-free objects. Persist explicit data, stable identities and declarative configuration, never Qt signals, slots, item/index objects, connections, closures or widget instances.
- Declare ordinary fields, selectors, component/parameter tables, actions and help through existing AutoForm spec constructs. Bind actions to model methods and fields to stable data paths; keep behavior out of Qt event handlers and presentation callbacks.
- Represent presentation state as plain data keyed by stable model/view identities. Use the same state and action semantics when a later renderer consumes the spec; do not make Qt object names or layout introspection the model/configuration schema.
- Prefer existing sections, but do not force a model into AutoForm's current capabilities. When a required interaction is not expressible, enhance the existing AutoForm spec, binding or section machinery with the smallest capability needed. Reuse the enhancement across models where appropriate; a legitimate scientific viewer/editor may remain a named custom section with a toolkit-neutral data/action/state contract. Do not simplify scientific behavior, omit controls or flatten a necessary editor into inert labels merely to fit a form, and do not grow a parallel Qt-only surface.
- Ground each enhancement in a concrete missing interaction and a red-capable regression before implementation. Test the declarative/binding/state contract independently of toolkit rendering, then exercise the actual renderer with real inputs and matched before/after captures. Keep computation in the model, rendering in the section, and persistence in the shared document contract; do not add a model-specific serializer as an AutoForm workaround.
- Preserve the existing before/after visual, interaction, numerical and fresh-file gates. Keeping an existing Qt AutoForm renderer is allowed for this port and does not imply that a native emtk migration has been completed.


Before modifying or deleting an affected interface, capture its actual current implementation with legitimate data, non-default model configuration, parameter values, selected modes and visited tabs. Preserve source hashes, model/configuration identity, scientific predictions, control inventory and the exact capture command beside the images. A screenshot of an already migrated replacement is not a recoverable legacy baseline.

For each migration, capture matched `before` and `after` images at both normal and constrained viewport sizes, resizing the same instance after opening stateful controls. Inspect both images directly. Confirm every previous control remains present and reachable (including controls moved into tables), plots are nonblank and correct, and labels, dialogs and tabs are not clipped or overlapped. Record deliberate layout changes; pixel similarity is not acceptance. Exercise interactions and assert numerical, dependency and fresh-process serialization parity separately.

A model row stays pending until its required pairs, direct visual review, interaction tests and canonical-state round-trip pass. Do not infer acceptance from empty Qt control inventories on embedded emtk surfaces, constructor success, view-spec availability or a screenshot saved but not inspected. Preserve historical failed evidence. No staging, commits, push, reset, stash, checkout or clean.

## Rich-editor tracer bullet — live matrix binding

Concrete interaction to reproduce: a rate changes through a live parameter/dependency after the grid was drawn; editing a different cell must not write the stale displayed rate back. The existing widget commits every cell's cached value. Use the existing `rate_matrix` section rather than omitting the scientific editor or building a second UI framework.

1. Add `test/gui/test_rate_matrix_live_binding.py` against the real rate group; capture before renders at 620×900 and 360×600 before the production edit and run the focused regression RED. Preserve rates, parameter identities, fixed flags, links and the exact changed cell.
2. Add Qt-free data/action tests in `test/core/test_rate_matrix_binding.py`; implement `chisurf/core/dataspec/rate_binding.py` for stable dotted-path read/one-cell commit, with dimension/index/finite-value rejection before mutation. No matrix arithmetic, scientific formulas or serialization changes.
3. Bind the existing `rate_matrix_section.py` value-change handler to that one-cell action, re-read current live values instead of cached whole-grid values, and refresh existing controls without causing new edits. Keep add/resize/fixed/link/detail behavior; do not edit performance-owned AutoForm renderer/model_editor/metadata/chiplot.
4. Rerun existing rate-matrix tests, inspect matched before/after captures, and exercise the real four-state FCS/PDA scheme including predictions and canonical `.cs.pto` fresh-process state. Capture remains data-only; the binding object and widgets are never archive contents.
5. Independent narrow specification PASS before quality review; update docs/OKF. A shared-section improvement does not close the 42 model/application acceptance rows. No staging, commits, push, reset, stash, checkout or clean.

## Shared rich-control acceptance probe — October 4, 2026

The rate-matrix enhancement now has parent 25/25 unique focused passes (12 core + 8 live-GUI/scientific + 5 existing renderer), exact current five-file hashes, narrow independent SPEC PASS followed by independent quality PASS, and directly inspected before/after normal/constrained pairs. Parent receipt: `scratch/autoform-migration-20261004/rate-binding/parent-accepted-evidence.json`. This is shared-editor acceptance only, not a whole-model row. Expanded 67-case selection is 66 passed/1 failed at unrelated duplicate `api_key` declarations in the existing AI-settings spec; do not label that whole selection green.

The current real Main FCS kinetics node reaches canonical and before publication/save/science phases, but its shared probe assumes every scientific parameter is a generated editable table. It fails to recognize a real `RateMatrixWidget` input. Fix the shared test contract rather than adding a per-model table, changing the producer's edited parameter, assigning science directly or weakening canonical prediction/save checks:

1. Parent real measured-FCS rich-control tests in `test/gui/test_scientific_document_rich_controls.py` first ran RED (2 expected failures) against the existing table-only helpers.
2. Extend `_editor_bindings` and `_edit_control` in `test/gui/scientific_document_gui_probe.py` generically for the existing `rate_matrix` section; address exact bound parameter objects and UIDs. Record display versus scientific values separately, preserve table coverage and reject foreign/disabled/linked/output or unrepresentable inputs.
3. Enter the requested value through the real live control with keyboard/Return and existing MDI/dock/section ancestry, never detach/reconstruct or directly invoke scientific setters/update. Require changed measured predictions/modes; strengthen wrong-owner rejection with a separate regression.
4. Parent rerun focused tests, actual model-31 ordinary Main six-stage file lifecycle, matched images and diagnostics; no `phase=complete` or child self-report substitutes for assertions/readbacks.
5. Independent SPEC before quality for the shared probe changes; keep all 42 full model rows pending until modes/history/backend/full presentation gates independently pass. No production formula, persistence or unrelated renderer edits and no Git mutation.

## Architectural constraint — shared implementation, catalogue-wide tests

The user's correction is binding: model entries are acceptance cases, not separate persistence implementations. Keep `capture_session`/`restore_session` as the one canonical scientific graph codec and `OwnerTransaction` as the one publication/rollback boundary. Close view capture at the shared macro/API/server document boundary using explicit GUI view hooks. No additional per-model save/load branches or edits to scientific formulas, model-specific serializers, or model-specific persistence workarounds.

Immediate RED→GREEN slice:

1. Make the production in-process dispatcher fixture register the snapshot services, then reproduce missing real view state and ignored capture faults through both local and proxy owners.
2. Capture client-owned presentation before any snapshot RPC or write, carry it into the authoritative snapshot without replacing server-owned selection/history/resources, and use the same core codec. Touch only `get_project_payload`, API `capture_project`, server capture entrypoints, and the shared UI capture function if selection is absent there.
3. Verify exact local/proxy file readback, original destination preservation at a reached capture fault, and detached presentation data. Add equivalent API and malformed-response checks one tracer bullet at a time.
4. Rerun the unchanged scientific catalogue and real-Main catalogue harness. All 42 entries remain pending for application acceptance until their common tests pass; no model-specific bypasses, graph repackaging or skips.
5. Obtain independent specification review before quality review. Preserve all historical failed evidence and distinguish current results; no staging, commits, push, reset, stash, checkout, clean or unrelated edits.

## Scope/coordination

- Existing owner-boundary worker proc_3e23185ef2f0 owns transition/API/server/project macro/Main view publication/resource guard sections. It must retain Save/Don't Save/Cancel and resource fixes.
- New scientific catalogue lane owns session codec and model state adapters, scoped scientific tests. No transition, history, macros, Main or documents.
- New history lane owns history package and HistoryMixin/history browser sections of main_helper/widgets only; no session codec or Main/macros/transition. Coordinate explicit needed integration seam in scratch before touching a peer file.
- Parent owns this plan, manifest/checklists, board/docs, cross-lane integration and actual reruns. CLI child evidence is a self-report, not approval.

## Current integrated history result — October 4

The expanded history/document/Qt/owner selection (`test/history`, `test/gui/test_history_document_gui.py`, `test/project/test_document_history_persistence.py`, transport, owner rollback and authoritative transition tests) now passes **202 tests with zero failures/errors/skips** in `chisurf-parent-history-notification-green.xml`. New RED/GREEN regressions prove full ordinary macro/server/local API capture; fresh original-source-deleted redo/recompute/resave; installed runtime history and lock identity; no tentative import notification; one committed notification; and failed controller subscription rollback by identity. OwnerTransaction validates the complete typed envelope against the concrete owner and restores data only, not runtime locks/callbacks/module namespaces. History module access resolves an explicitly installed owner without changing its module namespace. This is an integration revision gate, **not** independent specification/quality or whole-feature acceptance. Separate-process GUI/server history and all-model/real-DB acceptance remain open.

Science completion is continuing in disjoint session/model-codec/scientific-fixture and portable-dye-reference lanes. Parent `chisurf-parent-current-full-catalogue.xml` now independently records **85 cases: 75 passed, 10 failed, zero errors/skips**, wrapper elapsed 471.9 seconds; this is **43 inventory checks plus 32/42 scientific round-trips**, not 75 scientific models. Remaining failures at that run: FRETStructure source-deleted prediction becomes zero; TCSPC MaxEnt lifetime and DEER MaxEnt each exceed the 90-second per-entry bound; DyeShapeFCSModel cannot restore without MMFDB; both ICS configured modes change fixed flags; MFD three-state topology restores 14 instead of 20 parameters; ProteinMC structural dataset is unsupported; GlobalFit duplicates member parameter ownership; ParameterTransform graph registration calls the wrong native add_node signature. These precede the two continuing completion workers and must be rerun against their final source. Do not convert failures into skips or default-only acceptance. Parent also owns a separate test-only all-model GUI acceptance lane; science and GUI pass counts remain separate.

## Completed-lane integration checkpoint — October 4, 2026

The four scientific-completion, legacy-test-migration, initial all-model and actual-Main GUI processes have completed; they are no longer active lanes. Parent parsed their final artifacts rather than treating exit 0 as acceptance. `scientific-completion-matrix-final.xml` has **85 passed / zero failures/errors/skips: 42 scientific file loops plus 43 inventory checks**. Its 42 passing exercised configurations supersede the earlier 32/42 file result and bounded MaxEnt timeouts. `scientific-completion-focused-final.xml` has **164 passed**, zero failures/errors/skips. These are retained worker execution results, not a new parent full-catalogue rerun or every-mode approval.

Actual-Main final JUnit `chisurf-all-model-gui-final.xml` has **zero passes / 42 failures / zero errors/skips**, although all 42 scientific producers passed. Canonical Main failures: 20 native node-arity errors, 21 single-Fit iteration errors, one GeneralFCS registry KeyError. Graph-preserving packaging passed 34 and failed eight exact reconstructions; packaged Main then failed 12 native publications, 20 plot-set checks, one registry lookup and one ProteinMC GUI-state save. No final full GUI edit/save/fresh-reload case completed. Parent inspected both PDA control captures: bg0=0.001 is visible but the scientific subwindow is blank. All selectable mode combinations and structural visualizations remain open.

Fresh parent `chisurf-parent-four-lane-readback.xml` executes the three scientific native-identity tests, then all UID tests with an existing native graph, then the six migrated legacy test files: **36 passed / 13 failed / zero errors/skips**, wrapper 35.43 seconds. Native/UID subset: **8 passed / 9 failed**; migrated subset: **28 passed / 4 failed**. Compared source/test hashes are unchanged across this run. The earlier migration missing-session.py collection blocker is historical: session.py exists and collection now succeeds.

Immediate revision fronts, without relaxing validation or identities:

1. Repair the installed native map contract throughout owner publication/retirement/rollback: get_nodes iterates UID keys, and add_node requires UID plus node. The red-capable test order is scientific native identity before UID tests in the same process; UID-only clean-process green misses the defect. Preserve unrelated/concurrent mappings.
2. Handle canonical single Fit and FitGroup at the actual GUI presentation boundary without scientific graph repackaging; exercise normal ChiSurfAPI/Main load.
3. Decouple ordinary plot construction from optional MMFDB metadata-dictionary imports and propagate registration failures rather than silently returning zero plots; require every declared plot and inspect normal/constrained captures.
4. Resolve GeneralFCS declared-parameter registry publication, eight exact grouped reconstruction failures, ProteinMC omitted fit_windows and actual coordinate-control/structural rendering coverage.
5. Repair the remaining migration fixtures: one non-structured ProteinMC atom table and one dummy GUI lacking the owner guard; the other two migrated failures hit the native owner defect. Preserve actual scientific data and fault reachability.
6. Close the independent reset-review assertion gaps, all-model history/server/MMFDB integration, independent SPEC PASS and subsequent quality approval.

Machine-readable evidence with exact command, failures and before/after hashes: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-four-lane-batch-evidence.json`. Keep every full model acceptance row open.

## Delayed UI-review/history-owner integration checkpoint — October 4, 2026

Both handoffs are complete. Current-tree parent execution of their seven-file union is **111 passed / 1 failed / zero errors/skips**, wrapper 26.97 seconds, with compared source/test hashes unchanged. Four history/owner/reset files account for **67 passes**; three lifecycle/action files account for **44 passes / 1 failure**. The failing action-load fixture binds a GUI lacking the concrete transition guard; retain authorization and repair the real fixture.

Separate canonical real Main `[reset]`: **1 failure**, wrapper 16.74 seconds. The class-level `adopt` fault injection correction is already present. Execution fails at native graph insertion during load before the reset fault is reached; repair native publication first, then rerun and require the exact reset fault and complete rollback assertions. Do not substitute the historical scratch reset pass for this failed canonical test.

Historical worker results remain recorded: UI focused 45 passes with broader legacy browser 13 passes/2 failures; history 67 integrated passes, four isolated native plot cases and native ranges pass. The forced-child combined native attempt exited -11 without complete XML. Browser failure attribution and isolated successes do not close whole-application acceptance. Scoped current Ruff passes; full all-model/native/history/server/MMFDB SPEC and quality gates stay open. Complete receipt: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-ui-history-batch-evidence.json`. No production edits or git mutations in the parent batch.

## Delayed core-hardening readback — October 4, 2026

The core-hardening worker is complete, with historical 22-pass and 9-pass selections. Parent reran the current codec, transaction, server-session, server-service and local/hybrid API files plus the actual headless macro save/load/resave node: **33 passed / zero failures/errors/skips**, wrapper 5.56 seconds, compared source/test hashes unchanged. Partitions: 7 codec + 2 transactions + 14 session + 3 service + 6 API + 1 headless. Current headless assertions use canonical arrays, so the worker's old ds["x"] schema blocker is superseded. One top-level macro definition per capture/save/payload-load/file-load entrypoint; codec/test Ruff and scoped whitespace pass. Receipt: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-core-hardening-evidence.json`.

This fresh-process subset does not supersede the native-transform-before-UID failures or all-model actual Main failures. Separate-server/authenticated-MMFDB and all-model history acceptance remain open; no new production edits, git mutations or independent approval are claimed.

## Delayed storage-hardening readback — October 4, 2026

The storage-hardening worker is complete. Its 18-pass selection required an in-memory import shim and reported an obsolete PTO-layout test failure; no HTTP integration was in its ownership scope. Parent normal-import execution now gives **33 passed / zero failures/errors/skips** in 9.8 seconds: storage 22, canonical PTO 9, real HTTP MMFDB 2, in that order and process. The normal-collection and old-layout blockers are superseded. Compared source/test hashes stayed unchanged; storage-module/test Ruff and scoped whitespace pass.

Current actual HTTP evidence uses captured TCSPC Fit snapshots, a temporary authenticated service/database and exact version/project payload readback, project-wide version allocation, unauthorized-write rejection and old-version immutability. Credit this only to the new parent run, not the worker's in-process backend report. Neither raw transport payload equality nor these 33 passes establish restored numerical predictions, all-model GUI/history or complete MMFDB lifecycle acceptance. Native publication and independent SPEC/quality gates remain open. Receipt: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-storage-hardening-evidence.json`. No parent production edits or git mutations.

## Active integration revision — October 4, 2026

The user continued implementation. Three disjoint implementation slices now replace handoff-only bookkeeping: native keyed graph publication/peer-safe rollback and inactive persisted parameter ownership; canonical single-Fit/FitGroup GUI presentation plus fit-window state; optional metadata dictionary imports at the pdbx facade (not the externally owned metadata/ModelEditor performance files). Exact tasks are `scratch/chisurf-{native-owner,fit-presentation,optional-plots}-integration-task.md` under the Hermes cache directory. Parent repairs only legacy/example/action/reset test fixtures and assertion strength, then reruns populated-native-before-UID, strict actual-Main 42-entry matrix, history/server/storage and independent SPEC followed by quality. No relaxed validation, scientific repackaging, skipped models or git mutation. Initial red-capable receipts are required before each production edit; later source/test/native hashes and exact XML counts govern gate closure.

Parent tracer bullets: migrate ProteinMC example to its legitimate structured atom table and valid model configuration; bind every GUI fixture to its concrete guard and isolate runtime authorization; assert partial-presentation fault reachability/exact message; retain checkpoint row/snapshot/nested-list identity and validate successful reset's concrete owned empty history. Run each immediately, preserve prior assertion strength and actual source-readback failures. Existing 42 science-file / 164 focused / 202 history results remain scoped historical green evidence until stable-source rerun.

## Parent fixture revision and reached Main preview — October 4, 2026

Current four-file fixture/assertion selection is **47 passed, zero failures/errors/skips**, 4.22 seconds; compared fixture hashes unchanged and scoped Ruff/whitespace clean. ProteinMC now uses copied real T4L StructureReader data, legitimate structural (0,0) range, nondefault sampling controls and exact atom/coordinate readback after deleting the copied source. Staging/action fixtures use the addressed guard. Strengthened reset fault reachability actually exposed invalid old object() science; a real ParseModel fixture now reaches the exact intended fault and retains root containers, document, prediction and range. All nested checkpoint containers retain identity by path; successful local/proxy reset exports the validated canonical empty owned history with the same lock. Independent SPEC re-review runs in a separate context; this is execution evidence, not approval.

Strict actual-Main preview over TCSPC polarized/PDA simple/GeneralFCS remains **three failures**, but no longer the earlier native-arity or single-Fit crash: TCSPC/GeneralFCS generated tables bind a parameter outside the captured live manifest; TCSPC grouped reconstruction tries an absent rotation parameter; PDA reaches numerical/plot/edit checks then ordinary macro save lacks fit_windows. Preserve the strict harness and these exact reached failures. Native/presentation/optional-plot lanes are still active, so this preview is diagnostic, not final stable-source acceptance.

Parent next RED/GREEN tracer bullet owns only `get_project_payload` in macros/core_fit.py and new `test/project/test_project_ui_capture_contract.py`: capture the current real GUI view through the explicit hooks before assembling the canonical local/proxy snapshot; merge client-owned views with server-owned science without dropping server fields/resources/history; verify exact .cs.pto readback and failed-view-capture destination preservation; rerun actual PDA Main. No GUI save bypass, model cloning, schema weakening or production-lane file overlap.

## Shared binding ownership tracer — October 4, 2026

The current complete-budget native/UID/owner/public/legacy regression is139/139 (241.451s); earlier incomplete240/150s runs do not establish a hang. Rich rate enhancement and shared rich-control probe both passed narrow independent SPEC then quality; parent focused28/28 and selected actual-Main FCS kinetics1/1 remain separate from full42 acceptance. Fresh TCSPC/GeneralFCS rows still fail binding inventory; a read-only independent diagnosis finds GeneralFCS inactive archived inputs omitted by optimiser-only `parameters_all`, and TCSPC cached scalar/output projections not independently persisted ports. It does not prove any original stale object and does not resolve TCSPC grouped topology failure.

### Task A — Canonical document ports in the shared acceptance probe

**Files:** modify only parent-owned `test/gui/scientific_document_gui_probe.py`; create `test/gui/test_scientific_document_port_ownership.py`. No production/render/model/scientific-formula changes, no Git mutation. Parent retains tracking/reviews.

1. Extract the current active/global port-index construction into one testable helper without changing behavior; rerun existing three rich-control cases.
2. Write and run a RED actual-GeneralFCS case: an inactive preset input is excluded from `parameters_all` yet present identically in `get_session_parameters`, canonical snapshot and its generated table. The existing helper must reject/omit it before correction.
3. Reuse public toolkit-neutral `owned_scientific_objects` for the addressed scientific graph, without traversing UI/cache/global-registry objects or converting projection rows into fake scientific inputs. Keep exact UID/object identity checks unchanged. Apply the same per-member authority to rich-input selection.
4. Add/execute negative table and rich-control foreign-owner/same-UID cases. Assert exact scientific snapshot and predictions unchanged by inventory generation.
5. Parent reruns focused helper/rate union and actual GeneralFCS Main lifecycle; inspect stage reports and same-state normal/constrained images. Independent SPEC PASS then quality required; old accepted source hashes stay historical, new hashes govern the changed harness.

#### Task A completion checkpoint — October 4, 2026 (selected shared-control scope; full matrix remains pending)

**Entry point:** The GeneralFCS direct-grid control gap is resolved in the shared actual-Main probe. Canonical `.cs.pto` capture/load, ordinary local API load, exact snapshot readback, GeneralFCS scientific recomputation, macro save/readback, and fresh reload all completed. Do **not** restart the persistence redesign or treat this as a model/serializer defect. The next investigation is the first failure found while expanding the strict 42-entry actual-Main matrix.

**Scoped current files:**

- `test/gui/scientific_document_gui_probe.py` — currently untracked; shared actual-Main acceptance probe.
- `test/gui/test_scientific_document_port_ownership.py` — currently untracked; focused ownership/grid regressions.
- No production model, renderer, session codec, formula, or legacy serializer was changed in this latest Task A slice.

**Completed in the current tree:**

1. Added `_document_owned_parameter_index(fits)` to the shared probe. It creates a small declared owner over the selected fits and uses public `owned_scientific_objects(..., include_plugins=False)`, then keeps only actual `FittingParameter` instances. It deliberately does **not** use the process registry or optimiser-only `parameters_all` as the ownership authority.
2. Added `test_general_fcs_inactive_preset_table_uses_canonical_document_inventory`. It proves an inactive MDF preset port is absent from active `parameters_all`, present as the identical object in the canonical owner graph, and validly bound by the generated AutoForm table.
3. Verified after that change:

   ```text
   QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1 \
   PYTHONPATH='.:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:modules/chimol' \
   NUMBA_CACHE_DIR=/Users/tpeulen/.hermes/cache/scratch/chisurf-project-numba \
   /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest -q \
   test/gui/test_scientific_document_port_ownership.py -p no:cov -o addopts=''

   3 passed in 3.35s
   ```

   ```text
   /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest -q \
   test/project/test_native_owner_graph_publication.py::test_general_fcs_declared_inactive_parameters_have_concrete_owner_and_registry \
   -p no:cov -o addopts=''

   1 passed in 1.95s
   ```

**Historical RED baseline (resolved):**

```text
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH='.:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:modules/chimol' \
NUMBA_CACHE_DIR=/Users/tpeulen/.hermes/cache/scratch/chisurf-project-numba \
/Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest -q \
test/gui/test_scientific_document_port_ownership.py::test_general_fcs_species_grid_exposes_active_document_port \
-p no:cov -o addopts=''

FAILED: StopIteration
1 failed in 4.32s
```

The real `GeneralFCSModel` in `species` mode with three components owns the active `species._N` port, but the old probe reported no corresponding generated control.

**Root cause (resolved):**

- The `species` AutoForm section is a `dynamic_group` with its default grid layout. `AutoForm._build_dynamic_group()` creates direct `FittingParameterWidget` instances through `make_fitting_parameter_widget(...)`; it does **not** create a `QTableView`.
- The old `_editor_bindings()` enumerated only `QTableView` parameter tables and `RateMatrixWidget` cells.
- The old `_edit_control()` could commit through table delegates and rate-matrix `QDoubleSpinBox` controls, but not a direct `FittingParameterWidget.widget_value` (`ScientificDoubleSpinBox`).

**Implemented shared resolution:**

1. `_editor_bindings()` now enumerates direct `FittingParameterWidget` children after tables and rate grids. For each one it validates exact canonical owner identity (`live_parameters[uid] is widget.fitting_parameter`), live displayed numeric value, direct-widget output/link/read-only behavior, and records an ordinary `field="value"` cell with `control="FittingParameterWidget"` and `value_control="ScientificDoubleSpinBox"`.
2. `_edit_control()` now discovers the same direct widgets in the real Main hierarchy, validates document-owned object identity, expands/shows the real ancestors, types the value into the real `ScientificDoubleSpinBox.lineEdit()`, presses Return, processes Qt events, and asserts both control and exact live parameter values. It does not call a model setter or `update()` directly.
3. The focused red regression became green:

   ```text
   1 passed in 3.73s
   ```

4. The shared focused union passed after the change:

   ```text
   test/gui/test_scientific_document_port_ownership.py
   test/gui/test_scientific_document_rich_controls.py

   7 passed in 4.19s
   ```

   `compileall` for both changed GUI tests/probe and scoped `git diff --check` also passed.

5. The strict real-Main GeneralFCS lifecycle passed:

   ```text
   test/gui/test_all_model_document_gui.py -k 'GeneralFCSModel'

   1 passed, 41 deselected in 105.03s
   ```

   The five child reports under `pytest-466/test_configured_model_actual_m0` all end at `phase: complete`. The restored stage recorded the real keyboard edit as `N: 1.000 → 1.011`, using `FittingParameterWidget` → `ScientificDoubleSpinBox`, with `science_before != science_after`; canonical equality and ordinary macro `.cs.pto` save/readback passed.

6. Direct visual inspection of the real 1500-pixel restored/control-edited captures confirmed populated GeneralFCS controls and nonblank plot/table tabs. The direct `N` field visibly changes from `1` to `1.01`; data-table model/residual values and the reported χ² change, consistent with the asserted numerical recomputation. No blank or broken layout was observed in the inspected Fit and Data table tabs.

**Next entry point:** Run the strict actual-Main catalogue in controlled batches or a persisted long-running job, capture the first genuine failing row's child report and images, and repair only its shared contract gap. Do not infer 42-row acceptance from this one selected GeneralFCS pass. Current general support now covers parameter tables, rate matrices, and direct `FittingParameterWidget`/`ScientificDoubleSpinBox` grids.

**Do not do:** Do not change `GeneralFCSModel` formulae, the `.cs.pto` codec, `session.py`, model-specific serialization, or loosen identity checks. Do not downgrade the edit to a direct parameter assignment. Do not treat inactive preset ownership and direct grid-widget discovery as the same bug. No staging, commits, pushes, resets, stashes, checkouts, or cleans.

### Task B — TCSPC display projections and grouped topology

Diagnose before changing production. Scalar/configuration and computed-output display bindings require explicit toolkit-neutral owner/path/kind semantics, not bypassed UID assertions, serializing callbacks/widgets, appending fake fitted parameters, new Qt adapters or a parallel renderer. Separate TCSPC `rotation.amplitude.0` grouped restore from the inventory gap: the source snapshot has empty explicit `adapter_state.scalars`, saved structure `lifetime.components.1.rotations.2` and four rotation values. A tight standalone-to-group capture/restore loop must establish where the topology ceases to contain those ports. Preserve existing42-entry/196-image baseline; any production enhancement needs RED, matched before/after and science/file parity.

**Observed restore boundary (October 4):** the source canonical snapshot is valid. The failure begins while `restore_session()` creates a group member: `FitGroup` gives the placeholder local `Fit` a `group` before `_construct_saved_model()` calls `DescriptionModel.__init__`; the model's ordinary group-position policy injects `polarization=0` for a one-member group even though the snapshot has no explicit scalar. BFF consequently constructs a rotations.0 topology before `adapter_state` seeds its saved rotations. This is a session-construction contamination, not a model-specific serialization exception and not a reason to drop rotation values.

**Planned RED/GREEN repair (coordination required with the active project-lifecycle owner):** add a small `.cs.pto` round-trip regression for a standalone `tcspc_polarized` model selected to `lifetime.components.1.rotations.2`, then wrapped as a one-member `FitGroup`; it must retain empty explicit scalars, structure and all four rotation values after capture/file/load/fresh restore. In `restore_session()`, construct group-member models and apply their adapter states with the constructor-time `Fit.group` context temporarily detached; restore that runtime membership only after canonical state, scalar links and model update succeed. Do not change `DescriptionModel` formulas, special-case TCSPC, inject fake scalars, or weaken `native_graph_identity`/exact snapshot assertions. Follow with the focused regression, group-position tests, described-model state/MaxEnt regressions, and the TCSPC actual-Main row.

### TCSPC actual-Main expansion checkpoint — October 4, 2026

The first configured TCSPC block is now **13/13 individually verified actual-Main lifecycle rows** (catalogue indices 00–12). Each row ran in a fresh outer pytest process and exercised its nested scientific producer, canonical restore, group packaging, real Main capture, real keyboard/Return edit, recomputation, ordinary macro `.cs.pto` save/readback, and fresh restore. This is a bounded matrix checkpoint, **not** 42-row acceptance.

**Rows accepted in this current source tree:** `tcspc_polarized`, `tcspc_mixture`, `tcspc_fret_gaussian`, `tcspc_fret_discrete`, `tcspc_fret_worm_like_chain`, `tcspc_fret_saw_nu`, `tcspc_fret_ising_chain`, `tcspc_pddem`, `tcspc_fret_acceptor_density`, `ParseDecayModel`, `FRETStructure`, `tcspc_maxent_lifetime`, and `tcspc_maxent_fret`.

Two shared presentation defects were found through strict RED→GREEN tests while expanding this block:

1. `ParseDecayModel` inherited a Convolution `dt` scalar row even though its declarative model state has no `dt` scalar. `classic_editor.py` now emits that editable display projection only when `self._has("dt")`. `test_parse_convolution_rows_only_declare_persisted_scalars` first failed with the unsupported `("dt", "dt")` projection and now passes through the real generated parameter table.
2. MaxEnt descriptions validly omit the optional `background_pattern` dataset slot, while the Generic `PhB` computed-output row read it unconditionally. `Generic.background_curve` now returns `None` when the optional dataset is absent. `test_maxent_generic_output_display_handles_an_absent_background_slot` first failed at `AttributeError: background_pattern`; it now verifies the actual generated `PhB` read-only binding and finite value. The same current-source probe confirms both MaxEnt configurations have `background_slot=False`, `curve=None`, and `PhB=0.0`.

**Current test evidence:**

```text
pytest -q test/gui/test_parse_widget_expression_editor.py \
  test/gui/test_classic_tcspc_editor.py -p no:cov -o addopts=''
pytest -q test/gui/test_all_model_document_gui.py -k 'ParseDecayModel' -p no:cov -o addopts=''

21 passed, 1 asynchronous Qt warning
1 passed, 41 deselected in 77.87s
```

```text
pytest -q test/gui/test_scientific_document_port_ownership.py -p no:cov -o addopts=''
pytest -q test/gui/test_all_model_document_gui.py -k 'tcspc_maxent_lifetime' -p no:cov -o addopts=''
pytest -q test/gui/test_all_model_document_gui.py -k 'tcspc_maxent_fret' -p no:cov -o addopts=''

5 passed in 4.54s
1 passed, 41 deselected in 104.42s
1 passed, 41 deselected in 108.47s
```

The initially incomplete WLC/SAW/Ising and PDDEM batches were resolved by individually rerunning their remaining rows: WLC `1 passed in 102.54s`, Ising `1 passed in 101.36s`, and PDDEM `1 passed in 106.85s`. The existing exact-float table edit regression remains essential for SAW: type `repr(value)` into the live `ScientificDoubleSpinBox`, then Return; never programmatically `setValue()` before table commit.

**Visual gate:** Directly inspected actual-Main MaxEnt FRET `before` and `control-edited` 1500-pixel images show populated Convolution and Generic tables, visible read-only `#PhB`/`#PhF` rows, visible fit/residual/data plots, and no blank/error panel or obvious clipped editor state. This is a visual check only; scientific/reload acceptance comes from the lifecycle assertions above.

**Next entry point:** Continue at catalogue index 13 (`ParseStoppedFlowModel`) in bounded fresh-process slices. Keep all remaining 29 entries pending. Do not recast optional presentation values as persisted scientific inputs, add model-specific session codecs, directly mutate parameters in GUI acceptance, serialize Qt/runtime objects, or relax owner identity/snapshot checks.

### Stopped-flow and PDA actual-Main expansion checkpoint — October 4, 2026

The next nine configured entries are now individually verified in the same strict real-Main lifecycle, bringing the explicit current matrix receipt to **22/42** entries: stopped-flow `ParseStoppedFlowModel` and `ReactionModel`, plus PDA `Pda2cSimpleModel`, `Pda2cGaussianDistanceModel`, `Pda2cSawNuModel`, `Pda2cDynamicTwoStateModel`, `Pda2cDynamicNStateModel`, `Pda2cAnisotropyModel`, and `Pda3cModel`. Recorded durations range from 80.91 s to 231.00 s per configured row. Remaining rows 22–41 are still pending.

**PDA Gaussian persistence correction:** strict restored-stage readback first caught raw component amplitudes changing from `1.0, 0.4` to `0.7142857142857143, 0.28571428571428575` merely as the restored GUI was created. The calculation already obtains normalized non-negative weights through `Pda2cGaussianDistances.amplitudes`; the mutating override of `Pda2cGaussianDistances.finalize()` was therefore an invalid presentation/update side effect. `finalize()` now delegates only to `FittingParameterGroup.finalize()` for controller cleanup and leaves the stored fit values untouched.

The RED regression `test_gaussian_distance_recompute_preserves_raw_component_amplitudes` failed before the production change at the exact `1.0 != 0.7142857142857143` mismatch after `fit.model.finalize()`. It is green after the change, simultaneously proving normalized computational weights `[1/1.4, 0.4/1.4]` and exact raw-input preservation. The focused Gaussian AutoForm test and strict actual-Main lifecycle also pass:

```text
pytest -q test/models/test_pda2c_statistics.py::test_gaussian_distance_recompute_preserves_raw_component_amplitudes \
  -p no:cov -o addopts=''
pytest -q test/gui/test_pda2c_model_editor.py::test_pda_model_editor_renders_and_computes \
  -k 'GaussianDistance' -p no:cov -o addopts=''
pytest -q test/gui/test_all_model_document_gui.py -k 'Pda2cGaussianDistanceModel' \
  -p no:cov -o addopts=''

1 passed in 2.06s
1 passed, 4 deselected in 2.18s
1 passed, 41 deselected in 83.66s
```

A final fresh Gaussian actual-Main rerun remained green in 81.00 s. Direct inspection of its matched `before` and `control-edited` 1500-pixel captures shows two visible editable distance-component rows (`Rₚ`, `sₚ`, `xₚ`), preserving the raw visible amplitudes `1` and `0.4`; populated Distribution/Residuals/Residuals 2D/Info/Parameter scan tabs; and populated red/blue plotted traces with no blank or visibly clipped editor area. The post-edit capture shows the same two distance rows alongside an active nuisance-table edit, rather than silently renormalizing their inputs.

**Concurrent-source note:** an initial `Pda2cSawNuModel` process observed `NameError: DockArea is not defined` while the shared `fit_subwindow.py` was actively transitioning from `DockArea` to `FitPlotsArea`. The current source no longer contained that inconsistent constructor/import pair; after `compileall` its exact strict row reran green in 84.77 s. No change was made to another owner's `main.py` or `fit_subwindow.py`.

**Next entry point:** Continue at DEER catalogue index 22 (`DeerGaussianModel`) in bounded fresh-process slices. Do not claim a full PDA or whole-catalogue result from screenshots alone; keep canonical snapshots, raw values, computed normalized projections, and real widget keyboard/Return behavior separately asserted.

## Task 1 — Enumerated catalogue acceptance, not spot checks

Files: `chisurf/core/settings/experiment_configs.yaml`, `test/project/test_all_model_catalogue_roundtrip.py` and typed fixture helpers.

1. Enumerate each configured model/reader and its actual class identity automatically. Check independent manifested expected paths against runtime catalogue so new entries cannot escape testing. Retain configured aliases which share a class identity (ICS) as distinct scientific modes.
2. Use appropriate real bundled reader measurements or explicitly labelled deterministic scientific fixtures/simulators for each family: TCSPC, FCS, PCF, ICS, PCH/FIDA, PDA two/three-colour, MFD, DEER, stopped-flow/reactions, structural modelling, global/parameter transform.
3. Prove actual configured dataset output types and dimensional layouts, metadata, auxiliary axes/tables/count histograms/structure resources survive. A generic one-dimensional DataCurve is not evidence for multidimensional/structured outputs.
4. Run RED for each identified lost state/unsupported shipped path before production fixes. No constructor-only acceptance and no scientific test skips.
5. Required loop for every model: create -> nondefault scientific/editor state -> compute -> capture/save -> fresh restore -> compare class/mode/state/parameters/predictions -> edit -> recalculate -> resave/reload again. Preserve uncertainty/mask dtype/objective/fit range.

## Task 2 — Dependencies and nondefault model topology

Files: `core/project/session.py`, explicit `core/models/**` state adapters, tests above and graph regression.

1. Preserve exact UID targets for forward/reverse local/global/cross-fit parameter links with duplicate names. Edit source after restore and compare dependent predictions; reject dangling refs/cycles without live mutation.
2. Exercise mixtures referencing other fits, IRF/background/linearization curves, structure/label resources, reaction network/species/reactions/initial conditions, FCS kinetic matrices, dynamic PDA state counts/rates/seeds, multi-component distributions/grids/solver settings, descriptions with equation/catalogue/algorithm/selection changes, global membership/weights/constraints, parameter transform definitions/ports.
3. Preserve stored disabled/semi-infinite bounds, fixed/value/error/output roles, component identities/order and native ports/nodes. No default-state equality disguising discarded configuration.
4. Core class configuration must be portable, explicit, validated and free of arbitrary archive imports/executable callbacks/DB/widget handles. Never alter scientific formulas merely to get serialization green.

## Task 3 — History integrity, checkpoints and exact identity

Files: `chisurf/history/{core,replay,projection,__init__}.py`, `test/history/test_history_document_integrity.py`.

1. RED: checkpoint navigation with zero delta must retain datasets/fits; navigation add/remove delta must apply to base, not replace with delta-only lists. Recursive state merges must retain untouched bounds/link UIDs; unlink clears both link formats.
2. RED: events/checkpoints are detached immutable-by-copy at record/load/return/subscriber boundaries. Invalid scalar/duplicate/malformed/version-incompatible loads fail atomically with original history/cursor/checkpoints preserved. JSONL staged atomic save preserves old destination on fault.
3. Fix suppression nesting/concurrency and checkpoint indexing/compaction. Compaction must not silently claim replayability after deleting indispensable events; checkpoint continuity and cursor semantics must be explicit.
4. History checkpoints must cover complete canonical science and resources or retain equivalent exact restorable state, not only names/reprs. No source rereads/UID regeneration to replay data/fit add/remove.
5. Full bounds/fixed/link/unlink/components/fit ranges/model configuration navigation must match direct scientific operations. No duplicated events during restore/replay.

## Task 4 — Live history navigation and GUI publication

Files: HistoryMixin in `chisurf/gui/main_helper.py`, history browser widget and fresh GUI tests.

1. Actual real Fit/ParseModel plus duplicate-named cross-linked fits: edit -> undo -> redo -> save -> fresh reload -> undo/redo -> edit from historical cursor. Assert numerical predictions, exact link target UID and model controls, no new source reads.
2. A new scientific edit after undo has defined branch semantics; no stale redo branch is silently reapplied. Cursor and displayed scientific state move together only after acknowledged restoration; rendering/validation/remote failure leaves both unchanged.
3. Create/remove fits/datasets/groups and model components with history navigation while originals unavailable. Preserve resources/current selection/history singleton, subscriptions and lock identity.
4. Fresh actual Main captures must be inspected. Separate-process GUI/server has equivalent document-owned state and usable history.

## Task 5 — Parent acceptance gates

- Rerun every new RED/GREEN repro against integrated current source. Parse actual JUnit/logs, report no overlapping suite-count addition.
- Run full project/history/server/API/browser/native lifecycle plus all enumerated model cases and configured readers; verify optional-MMFDB fresh startup/science/history/file loop and real authenticated deployment save/version/export/import equivalence.
- Inspect actual model/editor/history captures and numerical readbacks; do not derive scientific correctness from screenshots.
- Independent specification PASS must cover this expanded contract, then independent quality approval, complete reruns and docs/OKF closure. Keep REQUEST_CHANGES until those gates genuinely pass.

### Parent integration tracer bullet — canonical regression fixtures

The stricter history boundary intentionally rejects incomplete event dictionaries. Run `test_history_owner_transaction.py`, `test_authoritative_transition.py` and `test_session_codec.py` first and retain the RED log/JUnit. Migrate only obsolete setup data to events produced by `OperationHistory.record(..., persist=False)` and provide the actual supported plot-state hooks on dummy windows. Preserve every rollback, namespace, nested-container, lock, selection, document and injected-publication-failure assertion. Re-run the same selection immediately; no production validation relaxation and no scientific skip.
