---
type: Plugin Reference
title: Menu Switch
description: 'Menu Switch This plugin provides a simple toggle to switch between the traditional menu bar and the modern ribbon interface in ChiSurf. Features: - One-click switching between menu and ribbon interfaces - Automatic state detection and switching - Persistent preference saving - Seamless transition without requiring restart The Menu Switch plugin allows users to easily toggle between the traditional menu bar interface and the modern ribbon interface based on their preference or workflow requirements. The current interface state is automatically saved and restored on application startup. This plugin is particularly useful for users who want to quickly switch between interfaces for different tasks or for those who are evaluating which interface works best for their workflow.'
resource: chisurf/plugins/core/menu_switch/
tags: [reference, plugins, menu-switch, setup]
anchor: plugin-menu_switch
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-menu_switch)=
# Menu Switch

Menu Switch  This plugin provides a simple toggle to switch between the traditional menu bar  and the modern ribbon interface in ChiSurf.  Features: - One-click switching between menu and ribbon interfaces - Automatic state detection and switching - Persistent preference saving - Seamless transition without requiring restart  The Menu Switch plugin allows users to easily toggle between the traditional menu bar interface and the modern ribbon interface based on their preference or workflow requirements. The current interface state is automatically saved and restored on application startup.  This plugin is particularly useful for users who want to quickly switch between interfaces for different tasks or for those who are evaluating which interface works best for their workflow.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `menu_switch` |
| Menu path | Setup → **Menu Switch** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/menu_switch/`
- Manifest: {src}`chisurf/plugins/core/menu_switch/manifest.json`
