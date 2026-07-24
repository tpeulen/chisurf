(plugin-tttr_time_windows)=
# TTTR→Time-Window BIDs

Split TTTR files into fixed-duration time-window BID (.bst) files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_time_windows` |
| Menu path | Tools → Converter → **TTTR→Time-Window BIDs** |
| Categories | Tools, Converter |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `tttr_time_windows` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `tttr_time_windows.jobs.analyze_files` | yes | Split TTTR files into fixed-duration time-window BIDs. |
| `tttr_time_windows.contract.describe` | no | Return the Time Window Bins workflow contract. |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_time_windows/`
- Manifest: `chisurf/plugins/tttr/tttr_time_windows/manifest.json`
