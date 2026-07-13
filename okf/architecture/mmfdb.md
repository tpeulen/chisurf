---
type: Architecture
title: MMFDB — Metadata / Provenance Store
description: SQLite-backed metadata and provenance store with canonical tables generated from mmCIF dictionaries.
resource: modules/mmfdb/src/mmfdb/
tags: [mmfdb, metadata, provenance, sqlite, mmcif]
timestamp: '2026-07-06T00:00:00Z'
---

# Purpose

`modules/mmfdb/src/mmfdb/` is the vendored SQLite-backed metadata and
provenance package. It is versioned with migrations, has ACL/auth, and models a
provenance DAG (operations -> artifacts -> edges). MMFDB dictionary files
(`*.dic`) live in `modules/mmfdb/src/mmfdb/data/`; the old
`chisurf/core/mmfdb/data` dictionary copy has been removed.

MMFDB Admin is part of this package as the optional `mmfdb.admin` application
(`modules/mmfdb/src/mmfdb/admin`). The ChiSurf `core/mmfdb_admin` plugin is a thin
manifest/wrapper shim around `mmfdb.admin`, not the owner of the implementation.

ChiSurf imports `mmfdb` directly. The prerelease `chisurf.core.mmfdb`
compatibility facade and its meta-path submodule aliasing are removed, so the
standalone package has one canonical module identity and can later move to
`github.com/fluorescence-tools/mmfdb` without another application-wide cutover.

Current extraction boundary: runtime path/default-user/object-store
configuration, result registration, generic payload serialization, project
curve-array encoding, and seed Förster overlap/radius calculations are MMFDB
local. The package has no ChiSurf imports; host-specific fit serialization and
workflow execution enter through explicit ChiSurf-owned adapters.

The fluorophore reference `spectra.db` used by seeded/reference imports is now
bundled under `modules/mmfdb/src/mmfdb/data/`. `MFDatabase.import_reference_set()`
uses that package-local database by default or an explicit
`MMFDB_REFERENCE_SPECTRA_DB` override.

Known design issue addressed during extraction: probe-type reseeding now uses a
non-destructive upsert instead of `INSERT OR REPLACE`, preserving `probe_types`
primary keys referenced by imported probes.

Structured sample creation uses the single SQLite repository/DAO path; the
parallel SQLAlchemy ORM adapter is removed. Full-description reads expose a
stable shape, including nullable condition fields when no condition row exists.

# Schema authority

The canonical tables are **generated from mmCIF dictionaries** (`data/*.dic` —
the wwPDB/PDB-IHM family plus the local `mmfdb_flr_ext.dic`) by
`schema_from_dictionary.py`. Treat the `.dic` dictionaries as the schema
authority: change them and regenerate; do **not** hand-edit generated DDL.

## Dictionary programming rules

For flrCIF/PDBx fields the bundled `.dic` files are the source of truth; Python may
reflect tables and call repository helpers but must not become the authority for
item names, schema aliases, enums, defaults, descriptions, or mandatory flags. When
upstream flrCIF is incomplete, add store-local definitions to
`modules/mmfdb/src/mmfdb/data/mmfdb_flr_ext.dic` **before** writing Python that
persists or validates the field. Every persisted dictionary item declares
`_item.name`, `_item.category_id`, `_item_type.code`, `_item.mandatory_code`,
`_item_enumeration.value` (controlled values), `_item_default.value` (defaults), and
`_mmfdb_schema.table_name` / `_mmfdb_schema.column_name`.

**Idempotent identity rows.** Rows representing identity-like objects are looked up
by their natural key before insert (e.g. chemical descriptors keyed by
`(descriptor_type, descriptor, program, program_version)`; vocabulary rows by
declared name). Prefer a DB uniqueness constraint; where legacy schema makes that
impractical, repository code provides an idempotent upsert and tests prove repeated
writes reuse the same row. A dictionary change is not complete until tests prove
items map to live columns, enums/defaults drive behaviour, and repeated writes do
not duplicate identity rows.

# Package layout

The package (`modules/mmfdb/src/mmfdb/`) is organized into concern subpackages,
not a flat module list. The root `mmfdb` import is deliberately shallow: it
exports `MFDatabase` lazily plus runtime configuration. Feature APIs are reached
through explicit modules rather than being eagerly re-exported.

Dependency direction is inward: pure models/configuration → schema/store → the
SQLite repository → use-case API → admin/RPC transports; optional adapters sit
at the outside. `request_context.py` gives transports one request-scoped
database/principal lifetime, so the versioned API does not open or authenticate
twice.

- `schema/` — dictionary-driven schema engine: `schema`, `schema_from_dictionary`,
  `dictionary_schema_map`, `pdbx_metadata`, `dao` (`DictionaryDao`),
  `vocabulary_loader`, `docs_generator`, `_sqlutil`.
- `store/` — persistence primitives: `object_store`, `payload_codec`,
  `payload_models`, `database_resolver`, `transactions`.
- `provenance/` — DAG + results: `lineage`, `graph`, `result_registry`,
  `compute_spec`, `operation_parameters`.
- `samples/` — sample domain: `sample_manager`, `sample_requests`,
  `external_refs`, `reagents`, `importer`, `seed_data`.
- `lifecycle/` — state/events/audit: `lifecycle`, `event_log`, `events`, `staleness`.
- `security/` — identity & access: `auth` (Principal, token→principal, ACL/permissions,
  sessions), `credentials`, `session`, `boundary_validation`, `base`, plus the
  **provider-based authentication** layer (PRD-59, local + LDAP only): `auth_providers`
  (`AuthProvider` protocol + `LocalAuthProvider` / `LdapAuthProvider`) and `login` (the
  `login()` orchestrator that
  authenticates → resolves/JIT-provisions the MMFDB user via `flr_sample_users.auth_provider`/
  `external_id` → maps directory groups → mints the session). The `mmfdb.security.auth.login`
  RPC and `mmfdb-admin auth` CLI both route through `login()`; `ldap3` is an optional/lazy
  `[ldap]` dependency, so `security/` still imports with only `src` on the path.
- `project/` — `project_archiver`.
- `adapters/` — host-neutral bridges to external formats/systems. `chinet`
  accepts injected parameter-registry and fit-state conversion functions;
  ChiSurf supplies those from its thin adapter.
- `queries/` — per-concern **`MFDatabase` mixins** (god-class breakup, PRD-26):
  `artifacts` (artifact/operation/edge/provenance-graph core), `analysis`,
  `samples`, `setups`, `probes`, `objects`, `parameters`, `protocols`, `studies`,
  `branches`, `lifecycle`, `experiments`, `users`. `repository.py` is a thin
  composition of these over `self.conn`/`self.dao`/`self.lineage` — reduced from
  ~6,400 lines to ~1,650 (init/connection/properties, migration, audit,
  vocabulary, experiment key-values, pdbx metadata remain as the core).
- `admin/` — the admin RPC service (`backend/`, `cli/`); chisurf-free and import-
  clean. The chisurf-coupled admin **GUI** lives in the ChiSurf plugin
  (`chisurf/plugins/core/mmfdb_admin/gui/`), not in the package.
- `data/` — bundled `.dic` dictionaries and config JSON.

The package has its own **hermetic, standalone test suite** at
`modules/mmfdb/tests/` (isolated via `MMFDB_SETTINGS_DIR`, no chisurf import) —
run it with `cd modules/mmfdb && PYTHONPATH=src pytest`. ChiSurf↔MMFDB
integration tests (admin GUI client, chinet/parameter-registry alignment, etc.)
stay in the ChiSurf `test/` tree. This boundary is enforced by construction:
the core package imports cleanly with only `src` on the path (PRD-24).

# API

`api.py` is the transport-agnostic function API for the store. Direct calls own
one temporary `APIRequestContext`; RPC transports bind a caller-owned context so
all work in one request shares the same database and authenticated principal.

## Data access — one engine, raw SQL is an antipattern

CRUD goes through the dictionary-driven **`DictionaryDao`** (`db.dao`), which
whitelists every identifier against the reflected schema and binds all values:
`db.dao.insert / upsert / get / list / update / soft_delete`. New code **must**
use it. Hand-written / f-string / raw `db.conn.execute("INSERT …")` SQL for
create-read-update-delete is an **antipattern** — it duplicates the one engine,
bypasses schema-whitelisting and audit-column handling, and drifts from the
`.dic` source of truth (PRD-26/INC-05). Any remaining raw-SQL CRUD in the
repository is legacy debt being migrated onto the DAO, not a pattern to copy.

Raw SQL is reserved for genuinely **bespoke** statements the single-table DAO
cannot express — multi-table joins, graph/lineage traversal, aggregates, export,
`INSERT … SELECT` bulk copies, conditional/multi-column `WHERE` updates,
composite-key soft-deletes on PK-less junctions, resurrecting updates (reset
`deleted_at`), and intentional hard deletes — kept as organized methods (or
`# raw`-flagged blocks) on the relevant concern mixin. When in doubt: a
single-table CRUD shape is DAO; a join/traversal/bulk/conditional is raw.
`DictionaryDao.insert` works on keyless tables too (UNIQUE-only junctions like
`mmfdb_group_member`): with no resolvable primary key it returns the last rowid
rather than raising, so even junctions can be written through the DAO.

# Deployment & connection modes

MMFDB runs two ways. **Embedded** (default): ChiSurf opens the per-user SQLite
database in-process and registers the admin RPC services on a local dispatcher —
no server, no socket. **Standalone**: `mmfdb serve` runs a dependency-free WSGI
HTTP server exposing JSON-RPC at `/rpc`, a browser admin UI at `/login`, a
bounded streaming object endpoint at `/objects`, and `/healthz`. A Docker image
(`modules/mmfdb/Dockerfile`) and Compose file (`docker-compose.mmfdb.yml`) run
this on loopback `:8080` with a persistent data volume and a read-only rootfs.
The SQL backend is SQLite by default or PostgreSQL when a `MMFDB_DATABASE_URL` /
`database.url` is configured (runtime-only: no bootstrap/migration on Postgres).

ChiSurf's `MMFDBClient` (in the `mmfdb_admin` plugin) picks a transport from the
`mmfdb.client.mode` setting: `embedded` (local ZMQ / in-process) or
`remote` (HTTP JSON-RPC to a standalone `base_url`). Remote URLs must be HTTPS
unless loopback. The `mmfdb.status` RPC reports the running database's
`database_dialect`, a redacted `database_location`, and `object_store_backend`;
the mmfdb-admin **Overview** panel renders the client mode, endpoint, database
type, and object store so the operator can see which database they are editing.

The browser admin UI (`mmfdb/webadmin/`) mirrors the Qt admin dock-for-dock
against the same backend handlers. Beyond the generic entity tables it ships an
**Optical components** surface (`webadmin/optical_components.py`, routes
`/optical-components*`) that is a 1:1 port of the Qt `OpticalComponentDock`:
component-type tabs (fluorophore / filter / dichroic / detector / light source),
the curation toolbar (import reference set, approve, reject, AI triage, review
queue, find duplicates), a searchable status-filtered checkbox table, an overlaid
spectrum plot rendered as **inline SVG with presentation attributes only** (no
JS, satisfies the `default-src 'self'` CSP), a read-only detail panel, and a
duplicate review-and-merge page. Two pure-Python helpers were moved into the
standalone package so the web UI needs no ChiSurf import: the deterministic
triage checker (`admin/backend/triage_checks.py`, wired into `register_services`
as the default `deterministic_checks`) and the duplicate grouping model
(`admin/backend/duplicate_grouping.py`).

# Object store & provenance-aware readers

MMFDB has a content-addressed **object store** (`object_store.py`): blobs are
stored under `{root}/{md5[:2]}/{md5[2:4]}/{md5}` with streaming-MD5 dedup and
refcounting, shared across users, `root` defaulting to `~/.chisurf/objects`.
Blobs are addressed by UUID; the repository exposes
`put/get/get_info/delete/list_object` and the admin app surfaces them as
`mmfdb.objects.*` RPC methods and an "Objects" browser.

Experiment readers can record provenance automatically. The `ExperimentReader`
base (`chisurf/core/experiments/core/reader.py`) has provenance hooks
(`operation_type`, `artifact_kind_source`/`_derived`, and instance `db` /
`object_store` / `record_provenance`). When `get_data()` runs with a `db` set it:
registers the source file(s) as objects, calls the subclass `read()`, serializes
the derived curves to a language-agnostic JSON+base64 envelope
(`chisurf/core/experiments/core/serialize.py`), registers those, and records an
`mmfdb_operation` linking source → derived artifacts. The provenance DAG is
`source object → raw_data artifact → operation → processed_data artifact →
derived object`. Provenance is **opt-in and backward compatible**: readers still
work when `db` is unset, and direct `read()` calls skip provenance entirely.
TCSPC (TTTR + curve), PDA, PCH, and FCS readers declare provenance operation
types. This object-store/provenance layer is the foundation the MMFDB overhaul
(the [PRDs](/prds/index.md)) builds on.

# Related work

Curation of the fluorophore database (GUI/RPC/CLI) now lives in the optional
`mmfdb.admin` application. ChiSurf discovers that app through the
`core/mmfdb_admin` plugin shim. MMFDB is also the prototype for the broader
fdb4chembio (NFDI4Chem) fluorescence databank effort.

# Note on OKF

This [OKF](/index.md) bundle is a plain-markdown knowledge layer that sits
*beside* the code; MMFDB is the runtime provenance store. OKF could serve as
an interchange/export format for MMFDB provenance in the future.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
