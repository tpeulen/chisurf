---
type: Plugin Reference
title: Plots
description: Configure plot appearance, colors, and rendering backend
resource: chisurf/plugins/core/plot_settings/
tags: [reference, plugins, plot-settings, setup]
anchor: plugin-plot_settings
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-plot_settings)=
# Plots

Configure plot appearance, colors, and rendering backend

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `plot_settings` |
| Menu path | Setup → **Plots** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk, gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Rendering Backend

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Active backend | `backend` | choice |  | choices: `backends` | Rendering backend for chiplot panels: emtk is the native renderer, pyqtgraph the legacy one. It is used by plots created after you apply the change. |

### Colors

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Data curve | `color_data` | color |  |  | Colour of the data curve in decay plots. Click the swatch for a colour picker, or type a hex value such as #ffa52f. |
| Model curve | `color_model` | color |  |  | Colour of the fitted model curve. Click the swatch for a colour picker, or type a hex value. |
| Instrument response | `color_irf` | color |  |  | Colour of the instrument response function (IRF). Click the swatch for a colour picker, or type a hex value. |
| Residuals | `color_residuals` | color |  |  | Colour of the weighted residuals panel. Click the swatch for a colour picker, or type a hex value. |
| Autocorrelation | `color_auto_corr` | color |  |  | Colour of the autocorrelation curve. Click the swatch for a colour picker, or type a hex value. |
| Region selector | `color_region_selector` | color |  |  | Colour of the draggable fit-range band. Click the swatch for a colour picker, or type a hex value. |
| Region alpha | `region_alpha` | int |  | 0 … 255 | Opacity of the fit-range band, 0 (invisible) to 255 (solid). |
| Active transparency | `active_transparency` | float |  | 0.0 … 1.0 (step 0.05) | Opacity of the active plot, 0 to 1. |
| Inactive transparency | `inactive_transparency` | float |  | 0.0 … 1.0 (step 0.05) | Opacity of plots that are not active, 0 to 1. |

### Appearance

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Line width | `line_width` | float |  | 0.5 … 10.0 (step 0.5) | Width of the data and model curves, 0.5 to 10 pixels. |
| Axis font size | `font_size` | int |  | 0 … 24 (step 1) | Base point size for ticks, axis labels and titles. 'auto' (0) follows the application font. |
| Grid opacity | `grid_alpha_pct` | int |  | 0 … 100 | Grid line opacity, per cent. |

### Options

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Enable grid | `enable_grid` | bool |  |  | Show grid lines in the plots. |
| Grid on data panel | `show_data_grid` | bool |  |  | Draw the grid on the data (decay) panel. |
| Grid on residuals | `show_residual_grid` | bool |  |  | Draw the grid on the residuals panel. |
| Grid on autocorrelation | `show_acorr_grid` | bool |  |  | Draw the grid on the autocorrelation panel. |
| Fit-range selector | `enable_region_selector` | bool |  |  | Draw the draggable fit-range band on the data panel. |
| Show legend by default | `show_legend` | bool |  |  | Show the legend in new plots. |
| Hide titles | `hide_title` | bool |  |  | Hide plot titles by default. |
| Label axes | `label_axis` | bool |  |  | Show the axis names (counts, t / ns, ...). |

### Node Graphs (Global View)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show grid | `ng_show_grid` | bool |  |  | Show the background grid of a node graph. |
| Grid line width | `ng_line_width` | float |  | 0.0 … 4.0 (step 0.25) | Grid line thickness. Below one pixel draws a hairline; on a HiDPI screen a full pixel doubles to two device pixels and the grid starts to out-weigh the edges drawn on top of it. |
| Grid opacity | `ng_grid_opacity_pct` | int |  | 0 … 100 | Grid line opacity of a node graph, per cent. |
| Grid spacing | `ng_grid_spacing` | int |  | 4 … 96 (step 1) | Distance between the grid lines of a node graph, 4 to 96 pixels. |
| Node size (Global View) | `ng_node_size` | float |  | 6.0 … 30.0 (step 0.5) | The node radius a newly opened Global View starts its own node-size control at. A window that is already open keeps the value its slider holds. |

### Advanced: pyqtgraph Configuration

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Antialiasing | `pg_antialias` | bool |  |  | Use antialiased lines in pyqtgraph plots. |
| Left button pans | `pg_left_button_pan` | bool |  |  | Pan pyqtgraph plots with the left mouse button. |
| Background | `pg_background` | choice |  | choices: k, w, default | pyqtgraph background colour: k black, w white, default the library default. The preview follows it. |
| Foreground | `pg_foreground` | choice |  | choices: d, w, l, k | Axis, tick and label colour (d light grey, w white, l light, k black). Keep it contrasting with the background: matching the two hides every axis. |

## Source

- Plugin package: `chisurf/plugins/core/plot_settings/`
- Manifest: {src}`chisurf/plugins/core/plot_settings/manifest.json`
- UI spec: {src}`chisurf/plugins/core/plot_settings/gui/plot_settings_emtk.view.json`
