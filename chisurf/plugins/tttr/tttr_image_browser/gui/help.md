# TTTR Image Browser

Browse a folder of photon files (TTTR) and look at what each detector saw. For the selected file the browser draws one
tile per detector of the detector setup: the intensity image of the detector's routing channels and micro-time windows,
summed over all frames, scaled to 8 bit. The tiles are laid out as a mosaic with the detector, micro-time range and
routing channels written on each tile.

## Detector setup

The Detector setup tab is the shared setup editor (routing channels, PIE windows, reading routine, TAC corrections,
optical setup). Press Use setup and continue to use its settings for the tiles; the file list then shows only the file
types the setup reads. Without a setup the browser lists every supported file type and draws one tile with all channels.

## Files

Press Open folder or drop a folder on the window. Include subfolders lists the files below it as well. The list
has a filter box (any text in a row), sortable columns and a Rating filter (all, at least 1, 2 or 3 stars, or only
unrated). A click selects a file; with Multiple selection a click adds or removes a row, Select all takes every
row the filters show.

Ratings (0 to 3 stars) and the Annotation are saved at once in .image_browser_meta.json in the opened folder.
Reconstructed mosaics are cached in .tttr_image_cache folders; Clear caches deletes them.

## The image

Scroll the mouse wheel over the mosaic to zoom and drag to pan; Reset view shows it all. Colormap, Gamma
and the levels change how the 8-bit mosaic is drawn, never its values. The histogram beside the image shows the pixel
values; drag its two lines to set Min and Max (Auto levels then switches off).

## Exports

* Copy raw files copies the selected source files into a folder you choose, keeping their paths relative to the
  opened folder.
* TIFF writes the intensity stack (frames, y, x) of every detector window of the selected files.
* DOCX writes a Word report of every listed file: name, rating, annotation and the mosaic. It starts in the opened
  folder as <folder>.docx.
* Next → Intensity sends the current image to the imaging pipeline; it is available when the browser runs in
  Imaging Tools.

## Command line

    tttr-image-browser list FOLDER [--recursive]
    tttr-image-browser load FILE [--max-side 512]
    tttr-image-browser export-tiff FILE [FILE ...] --output-dir DIR
    tttr-image-browser contract

Further reading: [Scan images](docs/guides/24_scan_images.md).
