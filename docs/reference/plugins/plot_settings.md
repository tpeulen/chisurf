---
type: Plugin Reference
title: Plots
description: 'How fit plots look: curve colours and width, fit-range band, global fits, axes and grid, with a live preview'
resource: chisurf/plugins/core/plot_settings/
tags: [reference, plugins, plot-settings, setup]
anchor: plugin-plot_settings
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-plot_settings)=
# Plots

How fit plots look: curve colours and width, fit-range band, global fits, axes and grid, with a live preview

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `plot_settings` |
| Menu path | not in the menus (opened from a hub or another tool); display name Setup → **Plots** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Curves

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Data | `color_data` | color |  |  | Colour of the measured data. Click the swatch for a colour picker, or type a hex value such as #ffa629. |
| Model | `color_model` | color |  |  | Colour of the fitted model curve, drawn over the data in the fit range. |
| IRF | `color_irf` | color |  |  | Colour of the instrument response function (IRF). |
| Residuals | `color_residuals` | color |  |  | Colour of the weighted residuals, (data − model) / σ, in the strip above the data. |
| Autocorrelation | `color_auto_corr` | color |  |  | Colour of the autocorrelation of the residuals, the top strip: flat for a good fit, a wave for a systematic misfit. |
| Line width | `line_width` | float |  | 0.5 … 10.0 (step 0.5) | Width of the model, IRF, residual and autocorrelation curves. The noisy data trace is drawn at half of it, so the model stays visible through it. |

### Fit range

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show fit-range band | `enable_region_selector` | bool |  |  | Draw the draggable fit-range band on the data panel. Off, the range is still used; it is set in the fit's own controls. |
| Colour | `color_region_selector` | color |  |  | Colour of the fit-range band. |
| Opacity | `region_alpha` | int |  | 0 … 255 | Opacity of the fit-range band, 0 (invisible) to 255 (solid). Much above 60 it reads as a fill and hides the data under it. |

### Global fits

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Selected fit | `active_transparency` | float |  | 0.0 … 1.0 (step 0.05) | Opacity of the curves of the selected dataset, 0 (invisible) to 1 (solid). |
| Other fits | `inactive_transparency` | float |  | 0.0 … 1.0 (step 0.05) | Opacity of the curves of the other datasets of the group, 0 (invisible) to 1 (solid). The preview shows a second dataset at this opacity. |

### Axes and grid

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Axis text | `font_size` | int |  | 0 … 24 (step 1) | Point size of the tick numbers, axis names and legend. 'auto' (0) follows the interface font of Settings ▸ Fonts. Open plots follow at once. |
| Grid strength | `grid_alpha_pct` | int |  | 0 … 100 | How strongly the grid is drawn: 0 % none, 30 % the theme's own grid, 100 % solid lines. |

### Show

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Axis names | `label_axis` | bool |  |  | Show the axis names (counts, time, w.res., a.corr.). Off gives the space to the data in a narrow panel. |
| Legend | `show_legend` | bool |  |  | Show the legend naming each curve on the data panel of new plots. |
| Grid | `enable_grid` | bool |  |  | Draw grid lines. Off turns the grid off on every panel; on, the three switches below pick the panels. |
| Grid on data | `show_data_grid` | bool |  |  | Draw the grid on the data panel. |
| Grid on residuals | `show_residual_grid` | bool |  |  | Draw the grid on the weighted-residuals strip. |
| Grid on autocorrelation | `show_acorr_grid` | bool |  |  | Draw the grid on the autocorrelation strip. |

### Node graphs

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show grid | `ng_show_grid` | bool |  |  | Show the background grid of a node graph. |
| Grid line width | `ng_line_width` | float |  | 0.0 … 4.0 (step 0.25) | Grid line thickness. Below one pixel draws a hairline; on a HiDPI screen a full pixel doubles to two device pixels and the grid starts to out-weigh the edges drawn on top of it. |
| Grid opacity | `ng_grid_opacity_pct` | int |  | 0 … 100 | Grid line opacity of a node graph, per cent. |
| Grid spacing | `ng_grid_spacing` | float |  | 4 … 96 (step 1) | Distance between the grid lines of a node graph, 4 to 96 pixels. |
| Node size | `ng_node_size` | float |  | 6.0 … 30.0 (step 0.5) | The node radius a newly opened Global View starts its own node-size control at. A window that is already open keeps the value its slider holds. |

## Theory and workflow

- **Theory** — [The application shell: settings, interface, account, help and hubs](/concepts/application_shell.md)
- **Workflow** — [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/core/plot_settings/`
- Manifest: {src}`chisurf/plugins/core/plot_settings/manifest.json`
- UI spec: {src}`chisurf/plugins/core/plot_settings/gui/plot_settings_emtk.view.json`
