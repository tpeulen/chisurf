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
| Surfaces | cli, gui, services |
| State namespace | `trace_browser` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `trace_browser.files.list` | no | List TTTR trace files and metadata for a folder. |
| `trace_browser.metadata.get` | no | Load Trace Browser ratings and annotations. |
| `trace_browser.metadata.set` | no | Save Trace Browser ratings and annotations. |
| `trace_browser.traces.load` | no | Load binned trace data for preview. |
| `trace_browser.export.csv` | yes | Export selected traces as CSV files. |
| `trace_browser.contract.describe` | no | Return the Trace Browser RPC contract. |

## Source

- Plugin package: `chisurf/plugins/tttr/trace_browser/`
- Manifest: {src}`chisurf/plugins/tttr/trace_browser/manifest.json`
