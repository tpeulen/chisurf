(plugin-database_connector)=
# Database Connector

Core database connector services for source/user database resolution, migration, backup, reset, repository access, and FLR CIF import/export.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `database_connector` |
| Menu path | Core → **Database Connector** |
| Categories | Core, Database, Fluorescence |
| Version | 0.1.0 |
| Surfaces | services |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `database_connector.status` | no |  |
| `database_connector.open` | no |  |
| `database_connector.close` | no |  |
| `database_connector.backup` | no |  |
| `database_connector.reset_from_source` | no |  |
| `database_connector.repository` | no |  |
| `database_connector.import_file` | no |  |
| `database_connector.export_sample` | no |  |

## Source

- Plugin package: `chisurf/plugins/core/database_connector/`
- Manifest: `chisurf/plugins/core/database_connector/manifest.json`
