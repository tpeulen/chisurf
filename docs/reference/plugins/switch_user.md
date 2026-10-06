---
type: Plugin Reference
title: Switch User
description: Switch the active MMFDB user for this ChiSurf session.
resource: chisurf/plugins/core/switch_user/
tags: [reference, plugins, switch-user, setup]
anchor: plugin-switch_user
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-switch_user)=
# Switch User

Switch the active MMFDB user for this ChiSurf session.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `switch_user` |
| Menu path | Setup → **Switch User** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `switch_user` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Server | `server` | str |  |  | Host name or address of the MMFDB server. Type one, or pick a remembered server below. |
| Port | `port` | int |  | 1 … 65535 | Command port of the MMFDB server (1 to 65535). The publish port is the next one. |
| Recent servers | `recent_server` | choice |  | choices: `recent_servers` | The servers you signed in to before, newest first. Picking one fills the server field. |
| User | `user` | str |  |  | The account to sign in as. Type any account name, or pick one below. |
| Select user | `known_user` | choice |  | choices: `offered_users` | The configured account and the desktop accounts. Picking one fills the user field. |
| Password | `password` | password |  |  | The account's password. It is shown as stars and never stored. |
| Save selected user | `save_login` | bool |  |  | Remember this account as the default one for the next start. |
| Log in automatically when allowed | `autologin` | bool |  |  | Keep a session token in the operating system's credential store so the next start signs in without a password. |

## Source

- Plugin package: `chisurf/plugins/core/switch_user/`
- Manifest: {src}`chisurf/plugins/core/switch_user/manifest.json`
- UI spec: {src}`chisurf/plugins/core/switch_user/switch_user_emtk.view.json`
