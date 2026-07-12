# MMFDB extraction state

Current state as of 2026-07-11:

- Source package moved to `modules/mmfdb/src/mmfdb`.
- MMFDB dictionaries (`*.dic`) live under `modules/mmfdb/src/mmfdb/data/`; the
  old `chisurf/core/mmfdb/data` copy has been removed.
- MMFDB Admin lives inside the MMFDB package at `mmfdb.admin` as the optional admin
  application. The ChiSurf `core/mmfdb_admin` plugin is a thin manifest/wrapper
  shim around `mmfdb.admin`.
- ChiSurf package discovery includes `mmfdb*` from `modules/mmfdb/src`.
- ChiSurf imports `mmfdb` directly; the former `chisurf.core.mmfdb` facade and
  submodule aliasing are removed.
- MMFDB Admin, Database Connector, and Project Browser import `mmfdb` directly in
  their active backend/test paths. MMFDB Admin app code imports through
  `mmfdb.admin`.
- Structured sample creation uses the single SQLite repository/DAO path; the
  former parallel SQLAlchemy ORM adapter has been removed.
- Structured sample full-description reads have a stable raw-SQL fallback shape,
  including nullable condition fields when no condition row exists.
- Runtime path/default-user configuration lives in `mmfdb.config`; `mmfdb` no
  longer imports ChiSurf settings for database path, object-store root, or the
  default user.
- `mmfdb.result_registry` resolves through explicit DB arguments,
  `set_global_db`, or the MMFDB-configured database path; it no longer imports
  the ChiSurf `database_connector` singleton.
- `mmfdb.payload_models.GenericCurve` now serializes/deserializes plain curve
  arrays without importing ChiSurf `DataCurve`.
- `mmfdb.seed_data` computes seed Förster overlap/radius values locally and no
  longer imports ChiSurf fluorescence helpers.
- `mmfdb.project_archiver` encodes project curve arrays locally and no longer
  imports ChiSurf experiment serialization helpers.
- The fluorophore reference `spectra.db` is bundled under
  `modules/mmfdb/src/mmfdb/data/`; `MFDatabase.import_reference_set()` resolves
  that package-local file by default or an explicit `MMFDB_REFERENCE_SPECTRA_DB`.
- Probe-type reseeding uses a non-destructive upsert so imported probes keep
  valid `probe_types` foreign keys.
- The package root is shallow and intentionally exports only `MFDatabase` plus
  runtime configuration. Optional integrations and admin services are imported
  from their explicit submodules.
- The versioned API/RPC boundary shares one `APIRequestContext` (database and
  principal) for the lifetime of a request.
- Full schema reconciliation is an explicit migration (v41), not a side effect
  of every writable open; `readonly=True` is enforced by SQLite.
- ChiSurf-specific fit serialization, curation, Burst Selection, and pipeline
  functions are injected by the ChiSurf wrapper instead of imported by MMFDB.

The package core is independently import-clean. An AST guard rejects new
`chisurf` imports under `src/mmfdb`, and the standalone test suite runs with only
`PYTHONPATH=src`.

Next extraction steps:

1. Move/publish `modules/mmfdb` as its own repository when release ownership is
   decided.
