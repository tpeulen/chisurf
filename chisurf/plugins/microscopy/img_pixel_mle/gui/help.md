# Pixel-wise lifetime MLE

This tool fits a fluorescence decay in **every pixel** of confocal photon images by Poisson maximum likelihood and shows the fitted **lifetime** as a map.
Press **Guide** at the top of the settings window for a walk-through.

## Workflow

1. **CLSM imaging files**: **Add files** (several can be chosen), **Database**, or drop files on the window. **Remove** and **Clear** edit the list; no file is deleted.
2. **IRF file**: the instrument response measurement (the first file is used).
3. Name the **parallel** and **perpendicular** routing channels (space separated, different from each other) and the micro-time window **Fit start** / **Fit stop**
   (in binned channels), the **Micro-time binning** and **Min photons**: a pixel with fewer photons in the fit window is not fitted.
4. Optionally a **Region** file (CLSM Draw regions, a Cellpose segmentation, a label image or a mask) confines the fit to part of the frame.
5. Choose the **Fit model**: fit23 one lifetime plus anisotropy, fit24 bi-exponential, fit25 selects among four fixed lifetimes. Initial values and fixed flags
   are kept separately for each model.
6. **IRF preparation** (threshold and sub-bin shifts), **Fit flags** (2I*, BIFL scatter), **Background** and **Performance** (histogram engine, worker threads) are
   folded away until needed.
7. **Run** fits every file in the background; **Cancel** stops after the current file and keeps the finished ones. Each file's table is written next to it as
   `<stem>_pixel_mle.csv`.

## The map

The **Lifetime map** tab shows tau in ns; **Result** switches between the analysed files, the frame slider scrubs a stack, wheel zooms and a drag pans.
The imaging hub supplies the G factor and the mixing corrections (setup) and the IRF, background and fit range (calibration).

## Further reading

[Scan images](docs/guides/24_scan_images.md), [FLIM phasors](docs/concepts/imaging_flim_phasor.md)
