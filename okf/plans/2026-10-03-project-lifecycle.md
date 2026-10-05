# Project lifecycle replacement implementation plan

> **For Hermes:** Implement the separated workstreams with test-driven-development and independent review. Preserve concurrent edits; do not push.

**Goal:** Reliably save/reload ChiSurf analysis sessions, using portable `.cs.pto` when MMFDB is absent or only the bootstrap local database, and real MMFDB version storage when configured; prevent data loss on close/open/new.

**Architecture:** One GUI-independent session codec captures stable identities, datasets/groups, scientific model state, and parameter/dependency links. Reconstruction is detached and fail-closed: build every object and resolve every reference before committing to runtime collections. A project-document controller owns storage identity, successful-save baseline and lifecycle decisions; Qt is only its presentation. PTO and real MMFDB are transports for the same complete snapshot, never competing schemas or sources of truth.

**Tech stack:** Python, NumPy, existing Fit/FitGroup models, tttrlib/ptolib PTO objects, optional MMFDB RPC, existing Qt host and emtk dialogs.

## Observed baseline / red-capable loops

- `load_project_payload(Project(datasets={'bad': {'x': 'not an array', 'y': [1]}}))` logs a warning, returns `None`, and destroys the old unsaved dataset. It installs only the synthetic `Global-fit` dataset.
- Qt Save Project forcibly constructs `ProjectBrowserClient(inprocess=True)`: it is not a portable save and bypasses remote configuration. Export has a separate path and may save a stale database version instead of live work.
- Server project.load reads metadata but never restores SessionState. Server save uses separate `_safe_to_dict` serialization and swallows fit serialization errors.
- `Project.load` mutates the process BFF graph during reading; a portable document must not change live state.
- Project baseline: `test/project + test/agent/test_project_roundtrip.py + test/server/test_session.py`: 54 passed, 6 failed (stale ZIP/.csp expectations). Preserve the evidence and migrate those tests to PTO, not legacy compatibility.

## Expanded scientific/history contract

The user's October 4 clarification is authoritative: all experiments, models,
parameters, GUI model states and cross-fit dependencies, plus a working history
system. The explicit enumerated catalogue/nondefault-state/history plan is
`2026-10-04-full-scientific-session-history.md`. Passing the original targeted
project suites does not close these expanded acceptance gates.

## Acceptance criteria

1. Real curve arrays, metadata/UIDs, imported group membership and selections survive save/open; fit datasets keep object identity with imported curves.
2. Plain Fit and FitGroup (including selected member), model-specific state, ranges, values, bounds/fixed/error estimates, cross-fit links and IRF/background dependencies survive two successive saves/reloads. Forward links and identically named parameters must resolve to the exact saved target.
3. Invalid schema, missing models/dependencies, corrupt PTO, malformed arrays and restoration errors raise useful errors without touching active data/fits/history/document path. Failed saves preserve the previous valid file and document identity.
4. One codec is used by macros/actions, API/server, local files and real MMFDB versions. No optional MMFDB import on file save/open paths. No automatic use of fake embedded database.
5. Closing a nonempty/unsaved project offers Save / Don't Save / Cancel. Save cancellation or error keeps the main window, fits and plugin windows live. The same guard protects Close Project, New/Reinitialize and project replacement.
6. Save reuses its current destination. Save As explicitly writes `.cs.pto`; exported file is current live state, never a stale version. Open file/recent records state only after successful reconstruction.
7. Real MMFDB means a configured deployment, not bootstrap desktop seed; use configured remote transport/login, preserve project/version parent identity, verify saved snapshot by restoring exact version before marking clean. Missing configuration means PTO. A configured service error is surfaced; never quietly downgrade to another backend.
8. Render and inspect the close prompt and save/open interactions. Exercise actual application project path with fitted sample data.

## Task 1: Detached session codec (core worker)

Create `chisurf/core/project/session.py`; tests `test/project/test_session_codec.py`.

- First write/run a failing roundtrip for one real DataCurve and FitGroup.
- Implement `capture_session(datasets, fits, *, experiments=None, ui_state=None, name='untitled') -> Project`, `restore_session(project, *, experiments=None) -> RestoredSession` (owns `datasets`, `fits`, `ui_state`, resource lifetime/cleanup if needed).
- Preserve stable identifiers rather than sequential ds000/name-derived IDs. Record explicit classes and links. Scientific errors abort; do not substitute empty data/state or skip records.
- Reconstruct all datasets and all fit models before parameter-link pass. Preserve UID mappings explicitly; no by-name guessing across fits. Model-specific get_state/set_state are adapters; remove links during model construction and restore links centrally afterwards.
- Add/run failing tests vertically for group membership, forward links, duplicate parameter names, IRF/background dependencies, dynamic model state, plain fits, metadata and malformed input.
- Use existing PTO archive transport for embedded resources. Missing essential external files must fail clearly; scientific snapshot and file inspection must not mutate global BFF state.

## Task 2: Replace entrypoint serialization (core worker)

Modify project sections of `chisurf/macros/core_fit.py`, `chisurf/core/project/project.py`, `chisurf/server/services/projects.py`, relevant API/action boundaries; add transactional restore tests.

- Macros capture through `capture_session`; restore through detached `restore_session`, then commit collections once. Preserve active state/history/path on any precommit error. Avoid GUI reinitialize before staging.
- Low-level Project.save/load deal only with the explicit document; do not save/load an unrelated process-global BFF registry.
- Server save captures its own SessionState and load commits the reconstruction into that same SessionState; return useful error and counts only after success.
- Failures propagate instead of returning None/log-only success. Keep only thin forwarding wrappers for callers, remove competing full-project implementations.
- Migrate stale ZIP/.csp tests to PTO. Test fresh process re-open and changed-resave.

## Task 3: Storage/document lifecycle (parent worker)

Create `chisurf/core/project/lifecycle.py`, optionally `chisurf/core/project/storage.py`; tests `test/project/test_project_lifecycle.py`.

- Document identity is file Path or MMFDB project/version pair, separate from scientific data. Inject capture/restore and UI callbacks to keep tests independent of Qt/MMFDB.
- Explicit chooser: default/bootstrap embedded -> file; configured real/remote MMFDB -> MMFDB. Read configuration lazily; optional packages are not dependencies of the file path.
- Capture once for save, publish atomically, read back/restore exact target to verify, then update identity/baseline. Any failed/cancelled operation leaves prior document intact.
- Central discard guard returns boolean; Save callback must explicitly succeed before replacement/close. Cancel is default. Prompt may conservatively protect nonempty project even without dirty events.

## Task 4: GUI lifecycle integration (UI worker)

Modify project sections of `chisurf/gui/main_helper.py`, `chisurf/gui/main.py`, `chisurf/gui/project_helpers.py`, file/project menu labels and ribbon links where necessary. Use existing centralized dialogs/emtk host; no new handwritten Qt surfaces.

- Replace onSaveProject with controller-backed storage choice. Add Save As for portable `.cs.pto`; leave explicitly labelled database browser/archive actions separate.
- Put guarded close decision before geometry saving, closing fits or plugin windows. QCloseEvent.ignore on cancellation/error.
- Guard project close/reinitialize and file/recent opening; stage new project before dropping old session. Set recent/path/name only on success.
- Add real Qt close-event tests for all choices, cancelling file dialog, failed file/database save and successful save then reload. Ensure automated fixtures can clean up without modal hangs.
- Capture prompt PNG(s) at realistic size and inspect, drive real Save / Don't Save / Cancel controls.

## Task 5: Optional real-MMFDB adapter (storage worker or parent)

- Use resolved client configuration (including `config_file` deployment), current authenticated token at exact endpoint; never `_auto_auth` against an unrelated local database for a remote server.
- Save complete PTO bytes/project snapshot through actual existing RPC contract; include embedded resources/history. Verify exact returned version by readback before declaring success.
- Restore stages exact version through same codec. Backend optional/absent cases tested with imports blocked; real transport integration tested using local isolated actual server/database, not invented responses.

## Task 6: Verification / docs / review

- Targeted loop: `PYTHONPATH='modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:modules/chimol:.' QT_QPA_PLATFORM=offscreen /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest test/project test/server/test_session.py test/server/test_integration_lifecycle.py test/agent/test_project_roundtrip.py -q --tb=short`.
- Add targeted GUI lifecycle and project-browser tests; run broader core/API/actions/server/agent suites as feasible; identify baseline failures without destructive git operations.
- Ruff new/changed modules; compileall targeted files; `git diff --check`.
- Independent reviewer checks codec failure atomicity, correct link targets, storage choice/login/readback, shutdown order and every acceptance criterion. Fix findings and rerun tests.
- Update `okf/subsystems/project-persistence.md` (include Where to pick this up), `okf/usecases/project-save-restore.md`, user docs and dated `okf/log.md` entry. Update agent-board ticket on completion.

## Revised acceptance gates following independent review

The follow-up review is **REQUEST_CHANGES**, not approval. The current collection
of entrypoint-specific restore/rollback snippets is insufficient: replace it with
one owner-aware transition transaction rather than adding another rollback copy.
Core/UI/verify remain open despite the earlier 291-pass regression selection.

### Scientific schema owner

Own `core/project/session.py`, `fit_state.py`, `pto.py` and codec regression tests.
Require canonical scientific validation even if an archive omits its codec marker.
Round-trip the aggregate GlobalFitModel/global parameters as well as member fits;
preserve each semi-infinite bound endpoint; reject null non-output values and
reserved metadata that contradicts identities; validate group identity collisions.
Cover a real ParseModel, reader settings and four standard dataset-group classes.

### Authoritative transition owner

Own a GUI-independent `core/project/transition.py`, macro/action/API/server
integration and transaction tests. The runtime owner, not client-side proxy lists,
owns science/history/selection rollback. Provide one transaction that keeps the old
owner state available until synchronous presentation and document publication have
succeeded. Remote results must be handled as typed/validated RPC results, never
assumed to expose `.fits`. Never assign slices to unsupported server proxies.
Make direct project.load obey the same cancellation gate. Include history in ordinary
local GUI captures, and capture no-fit selection as None/-1 instead of invalid 0.

### Presentation/storage owner

Own `gui/main_helper.py`, `gui/project_helpers.py`, browser `gui/model.py`,
`core/project/storage.py` and related GUI/storage tests. Integrate the common
transition owner rather than another global-list rollback. Ordinary Save always
resolves configured backend first; only explicit Save As forces a portable file.
Require exact requested/returned project and version identities on database readback
and browser restore. Use canonical `ui`, and rollback history/selection/document
if window reconstruction fails. Coordinate the common transition API with its owner.

### Optional-dependency startup owner

Own the fresh-interpreter real-main-window MMFDB-blocking regression and necessary
GUI/optional-feature import boundaries, excluding the files owned above. Establish
an actual file-only application startup/save/reload path with every MMFDB import
rejected. Separate database-only operations from ordinary UI/model imports; no fake
modules, placeholder database, broad suppressed exceptions or skipped GUI test.
The current tight loop fails through the TTTR wizard importing lightpath workflow
and its unconditional MMFDB imports. Preserve database-enabled feature tests too.

### Parent integration gates after the four revision lanes

The four lanes have finished; their reports are evidence to rerun, not approval.
The parent real-MMFDB-free Main test selection returned 6 passed. A broader parent
run exited 1 without a complete pytest summary; its dots establish no count.

1. Route `SetupMixin.reinitialize` through the same authoritative transaction;
   eliminate legacy proxy slicing and destructive precommit cleanup. Test local and
   actual server-proxy reset, cancellation, failed Save, failed presentation and
   document publication. Own Main/helper/reset callers and new reset tests.
2. Make restored fit presentation preserve the exact stored scientific ranges;
   distinguish new-fit automatic range calculation from restoring an existing fit.
   Reproduce a nondefault saved range through real Main restoration before editing;
   exercise both restored and new-fit behavior. Own Main and the thin presentation
   call, which is no longer concurrently edited by the completed transition lane.
3. Reproduce/repair the actual deleted-QCheckBox callback reported at
   `gui/plots/lineplot/lineplot.py:1371 -> 625 -> 599`. Resource ownership/disposal,
   not broad exception suppression or skipping tests, must prevent callbacks into
   destroyed controls. Own plotting/controller lifecycle and focused resource tests.
4. Migrate the native browser/service/parity fixtures to real `capture_session`
   science and explicitly configured authenticated real-service tests. Preserve
   backend-policy assertions: embedded/bootstrap still means portable file. Never
   regain green by bypassing validation, identity checks, or auth. Own only those
   plugin test files while the GUI/plot integration lanes modify production.
5. Obtain a complete independent parent regression report using JUnit and a
   bounded runner with file-descriptor output; isolate proven native canvas cases
   only, identify the incomplete run's root failure, inspect captures, then run
   fresh independent specification and quality reviews. Leave the original tasks
   open until these gates and all named scientific checks are independently verified.

### Remaining integration revisions (October 4, 2026)

- Actual Main rollback exposed history-module-facade traversal into `__builtins__`.
  Resolve the actual history owner at the shared transaction boundary and snapshot
  only bounded owned history state, not module namespaces. Preserve lock and
  opaque resource identities. Tight facade regression plus native failed reset
  and failed restoration must complete with intact namespaces and windows.
- Canonical database artifact/parameter decomposition must consume `members` and
  canonical array/model records rather than legacy `local_fits`/top-level arrays.
  Assert actual fit/data/parameter/link resource readback, never add legacy aliases.
- Standalone authenticated browser export/import/details/delete must use canonical
  PTO content and resources; remote handlers must not access client-local paths.
  Finish all currently unreachable late sequence assertions.
- Preserve actual saved `version_number` through the checked storage result and
  notice; never infer it from local lists.
- Fix test isolation at the resolver alias source; the completed 191-pass project
  selection exposed real HTTP authentication resolving a prior temporary database.
  Retain actual authentication and service calls and rerun the exact failing order.
- Migrate the three stale window/reset failure hooks without weakening their
  scientific/window/document retention assertions.

### Independent specification revision gates — October 4, 2026

Fresh read-only specification review returned `passed=false` despite the parent
916-pass project/server/agent regression (2 pre-existing no-parameter skips).
Report: `/Users/tpeulen/.hermes/cache/scratch/chisurf-project-independent-spec-result.json`.
No quality review or overall approval is authorized before these cases pass:

1. Main import must select the configured authenticated real deployment, never
   force `inprocess=True` or mint a local session token.
2. Public `ChiSurfAPI.restore_project_payload`, load and reset, plus public server
   replacement, must use the same Save/Discard/Cancel, presentation/document and
   owner transaction. The private staged begin/finish protocol is not a public
   authorization bypass.
3. Saved UID addressing must resolve only active owned scientific objects.
   Verified server `set_parameter_value` mutated the discarded ParseModel
   parameter while returning success. Registry publication and rollback must be
   transactional, without exposing detached candidates early.
4. Attachment bytes must survive DB export -> portable file open -> restore ->
   recapture -> file/database save/export, even after source files disappear.
5. Shipped registered `TCSPCTTTRReader` and `DeerReader` must roundtrip their
   configurations and real bundled measurements without rereading raw files
   during restoration or accepting untrusted archive imports.
6. Browser/client export must stage/readback/atomically replace files and preserve
   an existing valid destination on short-write/disk-full/readback failure.

Three disjoint revision scopes own public transactions, canonical UID/readers/
resources, and import/export authentication/publication. Parent retains
fixture/doc/OKF integration, reruns and independent spec-then-quality approval.

### Current independent six-gate revision checkpoint

Dedicated parent reruns for all six findings are green. Full current integration:
1041 passed / 2 historical generic RPC no-parameter skips; no errors/failures.
Parent fresh measured-resource fixtures remove expired scratch dependencies,
owner-register plugin parameter groups with distinct fit/model UIDs, and require
failed restoration to publish no success event. These are producer/fixture fixes,
not weakened typed-science or ownership/authentication guards.

Final acceptance remains open: independent specification re-review
`proc_124b8a4d233e` over `chisurf-project-spec2-source-checkpoint.json` must return
parseable PASS; then independent quality review, any required retesting, docs/OKF
and top-level closure. A API worker final handoff remains pending; B/C finished.

### Escalation/revision: owner authority is not a private method name

The second independent specification process exited 1 with a provider safety flag
and produced no verdict artifact. It is **not approval**. Parent independently
reproduced direct `project.transition.begin`/`finish` clearing an attached GUI owner
while its rejecting guard is never called. Also actual `get_project_payload()`
loses attachment-only `cs.project_resources`; its proxy path discards the wire
resource field. Reopen public owner authorization and resource continuity.

This is architectural authority/entrypoint incompleteness, not a request to add
another truthy `confirmed` flag. Every externally reachable destructive operation
must reach the actual owner's authorization policy; private staging must be a
capability of an already authorized owning operation, not a public bypass. Preserve
separate-process GUI transactions with complete rollback and no server-thread Qt.
Main/macro Save must use the same complete resource-bearing owner snapshot as API.

Additional exact A handoffs: post-owner-ack disposal of retained old views, and
Main must propagate restored plot-refresh errors so restoration rolls back. Read
scratch/chisurf-project-spec-api-interface-notes.md. Named tests must reproduce
these before implementation; no source-swap, no weakened validators/guards, no
false event-success or independent-review claims. Current 1041-pass regression is
not full acceptance. Keep original raw analyses and REQUEST_CHANGES warning.

### Parent verification

Independently reproduce every review regression after its owner's changes; run the
full selected project/server/API/browser/GUI suites and actual standalone HTTP
version tests. Read rendered captures. Re-run independent review against the final
integrated tree; zero unaddressed scientific data loss or destructive transition
failures is required before accepting the task. Keep unrelated graph-test baseline
mismatch separate, with explicit attribution rather than suppressing it.
