---
type: Guide
title: Browsing a folder of scan images (Image Browser)
description: Paging through a folder of confocal photon files with the Image Browser — one tile per detector window, zoom and pan, colormap and levels, star ratings and notes, and raw-copy, TIFF and Word-report exports — in the window, from the command line and from Python.
tags: [guides, imaging, tttr, python, cli]
---

# Browsing a folder of scan images (Image Browser)

**What you get:** a quick look at every photon file of a folder before any
analysis: for the file you pick, one **tile per detector** of the detector
setup (the intensity image made from that detector's routing channels and
micro-time windows), laid out as a mosaic. You rate and annotate files, keep
the good ones with a filter, and copy, export or report the selection. The
browser measures nothing; it decides which files deserve the analysis tools.

Theory: how a confocal photon stream becomes an image, and why gating by
micro time and routing channel separates detectors and excitation windows, is
in {ref}`concept-imaging-flim-phasor` ("Detector windows and the browse view")
and {ref}`concept-photon-container`. The scan-image workflow that follows the
browser is {doc}`24_scan_images`.

## 1. Open the tool

It is the **Browser** step of **Imaging → Image Tools**, and **Next → Intensity** hands the picked
image to the Intensity step. The window has two tabs: **Image browser** (the page it
opens on) and **Detector setup**.

```{figure} figures/image_browser_mosaic.png
:name: fig-image-browser-mosaic
:width: 100%

The Image Browser on `Leica_SP8.ptu` (a Leica SP8 confocal scan, 12 MB, 93
frames) with a two-detector setup: the **green** detector (routing channels 0
and 1) shows the cells, the **red** one (channel 2) saw nothing in this file.
The file list, rating, annotation and the display controls are on the left and
above the image; the histogram on the right is the display levels.
```

## 2. The detector setup

The tiles follow the detector setup. Without one the browser lists every
supported file type and draws **one tile with all channels** (the file is
shown, nothing is gated). To define detectors, open the **Detector setup** tab:
it is the same one-page editor as in *Setup / Channel Definition* ([guide 87](87_channel_definition.md)):
the Setup row, the **TTTR Reading routine** (**File Type**, timing, binning), the
**PIE Windows** and **Detectors** tables, **LUT handling** and **Optical Setup...**.
Press **Use setup and continue** to use the settings; the file list then shows only
the file types the setup reads (a setup that reads **HT3** lists no PTU file).

```{figure} figures/image_browser_setup.png
:name: fig-image-browser-setup
:width: 100%

The shared setup editor on the Detector setup page: the Setup row, the reading routine, the detector table and the LUT handling, in one page (read with a BH SPC-132 measurement).
```

A detector with routing channels `0, 1` and the micro-time range `0:4095`
becomes one tile; all its windows are summed. The tile label says which
detector, micro-time range and channels it is.

## 3. Open a folder

**Open folder** chooses a folder (or drop a folder on the window); **Include
subfolders** also lists the files below it, shown with their relative path
(`sub/Leica_SP5.ptu`). Files are listed in name order with their size and
rating. The **filter** box above the list narrows the rows by any text in them,
a click on a header sorts, and **Rating filter** keeps all files, those with at
least 1, 2 or 3 stars, or only the unrated ones.

A file without an image (not a scan file, or a setup that finds no scanner
markers) says so in the image area instead of showing the previous image.

## 4. Look at the image

The mosaic is drawn from a reconstruction that is cached in a
`.tttr_image_cache` folder beside the data (**Clear caches** deletes it).

* **Scroll the mouse wheel** over the image to zoom about the pointer, **drag**
  to pan, **Reset view** to see everything again (a new file, or a resized
  window, also shows everything).
* **Colormap** (viridis, magma, inferno, plasma, cividis, turbo, gray), **Gamma**
  and the levels change how the picture is drawn, never its values.
* The histogram beside the image shows how the pixel values are spread
  (logarithmic counts). Its two lines are the display levels: drag one, or
  untick **Auto levels** and type **Min** and **Max**.
* **Tile labels** switches the labels off. A tile narrower than its label shows
  a shorter one (detector and channels); zoom in for the whole text.

```{figure} figures/image_browser_zoomed.png
:name: fig-image-browser-zoomed
:width: 100%

Six wheel notches and a drag later: the green tile is enlarged and the pixel
axes follow. The labels stay at the tile corners.
```

The values are 8-bit: each tile is scaled by its own maximum, so brightness
cannot be compared between tiles or between files. Use the TIFF export for
photon counts.

## 5. Rate, annotate, select

* **Rating** 0 to 3 stars and the **Annotation** box are saved at once in
  `.image_browser_meta.json` in the opened folder, keyed by the file's path
  relative to it. A rating shows as stars in the list; the rating filter uses it.
* **Multiple selection** makes a click add a row to the selection or remove
  it; **Select all** takes every row the filters show. A selection of several
  files is what **Copy raw files** and **TIFF** act on.

## 6. Export

| button | writes |
|---|---|
| **Copy raw files** | the selected source files into a folder you choose, paths kept relative to the opened folder |
| **TIFF** | one intensity stack (frames, y, x) per file and detector tile into a folder you choose, e.g. `Leica_SP8_green.tiff` (93 × 512 × 512, 2 710 575 photons) |
| **DOCX** | a Word report of every listed file: name, rating, annotation and the mosaic; it starts as `<folder>.docx` in the opened folder |

The three buttons stay grey until they have something to act on. The DOCX
report is written without any Word library.

## 7. From the command line and Python

```bash
tttr-image-browser list FOLDER [--recursive]
tttr-image-browser load FILE [--max-side 512]
tttr-image-browser export-tiff FILE [FILE ...] --output-dir DIR
tttr-image-browser contract
```

On the Leica SP8 file, `list` prints `Leica_SP8.ptu	12.0 MB	★0`, `load` prints the
mosaic shape (`[512, 512]`, one tile with all channels, no setup given) and
`export-tiff` writes `Leica_SP8_Image.tiff`.

```python
from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

model = ImageBrowserModel()
model.open_folder("scans")                     # lists the files, reads ratings and notes
model.select_file("scans/Leica_SP8.ptu")
model.load_current()                           # reconstruct the mosaic (cached on disk)
mosaic = model.current_image()                 # 8-bit array, tiles side by side
model.rate_2()                                 # saved in scans/.image_browser_meta.json
model.do_export_tiff("tiffs")                  # the stacks of the selected file
```

## 8. Where things go wrong

| symptom | cause |
|---|---|
| the list is empty after **Use setup and continue** | the setup's **TTTR format** reads another extension than the files have |
| every tile is black or one tile shows everything | the detectors' routing channels are not the file's (the SP8 file has channel 1, the SP5 file 0 to 2) |
| a file says "no image could be reconstructed" | it has no scanner markers (a point measurement), or the reading routine is wrong |
| the image looks unchanged after **Clear caches** | the mosaic is rebuilt from the file at once; only the cache was cleared |

## 9. Limits

The detector setup editor offers 8 of the 15 reading routines the Qt
wizard page had (no CZ-RAW, SM, PHOTONS, PHOTON-HDF5, SPC-QC, SPC-600_4096,
BRIGHTEYES-TTR or FLIMLABS); a saved setup that has one keeps it. The
preview is limited to 512 pixels on its longer side. Ratings and notes live in
the data folder, not in ChiSurf's settings.
