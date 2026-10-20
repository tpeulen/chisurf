---
type: Guide
title: The imaging pipeline in one window (Image Tools)
description: How Image Tools lists the steps of the imaging pipeline, which tools are buttons of their own, what the steps share (detector setup, photon source, imaging HDF5, calibration), how Back, Next and Run all walk the numbered steps, and what a tool that fails to open shows.
tags: [guides, imaging, photons, calibration]
---

# The imaging pipeline in one window (Image Tools)

**What you get:** one window for the imaging pipeline. The list on the left holds the steps, the chosen step opens on
the right, and the window keeps what they share, so you define the detectors once and choose the photon file once.

```{figure} figures/ribbon_spectroscopy_imaging.png
:name: fig-ribbon-spectroscopy-imaging
:width: 100%

The Spectroscopy ribbon's Imaging group: Image Tools and the four imaging tools that are buttons of their own (CLSM
Generator, Drift Correction, PSF Determination, Particle Tracking). Where the ribbon is too narrow the group collapses
into one button whose menu lists them.
```

Standalone: `pixi run -e test python -m chisurf.emtk --plugin imaging_tools`.

## 1. Open the window

**Spectroscopy → Imaging → Image Tools**. The window opens on **Browser**. It needs no data to open.

```{figure} figures/imaging_tools.png
:name: fig-imaging-tools
:width: 100%

Image Tools on **1. Intensity** with `test/data/clsm/Leica_SP8.ptu` as source and a one-detector setup on routing
channel 1, after the background precompute (*Imaging steps ready.*). Left: the **Search** field, the tools, the
**Back / Next / Run all** stepper, **Help** and **Guide**, and the status line. Top right: the tool's name and
description, and the shared **Source** and **HDF5** (none created yet). Below: the tool itself, here the Intensity step.
```

## 2. The list

| Group | Steps |
| --- | --- |
| Start | **Setup** (detector channels and PIE windows), **Browser** (choose the photon image) |
| Resolution, motion and channels | **Resolution** (FRC), **Flow**, **Colocalization** |
| The numbered per-pixel steps | **1. Intensity**, **2. Number & Brightness**, **3. Mean Micro-Time**, **4. IRF & BG** (optional), **5. Phasor-FLIM**, **6. Pixel-wise MLE** |
| Below the rule | **CLSM Draw**, **Spot Finder**, **Region MLE** |

Every listed step consumes the shared context of §3: the Setup's detector windows, the Browser's source, the imaging
HDF5 or the IRF & BG calibration. Tools that read their own input and take none of it are buttons of their own in
**Spectroscopy → Imaging**, each in its own window: **Drift Correction** (align a stack and export it before the maps
are built), **Particle Tracking**, **PSF Determination** and **CLSM Generator** (a synthetic photon image whose answer
is known; open the file it writes in Browser).

Type in **Search** to keep the tools whose name or description contains the text. Hover over a tool for what it does;
the same text is the description under the tool's name. A tool marked *pending* has no native version yet and says so
when you open it. If a step fails to open (a missing dependency), the header shows the reason and the rest of the
window keeps working.

## 3. What is shared

* **Detector setup.** Define channels and PIE windows once in **Setup**. Every step receives the definition and applies
  it again whenever you change it.
* **Source.** The photon file you choose in **Browser** (or in a step) becomes the **Source** of every later step.
* **HDF5.** **Intensity** creates the shared imaging HDF5; Number and Brightness, Mean Micro-Time, Phasor and MLE add
  their maps to that same file.
* **Calibration.** **IRF & BG** publishes per-detector IRF files, windows and backgrounds to Phasor and Pixel-wise MLE
  (a deep copy: later edits there do not reach a calibration that was already applied).

Each step keeps its settings, drawn regions and results while you move between steps, and the window remembers them
between sessions. A file dropped on the window goes to the open tool.

## 4. Moving through the steps

* Click a tool, or use the **Up** and **Down** arrow keys when no field has the keyboard.
* **Back** and **Next** move one tool up or down the list; both are greyed at the ends. The numbered per-pixel steps
  compute on arrival when a source is known.
* **Run all** walks the rest of the numbered steps (Setup to Pixel-wise MLE), each when the previous one has finished
  computing; the button turns into **Stop** while it walks, and a second press stops it after the step in flight. It is
  greyed below the rule and on the last step.
* **Background precompute.** As soon as a photon source is chosen, the window computes Intensity, Number & Brightness,
  Mean Micro-Time and Phasor in the background, one after the other (they share one imaging HDF5), so the tabs show
  finished maps when you arrive. Changing the detector setup makes those maps stale and they are recomputed with the
  new detector windows; the status line reads *Computing imaging steps in background ...* and then *Imaging steps ready.*

The steps themselves also hand off: **Next** inside a step moves to the following step of the pipeline (Browser,
Resolution, then the numbered steps), skipping Flow, Colocalization and the steps below the rule.

## 5. Help and the guided tour

**Help** explains how setup, calibration and the shared HDF5 are propagated. **Guide** walks through the list, the
search, Setup, Browser, Next and the shared Source line; it waits for you to click the tools it points at. Each tool has
its own **Help** and **Guide**.

## See also

* [Image browser](86_image_browser.md), [FRC resolution](51_frc_resolution.md), [Colocalization](38_colocalization.md),
  standalone: [Drift correction](43_drift_correction.md), [Particle tracking](50_particle_tracking.md),
  [CLSM generator](98_clsm_generator.md); [Number and brightness](67_number_and_brightness.md),
  [Spot finder](84_spot_finder.md), [Regions](48_regions.md), [Detector setup](87_channel_definition.md).
* [Plugin reference: Image Tools](../reference/plugins/imaging_tools.md)

## Theory

- [Detector setups](../concepts/detector_setup.md): the shared detector definition the window keeps.
- [FLIM and the phasor](../concepts/imaging_flim_phasor.md): what the numbered imaging steps compute.
