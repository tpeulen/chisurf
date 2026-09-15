---
type: Plugin Reference
title: User Editor
description: User editor plugin for Chisurf to manage users registered in the MMFDB.
resource: chisurf/plugins/core/user_editor/
tags: [reference, plugins, user-editor, setup]
anchor: plugin-user_editor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-user_editor)=
# User Editor

User editor plugin for Chisurf to manage users registered in the MMFDB.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `user_editor` |
| Menu path | Setup → **User Editor** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `user_editor` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Username | `user_id` | str |  |  | How the account is addressed. Changing it renames the account; built-in accounts cannot be renamed. |
| Display name | `display_name` | str |  |  | The name shown wherever the user appears. |
| E-mail | `email` | str |  |  | Optional contact address. |
| Role | `role` | choice |  | choices: `role_options` | The user's role. Pick one or type another; a role set by a different tool is kept as it is. |
| Affiliation | `affiliation` | str |  |  | Institution or company. |
| Department | `department` | str |  |  | Department or group. |
| Phone | `phone` | str |  |  | Optional contact number. |
| Website | `website` | str |  |  | Optional URL; must start with http:// or https://. |
| Address | `address` | str |  |  | Postal address. |
| Notes | `details` | str |  |  | Free-text notes about the account. |
| Administrator | `is_admin` | bool |  |  | Administrators may list, edit and delete users. The server refuses to remove the last one. |
| Allow sign-in without a password | `allow_autologin` | bool |  |  | Convenient on a single-user machine. Administrators may not use it. |

## Source

- Plugin package: `chisurf/plugins/core/user_editor/`
- Manifest: {src}`chisurf/plugins/core/user_editor/manifest.json`
- UI spec: {src}`chisurf/plugins/core/user_editor/gui/users.view.json`
