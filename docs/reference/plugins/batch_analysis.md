---
type: Plugin Reference
title: Batch-Analysis
description: Apply one pre-optimised template fit to many datasets or files in one pass and export the consolidated results (CSV, DOCX report, per-run ZIP).
resource: chisurf/plugins/core/batch_analysis/
tags: [reference, plugins, batch-analysis, main, tools, analysis]
anchor: plugin-batch_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-batch_analysis)=
# Batch-Analysis

Apply one pre-optimised template fit to many datasets or files in one pass and export the consolidated results (CSV, DOCX report, per-run ZIP).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `batch_analysis` |
| Menu path | Main → Tools → **Batch-Analysis** |
| Categories | Main, Tools, Analysis |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `batch_analysis` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  | Drag-drop files (or add a folder) to fit with the template. |
| Template fit | `selected_fit_name` | choice |  | choices: `fit_names` | The pre-optimised fit whose parameters seed every run. |
| Results CSV | `save_path` | file |  |  | Destination CSV. A DOCX report and a ZIP of per-run exports are written alongside. |

## Theory and workflow

- **Theory** — [Parameter uncertainty: priors, posteriors and sampling](/concepts/parameter_uncertainty.md)

## Source

- Plugin package: `chisurf/plugins/core/batch_analysis/`
- Manifest: {src}`chisurf/plugins/core/batch_analysis/manifest.json`
- UI spec: {src}`chisurf/plugins/core/batch_analysis/batch.view.json`
