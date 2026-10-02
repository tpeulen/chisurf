---
type: Guide
title: Histogramming micro times per detector and polarization (Histogram-Microtime)
description: Building the VV/VH decay of one or many photon files with Histogram-Microtime — queue files and burst selections, choose the detector and channels, gate, bin and shift, compute, save and transfer to the TCSPC analysis — in the window and from Python.
tags: [guides, tttr, tcspc, decay, polarization, python]
---

# Histogramming micro times per detector and polarization (Histogram-Microtime)

**What you get:** the cumulative decay of the photons you select (VV and VH, and the combined VV + 2G·VH trace), a
one-column file of it, and with one more click a TCSPC dataset in ChiSurf with the right time step, G-factor and
polarization.

Theory: how photons are selected and combined is in {ref}`concept-microtime-histogram`; what the decay is used for is
{ref}`concept-tcspc-lifetime`; the detectors and windows come from the detector setup of
{doc}`87_channel_definition`. The generic decay of a photon file without polarization handling is in
{doc}`73_tttr_decay_and_correlation`.

## 1. Open the tool

**Spectroscopy → Fluorescence decay → Histogram-Microtime**. Two tabs share the left dock, as in the Qt tool:
**Inputs and options** and **Detector definition** (the shared detector editor: reading routine, PIE windows,
detectors, TAC linearization). The decay is on the right and gets the room. **Guide** walks through the tool, **Help**
explains every group.

```{figure} figures/89_microtime_histogram.png
:name: fig-microtime-histogram
:width: 100%

Histogram-Microtime on `BH_SPC132.spc` (Becker & Hickl SPC-130, 183 657 photons) with the *green* detector
(parallel channels 8 and 3, perpendicular channel 0): the VV, VH and combined decays on a logarithmic axis and the
FWHM of the combined trace under the run buttons.
```

## 2. Queue photons

**Files…**, **Folder…** (recursive) and **Database…** (the MMFDB object store) fill the *Photon files* list; you can
also drop files on the window. Untick a file to leave it out; **All**, **None**, **Remove** (the selected row) and
**Clear** act on the list, and a right-click on a row removes it. Headerless SPC files need their subtype in **TTTR
format** (e.g. SPC-130), otherwise Compute says so. The *Burst selections* header unfolds the list of `.bst`/`.bur`
photon-index files; **Find TTTR** looks up to four folders above for the photon files they were made on.

## 3. Detector, channels and gates

Define the detectors in the **Detector definition** tab (or load a saved setup), then choose **Detector**: its
interleaved routing channels fill *Parallel* and *Perpendicular* (editable, comma-separated) and its G-factor fills
**G-Factor**. Untick **Polarization resolved** for one unpolarized stream. **Excitation window** keeps one gate,
**Binning** groups bins. **dt** is read from the file header; typing a value keeps it (**Manual time step**). **VV
shift** and **VH shift** pad or clip a histogram to line the two decays up.

## 4. Compute, save, transfer

**Compute** reads the selected files in the background (**Stop** appears while it runs) and draws the decays; the
**FWHM** of the combined trace is shown beneath the run buttons. **Save** writes the VV bins followed by the VH bins to
*Output* (the name is built from the file, detector and channels and can be edited); **Save as…** asks for another
name; with **Autosave after compute** the file is written as soon as the computation succeeds. **Transfer to ChiSurf**
saves and adds a TCSPC dataset (polarization from the **Polarization** choice, time step, G-factor). The plot
toggles above the decay show or hide each trace and switch the axis between logarithmic and linear; the wheel zooms
and a drag pans.

## Headless

The computation has no GUI dependency:

```python
from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel

model = HistogramModel()
model.set_setup({"detectors": {"green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0}},
                 "windows": {}, "tttr_reading": {}})
model.filetype = "SPC-130"
model.add_paths(["BH_SPC132.spc"])
model.auto_save = False
model.compute()
print(model.cumulative_parallel.sum(), model.cumulative_perpendicular.sum(), model.fwhm_ns)
model.save("decay.dat")
```

## Using it well

- Check the channels of the detector against a quick intensity per channel before believing a VV/VH split: a swapped
  pair inverts the anisotropy.
- Histogram shifts do not wrap; if a decay starts before bin 0 use the photon Micro-time Shifter
  ({doc}`88_microtime_shifter`) instead.
- The combined trace needs the right G; a wrong G tilts it, it does not remove the polarization.

## Known defects

- The legacy Qt window shows a time step of 0.05 ns for SPC data (the detector page's default) where the file header
  says 0.0033 ns; the emtk window uses the header. Its numbers (histograms, FWHM in channels) are identical.
- The Qt window reads a `.pto` container with the (disabled) format box value `SPC-130`, which is wrong for a container;
  the emtk window reads it with the container's own header.

## See also

{doc}`73_tttr_decay_and_correlation` · {doc}`88_microtime_shifter` · {doc}`87_channel_definition` ·
{doc}`/concepts/microtime_histogram`
