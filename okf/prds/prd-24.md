---
type: PRD
prd: "24"
title: "PRD-24: Extract MMFDB into a Standalone Package"
description: Moves MMFDB (schema, dictionary, generator, repository/API, server, admin backend) out of chisurf into an independent module with a stable public API and no chisurf imports.
status: done
phase: "5"
resource: modules/mmfdb/src/mmfdb/
tags: [prd, mmfdb]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
PRD-24 extracts MMFDB — schema and dictionary and generator, repository and API, object store, result registry, auth, server, and admin backend — out of `chisurf` into an independent `modules/mmfdb` package with a stable public API and no `chisurf` imports, forcing a clean boundary and enabling reuse and independent testing. Settings and paths the package needs (database path, object-store root, default user) are injected rather than read from chisurf settings, and a thin chisurf adapter wires the application's config and GUI to the package API. The package is independently installable and carries its own hermetic test suite. It is sequenced last, after the interfaces it depends on have stabilized, so the move preserves stable interfaces instead of relocating churn.

# Status
Done. The standalone package is host-neutral and independently buildable/tested;
ChiSurf uses thin adapters and direct `mmfdb` imports, and the transitional
compatibility facade is deleted.

# Goal
Move MMFDB (schema, dictionary, generator, repository/API, server, admin backend) out of `chisurf` into an independent vendored `modules/mmfdb` package with a stable public API and **no `chisurf` imports**. This forces a clean boundary, enables reuse and independent testing, and prepares a later move to its own dedicated repository.

# Background
This was originally listed as deferred cleanup: move MMFDB out of `chisurf` into `modules/` — own the schema, repository/API layer, MMFDB server, and admin backend — after the current overhaul is basically finished so the extraction can preserve stabilized interfaces instead of moving churn. The current prerelease direction is a harder cut: vendor the package under `modules/mmfdb` first, then remove the remaining ChiSurf imports and publish it as its own repository.

# When
**Last** — after the operation/transformer spine ([PRD-11](prd-11.md) / [PRD-16](prd-16.md)), the identity/DI work ([PRD-17](prd-17.md) / [PRD-18](prd-18.md)), and the dictionary/migration cleanup ([PRD-19](prd-19.md)) have stabilized the interfaces. Extracting earlier just moves churn.

# Design
- `modules/mmfdb/` owns: `schema` + `.dic` + generator, `repository`/`api`, `object_store`, `result_registry`, `auth`, `server`, and the admin backend. The GUI admin *frontend* may stay in chisurf (Qt) but talks only through the package's RPC/API.
- **No `chisurf` imports** in the package. Settings/paths it needs (db path, object-store root, default user) are injected ([PRD-17](prd-17.md) `SessionContext` / explicit config), not read from `chisurf.core.settings`.
- A thin `chisurf` adapter wires chisurf settings/GUI to the package API.
- The package is independently installable and testable (its own hermetic test suite from [PRD-18](prd-18.md)).

# Tasks
1. Inventory and cut the chisurf→mmfdb dependency edges; replace `chisurf.core.settings` reads with injected config (depends on [PRD-17](prd-17.md) / [PRD-18](prd-18.md)).
2. Move the modules; keep import shims in `chisurf.core.mmfdb` only as a transitional re-export, then delete.
3. Package metadata + standalone test run (uses the hermetic harness).
4. chisurf adapter: config/GUI ↔ package API.
5. CI: the package builds and tests on its own.

# Definition of Done
- [x] MMFDB source package moved to `modules/mmfdb/src/mmfdb`; no compatibility
  package remains under `chisurf.core`.
- [x] `modules/mmfdb` is a standalone package with no `chisurf` imports; config
  and host-only workflow functions are injected.
- [x] chisurf uses it via thin adapters; transitional import shims removed.
- [x] Package builds and its hermetic tests pass independently.

# Definition of Clean
No `chisurf` imports in the package; config injected not global; the hermetic test harness ([PRD-18](prd-18.md)) travels with the package; delete shims, don't alias.

# Relationships
- Capstone of the architecture track; requires injected identity/config from [PRD-17](prd-17.md) and the injected database plus hermetic tests from [PRD-18](prd-18.md).
- Benefits from the self-contained dictionary-driven schema of [PRD-19](prd-19.md).
- Targets the [MMFDB target](/specs/mmfdb.md); the package talks over the [RPC target](/specs/rpc.md) and removes [runtime globals](/architecture/runtime-globals.md) dependencies.
