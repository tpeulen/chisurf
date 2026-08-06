(plugin-microtime_histogram)=
# Histogram-Microtime

Create and inspect TTTR microtime histograms.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `microtime_histogram` |
| Menu path | Spectroscopy → Fluorescence decay → **Histogram-Microtime** |
| Categories | Spectroscopy, Fluorescence decay, TTTR |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `microtime_histogram` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/microtime_histogram/`
- Manifest: {src}`chisurf/plugins/tttr/microtime_histogram/manifest.json`
