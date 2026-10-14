---
type: Plugin Reference
title: Database Connector
description: Core database connector services for source/user database resolution, migration, backup, reset, repository access, and FLR CIF import/export.
resource: chisurf/plugins/core/database_connector/
tags: [reference, plugins, database-connector, core, database, fluorescence]
anchor: plugin-database_connector
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-database_connector)=
# Database Connector

Core database connector services for source/user database resolution, migration, backup, reset, repository access, and FLR CIF import/export.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `database_connector` |
| Menu path | not in the menus; display name Core → **Database Connector** |
| Categories | Core, Database, Fluorescence |
| Version | 0.1.0 |
| Surfaces | services |

## Parameters

This plugin opens no window and has no parameters: it is shared code that other plugins import.

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `database_connector.status` | no | Report the connector's state and the active database. |
| `database_connector.open` | no | Open the connector on a database (the configured one by default). |
| `database_connector.close` | no | Close the connector. |
| `database_connector.backup` | no | Back up the active user database. |
| `database_connector.reset_from_source` | no | Reset the user database from the curated source database. |
| `database_connector.repository` | no | Repository metadata, optionally with record counts. |
| `database_connector.import_file` | no | Import a structure file into the database. |
| `database_connector.export_sample` | no | Export a sample as an FLR CIF file. |

## Theory and workflow

- **Theory** — [The measurement database: records, provenance and who may change them](/concepts/measurement_database.md)
- **Workflow** — [Administering the measurement database: MMFDB Admin](/guides/102_mmfdb_admin.md)

## Source

- Plugin package: `chisurf/plugins/core/database_connector/`
- Manifest: {src}`chisurf/plugins/core/database_connector/manifest.json`
