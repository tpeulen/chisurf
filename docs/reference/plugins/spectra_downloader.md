(plugin-spectra_downloader)=
# Spectra Downloader

Download, browse and push optical-component spectra (fluorophores, filters, dichroics, detectors, light sources)

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `spectra_downloader` |
| Menu path | Spectroscopy → **Spectra Downloader** |
| Categories | Spectroscopy, Spectra |
| Version | 0.2.0 |
| Surfaces | cli, gui |

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

## Source

- Plugin package: `chisurf/plugins/spectra_downloader/`
- Manifest: {src}`chisurf/plugins/spectra_downloader/manifest.json`
- UI spec: {src}`chisurf/plugins/spectra_downloader/gui/endpoint_auth.view.json`
- UI spec: {src}`chisurf/plugins/spectra_downloader/gui/overview.view.json`
