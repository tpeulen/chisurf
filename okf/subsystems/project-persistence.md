---
type: Subsystem
title: Project Persistence
description: Canonical scientific snapshots, transactional restoration and optional real-MMFDB storage.
resource: chisurf/core/project/
tags: [core, project, persistence, archive]
timestamp: '2026-10-03T00:00:00Z'
---

# Project persistence

## Where to pick this up — October 5, 2026 (latest; supersedes the Oct 4 list below)

Goal: a `.cs.pto` restores ChiSurf state for **all 42 configured models (11 families)**,
proven by the actual-Main probe (`test/gui/test_all_model_document_gui.py` driving
`test/gui/scientific_document_gui_probe.py`). Details of this session:
[handover](../plans/2026-10-05-handover-scientific-persistence.md) "Continuation".

1. ✅ **Strict full-42 aggregate run: 42 passed / 0 failed** (2026-10-05, 2757 s; slowest row
   90.8 s), every row through producer → canonical → group packaging → before → restored
   GUI-control edit → ordinary macro save → fresh reopen of the GUI-saved `.cs.pto`, with
   MMFDB blocked and original source files forbidden. Earlier attempts that day were invalidated by
   the environment (IMP rebuild mid-run, the in-flight FitInfo emtk lane, disk full, then the
   rattler-cache purge that removed `arm64`'s symlinked tttrlib — fixed at the root, see
   [build-and-env](../workflows/build-and-env.md)). Trap for reruns: check `df -h
   /System/Volumes/Data` and that no IMP build / FitInfo edit is in flight; smoke one row first
   (`-k ParseStoppedFlowModel`, ~75 s). Command and env: handover plan "Environment".
2. **Visual review** of before/edited pairs for rows that went green late (DEER, DyeShape, …).
   Trap: Qt `grab()` cannot capture chimol's GPU surface — every "Structure" tab PNG is black;
   judge 3D tabs with the viewer's `renderer.grab_image(chrome=False)`.
3. **SPEC acceptance gaps** (unchanged): ProteinMC disk-load assertions omit model type /
   sampling controls / fit-range; file-load actions don't prove success-only identity publication
   after transactional failure; failed-save tests don't prove injected save-fault reachability.
4. **Commit.** The arc's work is uncommitted (handover discipline: no git-changing operations).
   `proteinmc_model.py` hunks interleave several sessions' persistence work — commit as one
   persistence change, not per hunk.


## Latest verified checkpoint and where to pick this up — October 4, 2026

Optional-plot worker `proc_23f80cb91464` is complete and independently accepted **only for its optional-catalogue/plot scope**. Parent ordinary-import six-file rerun `chisurf-parent-optional-verified.xml`: **59 unique passed / zero failures/errors/skips**, 70.767 seconds, with all 15 compared source/test hashes unchanged. Scope: lazy optional MMFDB dictionary facade, narrow named-package absence, installed dictionary error propagation/sole authority, defensive copies, real five-plot PDA construction and editable unknown metadata with exact science/state/traces. Scoped Ruff/whitespace passed. Fresh read-only independent **SPEC PASS then quality APPROVED** were parsed, with current owned hashes still exact. Receipt: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-optional-plots-evidence.json`.

The parent additionally reran the actual-Main `Pda2cSimpleModel` node: **1 passed / zero failures/errors/skips**, 103.967 seconds. Science producer, canonical single-Fit presentation, exact group packaging, before, restored-control-edit and fresh edited-file stages all exited zero with MMFDB blocked. Exact scientific output and ordinary macro `fit_windows` save/readback pass; restored `bg0=0.001` is committed through the real spinbox and automatically recomputes before resave/fresh reload. This supersedes the worker's earlier missing-`fit_windows` failure **for this case**, not the last historical 0/42 whole-matrix result. JUnit: `chisurf-parent-optional-main-pda.xml`; artifacts and reports: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-optional-main-pda/test_configured_model_actual_m0/`.

All full model rows and overall acceptance remain **REQUEST_CHANGES**. The passing Main node still records caught diagnostic exceptions in bounds conversion, single-Fit traversal and decorator probing; classify these before claiming exception-free application behavior. Inspected normal/constrained real renders show science and editors, but metadata value-column clipping/minimum-width expansion and tab overflow remain unaccepted. Parameter scan was constructed, not executed; all-mode controls, all-model history/server/backend continuity and AutoForm migration before/after pairs remain open. Before acting on the older failure list below, reproduce it on current sources rather than reapplying superseded repairs.

Delayed storage-hardening handoff `proc_319af1e7899e` is complete. Fresh parent normal-import run `chisurf-parent-storage-hardening-readback.xml` has **33 passed / zero failures/errors/skips**, wrapper 9.8 seconds: storage 22, canonical PTO 9 and actual HTTP MMFDB 2. Storage/PTO were deliberately run before HTTP in one process; compared source/test hashes stayed unchanged. Four storage modules and the storage test file pass Ruff; scoped whitespace passes. Receipt: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-storage-hardening-evidence.json`.

The worker's 18 passes used a temporary in-memory import shim because session.py was missing at its revision. Current normal collection needs no shim, and current PTO tests assert the new canonical typed project layout, so both historical collection/layout limitations are superseded for this selection. The current HTTP fixture saves actual captured TCSPC Fit state to a temporary authenticated service, reads exact project/version payloads back, checks omitted/older-parent version allocation, ACL rejection and prior-version immutability. This is new parent transport/snapshot evidence; the old in-process backend test is not HTTP evidence. Full restored model predictions, all-model GUI/history/resources and whole-MMFDB lifecycle acceptance remain open; native owner publication is still blocked.

Delayed core-hardening handoff `proc_2b5ec4eb571a` is also complete. Fresh parent `chisurf-parent-core-hardening-readback.xml` has **33 passed / zero failures/errors/skips**, wrapper 5.56 seconds: codec 7, transaction 2, server-session 14, server-service 3, local/hybrid API 6, and the real headless macro PTO save/load/resave case 1. Compared source/test hashes stayed unchanged. AST confirms one top-level definition each of get_project_payload, save_project, load_project_payload and load_project. Codec/test Ruff and scoped whitespace checks passed. Receipt: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-core-hardening-evidence.json`.

The worker's earlier headless-test schema limitation is obsolete: the current test uses canonical arrays and passes. This clean-process selection does not exercise the previously failing nonempty native-transform registry order, actual Main GUI or authenticated remote MMFDB; all those gates remain open. Worker-reported 22 and 9 passes are historical subsets, not additional current passes. Parent made no production edits or git mutations while verifying this handoff.

Overall **REQUEST_CHANGES**. The scientific/migration/initial-catalogue/GUI deliveries and the delayed UI-review/history-owner handoffs are complete, not still-active workers. Historical checkpoints below cannot override later failures.

Additional UI/history parent readback on October 4: `chisurf-parent-ui-history-batch-readback.xml` has **111 passed / 1 failed / zero errors/skips**, wrapper 26.97 seconds. The same four-file history/owner/reset selection as the worker is **67 passed**; the disjoint three lifecycle/action files are **44 passed / 1 failed**. These partitions must not be added to the 111 passes. The remaining action-load fixture binds a dummy GUI without its concrete-owner transition guard; repair the fixture without bypassing authorization. Compared source/test hashes stayed unchanged.

The canonical actual Main `[reset]` node was rerun separately: **1 failed**, wrapper 16.74 seconds. The earlier instance-method monkeypatch artifact is already corrected in the live test; do not reapply that obsolete correction. Current execution fails earlier during load at `transition.py:495`, `native.add_node(node)`, with the keyed native insertion arity error. Reset publication/rollback assertions are not reached, so neither the old scratch reset pass nor the 67-test scope establishes current native reset acceptance. Scoped Ruff passed. Receipt and complete failures: `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-ui-history-batch-evidence.json`.

Retained worker evidence: UI focused 45 passes and legacy browser **13 passes / 2 failures** (worker attributed these to bootstrap saving and non-explicit success; they still require current-tree reconciliation); history JUnit 67 passes, four separately isolated native plot cases and native ranges each pass. The historical forced-child multi-case native invocation exited **-11** without complete XML; isolated cases passed, not a successful combined native run. The old canonical reset failed on the test-injected `adopt` attribute while a corrected scratch copy passed. These are historical verification results, not new all-model/history/GUI approval.

- Parent parsed final worker JUnit: **42/42 scientific portable-file loops pass**, plus **43 inventory checks** (85 total); separate focused scientific/codec selection **164 passes**, with no failures/errors/skips. This supersedes the earlier 32/42 science result for the exercised configurations, not for every selectable mode or actual application integration.
- Actual Main GUI matrix: **0 passed / 42 failed / 0 errors/skips** despite 42 successful scientific producers. Canonical failures are 20 native node-arity errors, 21 single-Fit iteration errors and one GeneralFCS registry KeyError. Exact graph-preserving packaging has eight reconstruction failures; successful packages still encounter native publication, missing plots or omitted ProteinMC window state. No completed GUI edit/save/fresh-reload case is accepted.
- Fresh parent stable-source readback: **36 passed / 13 failed / 0 errors/skips**. Scientific-native/UID subset is **8/9** and six migrated files are **28/4**. The missing session.py collection error from the migration worker is historical; current source exists and tests collect. Raw parent JUnit/outcome and exact source hashes are retained in `/Users/tpeulen/.hermes/cache/scratch/chisurf-parent-four-lane-batch-evidence.json`.
- Parent inspected both normal/constrained PDA control captures: bg0=0.001 is visible; the scientific subwindow is blank. Numeric control-edit success does not establish plot or complete GUI persistence acceptance.

Resume in this order:

1. Reproduce native owner publication/rollback with `test/project/test_scientific_native_identity_contracts.py` **before** `test/project/test_spec_science_uid.py` in one process. Use the installed node-map values and keyed add_node contract throughout publication, retirement and rollback; preserve peer mappings and exact native identities. A UID-only clean process misses nine failures.
2. Make normal canonical single-Fit presentation work without replacing its graph with a FitGroup. Decouple mandatory plot construction from optional MMFDB metadata dictionary imports; reject silently missing declared plots and inspect fresh renders.
3. Resolve declared GeneralFCS registry objects, exact grouped TCSPC reconstruction failures, ProteinMC fit_windows saving and meaningful structural GUI controls/rendering.
4. Repair the two additionally invalid migrated fixtures (structured ProteinMC atoms; concrete dummy GUI guard) while retaining rejection/state-preservation checks. Two other migrated failures share the native owner defect.
5. Close reset-review fault-reachability, nested-checkpoint-identity and validated-empty-history assertions; rerun all-model history/server/authenticated-MMFDB lifecycles, then independent specification and quality reviews. Existing 202-pass history scope is not this broader acceptance.

> **Acceptance status: REQUEST_CHANGES — October 4, 2026.** The earlier 13
> scientific/lifecycle findings and actual optional-MMFDB Main startup failure
> have dedicated passing parent regressions. This does **not** establish complete
> acceptance: a fresh independent specification review reproduced six further
> blockers: public API restore/reset authorization, active parameter UID
> ownership, portable attachment continuity, shipped TTTR/DEER readers, Main
> import's forced in-process authentication, and non-atomic browser export.
> Three disjoint revision owners now cover those gates. Required contract below
> is not proof that every public entrypoint currently satisfies it.

The replacement uses one version-5 scientific snapshot for portable `.cs.pto`
files, macros/actions, API/server operations and configured MMFDB project
versions. No backwards compatibility with the earlier ZIP/`.csp` or project
schemas is required. This implementation is **not yet fully accepted**: the six
fresh specification blockers and a new independent specification PASS followed
by quality review must be closed first.

| Module | Responsibility |
| --- | --- |
| `project.py` | Explicit detached project document and JSON representation. |
| `session.py` | Capture, validate and rebuild the scientific graph without replacing live state. |
| `pto.py` | Validate the snapshot and temporary PTO readback before atomic publication. |
| `archive.py` | PTO archive wrapper; not a competing scientific serializer. |
| `storage.py` | Optional backend policy and exact-version MMFDB readback verification. |
| `lifecycle.py` | Save/discard/cancel authorization and document identity/clean baseline. |
| `ui_state.py` | Supported window state; geometry is separate from essential science. |

## Scientific state

Datasets preserve stable UIDs, names, filenames, metadata and typed `x`, `y`,
`ex`, `ey` and mask arrays. All four standard dataset-group classes preserve
membership and current selection. Fit records preserve members, ranges,
noise/objective identity, model adapters, parameter values/bounds/fixed/error
state, dependencies and explicit parameter link targets. Link resolution is
by the recorded fit/member/parameter identity, not a name or selected member.
Duplicate identities, missing references, cycles, malformed arrays and invalid
layouts fail closed. Bounds are applied before the parameter value to avoid
clamping against constructor defaults.

Built-in TCSPC, FCS and GlobalFitSetup readers use curated portable descriptors.
Their shared identity and experiment/model registry are restored separately
from curves; reader controllers and database connections are not serialized.
Restoration never re-reads the original measurements. Unsupported readers fail
explicitly. An archive cannot choose an arbitrary module to import: reader
types are allowlisted and model/experiment construction uses trusted or
explicitly registered types.

## Publication and restoration

Capture verifies a detached reconstruction and scientific/model predictions
before reporting success. File publication validates schema/science, writes a
temporary candidate, validates its readback, then uses `os.replace`. The old
file and candidate cleanup are covered by failure-injection tests.

Replacement first stages the reconstructed science and document identity.
Commit/rollback covers datasets, fits, selections, history state and document
identity. History rollback copies its state, not synchronization primitives
such as an `RLock`. Server mode captures/restores the authoritative server
session through snapshot RPCs without replacing GUI proxy lists with local
scientific objects.

Save / Don't Save / Cancel protects close, replacement and reset. A cancelled
chooser or save failure is not permission to tear down the current session.
File and database identities are mutually exclusive and updated only after
explicit success. Ctrl+S is project save; Ctrl+Shift+S is portable Save As;
Ctrl+Alt+S is the separate fit save.

## MMFDB policy

`select_backend()` resolves the documented client configuration. Missing or
embedded/bootstrap settings select file and do not import MMFDB during
discovery. Explicit remote settings, including a configuration file that
resolves to remote mode, select MMFDB. A standalone deployment on localhost is
real; hostname-only classification is wrong. Configured errors are surfaced,
not silently downgraded.

Database saving validates science before acquiring a transport or performing
RPC, requires `ok is True`, and compares the exact returned version's complete
payload and project identity with the captured snapshot before marking clean.
The standalone MMFDB service stores that canonical payload on the project
operation; artifact decomposition is not used to reconstruct it.

## Reopened actual-owner boundary blockers — October 4, 2026

The latest independent specification process `proc_124b8a4d233e` exited 1 with a
provider safety flag and **no verdict artifact**. No quality approval follows it.
Parent independently confirmed two remaining failures despite the green regression:

- Registered `project.transition.begin` then `finish(commit=True)` clears an
  attached GUI session without invoking its rejecting guard. Method-name privacy
  is not owner authorization; public API authorization gate is reopened.
- Main/macro `get_project_payload()` omits owning resources locally and ignores the
  explicit resource wire field remotely; a resource-only attachment disappears
  before ordinary Save. Resource continuity gate is reopened at that actual path.

The exact repros and A view-lifetime/refresh-error handoffs are recorded in
scratch/chisurf-project-spec2-blocked-checkpoint.md and the plan. A/B/C now all
finished, but their completion is not whole-feature acceptance. Normal delegated
implementation was unavailable due provider rate limits; a bounded-scope independent
CLI implementation is running as `proc_3e23185ef2f0`, prompt/result
`chisurf-project-final-owner-boundary-{task,result}.md`. Preserve shared changes,
no source/schema weakening, no fake authentication/results or provider-policy
circumvention. The corrected owning authorization/resource/view boundary must have
actual RED/GREEN, integrated reruns and a genuine independent spec then quality
PASS before any closure. Original raw analyses remain required.

## Current six-gate revision checkpoint — October 4, 2026

The six fresh specification findings now have passing dedicated parent reruns,
including Main import/authentication and atomic native export, owning public API
and UID/prediction/refit semantics, exact file/DB/remote/empty-session attachments,
and measured TTTR/DEER/SDT plus curated reader configurations. Full integrated
project/server/agent JUnit: **1041 passed / 2 historical generic RPC no-parameter
skips**, no failures/errors. Current Main/native/browser selection passed; the
34-test import/export and 70-test API/UID/resource selections passed without skips.
These selections overlap and their totals must not be added.

Parent removed a test dependency on a prior expiring scratch export. The persistent
resource fixture now creates a fresh authenticated measured-data export and deletes
only its copied source before exact byte/alias resave checks; its reader/resource
selection passed 13 tests and the final resource-only rerun passed. Original plugin
UID fixtures now explicitly register owned working groups, preserve old assertions,
and give fit/model distinct IDs; failed-load events no longer claim success.

Overall acceptance stays **REQUEST_CHANGES** until fresh independent specification
re-review PASS followed by independent quality approval. Specification re-review is
`proc_124b8a4d233e`, final `chisurf-project-independent-spec2-result.json`; its scoped
source-hash checkpoint is `chisurf-project-spec2-source-checkpoint.json` in scratch.
B scientific and C import/export implementers finished; A API process
`proc_c041f3dd6f3d` still owes its final handoff. Do not count a pending process or
read-only review as approval. No project-owner commit/push.

## Latest parent verification checkpoint — October 4, 2026

These are executed selections with complete logs/JUnit in scratch, **not an
acceptance claim** and not disjoint totals to add together:

- `chisurf-parent-final-core-integration`: **916 passed, 2 skipped**, covering
  all `test/project`, `test/server`, and agent project round-trip. The two
  pre-existing generic server nonfinite-parameter tests had no parameters in
  their fixture; the named scientific input/bounds/identity checks ran without
  skips. Startup probes use real child readiness and a socket owned/closed by
  its REP thread, not fixed 20-ms sleeps or cross-thread ZMQ teardown.
- Scientific schema selection: **99 passed, 72 subtests passed**, including
  aggregate global parameters, links, semi-infinite/disabled bounds, non-output
  null/nonfinite inputs, identity collisions, trusted descriptors and native
  staging isolation.
- Actual authenticated MMFDB browser/transport/index/parity: **53 passed**;
  broader related browser/API/helper selection: **66 passed**. Canonical artifact
  indexes, version-scoped mask/dtype/UID/links, content-based export/import,
  actual version notices and remote path/auth guards are exercised.
- Standalone MMFDB version/auth/branch selection: **118 passed**.
- History/owner/Qt disposal and optional-MMFDB selection: **54 passed**.
- Actual measured-data native TCSPC restoration, exact saved member ranges,
  failed real Main reset and successful reset: **4 passed** in fresh renderer
  processes. Parent inspected actual restored, retained-reset and empty-reset
  captures; numeric arrays/model/identity assertions are separate from pixels.
- Actual Main startup/read/save/reload/edit/resave with all MMFDB imports blocked:
  **6 passed**. This established ordinary file-only startup for the tested reader,
  not the untested TTTR/DEER reader catalogue subsequently rejected by review.
- Scoped ChiSurf and companion MMFDB Ruff/diff checks are clean. Companion RPC
  broad exception handling is documented as an explicit error boundary, not
  success suppression.

Fresh independent specification verdict:
`/Users/tpeulen/.hermes/cache/scratch/chisurf-project-independent-spec-result.json`
contains one authentication concern and five reproduced logic errors. It also
ran 41 direct scientific and 11 history checks and actual restored ParseModel
refitting; its sandbox blocked normal writable pytest/GUI/HTTP reruns. Parent
passing reports do not override its demonstrated blockers.

## Historical verification recorded on 2026-10-03

- Parent regression of project, server lifecycle/API, agent project/API and
  GUI lifecycle/native TCSPC scenarios: **291 passed, 1 failed**. The remaining
  graph assertion expects an edge without the concurrently added `kind`
  field; the same failure reproduces in the isolated API file.
- Focused science, built-in reader/group, actual-file e2e and native GUI loop:
  **26 passed**.
- Parent-expanded browser backend/services/thread helpers: **18 passed,
  5 failed**. Three export tests use invalid opaque legacy payloads, one
  restore test expects prohibited v4-to-v5 conversion, and one reveals a real
  duplicate version-number defect when extending a project without a parent.
- Fresh-process file persistence and actual server construction/save/load
  pass with all MMFDB imports blocked. Actual standalone HTTP login/save/
  exact-version readback is included in the passing project regression.
- Scoped Ruff and `git diff --check` are clean. Real close prompt and native
  TCSPC before/after screenshots were inspected by the parent.

API test globals are isolated because `DataGroup.append` intentionally rejects
non-ExperimentalData dummy objects; inheriting that container from an earlier
project test created false order-dependent API failures. No production
container behavior was weakened.

Native TCSPC tests run each startup in a fresh process. A no-persistence
baseline also reproduced the repeated native teardown/startup crash; the
scenarios are exercised, not skipped. See `references/known-issues.md`.

## Where to pick this up

1. The acceptance plan now names all six fresh specification gates. Read the
   exact independent result and actual reproductions; do not infer completion
   from old test totals or stopped revision processes.
2. Revision contract in scratch: `chisurf-project-spec-revision-contract.md`.
   A owns guarded public API/server transitions (`spec-api`); B owns active UID,
   retained portable resources and shipped readers (`spec-science`); C owns
   configured authenticated Main import and shared atomic native-byte publication
   (`spec-io`). Preserve disjoint file ownership and unrelated dirty work.
3. Recover reports and **distinct** evidence files
   `chisurf-project-spec-{api,science,io}-{result,evidence}.md`. Re-run every
   demonstrated cancellation, stale UID write, attachment resave, real BH/DEER
   reader, denied/expired auth and disk-full export case in the parent.
4. Then re-run complete project/server/agent and browser/helper/companion
   selections, actual single-renderer Main guards/ranges and file-only fresh
   interpreter tests. Check complete JUnit and inspect real captures.
5. Require a fresh parseable independent specification PASS before independent
   quality review; only then update user docs/OKF and close acceptance. Work is
   uncommitted/unpushed by this project owner. Never reset others' shared changes.
