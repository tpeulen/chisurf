(plugin-project_browser)=
# Open Project

Browse, save, restore, export, and import Chisurf projects using the MMFDB database with version control.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `project_browser` |
| Menu path | Tools → **Open Project** |
| Categories | Tools, Project |
| Version | 1.0.0 |
| Surfaces | gui, services |
| State namespace | `project_browser` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
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

## Source

- Plugin package: `chisurf/plugins/core/project_browser/`
- Manifest: {src}`chisurf/plugins/core/project_browser/manifest.json`
