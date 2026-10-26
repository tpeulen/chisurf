---
type: Plugin Reference
title: FRET check
description: 'The single-button measurement check: drop a TTTR file, get a verdict. Is the measurement usable (burst density, multi-molecule events, stability, background)? Which bursts are suspicious? Works with or without ALEX/PIE; cw two-colour is a full citizen. Simple mode is one drop-zone and the verdict; advanced mode exposes editable detection, burst search and corrections, and hands off to ndX and burst analysis. Ported from smfret-web (peulen.xyz/smfret), now at home in ChiSurf.'
resource: chisurf/plugins/burst/fret_check/
tags: [reference, plugins, fret-check, spectroscopy, single-molecule]
anchor: plugin-fret_check
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fret_check)=
# FRET check

The single-button measurement check: drop a TTTR file, get a verdict. Is the measurement usable (burst density, multi-molecule events, stability, background)? Which bursts are suspicious? Works with or without ALEX/PIE; cw two-colour is a full citizen. Simple mode is one drop-zone and the verdict; advanced mode exposes editable detection, burst search and corrections, and hands off to ndX and burst analysis. Ported from smfret-web (peulen.xyz/smfret), now at home in ChiSurf.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fret_check` |
| Menu path | Spectroscopy → Single-Molecule → **FRET check** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | emtk, services |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fret_check.detect` | no | Detect the experiment configuration and routing channels from a TTTR file or a seeded scenario. |
| `fret_check.analyse` | no | Burst detection, corrections and quality control; the job JSON the app runs. |
| `fret_check.qc` | no | The quality verdict alone (burst density, multi-molecule, stability, background). |

## Theory and workflow

- **Theory** — [FRET check — is this smFRET measurement usable?](/concepts/fret_check.md)
- **Workflow** — [Checking an smFRET measurement](/guides/112_fret_check.md)

## Source

- Plugin package: `chisurf/plugins/burst/fret_check/`
- Manifest: {src}`chisurf/plugins/burst/fret_check/manifest.json`
