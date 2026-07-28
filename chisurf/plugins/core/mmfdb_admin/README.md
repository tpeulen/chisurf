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

The GUI entrypoint is `mmfdb.admin.gui.tool:MMFDBWidget`; `chisurf.plugins.core.mmfdb_admin.gui.*` remains as compatibility wrappers.
The widget uses `MMFDBClient`, which can talk to a ZMQ JSON-RPC endpoint or an
in-process dispatcher for local desktop use. The UI contains dedicated views and
docks for:

- generic entity editing and metadata display
- samples, experiments, studies, protocols, lifecycle state, calibrations, reagents,
  and pipelines
- connection and authentication
- optical components and fluorophore metadata
- provenance graph inspection

GUI connection fields are represented by `modules/mmfdb/src/mmfdb/admin/gui/connection_auth.view.json`.
Optical-component forms are represented by view JSON files in
`modules/mmfdb/src/mmfdb/admin/gui/optical_components/`.

New and refactored MMFDB Admin panels should use JSON view specs and AutoForm
wherever the interaction is a form, toolbar, table, wizard, info block, or
detail panel. If a required control shape is missing, implement it in the shared
AutoForm/dataspec layer first, then consume it from MMFDB Admin. Do not add new
one-off Qt form builders for ordinary schema-driven UI.

## API, CLI, And RPC

| Surface | Entry point / method | Purpose |
| --- | --- | --- |
| GUI | `mmfdb.admin.gui.tool:MMFDBWidget` | Desktop administration tool. |
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
- `modules/mmfdb/src/mmfdb/admin/gui/`: Qt views, clients, docks, generic forms, lifecycle/protocol/study/reagent
  views, optical-component editors, and provenance graph widgets.
- `modules/mmfdb/src/mmfdb/admin/gui/autoform_entity_form.py`: AutoForm-backed entity detail form used by
  schema-driven entity docks.
- `gui/*.view.json` and `modules/mmfdb/src/mmfdb/admin/gui/optical_components/*.view.json`: declarative view
  specs rendered through AutoForm.
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
- Several workflow panels still contain manual Qt table/form code. Migrate these
  incrementally to JSON view specs and shared AutoForm primitives.
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
- `modules/mmfdb/src/mmfdb/admin/gui/tool.py`
- `modules/mmfdb/src/mmfdb/admin/gui/autoform_entity_form.py`
- `test/`
- `docs/CONTRACT.md`
- `docs/STATUS.md`
