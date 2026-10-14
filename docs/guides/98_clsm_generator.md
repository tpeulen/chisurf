---
type: Guide
title: 'CLSM Generator: a scan whose answer is known'
description: Generate confocal photon scans from brightness and per-detector lifetime maps, then inspect and export them.
tags: [guides, photons, tcspc, lifetime]
---

# CLSM Generator: a scan whose answer is known

**Tool:** *Spectroscopy → Imaging → Image Tools*, then **CLSM Generator** (`clsm_generator`). It simulates the photon stream of a confocal lifetime scan from maps
you provide: a brightness image and one **fluorescence lifetime map per detector**. Because you chose the lifetimes, the
result is a test for the analysis tools ([pixel MLE](24_scan_images.md), [CLSM-Draw](24_scan_images.md), the
[Spot Finder](84_spot_finder.md)): they must give back what you put in.

```{figure} figures/98_clsm_generator.png
:width: 100%

Two detectors (lifetimes 2 and 3 ns with gradients) and a brightness image of two blobs: the reconstructed intensity of the
simulated photons (129,201), in the Maps window.
```

## 1. Inputs
**Intensity image** loads the relative brightness (TIFF, NPY or NPZ). **Add lifetime maps** adds the lifetime map (in ns) of
each detector in detector order; **Database lifetime maps** picks registered datasets; **Remove selected** and **Clear maps**
edit the list (dropping files on the window does the same: the first drop is the intensity image, later ones lifetime maps).
All maps must have the same shape.

## 2. Simulation
The folded **Simulation** panel sets the physical pixel size, the dwell time, the number of micro-time channels and their width,
the peak photon emission rate, the Gaussian IRF (centre, sigma) and the number of lifetime and intensity
quantization levels. **Generate** runs the simulation in the background (**Cancel generation** discards its result); the
status line reports the photon count.

## 3. Look and save
The **Map** choice in the Maps window browses the input brightness, each detector's lifetime and the reconstructed intensity;
the colormap, gamma and levels are the image canvas's. **Save photon stream** writes the photons as `.pto` (with the embedded
intensity), `.npz`, `.ptu`, `.spc` or `.ht3` (the **Output format** choice) and the reconstructed intensity as a TIFF; **Save /
Load settings** keep the inputs and parameters as JSON. A `.pto` or `.ptu` carries the scan grid and marker channels in
its header and its macro clock is the laser period (`n_micro · dt`), so the saved file opens in every Image Tools step
as it is (drop it on *1. Intensity*); a `<stem>.json` beside it declares the scanner for the `.spc` and `.ht3` formats,
which only CLSM Draw, the Spot Finder and Region MLE read. **Guide** walks through the whole sequence, **Help** is the reference.

## Saved settings and what the numbers mean

The window opens at 1100 × 720; a saved geometry wins. Input paths, simulation parameters, output format and display
preferences are restored on reopening (the content of **Save settings**); press **Generate** to recompute the photons.

**Brightness** sets an emission rate per detector at the brightest input
pixel, rather than a guaranteed count in that pixel. Detected counts also
depend on dwell and the excitation profile. Dwell is rounded to whole 10 ms
integration windows, with a minimum of one window. Use multiples of 0.01 s
when an exact requested exposure matters. The simulator's default random seeds are 12345 and 54321, so unchanged maps
and parameters repeat the same stream. Finite photon counts, map quantization and the excitation period must be included
when comparing fitted lifetimes with the input maps.

## Theory

- [Point spread function](../concepts/point_spread_function.md): the focus that shapes the simulated scan.
- [FLIM and the phasor](../concepts/imaging_flim_phasor.md): how the lifetime maps you put in come back out of the scan.
