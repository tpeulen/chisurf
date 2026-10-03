---
type: Guide
title: IRF and background calibration of an imaging detector (IRF & BG)
description: Calibrating one detector for the phasor and pixel-wise MLE steps - choosing the source photons, adding IRF files, dragging the fit, IRF and background windows on the decay, typing backgrounds and shifts, and applying the result to the pipeline.
tags: [guides, imaging, microscopy, calibration, irf]
---

# IRF and background calibration of an imaging detector (IRF & BG)

**What you get:** for each detector of an imaging measurement, an instrument response function (IRF) built from your IRF
photon files, the micro-time windows the analysis uses, the background counts to subtract, and the shifts that align the
IRF to the data. **Phasor-FLIM** (step 5) and **Pixel-wise MLE** (step 6) use this calibration; without it they use the
raw data. The step is optional: skip it in the imaging workflow to calibrate nothing.

The calibration is a step of the [Imaging Tools hub](98_imaging_tools.md) (**4. IRF & BG**), and the window also opens
on its own (**Imaging → IRF & BG**).

## 1. Choose the photons and the detector

```{figure} figures/img_calibration.png
:name: fig-img-calibration
:width: 100%

IRF & BG on real photons (the micro-time shifter's demo SPC as both source and IRF; detector *green* from channel 0
parallel and channel 8 perpendicular). Left: the toolbar, the source, the **Calibration** form and **Apply →**. Right:
the decay and the IRF on a log axis with the draggable windows tagged **Fit**, **IRF** and **BG**.
```

1. **Open TTTR…** chooses the source photon file whose decay is shown. In the hub the source is the one chosen in
   **Browser**, and the detectors are the ones defined in **Setup**; the window says *Configure detector windows in
   Imaging Tools* until a detector exists.
2. **Detector** picks the detector to calibrate; every setting below is kept per detector.

## 2. Add the IRF

**IRF files (this detector)** lists the photon files that make up the IRF. **Files…** opens a multi-select chooser,
**Database…** picks files from the MMFDB object store, **Remove** deletes the selected row, **Clear** empties the list, and
a file dropped on the window is added. The files are summed using the detector's parallel and perpendicular channels. With
no IRF file the raw data are used (the list says so).

## 3. Windows, backgrounds, shifts

| Field | Meaning |
| --- | --- |
| **Conv start / Conv stop** | the convolution / fit window in micro-time channels (the blue **Fit** boundaries on the decay) |
| **IRF start / IRF stop** | the window of the IRF (the green **IRF** boundaries) |
| **Background VV (∥) / VH (⊥)** | background counts per micro-time bin subtracted from each IRF; the grey **BG** interval estimates them from the source decay; **0** uses the IRF's automatic baseline |
| **Shift VV / VH (ch)** | circular shift of each IRF in micro-time channels; fractions are allowed |

Type a number and press Enter, step with the arrows, or drag a boundary on the plot. The raw histograms are cached, so
changing a shift or a background does not read the photons again; **Refresh** bins them again after you correct the
source files. Each IRF has its background subtracted, is shifted, clipped to non-negative values and normalised to unit
sum; the plot scales each normalised IRF to the peak of the decay so the two can be compared.

## 4. Apply

**Apply →** publishes every detector's IRF files, windows, shifts and backgrounds to Phasor-FLIM and Pixel-wise MLE as a
snapshot: edits you make afterwards do not reach a calibration that was already applied until you apply again. An empty
window or a negative background is refused, and the reason appears in the window. In the hub, **Next ▶** applies and goes
on to the next step.

## 5. Help and the guided tour

**Help** explains the windows and where the calibration goes; **Guide** walks through choosing the photons, adding the
IRF and applying; it waits for you to press **Open TTTR…** and **Apply →**.

## See also

* [The imaging workflow in one window](98_imaging_tools.md), [Confocal scan images](24_scan_images.md).
* [Plugin reference: IRF & BG](../reference/plugins/img_calibration.md)
