(plugin-ndxplorer)=
# ndX

Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `ndxplorer` |
| Menu path | Main → Tools → **ndX** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `ndxplorer` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Interactive multidimensional exploration](/concepts/multidimensional_exploration.md)
- **Workflow** — [Exploring & fitting multidimensional data (ndX)](/guides/46_ndxplorer.md), [From a selection to a fit: the ndX analysis bridges](/guides/47_ndxplorer_bridges.md)

## Source

- Plugin package: `chisurf/plugins/ndxplorer/`
- Manifest: {src}`chisurf/plugins/ndxplorer/manifest.json`
