---
type: Plugin Reference
title: Open Project
description: Browse, save, restore, export, and import Chisurf projects using the MMFDB database with version control.
resource: chisurf/plugins/core/project_browser/
tags: [reference, plugins, project-browser, tools, project]
anchor: plugin-project_browser
generator: build_tools/docs/generate_plugin_docs.py
---

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
| Surfaces | emtk, gui |
| State namespace | `project_browser` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Search | `search` | str |  |  | Search stored project names, identifiers, owners and version notes. The list reloads when you press Enter or click away. |
| Show public | `show_public` | bool |  |  | Include projects made readable to other authenticated users. |
| Show ID | `show_id` | bool |  |  | Show or hide the ID column (the project or version identifier). Undecided, it shows when the list is wide enough. |
| Show status | `show_status` | bool |  |  | Show or hide the Status column (the state of a version's last operation). Undecided, it shows when the list is wide enough. |
| Project name | `name` | str |  |  | Name a new project; a new version of an existing project keeps its project name. |
| Visibility | `visibility_name` | choice |  | choices: Private, Public | Private is visible to its owner; public is readable by any authenticated user. |
| notes | `notes` | code_editor |  |  | Optional notes recorded with the new version. |

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
- UI spec: {src}`chisurf/plugins/core/project_browser/gui/project_browser_emtk.view.json`
