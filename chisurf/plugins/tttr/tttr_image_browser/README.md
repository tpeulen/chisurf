# TTTR Image Browser Plugin

An interactive browser for folders of TTTR (time-tagged time-resolved) scan files.

## Features

- A folder (or a dropped folder, with subfolders on request) of photon files, listed with size and rating; text filter,
  sortable columns, rating filter, single and multiple selection.
- For the selected file the intensity image of every detector window of the detector setup, as a mosaic of tiles with the
  detector, micro-time range and routing channels on each tile (summed over frames, 8 bit).
- Mouse-wheel zoom and drag pan, colormap, gamma, display levels (a histogram with two draggable lines, or typed Min and
  Max) and tile labels.
- Star rating (0 to 3) and annotation per file, saved in `.image_browser_meta.json` beside the data.
- Export: copy of the raw files, TIFF stacks per detector window, Word report of the listed files.
- A hand-off of the picked image to the Intensity step of Imaging Tools.

## Usage

- Open the plugin from the ChiSurf **Imaging → Tools → Image Browser** menu (the emtk window; the Qt tool in
  `gui/tool.py` is kept until it is removed).
- The **Detector setup** tab is the shared setup editor; **Use setup and continue** applies it. Without a setup the
  browser lists every supported file type and draws one tile with all channels.
- Open or drop a folder, pick a file, inspect, rate, annotate and export.
- Command line: `tttr-image-browser list|load|export-tiff|contract` (see `cli/main.py`).

The guide is `docs/guides/86_image_browser.md`. The Qt-free model is `gui/model.py` (it extends the view model of the Qt tool,
`gui/view_model.py`); the emtk window is `gui/app.py` with its spec `gui/browser_emtk.view.json`.
