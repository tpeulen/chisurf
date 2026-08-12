---
type: PRD
prd: "17"
title: "PRD-17: Canonical Identity / Session Context"
description: Resolves the active user and target database once at the boundary into a single SessionContext threaded explicitly through registration, browse, and ownership code.
status: in-progress
phase: "1"
resource: modules/mmfdb/src/mmfdb/
tags: [prd, mmfdb]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
PRD-17 eliminates divergent identity resolution — where registration stamped one user while read handlers resolved another — that caused ownership and visibility bugs (for example, "Mine" returning zero results). It introduces a single `SessionContext` dataclass carrying `user_id`, database handle, admin flag, groups, and auth principal, constructed once per entry point (GUI launch or RPC dispatch). All MMFDB read and write APIs take the context explicitly, and the scattered per-module current-user resolvers are removed in favor of one canonical resolver used by both reads and writes.

# Status
In-progress (updated 2026-08-09). The canonical current-user resolver landed
and the "Mine returns 0" ownership/visibility bug is fixed. In the **float
zone**, identity resolution is canonicalized: `_resolve_active_user_id()` in
`result_registry.py` and `_default_user_id()` / `_resolve_owner_id()` in
`services.py` all delegate to `mmfdb.security.session.configured_default_user_id()`.
`register_result()` accepts `session: SessionContext | None` and uses it when
provided. The remaining DoD ("`resolve_session()` has production call sites,
threaded from entry points") is **boundary work**: ~10 `chisurf/` modules
still call `configured_default_user_id()` or construct `SessionContext`
inline rather than through `resolve_session()`.

# Goal
Resolve "who is the active user" and "which database" **once**, at the boundary, into a single `SessionContext` threaded explicitly through registration, browse, and ownership code — eliminating the divergent identity resolution that caused ownership/visibility bugs.

# Evidence (why)
"Active user" is resolved two ways: `register_*` stamps `cs_settings["mmfdb"]["default_user_id"]`; RPC handlers resolve the **auth principal** (anonymous for the in-process GUI). The mismatch made the dataset browser's "Mine" return 0 (the query resolved a different user than registration stamped) and forced ad-hoc "anonymous → default user" fallbacks in `datasets.browse` and `datasets.open`.

# Design
- A `SessionContext` dataclass: `user_id`, `db` (handle/path), `is_admin`, `groups`, `auth`. Constructed **once** per entry point: GUI launch (from settings / login) and RPC dispatch (from the auth principal, falling back to the configured default user *in one place*).
- All MMFDB read/write APIs take the context (or its `user_id`/`db`) explicitly: `register_result(..., session=ctx)`, `browse_datasets(..., session=ctx)`, ownership stamping, study/protocol scoping.
- Remove independent `_resolve_active_user_id()` calls scattered across `result_registry`, `tttr_setup_utils`, handlers — they all consult the one resolver behind the context.
- One **canonical current-user resolver** used by both reads and writes, so an artifact stamped by user X is always found under X's "Mine".

# Tasks
1. Define `SessionContext` + a single `resolve_session(auth=None)` (settings ⊕ auth) in `chisurf/core/mmfdb/session.py`.
2. Thread it through `register_result`/`register_raw_measurement`, browse/open handlers, ownership, and setup/sample resolution; delete the duplicate resolvers.
3. RPC dispatch builds the context once from auth (with the default-user fallback centralized here, not per handler).
4. Tests: write-then-read-as-same-user round trips under both logged-in and no-login modes; the two-user scoping still holds; no handler re-resolves identity independently.

# Definition of Done
- [ ] One `SessionContext` + one current-user resolver; no module re-resolves identity on its own.
- [ ] Registration owner and browse "own" scope always agree (no anonymous-fallback patches remain).
- [ ] Tests cover logged-in and no-login paths; two-user scoping intact.

# Definition of Clean
DI (context passed, not module-global); behavior-asserting tests (write→read same user); no swallowed identity mismatches.

# Relationships
- Subsumes the per-handler anonymous-fallback patches added in [PRD-10](prd-10.md).
- Pairs with [PRD-18](prd-18.md) — the SessionContext is the unit that gets dependency-injected.
- The injected identity/config becomes a prerequisite for [PRD-24](prd-24.md) package extraction.
- Targets the [MMFDB target](/specs/mmfdb.md); reduces reliance on [runtime globals](/architecture/runtime-globals.md).

# Where to pick this up

**Float-zone identity resolution is canonicalized; the boundary threading is
the open front.** In `modules/mmfdb/src/mmfdb/`, every resolver
(`_resolve_active_user_id` in `result_registry.py`, `_default_user_id` /
`_resolve_owner_id` in `services.py`) delegates to
`mmfdb.security.session.configured_default_user_id()`, and `register_result()`
accepts `session: SessionContext | None`. The remaining DoD ("`resolve_session()`
has production call sites, threaded from entry points") is boundary work:

1. **Wire `resolve_session()` at the entry points.** It currently has zero
   production call sites (only `test/fio/test_session_context.py`). Call it
   at GUI launch and RPC dispatch, construct the `SessionContext` once, and
   thread it through.
2. **Replace inline `SessionContext` construction.** `chisurf/plugins/ndxplorer/cli.py`
   and `chisurf/plugins/microscopy/imaging_common/base.py` build `SessionContext`
   inline — switch them to `resolve_session()`.
3. **Delete the duplicate `_resolve_active_user_id()` resolvers** in
   `chisurf/gui/widgets/wizard/tttr_channeldefinition/{tttr_detector_setups,tttr_channel_definition}.py`
   (boundary) so no module re-resolves identity on its own.
4. **Remove the anonymous→default-user fallback patches** in
   `datasets.browse`/`datasets.open` once the session is threaded.
5. **Tests:** write→read-same-user round trips under logged-in + no-login
   modes; two-user scoping intact.
