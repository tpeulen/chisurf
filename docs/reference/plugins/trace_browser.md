---
type: Plugin Reference
title: Trace Browser
description: Browse PTU/TTTR intensity traces from a folder, rate and annotate files, preview traces, and export selected traces.
resource: chisurf/plugins/tttr/trace_browser/
tags: [reference, plugins, trace-browser, spectroscopy, single-molecule]
anchor: plugin-trace_browser
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-trace_browser)=
# Trace Browser

Browse PTU/TTTR intensity traces from a folder, rate and annotate files, preview traces, and export selected traces.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `trace_browser` |
| Menu path | Spectroscopy → Single-Molecule → **Trace Browser** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `trace_browser` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Precompute after scan | `precompute_after_scan` | bool |  |  | Run the precompute automatically after every scan of a folder, as the Qt browser did. Switch it off for big folders if you only look at a few files. |
| Folder | `folder_text` | str |  |  | The folder whose files are listed. Use Open, or drop a folder on the window. |
| Include subfolders | `include_subfolders` | bool |  |  | Also list the files in the sub-folders of the opened folder (the .trash folder is never listed). Switching it rescans the folder. |
| Filter | `rating_filter` | choice |  | choices: `filter_label_list` | Show only the files whose rating passes: all, at least 1, 2 or 3 stars, or only unrated files. |
| Bin window [ms] | `window_ms` | float |  | 0.001 … 10000.0 (step 0.1) | Width of the time bins of the intensity trace in milliseconds. Changing it loads the trace of the selected file again. |
| Y min | `y_min` | float |  | -1000000000.0 … 1000000000000.0 (step 100.0) | Lower limit of the trace plot's y axis (counts per bin). Entered the wrong way round with Y max, the two are swapped. |
| Y max | `y_max` | float |  | -1000000000.0 … 1000000000000.0 (step 100.0) | Upper limit of the trace plot's y axis (counts per bin). |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `trace_browser.files.list` | no | List TTTR trace files and metadata for a folder. |
| `trace_browser.metadata.get` | no | Load Trace Browser ratings and annotations. |
| `trace_browser.metadata.set` | no | Save Trace Browser ratings and annotations. |
| `trace_browser.traces.load` | no | Load binned trace data for preview. |
| `trace_browser.export.csv` | yes | Export selected traces as CSV files. |
| `trace_browser.contract.describe` | no | Return the Trace Browser RPC contract. |

## Theory and workflow

- **Workflow** — [Binned photon traces (MCS)](/guides/22_binned_photon_traces.md)

## Source

- Plugin package: `chisurf/plugins/tttr/trace_browser/`
- Manifest: {src}`chisurf/plugins/tttr/trace_browser/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/trace_browser/gui/trace_browser_emtk.view.json`
