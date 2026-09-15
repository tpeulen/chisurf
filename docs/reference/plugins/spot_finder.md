---
type: Plugin Reference
title: Spot Finder
description: Detect spots and regions in imaging data and persist them, with their pixels, into the measurement's container.
resource: chisurf/plugins/microscopy/spot_finder/
tags: [reference, plugins, spot-finder, imaging, detection]
anchor: plugin-spot_finder
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-spot_finder)=
# Spot Finder

Detect spots and regions in imaging data and persist them, with their pixels, into the measurement's container.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `spot_finder` |
| Menu path | Imaging → **Spot Finder** |
| Categories | Imaging, Detection |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `spot_finder` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Detection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Imaging files | `files` | path_list |  |  | Photon or camera image file(s) to detect in. Drag-drop to add. |
| Workflow | `workflow` | choice |  | choices: `workflow_choices` | The recipe. single_molecule is the standard one — the pipeline the Region MLE has always been fitted on. Picking a workflow replaces every setting below with that recipe's; edit them afterwards to deviate from it. |
| Detection name | `name` | str |  |  | Stem the regions are stored under, so two detections of the same field can be compared instead of one replacing the other. |
| Analysis region | `regions` | region_list |  |  | Confines the search. The threshold is computed from these pixels alone, so the rest of the frame does not set it — which is the point of restricting an analysis to one cell or one illuminated patch. Empty = the whole frame. |

### Detector

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Method | `method` | choice |  | choices: `method_choices` | watershed splits objects that touch; threshold does not, which is right when they do not; log and dog measure each spot's own width. |
| Threshold | `threshold` | float |  | -1.0 … 1000000.0 | Intensity level; below 0 computes an Otsu level. For log/dog this is the minimum scale-normalised response instead, which does not follow the image units — read it off a run. |
| Smoothing σ | `sigma` | float |  | 0.0 … 100.0 | Gaussian smoothing before thresholding. Smoothing is what stops a single noisy pixel becoming an object. |
| Peak footprint | `peak_footprint_size` | int |  | 1 … 100 | Square footprint side for the watershed's local-maxima seeds. Larger merges nearby seeds, which is how over-splitting is cured. |

### Spot width (log / dog)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| min σ | `min_sigma` | float |  | 0.1 … 100.0 | Smallest spot width to look for, in pixels. A diffraction-limited spot has σ ≈ 0.21 λ / NA. |
| max σ | `max_sigma` | float |  | 0.1 … 100.0 | Largest spot width to look for, in pixels. |
| Scales | `num_sigma` | int |  | 2 … 100 | Number of scales between them (log only). |
| Overlap | `overlap` | float |  | 0.0 … 1.0 | Spots overlapping by more than this fraction are merged, the larger kept. |

### Filters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Min area (px) | `min_area` | int |  | 1 … 100000 | Smaller regions are dropped. 2 is what separates an object from a hot camera pixel: a spot covers several pixels, a defect covers exactly one. |
| Max area (px) | `max_area` | int |  | 0 … 10000000 | Larger regions are dropped; 0 disables. An aggregate is not a molecule, and it is the one that dominates a brightness histogram. |
| Clear border | `clear_border` | bool |  |  | Drop regions touching the frame edge. A partly-imaged object has a truncated area and a biased centroid — but on a crowded field this can remove most of the data. |

### Pick by clicking

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Fit window (px) | `pick_window` | int |  | 5 … 99 | Side of the square the fit sees. Wide enough to hold background as well as the spot — a window cropped to the spot has no baseline — and narrow enough not to contain the neighbouring spot, which is what pulls a fit sideways. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `spot_finder.detect.run` | yes | Detect regions in one or more images and write them to their containers. |
| `spot_finder.workflow.list` | no | Return the shipped detection workflows, the standard one first. |
| `spot_finder.workflow.prepare` | no | Resolve detection inputs from a cross-plugin workflow context, without running. |
| `spot_finder.contract.describe` | no | Return the RPC contract. |

## Source

- Plugin package: `chisurf/plugins/microscopy/spot_finder/`
- Manifest: {src}`chisurf/plugins/microscopy/spot_finder/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/spot_finder/gui/spot_finder.view.json`
