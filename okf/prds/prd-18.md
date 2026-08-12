---
type: PRD
prd: "18"
title: "PRD-18: Dependency Injection + Hermetic Test Harness"
description: Makes the test suite hermetic and contracts the MMFDB client while explicit database/session injection is still being completed.
status: in-progress
phase: "1"
resource: modules/mmfdb/src/mmfdb/
tags: [prd, mmfdb]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
PRD-18 makes the test suite hermetic and defines an explicit MMFDB client contract, while progressively replacing module-global database/session resolution with explicit boundary injection. The autouse conftest fixture redirects the settings directory, resolved database, and object store to a per-session temporary location so no test can read or write user data. `MMFDBClient.call`/`close` is exercised by integration tests against the real in-process client, so interface drift fails loudly instead of being masked by mocks. The broader dependency-injection goal is not complete yet: many RPC/API handlers still open `MFDatabase(resolve_database_path())` directly, overlapping with the open [PRD-17](prd-17.md) SessionContext work.

# Status
In-progress (updated 2026-08-09). Landed: the hermetic test harness
(`test/conftest.py`), real in-process `MMFDBClient.call` contract test, and
**handler-level db_path injection**: all 6 backend service modules
(`services.py`, `auth_services.py`, `measurement_services.py`,
`ndxplorer_services.py`, `elabftw_services.py`, `fluorophore_services.py`)
now accept `db_path: str = ""` and capture it once at registration time via
`_resolved_db_path`. Handlers use `MFDatabase(_resolved_db_path or ...)`
instead of calling `resolve_database_path()` on every invocation. 754 mmfdb
tests pass. **Remaining:** thread the injected path from the ~20 `chisurf/`
boundary callers (GUI plugins, spectra_downloader, etc.) that still call
`resolve_database_path()` directly.

# Goal
Stop resolving the database/dictionary/user via module-global functions re-imported into many namespaces; pass them explicitly. Make the test suite **hermetic** so no test can touch the real user database, and define an explicit client interface tested against the *real* in-process client.

# Evidence (why)
- `resolve_database_path` is `from … import`-bound into `services`, `setup_services`, `api`, `database_resolver`. Patching one missed `api`, so the setup-handler tests read the **real** `~/.chisurf/...db` and polluted each other (a leaked `rpc_test_setup` row made them "pass"). Repros during development mutated the live DB.
- `MMFDBClient` exposed `_call` but callers used `.call` → `AttributeError` swallowed → the dataset browser silently showed 0. Tests passed because they injected a **mock** client that had `.call`.

# Design
1. **Inject the DB/session** ([PRD-17](prd-17.md) `SessionContext`) into handlers and repository entry points instead of each calling `resolve_database_path()`. One resolution site at the boundary.
2. **Hermetic test harness:** an autouse `conftest` fixture (project-wide for `test/` and plugin tests) that points the settings dir + resolved DB + object store at a per-session temp location. No test can read or write the user DB. (Removes the whole class of cross-file pollution and protects user data.)
3. **Explicit client Protocol:** `MMFDBClientBase`/`MMFDBClient` declare `call`, `close` as the public contract; integration tests drive the **real** in-process client (not a mock) so interface drift (`.call` vs `_call`) fails loudly.
4. Where module-global resolution must stay (legacy), funnel it through one indirection that the harness overrides.

# Tasks
1. Project-wide autouse fixture redirecting settings/db/object-store to temp.
2. Add public `call` to `MMFDBClient`; an integration test exercising the real client end-to-end (browse + open) — would have caught the `.call` bug.
3. Refactor handlers to take the session/db from [PRD-17](prd-17.md) rather than re-resolving.
4. Audit + remove `from … import resolve_database_path` namespace-binding that makes patching fragile; prefer `database_resolver.resolve_database_path()` calls or injected paths.
5. Tests: full-suite run is order-independent (no cross-file pollution); a guard test asserts the real user DB path is never opened during tests.

# Definition of Done
- [ ] Autouse harness: no test touches the real user DB/object store; suite is order-independent.
- [ ] `MMFDBClient.call` is the public contract; an integration test uses the real client.
- [ ] Handlers take an injected session/db; fragile namespace-bound resolution removed.

# Definition of Clean
DI over monkeypatching; integration over mock-only; behavior-asserting tests; no silent swallow of interface errors.

# Relationships
- Carries [PRD-17](prd-17.md)'s SessionContext as the injected unit.
- Contracts the client `.call` fix that originated in [PRD-10](prd-10.md).
- Its hermetic harness is a prerequisite for [PRD-24](prd-24.md) standalone package tests.
- Reinforced by [PRD-25](prd-25.md) (fail-loud error policy, single RPC envelope).
- Targets the [MMFDB target](/specs/mmfdb.md) and [Core target](/specs/core.md); moves away from [runtime globals](/architecture/runtime-globals.md).

# Where to pick this up

**Handler injection is done in the float zone; the boundary callers are the
open front.** All 6 mmfdb backend service modules accept `db_path: str = ""`
and capture it once at registration via `_resolved_db_path` (with lazy
fallback to `resolve_database_path()`). The remaining work is threading the
injected path from the ~20 `chisurf/` boundary callers that still call
`resolve_database_path()` directly:

1. **Measure the boundary surface.** `grep -rn 'resolve_database_path' chisurf/ --include='*.py' -l`
   returns ~20 files (database_connector, project_browser, spectra_downloader,
   dyes/forster, tttr_channeldefinition, etc.). Each is a `chisurf/` file, so
   the edit is "delete the resolver call, accept the injected arg" — never
   change mmfdb internals.
2. **Pick the highest-leverage caller first** — `chisurf/core/mmfdb_services.py`
   and `chisurf/plugins/core/database_connector/services.py` are the composition
   roots that construct `MFDatabase` for the GUI. Thread a resolved path (or
   `SessionContext.db`) through them.
3. **Add a guard test** asserting no production handler opens its own
   database connection (the hermetic harness already prevents the real user DB
   from being touched in tests).
4. **Confirm order-independence** — the `_resolved_db_path` module global
   leaks between tests (same as the old `resolve_database_path()`); a
   `monkeypatch`/fixture reset in `conftest.py` would make the suite
   order-independent.
