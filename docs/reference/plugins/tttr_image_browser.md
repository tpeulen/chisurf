---
type: Plugin Reference
title: Image Browser
description: Browse TTTR files in a folder and preview intensity images for all DetectorWizard-defined detector windows.
resource: chisurf/plugins/tttr/tttr_image_browser/
tags: [reference, plugins, tttr-image-browser, imaging, tools]
anchor: plugin-tttr_image_browser
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_image_browser)=
# Image Browser

Browse TTTR files in a folder and preview intensity images for all DetectorWizard-defined detector windows.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_image_browser` |
| Menu path | Imaging → Tools → **Image Browser** |
| Categories | Imaging, Tools |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `tttr_image_browser` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Files

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Rating filter | `rating_filter` | choice |  | choices: `rating_filter_options` | Show only files at/above (or exactly at) a star rating. |
| Folder | `folder_text` | str |  |  | The opened folder. Use Open folder, or drop a folder on the window. |
| Multiple selection | `multi_select` | bool |  |  | A click on a row adds it to the selection or removes it. Copy raw files and TIFF act on the selection. |
| Rating | `current_rating` | choice |  | choices: 0, 1, 2, 3 | Stars for the file shown (0 clears the rating). Saved at once beside the data in .image_browser_meta.json; the filter above uses it. |

### Toolbar

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Include subfolders | `recursive` | bool |  |  | Also list the files of the sub-folders of the opened folder. Switching it lists the folder again. |

### Display

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Colormap | `colormap` | choice |  | choices: `colormap_options` | Colour scale of the mosaic. |
| Gamma | `gamma` | float |  | 0.1 … 5.0 (step 0.1) | Lift dim structures with a gamma above one. Display only: the pixel values and the exports are unchanged. |
| Auto levels | `auto_levels` | bool |  |  | Map the lowest and the highest pixel value of the mosaic to the ends of the colour scale. Switch it off to set the levels, or drag the two lines in the histogram. |
| Min | `level_low` | float |  | 0.0 … 254.0 (step 1.0) | Lower display level (0 to 254). Needs Auto levels off. |
| Max | `level_high` | float |  | 1.0 … 255.0 (step 1.0) | Upper display level (1 to 255). Needs Auto levels off. |
| Tile labels | `show_labels` | bool |  |  | Write each tile's detector, micro-time range and routing channels on the mosaic. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `tttr_image_browser.files.list` | no | List TTTR image files and metadata for a folder. |
| `tttr_image_browser.metadata.get` | no | Load TTTR Image Browser ratings and annotations. |
| `tttr_image_browser.metadata.set` | no | Save TTTR Image Browser ratings and annotations. |
| `tttr_image_browser.images.load` | no | Load binned image mosaic for preview. |
| `tttr_image_browser.export.tiff` | yes | Export intensity images (per combo) as TIFF stacks. |
| `tttr_image_browser.contract.describe` | no | Return the TTTR Image Browser RPC contract. |

## Theory and workflow

- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_image_browser/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_image_browser/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_image_browser/gui/browser.view.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_image_browser/gui/browser_emtk.view.json`
