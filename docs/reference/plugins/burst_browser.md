---
type: Plugin Reference
title: Burst Browser
description: Inspect burstwise analysis tables and plots.
resource: chisurf/plugins/burst/burst_browser/
tags: [reference, plugins, burst-browser, spectroscopy, single-molecule]
anchor: plugin-burst_browser
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_browser)=
# Burst Browser

Inspect burstwise analysis tables and plots.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_browser` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Browser** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `burst_browser` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Accurate FRET: correction factors, FRET lines, and where they come from](/concepts/accurate_fret.md), [Single-molecule FRET: burst analysis (E, S, corrections)](/concepts/smfret_bursts.md)
- **Workflow** — [Multi-parameter E–S histograms and correction factors](/guides/14_multiparameter_es.md), [Sending a gated burst population to FCS, TCSPC, PDA or PCH](/guides/52_send_bursts_to_analysis.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_browser/`
- Manifest: {src}`chisurf/plugins/burst/burst_browser/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_browser/gui/burst_browser.view.json`
