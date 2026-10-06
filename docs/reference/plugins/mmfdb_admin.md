---
type: Plugin Reference
title: MMFDB Admin
description: 'Manage the Multiparametric Fluorescence Database (MMFDB): samples, experiments, setups, raw/processed data, provenance, and project archives.'
resource: chisurf/plugins/core/mmfdb_admin/
tags: [reference, plugins, mmfdb-admin, tools, system, fluorescence, database]
anchor: plugin-mmfdb_admin
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-mmfdb_admin)=
# MMFDB Admin

Manage the Multiparametric Fluorescence Database (MMFDB): samples, experiments, setups, raw/processed data, provenance, and project archives.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `mmfdb_admin` |
| Menu path | Tools → System → **MMFDB Admin** |
| Categories | Tools, System, Fluorescence, Database |
| Version | 1.1.0 |
| Surfaces | emtk, gui, services |
| State namespace | `mmfdb_admin` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Connection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Host | `host` | str |  |  | The MMFDB server: the host of the embedded server, or the base URL of a standalone one. Login connects here. |
| Port | `port` | int |  | 1 … 65535 | The server's command port (its publish port is the next one). |
| User | `user` | str |  |  | The MMFDB user to sign in as. |
| Password | `password` | password |  |  | The password. Not needed when this ChiSurf session is already signed in, or the account may sign in without one. Never stored. |

### Choose

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Value | `value` | choice |  | choices: `option_list` | The value to apply. |

### Change password

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| New password | `password_new` | password |  |  | The new password; shown as dots. |
| Confirm password | `password_confirm` | password |  |  | Type the new password again; it must match. |

### Jump to branch

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Operation ID | `operation_id` | str |  |  | The recorded operation the new branch starts at (required). |
| Branch name | `branch_name` | str |  |  | A name for the branch (optional; the server picks one when empty). |
| Description | `description` | str |  |  | What the branch is for (optional). |

### Overview

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| text | `text` | text |  |  | The connection (mode, endpoint, database, object store), the database's counts, and samples that lack a description. |

### All items

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Type | `type_filter` | choice |  | choices: `type_options` | Show one record type, or all. |
| search | `search` | str |  |  | Keep the rows that contain this text in any column. |

### Measurements

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Kind | `kind` | choice |  | choices: `kind_options` | Show one kind of record, or all. |

### Sample Metadata

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Sample | `sample_id` | choice |  | choices: `sample_options` | The sample whose metadata is edited. |

### Detail

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Key | `detail_key` | choice |  | choices: `key_options` | The key, from the mmCIF catalogue (type to filter it). |
| Value | `detail_value` | str |  |  | The value. |
| Known values | `suggested_value` | choice |  | choices: `value_options` | Values already stored for this key in any sample; picking one fills Value. |
| Details | `detail_details` | str |  |  | Notes about the value. |

### Spectra

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Component Type | `component` | choice |  | choices: `component_options` | Which kind of optical component to list. |
| Status | `status_filter` | choice |  | choices: `status_options` | List only the components with this curation status. |

### Provenance Graph

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Seed Type | `seed_type` | choice |  | choices: `seed_options` | The kind of record to start from. |
| Seed ID | `seed_id` | str |  |  | The record's id (a raw-data, processing-run, processed-data, analysis-run or parameter id). |
| details | `details` | text |  |  | The record of the picked edge or node. |

### Import / Export

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| File | `path` | str |  |  | The PDBx / PDB-IHM / FLR CIF file Import file reads (empty: it asks). |
| preview | `preview` | text |  |  | The import summary or the CIF preview. |

### eLabFTW connection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Endpoint | `endpoint` | str |  |  | The eLabFTW server's URL. |
| API key | `api_key` | password |  |  | Your eLabFTW API key. Kept in memory only and cleared when a connection attempt starts. |
| Timeout | `timeout` | float |  | 0.1 … 120.0 | Seconds to wait for the server. |
| Verify TLS certificates | `verify_tls` | bool |  |  | Check the server's certificate (leave on). |
| Allow plain HTTP (unsafe) | `allow_http` | bool |  |  | Only enable for an isolated trusted network. API keys are plaintext over HTTP. |

### eLabFTW

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| query | `query` | str |  |  | Search the remote experiments. |

### Import into MMFDB

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Existing | `conflict` | choice |  | choices: skip, update, error | What to do with an experiment that was imported before. |

### Export from MMFDB

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Experiment | `local_experiment` | choice |  | choices: `local_options` | The MMFDB experiment to export. |
| Mode | `export_mode` | choice |  | choices: create, update | Create a new remote entry, or update an existing one. |
| Remote ID | `remote_id` | int |  | 1 … 2147483647 | The remote entry to update (only for update). |

### Studies

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Scope | `scope` | choice |  | choices: `scope_options` | All studies, yours, or the public ones. |
| new_name | `new_name` | str |  |  | The name of the study to create. |
| member_type | `member_type` | choice |  | choices: `member_type_options` | A sample or an artifact. |
| member_id | `member_id` | str |  |  | The id of the sample or artifact. |
| field_key | `field_key` | str |  |  | The field to set. |
| field_value | `field_value` | str |  |  | Its value. |

### Protocols

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| new_category | `new_category` | choice |  | choices: `category_options` | measurement, processing or analysis. |
| new_operation_type | `new_operation_type` | str |  |  | The operation type whose parameters it records (optional). |

### Lifecycle

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Entity type | `entity_type` | choice |  | choices: `type_options` | The kind of entity (each has its own states). |
| Entity ID | `entity_id` | str |  |  | Its id. |
| Transition to | `to_state` | choice |  | choices: `to_options` | The states the entity may move to from its current one. |
| Reason | `reason` | str |  |  | Why (recorded in the history). |

### Register calibration value

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Type | `new_type` | choice |  | choices: `type_options` | What is calibrated. |
| Value | `new_value` | str |  |  | The value (a number). |
| Notes | `new_notes` | str |  |  | Where it comes from. |

### Reagent Lots

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Kind | `kind_filter` | choice |  | choices: `filter_options` | Show one kind of reagent, or all. |
| Show expired | `show_expired` | bool |  |  | Also list lots past their expiry date. |

### Add lot

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Kind | `new_kind` | choice |  | choices: `kind_options` | The reagent kind. |
| Lot # | `new_lot_number` | str |  |  | The vendor's lot number. |
| Vendor | `new_vendor` | str |  |  | Who sold it. |
| Expiry | `new_expiry` | str |  |  | When it expires. |

### Advanced — user & connection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Command port | `cmd_port` | int |  | 1 … 65535 | ZMQ command port. |
| Publish port | `pub_port` | int |  | 1 … 65535 | ZMQ publish port. |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Probe ID | `probe_id` | str |  |  | MMFDB probe identifier. |
| Name | `chromophore_name` | str |  |  | Detector name / model. |
| Category | `category` | str |  |  | Probe category (detector). |
| Type | `type_name` | str |  |  | Detector type. |
| Status | `verification_status` | str |  |  | Verification status. |
| Source | `source` | str |  |  | Provenance source. |
| Source ref | `source_ref` | str |  |  | Source reference / URL. |
| Verified by | `verified_by` | str |  |  | User who approved/rejected this detector. |
| Verified at | `verified_at` | str |  |  | Timestamp of the verification decision. |
| Cut-On (nm) | `cut_on` | str |  |  | Cut-on wavelength. |
| Cut-Off (nm) | `cut_off` | str |  |  | Cut-off wavelength. |
| Center Wavelength (nm) | `center_wavelength` | str |  |  | Center wavelength. |
| Bandwidth (nm) | `bandwidth` | str |  |  | Filter bandwidth. |
| Optical Density | `optical_density` | str |  |  | Optical density. |
| Abs max | `abs_max` | str |  |  | Absorption maximum (nm). |
| Em max | `em_max` | str |  |  | Emission maximum (nm). |
| QY | `qy` | str |  |  | Fluorescence quantum yield. |
| Extinction | `ext_coeff` | str |  |  | Molar extinction coefficient (M^-1 cm^-1). |
| Lifetime | `lifetime` | str |  |  | Fluorescence lifetime (ns). |
| D₂₅ | `d25` | str |  |  | Translational diffusion coefficient in water at 25 °C (µm²/s); used by the FCS diffusion/volume calculator. |
| Quality | `quality` | str |  |  | Quality grade: unknown / low / medium / high. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fluorophores.diffusion_reference` | no | List every probe carrying a diffusion coefficient D(25 °C, water). |
| `fluorophores.import_diffusion_reference` | no | Seed literature diffusion coefficients as probe properties. |
| `mmfdb.security.auth.change_password` | no |  |
| `mmfdb.security.auth.login` | no |  |
| `mmfdb.security.auth.logout` | no |  |
| `mmfdb.security.auth.me` | no |  |
| `mmfdb.security.auth.sessions.list` | no |  |
| `mmfdb.security.auth.sessions.revoke` | no |  |
| `mmfdb.status` | no |  |
| `mmfdb.samples.list` | no |  |
| `mmfdb.samples.get` | no |  |
| `mmfdb.samples.save` | no |  |
| `mmfdb.samples.delete` | no |  |
| `mmfdb.samples.search` | no |  |
| `mmfdb.samples.key_values.save` | no |  |
| `mmfdb.samples.full_description` | no |  |
| `mmfdb.samples.validate_export` | no |  |
| `mmfdb.samples.create_structured` | no |  |
| `mmfdb.sample_conditions.list` | no |  |
| `mmfdb.sample_conditions.get` | no |  |
| `mmfdb.sample_conditions.save` | no |  |
| `mmfdb.sample_conditions.delete` | no |  |
| `mmfdb.entities.list` | no |  |
| `mmfdb.entities.get` | no |  |
| `mmfdb.entities.save` | no |  |
| `mmfdb.entities.delete` | no |  |
| `mmfdb.probes.list` | no |  |
| `mmfdb.probes.get` | no |  |
| `mmfdb.probes.save` | no |  |
| `mmfdb.probes.delete` | no |  |
| `mmfdb.probes.optical_properties.get` | no |  |
| `mmfdb.probes.optical_properties.save` | no |  |
| `mmfdb.probes.positions.list` | no |  |
| `mmfdb.probes.positions.get` | no |  |
| `mmfdb.probes.positions.save` | no |  |
| `mmfdb.probes.positions.delete` | no |  |
| `mmfdb.fret_pairs.list` | no |  |
| `mmfdb.fret_pairs.get` | no |  |
| `mmfdb.fret_pairs.save` | no |  |
| `mmfdb.fret_pairs.delete` | no |  |
| `mmfdb.pdbx.suggest_keys` | no |  |
| `mmfdb.pdbx.validate_value` | no |  |
| `mmfdb.mock_data.populate` | no |  |
| `mmfdb.users.list` | no |  |
| `mmfdb.users.save` | no |  |
| `mmfdb.users.delete` | no |  |
| `mmfdb.devices.list` | no |  |
| `mmfdb.devices.get` | no |  |
| `mmfdb.devices.save` | no |  |
| `mmfdb.devices.delete` | no |  |
| `mmfdb.experiment_types.list` | no |  |
| `mmfdb.experiment_types.get` | no |  |
| `mmfdb.experiment_types.save` | no |  |
| `mmfdb.experiment_types.delete` | no |  |
| `mmfdb.experiments.list` | no |  |
| `mmfdb.experiments.get` | no |  |
| `mmfdb.experiments.save` | no |  |
| `mmfdb.experiments.delete` | no |  |
| `mmfdb.experiments.key_values.save` | no |  |
| `mmfdb.experiments.data.save` | no |  |
| `mmfdb.experiments.data.delete` | no |  |
| `mmfdb.setups.list` | no |  |
| `mmfdb.setups.get` | no |  |
| `mmfdb.setups.save` | no |  |
| `mmfdb.setups.delete` | no |  |
| `mmfdb.setups.validate` | no |  |
| `mmfdb.setups.detector_channels.list` | no |  |
| `mmfdb.setups.pie_windows.list` | no |  |
| `mmfdb.setups.fcs_pairs.list` | no |  |
| `raw_data.register` | no |  |
| `raw_data.list` | no |  |
| `raw_data.get` | no |  |
| `processing.burst_selection.record` | no |  |
| `processing.burst_selection.run` | no |  |
| `processing.burst_selection.get` | no |  |
| `processing.burst_selection.list` | no |  |
| `processed_data.register` | no |  |
| `processed_data.list` | no |  |
| `processed_data.get` | no |  |
| `provenance.edges.list` | no |  |
| `provenance.trace_processed_data` | no |  |
| `archive.burst_processing_manifest.export` | no |  |
| `mmfdb.import_file` | no |  |
| `mmfdb.export_sample` | no |  |
| `mmfdb.export_table` | no |  |
| `mmfdb.backup` | no |  |
| `mmfdb.reset_from_source` | no |  |
| `mmfdb.v1.samples.register` | no |  |
| `mmfdb.v1.samples.get` | no |  |
| `mmfdb.v1.samples.list` | no |  |
| `mmfdb.v1.experiments.register` | no |  |
| `mmfdb.v1.experiments.get` | no |  |
| `mmfdb.v1.experiments.list` | no |  |
| `mmfdb.v1.artifacts.register` | no |  |
| `mmfdb.v1.artifacts.get` | no |  |
| `mmfdb.v1.artifacts.list` | no |  |
| `mmfdb.v1.operations.record` | no |  |
| `mmfdb.v1.operations.record_with_artifacts` | no |  |
| `mmfdb.v1.operations.get` | no |  |
| `mmfdb.v1.operations.list` | no |  |
| `mmfdb.v1.operations.link_artifact` | no |  |
| `mmfdb.v1.operations.link` | no |  |
| `mmfdb.v1.operations.transition_status` | no |  |
| `mmfdb.v1.graph.traverse` | no |  |
| `mmfdb.v1.graph.upstream` | no |  |
| `mmfdb.v1.graph.downstream` | no |  |
| `mmfdb.v1.graph.export` | no |  |
| `mmfdb.v1.parameters.record` | no |  |
| `mmfdb.v1.parameters.get` | no |  |
| `mmfdb.v1.parameters.list` | no |  |
| `mmfdb.v1.chinet.sessions.save` | no |  |
| `mmfdb.v1.chinet.sessions.get` | no |  |
| `mmfdb.v1.chinet.sessions.list` | no |  |
| `mmfdb.v1.chinet.sessions.restore` | no |  |
| `mmfdb.v1.setups.save` | no |  |
| `mmfdb.v1.setups.get` | no |  |
| `mmfdb.v1.setups.list` | no |  |
| `mmfdb.v1.audit.list` | no |  |
| `mmfdb.v1.branches.create` | no |  |
| `mmfdb.v1.branches.fork` | no |  |
| `mmfdb.v1.branches.get` | no |  |
| `mmfdb.v1.branches.list` | no |  |
| `mmfdb.v1.branches.update_head` | no |  |
| `mmfdb.v1.branches.delete` | no |  |
| `mmfdb.v1.users.set_active_branch` | no |  |
| `mmfdb.v1.users.get_active_branch` | no |  |
| `mmfdb.v1.users.jump_to_operation` | no |  |
| `mmfdb.groups.list` | no |  |
| `mmfdb.groups.get` | no |  |
| `mmfdb.groups.create` | no |  |
| `mmfdb.groups.update` | no |  |
| `mmfdb.groups.delete` | no |  |
| `mmfdb.groups.members.list` | no |  |
| `mmfdb.groups.members.add` | no |  |
| `mmfdb.groups.members.remove` | no |  |
| `mmfdb.permissions.get` | no |  |
| `mmfdb.permissions.chmod` | no |  |
| `mmfdb.permissions.chown` | no |  |
| `mmfdb.permissions.chgrp` | no |  |
| `mmfdb.permissions.grant` | no |  |
| `mmfdb.permissions.revoke` | no |  |
| `mmfdb.objects.put` | no | Store a file or bytes in the object store (deduplicates by MD5). |
| `mmfdb.objects.put_bytes` | no | Store base64-encoded bytes in the object store. |
| `mmfdb.objects.get` | no | Retrieve blob content by object UUID (returns base64-encoded data). |
| `mmfdb.objects.get_info` | no | Retrieve object metadata by UUID. |
| `mmfdb.objects.delete` | no | Delete an object or decrement its refcount. |
| `mmfdb.objects.list` | no | List objects with optional filtering. |
| `analysis.run.delete` | no |  |
| `analysis.run.get` | no |  |
| `analysis.run.list` | no |  |
| `analysis.run.record` | no |  |
| `archive.zip.export` | no |  |
| `audit_log.list` | no |  |
| `database.backup` | no |  |
| `fluorophores.ai_triage` | no |  |
| `fluorophores.approve` | no |  |
| `fluorophores.find_duplicates` | no |  |
| `fluorophores.forster_radius.lookup` | no |  |
| `fluorophores.get` | no |  |
| `fluorophores.get_spectra_batch` | no |  |
| `fluorophores.import_default_set` | no |  |
| `fluorophores.import_reference_set` | no |  |
| `fluorophores.list` | no |  |
| `fluorophores.merge` | no |  |
| `fluorophores.probe_types.list` | no |  |
| `fluorophores.reject` | no |  |
| `fluorophores.set_quality` | no |  |
| `mmfdb.analysis.get` | no |  |
| `mmfdb.analysis.full` | no |  |
| `mmfdb.analysis.list` | no |  |
| `mmfdb.artifacts.delete` | no |  |
| `mmfdb.artifacts.validation.set` | no |  |
| `mmfdb.branches.delete` | no |  |
| `mmfdb.branches.get` | no |  |
| `mmfdb.branches.list` | no |  |
| `mmfdb.branches.save` | no |  |
| `mmfdb.calibrations.create` | no |  |
| `mmfdb.calibrations.list` | no |  |
| `mmfdb.calibrations.stale` | no |  |
| `mmfdb.datasets.browse` | no |  |
| `mmfdb.datasets.open` | no |  |
| `mmfdb.elabftw.connect` | no |  |
| `mmfdb.elabftw.disconnect` | no |  |
| `mmfdb.elabftw.experiments.export` | no |  |
| `mmfdb.elabftw.experiments.import` | no |  |
| `mmfdb.elabftw.experiments.list` | no |  |
| `mmfdb.lifecycle.definitions` | no |  |
| `mmfdb.lifecycle.history` | no |  |
| `mmfdb.lifecycle.state` | no |  |
| `mmfdb.lifecycle.transition` | no |  |
| `mmfdb.pipelines.get` | no |  |
| `mmfdb.pipelines.list` | no |  |
| `mmfdb.pipelines.runs` | no |  |
| `mmfdb.processed_data.get` | no |  |
| `mmfdb.processed_data.list` | no |  |
| `mmfdb.processing.get` | no |  |
| `mmfdb.processing.list` | no |  |
| `mmfdb.projects.get` | no |  |
| `mmfdb.projects.list` | no |  |
| `project_browser.list` | no |  |
| `project_browser.save` | no |  |
| `project_browser.restore` | no |  |
| `project_browser.export_csp` | no |  |
| `project_browser.import_preview` | no |  |
| `project_browser.import_csp` | no |  |
| `project_browser.delete_version` | no |  |
| `project_browser.create_branch` | no |  |
| `project_browser.list_branches` | no |  |
| `project_browser.version_graph` | no |  |
| `project_browser.artifacts` | no |  |
| `project_browser.parameters` | no |  |
| `mmfdb.protocols.create` | no |  |
| `mmfdb.protocols.for_operation` | no |  |
| `mmfdb.protocols.get` | no |  |
| `mmfdb.protocols.list` | no |  |
| `mmfdb.protocols.versions` | no |  |
| `mmfdb.raw_data.get` | no |  |
| `mmfdb.raw_data.list` | no |  |
| `mmfdb.reagents.create` | no |  |
| `mmfdb.reagents.expired` | no |  |
| `mmfdb.reagents.list` | no |  |
| `mmfdb.reagents.usage.add` | no |  |
| `mmfdb.reagents.usage.list` | no |  |
| `mmfdb.studies.create` | no |  |
| `mmfdb.studies.fields.set` | no |  |
| `mmfdb.studies.get` | no |  |
| `mmfdb.studies.list` | no |  |
| `mmfdb.studies.members.add` | no |  |
| `ndxplorer.load_burst_product` | no |  |
| `ndxplorer.record_analysis` | no |  |
| `processing.run.record` | no |  |
| `provenance.dependencies.downstream` | no |  |
| `provenance.dependencies.upstream` | no |  |
| `provenance.graph.export` | no |  |

## Source

- Plugin package: `chisurf/plugins/core/mmfdb_admin/`
- Manifest: {src}`chisurf/plugins/core/mmfdb_admin/manifest.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/admin.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/admin_panels.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/connection_auth.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/detector.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/dichroic.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/filter.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/fluorophore.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/light_source.view.json`
