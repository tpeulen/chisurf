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

### Step 1 · New record

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Name | `new_name` | str |  |  | Folder and archive name: lower case, digits, '.', '_' or '-', e.g. t4l-unfolding-smfret-k60-n132c. |
| Title | `new_title` | str |  |  | The Zenodo title (you can change it in step 3). |

### Step 2 · Add data

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Add as | `add_role` | choice |  | choices: measurement, calibration | A measurement (sample data) or a calibration (IRF/scatter, buffer, dyes, DNA references). |
| Item | `add_name` | str |  |  | The item's folder name, e.g. 2014-08-12_0M-urea or h2o-scatter. |
| Group | `add_group` | str |  |  | The calibration group: the setup and day it calibrates, e.g. 2014-08-12_pq-hydraharp. |
| record_tree | `record_tree` | code_editor |  |  | What the record holds now: every item with its file count and size. |

### Step 3 · Zenodo metadata

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Title | `meta_title` | str |  |  | The record title. |
| Type | `meta_upload_type` | choice |  | choices: `UPLOAD_TYPES` | Zenodo upload type; measurement data is a dataset. |
| Date | `meta_publication_date` | str |  |  | Publication date, YYYY-MM-DD. |
| Version | `meta_version` | str |  |  | Optional version, e.g. 1.0. |
| Access | `meta_access_right` | choice |  | choices: `ACCESS_RIGHTS` | open, embargoed (with a date), restricted or closed. |
| License | `meta_license` | choice |  | choices: `LICENSES` | Needed for open and embargoed access; data is usually cc-by-4.0. Pick one or type any Zenodo licence id (e.g. odbl-1.0). |
| Embargo until | `meta_embargo_date` | str |  |  | When an embargoed record opens, YYYY-MM-DD. |
| Creators | `meta_creators` | text |  |  | One per line: Family, Given; Affiliation; ORCID (affiliation and ORCID optional). |
| Description | `meta_description` | text |  |  | What the data are and how they were measured (HTML allowed: &lt;p>, &lt;ul>, &lt;a>). |
| Keywords | `meta_keywords` | str |  |  | Comma separated, e.g. smFRET, T4 lysozyme, urea unfolding. |
| Related | `meta_related` | text |  |  | One per line: relation and identifier, e.g. isSupplementTo 10.1101/2026.01.01.123456 (the paper). |

### Sent to Zenodo (JSON)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| metadata_json | `metadata_json` | code_editor |  |  | Exactly the deposition metadata the upload sends. |

### Advanced · Build from a project script

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Configs | `configs_dir` | str |  |  | The folder of record build configs (one JSON per record: its measurements, calibrations, sources, construct, setups and Zenodo metadata). |
| config_text | `config_text` | code_editor |  |  | The selected build config, read-only. Edit it in the project, then Build record. |
| build_log | `build_log` | code_editor |  |  | What the last build printed: per container the burst tables, sidecars, encodings and checks, and VERIFY_OK or what failed. |

### 1 · Review

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Note | `note` | str |  |  | Stored with your decision, e.g. which file you looked at or why you rejected the item. |
| preview_json | `preview_json` | code_editor |  |  | The selected JSON file, read-only. |
| preview_cif | `preview_cif` | code_editor |  |  | The selected flrCIF/mmCIF file, read-only, highlighted: tags, loops and text fields. |
| Show | `md_mode` | choice |  | choices: Preview, Source | Preview: the Markdown rendered, roughly as Zenodo shows it. Source: the text as it is in the file. |
| preview_md | `preview_md` | code_editor |  |  | The selected Markdown file's source, read-only. |
| preview_txt | `preview_txt` | code_editor |  |  | The selected file's text, read-only. |

### 2 · Upload

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| zenodo_description | `zenodo_description` | code_editor |  |  | The record description as it will appear on Zenodo (HTML). |
| Trial run on the Zenodo sandbox | `sandbox` | bool |  |  | Upload to sandbox.zenodo.org instead of zenodo.org. The sandbox needs its own token (Zenodo token tab). |

### Zenodo token

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
