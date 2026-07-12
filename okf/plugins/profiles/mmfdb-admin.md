---
type: Plugin Profile
title: MMFDB Admin plugin
description: OKF profile for the MMFDB administration plugin.
resource: chisurf/plugins/core/mmfdb_admin/
tags: [plugins, mmfdb, provenance, rpc]
timestamp: '2026-07-06T00:00:00Z'
---

# Identity

| Field | Value |
| --- | --- |
| Plugin id | `mmfdb_admin` |
| Display name | `Tools:MMFDB Admin` |
| Categories | `Tools`, `Fluorescence`, `Database` |
| Version | `1.1.0` |
| State namespace | `mmfdb_admin` |
| Local README | `chisurf/plugins/core/mmfdb_admin/README.md` |

The manifest describes this as the administration surface for samples, experiments,
setups, raw/processed data, provenance, project archives, and fluorophore curation.

# Architecture Evidence

| Layer | Evidence |
| --- | --- |
| GUI | `modules/mmfdb/src/mmfdb/admin/gui/tool.py`, entity docks, lifecycle/protocol/study/reagent/calibration views, optical-component forms. |
| Backend services | `modules/mmfdb/src/mmfdb/admin/backend/services.py` plus auth, password, measurement, ndxplorer, and fluorophore service modules. |
| API placeholder | `api/` exists but no substantial public contract is visible from the file inventory. |
| CLI placeholder | `cli/` exists but the manifest exposes GUI and services, not a CLI command. |
| Tests | `test/test_*_handlers.py`, `test/test_*_view.py`, navigation, session SSO, and optical-component tests. GUI behavior coverage is tracked in `docs/GUI_TEST_COVERAGE.md`. |

The manifest lists 144 `mmfdb.*` RPC methods. `modules/mmfdb/src/mmfdb/admin/backend/services.py` defines
`register_services` and many handler functions for sample, protocol, study,
reagent, calibration, lifecycle, project, object, and dataset operations.

## Dictionary-driven dock architecture

The entity docks are generated, not hand-built. `gui/entity_registry.py` holds
**wiring only** (`EntitySpec`: RPC namespace, dictionary category, id field,
display group) with no field/column content. `gui/entity_schema.py` derives
`FieldSpec`s (label, widget, choices, required, tooltip, FK target) purely from
the mmCIF/flrCIF `.dic` dictionary via `MmcifDictionary` + `DictionarySchemaMap`,
so field types, enumerations, descriptions, and mandatory flags come from the
dictionary — the same authority as the schema itself. `gui/mixins.py` composes
behaviour (schema, CRUD, table, form, cross-link, toolbar) and `gui/entity_dock.py`
assembles one generic `EntityDock` per spec, grouped into logical categories.
Foreign keys are cross-linked: FK cells are clickable and jump to the target
dock's row, and detail forms render FKs as dropdowns; declared
`_item_linked.parent_name`/`child_name` links in the dictionary win, with an
`_id`-naming convention as fallback. When extending: add wiring to the registry
and the field metadata to the `.dic`, never a hardcoded field list. (`gui/tool.py`
remains large — the host-shell slimming that the dictionary-driven design enables
is not fully complete.)

UI direction: MMFDB Admin should use JSON view specs and AutoForm for ordinary
forms, detail panels, tables, wizard steps, and toolbars. When AutoForm lacks a
needed primitive, implement it in the shared AutoForm/dataspec layer first rather
than adding another one-off MMFDB Qt widget.

# Data And Provenance Impact

This is a P0 documentation target because it is the broadest MMFDB mutation and
inspection surface. It can create, edit, delete, browse, and validate database
entities used by provenance-aware workflows. Its docs must make clear which handlers
are mutating, which are read-only, and which operations are fail-loud versus
best-effort.

# Verification Surface

Focused test command:

```bash
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." python3 -m pytest chisurf/plugins/core/mmfdb_admin/test
```

Current full plugin-local suite status in the arm64 Qt environment is green:
111 passed, 2 warnings on 2026-07-06.

The wider MMFDB Admin plus adjacent database surfaces smoke set is also green
without the removed `modules/mmfdb_admin/src` import path:
`test/core/test_mmfdb_vendor_package.py`, `chisurf/plugins/core/mmfdb_admin/test`,
`chisurf/plugins/core/database_connector/test`, and
`chisurf/plugins/core/project_browser/test` reported 133 passed, 2 warnings on
2026-07-06.

The focused GUI/admin/database smoke command in `docs/GUI_TEST_COVERAGE.md`
reported 58 passed, 2 warnings on 2026-07-06 after adding raw/processed
Copy ID, Reveal/Open, provenance-seed, validation-status update, and confirmed
soft-delete coverage plus analysis Copy ID, Details, and provenance-seed
coverage.

The MMFDB client/integration/startup slice is green on the same path contract:
`test/plugins/test_mmfdb_client_integration.py`,
`test/plugins/test_ndxplorer_mmfdb_launcher.py`,
`test/plugins/test_provenance_graph_adapter.py`,
`test/fluorescence/test_pipeline_e2e.py`, and `test/startup/test_services.py`
reported 60 passed on 2026-07-06.

GUI coverage status:

- Headless interaction tested: workflow views for studies, protocols, lifecycle,
  calibrations, reagent lots, pipelines, the connection dialog, and core
  EntityDock paths for Samples, Sample Conditions, Entities, Probes, Label
  Positions, FRET Pairs, Experiments, Experiment Types, Setups, Detector
  Channels, PIE Windows, FCS Pairs, Devices, Users, Raw Data, Processing Runs,
  Processed Products, Analyses, Objects, Projects, and Branches.
  Sample Conditions, Experiment Types, and Devices include New-button create,
  auto-save update, and checked-row delete coverage.
  Branches include New-button create, auto-save update, and checked-row delete
  coverage. Users include New-button create, rename, checked-row delete, and
  built-in-user delete protection coverage.
  Raw Data and Processed Products include Copy ID, Reveal/Open,
  provenance-seed, validation-status update, and confirmed soft-delete coverage
  through the visible EntityDock. Analyses include
  Copy ID, Details drilldown with parameter/output-product tables, and
  provenance-seed coverage through the visible EntityDock.
  Objects include object-store-backed refresh, row selection, AutoForm load, Copy
  UUID, Reveal, and confirmed delete coverage through the visible Objects
  EntityDock.
  Measurements include sample-data-backed refresh and kind/search filtering over
  raw data, processing runs, and processed products.
  Provenance Graph includes sample-data-backed full-graph loading, edge-table
  population, node-editor graph loading, and edge-detail selection.
  Import / Export includes sample-data-backed validation, flrCIF preview, sample
  CIF export, sample-table export, and minimal CIF file import.
- Partially tested: spectra/optical components.
- Construction-only and behavior-untested: aggregate panels and remaining
  generic `EntityDock` mutation paths unless a narrower test says otherwise.

Construction-only entries are not done. Manual testing has shown failures in GUI
elements, so `docs/GUI_TEST_COVERAGE.md` is the source of truth for what must be
treated as untested.

MMFDB source now lives under `modules/mmfdb/src/mmfdb`; MMFDB Admin application code
now lives under `modules/mmfdb/src/mmfdb/admin` as the optional `mmfdb.admin` app.
The ChiSurf `core/mmfdb_admin` plugin is only a thin manifest/wrapper shim around
that application. The old `chisurf.core.mmfdb` namespace is only a transitional
facade, aliases loaded submodules to avoid duplicate class objects, and should
not be used for new plugin work.

Current MMFDB extraction boundary: runtime config, result registration, generic
payload serialization, project curve-array encoding, and seed Förster
overlap/radius calculations are MMFDB local. Remaining ChiSurf-specific imports
are in ChiNet adapter code. The fluorophore reference `spectra.db` for
seeded/reference imports is bundled in `modules/mmfdb/src/mmfdb/data/` and can be
overridden with `MMFDB_REFERENCE_SPECTRA_DB`.

# Documentation Work

- Keep `chisurf/plugins/core/mmfdb_admin/README.md` current as the user-facing overview.
- Extend `docs/CONTRACT.md` from method-family coverage to per-method schemas for high-risk mutations.
- Add `docs/WORKFLOWS.md` for common admin tasks: browse sample, edit setup, inspect provenance, import/export project.
- Keep `docs/STATUS.md` synchronized with manifest/service drift findings.
- Keep `docs/GUI_TEST_COVERAGE.md` synchronized with real headless GUI tests.
- Explicitly document destructive actions, auth/session assumptions, and user-safety constraints.
- Continue migrating manual GUI panels to AutoForm JSON specs, starting with simple
  browse/list panels that fit the shared table primitive.
