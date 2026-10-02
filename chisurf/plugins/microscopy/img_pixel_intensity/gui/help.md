# Per-pixel intensity

This tool turns a confocal photon stream into **images of photon counts**: for every detector window, the counts per pixel, the count rate in kHz and the
raw frames. It is also the step that creates the **imaging HDF5** the other per-pixel tools (N&B, mean micro-time, phasor) add their columns to.
If you have never used it, press **Guide** at the top of the settings window.

## Workflow

1. Select a **TTTR file**: type a path and press Enter, press **Browse** or **Database**, or drop a file on the window (a dropped file is loaded and run
   at once). The scanner markers (line start, line stop, frame) are read from the file header.
2. Check the **Detectors** tab: one set of maps is computed for every detector window. Without a setup the single channel-0 window is used. The tab is the
   shared detector editor of the Setup tool; inside the Imaging Tools pipeline the windows of its setup step are used.
3. Press **Run**. The maps are computed in the background (**Cancel** discards the unfinished result). Nothing is recomputed when neither the file nor the
   windows changed.
4. Read the maps: **Intensity**, **Count rate (kHz)** and the **Frames (movie)**. The **Detector window** field chooses the window that is drawn.

## What is computed

For every detector window the parallel, perpendicular and total photon counts per pixel (`N{c}-p-all`, `N{c}-s-all`, `N{c}-all`), the count rate and a
global **Number of Photons** column. The count rate is the total photons divided by the scanner dwell time of the pixel (in seconds) and by 1000, so it is
in kHz; the calibrated background of the detector (kHz, from the IRF and background step) is subtracted and the result is clipped at zero. The count
columns stay raw counts.

## The maps

The colormap, gamma and display levels change only the picture, never the stored numbers. Wheel zooms and a drag pans; **Reset view** shows the whole
image. The **Frames (movie)** tab plays the scanner frames: **Play**, **Loop**, **Stop** and the playback speed (1 to 120 frames per second).

## Writing and handing on

- **Create imaging HDF5** writes the per-pixel table with the back-reference to the photon file. When the pipeline already remembers a file it is written
  there, otherwise a file is asked for.
- **Save container** writes the same table as a pixel-map artifact into the container beside the photon file (the Qt tool did this when it closed).
- **ndX** opens the live table in the explorer; **Back to the maps** returns.
- **Next** remembers the file and the HDF5 and goes on to the next analysis step; it is available inside the Imaging Tools pipeline only.

Closing a computed session flushes the standard HDF5 and the container, as the Qt tool does.

## Further reading

[Scan images](docs/guides/24_scan_images.md)
