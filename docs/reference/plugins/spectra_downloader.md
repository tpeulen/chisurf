---
type: Plugin Reference
title: Spectra Downloader
description: Download, browse and push optical-component spectra (fluorophores, filters, dichroics, detectors, light sources)
resource: chisurf/plugins/spectra_downloader/
tags: [reference, plugins, spectra-downloader, tools, calculators, spectra]
anchor: plugin-spectra_downloader
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-spectra_downloader)=
# Spectra Downloader

Download, browse and push optical-component spectra (fluorophores, filters, dichroics, detectors, light sources)

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `spectra_downloader` |
| Menu path | Tools → Calculators → **Spectra Downloader** |
| Categories | Tools, Calculators, Spectra |
| Version | 0.2.0 |
| Surfaces | cli, emtk, gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Endpoint | `mode` | choice |  | choices: local, server | Where to add the staging components: a local MMFDB file, or a running MMFDB server. |
| Local MMFDB | `db_path` | str |  |  | Target MMFDB SQLite path (local mode). Blank = the resolved live MMFDB. |
| Replace existing reference set | `replace` | bool |  |  | Purge the existing reference probes before importing (a backup is made for local files). |
| Mark imported as approved | `mark_verified` | bool |  |  | Stamp imported components as approved instead of unverified. |
| Total components | `total` | str |  |  | Number of components in the staging database. |
| With spectra | `with_spectra` | str |  |  | Components that carry at least one spectrum. |
| Fluorophores | `fluorophores` | str |  |  | Proteins + organic dyes + other fluorophores. |
| Filters | `filters` | str |  |  | Optical filters. |
| Dichroics | `dichroics` | str |  |  | Dichroic beamsplitters / mirrors. |
| Detectors | `detectors` | str |  |  | Cameras / SPADs / PMTs (quantum-efficiency curves). |
| Light sources | `light_sources` | str |  |  | Lamps / LEDs / lasers. |
| Filter | `search` | str |  |  | Keep the components whose name contains this text. |
| Source | `source_filter` | choice |  | choices: `source_options` | Keep the components from one source (All shows every source). |
| Category | `category_filter` | choice |  | choices: `category_options` | Keep one category of component (All shows every category). |
| metadata_json | `metadata_json` | code_editor |  |  | The probe row, its properties and a spectrum summary as JSON. |
| Available sources | `scraper_label` | choice |  | choices: `scraper_labels` | The scraper to run into the staging database. |
| log | `log` | code_editor |  |  | The scraper's output. |
| mmfdb_log | `mmfdb_log` | code_editor |  |  | What the import did. |

### Advanced — connection & authentication

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Host | `host` | str |  |  | MMFDB server host (server mode). |
| Command port | `cmd_port` | int |  | 1 … 65535 | ZMQ command port (server mode). |
| Publish port | `pub_port` | int |  | 1 … 65535 | ZMQ publish port (server mode). |
| User | `user` | str |  |  | Authenticate as this user. Defaults to the current session user. |
| Password | `password` | password |  |  | MMFDB password. Not needed when the session user is already an administrator. |

## Theory and workflow

- **Theory** — [Förster resonance energy transfer (FRET)](/concepts/fret.md)
- **Workflow** — [Spectra, overlap integrals and R₀](/guides/83_spectra_and_r0.md)

## Source

- Plugin package: `chisurf/plugins/spectra_downloader/`
- Manifest: {src}`chisurf/plugins/spectra_downloader/manifest.json`
- UI spec: {src}`chisurf/plugins/spectra_downloader/gui/endpoint_auth.view.json`
- UI spec: {src}`chisurf/plugins/spectra_downloader/gui/overview.view.json`
- UI spec: {src}`chisurf/plugins/spectra_downloader/gui/spectra_emtk.view.json`
