---
type: Plugin Reference
title: About ChiSurf
description: ChiSurf's logo, version, developer and contact details.
resource: chisurf/plugins/core/about/
tags: [reference, plugins, about, help]
anchor: plugin-about
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-about)=
# About ChiSurf

ChiSurf's logo, version, developer and contact details.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `about` |
| Menu path | Help → **About ChiSurf** |
| Categories | Help |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Application identity and support details](/concepts/application_identity.md)
- **Workflow** — [Application details for a support request](/guides/103_application_identity.md)

## Source

- Plugin package: `chisurf/plugins/core/about/`
- Manifest: {src}`chisurf/plugins/core/about/manifest.json`
- UI spec: {src}`chisurf/plugins/core/about/gui/about.view.json`
