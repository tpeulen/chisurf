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
| Surfaces | cli, gui, services |
| State namespace | `tttr_image_browser` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Rating filter | `rating_filter` | choice |  | choices: `rating_filter_options` | Show only files at/above (or exactly at) a star rating. |

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
