---
type: Plugin Reference
title: Zenodo deposit
description: Review a deposition record item by item -- every measurement folder, calibration folder and metadata file, with where it came from and why it is flagged -- then upload it as a Zenodo draft and check the draft against the local package. Nothing is uploaded until every item is approved at its current content; publishing needs its own approval of the exact package.
resource: chisurf/plugins/core/zenodo_deposit/
tags: [reference, plugins, zenodo-deposit, file, data]
anchor: plugin-zenodo_deposit
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-zenodo_deposit)=
# Zenodo deposit

Review a deposition record item by item -- every measurement folder, calibration folder and metadata file, with where it came from and why it is flagged -- then upload it as a Zenodo draft and check the draft against the local package. Nothing is uploaded until every item is approved at its current content; publishing needs its own approval of the exact package.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `zenodo_deposit` |
| Menu path | File → Data → **Zenodo deposit** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### New record

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Name | `new_name` | str |  |  | Folder and archive name: lower case, digits, '.', '_' or '-', e.g. t4l-unfolding-smfret-k60-n132c. |
| Title | `new_title` | str |  |  | The Zenodo title (you can change it in step 3). |

### Add data

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Add as | `add_role` | choice |  | choices: measurement, calibration | A measurement (sample data) or a calibration (IRF/scatter, buffer, dyes, DNA references). |
| Item | `add_name` | str |  |  | The item's folder name, e.g. 2014-08-12_0M-urea or h2o-scatter. |
| Group | `add_group` | str |  |  | The calibration group: the setup and day it calibrates, e.g. 2014-08-12_pq-hydraharp. |
| record_tree | `record_tree` | code_editor |  |  | What the record holds now: every item with its file count and size. |

### Sent to Zenodo (JSON)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| metadata_json | `metadata_json` | code_editor |  |  | Exactly the deposition metadata the upload sends. |

### Build from a project script

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Configs | `configs_dir` | str |  |  | The folder of record build configs (one JSON per record: its measurements, calibrations, sources, construct, setups and Zenodo metadata). |
| config_edit | `config_edit` | code_editor |  |  | The selected build config, or the example: edit it here and Save config (keys starting with _ are notes, ignored by the build). |
| build_log | `build_log` | code_editor |  |  | What the last build printed: per container the burst tables, sidecars, encodings and checks, and VERIFY_OK or what failed. |

### 2 · Review

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Note | `note` | str |  |  | Stored with your decision, e.g. which file you looked at or why you rejected the item. |

### Before upload

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Build the metadata separate | `separate_metadata` | bool |  |  | Keep every metadata file out of the raw archive: the editable README.md and metadata.cif AND the provenance (origins.json, manifest_sha256.csv) are uploaded beside it as sidecars, so correcting or regenerating any of them later is a metadata-only swap and never re-sends the raw data. |

### Draft

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| zenodo_description | `zenodo_description` | code_editor |  |  | The record description as it will appear on Zenodo (HTML). |
| Deposit these projects without their linked data (they cannot be reopened with their data from the deposit) | `accept_linked_data` | bool |  |  | Tick to allow the override, then press Confirm. Without the data a reader of the deposit cannot reopen these projects' measurements. |

### DOI & publish

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Trial run on the Zenodo sandbox | `sandbox` | bool |  |  | Upload to sandbox.zenodo.org instead of zenodo.org. The sandbox needs its own token (Zenodo token tab). |

### Token

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Token | `token_entry` | password |  |  | Paste the token and press Save. The field is cleared once it is stored; the token goes to the system keychain, never into a file or ChiSurf's settings. |

## Theory and workflow

- **Theory** — [Depositing data — a reviewed path to Zenodo](/concepts/data_deposition.md)
- **Workflow** — [Uploading a record to Zenodo](/guides/109_zenodo_deposit.md)

## Source

- Plugin package: `chisurf/plugins/core/zenodo_deposit/`
- Manifest: {src}`chisurf/plugins/core/zenodo_deposit/manifest.json`
- UI spec: {src}`chisurf/plugins/core/zenodo_deposit/gui/zenodo_deposit_emtk.view.json`
