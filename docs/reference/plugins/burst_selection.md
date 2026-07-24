(plugin-burst_selection)=
# Burst Selection

Burst selection and FRET analysis for single-molecule fluorescence data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_selection` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Selection** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 2.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_selection` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_selection.jobs.analyze_files` | yes | Run burst selection analysis over TTTR files. |
| `burst_selection.results.inspect_bur` | no | Inspect a saved ChiSurf .bur file. |
| `burst_selection.gmm.fit` | no | Fit a GMM to features extracted from a .bur file. |
| `burst_selection.diagnostics.load` | no | Run photon filtering and burst finding for diagnostic plots. |
| `burst_selection.contract.describe` | no | Return the Burst Selection workflow contract. |

## Source

- Plugin package: `chisurf/plugins/burst/burst_selection/`
- Manifest: `chisurf/plugins/burst/burst_selection/manifest.json`
