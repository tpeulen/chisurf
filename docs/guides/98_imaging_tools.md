---
type: Guide
title: The imaging workflow in one window (Imaging Tools)
description: How the Imaging Tools hub lists the imaging tools, what the tools share (detector setup, photon source, imaging HDF5, calibration), how Back, Next and Run all walk the numbered steps, and what a tool that fails to open shows.
tags: [guides, imaging, microscopy, hub]
---

# The imaging workflow in one window (Imaging Tools)

**What you get:** one window for the whole imaging workflow. The list on the left holds the tools, the chosen tool
opens on the right, and the hub keeps what they share, so you define the detectors once and choose the photon file once.

## 1. Open the hub

**Imaging → Image Tools**. The window opens on **Browser**. It needs no data to open.

```{figure} figures/imaging_tools.png
:name: fig-imaging-tools
:width: 100%

The hub on **1. Intensity** with a photon file chosen. Left: the **Search** field, the tools, the **Back / Next / Run all**
stepper, **Help** and **Guide**, and the status line. Top right: the tool's name and description, and the shared **Source**
and **HDF5**. Below: the tool itself, here the Intensity step.
```

## 2. The list

| Group | Tools |
| --- | --- |
| Start | **Setup** (detector channels and PIE windows), **Browser** (choose the photon image) |
| Motion, resolution and channels | **Drift**, **Resolution** (FRC), **Flow**, **Tracking**, **Colocalization** |
| The numbered per-pixel steps | **1. Intensity**, **2. Number & Brightness**, **3. Mean Micro-Time**, **4. IRF & BG** (optional), **5. Phasor-FLIM**, **6. Pixel-wise MLE** |
| Below the rule | **CLSM Draw**, **Spot Finder**, **Region MLE**, **PSF Determination**, **CLSM Generator** (a synthetic photon image whose answer is known) |

Type in **Search** to keep the tools whose name or description contains the text. Hover over a tool for what it does;
the same text is the description under the tool's name. A tool marked *pending* has no native version yet and says so
when you open it. If a tool fails to open (a missing dependency), the header shows the reason and the rest of the hub
keeps working.

## 3. What is shared

* **Detector setup.** Define channels and PIE windows once in **Setup**. Every step receives the definition and applies
  it again whenever you change it.
* **Source.** The photon file you choose in **Browser** (or in a step) becomes the **Source** of every later step.
* **HDF5.** **Intensity** creates the shared imaging HDF5; Number and Brightness, Mean Micro-Time, Phasor and MLE add
  their maps to that same file.
* **Calibration.** **IRF & BG** publishes per-detector IRF files, windows and backgrounds to Phasor and Pixel-wise MLE
  (a deep copy: later edits there do not reach a calibration that was already applied).

Each tool keeps its settings, drawn regions and results while you move between tools, and the hub remembers them
between sessions. A file dropped on the window goes to the open tool.

## 4. Moving through the steps

* Click a tool, or use the **Up** and **Down** arrow keys when no field has the keyboard.
* **Back** and **Next** move one tool up or down the list; both are greyed at the ends. The numbered per-pixel steps
  compute on arrival when a source is known.
* **Run all** walks the rest of the numbered steps (Setup to Pixel-wise MLE), each when the previous one has finished
  computing; the button turns into **Stop** while it walks, and a second press stops it after the step in flight. It is
  greyed below the rule and on the last step.

The tools themselves also hand off: **Next** inside a step asks the hub to move to the following step of the pipeline
(Browser, Drift, Resolution, Tracking, then the numbered steps), skipping the tools that are not part of it.

## 5. Help and the guided tour

**Help** explains how setup, calibration and the shared HDF5 are propagated. **Guide** walks through the list, the
search, Setup, Browser, Next and the shared Source line; it waits for you to click the tools it points at. Each tool has
its own **Help** and **Guide**.

## See also

* [Image browser](86_image_browser.md), [Drift correction](43_drift_correction.md), [FRC resolution](51_frc_resolution.md),
  [Particle tracking](50_particle_tracking.md), [Number and brightness](67_number_and_brightness.md),
  [Spot finder](84_spot_finder.md), [Regions](48_regions.md), [Detector setup](87_channel_definition.md).
* [Plugin reference: Image Tools](../reference/plugins/imaging_tools.md)
