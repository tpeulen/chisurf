# MMFDB Admin

MMFDB Admin is the main ChiSurf administration surface for the Multiparametric
Fluorescence Database. It lets users and maintainers inspect and manage samples,
experiments, setup definitions, raw and processed artifacts, provenance, project
archives, users, permissions, fluorophore curation, and workflow metadata.

## Status

| Field | Value |
| --- | --- |
| Plugin id | `mmfdb_admin` |
| Menu path | `Tools:MMFDB Admin` |
| Category | `Tools`, `Fluorescence`, `Database` |
| Maturity | `active` |
| Architecture | `client-server` |
| MMFDB | `full provenance` |

The plugin is actively used as a GUI and JSON-RPC service surface. Its manifest is
the discovery contract for most methods, but not every registered backend method is
currently declared there; see `docs/STATUS.md`.

## User Workflows

1. Browse and edit MMFDB entities: samples, experiments, users, devices, experiment
   types, setup definitions, studies, protocols, reagent lots, calibrations, and
   pipeline metadata.
2. Inspect data and provenance: list raw/processed artifacts, trace processed data,
   browse datasets, open dataset payloads, and inspect graph relationships.
3. Curate scientific metadata: manage probes, FRET pairs, PDBx/mmCIF metadata,
   fluorophore records, optical components, and quality/status lifecycle state.
4. Administer database state: authenticate users, inspect sessions, manage groups
   and permissions, import/export data, create backups, and reset from the source
   database when intentionally requested.

## Inputs And Outputs

| Kind | Formats | Notes |
| --- | --- | --- |
| Input | MMFDB SQLite database | Resolved through `mmfdb.database_resolver.resolve_database_path()`. |
| Input | PDBx/mmCIF or FLR CIF import files | Routed through import/export handlers where supported. |
| Input | Object-store payloads | Binary and path-based object registration are exposed through `mmfdb.objects.*`. |
| Output | MMFDB rows | Samples, experiments, users, setup definitions, provenance records, artifacts, permissions, and workflow metadata. |
| Output | Files | Table exports, sample exports, backups, archive manifests, and opened dataset paths. |

Mutating workflows should be treated as real database writes. Tests patch the
database resolver to a temporary `MFDatabase`; production calls use the configured
source/user database resolution.

## UI Surface

The window is the native emtk app `chisurf.plugins.core.mmfdb_admin.gui.app:make_app`
(`entrypoints.emtk`) over the Qt-free view models in `gui/native/` and the view
specs `gui/admin.view.json`, `gui/admin_panels.view.json` and
`gui/entity_extras.view.json`; the Qt `MMFDBWidget` is retired. The app uses
`MMFDBClient`, which can talk to a ZMQ JSON-RPC endpoint or an in-process
dispatcher for local desktop use. Its panels cover:

- generic entity editing and metadata display
- samples, experiments, studies, protocols, lifecycle state, calibrations, reagents,
  and pipelines
- connection and authentication
- optical components and fluorophore metadata
- provenance graph inspection

The login dialog's fields are `gui/connection_auth.view.json`; the optical-component
detail forms are the view JSON files in `gui/optical_components/`.

New MMFDB Admin panels are view specs drawn by emtk. If a control shape is
missing, add it to emtk (with tests) first, then consume it here.

## API, CLI, And RPC

| Surface | Entry point / method | Purpose |
| --- | --- | --- |
| GUI | `chisurf.plugins.core.mmfdb_admin.gui.app:make_app` | Desktop administration tool (emtk). |
| Service registration | `mmfdb.admin.backend.services:register_services` | Registers MMFDB admin JSON-RPC handlers. |
| Python client | `mmfdb.admin.gui.client:MMFDBClient` | GUI-facing wrapper around JSON-RPC calls. |
| CLI | None declared in `manifest.json` | `cli/` exists as a package placeholder. |
| RPC | `mmfdb.*`, `mmfdb.v1.*`, `raw_data.*`, `processed_data.*`, `processing.*`, `provenance.*`, `archive.*` | Main service contract; see `docs/CONTRACT.md`. |

## Architecture

- `manifest.json`: plugin identity, GUI/service entrypoints, state namespace, and
  declared RPC method names.
- `modules/mmfdb/src/mmfdb/admin/backend/services.py`: main registration hub for `mmfdb.*`, `mmfdb.v1.*`,
  raw/processed data, provenance, object-store, dataset, import/export, backup, and
  archive handlers.
- `backend/auth_services.py`: login/session, groups, and permissions.
- `backend/measurement_services.py`: measurement/raw/processed-data handlers.
- `backend/ndxplorer_services.py`: ndX handoff/query handlers.
- `backend/fluorophore_services.py`: fluorophore curation handlers.
- `gui/app.py`: the emtk window (menu bar, rail, status bar, spectra plot, provenance graph).
- `gui/native/`: the Qt-free view models (`model.py` AdminModel, `entity.py`, `panels.py`,
  `spectra.py`, `provenance.py`, `dialogs.py`).
- `gui/*.view.json` and `gui/optical_components/*.view.json`: the declarative view specs.
- `test/`: focused handler, view, auth/session, navigation, and optical-component
  tests.

The backend currently opens `MFDatabase(resolve_database_path())` inside handlers.
Tests patch that resolver to isolate writes.

## MMFDB And Provenance

MMFDB Admin is a full MMFDB read/write surface. It can:

- create and mutate samples, experiments, devices, users, groups, permissions, setup
  definitions, studies, protocols, reagent lots, calibration records, pipelines, and
  fluorophore records
- register raw and processed artifacts
- store/retrieve object-store payloads
- record and traverse versioned `mmfdb.v1.*` operation/artifact/provenance graphs
- open datasets and export/import table, sample, project, and archive data

Authentication and ACL enforcement are mixed by method family. Versioned
`mmfdb.v1.*` calls enforce authentication before delegating to `mmfdb.api`.
Some local GUI flows support an anonymous in-process client by resolving the
configured default user. Destructive operations such as delete, backup reset, and ACL
changes must be documented and tested explicitly before broad use.

## Verification

Run the focused plugin tests:

```bash
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." python3 -m pytest chisurf/plugins/core/mmfdb_admin/test
```

Useful narrower slices while editing docs or handlers:

```bash
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." python3 -m pytest chisurf/plugins/core/mmfdb_admin/test/test_admin_handlers.py
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." python3 -m pytest chisurf/plugins/core/mmfdb_admin/test/test_session_sso.py
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." python3 -m pytest chisurf/plugins/core/mmfdb_admin/test/test_optical_components.py
```

## Limitations And Open Work

- `docs/CONTRACT.md` documents method families, but individual request/response
  schemas still need to be filled in for high-risk mutations.
- Registered fluorophore RPC methods and `mmfdb.auth.change_password` are not declared
  in the current manifest.
- The retired `sample_database` plugin is not a supported RPC namespace; all new
  callers should use `mmfdb.*` or `mmfdb.v1.*`.
- Auth/ACL behavior should be reviewed per method before claiming a uniformly secure
  contract.

## Related Files

- `manifest.json`
- `modules/mmfdb/src/mmfdb/admin/backend/services.py`
- `backend/auth_services.py`
- `backend/measurement_services.py`
- `backend/ndxplorer_services.py`
- `backend/fluorophore_services.py`
- `modules/mmfdb/src/mmfdb/admin/gui/client.py`
- `gui/app.py`, `gui/native/`
- `test/`
- `docs/CONTRACT.md`
- `docs/STATUS.md`
