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

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| All photons | `show_all_photons` | bool |  |  | Show the diagnostic layers computed from every photon in the range. |
| Selected photons | `show_selected_photons` | bool |  |  | Show the diagnostic layers computed from the photons the burst search kept. |
| First photon | `photon_first` | int |  | 0 … 99999999 | First photon index to process. 0 is the start of the file. |
| Last photon | `photon_last` | int |  | 0 … 99999999 | Last photon index to process. The default is the end of the file. |

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
- UI spec: `chisurf/plugins/burst/burst_selection/gui/burst_display.view.json`
