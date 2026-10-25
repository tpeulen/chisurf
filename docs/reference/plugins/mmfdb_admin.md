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
| Surfaces | cli, emtk, services |
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

### Enter a value

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Value | `value` | str |  |  | The value to apply. |

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
| search | `search` | str |  |  | Keep rows whose kind, id, sample or project contains this text. |

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
| Search | `search` | str |  |  | List the components whose name contains this: as you type (with Auto on), or on Enter. |
| Auto | `auto_search` | bool |  |  | Search while typing (300 ms after the last key). Turn off for a large database and press Enter to search. |
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
| query | `query` | str |  |  | Search the remote experiments (Enter lists them). |

### Import into MMFDB

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Existing | `conflict` | choice |  | choices: skip, update, error | What to do with an experiment that was imported before. |
| Sample | `sample_id` | str |  |  | Attach the imported experiments to this sample (optional). |

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
| Scope | `scope` | choice |  | choices: `scope_options` | All protocols, your own, or the public ones. |
| new_name | `new_name` | str |  |  | The protocol's name (an existing name makes a new version). |
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
| Name | `new_name` | str |  |  | Its name. |
| Lot # | `new_lot_number` | str |  |  | The vendor's lot number. |
| Vendor | `new_vendor` | str |  |  | Who sold it. |
| Expiry | `new_expiry` | str |  |  | When it expires. |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Password | `password` | password |  |  | MMFDB password for the user below. Blank attempts a passwordless login. |
| Probe ID | `probe_id` | str |  |  | MMFDB probe identifier. |
| Name | `chromophore_name` | str |  |  | Detector name / model. |
| Category | `category` | str |  |  | Probe category (detector). |
| Type | `type_name` | str |  |  | Detector type. |
| Status | `verification_status` | str |  |  | Verification status. |
| Source | `source` | str |  |  | Provenance source. |
| Source ref | `source_ref` | str |  |  | Source reference / URL. |
| Verified by | `verified_by` | str |  |  | User who approved/rejected this detector. |
| Verified at | `verified_at` | str |  |  | Timestamp of the verification decision. |
| Description | `description` | str |  |  | Free-text description. |
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

### Advanced — user & connection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| User | `user` | str |  |  | MMFDB user id to authenticate as. |
| Host | `host` | str |  |  | MMFDB server host. Change to connect to a different server. |
| Command port | `cmd_port` | int |  | 1 … 65535 | ZMQ command port. |
| Publish port | `pub_port` | int |  | 1 … 65535 | ZMQ publish port. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fluorophores.diffusion_reference` | no | List every probe carrying a diffusion coefficient D(25 °C, water). |
| `fluorophores.import_diffusion_reference` | no | Seed literature diffusion coefficients as probe properties. |
| `mmfdb.security.auth.change_password` | no | Change the authenticated user's password. |
| `mmfdb.security.auth.login` | no | Authenticate a user and return a session token. |
| `mmfdb.security.auth.logout` | no | Revoke the current session. |
| `mmfdb.security.auth.me` | no | Return the authenticated user, or fail if anonymous. |
| `mmfdb.security.auth.sessions.list` | no | List active sessions. Admin can see all; users see their own. |
| `mmfdb.security.auth.sessions.revoke` | no | Revoke a session by ID. Admin can revoke any; users revoke their own. |
| `mmfdb.status` | no | Return the database identity, backend type and entity counts. |
| `mmfdb.samples.list` | no | List the samples the caller may read. |
| `mmfdb.samples.get` | no | Return one sample with its full record (read access required). |
| `mmfdb.samples.save` | no | Create or update a sample; a structured payload goes through the structured-sample path. |
| `mmfdb.samples.delete` | no | Delete a sample (write access required). |
| `mmfdb.samples.search` | no | List the readable samples matching a free-text query (all of them without one). |
| `mmfdb.samples.key_values.save` | no | Replace the key/value annotations of a sample. |
| `mmfdb.samples.full_description` | no | Return the nested public description of a sample. |
| `mmfdb.samples.validate_export` | no | Return export validation warnings for a sample. |
| `mmfdb.samples.create_structured` | no | Create a sample from a structured description (entities, probes, conditions). |
| `mmfdb.sample_conditions.list` | no | List sample conditions. |
| `mmfdb.sample_conditions.get` | no | Return one sample-condition row. |
| `mmfdb.sample_conditions.save` | no | Create or update a sample condition. |
| `mmfdb.sample_conditions.delete` | no | Soft-delete a sample condition. |
| `mmfdb.entities.list` | no | List entities globally or for one sample. |
| `mmfdb.entities.get` | no | Return one entity row. |
| `mmfdb.entities.save` | no | Create or update an entity and its sequence. |
| `mmfdb.entities.delete` | no | Soft-delete an entity. |
| `mmfdb.probes.list` | no | List the probes with their optical properties. |
| `mmfdb.probes.get` | no | Return one probe identity row. |
| `mmfdb.probes.save` | no | Create or update a probe identity row. |
| `mmfdb.probes.delete` | no | Soft-delete a probe identity row. |
| `mmfdb.probes.optical_properties.get` | no | Return the optical properties of a probe. |
| `mmfdb.probes.optical_properties.save` | no | Replace editable optical properties for a probe. |
| `mmfdb.probes.positions.list` | no | List probe positions by sample or probe. |
| `mmfdb.probes.positions.get` | no | Return one probe-position row. |
| `mmfdb.probes.positions.save` | no | Create or update a polymer probe-position row. |
| `mmfdb.probes.positions.delete` | no | Soft-delete a polymer probe-position row. |
| `mmfdb.fret_pairs.list` | no | List FRET pair/Förster radius records globally or for one sample. |
| `mmfdb.fret_pairs.get` | no | Return one FRET pair/Förster radius row. |
| `mmfdb.fret_pairs.save` | no | Create a FRET pair/Förster radius record. |
| `mmfdb.fret_pairs.delete` | no | Delete a FRET pair/Förster radius record. |
| `mmfdb.pdbx.suggest_keys` | no | Return matching PDBx/flrCIF dictionary keys. |
| `mmfdb.pdbx.validate_value` | no | Validate one PDBx/flrCIF key/value pair. |
| `mmfdb.mock_data.populate` | no | Populate the authenticated database with packaged synthetic burst tables. |
| `mmfdb.users.list` | no | List the database users. Admin only. |
| `mmfdb.users.save` | no | Create or update a user account, optionally renaming it or setting its password. |
| `mmfdb.users.delete` | no | Delete a user account. Admin only. |
| `mmfdb.devices.list` | no | List the instruments/devices. |
| `mmfdb.devices.get` | no | Return one instrument/device row. |
| `mmfdb.devices.save` | no | Create or update an instrument/device row. |
| `mmfdb.devices.delete` | no | Delete an instrument/device and return the remaining list. |
| `mmfdb.experiment_types.list` | no | List the experiment types. |
| `mmfdb.experiment_types.get` | no | Return one experiment type. |
| `mmfdb.experiment_types.save` | no | Create or update an experiment type (an empty name gets an untitled one). |
| `mmfdb.experiment_types.delete` | no | Delete an experiment type and return the remaining list. |
| `mmfdb.experiments.list` | no | List experiments, optionally filtered by sample, project or type. |
| `mmfdb.experiments.get` | no | Return one experiment with its data entries. |
| `mmfdb.experiments.save` | no | Create or update an experiment. |
| `mmfdb.experiments.delete` | no | Delete an experiment. |
| `mmfdb.experiments.key_values.save` | no | Replace the key/value annotations of an experiment. |
| `mmfdb.experiments.data.save` | no | Attach a data entry (linked or stored) to an experiment. |
| `mmfdb.experiments.data.delete` | no | Remove a data entry from an experiment. |
| `mmfdb.setups.list` | no | List the readable instrument setups. |
| `mmfdb.setups.get` | no | Return one setup (read access required). |
| `mmfdb.setups.save` | no | Create or update an instrument setup and its configuration. |
| `mmfdb.setups.delete` | no | Delete a setup (write access required). |
| `mmfdb.setups.validate` | no | Validate a stored setup without bypassing its read ACL. |
| `mmfdb.setups.detector_channels.list` | no | List detector channel definitions. |
| `mmfdb.setups.pie_windows.list` | no | List PIE window definitions. |
| `mmfdb.setups.fcs_pairs.list` | no | List FCS channel-pair definitions. |
| `raw_data.register` | no | Register a raw TTTR/PTU/SPC/BH data reference. |
| `raw_data.list` | no | List raw-data artifacts. |
| `raw_data.get` | no | Return one raw-data artifact row. |
| `processing.burst_selection.record` | no | Record a Burst Selection processing run and its products. |
| `processing.burst_selection.run` | no | Run burst selection on photon files and record the run and its products with provenance. |
| `processing.burst_selection.get` | no | Return one Burst Selection processing run. |
| `processing.burst_selection.list` | no | List Burst Selection processing runs. |
| `processed_data.register` | no | Register a processed data product. |
| `processed_data.list` | no | List processed-data artifacts. |
| `processed_data.get` | no | Return one processed-data artifact. |
| `provenance.edges.list` | no | List provenance edges. |
| `provenance.trace_processed_data` | no | Trace a product back through raw inputs and settings. |
| `archive.burst_processing_manifest.export` | no | Export an archive manifest for one Burst Selection run. |
| `mmfdb.import_file` | no | Import a structure/description file into the database and return a summary. |
| `mmfdb.export_sample` | no | Export a sample's FRET analysis as flrCIF, to a file or as text. Admin only. |
| `mmfdb.export_table` | no | Write the sample table (one sample or all) to a file. Admin only. |
| `mmfdb.backup` | no | Back up the database file and return the backup path. Admin only. |
| `mmfdb.reset_from_source` | no | Replace the user database with the curated seed and restore its admin. |
| `mmfdb.v1.samples.register` | no | Register or update a sample in the FLR domain layer. |
| `mmfdb.v1.samples.get` | no | Retrieve a sample by identifier. |
| `mmfdb.v1.samples.list` | no | List samples. |
| `mmfdb.v1.experiments.register` | no | Register or update an experiment in the FLR domain layer. |
| `mmfdb.v1.experiments.get` | no | Retrieve an experiment by identifier. |
| `mmfdb.v1.experiments.list` | no | List experiments with optional filters. |
| `mmfdb.v1.artifacts.register` | no | Register or update an MMFDB artifact in the database. |
| `mmfdb.v1.artifacts.get` | no | Retrieve an artifact by its identifier. |
| `mmfdb.v1.artifacts.list` | no | List artifacts with optional filtering. |
| `mmfdb.v1.operations.record` | no | Record or update a processing or analysis operation. |
| `mmfdb.v1.operations.record_with_artifacts` | no | Record an operation and related artifacts atomically. |
| `mmfdb.v1.operations.get` | no | Retrieve an operation by its identifier. |
| `mmfdb.v1.operations.list` | no | List operations with optional filtering. |
| `mmfdb.v1.operations.link_artifact` | no | Link an operation and an artifact. |
| `mmfdb.v1.operations.link` | no | Alias of mmfdb.v1.operations.link_artifact: link an operation and an artifact. |
| `mmfdb.v1.operations.transition_status` | no | Transition an operation status. |
| `mmfdb.v1.graph.traverse` | no | Traverse the canonical graph recursively, cycle-safe. |
| `mmfdb.v1.graph.upstream` | no | Traverse upstream canonical graph edges. |
| `mmfdb.v1.graph.downstream` | no | Traverse downstream canonical graph edges. |
| `mmfdb.v1.graph.export` | no | Export a provenance graph as JSON-serializable nodes and edges. |
| `mmfdb.v1.parameters.record` | no | Record or update a semantic parameter. |
| `mmfdb.v1.parameters.get` | no | Retrieve a parameter by its UUID. |
| `mmfdb.v1.parameters.list` | no | List parameters with optional filters. |
| `mmfdb.v1.graph.sessions.save` | no | Store a canonical node-graph session payload in MMFDB. |
| `mmfdb.v1.graph.sessions.get` | no | Load a node-graph session artifact from MMFDB. |
| `mmfdb.v1.graph.sessions.list` | no | List node-graph session artifacts in MMFDB. |
| `mmfdb.v1.graph.sessions.restore` | no | Restore a node-graph session artifact from MMFDB. |
| `mmfdb.v1.setups.save` | no | Save or update an instrument/calibration setup configuration. |
| `mmfdb.v1.setups.get` | no | Retrieve a setup configuration by its identifier. |
| `mmfdb.v1.setups.list` | no | List setup snapshots. |
| `mmfdb.v1.audit.list` | no | List audit log records with optional filtering. |
| `mmfdb.v1.branches.create` | no | Create a branch pointer in the MMFDB provenance graph. |
| `mmfdb.v1.branches.fork` | no | Create a parallel branch from an existing branch. |
| `mmfdb.v1.branches.get` | no | Return one branch by UUID or name. |
| `mmfdb.v1.branches.list` | no | Return all non-deleted branches. |
| `mmfdb.v1.branches.update_head` | no | Move a branch head to an operation or clear it. |
| `mmfdb.v1.branches.delete` | no | Soft-delete a branch when it is not protected or active. |
| `mmfdb.v1.users.set_active_branch` | no | Set the active branch for a user (self, or any user when admin). |
| `mmfdb.v1.users.get_active_branch` | no | Return the active branch for a user (self, or any user when admin). |
| `mmfdb.v1.users.jump_to_operation` | no | Create and activate a user branch at a historical operation. |
| `mmfdb.groups.list` | no | List all groups. |
| `mmfdb.groups.get` | no | Get a single group by ID. |
| `mmfdb.groups.create` | no | Create a new group. Admin only. |
| `mmfdb.groups.update` | no | Update a group. Admin or group manager only. |
| `mmfdb.groups.delete` | no | Soft-delete a group. Admin only. Built-in groups cannot be deleted. |
| `mmfdb.groups.members.list` | no | List members of a group. |
| `mmfdb.groups.members.add` | no | Add a member to a group. Admin or group manager/owner only. |
| `mmfdb.groups.members.remove` | no | Remove a member from a group. Admin or group manager/owner only. |
| `mmfdb.permissions.get` | no | Get the ACL for an object. Requires read access on the object. |
| `mmfdb.permissions.chmod` | no | Change mode bits on an object. Requires the manage permission (`x`). |
| `mmfdb.permissions.chown` | no | Change object owner. Requires the manage permission (`x`). |
| `mmfdb.permissions.chgrp` | no | Change object owning group. Requires the manage permission (`x`). |
| `mmfdb.permissions.grant` | no | Grant or deny a permission on an object. Requires the manage permission (`x`). |
| `mmfdb.permissions.revoke` | no | Revoke an ACL entry. Requires the manage permission (`x`) on the referenced object. |
| `mmfdb.objects.put` | no | Store a file or bytes in the object store (deduplicates by MD5). |
| `mmfdb.objects.put_bytes` | no | Store base64-encoded bytes in the object store. |
| `mmfdb.objects.get` | no | Retrieve blob content by object UUID (returns base64-encoded data). |
| `mmfdb.objects.get_info` | no | Retrieve object metadata by UUID. |
| `mmfdb.objects.delete` | no | Delete an object or decrement its refcount. |
| `mmfdb.objects.list` | no | List objects with optional filtering. |
| `analysis.run.delete` | no | Delete an analysis run. |
| `analysis.run.get` | no | Retrieve one analysis run with all details. |
| `analysis.run.list` | no | List registered analysis runs. |
| `analysis.run.record` | no | Record an analysis run with its parameters, inputs, products, and linkages. |
| `archive.zip.export` | no | Package a full ZIP archive containing DB snapshot, graph, manifest and optionally data. |
| `audit_log.list` | no | Retrieve audit log records with optional filtering. |
| `database.backup` | no | Create a hot backup of the SQLite database to the specified target path. |
| `fluorophores.ai_triage` | no | Run AI-assisted triage (deterministic checks plus a model review) on one probe. |
| `fluorophores.approve` | no | Approve a fluorophore probe. |
| `fluorophores.find_duplicates` | no | Return all probe data for the frontend to compute duplicate groupings. |
| `fluorophores.forster_radius.lookup` | no | Look up the Förster radius R0 for a donor-acceptor pair. |
| `fluorophores.get` | no | Get a single probe with its optical properties and spectra. |
| `fluorophores.get_spectra_batch` | no | Fetch all spectra data for a batch of probes. |
| `fluorophores.import_default_set` | no | Seed ChiSurf's built-in default fluorophore spectra into the database. |
| `fluorophores.import_reference_set` | no | Import optical-component reference data from a scraped spectra.db. |
| `fluorophores.list` | no | List fluorophore probes with optional filtering. |
| `fluorophores.merge` | no | Merge duplicate probes into a primary probe. |
| `fluorophores.probe_types.list` | no | List all available probe types. |
| `fluorophores.reject` | no | Reject a fluorophore probe. |
| `fluorophores.set_quality` | no | Set the quality level of a probe. |
| `mmfdb.analysis.get` | no | Return one analysis operation. |
| `mmfdb.analysis.full` | no | Return one analysis operation with parameters and linked products. |
| `mmfdb.analysis.list` | no | List analysis operations. |
| `mmfdb.artifacts.delete` | no | Soft-delete an artifact and its direct provenance links. |
| `mmfdb.artifacts.validation.set` | no | Set the validation status for a raw or processed artifact. |
| `mmfdb.branches.delete` | no | Soft-delete a branch. |
| `mmfdb.branches.get` | no | Return one branch by UUID or name. |
| `mmfdb.branches.list` | no | List MMFDB branches. |
| `mmfdb.branches.save` | no | Create or update a branch record. |
| `mmfdb.calibrations.create` | no | Register a calibration value (defaults to a user-provided / literature value). |
| `mmfdb.calibrations.list` | no | List calibration records (type/method/value/notes), newest first. |
| `mmfdb.calibrations.stale` | no | List uses whose calibration is superseded by a newer one of the same type. |
| `mmfdb.datasets.browse` | no | Browse datasets with scope-based access control and pagination. |
| `mmfdb.datasets.open` | no | Open a dataset and return a local readable path. |
| `mmfdb.elabftw.connect` | no | Probe credentials once and retain them behind an opaque handle. |
| `mmfdb.elabftw.disconnect` | no | Discard an owner-bound remote connection handle. |
| `mmfdb.elabftw.experiments.export` | no | Create or explicitly update an eLabFTW experiment from MMFDB. |
| `mmfdb.elabftw.experiments.import` | no | Atomically import remote experiments with an explicit conflict policy. |
| `mmfdb.elabftw.experiments.list` | no | Return bounded remote experiment summaries for the Admin GUI. |
| `mmfdb.lifecycle.definitions` | no | Return the authored lifecycle definitions (states + transitions per entity). |
| `mmfdb.lifecycle.history` | no | Return an entity's ordered transition history (already JSON-safe dicts). |
| `mmfdb.lifecycle.state` | no | Return an entity's current lifecycle state (null when it has none). |
| `mmfdb.lifecycle.transition` | no | Transition an entity; an illegal jump is returned as an error, not raised. |
| `mmfdb.pipelines.get` | no | Return a pipeline's structure (nodes + typed edges), or an error. |
| `mmfdb.pipelines.list` | no | List stored pipeline definitions scoped mine/public/all. |
| `mmfdb.pipelines.runs` | no | List runs (newest first) with operation counts, optionally for one pipeline. |
| `mmfdb.processed_data.get` | no | Return one processed-data artifact. |
| `mmfdb.processed_data.list` | no | List processed-data artifacts. |
| `mmfdb.processing.get` | no | Return one processing operation. |
| `mmfdb.processing.list` | no | List processing operations. |
| `mmfdb.projects.get` | no | Return one MMFDB project record by project ID or version operation ID. |
| `mmfdb.projects.list` | no | List MMFDB project records. |
| `mmfdb.protocols.create` | no | Create a protocol (or a new version); an invalid category returns an error. |
| `mmfdb.protocols.for_operation` | no | Return the protocol/version recorded on an operation (run provenance). |
| `mmfdb.protocols.get` | no | Return a protocol (default latest) with its declared parameter schema. |
| `mmfdb.protocols.list` | no | List the latest version of each protocol, scoped own/public/all. |
| `mmfdb.protocols.versions` | no | Return all versions of a protocol name (oldest first). |
| `mmfdb.raw_data.get` | no | Return one raw-data artifact row. |
| `mmfdb.raw_data.list` | no | List raw-data artifacts. |
| `mmfdb.reagents.create` | no | Create a reagent lot; a bad kind / missing name returns an error. |
| `mmfdb.reagents.expired` | no | List lots whose expiry is in the past (QC). |
| `mmfdb.reagents.list` | no | List reagent lots, optionally filtered by kind and excluding expired ones. |
| `mmfdb.reagents.usage.add` | no | Link a lot to an operation/setup/sample; a bad target_type returns an error. |
| `mmfdb.reagents.usage.list` | no | List the reagent lots used by an operation/setup/sample. |
| `mmfdb.studies.create` | no | Create a study; a missing name returns an error. |
| `mmfdb.studies.fields.set` | no | Set a configurable per-study field. |
| `mmfdb.studies.get` | no | Return a study with its members and configurable fields. |
| `mmfdb.studies.list` | no | List studies scoped mine/public/all. |
| `mmfdb.studies.members.add` | no | Add a sample/artifact to a study; a bad member_type returns an error. |
| `mmfdb.burst_product.load` | no | Load a registered burst product into ndxplorer data structures. |
| `mmfdb.analysis.record` | no | Record an ndxplorer analysis run and its generated products. |
| `processing.run.record` | no | Record a general processing run and its inputs/products. |
| `provenance.dependencies.downstream` | no | Retrieve downstream dependencies for a node. |
| `provenance.dependencies.upstream` | no | Retrieve upstream dependencies for a node. |
| `provenance.graph.export` | no | Export the provenance subgraph as a JSON-serializable structure. |

## Theory and workflow

- **Theory** — [The measurement database: records, provenance and who may change them](/concepts/measurement_database.md)
- **Workflow** — [Administering the measurement database: MMFDB Admin](/guides/102_mmfdb_admin.md)

## Source

- Plugin package: `chisurf/plugins/core/mmfdb_admin/`
- Manifest: {src}`chisurf/plugins/core/mmfdb_admin/manifest.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/admin.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/admin_panels.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/connection_auth.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/entity_extras.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/detector.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/dichroic.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/filter.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/fluorophore.view.json`
- UI spec: {src}`chisurf/plugins/core/mmfdb_admin/gui/optical_components/light_source.view.json`
